import io
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rd_core import cli, fm, mine
from rd_core.project import Project
from rd_core.server import create_app
from test_pnotes import compatible, vault_note

PAGE = """---
title: 近藤屏蔽
---
# 近藤屏蔽

引言。

## 1. 两种屏蔽

单通道时杂质自旋被完全屏蔽，$T_K$ 以下形成**单态**。

- 多通道时过屏蔽，留下 [[非费米液体|非费米液体]]。

```text
## 代码块里的不算标题
```

### 细节

更细的东西。

## 两种屏蔽的比较

另一节。
"""

TEXT = "屏蔽云其实就是 $T_K$ 以下传导电子的一团自旋关联，\n单通道时正好补满杂质自旋。"


@pytest.fixture
def page(project_dir: Path) -> Path:
    p = project_dir / "wiki" / "kondo.md"
    p.write_text(PAGE, encoding="utf-8")
    return p


def add(pr: Project, **kw) -> dict:
    args = {"page": "wiki/kondo.md", "section": "1. 两种屏蔽", "quote": "杂质自旋被完全屏蔽，$T_K$ 以下形成单态", "title": "屏蔽云的图像", "text": TEXT}
    args.update(kw)
    return mine.save(pr, **args)


def test_plain_ignores_math_and_markup():
    assert mine.plain("以下形成**单态**，$T_K$ 见 [[a|非费米液体]] 与 [链接](x.md)") == "以下形成单态，见非费米液体与链接"
    assert mine.plain("- 多通道\n> 引用") == "多通道引用"


def test_find_section(page: Path):
    body = fm.read(page)[1]
    raw, text, _ = mine.find_section(body, "1. 两种屏蔽")
    assert raw == "1. 两种屏蔽" and "过屏蔽" in text and "更细的东西" in text and "另一节" not in text  # 子节算在内，到同级标题为止
    assert mine.find_section(body, "细节")[0] == "细节"
    assert mine.find_section(body, "两种屏蔽")[0] is None  # 不和「1. 两种屏蔽」算相等：编号是标题的一部分
    assert mine.find_section(body, "两种屏蔽", loose=True)[0] is None  # 两个标题都含这几个字：要说完整
    assert mine.find_section(body, "比较", loose=True)[0] == "两种屏蔽的比较"
    assert mine.find_section(body, "代码块里的不算标题")[0] is None
    assert mine.find_section(body, "")[0] == ""  # 空 = 整页


def test_save_writes_beside_note_and_indexes_once(project_dir: Path, tmp_path: Path, page: Path):
    note = vault_note(tmp_path, project_dir)
    pr = Project(project_dir)
    it = add(pr)
    f = note.parent / "我的理解" / f"{it['id']}.md"
    assert f.is_file() and it["id"] == f"{date.today().isoformat()}-屏蔽云的图像"
    meta, body = fm.read(f)
    assert meta["page"] == "wiki/kondo.md" and meta["section"] == "1. 两种屏蔽" and meta["project"] == "demo"
    assert meta["quote"] == "杂质自旋被完全屏蔽，$T_K$ 以下形成单态" and meta["tags"] == ["我的理解"]
    assert meta["dashboard"].endswith("/#/wiki/kondo") and body.strip() == TEXT
    text = note.read_text(encoding="utf-8")
    assert text.count(mine.INDEX_MARK) == 1 and "```dataview" in text and compatible(text)
    add(pr, title="第二条", section="细节", quote="")
    assert note.read_text(encoding="utf-8").count(mine.INDEX_MARK) == 1  # 第二条不再加
    assert [x["title"] for x in mine.items(pr)][0] in ("屏蔽云的图像", "第二条") and mine.count(pr) == 2


