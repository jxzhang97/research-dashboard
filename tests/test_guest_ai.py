"""只读访客的控件显示开关、访客投稿层（留名字、负责人放行后才派 agent）、给 AI 读的 markdown 出口。"""

from pathlib import Path

from fastapi.testclient import TestClient

from rd_core import fm
from rd_core.project import Project
from rd_core.server import create_app

AI_HOST = {"x-forwarded-proto": "https", "x-forwarded-host": "demo.example"}


def _enable_guest(project_dir: Path) -> None:
    p = project_dir / "config.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("guest_submissions = false", "guest_submissions = true"), encoding="utf-8")


def _clients(project_dir: Path) -> tuple[TestClient, TestClient]:
    """(课题负责人：本机地址, 外人：校园网地址)。"""
    app = create_app(Project(project_dir))
    return TestClient(app, client=("127.0.0.1", 5000)), TestClient(app, client=("169.231.1.1", 5000))


def test_readonly_flags_in_overview(project_dir: Path):
    _, outsider = _clients(project_dir)
    o = outsider.get("/api/overview").json()
    assert o["readonly"] is True and o["readonly_show_controls"] is True and o["guest_submissions"] is False
    assert o["ai_entry"].endswith("/llms.txt")
    # 关掉开关 → 前端整块隐藏
    p = project_dir / "config.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("readonly_show_controls = true", "readonly_show_controls = false"), encoding="utf-8")
    assert outsider.get("/api/overview").json()["readonly_show_controls"] is False


def test_guest_endpoints_closed_by_default(project_dir: Path):
    _, outsider = _clients(project_dir)
    assert outsider.post("/api/guest/ideas", json={"name": "小王", "text": "一个想法"}).status_code == 403
    assert outsider.post("/api/guest/discussion", json={"name": "小王", "title": "问", "text": "为什么"}).status_code == 403


def test_guest_idea_waits_for_owner(project_dir: Path):
    _enable_guest(project_dir)
    owner, outsider = _clients(project_dir)
    pr = Project(project_dir)
    # 外人：名字必填；其他写操作仍然 403
    assert outsider.post("/api/guest/ideas", json={"name": " ", "text": "x"}).status_code == 400
    assert outsider.post("/api/ideas", json={"text": "直接写"}).status_code == 403
    assert outsider.post("/api/runs", json={"prompt": "rm", "label": "x"}).status_code == 403
    r = outsider.post("/api/guest/ideas", json={"name": "小王", "text": "量子度规能不能给个下界？"})
    assert r.status_code == 200
    slug = r.json()["id"]
    meta, body = fm.read(project_dir / "ideas" / f"{slug}.md")
    assert meta["source"] == "guest" and meta["author"] == "小王" and meta["from_ip"] == "169.231.1.1"
    assert "量子度规能不能给个下界" in body and "投稿人：小王" in body
    # 没放行：不进待办，但首页提醒负责人；外人也能看到自己的投稿
    assert all(w["kind"] != "triage_idea" for w in pr.pending_work())
    assert any(it["kind"] == "idea" and it["id"] == slug and "小王" in it["why"] for it in pr.attention()["items"])
    assert outsider.get(f"/api/ideas/{slug}").json()["meta"]["author"] == "小王"
    # 外人不能放行；负责人放行后进待办
    assert outsider.post(f"/api/ideas/{slug}/triage", json={}).status_code == 403
    assert owner.post(f"/api/ideas/{slug}/triage", json={}).status_code == 200
    kinds = {(w["kind"], w["id"]) for w in pr.pending_work()}
    live = {str(x.get("label", "")) for x in pr.runs() if x.get("status") in ("queued", "running")}
    assert ("triage_idea", slug) in kinds or f"triage_idea:{slug}" in live
    assert not any(it["id"] == slug for it in pr.attention()["items"])


