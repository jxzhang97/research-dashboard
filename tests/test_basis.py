from pathlib import Path

from fastapi.testclient import TestClient

from rd_core import basis
from rd_core.project import Project
from rd_core.server import create_app

CH1 = """---
title: 第 1 章
---
# 第 1 章　语言模型入门

## 1.1 什么是"语言模型"？——它只做一件事

### 1.1.2 定义：联合分布可以拆成一串条件分布

正文。

### 1.1.5 采样温度：同一组 logits，换一个 $\\beta$ 就换一个分布

## 2. 训练

### 小结

### 小结
"""

OLD_NOTES = """# lab 02 笔记

## 1. 定义：什么叫非高斯性？

### 1.2 高斯态的偏迹仍是高斯态

## 4. 可解 toy
"""


def setup(project_dir: Path) -> Project:
    lab = project_dir / "labs" / "01-first-task"
    (lab / "notes").mkdir(parents=True)
    (lab / "notes" / "index.md").write_text("# lab 01 notes · 总览：入门\n", encoding="utf-8")
    (lab / "notes" / "ch01-basics.md").write_text(CH1, encoding="utf-8")
    (lab / "notes" / "ch02-more.md").write_text("# 第 2 章　更多\n", encoding="utf-8")
    (lab / "report.md").write_text("---\ntitle: 摘要\n---\n# 摘要\n\n依据见 [notes §1.1.2](notes/ch01-basics.md#112-定义联合分布可以拆成一串条件分布)。\n", encoding="utf-8")
    lab2 = project_dir / "labs" / "02-old"
    lab2.mkdir()
    (lab2 / "brief.md").write_text("---\ntitle: 旧任务\nstatus: done\n---\n# 旧任务\n", encoding="utf-8")
    (lab2 / "notes.md").write_text(OLD_NOTES, encoding="utf-8")
    (project_dir / "wiki" / "llm.md").write_text(
        "---\ntitle: 大语言模型是什么\nshort: 大语言模型\n---\n# 大语言模型\n\n"
        "见[逐步推导（notes §1.1.2）](#/doc/labs/01-first-task/notes/ch01-basics.md?h=112-定义联合分布可以拆成一串条件分布)，"
        "温度见[这里](#/doc/labs/01-first-task/notes/ch01-basics.md?h=115-采样温度同一组-logits换一个-beta-就换一个分布)；"
        "旧笔记见 [notes §1.2、§4](../labs/02-old/notes.md) 与 [整份](../labs/02-old/notes.md)；外链 [x](https://a.b/notes.md) 不算。\n",
        encoding="utf-8")
    return Project(project_dir)


def test_slug_and_heading_ids_match_the_web_page():
    ids = basis.heading_ids(CH1.split("---\n", 2)[2])
    assert [h["id"] for h in ids] == [
        "第-1-章-语言模型入门", "11-什么是语言模型它只做一件事", "112-定义联合分布可以拆成一串条件分布",
        "115-采样温度同一组-logits换一个-beta-就换一个分布", "2-训练", "小结", "小结-2"]  # 重名的加 -2，与 app.js 一致
    assert basis.slug_id("  A **b**  c ") == "a-b-c" and basis.slug_id("？！") == "sec"


def test_targets_read_both_link_styles():
    body = "[a](#/doc/labs/01-x/notes/ch01.md?h=11-%E4%B8%80) [b](../labs/02-y/notes.md#sec) [notes §6.3、§7](../labs/02-y/notes.md) [c](../labs/02-y/report.md)"
    assert list(basis._targets("wiki/p.md", body)) == [
        ("labs/01-x/notes/ch01.md", ["11-一"]), ("labs/02-y/notes.md", ["sec"]), ("labs/02-y/notes.md", ["§6.3", "§7"])]


def test_basis_groups_sections_by_chapter(project_dir: Path):
    pr = setup(project_dir)
    groups = basis.basis(pr, "wiki/llm.md")
    assert [g["label"] for g in groups] == ["lab 01 笔记 · 第 1 章　语言模型入门", "lab 02 笔记"]
    assert [s["id"] for s in groups[0]["sections"]] == ["112-定义联合分布可以拆成一串条件分布", "115-采样温度同一组-logits换一个-beta-就换一个分布"]
    old = groups[1]
    assert [s["text"] for s in old["sections"]] == ["1.2 高斯态的偏迹仍是高斯态", "4. 可解 toy"] and old["whole"] is False  # 「§1.2、§4」按编号对上标题


def test_docnav_lists_chapters_and_citations(project_dir: Path):
    pr = setup(project_dir)
    nav = basis.docnav(pr, "labs/01-first-task/notes/ch01-basics.md")
    assert nav["label"] == "lab 01 笔记 · 第 1 章　语言模型入门"
    assert [c["title"] for c in nav["chapters"]] == ["总览：入门", "第 1 章　语言模型入门", "第 2 章　更多"]
    refs = nav["ids"]["112-定义联合分布可以拆成一串条件分布"]
    assert [(r["kind"], r["title"], r["route"]) for r in refs] == [("wiki", "大语言模型", "#/wiki/llm"), ("lab", "lab 01 摘要", "#/labs/01-first-task")]
    assert nav["whole"] == []
    old = basis.docnav(pr, "labs/02-old/notes.md")
    assert old["chapters"] == [] and set(old["ids"]) == {"12-高斯态的偏迹仍是高斯态", "4-可解-toy"}
    assert old["whole"] == []  # 同一页既引了整份又引了具体几节：不再算「整份」
    assert basis.docnav(pr, "wiki/llm.md") == {"label": "大语言模型", "chapters": [], "ids": {}, "whole": []}


def test_api(project_dir: Path):
    pr = setup(project_dir)
    c = TestClient(create_app(pr))
    assert len(c.get("/api/basis", params={"path": "wiki/llm.md"}).json()["groups"]) == 2
    assert "112-定义联合分布可以拆成一串条件分布" in c.get("/api/docnav", params={"path": "labs/01-first-task/notes/ch01-basics.md"}).json()["ids"]
    assert c.get("/api/docnav", params={"path": "../etc/passwd"}).status_code == 403
