"""Optional, read-only translations. Workflow records always remain in the source files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from . import fm


def source_hash(path: Path) -> str:
    meta, body = fm.read(path)
    # A status-only transition does not change the text that was translated.
    return hashlib.sha256((str(meta.get("title", "")) + "\0" + body).encode("utf-8")).hexdigest()


def catalog(project) -> dict:
    directory = project.root / "translations" / "en"
    manifest_path = directory / "manifest.json"
    empty = {"enabled": False, "language": "en", "documents": {}}
    if not manifest_path.is_file():
        return empty
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if manifest.get("enabled") is not True:
        return empty
    documents = {}
    errors = []
    for name in manifest.get("batches", []):
        try:
            batch_path = (directory / name).resolve()
            if not batch_path.is_relative_to(directory.resolve()) or batch_path.suffix != ".json":
                raise ValueError("Invalid translation batch path")
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            if batch.get("language") != "en" or batch.get("schema_version") != 1:
                raise ValueError("Unsupported translation format")
            for path, entry in batch["documents"].items():
                source = project.safe_path(path)
                if not source.is_file() or source.suffix != ".md":
                    continue
                if not all(isinstance(entry.get(k), str) for k in ("title", "body", "source_sha256")):
                    raise ValueError("Invalid translation entry")
                meta, original = fm.read(source)
                current_hash = hashlib.sha256((str(meta.get("title", "")) + "\0" + original).encode("utf-8")).hexdigest()
                stale = current_hash != entry["source_sha256"]
                documents[path] = {
                    "title": entry["title"], "body": entry["body"],
                    "source_sha256": entry["source_sha256"], "current_sha256": current_hash,
                    "state": "stale" if stale else "current",
                    "source_headings": re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", original, re.M),
                    "source_body": original if stale else None,
                }
        except (OSError, ValueError, KeyError, TypeError, PermissionError):
            errors.append(str(name))
    return {"enabled": True, "language": "en", "documents": documents, "errors": errors}
