"""Project Notes 联动（用户的 Obsidian 题目库）。

用户在 `~/Documents/Project Notes` 里每个题目一页：frontmatter 有 title / status / updated / coauthor /
next_step / tags，正文有「## Thoughts」「## Next Plan」；库的同步工具在课题文件夹里放一个指回那页的
`<题目>.notes.md` 快捷方式（符号链接）。这里只做三件事：

1. 找到本课题那一页：课题目录或上一级目录里的 `*.notes.md`；config.toml `[notes] path` 可直接指定，"off" 关闭联动。
2. 读写「下一步」：`next_step` 一句话归用户，网页首页显示；网页上改、`rd next` 改、Obsidian 里改，改的都是同一个文件。
3. 把网页地址和摘要写进 `dashboard` / `rd_waiting`（等你裁决的，不含 arXiv）/ `rd_arxiv`（待审 arXiv 候选）/
   `rd_running`（在跑的 lab）四个字段，供 Project.md 总表显示；每 5 分钟看一次、值变了才写，
   不动 `updated`（那是用户自己改动的日期）。

只改涉及的那几行，其余原样保留；写法与同步工具的解析器兼容（单行 `key: value`、列表 `  - item`）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from . import config, fm

MIRROR_KEYS = ("dashboard", "rd_waiting", "rd_arxiv", "rd_running")


# ---------- 找到那一页 ----------
def find_note(project) -> Path | None:
    root = Path(project.root)
    want = str(config.load(root).get("notes", {}).get("path") or "").strip()
    if want.lower() == "off":
        return None
    if want:
        p = Path(want).expanduser()
        p = p if p.is_absolute() else root / p
        return p.resolve() if p.exists() else None
    d = root
    for _ in range(2):  # 课题目录本身，或上一级（magic/heavyfermion 这种课题在题目文件夹下面一层）
        named = d / f"{d.name}.notes.md"
        cands = [named] if named.exists() else sorted(d.glob("*.notes.md"))
        if len(cands) == 1 and cands[0].exists():
            return cands[0].resolve()
        if d.parent == d or d.parent == Path.home():
            break
        d = d.parent
    return None


def _vault_of(path: Path) -> Path | None:
    for d in path.parents:
        if (d / ".obsidian").is_dir():
            return d
    return None


def obsidian_uri(path: Path) -> str:
    vault = _vault_of(path)
    if not vault:
        return ""
    rel = path.relative_to(vault).as_posix()
    rel = rel[:-3] if rel.endswith(".md") else rel
    return f"obsidian://open?vault={quote(vault.name)}&file={quote(rel)}"


# ---------- frontmatter 按行改 ----------
def _split(text: str) -> tuple[list[str], str] | None:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return None


def _join(head: list[str], body: str) -> str:
    return "---\n" + "\n".join(head) + "\n---\n" + body


def _find(head: list[str], key: str) -> int:
    for i, line in enumerate(head):
        if line.startswith(f"{key}:"):
            return i
    return -1


def _raw(head: list[str], key: str) -> str | None:
    i = _find(head, key)
    return None if i < 0 else head[i].split(":", 1)[1].strip()


def _set(head: list[str], key: str, rendered: str) -> bool:
    """把 `key:` 那一行换成 `key: rendered`（原来若是列表，连同下面的 `  - ` 行一起换掉）；没有就加在末尾。"""
    new = f"{key}: {rendered}"
    i = _find(head, key)
    if i < 0:
        head.append(new)
        return True
    j = i + 1
    while j < len(head) and head[j].startswith("  - "):
        j += 1
    if head[i:j] == [new]:
        return False
    head[i:j] = [new]
    return True


def _quoted(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _write(path: Path, before: str, after: str) -> bool:
    """写回前再读一遍：期间文件被别处（Obsidian、另一台机器经 iCloud）改过就放弃，交给调用方重来。"""
    if path.read_text(encoding="utf-8") != before:
        return False
    tmp = path.with_name(f".{path.name}.rd-tmp")
    tmp.write_text(after, encoding="utf-8")
    try:
        shutil.copymode(path, tmp)
    except OSError:
        pass
    os.replace(tmp, path)
    return True


def _edit(path: Path, fn) -> bool:
    """fn(head) 就地改 frontmatter 行并返回是否有改动；最多重试一次（读写之间文件被别处改了）。"""
    for _ in range(2):
        text = path.read_text(encoding="utf-8")
        parts = _split(text)
        if parts is None:
            return False
        head, body = parts
        if not fn(head):
            return False
        if _write(path, text, _join(head, body)):
            return True
    return False


# ---------- 读 ----------
def _section(body: str, title: str) -> str:
    m = re.search(rf"^##[ \t]+{re.escape(title)}[ \t]*$", body, re.M | re.I)
    if not m:
        return ""
    rest = body[m.end():]
    n = re.search(r"^#{1,2}[ \t]+\S", rest, re.M)
    return (rest[: n.start()] if n else rest).strip()


def read(project) -> dict | None:
    path = find_note(project)
    if not path:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = fm.parse(text)
    vault = _vault_of(path)
    return {
        "title": str(meta.get("title") or path.name.removesuffix(".notes.md")),
        "status": str(meta.get("status") or ""),
        "updated": str(meta.get("updated") or ""),
        "next_step": " ".join(str(meta.get("next_step") or "").split()),
        "next_plan": _section(body, "Next Plan"),
        "path": str(path.relative_to(vault)) if vault else str(path),
        "obsidian": obsidian_uri(path),
    }


# ---------- 写下一步 ----------
def set_next(project, text: str) -> dict | None:
    path = find_note(project)
    if not path:
        return None
    line = " ".join((text or "").split())

    def fn(head):
        changed = _set(head, "next_step", _quoted(line))
        if changed:
            _set(head, "updated", date.today().isoformat())
        return changed

    _edit(path, fn)
    out = read(project)
    if out is None or out["next_step"] != line:  # 两次都撞上别处同时在改：别假装写成了
        raise RuntimeError("Project Notes 那一页正被别处修改，没有写成，请再试一次")
    return out


# ---------- 网页地址与摘要 ----------
_TAILSCALE = ("tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale", "~/.local/bin/tailscale",
              "/opt/homebrew/bin/tailscale", "/usr/local/bin/tailscale")


@lru_cache(maxsize=1)
def _tailnet_name() -> str:
    for exe in _TAILSCALE:
        exe = shutil.which(os.path.expanduser(exe)) or ""
        if not exe:
            continue
        try:
            out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=5).stdout
            name = (json.loads(out).get("Self") or {}).get("DNSName", "").rstrip(".")
            if name:
                return name
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
    return ""


def dashboard_url(project) -> str:
    cfg = config.load(Path(project.root))
    url = str(cfg.get("notes", {}).get("url") or "").strip()
    if url:
        return url
    host = _tailnet_name() or socket.gethostname()
    return f"http://{host}:{cfg['server']['port']}"


def mirror_values(project) -> dict:
    running = []
    for lab in project.labs():
        if lab.meta.get("status") == "running":
            m = re.match(r"(\d+)", lab.id)
            running.append(f"lab {m.group(1) if m else lab.id}")
    hard = [it for it in project.attention()["items"] if not it.get("soft")]
    return {
        "dashboard": dashboard_url(project),
        "rd_waiting": sum(1 for it in hard if it["kind"] != "inbox"),
        "rd_arxiv": sum(1 for it in hard if it["kind"] == "inbox"),
        "rd_running": ("、".join(running) + " 运行中") if running else "",
    }


def mirror(project, values: dict | None = None) -> bool:
    """把网页地址与摘要写进那一页的 frontmatter；值没变不写。返回是否写了。"""
    path = find_note(project)
    if not path:
        return False
    values = values if values is not None else mirror_values(project)

    def fn(head):
        changed = False
        for key in MIRROR_KEYS:
            v = values.get(key, "")
            changed |= _set(head, key, str(v) if isinstance(v, int) else _quoted(str(v)))
        return changed

    return _edit(path, fn)
