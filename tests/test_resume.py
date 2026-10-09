"""孤儿 running 的 lab 自动续跑、重复派发去重、额度暂停、按种类选模型。"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from rd_core import fm
from rd_core.project import Project


def _lab(project_dir: Path, status: str) -> None:
    fm.update(project_dir / "labs" / "01-first-task" / "brief.md", status=status)


def _run(project_dir: Path, run_id: str, label: str, status: str, started: datetime | None = None, result: str = "") -> None:
    d = project_dir / ".dashboard" / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    meta = {"id": run_id, "kind": label.split(":")[0], "label": label, "status": status, "result": result,
            "started": started.strftime("%Y-%m-%d %H:%M:%S") if started else None}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def _stamp(t: datetime) -> str:
    return t.strftime("%Y%m%d-%H%M%S")


def test_running_without_live_run_becomes_resume(project_dir: Path):
    pr = Project(project_dir)
    _lab(project_dir, "running")
    old = datetime.now() - timedelta(hours=3)
    _run(project_dir, _stamp(old) + "-run_lab-01", "run_lab:01-first-task", "failed", old, "You've hit your session limit · resets 5:50am (America/Los_Angeles)")
    work = pr.pending_work()
    kinds = [w["kind"] for w in work]
    assert "resume_lab" in kinds and "run_lab" not in kinds
    w = next(w for w in work if w["kind"] == "resume_lab")
    assert w["last_run_status"] == "failed" and "session limit" in w["last_run_result"]
    assert pr.labs()[0].extra["stale_run"] is True
    # 续跑提示词能格式化
    from rd_core.tick import PROMPTS
    assert "resume.md" in PROMPTS["resume_lab"].format(**w)


def test_live_run_suppresses_resume_and_duplicate_dispatch(project_dir: Path):
    pr = Project(project_dir)
    now = datetime.now()
    # running + 活着的运行 → 不续跑
    _lab(project_dir, "running")
    _run(project_dir, _stamp(now) + "-run_lab-01", "run_lab:01-first-task", "running", now)
    assert [w["kind"] for w in pr.pending_work()] == []
    assert pr.labs()[0].extra["stale_run"] is False
    # approved + 排队中的运行（网页批准刚入队、tick 几秒后扫描）→ 不再派第二次
    _lab(project_dir, "approved")
    _run(project_dir, _stamp(now) + "-run_lab-01", "run_lab:01-first-task", "queued")
    assert [w["kind"] for w in pr.pending_work()] == []
    # 陈旧的 running 记录（服务器死了留下的）不算活着
    stale = now - timedelta(hours=30)
    _run(project_dir, _stamp(now) + "-run_lab-01", "run_lab:01-first-task", "running", stale)
    assert [w["kind"] for w in pr.pending_work()] == ["run_lab"]


def test_limit_pause_defers_everything(project_dir: Path):
    from rd_core.runner import parse_reset
    from rd_core.tick import actionable
    pr = Project(project_dir)
    _lab(project_dir, "approved")
    assert actionable(pr)[0][0]["kind"] == "run_lab"
    msg = "You've hit your session limit · resets 5:50am (America/Los_Angeles)"
    until = parse_reset(msg, now=time.time())
    assert time.time() < until <= time.time() + 24 * 3600 + 130
    pr.set_pause(until, msg)
    ready, deferred = actionable(pr)
    assert ready == [] and deferred[0]["last_status"] == "limit" and deferred[0]["retry_in_s"] > 0
    assert pr.pause_info()["reason"] == msg
    # 过了重置时刻就恢复
    pr.set_pause(time.time() - 1, msg)
    assert pr.pause_info() is None and actionable(pr)[0][0]["kind"] == "run_lab"
    # 认不出重置时刻 → 一小时后
    assert abs(parse_reset("You've reached your Fable limit.", now=1000.0) - 4600.0) < 1e-6


def test_parse_reset_times():
    from zoneinfo import ZoneInfo
    from rd_core.runner import parse_reset
    tz = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 10, 8, 4, 41, tzinfo=tz).timestamp()
    t = datetime.fromtimestamp(parse_reset("resets 5:50am (America/Los_Angeles)", now), tz)
    assert (t.hour, t.minute, t.day) == (5, 52, 8)
    t = datetime.fromtimestamp(parse_reset("resets 1pm (America/Los_Angeles)", now), tz)
    assert (t.hour, t.minute, t.day) == (13, 2, 8)
    # 已过的时刻 → 明天
    t = datetime.fromtimestamp(parse_reset("resets 12:40am (America/Los_Angeles)", now), tz)
    assert (t.hour, t.minute, t.day) == (0, 42, 9)


def test_resume_failure_cap_blocks_lab(project_dir: Path, monkeypatch):
    from rd_core import tick
    pr = Project(project_dir)
    _lab(project_dir, "running")
    for _ in range(3):
        pr.record_attempt("resume_lab", "01-first-task", "failed")
    assert pr.attempt_info("resume_lab", "01-first-task")["fails"] == 3
    # 退避期内是 deferred；force 之后进入 run_pending 就被改成 blocked，而不是再花一次钱
    calls = []
    monkeypatch.setattr(tick.Runner, "run", lambda self, *a, **k: calls.append(k) or {"status": "done"})
    res = tick.run_pending(pr, force=True)
    assert res[0]["status"] == "blocked" and calls == []
    assert fm.read(project_dir / "labs" / "01-first-task" / "brief.md")[0]["status"] == "blocked"
    assert pr.pending_work() == []
    # done 之后计数清零
    pr.record_attempt("resume_lab", "01-first-task", "done")
    assert pr.attempt_info("resume_lab", "01-first-task")["fails"] == 0


def test_models_per_kind_and_frontmatter_override(project_dir: Path):
    from rd_core import config
    from rd_core.tick import model_for, run_pending
    pr = Project(project_dir)
    cfg = config.load(project_dir)
    assert model_for(cfg, "arxiv_reason") == ("claude-opus-5-5", "xhigh")
    assert model_for(cfg, "triage_idea") == ("claude-opus-5-5", "xhigh")
    assert model_for(cfg, "run_lab") == ("claude-fable-5-1", "xhigh")
    assert model_for(cfg, "promote_idea") == ("claude-fable-5-1", "xhigh")
    # 任务书 frontmatter 优先于种类默认
    _lab(project_dir, "approved")
    fm.update(project_dir / "labs" / "01-first-task" / "brief.md", model="claude-opus-5-5", effort="max")
    res = run_pending(pr, dry_run=True)
    assert res[0]["kind"] == "run_lab" and res[0]["model"] == "claude-opus-5-5" and res[0]["effort"] == "max"
    # 课题 config 可以覆盖种类默认（模板里已有 [models.kinds]，改那一行）
    text = (project_dir / "config.toml").read_text(encoding="utf-8")
    assert 'arxiv_reason = { model = "claude-opus-5-5", effort = "xhigh" }' in text
    (project_dir / "config.toml").write_text(text.replace('arxiv_reason = { model = "claude-opus-5-5", effort = "xhigh" }',
                                                          'arxiv_reason = { model = "claude-fable-5-1", effort = "high" }'), encoding="utf-8")
    cfg = config.load(project_dir)
    assert model_for(cfg, "arxiv_reason") == ("claude-fable-5-1", "high")
    assert model_for(cfg, "triage_idea") == ("claude-opus-5-5", "xhigh")


def test_second_item_is_rechecked_before_dispatch(project_dir: Path, monkeypatch):
    """同一次 tick 里排在后面的项，派之前再查一次：前一项跑的那段时间里别的 tick 可能已经派过它了。"""
    from rd_core import tick
    pr = Project(project_dir)
    _lab(project_dir, "approved")
    (project_dir / "ideas" / "inbox").mkdir(exist_ok=True)
    (project_dir / "ideas" / "inbox" / "2026-10-08-new.md").write_text("---\ntitle: 新想法\n---\n# 新想法\n\n原话\n", encoding="utf-8")
    ready, _ = tick.actionable(pr)
    assert [w["kind"] for w in ready] == ["run_lab", "triage_idea"]
    calls = []

    def fake_run(self, prompt, kind="manual", label="", model=None, effort=None, **_):
        calls.append(kind)
        if kind == "run_lab":
            # 第一项跑的期间，"别的 tick" 已经把 triage 派了出去：留下一条排队记录
            _run(project_dir, _stamp(datetime.now()) + "-triage", "triage_idea:inbox/2026-10-08-new", "queued")
            fm.update(project_dir / "ideas" / "inbox" / "2026-10-08-new.md", triaged=True)
        return {"status": "done"}

    monkeypatch.setattr(tick.Runner, "run", fake_run)
    res = tick.run_pending(pr)
    assert calls == ["run_lab"]
    assert [r["status"] for r in res] == ["done", "skipped"]


def test_reap_stale_runs_on_server_start(project_dir: Path):
    import os
    from rd_core import config
    pr = Project(project_dir)
    now = datetime.now()
    host = config.hostname()
    alive, dead = os.getpid(), 999999
    # 死掉的服务器排的队 → stopped；还活着的进程（launchd tick）排的队 → 不动；别的机器的 → 不动；running 且 agent 进程已不在 → failed
    for rid, label, st, rp, pid, h in [
        ("a", "run_lab:01-first-task", "queued", dead, None, host),
        ("b", "triage_idea:x", "queued", alive, None, host),
        ("c", "run_lab:zz", "queued", dead, None, "studio"),
        ("d", "run_lab:01-first-task", "running", dead, dead, host),
    ]:
        d = project_dir / ".dashboard" / "runs" / (_stamp(now) + "-" + rid)
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": d.name, "kind": label.split(":")[0], "label": label, "status": st, "runner_pid": rp, "pid": pid, "host": h,
                                                 "started": now.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    reaped = pr.reap_stale_runs()
    assert sorted(x[-1] for x in reaped) == ["a", "d"]
    states = {m["id"][-1]: m["status"] for m in pr.runs()}
    assert states["a"] == "stopped" and states["d"] == "failed" and states["b"] == "queued" and states["c"] == "queued"
    # live_runs 也不把死进程的记录当活的
    assert sorted(m["id"][-1] for m in pr.live_runs()) == ["b", "c"]


def test_resume_waits_for_live_codex_job(project_dir: Path, monkeypatch):
    from rd_core import codex, tick
    pr = Project(project_dir)
    _lab(project_dir, "running")
    monkeypatch.setattr(codex, "live_jobs", lambda root: [{"kind": "audit", "name": "x", "lab": "01-first-task", "pid": 1, "state": "running"}])
    ready, deferred = tick.actionable(pr)
    assert ready == [] and deferred[0]["last_status"] == "codex"
    monkeypatch.setattr(codex, "live_jobs", lambda root: [])
    assert tick.actionable(pr)[0][0]["kind"] == "resume_lab"
