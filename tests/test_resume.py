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
    assert model_for(cfg, "run_lab") == ("claude-fable-5-2", "xhigh")
    assert model_for(cfg, "promote_idea") == ("claude-fable-5-2", "xhigh")
    # 任务书 frontmatter 优先于种类默认
    _lab(project_dir, "approved")
    fm.update(project_dir / "labs" / "01-first-task" / "brief.md", model="claude-opus-5-5", effort="max")
    res = run_pending(pr, dry_run=True)
    assert res[0]["kind"] == "run_lab" and res[0]["model"] == "claude-opus-5-5" and res[0]["effort"] == "max"
    # 课题 config 可以覆盖种类默认（模板里已有 [models.kinds]，改那一行）
    text = (project_dir / "config.toml").read_text(encoding="utf-8")
    assert 'arxiv_reason = { model = "claude-opus-5-5", effort = "xhigh" }' in text
    (project_dir / "config.toml").write_text(text.replace('arxiv_reason = { model = "claude-opus-5-5", effort = "xhigh" }',
                                                          'arxiv_reason = { model = "claude-fable-5-2", effort = "high" }'), encoding="utf-8")
    cfg = config.load(project_dir)
    assert model_for(cfg, "arxiv_reason") == ("claude-fable-5-2", "high")
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


def test_non_lab_items_are_deduped_too(project_dir: Path):
    """想法整理、升级、建卡、回答用户提问：已有排队/运行中的同名记录就不再列为待办。"""
    pr = Project(project_dir)
    (project_dir / "ideas" / "inbox").mkdir(exist_ok=True)
    (project_dir / "ideas" / "inbox" / "2026-10-08-x.md").write_text("---\ntitle: x\n---\n# x\n\n原话\n", encoding="utf-8")
    fm.update(project_dir / "ideas" / "root-idea.md", promote_requested="2026-10-08 10:00")
    kinds = sorted(w["kind"] for w in pr.pending_work())
    assert kinds == ["promote_idea", "triage_idea"]
    now = datetime.now()
    _run(project_dir, _stamp(now) + "-triage", "triage_idea:inbox/2026-10-08-x", "running", now)
    _run(project_dir, _stamp(now) + "-promote", "promote_idea:root-idea", "queued")
    assert pr.pending_work() == []


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


def test_resume_waits_for_registered_numerics(project_dir: Path):
    """等数值的 lab：登记的作业还活着就不派续跑；有一个结束就立刻派并说明；没登记作业的按 resume_minutes 节奏。"""
    import os
    import subprocess

    from rd_core import config, cores
    from rd_core.tick import PROMPTS, actionable, run_pending

    pr = Project(project_dir)
    lab = "01-first-task"
    _lab(project_dir, "running")
    cfg = config.load(project_dir)
    # 没登记作业、上次续跑刚正常结束 → 按 resume_minutes 等，不再 15 秒一派；resume_minutes=0 则立刻可派
    pr.record_attempt("resume_lab", lab, "done")
    ready, deferred = actionable(pr, cfg)
    assert ready == [] and deferred[0]["last_status"] == "waiting" and deferred[0]["retry_in_s"] > 0
    cfg["schedule"]["resume_minutes"] = 0
    assert actionable(pr, cfg)[0][0]["kind"] == "resume_lab"
    # 登记两个活作业（标签以 lab id 开头）→ 等数值；别的课题、别的 lab（同前缀）的作业不算
    a = cores.claim(project_dir, 1, f"{lab} phase1", pid=os.getpid())
    sleeper = subprocess.Popen(["sleep", "300"])
    try:
        b = cores.claim(project_dir, 1, f"{lab} phase2", pid=sleeper.pid)
        cores.claim(None, 1, f"{lab} elsewhere", pid=os.getpid())
        cores.claim(project_dir, 1, f"{lab}-b other lab", pid=os.getpid())
        assert {j["id"] for j in cores.lab_jobs(project_dir, lab)} == {a, b}
        ready, deferred = actionable(pr, cfg)
        assert ready == [] and deferred[0]["last_status"] == "numerics" and "phase1" in deferred[0]["reason"]
        assert set(pr.lab_jobs_snapshot(lab)) == {a, b}  # 没有基线时以现在活着的为基线
        # 其中一个跑完 → 立刻叫醒（哪怕另一个还活着），提示里说明是哪一个
        sleeper.kill()
        sleeper.wait()
        ready, _ = actionable(pr, cfg)
        assert ready and ready[0]["kind"] == "resume_lab" and "phase2" in ready[0]["wake_note"]
        assert "phase2" in PROMPTS["resume_lab"].format(**ready[0])
        # 派一次（conftest 的假 claude）→ 基线更新为现在活着的 → 又回到等数值
        res = run_pending(pr)
        assert any(r.get("kind") == "resume_lab" and r.get("status") == "done" for r in res)
        assert set(pr.lab_jobs_snapshot(lab)) == {a}
        ready, deferred = actionable(pr, cfg)
        assert ready == [] and deferred[0]["last_status"] == "numerics"
        # 全部结束 → 立刻可派
        cores.release(a)
        assert actionable(pr, cfg)[0][0]["kind"] == "resume_lab"
    finally:
        if sleeper.poll() is None:
            sleeper.kill()
            sleeper.wait()


