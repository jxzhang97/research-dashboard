import os
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from rd_core import pnotes
from rd_core.project import Project
from rd_core.server import create_app

NOTE = '''---
title: "demo"
status: working
updated: 2026-03-27
coauthor:
  - Wen Wang
next_step: ""
tags:
  - working
active: true
---

# demo

## Thoughts
先想清楚 $\\delta$ 的来源。

## Next Plan
- 算三角晶格
- 写场论

## 附录
不属于 Next Plan。
'''


def vault_note(tmp_path: Path, link_dir: Path, name: str = "demo") -> Path:
    """仿照 Project Notes：库里一页真文件，课题目录里一个指向它的快捷方式。"""
    vault = tmp_path / "Project Notes"
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    note = vault / name / f"{name}.notes.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(NOTE, encoding="utf-8")
    os.chmod(note, 0o600)
    (link_dir / f"{name}.notes.md").symlink_to(os.path.relpath(note, link_dir))
    return note


def compatible(text: str) -> bool:
    """同步工具的解析器只认单行 key: value 和「  - item」列表；其余写法它会放弃维护这一页。"""
    head = text.split("---\n")[1].splitlines()
    return all((not ln.strip()) or ln.startswith("  - ") or (":" in ln and not ln.startswith((" ", "\t", "- "))) for ln in head)


def test_read_finds_note_through_shortcut(project_dir: Path, tmp_path: Path):
    note = vault_note(tmp_path, project_dir)
    n = pnotes.read(Project(project_dir))
    assert pnotes.find_note(Project(project_dir)) == note.resolve()
    assert n["title"] == "demo" and n["status"] == "working" and n["next_step"] == ""
    assert n["next_plan"] == "- 算三角晶格\n- 写场论"  # 只到下一个二级标题
    assert n["path"] == "demo/demo.notes.md"
    assert n["obsidian"] == "obsidian://open?vault=Project%20Notes&file=demo/demo.notes"


def test_note_one_level_up_and_off_switch(tmp_path: Path, project_dir: Path):
    # magic/heavyfermion 这种：课题在题目文件夹下一层，快捷方式在上一级
    sub = project_dir / "heavy"
    sub.mkdir()
    (sub / "config.toml").write_text((project_dir / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
    note = vault_note(tmp_path, project_dir)
    assert pnotes.find_note(Project(sub)) == note.resolve()
    with (sub / "config.toml").open("a", encoding="utf-8") as f:
        f.write('\n[notes]\npath = "off"\n')
    assert pnotes.find_note(Project(sub)) is None and pnotes.read(Project(sub)) is None


def test_set_next_rewrites_only_that_line(project_dir: Path, tmp_path: Path):
    note = vault_note(tmp_path, project_dir)
    out = pnotes.set_next(Project(project_dir), "  先精读 2609.28448，\n再定 lab 02 ")
    text = note.read_text(encoding="utf-8")
    assert out["next_step"] == "先精读 2609.28448， 再定 lab 02"
    assert 'next_step: "先精读 2609.28448， 再定 lab 02"' in text  # 中文原样写，不转成 \\u 转义
    assert f"updated: {date.today().isoformat()}" in text
    assert text.replace(f"updated: {date.today().isoformat()}", "updated: 2026-03-27").replace(
        'next_step: "先精读 2609.28448， 再定 lab 02"', 'next_step: ""') == NOTE
    assert compatible(text) and oct(note.stat().st_mode & 0o777) == "0o600"
    assert not note.is_symlink() and (project_dir / "demo.notes.md").is_symlink()  # 快捷方式还在，写的是库里的真文件


def test_mirror_writes_once_and_keeps_updated(project_dir: Path, tmp_path: Path):
    note = vault_note(tmp_path, project_dir)
    pr = Project(project_dir)
    vals = {"dashboard": "http://studio.ts.net:8014", "rd_waiting": 3, "rd_arxiv": 28, "rd_running": "lab 02 运行中"}
    assert pnotes.mirror(pr, vals) is True
    text = note.read_text(encoding="utf-8")
    for line in ('dashboard: "http://studio.ts.net:8014"', "rd_waiting: 3", "rd_arxiv: 28", 'rd_running: "lab 02 运行中"', "updated: 2026-03-27"):
        assert line in text
    assert compatible(text) and text.endswith(NOTE.split("---\n", 2)[2])
    mtime = note.stat().st_mtime_ns
    assert pnotes.mirror(pr, vals) is False and note.stat().st_mtime_ns == mtime  # 值没变不写
    assert pnotes.mirror(pr, {**vals, "rd_running": ""}) is True and 'rd_running: ""' in note.read_text(encoding="utf-8")


def test_mirror_values_split_arxiv(project_dir: Path, tmp_path: Path):
    vault_note(tmp_path, project_dir)
    with (project_dir / "config.toml").open("a", encoding="utf-8") as f:
        f.write('\n[notes]\nurl = "http://example:9"\n')
    (project_dir / "references" / "inbox" / "2601.00001.md").write_text("---\ntitle: 候选\nstatus: pending\n---\n", encoding="utf-8")
    v = pnotes.mirror_values(Project(project_dir))
    # 示例课题：一份等过目的任务书 + 一个 agent 的提问；arXiv 候选另算
    assert v == {"dashboard": "http://example:9", "rd_waiting": 2, "rd_arxiv": 1, "rd_running": ""}


def test_stale_write_is_refused(project_dir: Path, tmp_path: Path):
    note = vault_note(tmp_path, project_dir)
    assert pnotes._write(note, NOTE + "别处改过", "x") is False and note.read_text(encoding="utf-8") == NOTE


def test_set_replaces_list_value():
    head = ["title: a", "rd_running:", "  - x", "  - y", "tags:", "  - idea"]
    assert pnotes._set(head, "rd_running", '""') is True
    assert head == ["title: a", 'rd_running: ""', "tags:", "  - idea"]


def test_api_overview_and_write(project_dir: Path, tmp_path: Path):
    note = vault_note(tmp_path, project_dir)
    c = TestClient(create_app(Project(project_dir)))
    assert c.get("/api/overview").json()["notes"]["next_plan"].startswith("- 算三角晶格")
    r = c.post("/api/notes/next", json={"text": "先写场论"})
    assert r.status_code == 200 and r.json()["next_step"] == "先写场论"
    assert 'next_step: "先写场论"' in note.read_text(encoding="utf-8")
    assert "下一步：先写场论" in (project_dir / "log.md").read_text(encoding="utf-8")


def test_api_without_note(project_dir: Path):
    c = TestClient(create_app(Project(project_dir)))
    assert c.get("/api/overview").json()["notes"] is None
    assert c.post("/api/notes/next", json={"text": "x"}).status_code == 404


def test_set_next_reports_lost_race(project_dir: Path, tmp_path: Path, monkeypatch):
    vault_note(tmp_path, project_dir)
    monkeypatch.setattr(pnotes, "_write", lambda *a: False)  # 每次写之前文件都被别处改了
    import pytest
    with pytest.raises(RuntimeError):
        pnotes.set_next(Project(project_dir), "先写场论")
    c = TestClient(create_app(Project(project_dir)))
    assert c.post("/api/notes/next", json={"text": "先写场论"}).status_code == 409
