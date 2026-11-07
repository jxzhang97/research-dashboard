"""「我的理解」：用户自己对某一节内容的物理图像，用用户的口吻写。

每条一个 markdown 文件，放在 Project Notes 里本课题那一页旁边的「我的理解/」文件夹
（找不到那一页时放在课题目录的「我的理解/」）。网页和 Obsidian 读的是同一份。
frontmatter 记出处：page（项目内路径）、section（节标题原文）、quote（引的那句话，可空）。
网页像夹批一样把它紧跟在出处后面：引了句子就放在那句话所在段落之后（句子下面划朱色虚线），没引句子放在那一节末尾；另有汇总页 #/mine。

理解只由 agent 在用户批准措辞之后用 `rd mine` 写入；网页只显示，没有编辑入口。
理解原文不写进 wiki 或 notes，所以 agent 改写那些页面时碰不到它。
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote as urlquote

from . import config, fm, pnotes

DIRNAME = "我的理解"
AI_PATH = "我的理解.md"  # 给 AI 读的出口 /md/我的理解.md
INDEX_MARK = "<!-- rd:我的理解 -->"

_MATH = re.compile(r"\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_LIST = re.compile(r"^[ \t]*(?:>[ \t]?)*(?:[-+*]|\d+[.)])[ \t]+", re.M)
_HEADING = re.compile(r"^(#{1,4})[ \t]+(.+?)[ \t]*#*[ \t]*$")  # 网页只给 h1–h4 加锚点


def plain(s: str, lists: bool = True) -> str:
    """比对用的纯文字：去掉公式、markdown 记号和所有空白。网页端（app.js plainQuote）用同一套规则在渲染后的正文里找这句话。
    比标题时 lists=False：「1. 两种屏蔽」的编号是标题的一部分，不是列表记号。"""
    s = _MATH.sub("", s or "")
    s = _WIKILINK.sub(lambda m: m.group(2) or m.group(1), s)
    s = _LINK.sub(r"\1", s)
    if lists:
        s = _LIST.sub("", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[\s*`#>|\\]", "", s)


def headings(body: str) -> list[tuple[int, str, int]]:
    """(级别, 标题原文, 行号)，跳过代码块。"""
    out, fence = [], None
    for i, line in enumerate(body.splitlines()):
        st = line.lstrip()
        if st.startswith(("```", "~~~")):
            mark = st[:3]
            fence = None if fence == mark else (fence or mark)
            continue
        if fence:
            continue
        m = _HEADING.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), i))
    return out


def find_section(body: str, want: str, loose: bool = False) -> tuple[str | None, str, list[str]]:
    """按标题找节：比原文（去掉记号后相等，重名取第一个，和网页一样）；loose 时再退一步找唯一包含它的标题（只在新写时帮着找）。
    返回 (标题原文或 None, 这一节的正文, 候选标题)。want 为空表示整页。"""
    lines = body.splitlines()
    if not (want or "").strip():
        return "", body, []
    hs = headings(body)
    pw = plain(want, lists=False)
    exact = [h for h in hs if plain(h[1], lists=False) == pw]
    cands = exact[:1] or ([h for h in hs if pw and pw in plain(h[1], lists=False)] if loose else [])
    if len(cands) != 1:
        return None, "", [h[1] for h in cands]  # 空 = 没有这个标题；多个 = 说得不够完整
    lvl, raw, i = cands[0]
    end = next((j for (l, _, j) in hs if j > i and l <= lvl), len(lines))
    return raw, "\n".join(lines[i + 1:end]), []


def norm_page(page: str) -> str:
    p = (page or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def locate(project, page: str, section: str, quote: str = "", loose: bool = False) -> str:
    """核对出处，返回节标题原文；对不上就抛 ValueError，信息里列出可选的标题。
    loose：新写时允许只说出标题的一部分；核对已有的条目时必须和标题原文一致，免得改名后悄悄挂到别的节。"""
    page = norm_page(page)
    if not page.endswith(".md"):
        raise ValueError(f"出处要是课题里的 markdown 页面：{page}")
    try:
        p = project.safe_path(page)
    except PermissionError:
        raise ValueError(f"出处不在课题目录里：{page}")
    if not p.is_file():
        raise ValueError(f"找不到这一页：{page}")
    _, body = fm.read(p)
    raw, text, cands = find_section(body, section, loose)
    if raw is None:
        what = "有几个标题都含这几个字，说得再完整些" if cands else "这一页没有这个标题"
        raise ValueError(f"{what}：「{section}」。可选的标题：\n" + "\n".join(f"  - {c}" for c in (cands or [h[1] for h in headings(body)])))
    if quote.strip() and plain(quote) not in plain(text):
        raise ValueError(f"「{raw or page}」这一节里找不到引的那句话：「{quote}」（引原文里连续的一段，公式可以省略）")
    return raw


def mine_dir(project) -> Path:
    note = pnotes.find_note(project)
    return (note.parent if note else Path(project.root)) / DIRNAME


def _project_name(project) -> str:
    return str(config.load(Path(project.root))["project"].get("name") or "")


def _q(s: str) -> str:
    return json.dumps(s or "", ensure_ascii=False)


def _slug(title: str) -> str:
    s = re.sub(r"[^\w一-鿿]+", "-", title).strip("-_")
    return (s[:40].rstrip("-_") or "理解")


def route(page: str) -> str:
    """网页上这一页的地址（hash 路由）；与 app.js mineRoute 一致。"""
    parts = page.split("/")
    if parts[0] == "wiki" and page.endswith(".md"):
        return "#/wiki/" + "/".join(urlquote(x) for x in page[5:-3].split("/"))
    if parts[0] == "labs" and len(parts) == 3 and parts[2] == "report.md":
        return "#/labs/" + urlquote(parts[1])
    if parts[:2] == ["references", "cards"] and len(parts) == 3:
        return "#/refs/" + urlquote(parts[2][:-3])
    return "#/doc/" + "/".join(urlquote(x) for x in parts)


def _page_title(project, page: str, cache: dict) -> str:
    if page not in cache:
        title = page
        try:
            meta, body = fm.read(project.safe_path(page))
            m = re.search(r"^#\s+(.+?)\s*$", body, re.M)
            title = str(meta.get("title") or (m.group(1) if m else Path(page).stem))
        except (OSError, PermissionError):
            pass
        cache[page] = title
    return cache[page]


def _read(p: Path) -> dict | None:
    try:
        meta, body = fm.read(p)
    except OSError:
        return None
    if not meta.get("page"):
        return None
    return {
        "id": p.stem, "title": str(meta.get("title") or p.stem), "page": norm_page(str(meta["page"])),
        "section": str(meta.get("section") or ""), "quote": str(meta.get("quote") or ""), "text": body.strip(),
        "created": str(meta.get("created") or ""), "updated": str(meta.get("updated") or meta.get("created") or ""),
        "project": str(meta.get("project") or ""),
    }


def items(project) -> list[dict]:
    """本课题的全部理解，最近改过的在前。同一个文件夹若被几个课题共用，按 frontmatter 的 project 分开。"""
    d = mine_dir(project)
    if not d.is_dir():
        return []
    name = _project_name(project)
    titles: dict = {}
    out = []
    for p in sorted(d.glob("*.md")):
        if p.name.startswith("."):
            continue
        it = _read(p)
        if not it or (it["project"] and name and it["project"] != name):
            continue
        it["page_title"] = _page_title(project, it["page"], titles)
        out.append(it)
    out.sort(key=lambda it: (it["updated"], it["created"], it["id"]), reverse=True)
    return out


def count(project) -> int:
    try:
        return len(items(project))
    except OSError:
        return 0


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.rd-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save(project, *, page: str, section: str, quote: str = "", title: str, text: str, id: str | None = None) -> dict:
    """新增一条（id 为空）或整条改写已有的一条（created 保留）。出处先核对，对不上就抛 ValueError、什么也不写。"""
    page = norm_page(page)
    raw = locate(project, page, section, quote, loose=True)
    text = (text or "").strip()
    title = " ".join((title or "").split())
    if not text:
        raise ValueError("理解的正文是空的")
    if not title:
        raise ValueError("要给这条理解起一个短标题（Obsidian 里的文件名和汇总页用）")
    d = mine_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    if id:
        p = d / f"{id}.md"
        if not p.is_file():
            raise ValueError(f"没有这一条：{id}")
        old = _read(p) or {}
        created = old.get("created") or today
    else:
        created = today
        base = f"{today}-{_slug(title)}"
        p, n = d / f"{base}.md", 2
        while p.exists():
            p, n = d / f"{base}-{n}.md", n + 1
    url = pnotes.dashboard_url(project) + "/" + route(page)
    head = [
        f"title: {_q(title)}", f"project: {_q(_project_name(project))}", f"page: {_q(page)}", f"section: {_q(raw)}",
        f"quote: {_q(' '.join(quote.split()))}", f"dashboard: {_q(url)}", f"created: {created}", f"updated: {today}",
        "tags:", "  - 我的理解",
    ]
    _atomic_write(p, "---\n" + "\n".join(head) + "\n---\n\n" + text + "\n")
    ensure_index(project)
    out = _read(p)
    out["page_title"] = _page_title(project, page, {})
    return out


def check(project) -> list[tuple[dict, str]]:
    """出处对不上的理解（页面被改写、标题改名、引的句子被删）：(条目, 原因)。"""
    bad = []
    for it in items(project):
        try:
            locate(project, it["page"], it["section"], it["quote"])
        except ValueError as e:
            bad.append((it, str(e).splitlines()[0]))
    return bad


INDEX_BLOCK = f"""
## 我的理解