def test_comments_on_results_are_dispatched(project_dir: Path):
    """任务进行中或已完成后用户在任务页写的意见：派 address_comments，不等续跑；待过目的仍是 revise_brief；批准的走 run_lab。"""
    import os

    from rd_core import config, cores
    from rd_core.tick import PROMPTS, actionable

    pr = Project(project_dir)
    lab = "01-first-task"
    _lab(project_dir, "done")
    pr.comment_lab(lab, "图 2 的误差棒怎么来的？")
    w = pr.pending_work()
    item = next(x for x in w if x["kind"] == "address_comments")
    assert item["status"] == "done" and "用户意见" in PROMPTS["address_comments"].format(**item)
    # running 且登记的数值还活着：续跑会被挡，意见不被挡
    _lab(project_dir, "running")
    cores.claim(project_dir, 1, f"{lab} phase1", pid=os.getpid())
    ready, deferred = actionable(pr, config.load(project_dir))
    assert "address_comments" in [x["kind"] for x in ready]
    assert "resume_lab" not in [x["kind"] for x in ready + deferred]
    # 待过目的任务书：仍是 revise_brief
    _lab(project_dir, "awaiting_review")
    kinds = [x["kind"] for x in pr.pending_work()]
    assert "revise_brief" in kinds and "address_comments" not in kinds
    # 批准了：直接执行，run_lab 的提示里要求先处理未回复的意见
    _lab(project_dir, "approved")
    w = pr.pending_work()
    kinds = [x["kind"] for x in w]
    assert "run_lab" in kinds and "address_comments" not in kinds and "revise_brief" not in kinds
    assert "用户意见" in PROMPTS["run_lab"].format(**next(x for x in w if x["kind"] == "run_lab"))


# ---------- 2026-11-12：额度用尽没被认出来、三次空派后 lab 被标成 blocked 且放不开 ----------
LIMIT_TEXT = "You've hit your 5-hour limit · resets 3am (America/Los_Angeles)"


def _limit_events(resets_at: float) -> list[dict]:
    """Claude Code 2.1.x 撞额度时依次吐出的三条事件（字段照抄真实记录，只留用得到的）。"""
    info = {"status": "rejected", "resetsAt": resets_at, "rateLimitType": "five_hour"}
    return [
        {"type": "rate_limit_event", "rate_limit_info": info},
        {"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": LIMIT_TEXT}]},
         "error": "rate_limit", "is_api_error_message": True, "api_error": "usage_limit_reached", "api_error_params": {"rate_limit_info": info}},
        {"type": "result", "subtype": "success", "is_error": True, "api_error": "usage_limit_reached", "result": LIMIT_TEXT, "total_cost_usd": 0},
    ]


