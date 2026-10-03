"""YAML frontmatter 读写。所有内容文件都是 `--- yaml --- + markdown 正文`。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)


def parse(text: str) -> tuple[dict, str]:
    """返回 (frontmatter dict, 正文)。没有 frontmatter 时返回 ({}, 全文)。"""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[m.end():]


def dump(meta: dict, body: str) -> str:
    if not meta:
        return body
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip("\n")
    return f"---\n{head}\n---\n{body}"


def read(path: Path) -> tuple[dict, str]:
    return parse(path.read_text(encoding="utf-8"))


def write(path: Path, meta: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(meta, body), encoding="utf-8")


def update(path: Path, **changes) -> dict:
    """只改 frontmatter 字段，正文原样保留。返回新的 meta。"""
    meta, body = read(path)
    meta.update(changes)
    write(path, meta, body)
    return meta


def append(path: Path, text: str) -> None:
    """在正文末尾追加，frontmatter 不动。"""
    meta, body = read(path)
    if body and not body.endswith("\n"):
        body += "\n"
    write(path, meta, body + text)
