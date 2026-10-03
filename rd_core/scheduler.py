"""launchd 定时任务（只装在 studio）：
- com.jiaxin.rd.<课题>.server  常驻 dashboard
- com.jiaxin.rd.<课题>.tick    每 N 分钟处理待办（回答、审批、升级）
- com.jiaxin.rd.<课题>.arxiv   每天固定时间扫 arXiv"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from . import TEMPLATE_ROOT, config

LAUNCH_DIR = Path("~/Library/LaunchAgents").expanduser()


def _label(cfg: dict, job: str) -> str:
    name = cfg["project"]["name"].replace(" ", "_")
    return f"com.jiaxin.rd.{name}.{job}"


def _env(project: Path) -> dict:
    bin_dir = os.path.dirname(config.claude_bin(project))
    path = f"{bin_dir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    return {"PATH": path, "HOME": str(Path.home()), "LANG": "en_US.UTF-8"}


def plists(project: Path) -> dict[str, dict]:
    cfg = config.load(project)
    rd = str(TEMPLATE_ROOT / "rd")
    logdir = project / ".dashboard" / "launchd"
    logdir.mkdir(parents=True, exist_ok=True)
    env = _env(project)
    base = lambda job, args: {  # noqa: E731
        "Label": _label(cfg, job),
        "ProgramArguments": [rd, *args, str(project)],
        "EnvironmentVariables": env,
        "StandardOutPath": str(logdir / f"{job}.log"),
        "StandardErrorPath": str(logdir / f"{job}.err"),
        "WorkingDirectory": str(project),
    }
    out = {
        "server": {**base("server", ["serve"]), "KeepAlive": True, "RunAtLoad": True},
        "tick": {**base("tick", ["tick"]), "StartInterval": int(cfg["schedule"]["tick_minutes"]) * 60, "RunAtLoad": False},
    }
    if cfg["arxiv"].get("enabled", True):
        out["arxiv"] = {**base("arxiv", ["arxiv-scan"]), "StartCalendarInterval": {"Hour": int(cfg["arxiv"]["hour"]), "Minute": 5}}
    return out


def install(project: Path) -> list[str]:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    done = []
    for job, pl in plists(project).items():
        p = LAUNCH_DIR / f"{pl['Label']}.plist"
        subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
        with p.open("wb") as f:
            plistlib.dump(pl, f)
        r = subprocess.run(["launchctl", "load", str(p)], capture_output=True, text=True)
        done.append(f"{pl['Label']}: {'已加载' if r.returncode == 0 else r.stderr.strip()}  ({p})")
    return done


def uninstall(project: Path) -> list[str]:
    done = []
    for job, pl in plists(project).items():
        p = LAUNCH_DIR / f"{pl['Label']}.plist"
        if p.exists():
            subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
            p.unlink()
            done.append(f"{pl['Label']}: 已卸载")
    return done


def status(project: Path) -> list[str]:
    out = []
    listing = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    for job, pl in plists(project).items():
        loaded = pl["Label"] in listing
        out.append(f"{pl['Label']}: {'运行中/已加载' if loaded else '未加载'}")
    return out
