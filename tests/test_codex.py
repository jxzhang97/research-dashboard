"""Codex 作业：找可执行文件（优先带 host 的）、脱离父进程启动、结束行、进程消失、fail closed 识别。"""

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

from rd_core import codex


def _fake_codex(d: Path, body: str, with_host: bool = True) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / "codex"
    p.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    if with_host:
        (d / "codex-code-mode-host").write_text("", encoding="utf-8")
    return p


FAKE_OK = r'''
case "$1" in
  login) echo "Logged in using ChatGPT"; exit 0;;
  --version) echo "codex-cli 0.160.0"; exit 0;;
  exec)
    out=""; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { out="$2"; shift; }; shift; done
    sleep ${FAKE_SLEEP:-0}
    echo "OpenAI Codex v0.160.0"; echo "tokens used"; echo "12,345"
    echo "报告已生成" > "$out"; exit 0;;
esac
'''

FAKE_FAIL_CLOSED = r'''
case "$1" in
  login) echo "Logged in using ChatGPT"; exit 0;;
  --version) echo "codex-cli 0.160.0"; exit 0;;
  exec) echo "OpenAI Codex v0.160.0"
        echo "warning: Code Mode is unavailable because failed to spawn code-mode host /x/codex-code-mode-host: host executable was not found. Code mode will fail closed"
        echo "2026-10-08T09:06:23.854005Z ERROR codex_core::tools::router: error=failed to spawn code-mode host /x/codex-code-mode-host: No such file or directory (os error 2)"
        echo "报告未生成"; exit 0;;
esac
'''

# 健康的运行：codex 把提示词和它读到的 skill 文本、log.md 原样回显，里面也有 "fail closed""codex-code-mode-host" 字样，不能算失败
FAKE_ECHOES_WORDS = r'''
case "$1" in
  login) echo "Logged in using ChatGPT"; exit 0;;
  --version) echo "codex-cli 0.160.0"; exit 0;;
  exec)
    out=""; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { out="$2"; shift; }; shift; done
    echo "OpenAI Codex v0.160.0"; echo "user"
    echo "# 等待：退出码 6 Codex 工具执行 fail closed、9 进程消失"
    echo "模板问题：本机 codex 缺同目录的 codex-code-mode-host，Codex 的工具执行 fail closed"
    echo "codex"; echo "读完了，Code Mode is unavailable 这句只是引文"; echo "tokens used"; echo "100"
    echo "报告已生成" > "$out"; exit 0;;
esac
'''


def test_find_prefers_binary_with_host(tmp_path: Path, monkeypatch):
    bare = _fake_codex(tmp_path / "bare", FAKE_OK, with_host=False)
    good = _fake_codex(tmp_path / "good", FAKE_OK, with_host=True)
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setattr(codex, "BUNDLED", tmp_path / "nope" / "codex")
    monkeypatch.setattr(codex, "LEGACY_BUNDLED", tmp_path / "nope2" / "codex")
    monkeypatch.setattr(codex.shutil, "which", lambda _n: str(bare))
    monkeypatch.setattr(Path, "expanduser", lambda self: Path(str(self).replace("~", str(tmp_path / "home"))))
    # PATH 上的那个没有 host；~/.local/bin 没有；只有 good 有 host → 但 good 不在候选里，于是退回第一个并给警告
    p, warn = codex.find_codex()
    assert p == bare and "codex-code-mode-host" in warn
    # CODEX_BIN 指定 good → 用它，无警告
    monkeypatch.setenv("CODEX_BIN", str(good))
    p, warn = codex.find_codex()
    assert p == good and warn == ""


def _start(project_dir: Path, fake: Path, name: str, monkeypatch, prompt_text: str = "审 {{MODEL}} {{EFFORT}} {{DATE}}\n看 labs/01-first-task/notes.md") -> dict:
    monkeypatch.setenv("CODEX_BIN", str(fake))
    prompt = project_dir / "labs" / "01-first-task" / "audit" / "prompt-test.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(prompt_text, encoding="utf-8")
    return codex.start(project_dir, "audit", prompt, name)


def test_start_detaches_and_wait_sees_exit_line(project_dir: Path, tmp_path: Path, monkeypatch):
    fake = _fake_codex(tmp_path / "ok", FAKE_OK)
    res = _start(project_dir, fake, "t-ok", monkeypatch)
    assert res["ok"], res
    rec = Path(res["rec"])
    assert (rec / "pid").exists() and (rec / "job.json").exists()
    job = json.loads((rec / "job.json").read_text(encoding="utf-8"))
    assert job["lab"] == "01-first-task" and job["model"] == "gpt-6-astra"
    filled = (rec / "prompt.filled.md").read_text(encoding="utf-8")
    assert "{{" not in filled and "gpt-6-astra" in filled and "xhigh" in filled
    st = codex.wait(project_dir, "audit", "t-ok", max_seconds=30, poll=1)
    assert st["state"] == "done" and st["code"] == 0, st
    assert "报告已生成" in st["last_message"]
    info = (rec / "run_info.txt").read_text(encoding="utf-8")
    assert info.startswith("codex-cli") and "exit 0" in info and "tokens: 12,345" in info
    assert codex.live_jobs(project_dir) == []


