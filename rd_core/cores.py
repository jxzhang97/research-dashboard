"""空闲核数与作业登记：跑数值前看一眼，别让 core 打架。
登记表是**机器级**的（~/.rd/jobs.json），本机所有课题共用，所以不同课题的数值也互相看得见。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from . import registry
from .config import hostname


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


def _jobs_path() -> Path:
    return registry.home() / "jobs.json"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _project_name(project: Path | None) -> str:
    if not project:
        return ""
    try:
        from . import config
        return config.load(project)["project"]["name"]
    except Exception:  # noqa: BLE001
        return project.name


def list_jobs(prune: bool = True) -> list[dict]:
    p = _jobs_path()
    jobs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    if prune:
        kept = [j for j in jobs if (j.get("pid") and _alive(int(j["pid"]))) or (not j.get("pid") and time.time() - j.get("t", 0) < 86400)]
        if len(kept) != len(jobs):
            p.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        jobs = kept
    return jobs


def claim(project: Path | None, cores: int, label: str, pid: int | None = None) -> str:
    jobs = list_jobs()
    jid = f"{int(time.time())}-{os.getpid()}"
    jobs.append({"id": jid, "cores": int(cores), "label": label, "project": _project_name(project),
                 "pid": pid or os.getppid(), "t": time.time(), "host": hostname()})
    _jobs_path().write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    return jid


def release(jid: str) -> bool:
    jobs = list_jobs(prune=False)
    kept = [j for j in jobs if j["id"] != jid]
    _jobs_path().write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(kept) != len(jobs)


def status(project: Path | None = None) -> dict:
    jobs = list_jobs()
    reserve = int(registry.machine_settings().get("reserve_cores", 2))
    claimed = sum(int(j.get("cores", 0)) for j in jobs)
    total = perf_cores()
    load = load_1min()
    busy = max(claimed, int(round(load)))
    free = max(0, total - busy - reserve)
    others = [j for j in jobs if project and j.get("project") and j["project"] != _project_name(project)]
    return {
        "host": hostname(), "perf_cores": total, "load_1min": round(load, 2), "claimed": claimed,
        "reserve": reserve, "free": free, "jobs": jobs,
        "advice": (f"本机 {total} 个性能核，当前负载 {load:.1f}，所有课题已登记 {claimed} 核"
                   + (f"（其中别的课题 {sum(int(j['cores']) for j in others)} 核）" if others else "")
                   + f"，留 {reserve} 核；现在最多再用 {free} 核。"),
    }
