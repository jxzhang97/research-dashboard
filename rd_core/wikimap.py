"""wiki 星图：把概念页排成"从左往右读"的星图，坐标在这里算好，前端只负责画。

数据来源：
- `wiki/index.md` 的 `## 小节` 是分区，从左到右按小节顺序排；小节里出现的 [[链接]] 归入该区，
  没编入索引的页放在最后一区。`index`、`notation` 两页不上图。
- 每页 frontmatter：
  - `prereqs:` 读这页之前要先读的页（slug 或标题）。决定从左到右的列、点星后的阅读路线，以及晕染大小；
  - `part_of:` 从属于哪一页，画成那颗星的卫星；
  - `short:` 星图上显示的短名（不写就取标题冒号前的部分）；
  - `hub: true` 总表类页：画成菱形，平时不画它的连线；
  - `map: false` 不上星图。
- 晕染（halo）面积正比于"后面有几页以它为前置"（沿 prereqs 往后能到达的页数）。

布局是确定性的：同样的文件永远得到同样的坐标。没写 prereqs 时退化为按 index 分区排成网格。
"""

from __future__ import annotations

import math
import re

from . import fm
from .project import WIKILINK_RE

EXCLUDE = frozenset({"index", "notation"})
UNINDEXED = "未编入索引"
MAX_ROWS = 4      # 一列最多几颗星，多了拆成几列（没写 prereqs 的 wiki 因此排成网格）
COL = 104         # 列距
GAP = 30          # 分区之间额外的空隙
ROW = 92          # 行距
MARGIN = 76       # 左右留白
TOP = 104         # 第一行星的 y（上面是分区名）
MIN_W = 720
R0, RM = 11.0, 58.0  # 晕染的最小、最大半径
ORBIT = 46        # 卫星到主星的距离
SAT_ANGLES = (-50, 50, -130, 130, -20, 20, -160, 160, -90, 90)


def _as_list(v) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()]


def region_name(heading: str) -> str:
    """'入门：语言模型与 transformer（lab 01）' → '入门'：去掉末尾括号，取冒号前的部分。"""
    s = re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", heading).strip()
    return re.split(r"[：:]", s, maxsplit=1)[0].strip() or s or heading.strip()


def short_name(meta: dict, title: str) -> str:
    s = str(meta.get("short") or "").strip()
    return s or re.split(r"[：:]", title, maxsplit=1)[0].strip() or title


def current_answer(body: str) -> str:
    """正文里 `**当前回答。**` 那一段，去掉链接标记。"""
    m = re.search(r"^\*\*当前回答[。.：:]?\*\*\s*(.+)$", body or "", re.M)
    if not m:
        return ""
    t = WIKILINK_RE.sub(lambda x: (x.group(2) or x.group(1)).strip(), m.group(1).strip())
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)


def text_width(s: str, size: float = 12.0, spacing: float = 0.0) -> float:
    """宋体标签宽度的估计：中文与全角字符一个字号宽，西文大约一半。"""
    w = 0.0
    for ch in s:
        if ord(ch) >= 0x2E80:
            w += size
        elif ch == " ":
            w += size * 0.3
        elif ch.isupper() or ch.isdigit():
            w += size * 0.62
        else:
            w += size * 0.52
    return w + spacing * len(s)


def wrap_label(text: str, maxw: float = 118.0, size: float = 12.0, max_lines: int = 2) -> list[str]:
    """长名字折成至多两行，西文单词不拆；还放不下就在第二行末尾加省略号（全名在点星后的卡片里）。"""
    if text_width(text, size) <= maxw:
        return [text]
    lines, cur = [], ""
    for t in re.findall(r"[A-Za-z0-9_\-–.'’]+\s*|\s+|.", text):
        if cur.strip() and text_width(cur + t, size) > maxw:
            lines.append(cur.rstrip())
            cur = t.lstrip()
        else:
            cur += t
    if cur.strip():
        lines.append(cur.rstrip())
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and text_width(last + "…", size) > maxw:
            last = last[:-1]
        lines = lines[:max_lines - 1] + [last.rstrip() + "…"]
    return lines


