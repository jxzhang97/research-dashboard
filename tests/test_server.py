from pathlib import Path

from fastapi.testclient import TestClient

from rd_core.project import Project
from rd_core.server import create_app


def client(project_dir: Path) -> TestClient:
    return TestClient(create_app(Project(project_dir)))


def test_overview_and_lists(project_dir: Path):
    c = client(project_dir)
    o = c.get("/api/overview").json()
    assert o["project"]["name"] == "demo"
    assert o["attention"]["total"] >= 2
    assert o["counts"]["cards"] == 1
    assert c.get("/api/references").json()["cards"][0]["id"] == "2104.14257"
    assert c.get("/api/wiki/quantum-metric").json()["title"] == "量子度规"
    assert c.get("/api/labs/01-first-task").json()["meta"]["status"] == "awaiting_review"
    assert c.get("/api/ideas").json()["tree"][0]["id"] == "root-idea"
    assert c.get("/api/links").json()["量子度规"]["kind"] == "wiki"
    assert c.get("/").status_code == 200


def test_write_endpoints(project_dir: Path):
    c = client(project_dir)
    r = c.post("/api/discussion/2026-10-02-which-limit/answer", json={"text": "选 B"})
    assert r.json()["status"] == "answered"
    r = c.post("/api/ideas", json={"text": "速记一下"})
    assert r.json()["id"].startswith("inbox/")
    r = c.post("/api/discussion", json={"title": "一个问题", "text": "为什么？"})
    assert c.get(f"/api/discussion/{r.json()['id']}").json()["meta"]["asked_by"] == "user"
    r = c.post("/api/labs/01-first-task/approve")
    assert r.json()["status"] == "approved"
    pending = c.get("/api/pending").json()
    assert {w["kind"] for w in pending["ready"]} >= {"run_lab", "triage_idea", "answer_user_question"}
    assert all(w["kind"] != "digest_answer" for w in pending["ready"])  # 回答走定时的统一消化，不进即时待办
    assert pending["deferred"] == []
    dg = c.get("/api/digest").json()
    assert [t["id"] for t in dg["answered"]] == ["2026-10-02-which-limit"] and dg["digest_minutes"] == 300
    assert c.get("/api/file", params={"path": "../x"}).status_code in (403, 404)
    assert c.get("/api/file", params={"path": "PROJECT.md"}).status_code == 200
    assert c.get("/api/raw", params={"path": "wiki/notation.md"}).json()["meta"]["title"] == "notation"


def test_status_in_overview_and_raw_siblings(project_dir: Path):
    c = client(project_dir)
    o = c.get("/api/overview").json()
    assert o["status"]["path"] == "STATUS.md" and "课题状态" in o["status"]["body"]
    r = c.get("/api/raw", params={"path": "wiki/notation.md"}).json()
    assert "index.md" in r["siblings"] and r["updated"]
    assert c.get("/api/raw", params={"path": "config.toml"}).status_code == 404  # 只开放 md/txt/csv


def test_update_adds_status_md(project_dir: Path):
    import subprocess, sys
    from tests.conftest import ROOT
    (project_dir / "STATUS.md").unlink()
    subprocess.check_call([sys.executable, "-m", "rd_core.cli", "update", str(project_dir)], cwd=ROOT)
    assert (project_dir / "STATUS.md").exists()
    assert "@AGENTS.md" in (project_dir / "CLAUDE.md").read_text()


def test_readonly_for_outside_addresses(project_dir: Path):
    """write_from 之外的地址只能 GET；本机和 Tailscale 网段能写。"""
    app = create_app(Project(project_dir))
    outside = TestClient(app, client=("169.231.1.1", 5000))
    assert outside.get("/api/overview").json()["readonly"] is True
    assert outside.get("/api/labs").status_code == 200
    assert outside.post("/api/ideas", json={"text": "外人写不进来"}).status_code == 403
    tailscale = TestClient(app, client=("100.120.253.99", 5000))
    assert tailscale.get("/api/overview").json()["readonly"] is False
    assert tailscale.post("/api/ideas", json={"text": "自己人"}).status_code == 200
