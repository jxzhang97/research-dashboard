"""Codex 作业（审计步、写作步）：找可用的 codex、脱离父进程启动、记录 pid、前台等待。

为什么要脱离父进程：无人值守的研究 agent 是一次性的 `claude -p` 进程，它一结束，它名下的后台任务
（Claude Code 的 run_in_background）一起被清掉；lab 02 的审计就是这样死的。这里用 start_new_session
把 codex 放进独立会话，agent 退出后它照跑，结果落在记录目录里，续跑运行接着处理。

记录目录：<课题根>/.dashboard/auditing/<名>/ 或 writing/<名>/，内含
  prompt.md、prompt.filled.md、job.json（pid、模型、图）、run_info.txt（开始行 / 结束行）、
  codex_output.txt（完整输出）、last_message.txt（最后回复）、worker.log。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config

KINDS = {"audit": ("auditor", "auditing"), "write": ("writer", "writing")}
BUNDLED = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")
LEGACY_BUNDLED = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
# 0.16x 的独立二进制在工具执行不可用时不报错，只在输出里留 codex 自己的诊断行（行首是 "warning: Code Mode is unavailable"
# 或带时间戳的 "ERROR codex_core::tools::router: error=failed to spawn code-mode host"），然后带着 exit 0 返回一句"报告未生成"。
# 只认这两种行首形式：提示词、skill 文本、log.md 被 codex 读出来时也会含"fail closed""code-mode-host"字样，不能按词匹配。
FAIL_CLOSED_RE = re.compile(
    r"^(?:warning: Code Mode is unavailable|\d{4}-\d{2}-\d{2}T\S+\s+ERROR codex_core::tools::router: error=failed to spawn code-mode host)",
    re.I | re.M,
)
PLACEHOLDER_RE = re.compile(r"{{[A-Z_]+}}")
STILL_RUNNING = 7
DIED = 9
FAIL_CLOSED = 6


# ---------- 找 codex ----------
def candidates() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("CODEX_BIN")
    if env:
        out.append(Path(env).expanduser())
    out.append(BUNDLED)
    w = shutil.which("codex")
    if w:
        out.append(Path(w))
    out += [Path("~/.local/bin/codex").expanduser(), Path("/opt/homebrew/bin/codex"), LEGACY_BUNDLED]
    seen: set[Path] = set()
    res = []
    for p in out:
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key in seen:
            continue
        seen.add(key)
        if p.is_file() and os.access(p, os.X_OK):
            res.append(p)
    return res


def has_host(p: Path) -> bool:
    """同目录有没有 codex-code-mode-host（没有它，codex 读不了文件、跑不了命令，但照样返回 exit 0）。"""
    return (p.parent / "codex-code-mode-host").exists()


def find_codex() -> tuple[Path | None, str]:
    """返回 (路径, 警告)。CODEX_BIN 显式指定的优先；否则优先带 host 的候选。"""
    cands = candidates()
    env = os.environ.get("CODEX_BIN")
    if env and cands and cands[0] == Path(env).expanduser():
        return cands[0], "" if has_host(cands[0]) else f"CODEX_BIN 指定的 {cands[0]} 旁边没有 codex-code-mode-host，工具执行可能 fail closed"
    for p in cands:
        if has_host(p):
            return p, ""
    if cands:
        return cands[0], f"{cands[0]} 旁边没有 codex-code-mode-host，工具执行可能 fail closed；建议用 ChatGPT.app 自带的 {BUNDLED}"
    return None, "找不到 codex（装 ChatGPT.app，或 npm install -g @openai/codex，然后 codex login）"


def logged_in(codex: Path) -> bool:
    try:
        r = subprocess.run([str(codex), "login", "status"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "logged in" in (r.stdout + r.stderr).lower()


def version(codex: Path) -> str:
    try:
        r = subprocess.run([str(codex), "--version"], capture_output=True, text=True, timeout=30)
        parts = (r.stdout or r.stderr).split()
        return parts[-1] if parts else "?"
    except (OSError, subprocess.TimeoutExpired):
        return "?"


# ---------- 记录目录 ----------
def rec_dir(root: Path, kind: str, name: str) -> Path:
    return root / ".dashboard" / KINDS[kind][1] / name


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _exit_line(rec: Path) -> str | None:
    p = rec / "run_info.txt"
    if not p.exists():
        return None
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("exit "):
            return ln
    return None


def _job(rec: Path) -> dict:
    p = rec / "job.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def infer_lab(prompt_path: Path, prompt_text: str) -> str:
    m = re.search(r"labs/([0-9]{2}-[^/\s]+)/", str(prompt_path)) or re.search(r"labs/([0-9]{2}-[^/\s`)]+)/", prompt_text)
    return m.group(1) if m else ""


# ---------- 启动 ----------
def start(root: Path, kind: str, prompt: Path, name: str, images: list[Path] | None = None, lab: str = "") -> dict:
    """组好记录目录，派一个独立会话的 worker 去跑 codex exec，立刻返回。"""
    if kind not in KINDS:
        return {"ok": False, "code": 1, "error": f"kind 只能是 {'/'.join(KINDS)}"}
    root = Path(root).resolve()
    rec = rec_dir(root, kind, name)
    prev = status(root, kind, name) if rec.exists() else None
    if prev and prev["state"] == "running":
        return {"ok": False, "code": 1, "error": f"记录目录 {name} 里的作业还在跑（pid {prev.get('pid')}），换个名字或先等它", "rec": str(rec)}
    rec.mkdir(parents=True, exist_ok=True)
    prompt = Path(prompt)
    if not prompt.is_file():
        return {"ok": False, "code": 1, "error": f"提示词文件不存在: {prompt}"}
    shutil.copy(prompt, rec / "prompt.md")
    section = KINDS[kind][0]
    sec = config.load(root).get(section, {})
    model = sec.get("model", "gpt-6-astra")
    effort = sec.get("reasoning_effort", "xhigh")
    info = rec / "run_info.txt"

    codex, warn = find_codex()
    if not codex:
        info.write_text(warn + "\n", encoding="utf-8")
        return {"ok": False, "code": 2, "error": warn, "rec": str(rec)}
    if not logged_in(codex):
        msg = f"codex 未登录（在这台机器上运行 {codex} login）"
        info.write_text(msg + "\n", encoding="utf-8")
        return {"ok": False, "code": 3, "error": msg, "rec": str(rec)}

    imgs = []
    for f in images or []:
        f = Path(f)
        if not f.is_file():
            msg = f"图不存在: {f}"
            info.write_text(msg + "\n", encoding="utf-8")
            return {"ok": False, "code": 4, "error": msg, "rec": str(rec)}
        imgs.append(str(f.resolve()))

    text = prompt.read_text(encoding="utf-8")
    text = text.replace("{{MODEL}}", model).replace("{{EFFORT}}", effort).replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        msg = f"提示词还有没填的占位符: {' '.join(left)}"
        info.write_text(msg + "\n", encoding="utf-8")
        return {"ok": False, "code": 5, "error": msg, "rec": str(rec)}
    (rec / "prompt.filled.md").write_text(text, encoding="utf-8")

    lab = lab or infer_lab(prompt, text)
    head = (f"codex-cli {version(codex)} | start {_now()} | model {model} | reasoning_effort {effort} | sandbox workspace-write"
            f" | images: {len(imgs)} | prompt: {prompt.name} | bin: {codex}")
    info.write_text(head + ("\n警告: " + warn if warn else "") + "\n", encoding="utf-8")
    job = {"kind": kind, "name": name, "lab": lab, "codex": str(codex), "model": model, "effort": effort,
           "images": imgs, "root": str(root), "started": _now(), "started_ts": time.time(), "pid": None}
    (rec / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    log = (rec / "worker.log").open("ab")
    env = dict(os.environ)
    env["CODEX_BIN"] = str(codex)
    proc = subprocess.Popen(
        [sys.executable, "-m", "rd_core.codex", "worker", str(root), kind, name],
        cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
        start_new_session=True,  # 独立会话：agent 的运行结束不会把它带走
    )
    log.close()
    job["pid"] = proc.pid
    (rec / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    (rec / "pid").write_text(str(proc.pid), encoding="utf-8")
    return {"ok": True, "code": 0, "rec": str(rec), "pid": proc.pid, "model": model, "effort": effort, "codex": str(codex), "warn": warn, "lab": lab}


def worker(root: Path, kind: str, name: str) -> int:
    """独立会话里真正跑 codex exec 的进程。"""
    root = Path(root)
    rec = rec_dir(root, kind, name)
    job = _job(rec)
    codex = job.get("codex") or os.environ.get("CODEX_BIN") or "codex"
    prompt_text = (rec / "prompt.filled.md").read_text(encoding="utf-8")
    cmd = [codex, "exec", "-C", str(root), "-m", job.get("model", "gpt-6-astra"),
           "-c", f"model_reasoning_effort={job.get('effort', 'xhigh')}", "-s", "workspace-write"]
    for img in job.get("images") or []:
        cmd += ["-i", img]
    cmd += ["-o", str(rec / "last_message.txt"), prompt_text]
    t0 = time.time()
    with (rec / "codex_output.txt").open("wb") as out:
        try:
            # stdin 必须接 /dev/null，否则 codex exec 会等标准输入
            rc = subprocess.run(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT).returncode
        except OSError as e:
            out.write(f"启动 codex 失败: {e!r}\n".encode())
            rc = 2
    text = (rec / "codex_output.txt").read_text(encoding="utf-8", errors="replace")
    fail_closed = bool(FAIL_CLOSED_RE.search(text))
    if fail_closed and rc == 0:
        rc = FAIL_CLOSED
    tokens = ""
    m = re.search(r"^tokens used\s*\n?\s*([^\n]*)", text, re.M | re.I)
    if m:
        tokens = m.group(1).strip().replace(" ", "")
    line = f"exit {rc} | end {_now()} | duration {int(time.time() - t0)} s | tokens: {tokens}"
    if fail_closed:
        line += " | codex 工具执行不可用（缺 codex-code-mode-host，fail closed），这次的输出无效"
    with (rec / "run_info.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return rc


# ---------- 查询与等待 ----------
def status(root: Path, kind: str, name: str) -> dict:
    """state: running / done / failed / died / missing。done = exit 0。"""
    root = Path(root)
    rec = rec_dir(root, kind, name)
    if not rec.exists():
        return {"state": "missing", "code": 1, "rec": str(rec), "name": name, "kind": kind}
    job = _job(rec)
    out = {"rec": str(rec), "name": name, "kind": kind, "lab": job.get("lab", ""), "pid": job.get("pid"),
           "started": job.get("started"), "elapsed_s": int(time.time() - job["started_ts"]) if job.get("started_ts") else None}
    op = rec / "codex_output.txt"
    out["output_bytes"] = op.stat().st_size if op.exists() else 0
    ex = _exit_line(rec)
    if ex is None and not (rec / "run_info.txt").exists():
        return {**out, "state": "failed", "code": 1, "detail": "没有 run_info.txt，作业没有启动"}
    if ex is None:
        first = (rec / "run_info.txt").read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        if first and not first[0].startswith("codex-cli"):
            return {**out, "state": "failed", "code": 2, "detail": first[0]}
        if _pid_alive(job.get("pid")):
            return {**out, "state": "running", "code": STILL_RUNNING}
        ex = f"exit {DIED} | end {_now()} | 进程消失（没有结束行，多半是随上一次 agent 运行一起被杀）"
        with (rec / "run_info.txt").open("a", encoding="utf-8") as f:
            f.write(ex + "\n")
    m = re.match(r"exit (\d+)", ex)
    code = int(m.group(1)) if m else 1
    lm = rec / "last_message.txt"
    out["last_message"] = lm.read_text(encoding="utf-8", errors="replace").strip() if lm.exists() else ""
    out["detail"] = ex
    out["code"] = code
    out["state"] = "done" if code == 0 else ("died" if code == DIED else "failed")
    return out


def wait(root: Path, kind: str, name: str, max_seconds: int = 100, poll: int = 10) -> dict:
    """前台阻塞到作业结束或 max_seconds 到；还在跑返回 state=running（退出码 7），调用方循环即可。"""
    t0 = time.time()
    while True:
        st = status(root, kind, name)
        if st["state"] != "running":
            return st
        if time.time() - t0 >= max_seconds:
            return st
        time.sleep(max(1, min(poll, max_seconds)))


def live_jobs(root: Path) -> list[dict]:
    """本课题所有还在跑的 codex 作业（审计 + 写作）。"""
    root = Path(root)
    out = []
    for kind, (_, sub) in KINDS.items():
        d = root / ".dashboard" / sub
        if not d.exists():
            continue
        for rec in sorted(d.iterdir()):
            if not (rec / "job.json").exists():
                continue
            st = status(root, kind, rec.name)
            if st["state"] == "running":
                out.append(st)
    return out


# ---------- 命令行 ----------
def _print(st: dict) -> None:
    print(json.dumps({k: v for k, v in st.items() if k != "last_message"}, ensure_ascii=False))
    if st.get("last_message"):
        print("--- last message ---")
        print(st["last_message"])


def cli(args) -> int:
    root = Path(args.path).expanduser().resolve()
    if args.action == "start":
        res = start(root, args.kind, Path(args.prompt).expanduser(), args.name, [Path(i) for i in (args.image or [])], lab=args.lab or "")
        if not res["ok"]:
            print(json.dumps(res, ensure_ascii=False))
            return int(res["code"])
        print(json.dumps(res, ensure_ascii=False))
        if not args.sync:
            return 0
        st = wait(root, args.kind, args.name, max_seconds=10 ** 7, poll=15)
        _print(st)
        return int(st["code"])
    if args.action == "wait":
        st = wait(root, args.kind, args.name, max_seconds=int(args.max_seconds), poll=int(args.poll))
        _print(st)
        return int(st["code"])
    if args.action == "status":
        st = status(root, args.kind, args.name)
        _print(st)
        return int(st["code"])
    if args.action == "list":
        jobs = live_jobs(root)
        print(json.dumps(jobs, ensure_ascii=False, indent=1) if jobs else "没有在跑的 codex 作业")
        return 0
    return 1


def add_parser(sub) -> None:
    p = sub.add_parser("codex", help="Codex 作业（审计 / 写作）：start 脱离父进程启动，wait 前台等待，status 查询，list 列出在跑的")
    p.add_argument("action", choices=["start", "wait", "status", "list"])
    p.add_argument("path", help="课题目录")
    p.add_argument("--kind", choices=list(KINDS), default="audit")
    p.add_argument("--name", help="记录目录名")
    p.add_argument("--prompt", help="提示词文件（start）")
    p.add_argument("--image", action="append", help="附图（start，可多次）")
    p.add_argument("--lab", help="所属 lab id（start，缺省从提示词推断）")
    p.add_argument("--sync", action="store_true", help="start 后一直等到结束（交互会话用）")
    p.add_argument("--max-seconds", default=100, help="wait 最多等几秒，到了返回 7（还在跑）")
    p.add_argument("--poll", default=10)
    p.set_defaults(fn=lambda a: sys.exit(cli(a)))


if __name__ == "__main__":  # python -m rd_core.codex worker <root> <kind> <name>
    if len(sys.argv) >= 5 and sys.argv[1] == "worker":
        sys.exit(worker(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
    print("用法: python -m rd_core.codex worker <课题根> <audit|write> <记录目录名>", file=sys.stderr)
    sys.exit(2)