{INDEX_MARK}
```dataview
TABLE WITHOUT ID file.link AS "理解", page AS "页面", section AS "节", updated AS "更新"
WHERE file.folder = this.file.folder + "/{DIRNAME}"
SORT updated DESC
```
"""


def ensure_index(project) -> bool:
    """Project Notes 里本课题那一页末尾加一节「我的理解」，用 Dataview 列出文件夹里的各条；已有就不动。"""
    note = pnotes.find_note(project)
    if not note:
        return False
    before = note.read_text(encoding="utf-8")
    if INDEX_MARK in before:
        return False
    after = before.rstrip("\n") + "\n" + INDEX_BLOCK
    return pnotes._write(note, before, after)


def ai_markdown(project, base: str) -> str:
    """给 AI 读：全部理解按出处分组，带出处链接。"""
    name = _project_name(project)
    out = [f"# 我的理解（{name}）", "", "课题负责人读 wiki、推导时形成的物理图像，用自己的话写。每条注明出处（哪一页、哪一节、引的哪句话）。", ""]
    groups: dict[str, list[dict]] = {}
    for it in items(project):
        groups.setdefault(it["page"], []).append(it)
    for page, arr in groups.items():
        out += [f"## {arr[0]['page_title']}", "", f"出处页面：{base}/md/{urlquote(page)}", ""]
        for it in arr:
            src = f"「{it['section']}」一节" if it["section"] else "全文"
            out += [f"### {it['title']}", "", f"> {src}" + (f"，引：「{it['quote']}」" if it["quote"] else "") + f" · {it['updated']}", "", it["text"], ""]
    return "\n".join(out)