def test_guest_question_waits_for_owner(project_dir: Path):
    _enable_guest(project_dir)
    owner, outsider = _clients(project_dir)
    pr = Project(project_dir)
    r = outsider.post("/api/guest/discussion", json={"name": "小李", "title": "平带 BEC 的临界温度", "text": "怎么估？"})
    assert r.status_code == 200
    did = r.json()["id"]
    meta, body = fm.read(project_dir / "discussion" / f"{did}.md")
    assert meta["asked_by"] == "guest" and meta["author"] == "小李" and meta["status"] == "open"
    assert "提问人：小李" in body
    assert all(w["id"] != did for w in pr.pending_work())
    assert any(it["id"] == did and "小李" in it["why"] for it in pr.attention()["items"])
    assert outsider.get(f"/api/discussion/{did}").json()["meta"]["author"] == "小李"
    assert outsider.post(f"/api/discussion/{did}/approve", json={}).status_code == 403
    assert owner.post(f"/api/discussion/{did}/approve", json={}).status_code == 200
    kinds = {(w["kind"], w["id"]) for w in pr.pending_work()}
    live = {str(x.get("label", "")) for x in pr.runs() if x.get("status") in ("queued", "running")}
    assert ("answer_user_question", did) in kinds or f"answer_user_question:{did}" in live


def test_llms_and_md_endpoints(project_dir: Path):
    _, outsider = _clients(project_dir)
    lab = project_dir / "labs" / "01-first-task"
    (lab / "report.md").write_text("---\ntitle: 第一个任务\nstatus: done\n---\n# 第一个任务\n\n见 [[quantum-metric]] 与 [[2104.14257]]。\n\n![主图](fig/main.png)\n\n细节在 [notes](notes.md#x)。\n", encoding="utf-8")
    txt = outsider.get("/llms.txt", headers=AI_HOST).text
    assert txt.startswith("# demo") and "https://demo.example/llms-full.txt" in txt
    assert "https://demo.example/md/STATUS.md" in txt and "https://demo.example/md/wiki/quantum-metric.md" in txt
    assert "https://demo.example/md/labs/01-first-task/report.md" in txt and "https://demo.example/md/references/cards/2104.14257.md" in txt
    # 单页：frontmatter 变成开头几行，[[双括号]] 变绝对链接，图和相对链接变绝对地址
    md = outsider.get("/md/labs/01-first-task/report.md", headers=AI_HOST)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "<!-- labs/01-first-task/report.md -->" in md.text and "- title: 第一个任务" in md.text
    assert "[quantum-metric](https://demo.example/md/wiki/quantum-metric.md)" in md.text
    assert "[2104.14257](https://demo.example/md/references/cards/2104.14257.md)" in md.text
    assert "(https://demo.example/api/file?path=labs/01-first-task/fig/main.png)" in md.text
    assert "(https://demo.example/md/labs/01-first-task/notes.md#x)" in md.text
    # 不该给的：运行记录、原始 PDF、交接单、越界
    (lab / "handoff.md").write_text("交接单", encoding="utf-8")
    for bad in ("/md/.dashboard/state.json", "/md/references/raw/x.pdf", "/md/labs/01-first-task/handoff.md", "/md/../config.toml", "/md/config.toml"):
        assert outsider.get(bad).status_code in (403, 404), bad
    full = outsider.get("/llms-full.txt").text
    assert "═══ Wiki" in full and "<!-- STATUS.md -->" in full and "<!-- labs/01-first-task/report.md -->" in full
    html = outsider.get("/", headers={"user-agent": "Mozilla/5.0 Safari/605.1.15", "accept": "text/html,*/*"}).text
    assert html.count("/llms.txt") >= 1  # 网页壳里有 rel=alternate 与 noscript 的入口


def test_root_serves_markdown_to_ai_and_html_to_browsers(project_dir: Path):
    """合作者把根地址直接丢给 AI 也行：不跑 JS 的来访者在根地址拿到 llms.txt 的目录，浏览器拿到网页壳。"""
    _, outsider = _clients(project_dir)
    browser = {"user-agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
               "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    r = outsider.get("/", headers=browser)
    assert r.headers["content-type"].startswith("text/html") and "<script" in r.text
    for ua in ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
               "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "PerplexityBot/1.0", "curl/8.4.0"):
        r = outsider.get("/", headers={"user-agent": ua, "accept": "text/html,*/*"})
        assert r.headers["content-type"].startswith("text/markdown"), ua
        assert r.text.startswith("# demo") and "/md/STATUS.md" in r.text
    # 没说要 html 的（通用 HTTP 客户端）也给 markdown
    r = outsider.get("/", headers={"user-agent": "SomeTool/1.0", "accept": "*/*"})
    assert r.headers["content-type"].startswith("text/markdown")
