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


def test_answers_are_digested_in_one_batch(project_dir: Path):
    """回答不进即时待办；run_digest 把所有已回答的讨论放进同一个提示词。"""
    from rd_core.tick import actionable, run_digest
    pr = Project(project_dir)
    pr.answer_discussion("2026-10-02-which-limit", "选 A")
    pr.new_discussion("第二个问题", "B 还是 C？", asked_by="agent")
    did2 = [d.id for d in pr.discussions() if d.title == "第二个问题"][0]
    pr.answer_discussion(did2, "选 C，和上一个问题一致")
    ready, _ = actionable(pr)
    assert all(w["kind"] != "digest_answer" for w in ready)
    plan = run_digest(pr, dry_run=True)
    assert plan["kind"] == "digest_answers" and set(plan["threads"]) == {"2026-10-02-which-limit", did2}
    assert "先通读全部回答" in plan["prompt"] and "which-limit" in plan["prompt"]


def test_backoff_after_failure(project_dir: Path):
    from rd_core.tick import actionable
    pr = Project(project_dir)
    pr.set_lab_status("01-first-task", "approved")
    ready, deferred = actionable(pr)
    assert [w["kind"] for w in ready] == ["run_lab"] and deferred == []
    pr.record_attempt("run_lab", "01-first-task", "failed")
    ready, deferred = actionable(pr)
    assert ready == [] and deferred[0]["last_status"] == "failed"
    pr.record_attempt("run_lab", "01-first-task", "done")
    assert actionable(pr)[0][0]["kind"] == "run_lab"


def test_safe_path(project_dir: Path):
    pr = Project(project_dir)
    try:
        pr.safe_path("../../etc/passwd")
        assert False, "应当拒绝越界路径"
    except PermissionError:
        pass


def test_lab_answer_pdfs_and_gallery(project_dir: Path):
    """report.md 首屏的「当前回答」进列表；PDF 在子目录也能找到；fig/ 与 report/figs/ 的同名图只显示一次，图注取 alt。"""
    lab = project_dir / "labs" / "01-first-task"
    (lab / "report.md").write_text(
        "---\ntitle: 短标题\nstatus: running\nnotes: notes.md\n---\n# 短标题\n\n## 问题\n\n能不能算？\n\n## 当前回答\n\n能，$L\\le 8$ 时见 [[quantum-metric]]。\n\n## 为什么信\n\n![看哪里 → 看到峰 → 说明有 gap](fig/main.png)\n", encoding="utf-8")
    (lab / "notes.md").write_text("# notes\n\n## 第一节\n\n推导。\n", encoding="utf-8")
    (lab / "fig").mkdir(); (lab / "fig" / "main.png").write_bytes(b"png")
    (lab / "report").mkdir(); (lab / "report" / "figs").mkdir()
    (lab / "report" / "figs" / "main.png").write_bytes(b"png")
    (lab / "report" / "report_CN.pdf").write_bytes(b"%PDF")
    pr = Project(project_dir)
    s = pr.labs()[0].summary()
    assert s["answer"].startswith("能，") and "quantum-metric" in s["answer"]
    assert s["question"] == "能不能算？" and s["short"] == "短标题" and s["notes"] == "notes.md"
    assert s["pdfs"] == ["report/report_CN.pdf"]
    full = pr.lab("01-first-task").full()
    imgs = full["images"]
    assert [i["name"] for i in imgs] == ["fig/main.png"]
    assert imgs[0]["caption"].startswith("看哪里")


