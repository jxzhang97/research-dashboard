"""launchd 定时任务（只装在 studio），每个课题三件：
- com.jiaxin.rd.<课题>.server  常驻 dashboard
- com.jiaxin.rd.<课题>.tick    每 N 分钟兜底处理待办
- com.jiaxin.rd.<课题>.arxiv   每天固定时间扫 arXiv（分钟按课题名错开）
安装时自动保证端口不和本机其他课题冲突，并登记到 ~/.rd/projects.json。"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
import zlib
from pathlib import Path

from . import TEMPLATE_ROOT, config, registry

LAUNCH_DIR = Path("~/Library/LaunchAgents").expanduser()


def _label(cfg: dict, job: str) -> str:
    name = re.sub(r"[^\w.-]", "_", cfg["project"]["name"])
    return f"com.jiaxin.rd.{name}.{job}"


def _env(project: Path) -> dict:
    bin_dir = os.path.dirname(config.claude_bin(project))
    path = f"{bin_dir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    return {"PATH": path, "HOME": str(Path.home()), "LANG": "en_US.UTF-8"}


def write_port(project: Path, port: int) -> None:
    """把端口写回课题的 config.toml（它会随 iCloud 同步，两台机器看到同一个端口）。"""
    p = project / "config.toml"
    text = p.read_text(encoding="utf-8")
    if re.search(r"(?m)^port\s*=", text):
        text = re.sub(r"(?m)^(port\s*=\s*)\d+", rf"\g<1>{port}", text, count=1)
    elif "[server]" in text:
        text = text.replace("[server]", f"[server]\nport = {port}", 1)
    else:
        text += f"\n[server]\nport = {port}\n"
    p.write_text(text, encoding="utf-8")


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
        # 回答的统一消化：server 自己有定时器，这个是 server 没开时的兜底
        "digest": {**base("digest", ["digest"]), "StartInterval": int(cfg["schedule"].get("digest_minutes", 120)) * 60, "RunAtLoad": False},
    }
    if cfg["arxiv"].get("enabled", True):
        minute = 5 + (zlib.crc32(cfg["project"]["name"].encode()) % 10) * 5  # 不同课题错开 5 分钟
        out["arxiv"] = {**base("arxiv", ["arxiv-scan"]), "StartCalendarInterval": {"Hour": int(cfg["arxiv"]["hour"]), "Minute": minute}}
    return out


def install(project: Path) -> list[str]:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    project = project.resolve()
    cfg = config.load(project)
    name = cfg["project"]["name"]
    done = []
    port = int(cfg["server"]["port"])
    taken = registry.port_taken(port, exclude=project)
    if taken:
        new = registry.free_port(port + 1, exclude=project)
        write_port(project, new)
        done.append(f"端口 {port} 已被「{taken}」占用，本课题改用 {new}（已写回 config.toml）")
        port = new
    registry.register(project, name, port)  # 课题名重复会在这里报错
    config.write_machine(project, claude_bin=config.find_claude_bin() or "")
    for job, pl in plists(project).items():
        p = LAUNCH_DIR / f"{pl['Label']}.plist"
        subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
        with p.open("wb") as f:
            plistlib.dump(pl, f)
        r = subprocess.run(["launchctl", "load", str(p)], capture_output=True, text=True)
        done.append(f"{pl['Label']}: {'已加载' if r.returncode == 0 else r.stderr.strip()}  ({p})")
    done.append(f"dashboard: http://localhost:{port}")
    return done


def uninstall(project: Path) -> list[str]:
    done = []
    for job, pl in plists(project).items():
        p = LAUNCH_DIR / f"{pl['Label']}.plist"
        if p.exists():
            subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
            p.unlink()
            done.append(f"{pl['Label']}: 已卸载")
    registry.unregister(project)
    return done


def status(project: Path) -> list[str]:
    out = []
    listing = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    for job, pl in plists(project).items():
        loaded = pl["Label"] in listing
        out.append(f"{pl['Label']}: {'运行中/已加载' if loaded else '未加载'}")
    port = int(config.load(project)["server"]["port"])
    out.append(f"端口 {port}: {'在监听' if registry.port_listening(port) else '没有服务'}")
    return out