def test_limit_is_recognised_from_structured_events():
    from rd_core.runner import LIMIT_RE, limit_from_event
    assert LIMIT_RE.search(LIMIT_TEXT) and LIMIT_RE.search("You've hit your session limit · resets 5:50am (America/Los_Angeles)")
    assert LIMIT_RE.search("You've reached your Fable limit.")
    ev = _limit_events(1794481200)
    assert limit_from_event(ev[0]) == ("Claude 额度用尽（five_hour）", 1794481200.0)
    assert limit_from_event(ev[1]) == (LIMIT_TEXT, 1794481200.0)
    assert limit_from_event(ev[2])[0] == LIMIT_TEXT
    # 旧版本没有结构化字段：合成的错误消息、出错的 result 里的提示语也认
    assert limit_from_event({"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": LIMIT_TEXT}]}}) == (LIMIT_TEXT, None)
    assert limit_from_event({"type": "result", "is_error": True, "result": LIMIT_TEXT}) == (LIMIT_TEXT, None)
    # 不是额度用尽的：额度还够的 rate_limit_event；agent 自己复述上次的提示（续跑时常见）；正常结束的总结里提到它
    assert limit_from_event({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1}}) is None
    assert limit_from_event({"type": "assistant", "message": {"model": "claude-fable-5-2", "content": [{"type": "text", "text": "上次运行：" + LIMIT_TEXT}]}}) is None
    assert limit_from_event({"type": "result", "is_error": False, "result": "上次运行：" + LIMIT_TEXT}) is None


def test_agent_env_defaults_to_single_thread():
    from rd_core.runner import THREAD_ENV, agent_env
    env = agent_env(Path("/tmp/x"), "run-1", base={"PATH": "/opt/anaconda3/bin:/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "4"})
    assert all(env[v] == "1" for v in THREAD_ENV if v != "OPENBLAS_NUM_THREADS")
    assert env["OPENBLAS_NUM_THREADS"] == "4"  # 显式给的值优先
    assert env["PATH"].split(":")[-2:] == ["/usr/sbin", "/sbin"] and env["RD_RUN_ID"] == "run-1" and env["RD_PROJECT"] == "/tmp/x"
    assert agent_env(Path("/tmp/x"), "r", base={"PATH": "/usr/sbin:/bin"})["PATH"] == "/usr/sbin:/bin:/sbin"


def test_runner_pauses_until_reset_and_exports_thread_env(project_dir: Path, tmp_path: Path, monkeypatch):
    from rd_core import runner
    resets = time.time() + 3 * 3600
    events = tmp_path / "events.jsonl"
    events.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in _limit_events(resets)) + "\n", encoding="utf-8")
    seen = tmp_path / "env.txt"
    for v in runner.THREAD_ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(runner, "build_command", lambda *a, **k: ["/bin/sh", "-c", f'echo "$OMP_NUM_THREADS/$OPENBLAS_NUM_THREADS/$VECLIB_MAXIMUM_THREADS" > "{seen}"; cat "{events}"; exit 1'])
    pr = Project(project_dir)
    meta = runner.Runner(pr).run("x", kind="resume_lab", label="resume_lab:01-first-task")
    assert meta["status"] == "failed" and meta["limit"] == LIMIT_TEXT
    assert seen.read_text().strip() == "1/1/1"
    assert abs(pr.pause_info()["until"] - (resets + 120)) < 1 and pr.pause_info()["reason"] == LIMIT_TEXT


def test_limit_is_not_a_failure_and_unblocking_resets_the_count(project_dir: Path, monkeypatch):
    from rd_core import tick
    pr = Project(project_dir)
    _lab(project_dir, "running")
    outcome = {"status": "failed", "limit": LIMIT_TEXT}
    calls = []
    monkeypatch.setattr(tick.Runner, "run", lambda self, *a, **k: calls.append(k) or dict(outcome))
    # 撞额度三次：不计失败，不进退避（何时再试由额度暂停决定），lab 仍是 running
    for _ in range(3):
        assert tick.actionable(pr)[0][0]["kind"] == "resume_lab"
        tick.run_pending(pr)
    info = pr.attempt_info("resume_lab", "01-first-task")
    assert info["status"] == "limit" and info["fails"] == 0 and len(calls) == 3
    assert fm.read(project_dir / "labs" / "01-first-task" / "brief.md")[0]["status"] == "running"
    # 真失败三次 → blocked；改 blocked 这一步自己不再把计数加一
    outcome.pop("limit")
    for _ in range(3):
        tick.run_pending(pr, force=True)
    assert pr.attempt_info("resume_lab", "01-first-task")["fails"] == 3 and len(calls) == 6
    assert tick.run_pending(pr, force=True)[0]["status"] == "blocked" and len(calls) == 6
    assert pr.attempt_info("resume_lab", "01-first-task") == {**pr.attempt_info("resume_lab", "01-first-task"), "status": "blocked", "fails": 3}
    assert pr.pending_work() == []
    # 有人把它放开（状态改回 running）：立刻可派，不再被原地改回 blocked，次数重新给满
    _lab(project_dir, "running")
    outcome["status"] = "done"
    assert tick.actionable(pr)[0][0]["kind"] == "resume_lab"
    assert tick.run_pending(pr)[0]["status"] == "done" and len(calls) == 7
    assert pr.attempt_info("resume_lab", "01-first-task")["fails"] == 0
    assert fm.read(project_dir / "labs" / "01-first-task" / "brief.md")[0]["status"] == "running"


