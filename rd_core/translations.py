"""Optional, read-only translations. Workflow records always remain in the source files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from . import fm

DISPLAY_FIELDS = {"verdict", "tags", "reason"}


def metadata_hash(meta: dict, keys) -> str:
    values = {key: meta.get(key) for key in keys}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def gallery_sources(project) -> dict[str, str]:
    """Match the live Lab gallery's report-first caption selection, without writes."""
    from .project import figure_captions
    sources = {}
    for brief in sorted((project.root / "labs").glob("*/brief.md")):
        folder = brief.parent
        captions = {}
        for name in ("report.md", "notes.md"):
            source = folder / name
            if source.is_file():
                for filename, caption in figure_captions(fm.read(source)[1]).items():
                    captions.setdefault(filename, caption)
        seen = set()
        for image in sorted(folder.rglob("*"), key=lambda p: (0 if p.relative_to(folder).parts[:1] in (("fig",), ("figs",)) else 1, str(p))):
            if not image.is_file() or image.name.startswith(".") or image.suffix.lower() not in (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp") or "writing-test" in image.parts or "__pycache__" in image.parts or image.name in seen:
                continue
            seen.add(image.name)
            if image.name in captions:
                sources[image.relative_to(project.root).as_posix()] = captions[image.name]
    return sources


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
                fields = entry.get("fields", {})
                if not isinstance(fields, dict) or not set(fields).issubset(DISPLAY_FIELDS):
                    raise ValueError("Invalid translated display fields")
                if "verdict" in fields and not isinstance(fields["verdict"], str):
                    raise ValueError("Invalid translated verdict")
                if "reason" in fields and not isinstance(fields["reason"], str):
                    raise ValueError("Invalid translated relevance reason")
                if "tags" in fields and (not isinstance(fields["tags"], list) or not all(isinstance(tag, str) for tag in fields["tags"])):
                    raise ValueError("Invalid translated tags")
                if fields and not isinstance(entry.get("source_meta_sha256"), str):
                    raise ValueError("Missing display field source hash")
                source_field_keys = set(meta) & DISPLAY_FIELDS
                tracks_fields = "source_meta_sha256" in entry or path.startswith(("ideas/", "references/"))
                fields_changed = tracks_fields and (
                    set(fields) != source_field_keys
                    or bool(fields and metadata_hash(meta, fields) != entry["source_meta_sha256"])
                )
                stale = current_hash != entry["source_sha256"] or fields_changed
                documents[path] = {
                    "title": entry["title"], "body": entry["body"],
                    "fields": fields,
                    "source_sha256": entry["source_sha256"], "current_sha256": current_hash,
                    "state": "stale" if stale else "current",
                    "source_headings": re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", original, re.M),
                    "source_body": original if stale else None,
                    "source_fields": {key: meta.get(key) for key in source_field_keys | set(fields)} if stale else None,
                }
        except (OSError, ValueError, KeyError, TypeError, PermissionError):
            errors.append(str(name))
    captions = {}
    if manifest.get("gallery"):
        sources = gallery_sources(project)
        for name in manifest["gallery"]:
            try:
                batch_path = (directory / name).resolve()
                if not batch_path.is_relative_to(directory.resolve()) or batch_path.suffix != ".json":
                    raise ValueError("Invalid gallery batch path")
                batch = json.loads(batch_path.read_text(encoding="utf-8"))
                if batch.get("language") != "en" or batch.get("schema_version") != 1:
                    raise ValueError("Unsupported gallery format")
                for path, entry in batch["captions"].items():
                    if path not in sources:
                        continue
                    if not all(isinstance(entry.get(k), str) for k in ("text", "source_sha256")):
                        raise ValueError("Invalid gallery caption")
                    source = sources[path]
                    stale = hashlib.sha256(source.encode("utf-8")).hexdigest() != entry["source_sha256"]
                    captions[path] = {"text": entry["text"], "state": "stale" if stale else "current", "source_text": source if stale else None}
            except (OSError, ValueError, KeyError, TypeError, PermissionError):
                errors.append(str(name))
    images = {}
    for name in manifest.get("images", []):
        try:
            batch_path = (directory / name).resolve()
            if not batch_path.is_relative_to(directory.resolve()) or batch_path.suffix != ".json":
                raise ValueError("Invalid image translation batch path")
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            if batch.get("language") != "en" or batch.get("schema_version") != 1:
                raise ValueError("Unsupported image translation format")
            for path, entry in batch["images"].items():
                source = project.safe_path(path)
                target = project.safe_path(entry["path"])
                if not target.is_relative_to((directory / "images").resolve()):
                    raise ValueError("Image translation must be in translations/en/images")
                if any(p.suffix.lower() not in (".png", ".svg", ".jpg", ".jpeg", ".webp") for p in (source, target)):
                    raise ValueError("Invalid translated image type")
                if not source.is_file() or not target.is_file():
                    continue
                current_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                images[path] = {
                    "path": entry["path"], "source_sha256": entry["source_sha256"],
                    "current_sha256": current_hash,
                    "asset_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "state": "current" if current_hash == entry["source_sha256"] else "stale",
                }
        except (OSError, ValueError, KeyError, TypeError, PermissionError):
            errors.append(str(name))
    return {"enabled": True, "language": "en", "documents": documents, "captions": captions, "images": images, "errors": errors}
