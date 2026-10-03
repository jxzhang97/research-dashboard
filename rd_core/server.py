"""FastAPI 服务：只读视图 + 四个写入口（回答、审批、速记、立刻执行）。
agent 运行放在后台线程队列里，同一时间只跑一个。"""

from __future__ import annotations

import json
import mimetypes
import queue
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import TEMPLATE_ROOT, config, cores
from .project import Project
from .runner import Runner, new_run_id, stop_run
from .tick import PROMPTS

STATIC = TEMPLATE_ROOT / "dashboard" / "static"


class RunQueue:
    """串行跑 agent；tick 请求会合并（队列里已有 tick 就不再加）。"""

    def __init__(self, project: Project):
        self.project = project
        self.q: queue.Queue = queue.Queue()
        self.current: dict | None = None
        self.pending: list[dict] = []
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, prompt: str, kind: str, label: str, model: str | None = None, effort: str | None = None) -> str:
        run_id = new_run_id(label)
        item = {"id": run_id, "prompt": prompt, "kind": kind, "label": label, "model": model, "effort": effort}
        d = self.project.dash / "runs" / run_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"id": run_id, "kind": kind, "label": label, "status": "queued", "model": model, "prompt": prompt}, ensure_ascii=False), encoding="utf-8")
        with self._lock:
            self.pending.append(item)
        self.q.put(item)
        return run_id

    def submit_tick(self) -> str | None:
        with self._lock:
            if any(p["kind"] == "tick" for p in self.pending) or (self.current and self.current["kind"] == "tick"):
                return None
        return self.submit("", kind="tick", label="tick")

    def _worker(self):
        while True:
            item = self.q.get()
            with self._lock:
                self.pending = [p for p in self.pending if p["id"] != item["id"]]
                self.current = item
            try:
                if item["kind"] == "tick":
                    from .tick import run_pending
                    run_pending(self.project)
                    d = self.project.dash / "runs" / item["id"]
                    (d / "meta.json").write_text(json.dumps({"id": item["id"], "kind": "tick", "label": "tick", "status": "done"}, ensure_ascii=False), encoding="utf-8")
                else:
                    Runner(self.project).run(item["prompt"], kind=item["kind"], label=item["label"], model=item["model"],
                                             effort=item["effort"], run_id=item["id"])
            except Exception as e:  # noqa: BLE001
                d = self.project.dash / "runs" / item["id"]
                d.mkdir(parents=True, exist_ok=True)
                (d / "log.txt").open("a", encoding="utf-8").write(f"队列异常: {e!r}\n")
            finally:
                with self._lock:
                    self.current = None

    def snapshot(self) -> dict:
        with self._lock:
            return {"current": self.current and {k: self.current[k] for k in ("id", "kind", "label")},
                    "pending": [{k: p[k] for k in ("id", "kind", "label")} for p in self.pending]}


class AnswerIn(BaseModel):
    text: str


class CaptureIn(BaseModel):
    text: str
    title: str | None = None


class QuestionIn(BaseModel):
    title: str
    text: str


class RunIn(BaseModel):
    prompt: str
    label: str = "manual"
    model: str | None = None
    effort: str | None = None


class PromoteIn(BaseModel):
    note: str = ""


class SeenIn(BaseModel):
    kind: str
    id: str


