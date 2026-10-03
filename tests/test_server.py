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
    assert {w["kind"] for w in pending["ready"]} >= {"digest_answer", "run_lab", "triage_idea", "answer_user_question"}
    assert pending["deferred"] == []
    assert c.get("/api/file", params={"path": "../x"}).status_code in (403, 404)
    assert c.get("/api/file", params={"path": "PROJECT.md"}).status_code == 200
    assert c.get("/api/raw", params={"path": "wiki/notation.md"}).json()["meta"]["title"] == "notation"
