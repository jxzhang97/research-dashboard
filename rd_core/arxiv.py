"""每日 arXiv 扫描：按分类 + 关键词/作者拉新文章，写成 references/inbox/<id>.md 候选，等用户审批。
第一步不调用模型，只按关键词命中排序；"为什么相关"由随后的 agent 运行补写。"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import fm
from .project import Project, now_str

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _seen_path(project: Project) -> Path:
    return project.root / "references" / "inbox" / ".seen.json"


def load_seen(project: Project) -> dict:
    p = _seen_path(project)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_seen(project: Project, seen: dict) -> None:
    p = _seen_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def _arxiv_id(entry_id: str) -> str:
    m = re.search(r"abs/([^v]+)(v\d+)?$", entry_id)
    return m.group(1) if m else entry_id.rsplit("/", 1)[-1]


def fetch(categories: list[str], max_results: int = 100, start: int = 0) -> list[dict]:
    cat_q = " OR ".join(f"cat:{c}" for c in categories) or "cat:cond-mat.str-el"
    url = API + "?" + urllib.parse.urlencode({
        "search_query": cat_q, "sortBy": "submittedDate", "sortOrder": "descending",
        "start": start, "max_results": max_results,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "research-dashboard/0.1 (arxiv scan)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    root = ET.fromstring(data)
    out = []
    for e in root.findall("a:entry", NS):
        eid = e.findtext("a:id", default="", namespaces=NS)
        out.append({
            "arxiv": _arxiv_id(eid),
            "title": re.sub(r"\s+", " ", e.findtext("a:title", default="", namespaces=NS)).strip(),
            "abstract": re.sub(r"\s+", " ", e.findtext("a:summary", default="", namespaces=NS)).strip(),
            "authors": [a.findtext("a:name", default="", namespaces=NS) for a in e.findall("a:author", NS)],
            "published": e.findtext("a:published", default="", namespaces=NS)[:10],
            "updated": e.findtext("a:updated", default="", namespaces=NS)[:10],
            "categories": [c.get("term") for c in e.findall("a:category", NS)],
            "url": eid,
        })
    return out


def score(entry: dict, keywords: list[str], authors: list[str]) -> tuple[int, list[str]]:
    text = (entry["title"] + " " + entry["abstract"]).lower()
    hits = []
    s = 0
    for kw in keywords:
        k = kw.lower().strip()
        if k and k in text:
            hits.append(kw)
            s += 3 if k in entry["title"].lower() else 1
    for au in authors:
        a = au.lower().strip()
        if a and any(a in x.lower() for x in entry["authors"]):
            hits.append(f"作者:{au}")
            s += 3
    return s, hits


def scan(project: Project, dry_run: bool = False) -> dict:
    from . import config
    cfg = config.load(project.root)["arxiv"]
    if not cfg.get("enabled", True):
        return {"skipped": "arxiv.enabled = false"}
    if not cfg["keywords"] and not cfg["authors"]:
        return {"skipped": "config.toml 的 [arxiv] keywords 和 authors 都为空；先填关键词，否则每天只能随机抓"}
    seen = load_seen(project)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(cfg["lookback_days"]))).strftime("%Y-%m-%d")
    entries = []
    for start in (0, 100, 200):
        batch = fetch(cfg["categories"], max_results=100, start=start)
        entries += batch
        if not batch or batch[-1]["published"] < cutoff:
            break
        time.sleep(3)  # arXiv API 礼貌间隔
    fresh = [e for e in entries if e["published"] >= cutoff and e["arxiv"] not in seen]
    ranked = []
    for e in fresh:
        s, hits = score(e, cfg["keywords"], cfg["authors"])
        if s > 0:
            ranked.append((s, hits, e))
    ranked.sort(key=lambda x: -x[0])
    limit = int(cfg["max_per_day"]) * 2  # 多给 agent 一倍，由它挑
    chosen = ranked[:limit]
    written = []
    for s, hits, e in chosen:
        if dry_run:
            written.append({"arxiv": e["arxiv"], "score": s, "title": e["title"]})
            continue
        p = project.root / "references" / "inbox" / f"{e['arxiv']}.md"
        meta = {
            "title": e["title"], "arxiv": e["arxiv"], "authors": e["authors"], "published": e["published"],
            "categories": e["categories"], "url": e["url"], "status": "pending", "score": s,
            "hits": hits, "reason": "", "found": now_str(), "source": "arxiv-scan",
        }
        authors = ", ".join(e["authors"])
        body = (f"# {e['title']}\n\n**作者**：{authors}\n\n**摘要**：{e['abstract']}\n\n"
                "## 为什么可能相关\n\n（待 agent 基于摘要补写，并标注「仅基于摘要」）\n")
        fm.write(p, meta, body)
        written.append({"arxiv": e["arxiv"], "score": s, "title": e["title"]})
    if not dry_run:
        for e in fresh:
            seen[e["arxiv"]] = {"t": now_str(), "written": any(w["arxiv"] == e["arxiv"] for w in written)}
        save_seen(project, seen)
        if written:
            project.append_log("arXiv 扫描", f"新增 {len(written)} 篇候选到 references/inbox/")
    return {"fetched": len(entries), "fresh": len(fresh), "written": written, "cutoff": cutoff}
