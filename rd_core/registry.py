"""机器级注册表（~/.rd/，每台机器一份，不进 iCloud）：
- projects.json：本机上有哪些课题、各用哪个端口（端口唯一、课题名唯一）
- machine.toml：本机同时最多跑几个 agent、给系统留几个核
- jobs.json：所有课题共用的数值作业登记（见 cores.py）
- slots/：agent 并发槽位的锁文件（见 runner.py）"""

from __future__ import annotations

import json
import os
import socket
import time
import tomllib
from pathlib import Path

DEFAULT_PORT = 8010
MACHINE_DEFAULTS = {"max_agents": 2, "reserve_cores": 2}


def home() -> Path:
    p = Path(os.environ.get("RD_HOME") or "~/.rd").expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def machine_settings() -> dict:
    p = home() / "machine.toml"
    if not p.exists():
        p.write_text(
            "# 本机设置（不同步）\n"
            f"max_agents = {MACHINE_DEFAULTS['max_agents']}      # 所有课题加起来同时最多跑几个 agent\n"
            f"reserve_cores = {MACHINE_DEFAULTS['reserve_cores']}   # 跑数值时永远给系统和交互留几个核\n",
            encoding="utf-8",
        )
    with p.open("rb") as f:
        d = tomllib.load(f)
    return {**MACHINE_DEFAULTS, **d}


def _projects_path() -> Path:
    return home() / "projects.json"


def load_projects() -> dict[str, dict]:
    p = _projects_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_projects(d: dict) -> None:
    _projects_path().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


def port_taken(port: int, exclude: Path | None = None) -> str | None:
    """端口被别的课题占了就返回那个课题名；被别的程序占了返回 '其他程序'。"""
    ex = str(exclude.resolve()) if exclude else None
    projects = load_projects()
    for path, info in projects.items():
        if path != ex and int(info.get("port", 0)) == int(port):
            return info.get("name", path)
    # 这个课题自己登记的端口：就算正在监听（它自己的 server 还没停），也不算被占
    if ex and int(projects.get(ex, {}).get("port", 0) or 0) == int(port):
        return None
    if port_listening(port):
        return "其他程序"
    return None


def free_port(start: int = DEFAULT_PORT, exclude: Path | None = None) -> int:
    port = start
    while port_taken(port, exclude):
        port += 1
    return port


def register(project: Path, name: str, port: int) -> None:
    d = load_projects()
    key = str(project.resolve())
    for path, info in d.items():
        if path != key and info.get("name") == name and Path(path).exists():
            raise RuntimeError(f"课题名「{name}」已被 {path} 使用；launchd 标签和 data_root 都按课题名区分，请换一个名字")
    d[key] = {"name": name, "port": int(port), "t": time.strftime("%Y-%m-%d %H:%M")}
    save_projects(d)


def unregister(project: Path) -> None:
    d = load_projects()
    d.pop(str(project.resolve()), None)
    save_projects(d)


def list_projects() -> list[dict]:
    out = []
    for path, info in sorted(load_projects().items(), key=lambda kv: kv[1].get("name", "")):
        out.append({
            "path": path, "name": info.get("name"), "port": info.get("port"), "registered": info.get("t"),
            "exists": (Path(path) / "config.toml").exists(), "listening": port_listening(int(info.get("port", 0) or 0)),
        })
    return out
