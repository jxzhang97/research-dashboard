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


# ---------- 核打架的三个信号：CPU 的 system 占比、活跃线程数超过核数、内存被压缩/交换 ----------
_CACHE: dict = {"t": 0.0, "v": None}


def cpu_usage() -> dict | None:
    """macOS：top 连采两次取第二次的 user/sys/idle（第一次是开机以来的累计，不准）。拿不到返回 None。"""
    try:
        out = subprocess.check_output(["top", "-l", "2", "-n", "0", "-s", "1"], text=True, stderr=subprocess.DEVNULL, timeout=8)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = [ln for ln in out.splitlines() if ln.startswith("CPU usage")]
    if not lines:
        return None
    try:
        parts = {w.strip().split("%")[1].strip(): float(w.strip().split("%")[0]) for w in lines[-1].split(":", 1)[1].split(",")}
        return {"user": parts.get("user", 0.0), "sys": parts.get("sys", 0.0), "idle": parts.get("idle", 0.0)}
    except (ValueError, IndexError):
        return None


def memory_pressure() -> dict | None:
    """压缩区占了多少内存、交换区用了多少（GB）。"""
    try:
        vm = subprocess.check_output(["vm_stat"], text=True, stderr=subprocess.DEVNULL, timeout=5)
        page = int(vm.splitlines()[0].split("page size of")[1].split()[0])
        comp = next(int(ln.split(":")[1].strip().rstrip(".")) for ln in vm.splitlines() if ln.startswith("Pages occupied by compressor"))
        swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True, stderr=subprocess.DEVNULL, timeout=5)
        used = float(swap.split("used =")[1].split("M")[0]) / 1024
        total = (_sysctl("hw.memsize") or 0) / 2**30
        return {"ram_gb": round(total, 1), "compressor_gb": round(comp * page / 2**30, 1), "swap_used_gb": round(used, 1)}
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError, StopIteration):
        return None


_NUMERIC = ("julia", "python", "wolframkernel", "wolframscript", "mathkernel", "matlab", "octave")


def numeric_processes(min_cpu: float = 5.0) -> list[dict]:
    """正在算数的进程（命令含 julia/python/Mathematica 等且 CPU 占用超过 min_cpu%），以及每个进程**正在跑**的线程数（ps -M 里状态 R 的线程）。"""
    try:
        out = subprocess.check_output(["ps", "-axo", "pid=,pcpu=,rss=,command="], text=True, stderr=subprocess.DEVNULL, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []
    procs = []
    for ln in out.splitlines():
        try:
            pid, pcpu, rss, cmd = ln.split(None, 3)
            pid, pcpu, rss = int(pid), float(pcpu), int(rss)
        except ValueError:
            continue
        low = cmd.lower()
        if pcpu < min_cpu or not any(k in low for k in _NUMERIC) or pid == os.getpid():
            continue
        running = 0
        try:
            th = subprocess.check_output(["ps", "-M", "-p", str(pid)], text=True, stderr=subprocess.DEVNULL, timeout=5).splitlines()[1:]
            # ps -M：第一列 USER（主线程行）或空（子线程行），STAT 列在 %CPU 之后
            for t in th:
                cols = t.split()
                stat = cols[4] if t[:1] != " " else cols[3]
                if stat.startswith("R"):
                    running += 1
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, IndexError):
            running = max(1, int(round(pcpu / 100)))
        short = cmd.split()[0].rsplit("/", 1)[-1]
        args = " ".join(a for a in cmd.split()[1:] if not a.startswith("--sysimage") and not a.endswith(".so"))[:60]
        procs.append({"pid": pid, "cpu": round(pcpu, 1), "rss_gb": round(rss / 2**20, 2), "running_threads": max(running, 1), "cmd": f"{short} {args}".strip()})
    procs.sort(key=lambda x: -x["cpu"])
    return procs


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


def status(project: Path | None = None, probe: bool = True, cache_seconds: float = 10.0) -> dict:
    """空闲核数 + 打架检测。probe=True 时采 CPU/内存/线程（约 1 秒，结果缓存 cache_seconds）。"""
    jobs = list_jobs()
    reserve = int(registry.machine_settings().get("reserve_cores", 2))
    claimed = sum(int(j.get("cores", 0)) for j in jobs)
    total = perf_cores()
    load = load_1min()
    busy = max(claimed, int(round(load)))
    free = max(0, total - busy - reserve)
    others = [j for j in jobs if project and j.get("project") and j["project"] != _project_name(project)]
    st = {
        "host": hostname(), "perf_cores": total, "load_1min": round(load, 2), "claimed": claimed,
        "reserve": reserve, "free": free, "jobs": jobs, "warnings": [],
    }
    if probe:
        now = time.time()
        if _CACHE["v"] is None or now - _CACHE["t"] > cache_seconds:
            _CACHE["v"] = {"cpu": cpu_usage(), "mem": memory_pressure(), "procs": numeric_processes()}
            _CACHE["t"] = now
        st.update(_CACHE["v"])
        cpu, mem, procs = st["cpu"], st["mem"], st["procs"]
        threads = sum(p["running_threads"] for p in procs)
        st["running_threads"] = threads
        warn = st["warnings"]
        if threads > total:
            warn.append(f"核在打架：{len(procs)} 个数值进程共 {threads} 个线程在跑，超过 {total} 个性能核。减少并行数（WORKERS）或每个进程的线程数（Julia -t、OPENBLAS/MKL/OMP_NUM_THREADS）。")
        if cpu and cpu["sys"] >= 25 and (load >= total * 0.5 or threads >= total):
            warn.append(f"CPU 的 system 占比 {cpu['sys']:.0f}%（user {cpu['user']:.0f}%）：这么高多半是线程超额争抢（自旋、调度）或内存压缩/交换在吃 CPU，不是在算数。先查上面的线程数和下面的内存。")
        if mem and mem["ram_gb"] and (mem["compressor_gb"] > 0.35 * mem["ram_gb"] or mem["swap_used_gb"] > 8):
            warn.append(f"内存吃紧：压缩区 {mem['compressor_gb']} GB、交换区已用 {mem['swap_used_gb']} GB（物理内存 {mem['ram_gb']} GB）。再加并行只会更慢；减少同时跑的作业数。")
        if warn:
            free = 0
            st["free"] = 0
    st["advice"] = (f"本机 {total} 个性能核，当前负载 {load:.1f}，所有课题已登记 {claimed} 核"
                    + (f"（其中别的课题 {sum(int(j['cores']) for j in others)} 核）" if others else "")
                    + f"，留 {reserve} 核；现在最多再用 {free} 核。"
                    + ("".join(" ⚠ " + w for w in st["warnings"]) if st["warnings"] else ""))
    return st
