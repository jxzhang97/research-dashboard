"""FastAPI 服务：只读视图 + 四个写入口（回答、审批、速记、立刻执行）。
agent 运行放在后台线程队列里，同一时间只跑一个。"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import queue
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import TEMPLATE_ROOT, config, cores, fm
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
        (d / "meta.json").write_text(json.dumps({"id": run_id, "kind": kind, "label": label, "status": "queued", "model": model, "prompt": prompt,
                                                 "host": config.hostname(), "runner_pid": os.getpid()}, ensure_ascii=False), encoding="utf-8")
        with self._lock:
            self.pending.append(item)
        self.q.put(item)
        return run_id

    def submit_tick(self) -> str | None:
        with self._lock:
            if any(p["kind"] == "tick" for p in self.pending) or (self.current and self.current["kind"] == "tick"):
                return None
        return self.submit("", kind="tick", label="tick")

    def submit_digest(self) -> str | None:
        with self._lock:
            if any(p["kind"] == "digest" for p in self.pending) or (self.current and self.current["kind"] == "digest"):
                return None
        return self.submit("", kind="digest", label="digest")

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
                elif item["kind"] == "digest":
                    from .tick import run_digest
                    meta = run_digest(self.project)
                    d = self.project.dash / "runs" / item["id"]
                    (d / "meta.json").write_text(json.dumps({"id": item["id"], "kind": "digest", "label": "digest", "status": "done",
                                                             "result": "没有待消化的回答" if meta is None else f"→ {meta['id']}"}, ensure_ascii=False), encoding="utf-8")
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

    def idle(self) -> bool:
        with self._lock:
            return self.current is None and not self.pending

    def snapshot(self) -> dict:
        with self._lock:
            return {"current": self.current and {k: self.current[k] for k in ("id", "kind", "label")},
                    "pending": [{k: p[k] for k in ("id", "kind", "label")} for p in self.pending]}


def start_watcher(project: Project, rq: RunQueue) -> None:
    """文件监视：用户不经网页、直接在编辑器里写了 ideas/inbox 或改了状态，也在 watch_seconds 内开始处理。"""
    from .tick import actionable

    def loop():
        while True:
            try:
                interval = int(config.load(project.root)["schedule"].get("watch_seconds", 15))
            except Exception:  # noqa: BLE001
                interval = 15
            time.sleep(max(5, interval))
            try:
                if rq.idle() and actionable(project)[0]:
                    rq.submit_tick()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=loop, daemon=True).start()


def digest_status(project: Project) -> dict:
    from .tick import answered_threads
    s = project.state()
    nxt = s.get("next_digest") or 0
    cfg = config.load(project.root)
    return {
        "answered": [{"id": w["id"], "title": w["title"]} for w in answered_threads(project)],
        "next_digest": nxt, "next_digest_str": time.strftime("%H:%M", time.localtime(nxt)) if nxt else "",
        "digest_minutes": int(cfg["schedule"].get("digest_minutes", 300)),
    }


def schedule_next_digest(project: Project, minutes: int) -> float:
    s = project.state()
    s["next_digest"] = time.time() + minutes * 60
    project._save_state(s)
    return s["next_digest"]


def start_digest_timer(project: Project, rq: RunQueue) -> None:
    """回答的统一消化：每 digest_minutes 看一次，有已回答的讨论就把它们放进一次运行。"""
    from .tick import answered_threads

    def loop():
        cfg = config.load(project.root)
        minutes = int(cfg["schedule"].get("digest_minutes", 300))
        if not project.state().get("next_digest"):
            schedule_next_digest(project, minutes)
        while True:
            time.sleep(30)
            try:
                minutes = int(config.load(project.root)["schedule"].get("digest_minutes", 300))
                if time.time() >= project.state().get("next_digest", 0):
                    if answered_threads(project):
                        rq.submit_digest()
                    schedule_next_digest(project, minutes)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=loop, daemon=True).start()


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


class GuestQuestionIn(BaseModel):
    name: str
    title: str
    text: str


class GuestIdeaIn(BaseModel):
    name: str
    text: str
    title: str | None = None


class SeenIn(BaseModel):
    kind: str
    id: str


# 不跑 JavaScript 的来访者：AI 抓取器（ChatGPT-User、ClaudeBot、PerplexityBot…）、通用爬虫、命令行工具。
# 浏览器的 Accept 里一定有 text/html 且 UA 不在这个表里；其余都当成要 markdown 的
AI_UA_RE = re.compile(
    r"gptbot|chatgpt|openai|claude|anthropic|perplexity|cohere|mistral|google-extended|googlebot|bingbot|duckassist|youbot|applebot"
    r"|ccbot|bytespider|diffbot|amazonbot|meta-external|facebookexternalhit|crawler|spider|\bbot\b|python-requests|python-urllib|httpx|aiohttp"
    r"|curl|wget|go-http-client|node-fetch|undici|axios|libwww|okhttp",
    re.I,
)


def _wants_markdown(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    ua = request.headers.get("user-agent", "")
    if AI_UA_RE.search(ua):
        return True
    return "text/html" not in accept


def _can_write(request: Request, project: Project) -> bool:
    """只有 config.toml server.write_from 里的网段（默认本机 + Tailscale）能写；其他来源（校园网、公网）只读。
    拿不到合法 IP（测试客户端、unix socket）按本机处理。"""
    # 经 Tailscale Funnel 从公网进来的请求带这个头（tailscaled 会覆盖客户端伪造的 X-Forwarded-For，但再加一道硬规则）：一律只读
    if request.headers.get("tailscale-funnel-request"):
        return False
    host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    # 经本机反向代理进来的（Tailscale Funnel/Serve、cloudflared）：直连方是 127.0.0.1，真实来源在 X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for", "")
    if ip.is_loopback and fwd:
        try:
            ip = ipaddress.ip_address(fwd.split(",")[0].strip())
        except ValueError:
            return False
    nets = config.load(project.root)["server"].get("write_from") or []
    for n in nets:
        try:
            if ip in ipaddress.ip_network(n, strict=False):
                return True
        except ValueError:
            continue
    return False


def create_app(project: Project) -> FastAPI:
    app = FastAPI(title="research-dashboard")
    reaped = project.reap_stale_runs()  # 上次服务留下的排队/运行记录：进程不在了就标掉，免得挡住派发
    if reaped:
        project.append_log("程序", f"服务启动：清理了 {len(reaped)} 条陈旧运行记录（{', '.join(reaped[:5])}）")
    rq = RunQueue(project)
    start_watcher(project, rq)
    start_digest_timer(project, rq)

    @app.middleware("http")
    async def readonly_guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and not _can_write(request, project):
            # 访客投稿层：config.toml server.guest_submissions = true 时，任何人都能留名字投想法、向 agent 提问
            if request.url.path.startswith("/api/guest/") and config.load(project.root)["server"].get("guest_submissions"):
                return await call_next(request)
            return JSONResponse({"detail": "只读访问：这个地址只能看，不能操作"}, status_code=403)
        return await call_next(request)

    def _base(request: Request) -> str:
        """对外可用的绝对地址前缀：经反向代理（Tailscale Funnel）时用 X-Forwarded-Proto/Host。"""
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        return f"{proto}://{host}"

    def _client_ip(request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")

    def _llms_text(request: Request) -> str:
        base = _base(request)
        name = config.load(project.root)["project"]["name"]
        pm = project.root / "PROJECT.md"
        intro = ""
        if pm.exists():
            _, pb = fm.read(pm)
            # 第一段正文：跳过标题和引用块里的说明（"> 由 agent 整理于…"之类）
            paras = [x.strip() for x in pb.split("\n\n") if x.strip() and not x.strip().startswith(("#", ">", "<!--"))]
            intro = " ".join(paras[0].split())[:300] if paras else ""
        lines = [f"# {name}", ""]
        if intro:
            lines += [f"> {intro}", ""]
        lines += [
            f"这是课题「{name}」的机器可读入口，所有页面都是 markdown 原文（UTF-8）。",
            "读法：先读「课题状态」（研究问题、当前回答、正在做什么），再按需读 Wiki（我们对各概念的当前理解）、Lab（任务书、摘要、推导）、文献卡片、讨论（需要裁决的问题与回答）、问题树。",
            f"全部内容合并成一个文件：{base}/llms-full.txt",
            "",
        ]
        for sec, items in project.ai_pages():
            if not items:
                continue
            lines.append(f"## {sec}")
            lines += [f"- [{t['title']}]({base}/md/{quote(t['path'])})" for t in items]
            lines.append("")
        return "\n".join(lines)

    @app.get("/")
    def index(request: Request):
        # 根地址按来访者分流：浏览器给网页壳（JS 应用）；AI 抓取器、curl 之类不跑 JS 的客户端直接给 llms.txt 的目录，
        # 这样合作者把根地址丢给 AI 就能读，不必知道 /llms.txt
        if _wants_markdown(request):
            return PlainTextResponse(_llms_text(request), media_type="text/markdown; charset=utf-8")
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    # ---------- 总览 ----------
    @app.get("/api/overview")
    def overview(request: Request):
        cfg = config.load(project.root)
        pm = project.root / "PROJECT.md"
        return {
            "readonly": not _can_write(request, project),
            "readonly_show_controls": bool(cfg["server"].get("readonly_show_controls", True)),
            "guest_submissions": bool(cfg["server"].get("guest_submissions", False)),
            "ai_entry": f"{_base(request)}/llms.txt",
            "project": cfg["project"], "models": cfg["models"], "attention": project.attention(), "log": project.log_entries(20),
            "queue": rq.snapshot(), "runs": project.runs(8), "host": config.hostname(), "digest": digest_status(project),
            "project_md": pm.read_text(encoding="utf-8") if pm.exists() else "",
            "status": project.status_doc(),
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

    @app.post("/api/labs/{lab_id}/comment")
    def lab_comment(lab_id: str, body: AnswerIn):
        """用户对任务书的意见：追加到 brief.md，然后立刻派 agent 按意见修改任务书。"""
        try:
            meta = project.comment_lab(lab_id, body.text)
        except FileNotFoundError:
            raise HTTPException(404)
        rq.submit_tick()
        return meta

    @app.post("/api/labs/{lab_id}/audit/{kind}")
    def lab_audit(lab_id: str, kind: str):
        from .tick import AUDIT_PROMPTS
        key = f"audit_{kind}"
        if key not in AUDIT_PROMPTS:
            raise HTTPException(400, "kind 只能是 derivation 或 code")
        try:
            project.lab(lab_id)
        except FileNotFoundError:
            raise HTTPException(404)
        rid = rq.submit(AUDIT_PROMPTS[key].format(id=lab_id), kind=key, label=f"{key}:{lab_id}")
        project.append_log("用户", f"要求对 {lab_id} 做{'推导' if kind == 'derivation' else '代码'}审计", f".dashboard/runs/{rid}/log.txt")
        return {"id": rid}

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
        # 回答不当场消化：等 digest 定时统一处理，互相关联的回答一起看
        return meta

    @app.get("/api/digest")
    def digest_get():
        return digest_status(project)

    @app.post("/api/digest")
    def digest_now():
        rid = rq.submit_digest()
        cfg = config.load(project.root)
        schedule_next_digest(project, int(cfg["schedule"].get("digest_minutes", 300)))
        project.append_log("用户", "要求现在就统一消化已回答的讨论")
        return {"id": rid, **digest_status(project)}

    @app.post("/api/discussion/{did}/resolve")
    def resolve(did: str):
        from . import fm
        return fm.update(project.safe_path(f"discussion/{did}.md"), status="resolved")

    @app.post("/api/discussion")
    def ask(body: QuestionIn):
        did = project.new_discussion(body.title, body.text, asked_by="user")
        rq.submit_tick()
        return {"id": did}

    # ---------- 访客投稿层（server.guest_submissions = true 时对所有人开放；负责人放行后 agent 才处理） ----------
    @app.post("/api/guest/discussion")
    def guest_ask(body: GuestQuestionIn, request: Request):
        if not config.load(project.root)["server"].get("guest_submissions"):
            raise HTTPException(403, "这个课题没有开放访客投稿")
        name, title, text = body.name.strip(), body.title.strip(), body.text.strip()
        if not name or not title or not text:
            raise HTTPException(400, "名字、标题、内容都要填")
        did = project.new_discussion(title, text, asked_by="guest", author=name, from_ip=_client_ip(request))
        return {"id": did}

    @app.post("/api/guest/ideas")
    def guest_capture(body: GuestIdeaIn, request: Request):
        if not config.load(project.root)["server"].get("guest_submissions"):
            raise HTTPException(403, "这个课题没有开放访客投稿")
        name, text = body.name.strip(), body.text.strip()
        if not name or not text:
            raise HTTPException(400, "名字和内容都要填")
        slug = project.capture_idea(text, body.title, author=name, source="guest", from_ip=_client_ip(request))
        return {"id": slug}

    @app.post("/api/discussion/{did}/approve")
    def approve_question(did: str):
        """负责人放行访客的提问：下次 tick 让 agent 回答。"""
        try:
            meta = project.approve_guest_discussion(did)
        except FileNotFoundError:
            raise HTTPException(404)
        project.append_log("用户", f"放行了访客 {meta.get('author', '')} 的提问「{meta.get('title', did)}」", f"discussion/{did}.md")
        rq.submit_tick()
        return meta

    @app.post("/api/ideas/{slug:path}/triage")
    def approve_idea(slug: str):
        """负责人放行访客投的想法：下次 tick 让 agent 整理进问题树。"""
        try:
            meta = project.approve_guest_idea(slug)
        except FileNotFoundError:
            raise HTTPException(404)
        project.append_log("用户", f"放行了访客 {meta.get('author', '')} 的想法「{meta.get('title', slug)}」", f"ideas/{slug}.md")
        rq.submit_tick()
        return meta

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
        from .tick import actionable
        ready, deferred = actionable(project)
        return {"id": rq.submit_tick(), "pending": ready, "deferred": deferred}

    @app.get("/api/pending")
    def pending():
        from .tick import actionable
        ready, deferred = actionable(project)
        return {"ready": ready, "deferred": deferred}

    @app.get("/api/cores")
    def cores_status():
        return cores.status(project.root)

    @app.get("/api/projects")
    def projects_list():
        from . import registry
        return registry.list_projects()

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

    # ---------- 给 AI 读的入口：把网址丢给任何 AI，它顺着 llms.txt 的链接就能读完全部内容 ----------
    @app.get("/llms.txt")
    def llms(request: Request):
        return PlainTextResponse(_llms_text(request), media_type="text/markdown; charset=utf-8")

    @app.get("/llms-full.txt")
    def llms_full(request: Request):
        base = _base(request)
        table = project.link_table()
        name = config.load(project.root)["project"]["name"]
        out = [f"# {name}（全部内容）", "", f"目录见 {base}/llms.txt。每一页以 `<!-- 路径 -->` 开头。", ""]
        for sec, items in project.ai_pages():
            if not items:
                continue
            out += [f"\n\n# ═══ {sec} ═══\n"]
            for t in items:
                try:
                    out += ["\n\n---\n", project.ai_markdown(t["path"], base, table)]
                except (OSError, PermissionError):
                    continue
        return PlainTextResponse("\n".join(out), media_type="text/markdown; charset=utf-8")

    @app.get("/md/{path:path}")
    def md_page(path: str, request: Request):
        if not project.ai_allowed(path):
            raise HTTPException(404)
        try:
            p = project.safe_path(path)
        except PermissionError:
            raise HTTPException(403)
        if not p.is_file():
            raise HTTPException(404)
        return PlainTextResponse(project.ai_markdown(path, _base(request)), media_type="text/markdown; charset=utf-8")

    @app.get("/api/raw")
    def raw(path: str):
        """项目内任意 markdown（notes.md、handoff.md、STATUS.md …）的 frontmatter 与正文，给前端的通用文档页用。"""
        try:
            p = project.safe_path(path)
        except PermissionError:
            raise HTTPException(403)
        if not p.is_file() or p.suffix.lower() not in (".md", ".txt", ".csv"):
            raise HTTPException(404)
        from . import fm
        meta, body = fm.read(p)
        # 同目录下的其他 md，给文档页做"同一文件夹"导航
        siblings = sorted(x.name for x in p.parent.glob("*.md") if x.name != p.name and not x.name.startswith("."))
        return {"path": path, "meta": meta, "body": body, "siblings": siblings[:50],
                "updated": __import__("datetime").datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}

    return app
