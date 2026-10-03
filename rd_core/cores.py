"""空闲核数与作业登记：跑数值前看一眼，别让 core 打架。
登记表按主机名分开（.dashboard/jobs/<host>.json），不同机器互不干扰。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .config import hostname

RESERVE = 2  # 永远给系统和交互留两个核


def _sysctl(key: str) -> int | None:
    try:
        return int(subprocess.check_output(["sysctl", "-n", key], text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def perf_cores() -> int:
    return _sysctl("hw.perflevel0.physicalcpu") or _sysctl("hw.physicalcpu") or os.cpu_count() or 4


def load_1min() -> float:
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return 0.0


def _jobs_path(project: Path) -> Path:
    p = project / ".dashboard" / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{hostname()}.json"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def list_jobs(project: Path, prune: bool = True) -> list[dict]:
    p = _jobs_path(project)
    jobs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    if prune:
        kept = [j for j in jobs if (j.get("pid") and _alive(int(j["pid"]))) or (not j.get("pid") and time.time() - j.get("t", 0) < 86400)]
        if len(kept) != len(jobs):
            p.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        jobs = kept
    return jobs


def claim(project: Path, cores: int, label: str, pid: int | None = None) -> str:
    jobs = list_jobs(project)
    jid = f"{int(time.time())}-{os.getpid()}"
    jobs.append({"id": jid, "cores": cores, "label": label, "pid": pid or os.getppid(), "t": time.time(), "host": hostname()})
    _jobs_path(project).write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    return jid


def release(project: Path, jid: str) -> bool:
    jobs = list_jobs(project, prune=False)
    kept = [j for j in jobs if j["id"] != jid]
    _jobs_path(project).write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(kept) != len(jobs)


def status(project: Path) -> dict:
    jobs = list_jobs(project)
    claimed = sum(int(j.get("cores", 0)) for j in jobs)
    total = perf_cores()
    load = load_1min()
    busy = max(claimed, int(round(load)))
    free = max(0, total - busy - RESERVE)
    return {
        "host": hostname(), "perf_cores": total, "load_1min": round(load, 2), "claimed": claimed,
        "reserve": RESERVE, "free": free, "jobs": jobs,
        "advice": f"本机 {total} 个性能核，当前负载 {load:.1f}，已登记 {claimed} 核，留 {RESERVE} 核；现在最多再用 {free} 核。",
    }
