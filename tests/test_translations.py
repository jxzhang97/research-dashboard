import json

from fastapi.testclient import TestClient

from rd_core import fm
from rd_core.project import Project
from rd_core.server import create_app
from rd_core.translations import catalog, source_hash


def install(root):
    path = "discussion/2026-10-02-which-limit.md"
    directory = root / "translations/en"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"enabled": True, "batches": ["content.json"]}))
    (directory / "content.json").write_text(json.dumps({
        "schema_version": 1, "language": "en", "documents": {
            path: {"title": "Which limit?", "body": "## Question\n\nA or B?", "source_sha256": source_hash(root/path)}
        }}))
    return path


def test_opt_in_and_original_apis_unchanged(project_dir):
    project = Project(project_dir)
    assert catalog(project)["enabled"] is False
    path = install(project_dir)
    before = (project_dir/path).read_bytes()
    client = TestClient(create_app(project))
    translated = client.get("/api/translations")
    assert translated.headers["cache-control"] == "no-store"
    entry = translated.json()["documents"][path]
    assert entry["title"] == "Which limit?"
    assert entry["state"] == "current"
    original = client.get("/api/discussion/2026-10-02-which-limit").json()
    assert original["title"] == "取哪个极限"
    assert original["meta"]["status"] == "open"
    assert (project_dir/path).read_bytes() == before


def test_shared_status_and_new_answer_marks_stale(project_dir):
    path = install(project_dir)
    source = project_dir/path
    fm.update(source, status="resolved")
    assert catalog(Project(project_dir))["documents"][path]["state"] == "current"
    fm.append(source, "\n## 回答\n\n选 B。\n")
    entry = catalog(Project(project_dir))["documents"][path]
    assert entry["state"] == "stale"
    assert "选 B" in entry["source_body"]
    assert entry["body"] == "## Question\n\nA or B?"


def test_missing_or_invalid_batch_does_not_break_chinese(project_dir):
    path = install(project_dir)
    directory = project_dir/"translations/en"
    (directory/"content.json").write_text("{")
    result = catalog(Project(project_dir))
    assert result["documents"] == {}
    assert result["errors"] == ["content.json"]
    (directory/"manifest.json").write_text(json.dumps({"enabled": True, "batches": ["../../config.toml"]}))
    assert catalog(Project(project_dir))["documents"] == {}
