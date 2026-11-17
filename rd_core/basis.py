"""薄层与厚层的对照：wiki 概念页、lab 摘要（report.md）引用了推导笔记（labs/NN/notes.md、labs/NN/notes/*.md）的哪几节。

只从现有链接算，不改任何文件，agent 也不用另写什么。网页拿它做两件事：
- 笔记页：被引用的小节标题下注明「这一节是这些薄层的依据」，目录里标出来；
- wiki 页、lab 页：顶上列出「这一页的依据」，按章列出本页引用的小节。

链接有两种写法，都认：网页地址 `#/doc/<路径>?h=<节锚点>`，和相对路径 `../labs/NN/notes.md#节`。
节锚点与网页给标题编的 id 同一套规则（app.js slugId）。没有锚点、但链接文字写了「§7.1」「§6.3、§7」的，
按编号对上笔记里以「7.1」开头的标题（网页点这种链接也跳到那一节）。都对不上的算作引用整份笔记。
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import fm
from .mine import headings

_TARGET = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*<?([^)\s>]+)>?")
_SECNO = re.compile(r"§\s*(\d+(?:\.\d+)*)")
_HEADNO = re.compile(r"^§?\s*(\d+(?:\.\d+)*)\.?(?![\d.])")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")


def is_thick(rel: str) -> bool:
    """推导笔记：labs/<lab>/notes.md，或分章放在 labs/<lab>/notes/ 下的 md。"""
    p = rel.split("/")
    return len(p) >= 3 and p[0] == "labs" and rel.endswith(".md") and (p[2] == "notes.md" or (p[2] == "notes" and len(p) >= 4))


def slug_id(text: str) -> str:
    """与 app.js 的 slugId 相同：小写、空白换成 -、只留字母数字和 -_，最长 80。"""
    s = re.sub(r"\s+", "-", text.strip().lower())
    s = re.sub(r"[^\w\-]", "", s)
    return s[:80] or "sec"


def _heading_text(raw: str) -> str:
    """标题渲染后的文字（网页按它编 id）：链接留文字、去掉加粗与代码记号，公式原样。"""
    s = _WIKILINK.sub(lambda m: m.group(2) or m.group(1), raw)
    s = _LINK.sub(r"\1", s)
    return re.sub(r"\*\*|__|[*`]", "", s)


def heading_ids(body: str) -> list[dict]:
    """h1–h4 的 {level, text, id}；重名标题依次加 -2、-3，与网页一致。"""
    used: dict[str, int] = {}
    out = []
    for level, raw, _ in headings(body):
        hid = slug_id(_heading_text(raw))
        if hid in used:
            used[hid] += 1
            hid = f"{hid}-{used[hid]}"
        else:
            used[hid] = 1
        out.append({"level": level, "text": raw, "id": hid})
    return out


def _targets(src_rel: str, body: str):
    """一页薄层里指向推导笔记的链接：(笔记路径, [节锚点或「§编号」…])；空串表示整份。"""
    base = posixpath.dirname(src_rel)
    for m in _TARGET.finditer(body):
        text, t = m.group(1), m.group(2)
        if t.startswith("#/doc/"):
            p, _, q = t[len("#/doc/"):].partition("?")
            path = "/".join(unquote(x) for x in p.split("/"))
            frag = (parse_qs(q).get("h") or [""])[0]
        elif re.match(r"^[a-zA-Z][\w+.-]*:", t) or t.startswith(("#", "/")):
            continue
        else:
            p, _, frag = t.partition("#")
            path = posixpath.normpath(posixpath.join(base, unquote(p)))
            frag = unquote(frag)
        if path.startswith("..") or not is_thick(path):
            continue
        frag = frag.strip()
        yield path, [frag] if frag else (["§" + n for n in _SECNO.findall(text)] or [""])


def thin_pages(project) -> list[dict]:
    """薄层：wiki 概念页与各 lab 的摘要 report.md。"""
    out = []
    for d in project.wiki_pages():
        out.append({"path": d.path, "kind": "wiki", "route": f"#/wiki/{d.id}", "title": str(d.meta.get("short") or d.title), "body": d.body})
    for lab in project._lab_dirs():
        rep = lab / "report.md"
        if rep.is_file():
            meta, body = fm.read(rep)
            out.append({"path": f"labs/{lab.name}/report.md", "kind": "lab", "route": f"#/labs/{lab.name}",
                        "title": f"lab {_lab_no(lab.name)} 摘要", "body": body})
    return out


def _lab_no(lab_id: str) -> str:
    m = re.match(r"\d+", lab_id)
    return m.group(0) if m else lab_id


def _h1(project, rel: str) -> str:
    try:
        meta, body = fm.read(project.safe_path(rel))
    except (OSError, PermissionError):
        return ""
    m = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    return str((m.group(1) if m else "") or meta.get("title") or "").strip()  # 正文第一行标题比 frontmatter 的 title 更具体


def chapter_title(project, rel: str) -> str:
    """分章笔记里一章的短名：第一行标题，去掉「lab NN notes ·」之类的前缀。"""
    t = _h1(project, rel)
    t = re.sub(r"^lab\s*\d+\s*(notes|笔记)\s*[·・:：]?\s*", "", t, flags=re.I)
    return t or Path(rel).stem


def doc_label(project, rel: str) -> str:
    """「lab 01 笔记」，分章的再加「 · 第 1 章 …」。"""
    p = rel.split("/")
    if not is_thick(rel):
        return _h1(project, rel) or p[-1]
    label = f"lab {_lab_no(p[1])} 笔记"
    return label + (f" · {chapter_title(project, rel)}" if p[2] == "notes" else "")


def chapters(project, rel: str) -> list[dict]:
    """分章笔记的各章（同一个 notes/ 文件夹里的 md，总览 index.md 在前）。"""
    p = rel.split("/")
    if not (is_thick(rel) and p[2] == "notes"):
        return []
    folder = project.safe_path("/".join(p[:-1]))
    files = sorted((x for x in folder.glob("*.md") if not x.name.startswith(".")), key=lambda x: (x.name != "index.md", x.name))
    base = "/".join(p[:-1])
    return [{"path": f"{base}/{x.name}", "title": chapter_title(project, f"{base}/{x.name}")} for x in files]


def _read_ids(project, rel: str) -> list[dict]:
    try:
        return heading_ids(fm.read(project.safe_path(rel))[1])
    except (OSError, PermissionError):
        return []


def _resolve(ids: list[dict], frag: str) -> dict | None:
    if not frag:
        return None
    num = re.fullmatch(r"§\s*(\d+(?:\.\d+)*)\.?", frag)
    if num:
        for h in ids:
            m = _HEADNO.match(h["text"])
            if m and m.group(1) == num.group(1):
                return h
        return None
    for want in (frag, slug_id(frag)):
        for h in ids:
            if h["id"] == want:
                return h
    return None


def cited_by(project, rel: str) -> dict:
    """一份笔记被哪些薄层引用：{"ids": {节 id: [薄层…]}, "whole": [只引整份的薄层…]}。"""
    ids = _read_ids(project, rel)
    by_id: dict[str, list[dict]] = {}
    whole: list[dict] = []
    for page in thin_pages(project):
        ref = {k: page[k] for k in ("kind", "route", "title", "path")}
        for path, frags in _targets(page["path"], page["body"]):
            if path != rel:
                continue
            for frag in frags:
                h = _resolve(ids, frag)
                bucket = by_id.setdefault(h["id"], []) if h else whole
                if ref not in bucket:
                    bucket.append(ref)
    whole = [r for r in whole if not any(r in v for v in by_id.values())]
    return {"ids": by_id, "whole": whole}


def basis(project, rel: str) -> list[dict]:
    """一页薄层引用的推导：按笔记（章）分组，组内各节按它们在笔记里的先后排。路径越出课题目录抛 PermissionError。"""
    project.safe_path(rel)
    try:
        _, body = fm.read(project.safe_path(rel))
    except (OSError, PermissionError):
        return []
    groups: dict[str, dict] = {}
    for path, frags in _targets(rel, body):
        if not project.safe_path(path).is_file():
            continue
        g = groups.get(path)
        if g is None:
            g = groups[path] = {"path": path, "label": doc_label(project, path), "whole": False, "sections": [], "_ids": _read_ids(project, path)}
        for frag in frags:
            h = _resolve(g["_ids"], frag)
            if h is None:
                g["whole"] = True
            elif not any(s["id"] == h["id"] for s in g["sections"]):
                g["sections"].append(h)
    out = []
    for g in groups.values():
        order = {h["id"]: i for i, h in enumerate(g.pop("_ids"))}
        g["sections"].sort(key=lambda s: order.get(s["id"], 0))
        if g["sections"]:
            g["whole"] = False  # 既引了整份又引了具体几节时，只列具体几节
        out.append(g)
    return out


def docnav(project, rel: str) -> dict:
    """文档页的导航数据：标签、同一份笔记的各章、被哪些薄层引用。路径越出课题目录抛 PermissionError。"""
    project.safe_path(rel)
    return {"label": doc_label(project, rel), "chapters": chapters(project, rel),
            **(cited_by(project, rel) if is_thick(rel) else {"ids": {}, "whole": []})}