def test_save_refuses_bad_anchor(project_dir: Path, page: Path):
    pr = Project(project_dir)
    with pytest.raises(ValueError, match="说得再完整"):
        add(pr, section="两种屏蔽")
    with pytest.raises(ValueError, match="没有这个标题"):
        add(pr, section="三种屏蔽")
    with pytest.raises(ValueError, match="找不到引的那句话"):
        add(pr, quote="另一节")  # 在别的节里
    with pytest.raises(ValueError, match="找不到这一页"):
        add(pr, page="wiki/none.md")
    with pytest.raises(ValueError, match="不在课题目录"):
        add(pr, page="../x.md")
    assert not (project_dir / "我的理解").exists() or not any((project_dir / "我的理解").iterdir())


def test_without_note_and_rewrite_keeps_created(project_dir: Path, page: Path):
    pr = Project(project_dir)
    it = add(pr)
    f = project_dir / "我的理解" / f"{it['id']}.md"
    assert f.is_file()
    text = f.read_text(encoding="utf-8").replace(f"created: {date.today().isoformat()}", "created: 2026-01-02")
    f.write_text(text, encoding="utf-8")
    again = add(pr, id=it["id"], text="改过的说法。")
    assert again["id"] == it["id"] and again["created"] == "2026-01-02" and again["text"] == "改过的说法。"
    assert len(list((project_dir / "我的理解").glob("*.md"))) == 1


def test_items_skip_other_projects(project_dir: Path, page: Path):
    pr = Project(project_dir)
    it = add(pr)
    f = project_dir / "我的理解" / f"{it['id']}.md"
    f.write_text(f.read_text(encoding="utf-8").replace('project: "demo"', 'project: "别的课题"'), encoding="utf-8")
    assert mine.items(pr) == []


def test_check_reports_moved_anchor(project_dir: Path, page: Path):
    pr = Project(project_dir)
    add(pr)
    assert mine.check(pr) == []
    page.write_text(PAGE.replace("## 1. 两种屏蔽", "## 1. 屏蔽的两种情形"), encoding="utf-8")
    bad = mine.check(pr)
    assert len(bad) == 1 and "没有这个标题" in bad[0][1]


def test_api_and_ai_export(project_dir: Path, page: Path):
    pr = Project(project_dir)
    c = TestClient(create_app(pr))
    assert c.get("/api/overview").json()["mine"] == 0 and c.get("/api/mine").json() == {"items": []}
    assert "我的理解" not in c.get("/llms.txt").text
    add(pr)
    items = c.get("/api/mine").json()["items"]
    assert len(items) == 1 and items[0]["page_title"] == "近藤屏蔽" and items[0]["section"] == "1. 两种屏蔽"
    assert c.get("/api/overview").json()["mine"] == 1
    assert "/md/%E6%88%91%E7%9A%84%E7%90%86%E8%A7%A3.md" in c.get("/llms.txt").text
    md = c.get("/md/我的理解.md").text
    assert "### 屏蔽云的图像" in md and "「1. 两种屏蔽」一节" in md and TEXT in md
    assert "屏蔽云的图像" in c.get("/llms-full.txt").text


def test_cli_add_list_check(project_dir: Path, page: Path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(TEXT))
    cli.main(["mine", str(project_dir), "--page", "./wiki/kondo.md", "--section", "细节", "--quote", "更细的东西", "--title", "细节里的图像", "--text-file", "-"])
    out = capsys.readouterr().out
    assert "已写" in out and "#/wiki/kondo" in out
    assert "我的理解：细节里的图像" in (project_dir / "log.md").read_text(encoding="utf-8")
    cli.main(["mine", str(project_dir)])
    assert "细节里的图像" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        cli.main(["mine", str(project_dir), "--check"])
    assert e.value.code == 0
    with pytest.raises(SystemExit) as e:
        cli.main(["mine", str(project_dir), "--page", "wiki/kondo.md", "--section", "无此节", "--title", "x", "--text", "y"])
    assert e.value.code == 1 and "没有写" in capsys.readouterr().out
    cli.main(["mine", str(project_dir), "--headings", "wiki/kondo.md"])
    assert "  1. 两种屏蔽" in capsys.readouterr().out
