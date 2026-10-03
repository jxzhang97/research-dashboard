from pathlib import Path

from rd_core import fm
from rd_core.project import Project


def test_init_creates_skeleton(project_dir: Path):
    for rel in ("AGENTS.md", "CLAUDE.md", "PROJECT.md", "config.toml", "wiki/notation.md", "log.md", "references/cards", "ideas/inbox"):
        assert (project_dir / rel).exists(), rel
    assert (project_dir / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert "demo" in (project_dir / "config.toml").read_text()


def test_frontmatter_roundtrip(tmp_path: Path):
    p = tmp_path / "x.md"
    fm.write(p, {"title": "中文", "tags": ["a"]}, "# 中文\n\n正文 $x$\n")
    meta, body = fm.read(p)
    assert meta == {"title": "中文", "tags": ["a"]}
    assert body.startswith("# 中文")
    fm.update(p, status="done")
    assert fm.read(p)[0]["status"] == "done"
    fm.append(p, "## 追加\n")
    assert fm.read(p)[1].endswith("## 追加\n")


def test_scan_and_links(project_dir: Path):
    pr = Project(project_dir)
    assert [c.id for c in pr.cards()] == ["2104.14257"]
    pages = {p.id for p in pr.wiki_pages()}
    assert {"index", "notation", "quantum-metric"} <= pages
    qm = pr.wiki("quantum-metric")
    assert set(qm.extra["links"]) == {"notation", "2104.14257"}
    table = pr.link_table()
    assert table["2104.14257"]["kind"] == "card"
    assert table["量子度规"] == {"kind": "wiki", "id": "quantum-metric"}
    assert pr.resolve_link("第一个任务") == {"kind": "lab", "id": "01-first-task"}


def test_idea_tree_and_attention(project_dir: Path):
    pr = Project(project_dir)
    tree = pr.idea_tree()
    assert [n["id"] for n in tree] == ["root-idea"]
    assert tree[0]["children"][0]["id"] == "metric-bound"
    att = pr.attention()
    kinds = {(i["kind"], i["id"]) for i in att["items"]}
    assert ("discussion", "2026-10-02-which-limit") in kinds
    assert ("lab", "01-first-task") in kinds
    assert att["counts"]["discussion"] == 1


def test_answer_capture_pending(project_dir: Path):
    pr = Project(project_dir)
    assert pr.pending_work() == []
    pr.answer_discussion("2026-10-02-which-limit", "选 A")
    d = pr.discussion("2026-10-02-which-limit")
    assert d.meta["status"] == "answered"
    assert "## 你的回答" in d.body and "选 A" in d.body
    slug = pr.capture_idea("一个模糊的想法\n细节……")
    assert slug.startswith("inbox/")
    pr.set_lab_status("01-first-task", "approved")
    pr.request_promote("root-idea", "不用过目")
    kinds = sorted(w["kind"] for w in pr.pending_work())
    assert kinds == ["digest_answer", "promote_idea", "run_lab", "triage_idea"]
    log = pr.log_entries(5)
    assert log[0]["who"] == "用户"
    assert any("回答了讨论" in e["what"] for e in log)
    pr.mark_seen("discussion", "2026-10-02-which-limit")
    assert not pr.is_unread("discussion", "2026-10-02-which-limit", d.mtime)


def test_safe_path(project_dir: Path):
    pr = Project(project_dir)
    try:
        pr.safe_path("../../etc/passwd")
        assert False, "应当拒绝越界路径"
    except PermissionError:
        pass