def create_app(project: Project) -> FastAPI:
    app = FastAPI(title="research-dashboard")
    rq = RunQueue(project)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    # ---------- 总览 ----------
    @app.get("/api/overview")
    def overview():
        cfg = config.load(project.root)
        pm = project.root / "PROJECT.md"
        return {
            "project": cfg["project"], "models": cfg["models"], "attention": project.attention(), "log": project.log_entries(20),
            "queue": rq.snapshot(), "runs": project.runs(8), "host": config.hostname(),
            "project_md": pm.read_text(encoding="utf-8") if pm.exists() else "",
            "counts": {
                "cards": len(project.cards()), "wiki": len(project.wiki_pages()), "labs": len(project.labs()),
                "discussion": len(project.discussions()), "ideas": len([i for i in project.ideas() if not i.id.startswith("inbox/")]),
                "inbox": len([i for i in project.inbox() if i.meta.get("status") == "pending"]),
            },
        }

    @app.get("/api/links")
    def links():
        return project.link_table()

    @app.post("/api/seen")
    def seen(body: SeenIn):
        project.mark_seen(body.kind, body.id)
        return {"ok": True}

    # ---------- references ----------
    @app.get("/api/references")
    def references():
        return {"cards": [d.summary() for d in project.cards()], "inbox": [d.summary() for d in project.inbox()]}

    @app.get("/api/references/{key}")
    def reference(key: str):
        try:
            return project.card(key).full()
        except FileNotFoundError:
            raise HTTPException(404)

    @app.get("/api/inbox/{key}")
    def inbox_item(key: str):
        try:
            return project._read_doc("inbox", project.safe_path(f"references/inbox/{key}.md")).full()
        except FileNotFoundError:
            raise HTTPException(404)

    @app.post("/api/inbox/{key}/{decision}")
    def inbox_decide(key: str, decision: str):
        if decision not in ("approved", "rejected", "pending"):
            raise HTTPException(400)
        meta = project.set_inbox_status(key, decision)
        project.append_log("用户", f"{'批准' if decision == 'approved' else '拒绝'}了候选文献 {key}", f"references/inbox/{key}.md")
        if decision == "approved":
            rq.submit_tick()
        return meta

    # ---------- wiki ----------
    @app.get("/api/wiki")
    def wiki_list():
        return [d.summary() for d in project.wiki_pages()]

    @app.get("/api/wiki/{slug:path}")
    def wiki_page(slug: str):
        try:
            return project.wiki(slug).full()
        except FileNotFoundError:
            raise HTTPException(404)

    # ---------- labs ----------
    @app.get("/api/labs")
    def labs():
        return [d.summary() for d in project.labs()]

    @app.get("/api/labs/{lab_id}")
    def lab(lab_id: str):
        try:
            return project.lab(lab_id).full()
        except FileNotFoundError:
            raise HTTPException(404)

    @app.post("/api/labs/{lab_id}/approve")
    def lab_approve(lab_id: str):
        meta = project.set_lab_status(lab_id, "approved")
        project.append_log("用户", f"批准了任务书 {lab_id}", f"labs/{lab_id}/brief.md")
        rq.submit_tick()
        return meta

    @app.post("/api/labs/{lab_id}/status/{status}")
    def lab_status(lab_id: str, status: str):
        try:
            meta = project.set_lab_status(lab_id, status)
        except AssertionError:
            raise HTTPException(400)
        project.append_log("用户", f"把任务 {lab_id} 状态改为 {status}", f"labs/{lab_id}/brief.md")
        return meta

    # ---------- discussion ----------
    @app.get("/api/discussion")
    def discussions():
        return [d.summary() for d in project.discussions()]

    @app.get("/api/discussion/{did}")
    def discussion(did: str):
        try:
            return project.discussion(did).full()
        except FileNotFoundError:
            raise HTTPException(404)

    @app.post("/api/discussion/{did}/answer")
    def answer(did: str, body: AnswerIn):
        if not body.text.strip():
            raise HTTPException(400, "空回答")
        meta = project.answer_discussion(did, body.text)
        rq.submit_tick()
        return meta

    @app.post("/api/discussion/{did}/resolve")
    def resolve(did: str):
        from . import fm
        return fm.update(project.safe_path(f"discussion/{did}.md"), status="resolved")

    @app.post("/api/discussion")
    def ask(body: QuestionIn):
        did = project.new_discussion(body.title, body.text, asked_by="user")
        rq.submit_tick()
        return {"id": did}

    # ---------- ideas ----------
    @app.get("/api/ideas")
    def ideas():
        return {"tree": project.idea_tree(), "flat": [d.summary() for d in project.ideas()]}

    @app.get("/api/ideas/{slug:path}")
    def idea(slug: str):
        try:
            return project.idea(slug).full()
        except FileNotFoundError:
            raise HTTPException(404)

    @app.post("/api/ideas")
    def capture(body: CaptureIn):
        if not body.text.strip():
            raise HTTPException(400, "空想法")
        slug = project.capture_idea(body.text, body.title)
        rq.submit_tick()
        return {"id": slug}

    @app.post("/api/ideas/{slug:path}/promote")
    def promote(slug: str, body: PromoteIn):
        meta = project.request_promote(slug, body.note)
        project.append_log("用户", f"请求把想法 {slug} 升级为 lab", f"ideas/{slug}.md")
        rq.submit_tick()
        return meta

    # ---------- runs ----------
    @app.get("/api/runs")
    def runs():
        return {"runs": project.runs(50), "queue": rq.snapshot()}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        r = project.run(run_id)
        if not r:
            raise HTTPException(404)
        return r

    @app.get("/api/runs/{run_id}/stream")
    def run_stream(run_id: str):
        log = project.dash / "runs" / run_id / "log.txt"
        meta_p = project.dash / "runs" / run_id / "meta.json"

        def gen():
            pos = 0
            idle = 0
            while True:
                if log.exists():
                    with log.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(pos)
                        chunk = f.read()
                        pos = f.tell()
                    if chunk:
                        idle = 0
                        for ln in chunk.splitlines():
                            yield f"data: {json.dumps(ln, ensure_ascii=False)}\n\n"
                try:
                    st = json.loads(meta_p.read_text(encoding="utf-8")).get("status")
                except (OSError, json.JSONDecodeError):
                    st = None
                if st in ("done", "failed", "stopped") and idle > 2:
                    yield f"event: end\ndata: {json.dumps(st)}\n\n"
                    return
                idle += 1
                time.sleep(1)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/runs")
    def run_now(body: RunIn):
        if not body.prompt.strip():
            raise HTTPException(400)
        rid = rq.submit(body.prompt, kind="manual", label=body.label, model=body.model, effort=body.effort)
        project.append_log("用户", f"立刻执行：{body.label}", f".dashboard/runs/{rid}/log.txt")
        return {"id": rid}

    @app.post("/api/runs/{run_id}/stop")
    def run_stop(run_id: str):
        return {"ok": stop_run(project, run_id)}

    @app.post("/api/tick")
    def tick():
        return {"id": rq.submit_tick(), "pending": project.pending_work()}

    @app.get("/api/pending")
    def pending():
        return project.pending_work()

    @app.get("/api/cores")
    def cores_status():
        return cores.status(project.root)

    @app.get("/api/prompts")
    def prompts():
        return PROMPTS

    # ---------- 文件 ----------
    @app.get("/api/file")
    def file(path: str):
        try:
            p = project.safe_path(path)
        except PermissionError:
            raise HTTPException(403)
        if not p.is_file():
            raise HTTPException(404)
        mt, _ = mimetypes.guess_type(str(p))
        return FileResponse(str(p), media_type=mt or "application/octet-stream")

    @app.get("/api/raw")
    def raw(path: str):
        try:
            p = project.safe_path(path)
        except PermissionError:
            raise HTTPException(403)
        if not p.is_file():
            raise HTTPException(404)
        from . import fm
        meta, body = fm.read(p)
        return {"path": path, "meta": meta, "body": body}

    return app