def test_gallery_matches_full_paths_and_bracketed_math(project_dir: Path):
    from rd_core.translations import gallery_sources
    lab = project_dir / "labs/01-first-task"
    files = {"fig/main.png": b"L3", "fig/L6/main.png": b"L6", "fig/multiL/main.png": b"all sizes",
             "report/figs/main.png": b"older export"}
    for name, content in files.items():
        image = lab / name
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(content)
    (lab / "report.md").write_text("![L3 caption](fig/main.png)\n")
    (lab / "notes.md").write_text("![L6: $J \u2208 [3.1,3.3]$](fig/L6/main.png)\n![ignored older caption](fig/main.png)\n")
    project = Project(project_dir)
    images = project.lab("01-first-task").full()["images"]
    assert {image["name"]: image["caption"] for image in images} == {
        "fig/main.png": "L3 caption", "fig/L6/main.png": "L6: $J \u2208 [3.1,3.3]$", "fig/multiL/main.png": ""}
    captions = gallery_sources(project)
    assert captions["labs/01-first-task/fig/main.png"] == "L3 caption"
    assert captions["labs/01-first-task/fig/L6/main.png"] == "L6: $J \u2208 [3.1,3.3]$"
    assert "labs/01-first-task/fig/multiL/main.png" not in captions


def test_idea_answer_and_status_doc(project_dir: Path):
    (project_dir / "ideas" / "metric-bound.md").write_text(
        "---\ntitle: 度规 bound\nparent: root-idea\nkind: route\nstatus: lab\nlabs: [01-first-task]\n---\n# 度规 bound\n\n## 原话\n\n……\n\n<!-- agent -->\n## 当前回答\n\n未回答，等 lab 01。\n\n## 历史\n\n- 建立。\n", encoding="utf-8")
    pr = Project(project_dir)
    node = pr.idea_tree()[0]["children"][0]
    assert node["answer"] == "未回答，等 lab 01。" and node["meta"]["kind"] == "route"
    st = pr.status_doc()
    assert st and st["path"] == "STATUS.md" and "研究问题" in st["body"]


def test_wiki_handoff_dir_is_not_a_page(project_dir: Path):
    (project_dir / "wiki" / "handoff").mkdir()
    (project_dir / "wiki" / "handoff" / "2026-10-04-rewrite.md").write_text("---\ntitle: 交接单\n---\n# 交接单\n", encoding="utf-8")
    ids = {p.id for p in Project(project_dir).wiki_pages()}
    assert "handoff/2026-10-04-rewrite" not in ids and "quantum-metric" in ids


def test_wiki_internal_records_are_not_concepts(project_dir: Path):
    internal = (
        "audit/review.md", "audit/scratch/algebra.md", "scratch/check.md",
        "models/audit/review.md", "models/handoff/prompt.md",
    )
    concepts = ("models/hubbard.md", "audit-method.md")
    for rel in internal + concepts:
        p = project_dir / "wiki" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {rel}\n", encoding="utf-8")
    pr = Project(project_dir)
    ids = {p.id for p in pr.wiki_pages()}
    ai_paths = {p["path"] for _, pages in pr.ai_pages() for p in pages}
    for rel in internal:
        assert rel[:-3] not in ids
        assert pr.resolve_link(rel[:-3]) is None
        assert f"wiki/{rel}" not in ai_paths
        assert not pr.ai_allowed(f"wiki/{rel}")
        assert pr.wiki(rel[:-3]).body  # Existing direct links still open the record.
    for rel in concepts:
        assert rel[:-3] in ids
        assert f"wiki/{rel}" in ai_paths
        assert pr.ai_allowed(f"wiki/{rel}")


def test_review_discussions_are_soft_attention(project_dir: Path):
    """被 lab 的 pending_review 指向的讨论：review_only，首页里标为"过目即可"并排在真正等回答的问题之后。"""
    pr = Project(project_dir)
    fm.update(project_dir / "labs" / "01-first-task" / "brief.md", status="done", pending_review="2026-10-02-which-limit")
    d = pr.discussion("2026-10-02-which-limit")
    assert d.extra["review_only"] is True and d.extra["review_lab"] == "01-first-task"
    pr.new_discussion("真正的问题", "A 还是 B？", asked_by="agent")
    att = pr.attention()
    disc = [i for i in att["items"] if i["kind"] == "discussion"]
    assert disc[0]["title"] == "真正的问题" and not disc[0].get("soft")
    assert disc[1]["id"] == "2026-10-02-which-limit" and disc[1]["soft"] and "过目即可" in disc[1]["why"]
    assert att["soft_total"] == 1 and att["hard_total"] == att["total"] - 1
