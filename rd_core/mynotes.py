"""「我的笔记」的正文：课题负责人自己的 LaTeX 笔记，放在课题目录的 mynotes/。

以用户的手写稿为骨架、用户的记号为准；dashboard 的 wiki 和 lab 推导只是补细节时查的素材。
每一批增补：用户的内容照录（黑色），agent 补的细节用 \\orange{…} / orangeblock（橙色），agent 的问题用 \\cmt{…}（蓝色）；
用户批准后 accept 去掉橙色标记、把原稿从 inbox/ 移到 originals/。网页「我的笔记 › 正文」显示 build/main.pdf。
规矩见 skills/rd-mynotes/SKILL.md 和 skel/mynotes/README.md。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path

from . import TEMPLATE_ROOT, fm, pnotes

DIR = "mynotes"
SKEL = TEMPLATE_ROOT / "skel" / "mynotes"
STYLE_NAME = "我的笔记文风.md"  # 各课题共用的文风，放在 Project Notes（Obsidian 题目库）的根目录
SOURCES = ("main.tex", "preamble.tex", "notation.tex", "refs.bib")


def notes_dir(project) -> Path:
    return Path(project.root) / DIR


def exists(project) -> bool:
    return (notes_dir(project) / "main.tex").is_file()


def shared_style(project) -> Path | None:
    """各课题共用的文风文件：Project Notes 题目库根目录的「我的笔记文风.md」；找不到题目库时为 None。"""
    note = pnotes.find_note(project)
    vault = pnotes._vault_of(note) if note else None
    return vault / STYLE_NAME if vault else None


# ---------- 建骨架 ----------
def init(project, title: str = "", author: str = "") -> Path:
    """在课题目录下建 mynotes/ 骨架（已有就拒绝）；共用文风文件不存在时一并建。不写任何正文内容。"""
    d = notes_dir(project)
    if d.exists():
        raise ValueError(f"已经有了：{d}")
    shutil.copytree(SKEL, d)
    for sub in ("sections", "figs", "inbox", "originals", "review", "checks"):
        (d / sub).mkdir(exist_ok=True)
        (d / sub / ".gitkeep").touch()
    main = d / "main.tex"
    s = main.read_text(encoding="utf-8")
    s = s.replace("<<TITLE>>", title or "Notes").replace("<<AUTHOR>>", author or "")
    main.write_text(s, encoding="utf-8")
    st = shared_style(project)
    if st and not st.exists():
        shutil.copy(TEMPLATE_ROOT / "skel" / STYLE_NAME, st)
    return d


# ---------- 读 TeX 源 ----------
def tex_files(project) -> list[Path]:
    d = notes_dir(project)
    out = [d / n for n in ("main.tex", "preamble.tex", "notation.tex") if (d / n).is_file()]
    out += sorted((d / "sections").rglob("*.tex")) if (d / "sections").is_dir() else []
    return out


def _uncomment(line: str) -> str:
    """去掉行内注释（未转义的 % 之后）。"""
    m = re.search(r"(?<!\\)%", line)
    return line[: m.start()] if m else line


def _match_brace(s: str, i: int) -> int:
    """s[i] == '{'：返回与之配对的 '}' 的下标；跳过 \\{ \\} 和注释。配不上返回 -1。"""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "%":
            nl = s.find("\n", j)
            if nl < 0:
                return -1
            j = nl + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


_ORANGE = re.compile(r"\\orange(?![A-Za-z@])\s*\{")
_CMT = re.compile(r"\\cmt(?![A-Za-z@])\s*\{")
_BLOCK = re.compile(r"[ \t]*\\(begin|end)\{orangeblock\}[ \t]*\n?")


def _commented(s: str, i: int) -> bool:
    ls = s.rfind("\n", 0, i) + 1
    return _uncomment(s[ls:i]) != s[ls:i]


def strip_marks(s: str) -> tuple[str, int]:
    """去掉橙色标记：\\orange{x} → x（可嵌套），\\begin/\\end{orangeblock} 那一行删掉。返回 (新文本, 去掉了几处)。注释里的不动。"""
    n = 0
    while True:
        m = next((m for m in _ORANGE.finditer(s) if not _commented(s, m.start())), None)
        if not m:
            break
        open_ = m.end() - 1
        close = _match_brace(s, open_)
        if close < 0:
            raise ValueError(f"\\orange{{ 的括号配不上（第 {s.count(chr(10), 0, m.start()) + 1} 行）")
        s = s[: m.start()] + s[open_ + 1: close] + s[close + 1:]
        n += 1
    out, k = [], 0
    for m in _BLOCK.finditer(s):
        if _commented(s, m.start()):
            continue
        out.append(s[k:m.start()])
        k = m.end()
        n += 1 if m.group(1) == "begin" else 0
    out.append(s[k:])
    return "".join(out), n


def marks(project) -> dict:
    """待你看的标记：橙色补充几处、蓝色问题几处（带文件和行号）。"""
    orange, cmts = 0, []
    d = notes_dir(project)
    for p in tex_files(project):
        s = p.read_text(encoding="utf-8")
        orange += sum(1 for m in _ORANGE.finditer(s) if not _commented(s, m.start()))
        orange += sum(1 for m in re.finditer(r"\\begin\{orangeblock\}", s) if not _commented(s, m.start()))
        for m in _CMT.finditer(s):
            if _commented(s, m.start()):
                continue
            close = _match_brace(s, m.end() - 1)
            text = " ".join(s[m.end(): close if close > 0 else m.end() + 120].split())
            cmts.append({"file": str(p.relative_to(d)), "line": s.count("\n", 0, m.start()) + 1, "text": text[:200]})
    return {"orange": orange, "cmt": len(cmts), "questions": cmts}


def flatten(project) -> str:
    """把 main.tex 里的 \\input / \\include 展开成一个文件（给 AI 读；不编译）。"""
    d = notes_dir(project)

    def expand(p: Path, depth: int) -> str:
        try:
            s = p.read_text(encoding="utf-8")
        except OSError:
            return f"% （读不到 {p.name}）\n"
        if depth > 4:
            return s

        def sub(m):
            if _commented(s, m.start()):
                return m.group(0)
            name = m.group(2).strip()
            q = d / (name if name.endswith(".tex") else name + ".tex")
            return f"% ==== {q.relative_to(d)} ====\n" + expand(q, depth + 1) if q.is_file() else m.group(0)
        return re.sub(r"\\(input|include)\{([^}]*)\}", sub, s)
    return expand(d / "main.tex", 0) if exists(project) else ""


# ---------- 编译输出 ----------
def _clean_title(t: str) -> str:
    """目录标题里的 LaTeX 命令拆掉，公式 $…$ 原样留给网页 KaTeX。"""
    parts = re.split(r"(\$[^$]*\$)", t)
    for i in range(0, len(parts), 2):
        x = parts[i]
        for _ in range(4):
            x = re.sub(r"\\(?:protect|relax|ignorespaces)\s*", "", x)
            x = re.sub(r"\\[A-Za-z@]+\*?\s*\{([^{}]*)\}", r"\1", x)
        x = re.sub(r"\\([&%#_{}$])", r"\1", x)
        x = re.sub(r"\\[A-Za-z@]+\s*", "", x).replace("{", "").replace("}", "").replace("~", " ")
        parts[i] = x
    return " ".join("".join(parts).split())


def _toc_line(line: str):
    """\\contentsline {section}{\\numberline {I}Title}{3}{section*.3}% → (级别, 编号, 标题, 页码, 锚点)"""
    m = re.match(r"\\contentsline\s*\{(\w+)\}", line)
    if not m:
        return None
    args, j = [], m.end()
    while len(args) < 3 and j < len(line):
        if line[j] == "{":
            k = _match_brace(line, j)
            if k < 0:
                return None
            args.append(line[j + 1:k])
            j = k + 1
        else:
            j += 1
    if len(args) < 3:
        return None
    body, page, anchor = args
    num = ""
    nm = re.match(r"\s*\\numberline\s*\{", body)
    if nm:
        k = _match_brace(body, nm.end() - 1)
        num, body = body[nm.end():k], body[k + 1:]
    return m.group(1), num.strip(), _clean_title(body), page.strip(), anchor.strip()


def toc(project) -> list[dict]:
    """build/main.toc 的目录（跳过标题和 Contents 自己），附上每节的 \\label（从 main.aux 按锚点对上）。"""
    d = notes_dir(project) / "build"
    try:
        lines = (d / "main.toc").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    by_anchor = {v["anchor"]: k for k, v in labels(project).items() if v["anchor"]}
    out, depth = [], {"section": 1, "subsection": 2, "subsubsection": 3, "appendix": 1}
    for ln in lines:
        r = _toc_line(ln)
        if not r or r[0] not in depth or r[2] in ("Contents", "目录"):
            continue
        level, num, title, page, anchor = r
        out.append({"level": depth[level], "num": num, "title": title, "page": int(page) if page.isdigit() else None,
                    "label": by_anchor.get(anchor, "")})
    return out


def labels(project) -> dict:
    """main.aux 里的 \\newlabel：{label: {num, page, anchor}}。"""
    try:
        s = (notes_dir(project) / "build" / "main.aux").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out = {}
    for m in re.finditer(r"\\newlabel\{([^}]*)\}\{", s):
        j = m.end() - 1
        k = _match_brace(s, j)
        if k < 0:
            continue
        fields, inner, i = [], s[j + 1:k], 0
        while i < len(inner):
            if inner[i] == "{":
                e = _match_brace(inner, i)
                if e < 0:
                    break
                fields.append(inner[i + 1:e])
                i = e + 1
            else:
                i += 1
        if len(fields) >= 2:
            out[m.group(1)] = {"num": fields[0], "page": int(fields[1]) if fields[1].isdigit() else None,
                               "anchor": fields[3] if len(fields) > 3 else ""}
    return out


def _pages(log: Path) -> int | None:
    try:
        m = re.search(r"Output written on .*?\((\d+) pages?", log.read_text(encoding="utf-8", errors="replace").replace("\n", ""))
    except OSError:
        return None
    return int(m.group(1)) if m else None


def _newest_source(project) -> float:
    d = notes_dir(project)
    files = tex_files(project) + [d / "refs.bib"] + (list((d / "figs").rglob("*")) if (d / "figs").is_dir() else [])
    return max((p.stat().st_mtime for p in files if p.is_file()), default=0.0)


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t).isoformat(timespec="seconds")


def reviews(project, limit: int = 20) -> list[dict]:
    """review/ 里的对照清单，新的在前：{path, title, status, date}。"""
    d = notes_dir(project) / "review"
    out = []
    for p in sorted(d.glob("*.md"), reverse=True)[:limit] if d.is_dir() else []:
        try:
            meta, body = fm.read(p)
        except OSError:
            continue
        m = re.search(r"^#\s+(.+?)\s*$", body, re.M)
        out.append({"path": f"{DIR}/review/{p.name}", "title": str(meta.get("title") or (m.group(1) if m else p.stem)),
                    "status": str(meta.get("status") or "pending"), "date": str(meta.get("date") or p.name[:10]),
                    "inputs": [str(x) for x in (meta.get("inputs") or [])]})
    return out


def inbox(project) -> list[dict]:
    d = notes_dir(project) / "inbox"
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "path": f"{DIR}/inbox/{p.name}", "mtime": _iso(p.stat().st_mtime)} for p in files]


def notation_count(project) -> int:
    try:
        s = (notes_dir(project) / "notation.tex").read_text(encoding="utf-8")
    except OSError:
        return 0
    return sum(1 for ln in s.splitlines() if re.match(r"\s*\\notation\s*\{", _uncomment(ln)))


def latexmk() -> str | None:
    return shutil.which("latexmk") or next((str(p) for p in (Path("/Library/TeX/texbin/latexmk"), Path("/usr/local/bin/latexmk"),
                                                              Path("/opt/homebrew/bin/latexmk")) if p.exists()), None)


def status(project) -> dict:
    d = notes_dir(project)
    if not exists(project):
        return {"exists": False, "dir": DIR}
    b = d / "build"
    pdf, red = b / "main.pdf", b / "redline.pdf"
    built = pdf.stat().st_mtime if pdf.is_file() else 0.0
    st = shared_style(project)
    mk = marks(project)
    return {
        "exists": True, "dir": DIR,
        "pdf": f"{DIR}/build/main.pdf" if built else "", "built": _iso(built) if built else "", "pdf_v": int(built),
        "pages": _pages(b / "main.log") if built else None,
        "stale": bool(built) and _newest_source(project) > built + 1,
        "redline": f"{DIR}/build/redline.pdf" if red.is_file() and red.stat().st_mtime >= built - 1 else "",
        "redline_v": int(red.stat().st_mtime) if red.is_file() else 0,
        "toc": toc(project) if built else [],
        "sections": [str(p.relative_to(d)) for p in sorted((d / "sections").rglob("*.tex"))] if (d / "sections").is_dir() else [],
        "marks": {"orange": mk["orange"], "cmt": mk["cmt"]}, "questions": mk["questions"],
        "inbox": inbox(project), "reviews": reviews(project),
        "notation": notation_count(project),
        "style": {"shared": str(st) if st and st.exists() else "", "local": f"{DIR}/STYLE.md"},
        "latex": bool(latexmk()),
    }


# ---------- 编译、红线、接受 ----------
def _run_latexmk(cwd: Path, target: str, jobname: str | None = None) -> tuple[bool, str]:
    mk = latexmk()
    if not mk:
        raise ValueError("这台机器没有 TeX（找不到 latexmk）：到装了 TeX 的机器上编译，PDF 经 iCloud 同步过来网页就能看到")
    env = dict(os.environ, PATH=f"{Path(mk).parent}:{os.environ.get('PATH', '')}")
    cmd = [mk, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "-outdir=build"]
    if jobname:
        cmd.append(f"-jobname={jobname}")
    r = subprocess.run(cmd + [target], cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    return r.returncode == 0, (r.stdout + r.stderr)[-4000:]


def _log_problems(log: Path) -> dict:
    try:
        s = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    errs = re.findall(r"^\S+\.tex:\d+: .*$", s, re.M)
    return {
        "errors": errs[:10],
        "undefined_refs": sorted(set(re.findall(r"Reference `([^']+)' on page", s))),
        "undefined_cites": sorted(set(re.findall(r"Citation `([^']+)' on page", s))),
        "overfull": len(re.findall(r"^Overfull \\hbox", s, re.M)),
    }


def build(project) -> dict:
    d = notes_dir(project)
    if not exists(project):
        raise ValueError(f"还没有笔记：先 rd mynotes init {project.root}")
    ok, tail = _run_latexmk(d, "main.tex")
    out = {"ok": ok, "pdf": str(d / "build" / "main.pdf"), "pages": _pages(d / "build" / "main.log"), **_log_problems(d / "build" / "main.log")}
    out["marks"] = {k: v for k, v in marks(project).items() if k != "questions"}
    if not ok:
        out["tail"] = tail
    return out


def _git(project, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(project.root), *args], capture_output=True, text=True)


def redline(project, rev: str = "HEAD") -> dict:
    """和 git 里 rev 那一版（默认上次 commit，即上次接受的版本）比，出 build/redline.pdf：删的划掉、加的标出。"""
    d = notes_dir(project)
    if _git(project, "cat-file", "-e", f"{rev}:{DIR}/main.tex").returncode != 0:
        raise ValueError(f"git 里 {rev} 还没有 {DIR}/main.tex（第一批还没 commit）：没有可比的旧版本")
    ld = shutil.which("latexdiff") or ("/Library/TeX/texbin/latexdiff" if Path("/Library/TeX/texbin/latexdiff").exists() else None)
    if not ld:
        raise ValueError("这台机器没有 latexdiff")
    with tempfile.TemporaryDirectory() as tmp:
        arc = subprocess.run(["git", "-C", str(project.root), "archive", rev, DIR], capture_output=True)
        if arc.returncode != 0:
            raise ValueError(arc.stderr.decode(errors="replace")[-400:])
        subprocess.run(["tar", "-x", "-C", tmp], input=arc.stdout, check=True)
        r = subprocess.run([ld, "--flatten", "--encoding=utf8", str(Path(tmp) / DIR / "main.tex"), str(d / "main.tex")],
                           cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError("latexdiff 失败：" + r.stderr[-600:])
    (d / "build").mkdir(exist_ok=True)
    src = d / "build" / "redline.tex"
    # latexdiff 默认把新增内容染蓝：和「蓝色 = agent 的问题」撞色。新增内容保留原色（黑/橙/蓝），只加波浪下划线；删掉的仍是红色删除线
    out_tex = r.stdout.replace(r"{\protect\color{blue}\uwave{#1}}", r"{\uwave{#1}}").replace(r"{\color{blue}\fbox{", r"{\fbox{")
    src.write_text(out_tex, encoding="utf-8")
    ok, tail = _run_latexmk(d, "build/redline.tex", jobname="redline")
    out = {"ok": ok, "pdf": str(d / "build" / "redline.pdf"), "against": rev}
    if not ok:
        out["tail"] = tail
    return out


def accept(project, rebuild: bool = True) -> dict:
    """接受这一批：还有蓝色问题（\\cmt）就拒绝；否则去掉全部橙色标记，pending 的对照清单标 accepted，清单里列的 inbox 原稿移到 originals/。"""
    mk = marks(project)
    if mk["cmt"]:
        where = "\n".join(f"  {q['file']}:{q['line']}  {q['text']}" for q in mk["questions"])
        raise ValueError(f"还有 {mk['cmt']} 个问题没答（\\cmt）：先和课题负责人定下来、改掉问题再接受\n{where}")
    d = notes_dir(project)
    changed, n = [], 0
    for p in tex_files(project):
        s = p.read_text(encoding="utf-8")
        t, k = strip_marks(s)
        if k:
            p.write_text(t, encoding="utf-8")
            changed.append(str(p.relative_to(d)))
            n += k
    moved = []
    today = date.today().isoformat()
    for rv in reviews(project, limit=200):
        if rv["status"] != "pending":
            continue
        p = Path(project.root) / rv["path"]
        meta, body = fm.read(p)
        new_inputs = []
        for x in rv["inputs"]:
            src = Path(project.root) / x
            if x.startswith(f"{DIR}/inbox/") and src.is_file():
                (d / "originals").mkdir(exist_ok=True)
                name = src.name if re.match(r"\d{4}-\d{2}-\d{2}", src.name) else f"{today}-{src.name}"
                dst = d / "originals" / name
                k = 2
                while dst.exists():
                    dst = d / "originals" / f"{Path(name).stem}-{k}{Path(name).suffix}"
                    k += 1
                os.replace(src, dst)
                moved.append(f"{x} → {DIR}/originals/{dst.name}")
                new_inputs.append(f"{DIR}/originals/{dst.name}")
            else:
                new_inputs.append(x)
        meta.update({"status": "accepted", "accepted": today, "inputs": new_inputs})
        fm.write(p, meta, body)
    out = {"removed_marks": n, "files": changed, "moved": moved}
    if rebuild and latexmk():
        out["build"] = build(project)
    return out
