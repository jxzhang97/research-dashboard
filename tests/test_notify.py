from pathlib import Path

from rd_core import cli, fm, notify
from rd_core.project import Project


def finish(project_dir: Path, lab: str = "01-first-task", answer: str = "会。因为度规给出下界；其余细节见 notes。") -> None:
    d = project_dir / "labs" / lab
    fm.update(d / "brief.md", status="done")
    (d / "report.md").write_text(f"---\ntitle: 第一个任务\n---\n# 第一个任务\n\n## 问题\n\n度规有界吗？\n\n## 当前回答\n\n{answer}\n", encoding="utf-8")


def test_first_run_only_records(project_dir: Path, no_real_ticktick):
    pr = Project(project_dir)
    assert notify.check(pr) == []  # 示例课题里本来就有一份待过目的任务书和一个提问：不补发
    assert notify._load(pr)["labs"] == {"01-first-task": "awaiting_review"}
    assert notify.check(pr) == []


def test_lab_done_and_question(project_dir: Path):
    pr = Project(project_dir)
    notify.check(pr)
    finish(project_dir)
    (project_dir / "discussion" / "2026-11-16-new.md").write_text("---\ntitle: 取哪个规范\nstatus: open\nasked_by: agent\n---\n# 取哪个规范\n", encoding="utf-8")
    events = notify.check(pr)
    assert [(e["kind"], e["id"]) for e in events] == [("lab_done", "01-first-task"), ("agent_question", "2026-11-16-new")]
    assert events[0]["line"] == "lab 01 完成：第一个任务 —— 会。" and events[0]["url"].endswith("/#/labs/01-first-task")
    title, body = notify.message(pr, events)
    assert title == "(Dashboard) demo：2 件事等你"
    assert "· agent 向你提问：取哪个规范\n  " in body and "/#/discussion/2026-11-16-new" in body
    assert notify.message(pr, events[:1])[0] == "(Dashboard) demo：lab 01 完成：第一个任务 —— 会。"
    assert notify.check(pr) == events  # 还没发出去：留在待发里
    assert notify.run_once(pr)["sent"] == 2 and notify.check(pr) == []  # 发出去以后同一件事不再提醒


def test_already_seen_or_filtered_events_are_skipped(project_dir: Path):
    pr = Project(project_dir)
    notify.check(pr)
    finish(project_dir)
    pr.mark_seen("lab", "01-first-task")
    assert notify.check(pr) == []  # 网页上已经看过
    with (project_dir / "config.toml").open("a", encoding="utf-8") as f:
        f.write('\n[notify]\nevents = ["lab_done"]\n')
    lab = project_dir / "labs" / "02-second"
    lab.mkdir()
    (lab / "brief.md").write_text("---\ntitle: 第二个\nstatus: awaiting_review\n---\n# 第二个\n", encoding="utf-8")
    assert notify.check(pr) == []  # 这个课题只要「lab 完成」


def test_failed_send_is_retried_and_stale_items_dropped(project_dir: Path, monkeypatch, no_real_ticktick):
    pr = Project(project_dir)
    notify.check(pr)
    finish(project_dir)
    monkeypatch.setattr(notify, "send", lambda *a: (False, "Couldn't find shortcut"))
    r = notify.run_once(pr)
    assert r["sent"] == 0 and "find shortcut" in r["error"]
    assert notify._load(pr)["pending"] == [{"kind": "lab_done", "id": "01-first-task"}]
    monkeypatch.setattr(notify, "send", lambda pr_, t, b: (no_real_ticktick.append((t, b)) or (True, "")))
    assert notify.run_once(pr)["sent"] == 1 and no_real_ticktick[-1][0].startswith("(Dashboard) demo：lab 01 完成")
    assert notify._load(pr)["pending"] == [] and notify.run_once(pr) == {"sent": 0}
    # 待发里的事已经不成立（任务书被批准了）就不再发
    lab = project_dir / "labs" / "03-third"
    lab.mkdir()
    (lab / "brief.md").write_text("---\ntitle: 第三个\nstatus: awaiting_review\n---\n# 第三个\n", encoding="utf-8")
    monkeypatch.setattr(notify, "send", lambda *a: (False, "x"))
    notify.run_once(pr)
    fm.update(lab / "brief.md", status="approved")
    assert notify.check(pr) == []


def test_cli(project_dir: Path, capsys, no_real_ticktick):
    cli.main(["notify", str(project_dir), "--dry-run"])
    assert "还没开始记录" in capsys.readouterr().out
    cli.main(["notify", str(project_dir)])
    finish(project_dir)
    cli.main(["notify", str(project_dir), "--dry-run"])
    assert "(Dashboard) demo：lab 01 完成" in capsys.readouterr().out and not no_real_ticktick
    try:
        cli.main(["notify", str(project_dir), "--test"])
    except SystemExit as e:
        assert e.code == 0
    assert no_real_ticktick[-1][0] == "(Dashboard) demo：测试提醒，看到这条说明通了"


def test_codex_sender_reads_task_id(project_dir: Path, monkeypatch):
    import subprocess
    from rd_core import codex
    pr = Project(project_dir)
    seen = {}
    monkeypatch.setattr(codex, "find_codex", lambda: (Path("/bin/echo"), ""))

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text(seen.get("reply", "建好了。\nTASK_ID: 6a1b2c3d4e5f60718293a4b5"), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    ok, out = notify._send_codex(pr, notify._cfg(pr), "(Dashboard) demo：lab 01 完成", "· lab 01 完成\n  http://x/#/labs/01")
    assert ok and out == "6a1b2c3d4e5f60718293a4b5"
    cmd = seen["cmd"]
    assert cmd[cmd.index("-m") + 1] == "gpt-6.2-sol" and 'model_reasoning_effort="high"' in cmd and cmd[cmd.index("-s") + 1] == "read-only"
    assert "「research」清单" in cmd[-1] and "(Dashboard) demo：lab 01 完成" in cmd[-1] and "http://x/#/labs/01" in cmd[-1]
    seen["reply"] = "FAILED: 找不到 research 清单"
    ok, out = notify._send_codex(pr, notify._cfg(pr), "t", "b")
    assert not ok and "找不到 research 清单" in out