def test_manual_run_is_labelled_with_the_lab_it_names():
    from rd_core.tick import lab_label
    labs = ["01-first-task", "18-smg-su2-parton-bond", "18-smg"]
    assert lab_label("manual", "resume_lab:18-smg-su2-parton-bond继续", labs) == "manual:18-smg-su2-parton-bond"
    assert lab_label("", "把 labs/01-first-task 的图重画", labs) == "manual:01-first-task"
    assert lab_label("manual", "对比 01-first-task 和 18-smg-su2-parton-bond", labs) == "manual"   # 点了两个：不猜
    assert lab_label("manual", "整理一下 wiki", labs) == "manual"
    assert lab_label("我的标签", "resume_lab:01-first-task", labs) == "我的标签"                 # 用户填了就不动


def test_core_alert_shows_in_attention(project_dir: Path):
    pr = Project(project_dir)
    n = pr.attention()["total"]
    pr.set_core_alert({"text": "核在打架：1 个数值进程共 14 个线程在跑，超过 10 个性能核。", "procs": "pid 66196（14 线程，python3 scripts/su2mf.py）", "mine": True})
    first = pr.core_alert()["t"]
    it = next(i for i in pr.attention()["items"] if i["kind"] == "cores")
    assert pr.attention()["total"] == n + 1 and "本课题" in it["title"] and "pid 66196" in it["why"] and not it.get("soft")
    pr.set_core_alert({"text": "CPU 的 system 占比 71%", "procs": "", "mine": False})
    assert pr.core_alert()["t"] == first  # 同一次打架：起始时刻不变
    pr.set_core_alert(None)
    assert pr.core_alert() is None and pr.attention()["total"] == n


def test_core_watchdog_alerts_after_two_samples_and_clears(project_dir: Path, monkeypatch):
    from rd_core import cores
    from rd_core.server import core_watch_step
    pr = Project(project_dir)
    fighting = {"fight": ["核在打架：1 个数值进程共 14 个线程在跑，超过 10 个性能核。"],
                "procs": [{"pid": 66196, "cpu": 1104.2, "running_threads": 14, "cmd": "python3 scripts/su2mf.py"},
                          {"pid": 1345, "cpu": 25.3, "running_threads": 1, "cmd": "python -m rd_core.cli serve"}]}
    calm = {"fight": [], "procs": []}
    monkeypatch.setattr(cores, "proc_cwd", lambda pid: str(pr.root / "labs" / "01-first-task") if pid == 66196 else "/somewhere/else")
    log = project_dir / "log.md"
    before = log.read_text(encoding="utf-8").count("在抢核")
    memo: dict = {}
    core_watch_step(pr, fighting, memo)
    assert pr.core_alert() is None                      # 一次采样不报：短暂的峰值不算
    core_watch_step(pr, fighting, memo)
    alert = pr.core_alert()
    assert alert["mine"] and "pid 66196（14 线程" in alert["procs"] and "1345" not in alert["procs"]
    core_watch_step(pr, fighting, memo)
    assert log.read_text(encoding="utf-8").count("在抢核") == before + 1   # 同一次打架只记一行 log
    core_watch_step(pr, calm, memo)
    assert pr.core_alert() is None and memo == {"streak": 0, "logged": False}
    # 别的课题起的进程在打架：首页照样报（是本机的事），但不往本课题的 log 里写
    monkeypatch.setattr(cores, "proc_cwd", lambda pid: "/somewhere/else")
    core_watch_step(pr, fighting, memo); core_watch_step(pr, fighting, memo)
    assert pr.core_alert()["mine"] is False and log.read_text(encoding="utf-8").count("在抢核") == before + 1
