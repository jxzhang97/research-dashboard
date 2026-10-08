"""课题配置（config.toml，跨机器同步）与本机配置（.dashboard/machines/<host>.toml，不同步）。"""

from __future__ import annotations

import copy
import os
import shutil
import socket
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "project": {
        "name": "",
        "language": "zh",
        # 大的中间数据放在这里（studio 上），项目里只留 DATA.md 指路
        "data_root": "~/doc_unsyn/{name}",
    },
    "models": {
        # 默认一律 Fable 5.1 + max；任务书 frontmatter 的 model / effort 字段或任务页的下拉可以单独指定
        "read": "claude-fable-5-1",   # 读文献、推导、跑数值
        "write": "claude-fable-5-1",  # 已弃用：薄层写作由 [writer] 决定
        "effort": "xhigh",            # low / medium / high / xhigh / max（用户默认 extra high，特殊要求才用 max）
        # 按工作项种类给默认模型：只凭摘要筛 arXiv、把原话挂进问题树这两类文书任务不需要最贵的模型；
        # 起草任务书、建卡、消化裁决、执行 lab 仍用 read 的模型。任务书 frontmatter 的 model/effort 仍然优先。
        "kinds": {
            "arxiv_reason": {"model": "claude-opus-5-5", "effort": "xhigh"},
            "triage_idea": {"model": "claude-opus-5-5", "effort": "xhigh"},
        },
    },
    "writer": {
        # 薄层写作步（report.md、wiki 页、idea 当前回答、STATUS.md）交给谁写；见 rd-writer skill
        "backend": "codex",
        "model": "gpt-6-astra",
        "reasoning_effort": "xhigh",
    },
    "auditor": {
        # 审计步：推导审计每个 lab 收尾自动做，代码审计按钮触发；见 rd-audit skill
        "backend": "codex",
        "model": "gpt-6-astra",
        "reasoning_effort": "xhigh",
        "auto_derivation": True,
    },
    "agent": {
        "backend": "claude",  # 目前自动运行只支持 claude；codex 的交互会话靠 AGENTS.md + skills
        "max_turns": 0,       # 0 = 不限制
        "timeout_minutes": 240,
    },
    "arxiv": {
        "enabled": True,
        "categories": ["cond-mat.str-el", "cond-mat.supr-con", "cond-mat.quant-gas"],
        "keywords": [],
        "authors": [],
        "max_per_day": 5,
        "lookback_days": 3,
        "hour": 9,
    },
    "schedule": {
        "watch_seconds": 15,   # dashboard 开着时，多久扫一次待办（用户动作本身是立刻触发的）
        "tick_minutes": 60,    # dashboard 没开时 launchd 的兜底间隔
        "retry_minutes": 30,   # 某项失败后多久才重试
        # running 但没有活着的运行的 lab 会被自动续跑（resume_lab）；连续失败这么多次就改成 blocked 等用户看
        "max_resume_failures": 3,
        # 用户对讨论的回答不当场消化：每 digest_minutes 统一消化一次，这样互相关联的几个回答能一起考虑（用户 2026-10-04 定为 5 小时）
        "digest_minutes": 300,
    },
    "server": {
        "host": "0.0.0.0",
        # 只有这些网段来的请求能写（回答、审批、立刻执行）；其他地址一律只读。默认：本机 + Tailscale（100.64.0.0/10）
        "write_from": ["127.0.0.1/32", "::1/128", "100.64.0.0/10"],
        "port": 8010,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def hostname() -> str:
    return socket.gethostname().split(".")[0]


def load(project: Path) -> dict:
    cfg_path = project / "config.toml"
    user = {}
    if cfg_path.exists():
        with cfg_path.open("rb") as f:
            user = tomllib.load(f)
    cfg = _merge(DEFAULTS, user)
    if not cfg["project"]["name"]:
        cfg["project"]["name"] = project.name
    cfg["project"]["data_root"] = cfg["project"]["data_root"].format(name=cfg["project"]["name"])
    return cfg


def machine_file(project: Path) -> Path:
    return project / ".dashboard" / "machines" / f"{hostname()}.toml"


def load_machine(project: Path) -> dict:
    p = machine_file(project)
    if not p.exists():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def find_claude_bin() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for cand in (
        "/opt/homebrew/bin/claude",
        "/opt/anaconda3/bin/claude",
        "/usr/local/bin/claude",
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/.claude/local/claude"),
    ):
        if os.access(cand, os.X_OK):
            return cand
    return None


def claude_bin(project: Path) -> str:
    m = load_machine(project)
    b = m.get("claude_bin") or find_claude_bin()
    if not b:
        raise RuntimeError("找不到 claude 可执行文件；在 .dashboard/machines/<host>.toml 里写 claude_bin = \"...\"")
    return b


def write_machine(project: Path, **fields) -> Path:
    """写本机配置（简单 toml，只支持字符串/数字）。"""
    p = machine_file(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = load_machine(project)
    cur.update(fields)
    lines = []
    for k, v in cur.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        else:
            lines.append(f"{k} = {v}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