# ---------- 图：页、分区、先读关系 ----------
def _regions(project, resolve) -> list[dict]:
    p = project.root / "wiki" / "index.md"
    if not p.exists():
        return []
    _, body = fm.read(p)
    regions, cur, seen = [], None, set()
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*#*\s*$", line)
        if m:
            cur = {"name": region_name(m.group(1)), "full": m.group(1).strip(), "ids": []}
            regions.append(cur)
            continue
        if cur is None or line.startswith("# "):
            continue
        for lm in WIKILINK_RE.finditer(line):
            i = resolve(lm.group(1))
            if i and i not in seen:
                seen.add(i)
                cur["ids"].append(i)
    return [r for r in regions if r["ids"]]


def graph(project) -> dict:
    """页、分区、先读关系，以及要报给 `rd doctor` 的问题（断的 prereqs / part_of、成环）。"""
    pages = {d.id: d for d in project.wiki_pages() if d.id not in EXCLUDE and d.meta.get("map", True) is not False}
    keys: dict[str, str] = {}
    for d in pages.values():
        for k in (d.id, d.title, d.id.split("/")[-1]):
            keys.setdefault(str(k).strip(), d.id)
    resolve = lambda t: keys.get(str(t).strip())  # noqa: E731
    problems: list[str] = []

    regions = _regions(project, resolve)
    placed = {i for r in regions for i in r["ids"]}
    rest = [i for i in pages if i not in placed]
    if rest:
        regions.append({"name": UNINDEXED if regions else "", "full": UNINDEXED if regions else "", "ids": rest})
    reg_of = {i: k for k, r in enumerate(regions) for i in r["ids"]}
    pos = {i: n for n, i in enumerate(i for r in regions for i in r["ids"])}

    nodes: dict[str, dict] = {}
    for i, d in pages.items():
        pre = []
        for t in _as_list(d.meta.get("prereqs")):
            j = resolve(t)
            if j is None:
                problems.append(f"wiki 先读关系指向不存在的页：{d.path} 的 prereqs 里有 {t}")
            elif j == i:
                problems.append(f"wiki 页把自己列为先读：{d.path}")
            elif j not in pre:
                pre.append(j)
        parent = None
        for t in _as_list(d.meta.get("part_of"))[:1]:
            j = resolve(t)
            if j is None:
                problems.append(f"wiki 从属关系指向不存在的页：{d.path} 的 part_of 是 {t}")
            elif j != i:
                parent = j
        links = []
        for m in WIKILINK_RE.finditer(d.body):
            j = resolve(m.group(1))
            if j and j != i and j not in links:
                links.append(j)
        nodes[i] = {"id": i, "title": d.title, "short": short_name(d.meta, d.title), "path": d.path,
                    "region": reg_of[i], "prereqs": pre, "parent": parent, "hub": bool(d.meta.get("hub")),
                    "links": links, "answer": current_answer(d.body)}

    # 卫星只挂在主星上：part_of 链一路往上找到不是卫星的那页
    for n in nodes.values():
        seen = {n["id"]}
        while n["parent"] and nodes[n["parent"]]["parent"] and nodes[n["parent"]]["parent"] not in seen:
            seen.add(n["parent"])
            n["parent"] = nodes[n["parent"]]["parent"]
        if n["parent"] in seen:
            n["parent"] = None

    # 成环的先读关系：报问题，并在算深度时去掉回边
    back, color, stack = set(), {}, []

    def dfs(u):
        color[u] = 1
        stack.append(u)
        for p in nodes[u]["prereqs"]:
            if color.get(p) == 1:
                back.add((u, p))
                cyc = stack[stack.index(p):] + [p]
                problems.append("wiki 先读关系成环：" + " → ".join(reversed(cyc)) + "（这些页的 prereqs 互相指向）")
            elif not color.get(p):
                dfs(p)
        stack.pop()
        color[u] = 2

    for u in sorted(nodes, key=pos.get):
        if not color.get(u):
            dfs(u)
    for n in nodes.values():
        n["prereqs"] = [p for p in n["prereqs"] if (n["id"], p) not in back]

    depth: dict[str, int] = {}

    def dep(u):
        if u not in depth:
            depth[u] = 1 + max((dep(p) for p in nodes[u]["prereqs"]), default=-1)
        return depth[u]

    for u in nodes:
        dep(u)
    for n in nodes.values():
        n["depth"] = depth[n["id"]]
        n["next"] = sorted((m["id"] for m in nodes.values() if n["id"] in m["prereqs"]), key=pos.get)
    for n in nodes.values():
        seen, todo = set(), list(n["next"])
        while todo:
            u = todo.pop()
            if u not in seen:
                seen.add(u)
                todo += nodes[u]["next"]
        n["desc"] = len(seen)
        n["backlinks"] = sum(n["id"] in m["links"] for m in nodes.values())
    first = next((k for k, r in enumerate(regions) if any(not nodes[i]["parent"] and not nodes[i]["hub"] for i in r["ids"])), 0)
    any_pre = any(n["prereqs"] for n in nodes.values())  # 一条先读关系都没写时，谁都不算起点
    for n in nodes.values():
        n["start"] = any_pre and n["region"] == first and not n["prereqs"] and not n["parent"] and not n["hub"]
    return {"regions": regions, "nodes": nodes, "pos": pos, "problems": problems}