def test_wait_returns_running_then_done(project_dir: Path, tmp_path: Path, monkeypatch):
    fake = _fake_codex(tmp_path / "slow", FAKE_OK)
    monkeypatch.setenv("FAKE_SLEEP", "3")
    res = _start(project_dir, fake, "t-slow", monkeypatch)
    assert res["ok"], res
    st = codex.wait(project_dir, "audit", "t-slow", max_seconds=1, poll=1)
    assert st["state"] == "running" and st["code"] == codex.STILL_RUNNING
    jobs = codex.live_jobs(project_dir)
    assert len(jobs) == 1 and jobs[0]["lab"] == "01-first-task"
    # 同名记录还在跑时不允许再启动
    again = _start(project_dir, fake, "t-slow", monkeypatch)
    assert not again["ok"] and "还在跑" in again["error"]
    st = codex.wait(project_dir, "audit", "t-slow", max_seconds=30, poll=1)
    assert st["state"] == "done"


def test_fail_closed_is_a_failure(project_dir: Path, tmp_path: Path, monkeypatch):
    fake = _fake_codex(tmp_path / "fc", FAKE_FAIL_CLOSED)
    res = _start(project_dir, fake, "t-fc", monkeypatch)
    assert res["ok"], res
    st = codex.wait(project_dir, "audit", "t-fc", max_seconds=30, poll=1)
    assert st["state"] == "failed" and st["code"] == codex.FAIL_CLOSED
    assert "fail closed" in st["detail"]


def test_quoted_fail_closed_words_are_not_a_failure(project_dir: Path, tmp_path: Path, monkeypatch):
    fake = _fake_codex(tmp_path / "echo", FAKE_ECHOES_WORDS)
    res = _start(project_dir, fake, "t-echo", monkeypatch)
    assert res["ok"], res
    st = codex.wait(project_dir, "audit", "t-echo", max_seconds=30, poll=1)
    assert st["state"] == "done" and st["code"] == 0, st


def test_dead_worker_is_reported_as_died(project_dir: Path):
    rec = codex.rec_dir(project_dir, "write", "t-dead")
    rec.mkdir(parents=True)
    (rec / "run_info.txt").write_text("codex-cli 0.160.0 | start 2026-10-08 02:09:02 | model gpt-6-astra\n", encoding="utf-8")
    (rec / "job.json").write_text(json.dumps({"pid": 999999, "lab": "01-first-task", "started_ts": time.time() - 100}), encoding="utf-8")
    st = codex.status(project_dir, "write", "t-dead")
    assert st["state"] == "died" and st["code"] == codex.DIED
    assert "exit 9" in (rec / "run_info.txt").read_text(encoding="utf-8")


def test_placeholder_and_missing_image_refused(project_dir: Path, tmp_path: Path, monkeypatch):
    fake = _fake_codex(tmp_path / "ph", FAKE_OK)
    res = _start(project_dir, fake, "t-ph", monkeypatch, prompt_text="{{MODEL}} 和 {{OUT}} 没填")
    assert not res["ok"] and res["code"] == 5 and "{{OUT}}" in res["error"]
    monkeypatch.setenv("CODEX_BIN", str(fake))
    prompt = project_dir / "p.md"
    prompt.write_text("x", encoding="utf-8")
    res = codex.start(project_dir, "write", prompt, "t-img", images=[tmp_path / "missing.png"])
    assert not res["ok"] and res["code"] == 4


def test_shell_wrappers_route_to_rd(project_dir: Path, tmp_path: Path, monkeypatch):
    """codex-audit.sh / codex-write.sh 只是 rd codex 的薄包装；用 --status 验证参数传对了。"""
    fake = _fake_codex(tmp_path / "sh", FAKE_OK)
    res = _start(project_dir, fake, "t-sh", monkeypatch)
    assert res["ok"]
    codex.wait(project_dir, "audit", "t-sh", max_seconds=30, poll=1)
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "CODEX_BIN": str(fake), "RD_HOME": os.environ.get("RD_HOME", "")}
    r = subprocess.run([str(root / "skills" / "rd-audit" / "codex-audit.sh"), "--status", str(project_dir), "t-sh"],
                       capture_output=True, text=True, env=env, cwd=root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert '"state": "done"' in r.stdout
    r = subprocess.run([str(root / "skills" / "rd-writer" / "codex-write.sh"), "--status", str(project_dir), "nope"],
                       capture_output=True, text=True, env=env, cwd=root)
    assert r.returncode == 1 and '"missing"' in r.stdout
    r = subprocess.run([str(root / "skills" / "rd-writer" / "codex-write.sh")], capture_output=True, text=True, env=env, cwd=root)
    assert r.returncode == 0 and "--wait" in r.stdout
    assert sys.executable  # 用到的 python 在 rd 包装里是 .venv 的；这里只确认脚本可执行
