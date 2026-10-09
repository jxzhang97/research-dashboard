"""扫描课题文件夹：卡片、wiki、lab、discussion、ideas、日志、运行记录。
所有内容都从磁盘实时读取，不建索引；课题规模（几百个文件）下足够快。"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, fm

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
LOG_ENTRY_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)\s*·\s*(.*)$")

LAB_STATUSES = ["draft", "awaiting_review", "approved", "running", "waiting_answer", "done", "blocked", "parked"]
IDEA_STATUSES = ["seed", "exploring", "lab", "resolved", "parked", "dropped"]
DISCUSSION_STATUSES = ["open", "answered", "digested", "resolved"]
INBOX_STATUSES = ["pending", "approved", "rejected", "ingested"]

STATUS_ZH = {
    "draft": "草稿", "awaiting_review": "待过目", "approved": "已批准", "running": "进行中",
    "waiting_answer": "等你回答", "done": "完成", "blocked": "受阻", "parked": "搁置",
    "seed": "萌芽", "exploring": "探索中", "lab": "已立 lab", "resolved": "已解决", "dropped": "否决",
    "open": "待回答", "answered": "已回答", "digested": "已消化",
    "pending": "待审批", "rejected": "已拒绝", "ingested": "已入库",
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def slugify(text: str, maxlen: int = 40) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w一-鿿-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:maxlen] or "untitled"


def _title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def section_text(body: str, heading: str, max_chars: int = 400) -> str:
    """取 markdown 正文里 `## <heading>` 小节的第一段纯文本（去掉图、链接标记），给列表和首页做预览。"""
    m = re.search(rf"^##\s*{re.escape(heading)}[^\n]*\n(.*?)(?=^##\s|\Z)", body or "", re.S | re.M)
    if not m:
        return ""
    sec = m.group(1).strip()
    paras = [x.strip() for x in re.split(r"\n\s*\n", sec) if x.strip() and not x.strip().startswith("![")]
    if not paras:
        return ""
    t = paras[0]
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", t, flags=re.M)
    t = " ".join(t.split())
    return t[: max_chars - 1] + "…" if len(t) > max_chars else t


def figure_captions(body: str) -> dict[str, str]:
    """markdown 里 `![图注](path)` 的 path(basename) → 图注。"""
    out = {}
    for alt, path in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", body or ""):
        out.setdefault(Path(path).name, alt.strip())
    return out


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class Doc:
    kind: str
    id: str
    path: str  # 相对项目根
    title: str
    meta: dict
    body: str
    mtime: float
    extra: dict = field(default_factory=dict)

    def summary(self) -> dict:
        d = {
            "kind": self.kind, "id": self.id, "path": self.path, "title": self.title,
            "meta": self.meta, "mtime": self.mtime,
            "updated": datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M") if self.mtime else "",
        }
        d.update(self.extra)
        return d

    def full(self) -> dict:
        d = self.summary()
        d["body"] = self.body
        return d


class Project:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        if not (self.root / "config.toml").exists():
            raise FileNotFoundError(f"{self.root} 不是课题文件夹（没有 config.toml）")
        self.dash = self.root / ".dashboard"
        self.dash.mkdir(exist_ok=True)

    # ---------- 通用 ----------
    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def safe_path(self, rel: str) -> Path:
        """把相对路径解析成项目内的绝对路径；越界就拒绝。"""
        p = (self.root / rel).resolve()
        if self.root != p and self.root not in p.parents:
            raise PermissionError(f"路径越界: {rel}")
        return p

    def _read_doc(self, kind: str, path: Path, id_: str | None = None) -> Doc:
        meta, body = fm.read(path)
        id_ = id_ or path.stem
        title = meta.get("title") or _title_from_body(body, id_)
        return Doc(kind=kind, id=id_, path=self.rel(path), title=str(title), meta=meta, body=body, mtime=_mtime(path))

    def _md_files(self, d: Path, recursive: bool = False) -> list[Path]:
        if not d.exists():
            return []
        it = d.rglob("*.md") if recursive else d.glob("*.md")
        return sorted(p for p in it if not p.name.startswith(".") and p.name.lower() != "readme.md")

    # ---------- references ----------
    def cards(self) -> list[Doc]:
        docs = [self._read_doc("card", p) for p in self._md_files(self.root / "references" / "cards")]
        docs.sort(key=lambda d: d.mtime, reverse=True)
        return docs

    def card(self, key: str) -> Doc:
        return self._read_doc("card", self.safe_path(f"references/cards/{key}.md"))

    def inbox(self) -> list[Doc]:
        docs = [self._read_doc("inbox", p) for p in self._md_files(self.root / "references" / "inbox")]
        order = {s: i for i, s in enumerate(INBOX_STATUSES)}
        docs.sort(key=lambda d: (order.get(d.meta.get("status", "pending"), 9), -d.mtime))
        return docs

    def set_inbox_status(self, key: str, status: str) -> dict:
        assert status in INBOX_STATUSES, status
        p = self.safe_path(f"references/inbox/{key}.md")
        return fm.update(p, status=status, decided=now_str())

    # ---------- wiki ----------
    def wiki_pages(self) -> list[Doc]:
        docs = []
        for p in self._md_files(self.root / "wiki", recursive=True):
            if "handoff" in p.relative_to(self.root / "wiki").parts[:-1]:
                continue  # wiki/handoff/ 是写给 Codex 的交接单，不是概念页
            slug = self.rel(p)[len("wiki/"):-3]
            d = self._read_doc("wiki", p, id_=slug)
            d.extra["links"] = sorted({m.group(1).strip() for m in WIKILINK_RE.finditer(d.body)})
            docs.append(d)
        docs.sort(key=lambda d: d.id)
        return docs

    def wiki(self, slug: str) -> Doc:
        d = self._read_doc("wiki", self.safe_path(f"wiki/{slug}.md"), id_=slug)
        d.extra["links"] = sorted({m.group(1).strip() for m in WIKILINK_RE.finditer(d.body)})
        d.extra["backlinks"] = [
            {"id": o.id, "title": o.title}
            for o in self.wiki_pages()
            if o.id != slug and (slug in o.extra["links"] or d.title in o.extra["links"])
        ]
        return d

    def resolve_link(self, target: str) -> dict | None:
        """[[target]] 依次在 wiki、卡片、lab、idea、discussion 里找。"""
        t = target.strip()
        for d in self.wiki_pages():
            if d.id == t or d.title == t or d.id.split("/")[-1] == t:
                return {"kind": "wiki", "id": d.id}
        for d in self.cards():
            if d.id == t or d.title == t:
                return {"kind": "card", "id": d.id}
        for d in self.labs():
            if d.id == t or d.title == t:
                return {"kind": "lab", "id": d.id}
        for d in self.ideas():
            if d.id == t or d.title == t:
                return {"kind": "idea", "id": d.id}
        for d in self.discussions():
            if d.id == t or d.title == t:
                return {"kind": "discussion", "id": d.id}
        return None

    def link_table(self) -> dict[str, dict]:
        """一次性给前端所有可解析的链接目标。"""
        table: dict[str, dict] = {}
        for kind, docs in (
            ("discussion", self.discussions()), ("idea", self.ideas()), ("lab", self.labs()),
            ("card", self.cards()), ("wiki", self.wiki_pages()),
        ):
            for d in docs:
                for key in {d.id, d.title, d.id.split("/")[-1]}:
                    table[key] = {"kind": kind, "id": d.id}
        return table

    # ---------- labs ----------
    def labs(self) -> list[Doc]:
        docs = []
        labs_dir = self.root / "labs"
        if labs_dir.exists():
            for d in sorted(labs_dir.iterdir()):
                if d.is_dir() and (d / "brief.md").exists() and not d.name.startswith("."):
                    docs.append(self._lab_doc(d))
        docs.sort(key=lambda d: d.id, reverse=True)
        self._annotate_runs(docs)
        return docs

    # ---------- 活着的运行（去重派发、续跑判断都靠它） ----------
    def live_runs(self) -> list[dict]:
        """status 为 queued/running 且不陈旧的运行记录。running 以 started + timeout 为限；
        queued 只有 id 里的时间戳，排队超过一天当作陈旧（服务器死了留下的）。"""
        timeout = int(config.load(self.root)["agent"].get("timeout_minutes", 240)) * 60 + 600
        now = time.time()
        host = config.hostname()
        out = []
        for m in self.runs(200):
            st = m.get("status")
            if st not in ("queued", "running"):
                continue
            # 本机的记录：排队/运行它的进程已经不在（服务器重启、tick 被杀）就不算活着
            rp = m.get("runner_pid")
            if m.get("host") == host and rp and not _pid_alive(int(rp)):
                continue
            if st == "running":
                try:
                    t = datetime.strptime(m.get("started") or "", "%Y-%m-%d %H:%M:%S").timestamp()
                except ValueError:
                    t = 0
                if now - t < timeout:
                    out.append(m)
            elif st == "queued":
                try:
                    t = datetime.strptime(str(m.get("id", ""))[:15], "%Y%m%d-%H%M%S").timestamp()
                except ValueError:
                    t = 0
                if now - t < 86400:
                    out.append(m)
        return out

    def reap_stale_runs(self) -> list[str]:
        """服务启动时调用：本机上次留下的 queued（没来得及跑）和 running（进程已不在）记录标为 stopped / failed，
        免得被 live_runs 当成活着的运行而挡住派发。别的进程（launchd 的 tick）正排着队的记录，其 runner_pid 还活着，不动。"""
        host = config.hostname()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        out = []
        for m in self.runs(200):
            st = m.get("status")
            if st not in ("queued", "running"):
                continue
            if m.get("host") and m.get("host") != host:
                continue
            rp, pid = m.get("runner_pid"), m.get("pid")
            if rp and _pid_alive(int(rp)):
                continue  # 还有人在排/在跑它
            if st == "running" and pid and _pid_alive(int(pid)):
                continue
            if not rp and st == "queued" and not m.get("host"):
                # 旧版本服务器队列里的记录（没有 runner_pid 也没有 host）：服务器既然重启了，它们一定不会再跑
                pass
            elif not rp:
                continue  # 没法判断归属的记录不碰
            m["status"] = "stopped" if st == "queued" else "failed"
            m["ended"] = now
            m["note"] = "服务重启时清理：排队/运行它的进程已不在"
            (self.dash / "runs" / m["id"] / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(m["id"])
        return out

    @staticmethod
    def _run_for_lab(runs: list[dict], lab_id: str) -> dict | None:
        for m in runs:
            if str(m.get("label", "")).endswith(f":{lab_id}"):
                return m
        return None

    def last_lab_run(self, lab_id: str) -> dict | None:
        """最近一次与这个 lab 有关的运行（任何状态），给续跑提示词用。"""
        return self._run_for_lab(self.runs(200), lab_id)

    def _annotate_runs(self, docs: list[Doc]) -> None:
        """status 为 running 但没有活着的运行 → stale_run（上次运行中断，等自动续跑）。"""
        if not any(d.meta.get("status") == "running" for d in docs):
            for d in docs:
                d.extra["stale_run"] = False
            return
        live = self.live_runs()
        for d in docs:
            d.extra["stale_run"] = d.meta.get("status") == "running" and self._run_for_lab(live, d.id) is None

    # ---------- 审计报告（labs/NN/audit/*.md，见 rd-audit skill） ----------
    def _audits(self, d: Path) -> list[dict]:
        out = []
        for p in sorted((d / "audit").glob("*.md")) if (d / "audit").exists() else []:
            if p.name.startswith("prompt"):
                continue
            meta, _ = fm.read(p)
            if not meta.get("kind"):
                continue
            out.append({"path": self.rel(p), "name": p.name, "kind": meta.get("kind"), "verdict": meta.get("verdict", "pass"),
                        "counts": meta.get("counts") or {}, "date": str(meta.get("date", "")), "model": meta.get("model", ""),
                        "handled": bool(meta.get("handled", False)), "title": meta.get("title", p.stem)})
        return out

    @staticmethod
    def _audit_summary(audits: list[dict]) -> dict:
        """每种审计只取最新一份，给列表页和 lab 页的标记用。"""
        latest: dict[str, dict] = {}
        for a in audits:
            latest[a["kind"]] = a
        return latest

    def _lab_doc(self, d: Path) -> Doc:
        doc = self._read_doc("lab", d / "brief.md", id_=d.name)
        doc.meta.setdefault("status", "draft")
        doc.extra["has_report"] = (d / "report.md").exists()
        doc.extra["has_data"] = (d / "DATA.md").exists()
        doc.extra["has_notes"] = (d / "notes.md").exists()
        # PDF 可能在 lab 根目录，也可能在 report/ 之类的子目录
        pdfs = sorted(str(p.relative_to(d)) for p in d.rglob("*.pdf")
                      if not any(part.startswith(".") or part in ("results", "writing-test") for part in p.relative_to(d).parts))
        doc.extra["pdfs"] = pdfs[:20]
        doc.extra["audit"] = self._audit_summary(self._audits(d))
        doc.extra["question"] = doc.extra["answer"] = ""
        doc.extra["notes"] = ""
        if doc.extra["has_report"]:
            rm, rb = fm.read(d / "report.md")
            doc.extra["question"] = section_text(rb, "问题")
            doc.extra["answer"] = section_text(rb, "当前回答")
            doc.extra["notes"] = str(rm.get("notes") or ("notes.md" if doc.extra["has_notes"] else ""))
            doc.extra["short"] = str(rm.get("title") or "")
        return doc

    def lab(self, lab_id: str) -> Doc:
        d = self.safe_path(f"labs/{lab_id}")
        doc = self._lab_doc(d)
        self._annotate_runs([doc])
        doc.extra["has_resume"] = (d / "resume.md").exists()
        for name in ("report.md", "DATA.md"):
            p = d / name
            if p.exists():
                m, b = fm.read(p)
                doc.extra[name.replace(".md", "").lower()] = {"meta": m, "body": b}
        files = []
        images = []
        captions = {}
        for name in ("report.md", "notes.md"):
            if (d / name).exists():
                for k, v in figure_captions(fm.read(d / name)[1]).items():
                    captions.setdefault(k, v)
        seen_names: set[str] = set()
        img_ext = (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp")
        # 先收 fig/（权威图源），再收别处；同名文件（report/figs/ 里的导出副本）只显示一次
        ordered = sorted(d.rglob("*"), key=lambda p: (0 if p.relative_to(d).parts[:1] in (("fig",), ("figs",)) else 1, str(p)))
        for p in ordered:
            if not p.is_file() or p.name.startswith(".") or "__pycache__" in p.parts:
                continue
            rel_in = str(p.relative_to(d))
            files.append({"path": self.rel(p), "name": rel_in, "size": p.stat().st_size})
            if p.suffix.lower() in img_ext and "writing-test" not in p.parts:
                if p.name in seen_names:
                    continue
                seen_names.add(p.name)
                images.append({"path": self.rel(p), "name": rel_in, "caption": captions.get(p.name, "")})
        files.sort(key=lambda f: f["name"])
        doc.extra["files"] = files[:500]
        doc.extra["images"] = images[:200]  # lab 页的图画廊：fig/ 里的图都能看到，图注来自 report.md / notes.md 的 alt 文字
        doc.extra["audits"] = self._audits(d)
        return doc

    def next_lab_id(self, title: str) -> str:
        n = 0
        for d in self.labs():
            m = re.match(r"^(\d+)", d.id)
            if m:
                n = max(n, int(m.group(1)))
        return f"{n + 1:02d}-{slugify(title)}"

    def comment_lab(self, lab_id: str, text: str) -> dict:
        """用户在任务页写的意见：追加到任务书「## 用户意见」（带时间，原话不动），标记 comments_pending，agent 随后按意见修改任务书。"""
        p = self.safe_path(f"labs/{lab_id}/brief.md")
        meta, body = fm.read(p)
        stamp = now_str()
        if "## 用户意见" not in body:
            body = body.rstrip("\n") + "\n\n## 用户意见\n"
        body = body.rstrip("\n") + f"\n\n### 意见 · {stamp}\n\n{text.strip()}\n"
        meta["comments_pending"] = True
        meta["last_comment"] = stamp
        fm.write(p, meta, body)
        self.append_log("用户", f"对任务书 {lab_id} 提了意见", f"labs/{lab_id}/brief.md")
        return meta

    def set_lab_status(self, lab_id: str, status: str) -> dict:
        assert status in LAB_STATUSES, status
        return fm.update(self.safe_path(f"labs/{lab_id}/brief.md"), status=status)

    # ---------- discussion ----------
    def discussions(self) -> list[Doc]:
        docs = [self._read_doc("discussion", p) for p in self._md_files(self.root / "discussion")]
        for d in docs:
            d.meta.setdefault("status", "open")
            d.meta.setdefault("asked_by", "agent")
        order = {s: i for i, s in enumerate(DISCUSSION_STATUSES)}
        docs.sort(key=lambda d: (order.get(d.meta["status"], 9), -d.mtime))
        return docs

    def discussion(self, did: str) -> Doc:
        d = self._read_doc("discussion", self.safe_path(f"discussion/{did}.md"))
        d.meta.setdefault("status", "open")
        d.meta.setdefault("asked_by", "agent")
        return d

    def answer_discussion(self, did: str, text: str) -> dict:
        p = self.safe_path(f"discussion/{did}.md")
        meta, body = fm.read(p)
        stamp = now_str()
        if "## 你的回答" not in body:
            body = body.rstrip("\n") + "\n\n## 你的回答\n"
        body = body.rstrip("\n") + f"\n\n### 回答 · {stamp}\n\n{text.strip()}\n"
        meta["status"] = "answered"
        meta["answered"] = stamp
        fm.write(p, meta, body)
        self.append_log("用户", f"回答了讨论「{meta.get('title', did)}」", f"discussion/{did}.md")
        return meta

    def new_discussion(self, title: str, text: str, asked_by: str = "user") -> str:
        did = f"{today_str()}-{slugify(title)}"
        p = self.root / "discussion" / f"{did}.md"
        i = 2
        while p.exists():
            p = self.root / "discussion" / f"{did}-{i}.md"
            i += 1
        meta = {"title": title, "status": "open", "asked_by": asked_by, "created": now_str()}
        body = f"# {title}\n\n## 问题\n\n{text.strip()}\n"
        fm.write(p, meta, body)
        self.append_log("用户" if asked_by == "user" else "agent", f"新建讨论「{title}」", self.rel(p))
        return p.stem

    # ---------- ideas ----------
    def ideas(self) -> list[Doc]:
        docs = []
        for p in self._md_files(self.root / "ideas"):
            d = self._read_doc("idea", p)
            d.meta.setdefault("status", "seed")
            d.meta.setdefault("kind", "question")
            d.extra["answer"] = section_text(d.body, "当前回答", 240)
            docs.append(d)
        for p in self._md_files(self.root / "ideas" / "inbox"):
            d = self._read_doc("idea", p, id_=f"inbox/{p.stem}")
            d.meta.setdefault("status", "inbox")
            docs.append(d)
        return docs

    def idea(self, slug: str) -> Doc:
        p = self.safe_path(f"ideas/{slug}.md")
        d = self._read_doc("idea", p, id_=slug)
        d.meta.setdefault("status", "inbox" if slug.startswith("inbox/") else "seed")
        return d

    def idea_tree(self) -> list[dict]:
        docs = {d.id: d.summary() for d in self.ideas()}
        for d in docs.values():
            d["children"] = []
        roots = []
        for d in docs.values():
            parent = d["meta"].get("parent")
            if parent and parent in docs and parent != d["id"]:
                docs[parent]["children"].append(d)
            else:
                roots.append(d)
        def sort(nodes):
            nodes.sort(key=lambda n: (n["id"].startswith("inbox/"), n["meta"].get("order", 999), n["id"]))
            for n in nodes:
                sort(n["children"])
        sort(roots)
        return roots

    def capture_idea(self, text: str, title: str | None = None) -> str:
        title = (title or text.strip().splitlines()[0]).strip()[:60]
        stem = f"{today_str()}-{slugify(title)}"
        p = self.root / "ideas" / "inbox" / f"{stem}.md"
        i = 2
        while p.exists():
            p = self.root / "ideas" / "inbox" / f"{stem}-{i}.md"
            i += 1
        meta = {"title": title, "status": "inbox", "created": now_str(), "source": "dashboard"}
        fm.write(p, meta, f"# {title}\n\n{text.strip()}\n")
        self.append_log("用户", f"速记想法「{title}」", self.rel(p))
        return f"inbox/{p.stem}"

    def request_promote(self, slug: str, note: str = "") -> dict:
        p = self.safe_path(f"ideas/{slug}.md")
        return fm.update(p, promote_requested=now_str(), promote_note=note)

    # ---------- log ----------
    def append_log(self, who: str, what: str, link: str | None = None) -> None:
        p = self.root / "log.md"
        line = f"\n## {now_str()} · {who} · {what}\n"
        if link:
            line += f"\n[{link}]({link})\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)

    def log_entries(self, n: int = 30) -> list[dict]:
        p = self.root / "log.md"
        if not p.exists():
            return []
        entries: list[dict] = []
        cur: dict | None = None
        for line in p.read_text(encoding="utf-8").splitlines():
            m = LOG_ENTRY_RE.match(line)
            if m:
                parts = [x.strip() for x in m.group(2).split("·", 1)]
                who, what = (parts + [""])[:2] if len(parts) == 2 else ("", parts[0])
                cur = {"time": m.group(1), "who": who, "what": what, "body": ""}
                entries.append(cur)
            elif cur is not None:
                cur["body"] += line + "\n"
        entries.reverse()
        return entries[:n]

    # ---------- 已读状态 / 红点 ----------
    def _state_path(self) -> Path:
        return self.dash / "state.json"

    def state(self) -> dict:
        p = self._state_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"seen": {}}

    def _save_state(self, s: dict) -> None:
        self._state_path().write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

    def mark_seen(self, kind: str, id_: str) -> None:
        s = self.state()
        s.setdefault("seen", {})[f"{kind}:{id_}"] = time.time()
        self._save_state(s)

    # 工作项的最近一次尝试：失败后一段时间内不重试，避免登录失效之类的问题每 15 秒撞一次
    def record_attempt(self, kind: str, id_: str, status: str) -> None:
        s = self.state()
        key = f"{kind}:{id_}"
        prev = s.setdefault("attempts", {}).get(key) or {}
        fails = 0 if status == "done" else int(prev.get("fails", 0)) + 1  # 连续失败次数，续跑上限用
        s["attempts"][key] = {"t": time.time(), "status": status, "fails": fails}
        self._save_state(s)

    def attempt_info(self, kind: str, id_: str) -> dict | None:
        return self.state().get("attempts", {}).get(f"{kind}:{id_}")

    # Claude 额度用尽：runner 看到 limit 提示就记下重置时刻，到时之前什么都不派
    def set_pause(self, until: float, reason: str = "") -> None:
        s = self.state()
        s["paused_until"] = float(until)
        s["pause_reason"] = reason[:300]
        self._save_state(s)

    def pause_info(self) -> dict | None:
        s = self.state()
        until = float(s.get("paused_until") or 0)
        if until > time.time():
            return {"until": until, "reason": s.get("pause_reason", ""), "until_str": datetime.fromtimestamp(until).strftime("%m-%d %H:%M")}
        return None

    def is_unread(self, kind: str, id_: str, mtime: float) -> bool:
        return self.state().get("seen", {}).get(f"{kind}:{id_}", 0) < mtime

    def attention(self) -> dict:
        """首页"需要你处理"与导航红点的数据源。"""
        items = []
        for d in self.discussions():
            st = d.meta["status"]
            if st == "open" and d.meta.get("asked_by") == "agent":
                items.append({"kind": "discussion", "id": d.id, "title": d.title, "why": "agent 向你提问，等你回答", "time": d.mtime})
            elif st in ("digested", "resolved") and self.is_unread("discussion", d.id, d.mtime):
                items.append({"kind": "discussion", "id": d.id, "title": d.title, "why": "agent 消化了你的回答", "time": d.mtime})
        for d in self.inbox():
            if d.meta.get("status", "pending") == "pending":
                items.append({"kind": "inbox", "id": d.id, "title": d.title, "why": "arXiv 候选，等你审批", "time": d.mtime})
        for d in self.labs():
            st = d.meta.get("status")
            title = d.extra.get("short") or d.title  # 首页用 report.md 的短标题
            if st == "awaiting_review":
                items.append({"kind": "lab", "id": d.id, "title": title, "why": "任务书等你过目", "time": d.mtime})
            elif st == "waiting_answer":
                items.append({"kind": "lab", "id": d.id, "title": title, "why": "任务卡在一个问题上，见讨论", "time": d.mtime})
            elif st in ("done", "blocked") and self.is_unread("lab", d.id, d.mtime):
                items.append({"kind": "lab", "id": d.id, "title": title, "why": "任务" + ("完成" if st == "done" else "受阻") + "，未查看", "time": d.mtime})
        items.sort(key=lambda x: -x["time"])
        counts: dict[str, int] = {}
        for it in items:
            counts[it["kind"]] = counts.get(it["kind"], 0) + 1
        return {"items": items, "counts": counts, "total": len(items)}

    # ---------- 课题状态页 ----------
    def status_doc(self) -> dict | None:
        p = self.root / "STATUS.md"
        if not p.exists():
            return None
        meta, body = fm.read(p)
        return {"path": "STATUS.md", "meta": meta, "body": body, "updated": datetime.fromtimestamp(_mtime(p)).strftime("%Y-%m-%d %H:%M")}

    # ---------- 运行记录 ----------
    def runs(self, n: int = 50) -> list[dict]:
        rd = self.dash / "runs"
        if not rd.exists():
            return []
        out = []
        for d in sorted(rd.iterdir(), reverse=True)[:n]:
            m = d / "meta.json"
            if m.exists():
                try:
                    out.append(json.loads(m.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    continue
        return out

    def run(self, run_id: str) -> dict | None:
        m = self.dash / "runs" / run_id / "meta.json"
        if not m.exists():
            return None
        meta = json.loads(m.read_text(encoding="utf-8"))
        log = self.dash / "runs" / run_id / "log.txt"
        meta["log"] = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        return meta

    # ---------- 待处理工作项（tick 用） ----------
    def pending_work(self) -> list[dict]:
        """待办工作项。任何一项只要已有排队或运行中的记录（label 为 kind:id）就不再列出：
        网页动作、文件监视、launchd 兜底 tick 相隔几秒各扫一次时，同一项不会被派两次。"""
        live = self.live_runs()
        live_labels = {str(m.get("label", "")) for m in live}
        work = []

        def add(kind: str, d: Doc, **extra) -> None:
            if f"{kind}:{d.id}" not in live_labels:
                work.append({"kind": kind, "id": d.id, "path": d.path, "title": d.title, **extra})

        for d in self.discussions():
            if d.meta["status"] == "answered":
                add("digest_answer", d)
            elif d.meta["status"] == "open" and d.meta.get("asked_by") == "user":
                add("answer_user_question", d)
        for d in self.inbox():
            if d.meta.get("status") == "approved":
                add("ingest_reference", d)
        # lab：已批准的派执行；running 但没有活着的运行的派续跑（上次运行被额度/超时/自己提前结束打断）。
        # lab 的"活着"按 label 后缀匹配，手工的 resume_lab:<id>、审计 audit_*:<id> 也算。旧 lab 先。
        for d in sorted(self.labs(), key=lambda x: x.id):
            st = d.meta.get("status")
            busy = self._run_for_lab(live, d.id) is not None
            if st == "approved" and not busy:
                add("run_lab", d)
            elif st == "running" and not busy:
                last = self.last_lab_run(d.id) or {}
                add("resume_lab", d, last_run_id=last.get("id", "（没有记录）"), last_run_status=last.get("status", "?"),
                    last_run_result=" ".join(str(last.get("result") or "（无）").split())[:400])
            elif d.meta.get("comments_pending") and st in ("awaiting_review", "draft", "parked") and not busy:
                add("revise_brief", d)
        for d in self.ideas():
            if d.meta.get("promote_requested") and not d.meta.get("promoted_lab"):
                add("promote_idea", d)
            elif d.id.startswith("inbox/") and not d.meta.get("triaged"):
                add("triage_idea", d)
        return work