def problems(project) -> list[str]:
    return graph(project)["problems"]


# ---------- 布局 ----------
def _box_hit(a, b, pad=0.0) -> float:
    """两个矩形 (x0,y0,x1,y1) 的重叠面积（pad 给一点边距）。"""
    w = min(a[2], b[2]) + pad - max(a[0], b[0])
    h = min(a[3], b[3]) + pad - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def wiki_map(project) -> dict:
    g = graph(project)
    regions, nodes, pos = g["regions"], g["nodes"], g["pos"]
    by_pos = lambda ids: sorted(ids, key=pos.get)  # noqa: E731

    # 每区：主星按深度分列（深度相同的放一列，太多就拆开），总表页另放
    cols_of, hubs_of = [], []
    for r in regions:
        main = [i for i in r["ids"] if not nodes[i]["parent"] and not nodes[i]["hub"]]
        hubs = [i for i in r["ids"] if not nodes[i]["parent"] and nodes[i]["hub"]]
        if not main:
            main, hubs = hubs, []
        cols = []
        for dv in sorted({nodes[i]["depth"] for i in main}):
            col = by_pos(i for i in main if nodes[i]["depth"] == dv)
            k = math.ceil(len(col) / MAX_ROWS)
            size = math.ceil(len(col) / k)
            cols += [col[j:j + size] for j in range(0, len(col), size)]
        cols_of.append(cols)
        hubs_of.append(hubs)

    # x：分区从左到右，区内一列一列排
    X, Y, spans, x = {}, {}, [], 0.0
    for k, cols in enumerate(cols_of):
        if not cols:
            spans.append(None)
            continue
        if any(spans):
            x += GAP
        start = x
        for c in cols:
            for i in c:
                X[i] = x
            x += COL
        spans.append((start, x - COL))
    last = max((s[1] for s in spans if s), default=0.0)
    W = max(MIN_W, last + 2 * MARGIN)
    shift = (W - last) / 2
    X = {i: v + shift for i, v in X.items()}
    spans = [(s[0] + shift, s[1] + shift) if s else None for s in spans]

    # y：每列先居中，再反复往先读/后续邻居的平均高度靠（重心法），同列保持行距
    columns = [c for cols in cols_of for c in cols]
    rows = max((len(c) for c in columns), default=1)
    span = max((rows - 1) * ROW, 3.5 * ROW)
    mid, ylo, yhi = TOP + span / 2, TOP, TOP + span
    # 星少的列拉开行距铺满高度，免得全图挤成一条横带
    gap = {id(c): max(ROW, span / len(c)) if len(c) > 1 else ROW for c in columns}
    for c in columns:
        for j, i in enumerate(c):
            Y[i] = mid + (j - (len(c) - 1) / 2) * gap[id(c)]
    proxy = lambda i: nodes[i]["parent"] or i  # noqa: E731
    nb = {}
    for c in columns:
        for i in c:
            members = [i] + [s for s in nodes if nodes[s]["parent"] == i]
            ns = {proxy(j) for m in members for j in nodes[m]["prereqs"] + nodes[m]["next"]}
            nb[i] = sorted(j for j in ns if j != i and j in X)
    for _ in range(24):
        target = {}
        for c in columns:
            for i in c:
                ys = [Y[j] for j in nb[i]]
                t = Y[i] if not ys else 0.5 * Y[i] + 0.5 * sum(ys) / len(ys)
                target[i] = 0.9 * t + 0.1 * mid
        for c in columns:
            srt = sorted(c, key=lambda i: (target[i], pos[i]))
            ys = [target[i] for i in srt]
            for j in range(1, len(ys)):
                ys[j] = max(ys[j], ys[j - 1] + gap[id(c)])
            d = sum(target[i] for i in srt) / len(srt) - sum(ys) / len(ys)
            ys = [y + d for y in ys]
            d = ylo - ys[0] if ys[0] < ylo else yhi - ys[-1] if ys[-1] > yhi else 0.0
            for i, y in zip(srt, ys):
                Y[i] = y + d

    # 收紧上下留白：最高的星放在 TOP，画布高度按实际最低的星算
    if Y:
        top = min(Y.values())
        Y = {i: y - top + TOP for i, y in Y.items()}
    ymax = max(Y.values(), default=TOP)
    # 总表页：所在分区最右一列的下方
    has_hubs = any(hubs_of)
    hub_y = ymax + 80
    for k, hubs in enumerate(hubs_of):
        for j, i in enumerate(hubs):
            base_x = spans[k][1] if spans[k] else W / 2
            X[i], Y[i] = base_x - j * COL, hub_y
    H = (hub_y + 96) if has_hubs else (ymax + 110)

    def star_r(i):
        n = nodes[i]
        return 4.5 if n["parent"] else 8.0 if n["start"] else 6.5

    # 卫星：绕主星一圈找最空的位置（不压别的星、不压主星的名字、不压连线）
    prereq_edges = [(p, n["id"]) for n in nodes.values() for p in n["prereqs"]]
    for s in by_pos(i for i in nodes if nodes[i]["parent"]):
        p = nodes[s]["parent"]
        px, py = X[p], Y[p]
        lw = text_width(nodes[p]["short"]) / 2 + 6
        best = None
        for n_a, a in enumerate(SAT_ANGLES):
            x, y = px + ORBIT * math.cos(math.radians(a)), py + ORBIT * math.sin(math.radians(a))
            pen = n_a * 0.5
            for q in X:
                if q not in (p, s):
                    d = math.hypot(X[q] - x, Y[q] - y)
                    pen += max(0.0, (40 if nodes[q]["parent"] else 62) - d) * 10
            if abs(x - px) < lw and py + 2 < y < py + star_r(p) + 30:
                pen += 200
            for a_, b_ in prereq_edges:
                if p in (a_, b_) or s in (a_, b_) or a_ not in X or b_ not in X:
                    continue
                if _seg_dist(x, y, X[a_], Y[a_], X[b_], Y[b_]) < 12:
                    pen += 50
            if not (30 < x < W - 30 and 70 < y < H - 60):
                pen += 500
            if best is None or pen < best[0]:
                best = (pen, x, y)
        X[s], Y[s] = best[1], best[2]

    # 名字：默认在星下方，挤了就换到上、右、左
    ids = by_pos(i for i in nodes if not nodes[i]["parent"]) + by_pos(i for i in nodes if nodes[i]["parent"])
    circles = [(X[i] - star_r(i) - 2, Y[i] - star_r(i) - 2, X[i] + star_r(i) + 2, Y[i] + star_r(i) + 2, i) for i in nodes]
    taken, labels = [], {}
    for i in ids:
        n, x, y, r = nodes[i], X[i], Y[i], star_r(i)
        lines = wrap_label(n["short"] + (" · 起点" if n["start"] else ""))
        w, ex = max(text_width(t) for t in lines), 14 * (len(lines) - 1)  # ex：多出来的行高
        cand = {  # (第一行基线 x, y, 对齐, 占位框)
            "below": (x, y + r + 15, "middle", (x - w / 2, y + r + 4, x + w / 2, y + r + 18 + ex)),
            "above": (x, y - r - 8 - ex, "middle", (x - w / 2, y - r - 19 - ex, x + w / 2, y - r - 5)),
            "right": (x + r + 6, y + 4 - ex / 2, "start", (x + r + 6, y - 7 - ex / 2, x + r + 6 + w, y + 7 + ex / 2)),
            "left": (x - r - 6, y + 4 - ex / 2, "end", (x - r - 6 - w, y - 7 - ex / 2, x - r - 6, y + 7 + ex / 2)),
        }
        order = ["above", "right", "left", "below"] if n["parent"] and y < Y[n["parent"]] else ["below", "above", "right", "left"]
        best = None
        for o in order:
            box = cand[o][3]
            hit = sum(_box_hit(box, t, 2) for t in taken) + sum(_box_hit(box, c[:4]) for c in circles if c[4] != i)
            if box[1] < 60 or box[0] < 14 or box[2] > W - 14 or box[3] > H - 14:
                hit += 1000
            if best is None or hit < best[0]:
                best = (hit, o)
            if hit == 0:
                break
        lx, ly, anchor, box = cand[best[1]]
        taken.append(box)
        labels[i] = {"x": round(lx, 1), "y": round(ly, 1), "anchor": anchor, "lines": lines}

    # 晕染：面积 ∝ 后面几页以它为前置
    mx = max((n["desc"] for n in nodes.values()), default=0)
    halo = lambda v: math.sqrt(R0 * R0 + (RM * RM - R0 * R0) * v / mx) if mx else R0  # noqa: E731

    out_regions = []
    for k, r in enumerate(regions):
        if not spans[k] or not r["name"]:
            continue
        cx = (spans[k][0] + spans[k][1]) / 2
        room = spans[k][1] - spans[k][0] + COL - 12
        lines, spacing = [r["name"]], 2
        if text_width(r["name"], 13, 2) > room:
            spacing = 0
            if text_width(r["name"], 13) > room and len(r["name"]) > 3:
                # 太长就折两行，尽量折在空格或"与、和的及"前
                h = len(r["name"]) // 2
                cut = min((j for j, ch in enumerate(r["name"]) if ch in " 与、和的及" and 0 < j < len(r["name"]) - 1),
                          key=lambda j: abs(j - h), default=h)
                lines = [r["name"][:cut].strip(), r["name"][cut:].strip(" 、")]
        out_regions.append({"index": k, "name": r["name"], "full": r["full"], "x": round(cx, 1), "lines": lines, "spacing": spacing})

    see, rel = [], {(p, c) for p, c in prereq_edges} | {(c, p) for p, c in prereq_edges}
    for n in nodes.values():
        for j in n["links"]:
            pair = tuple(sorted((n["id"], j)))
            if (n["id"], j) in rel or n["parent"] == j or nodes[j]["parent"] == n["id"] or list(pair) in see:
                continue
            see.append(list(pair))

    # 能由别的先读间接推出的边（p 已是 c 另一位先读 q 的祖先）平时不画，点到 c 时才画
    anc: dict[str, set] = {}

    def ancestors(u):
        if u not in anc:
            anc[u] = set()
            for p in nodes[u]["prereqs"]:
                anc[u] |= {p} | ancestors(p)
        return anc[u]

    edges = [{"from": p, "to": c, "implied": any(p in ancestors(q) for q in nodes[c]["prereqs"] if q != p)}
             for p, c in prereq_edges]

    out_nodes = []
    for i in by_pos(nodes):
        n = nodes[i]
        out_nodes.append({
            "id": i, "title": n["title"], "short": n["short"], "region": n["region"],
            "x": round(X[i], 1), "y": round(Y[i], 1), "r": star_r(i), "halo": round(halo(n["desc"]), 1),
            "label": labels[i], "parent": n["parent"], "hub": n["hub"], "start": n["start"],
            "prereqs": n["prereqs"], "next": n["next"], "desc": n["desc"], "backlinks": n["backlinks"],
            "depth": n["depth"], "answer": n["answer"],
        })
    return {
        "width": round(W), "height": round(H), "regions": out_regions, "nodes": out_nodes,
        "edges": edges, "see": see,
        "has_prereqs": bool(prereq_edges), "problems": g["problems"],
    }
