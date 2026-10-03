"""无界面调用 Claude Code（`claude -p`）在课题目录里干活，并把过程写进 .dashboard/runs/<id>/。
同一课题同一时间只允许一个 agent 写文件：用 .dashboard/agent.lock 串行化（服务器和定时任务共用）。"""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config
from .project import Project

HEADLESS_RULES = """
你现在是无人值守运行（没有人在屏幕前）。在遵守 AGENTS.md 的前提下，额外注意：
1. 不要用 AskUserQuestion，也不要停下来等确认。需要用户裁决的问题，按 rd-discussion skill 写进 discussion/ 一个新文件（status: open, asked_by: agent），把当前任务的状态改成 waiting_answer，记录进 log.md，然后结束本次运行。用户回答后系统会再次调用你。
2. 只在课题目录内写文件；大的中间数据写到 config.toml 的 data_root 下，并在 lab 文件夹留 DATA.md。
3. 结束前：更新受影响的卡片/wiki/idea 状态，追加 log.md，然后 `git add -A && git commit -m "<简述>"`（如果课题目录是 git 仓库）。
4. 最后一条输出用三到五行中文总结：做了什么、改了哪些文件、还有什么没做。
""".strip()


def _run_dir(project: Project, run_id: str) -> Path:
    d = project.dash / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_run_id(label: str = "") -> str:
    from .project import slugify
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{slugify(label, 24)}" if label else stamp


def build_command(project: Project, prompt: str, model: str | None, effort: str | None, cfg: dict) -> list[str]:
    bin_ = config.claude_bin(project.root)
    settings = {}
    if effort:
        settings["effortLevel"] = effort
    cmd = [
        bin_, "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--append-system-prompt", HEADLESS_RULES,
    ]
    if model:
        cmd += ["--model", model]
    if settings:
        cmd += ["--settings", json.dumps(settings)]
    max_turns = int(cfg.get("agent", {}).get("max_turns", 0) or 0)
    if max_turns > 0:
        cmd += ["--max-turns", str(max_turns)]
    return cmd


def _fmt_event(ev: dict) -> str:
    """把 stream-json 事件压成人能读的一行行日志。"""
    t = ev.get("type")
    out = []
    if t == "assistant":
        for blk in ev.get("message", {}).get("content", []):
            bt = blk.get("type")
            if bt == "text" and blk.get("text", "").strip():
                out.append(blk["text"].rstrip())
            elif bt == "tool_use":
                inp = blk.get("input", {})
                name = blk.get("name", "?")
                if name == "Bash":
                    desc = inp.get("description") or inp.get("command", "")
                    out.append(f"▶ Bash: {str(desc)[:200]}")
                elif name in ("Read", "Write", "Edit", "MultiEdit"):
                    out.append(f"▶ {name}: {inp.get('file_path', '')}")
                elif name == "Skill":
                    out.append(f"▶ Skill: {inp.get('skill', '')}")
                elif name in ("Agent", "Task"):
                    out.append(f"▶ 子 agent: {str(inp.get('description', ''))[:120]}")
                else:
                    out.append(f"▶ {name}")
    elif t == "result":
        sub = ev.get("subtype", "")
        cost = ev.get("total_cost_usd")
        dur = ev.get("duration_ms")
        s = f"■ 结束 ({'出错' if ev.get('is_error') else sub})"
        if dur:
            s += f" 用时 {dur / 1000:.0f}s"
        if cost is not None:
            s += f" 费用 ${cost:.2f}"
        out.append(s)
    elif t == "system" and ev.get("subtype") == "init":
        out.append(f"● 会话开始 model={ev.get('model', '?')}")
    return "\n".join(out)


class Runner:
    """执行一次运行。阻塞；由调用方决定放线程还是直接跑。"""

    def __init__(self, project: Project):
        self.project = project
        self.cfg = config.load(project.root)

    def run(self, prompt: str, kind: str = "manual", label: str = "", model: str | None = None,
            effort: str | None = None, run_id: str | None = None, on_line=None) -> dict:
        run_id = run_id or new_run_id(label or kind)
        d = _run_dir(self.project, run_id)
        models = self.cfg["models"]
        model = model or models["read"]
        effort = effort or models.get("effort")
        meta = {
            "id": run_id, "kind": kind, "label": label or kind, "prompt": prompt, "model": model,
            "effort": effort, "status": "queued", "started": None, "ended": None, "pid": None,
            "host": config.hostname(),
        }
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "prompt.md").write_text(prompt, encoding="utf-8")

        lock_path = self.project.dash / "agent.lock"
        with lock_path.open("w") as lock:
            self._log(d, "⏳ 等待 agent 锁（同一课题同时只跑一个）…")
            fcntl.flock(lock, fcntl.LOCK_EX)
            meta["status"] = "running"
            meta["started"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cmd = build_command(self.project, prompt, model, effort, self.cfg)
            self._log(d, f"$ {' '.join(shlex.quote(c) for c in cmd[:1])} -p … --model {model} effort={effort}")
            env = dict(os.environ)
            env.setdefault("RD_RUN_ID", run_id)
            env["RD_PROJECT"] = str(self.project.root)
            timeout = int(self.cfg["agent"].get("timeout_minutes", 240)) * 60
            raw = (d / "raw.jsonl").open("a", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    cmd, cwd=self.project.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, env=env, start_new_session=True,
                )
                meta["pid"] = proc.pid
                self._save(d, meta)
                last_result = None
                deadline = time.time() + timeout

                def killer():
                    while proc.poll() is None:
                        if time.time() > deadline or (d / "STOP").exists():
                            try:
                                os.killpg(proc.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                            break
                        time.sleep(2)

                threading.Thread(target=killer, daemon=True).start()
                assert proc.stdout is not None
                for line in proc.stdout:
                    raw.write(line)
                    raw.flush()
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        self._log(d, line, on_line)
                        continue
                    if ev.get("type") == "result":
                        last_result = ev
                    txt = _fmt_event(ev)
                    if txt:
                        self._log(d, txt, on_line)
                proc.wait()
                if (d / "STOP").exists():
                    meta["status"] = "stopped"
                elif proc.returncode == 0 and last_result and last_result.get("subtype") == "success" and not last_result.get("is_error"):
                    meta["status"] = "done"
                else:
                    meta["status"] = "failed"
                    self._log(d, f"退出码 {proc.returncode}", on_line)
                if last_result:
                    meta["result"] = str(last_result.get("result", ""))[:4000]
                    meta["cost_usd"] = last_result.get("total_cost_usd")
            except Exception as e:  # noqa: BLE001
                meta["status"] = "failed"
                self._log(d, f"运行器异常: {e!r}", on_line)
            finally:
                raw.close()
                meta["ended"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                meta["pid"] = None
                self._save(d, meta)
                fcntl.flock(lock, fcntl.LOCK_UN)
        self.project.append_log("agent", f"运行 {meta['label']} → {meta['status']}", f".dashboard/runs/{run_id}/log.txt")
        return meta

    @staticmethod
    def _save(d: Path, meta: dict) -> None:
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def _log(d: Path, text: str, on_line=None) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        block = "\n".join(f"[{stamp}] {ln}" if i == 0 else f"           {ln}" for i, ln in enumerate(text.splitlines())) + "\n"
        with (d / "log.txt").open("a", encoding="utf-8") as f:
            f.write(block)
        if on_line:
            on_line(block)


def stop_run(project: Project, run_id: str) -> bool:
    d = project.dash / "runs" / run_id
    if not d.exists():
        return False
    (d / "STOP").touch()
    return True
