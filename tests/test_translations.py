import json
import hashlib

from fastapi.testclient import TestClient

from rd_core import fm
from rd_core.project import Project
from rd_core.server import create_app
from rd_core.translations import catalog, metadata_hash, source_hash


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


def test_question_verdict_freshness_preserves_live_workflow(project_dir):
    install(project_dir)
    path = "ideas/test-question.md"
    source = project_dir / path
    source.parent.mkdir(exist_ok=True)
    fm.write(source, {"title": "问题", "verdict": "有待检验", "tags": ["方法"], "status": "seed"}, "## 当前回答\n还需要证据。\n")
    meta, _ = fm.read(source)
    entry = {"title": "A question", "body": "## Current answer\nMore evidence is needed.\n", "source_sha256": source_hash(source),
             "fields": {"verdict": "Still to be tested", "tags": ["method"]},
             "source_meta_sha256": metadata_hash(meta, ["verdict", "tags"])}
    batch = project_dir / "translations/en/content.json"
    batch.write_text(json.dumps({"schema_version": 1, "language": "en", "documents": {path: entry}}))
    project = Project(project_dir)
    assert catalog(project)["documents"][path]["state"] == "current"
    fm.update(source, status="resolved")
    assert catalog(project)["documents"][path]["state"] == "current"
    client = TestClient(create_app(project))
    original = client.get("/api/ideas/test-question").json()
    assert original["meta"]["status"] == "resolved"
    assert original["meta"]["verdict"] == "有待检验"
    fm.update(source, verdict="已获数值支持")
    changed = catalog(project)["documents"][path]
    assert changed["state"] == "stale"
    assert changed["fields"]["verdict"] == "Still to be tested"
    assert changed["source_fields"]["verdict"] == "已获数值支持"


def test_translation_fields_cannot_replace_workflow_state(project_dir):
    path = install(project_dir)
    batch = project_dir / "translations/en/content.json"
    data = json.loads(batch.read_text())
    data["documents"][path]["fields"] = {"status": "resolved"}
    batch.write_text(json.dumps(data))
    assert catalog(Project(project_dir))["documents"] == {}
    assert fm.read(project_dir/path)[0]["status"] == "open"


def test_new_question_verdict_marks_existing_translation_stale(project_dir):
    install(project_dir)
    path = "ideas/new-question.md"
    source = project_dir / path
    source.parent.mkdir(exist_ok=True)
    fm.write(source, {"title": "问题", "status": "seed"}, "## 当前回答\n待检验。\n")
    batch = project_dir / "translations/en/content.json"
    batch.write_text(json.dumps({"schema_version": 1, "language": "en", "documents": {
        path: {"title": "A question", "body": "## Current answer\nTo be tested.\n", "source_sha256": source_hash(source)}
    }}))
    project = Project(project_dir)
    assert catalog(project)["documents"][path]["state"] == "current"
    fm.update(source, status="exploring")
    assert catalog(project)["documents"][path]["state"] == "current"
    fm.update(source, verdict="数值支持")
    entry = catalog(project)["documents"][path]
    assert entry["state"] == "stale"
    assert entry["source_fields"]["verdict"] == "数值支持"


def test_gallery_caption_freshness_tracks_caption_not_unrelated_notes(project_dir):
    install(project_dir)
    folder = project_dir / "labs/99-gallery-test"
    (folder / "fig").mkdir(parents=True)
    (folder / "brief.md").write_text("# 图例测试\n")
    image = folder / "fig/curve.png"
    image.write_bytes(b"unchanged image bytes")
    notes = folder / "notes.md"
    original_caption = "曲线先升高后变平"
    notes.write_text(f"# 笔记\n![{original_caption}](fig/curve.png)\n")
    path = image.relative_to(project_dir).as_posix()
    directory = project_dir / "translations/en"
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["gallery"] = ["gallery.json"]
    (directory / "manifest.json").write_text(json.dumps(manifest))
    (directory / "gallery.json").write_text(json.dumps({"schema_version": 1, "language": "en", "captions": {
        path: {"text": "The curve rises and then levels off.", "source_sha256": hashlib.sha256(original_caption.encode()).hexdigest()}
    }}))
    project = Project(project_dir)
    assert catalog(project)["captions"][path]["state"] == "current"
    notes.write_text(notes.read_text() + "\n不相关的推导更新。\n")
    assert catalog(project)["captions"][path]["state"] == "current"
    notes.write_text(notes.read_text().replace(original_caption, "曲线单调下降"))
    assert catalog(project)["captions"][path]["state"] == "stale"
    assert catalog(project)["captions"][path]["source_text"] == "曲线单调下降"
    # The report takes priority over notes, just as in the original Lab gallery.
    (folder / "report.md").write_text(f"![{original_caption}](fig/curve.png)\n")
    assert catalog(project)["captions"][path]["state"] == "current"
    assert image.read_bytes() == b"unchanged image bytes"
