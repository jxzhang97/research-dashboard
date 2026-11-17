"""提醒：dashboard 上出现新的「等你的事」时，在 TickTick 里建一条任务（经 macOS「快捷指令」）。

每隔 [notify].hours 小时看一次。和上次相比新出现的事，合成一条任务（每个课题每次最多一条）：
- lab 完成、lab 受阻（连续几次续跑真的失败；额度用尽不算，见 project.record_attempt）、任务书等你过目、agent 向你提问。
  等数值的 lab 一直是 running，不会提醒；arXiv 候选每天都有，不提醒。
- 已经在网页上看过的（标了已读）不再提醒。
- 第一次运行只记下现状、不补发旧事；发送失败的事留着，下次一起再发。

发送（[notify].via）：
- "codex"（默认）：后台跑一次 `codex exec`，让它用你在 Codex 里授权好的 TickTick 应用，在 [notify].list 清单里建这一条任务
  （标题、内容原样，日期为现在、带一个准时提醒），并只回报新任务的 id；拿到 id 才算发成功。模型与强度见 codex_model / codex_effort。
- "shortcut"：`shortcuts run <[notify].shortcut> --input-path <文本文件>`，文本第一行是标题，其余是描述
  （快捷指令里一个 TickTick「添加任务」动作，清单、提醒在快捷指令里设）。
标题一律以「(Dashboard)」开头。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import config, pnotes

PREFIX = "(Dashboard)"
EVENTS = ("lab_done", "lab_blocked", "brief_review", "agent_question")
_LAB_EVENT = {"done": "lab_done", "blocked": "lab_blocked", "awaiting_review": "brief_review"}
_WHAT = {"lab_done": "完成", "lab_blocked": "受阻（连续几次续跑失败，等你处理）", "brief_review": "任务书等你过目"}


def _cfg(project) -> dict:
    c = config.load(Path(project.root)).get("notify") or {}
    return {"enabled": bool(c.get("enabled", True)), "hours": float(c.get("hours", 3) or 3),
            "via": str(c.get("via") or "codex"), "list": str(c.get("list") or "research"),
            "codex_model": str(c.get("codex_model") or "gpt-6.1-sol"), "codex_effort": str(c.get("codex_effort") or "high"),
            "shortcut": str(c.get("shortcut") or "rd 提醒"), "events": [e for e in (c.get("events") or EVENTS) if e in EVENTS]}


def _state_path(project) -> Path:
    return Path(project.root) / ".dashboard" / "notify.json"


def _load(project) -> dict | None:
    try:
        return json.loads(_state_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(project, state: dict) -> None:
    p = _state_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(".notify.json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _snapshot(project) -> tuple[dict, dict, dict]:
    """(各 lab 的状态, 开着的 agent 提问 {id: 标题}, 各 lab 的 Doc)。"""
    labs = {d.id: d for d in project.labs()}
    questions = {d.id: d.title for d in project.discussions()
                 if d.meta.get("status") == "open" and d.meta.get("asked_by") == "agent" and not d.extra.get("review_only")}
    return {i: str(d.meta.get("status") or "") for i, d in labs.items()}, questions, labs


def _first_sentence(text: str, n: int = 90) -> str:
    s = re.sub(r"[*`#>]", "", " ".join(str(text or "").split()))
    s = re.split(r"(?<=[。；！？])", s)[0]
    return s if len(s) <= n else s[: n - 1] + "…"


def _event(project, kind: str, ident: str, labs: dict, questions: dict) -> dict:
    base = pnotes.dashboard_url(project)
    if kind == "agent_question":
        return {"kind": kind, "id": ident, "line": f"agent 向你提问：{questions.get(ident, ident)}", "url": f"{base}/#/discussion/{ident}"}
    d = labs.get(ident)
    short = (d.extra.get("short") or d.title) if d else ident
    no = (re.match(r"\d+", ident) or [ident])[0]
    line = f"lab {no} {_WHAT[kind]}：{short}"
    if kind == "lab_done" and d is not None and d.extra.get("answer"):
        line += f" —— {_first_sentence(d.extra['answer'])}"
    return {"kind": kind, "id": ident, "line": line, "url": f"{base}/#/labs/{ident}"}


def check(project, *, save: bool = True) -> list[dict]:
    """和上次相比新出现的事（加上上次没发出去的）。第一次运行只记下现状，返回空。"""
    cfg = _cfg(project)
    statuses, questions, labs = _snapshot(project)
    state = _load(project)
    if state is None:
        if save:
            _save(project, {"labs": statuses, "questions": sorted(questions), "pending": [], "since": time.strftime("%Y-%m-%d %H:%M")})
        return []
    new: list[tuple[str, str]] = [(p["kind"], p["id"]) for p in state.get("pending", [])]
    old_labs = state.get("labs", {})
    for i, st in statuses.items():
        kind = _LAB_EVENT.get(st)
        if kind and old_labs.get(i) != st and kind in cfg["events"]:
            d = labs[i]
            if kind != "brief_review" and not project.is_unread("lab", i, d.mtime):
                continue  # 已经在网页上看过了
            new.append((kind, i))
    if "agent_question" in cfg["events"]:
        new += [("agent_question", q) for q in questions if q not in set(state.get("questions", []))]
    seen, events = set(), []
    for kind, ident in new:
        still = (kind == "agent_question" and ident in questions) or (kind != "agent_question" and _LAB_EVENT.get(statuses.get(ident, "")) == kind)
        if (kind, ident) in seen or not still:
            continue  # 重复的，或已经不是那个状态了（比如任务书已批准）
        seen.add((kind, ident))
        events.append(_event(project, kind, ident, labs, questions))
    if save:
        state.update({"labs": statuses, "questions": sorted(questions), "pending": [{"kind": e["kind"], "id": e["id"]} for e in events]})
        _save(project, state)
    return events


def message(project, events: list[dict]) -> tuple[str, str]:
    """(标题, 描述)。一件事：标题就是那件事；几件：「N 件事等你」，描述里逐条列出，每条带网页链接。"""
    name = str(config.load(Path(project.root))["project"].get("name") or Path(project.root).name)
    if len(events) == 1:
        title = f"{PREFIX} {name}：{events[0]['line']}"
    else:
        title = f"{PREFIX} {name}：{len(events)} 件事等你"
    body = "\n".join(f"· {e['line']}\n  {e['url']}" for e in events)
    return " ".join(title.split())[:200], body


CODEX_PROMPT = """用 TickTick 应用在我的「{list}」清单里新建**一条**任务，然后结束。要求：
- 标题（原样，一字不改）：{title}
- 内容（原样，一字不改，保留换行）：
<<<
{body}
>>>
- 日期：{now}（时区 {tz}），不是全天任务；加一个准时提醒（到点就提醒）。
- 只建这一条：不要改、删、完成任何已有任务，不要建别的清单。清单名对不上时先列出清单，找名字一样（不分大小写）的那个；找不到就什么也别建。
- 最后一行只输出：TASK_ID: <新任务的 id>；没建成就输出：FAILED: <原因>"""


TICKTICK_APP = "asdk_app_69ddbaba3fb48191a825f22c21b0599d"  # ChatGPT 应用目录里 TickTick（Appest Inc）的 id


def _tz() -> str:
    try:
        return os.readlink("/etc/localtime").split("zoneinfo/")[-1]
    except OSError:
        return time.strftime("%Z")


def send(project, title: str, body: str) -> tuple[bool, str]:
    cfg = _cfg(project)
    return (_send_codex if cfg["via"] == "codex" else _send_shortcut)(project, cfg, title, body)


def _send_codex(project, cfg: dict, title: str, body: str) -> tuple[bool, str]:
    """后台跑一次 codex exec 建任务；回报里有 TASK_ID 才算成。"""
    from .codex import find_codex
    codex, why = find_codex()
    if not codex:
        return False, f"找不到 codex：{why}"
    prompt = CODEX_PROMPT.format(list=cfg["list"], title=title, body=body, now=time.strftime("%Y-%m-%dT%H:%M:%S%z"), tz=_tz())
    with tempfile.TemporaryDirectory(prefix="rd-notify-") as tmp:
        out = Path(tmp) / "last.txt"
        # 非交互的 codex exec 不会弹审批，写入类工具默认被拒：只在这一次调用里放行 TickTick 应用的工具（不改全局设置；
        # 提示词规定只建一条）。按单个工具放行（apps.<id>.tools.<名>.approval_mode）在 0.169 上对不上工具名，所以按应用放行
        cmd = [str(codex), "exec", "--skip-git-repo-check", "-C", tmp, "-s", "read-only", "-m", cfg["codex_model"],
               "-c", f'model_reasoning_effort="{cfg["codex_effort"]}"',
               "-c", f'apps.{TICKTICK_APP}.default_tools_approval_mode="approve"', "-o", str(out), prompt]
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, repr(e)
        last = out.read_text(encoding="utf-8").strip() if out.exists() else ""
    m = re.search(r"TASK_ID:\s*(\S+)", last)
    if r.returncode == 0 and m:
        return True, m.group(1)
    tail = last or (r.stdout + r.stderr)[-500:]
    return False, " ".join(tail.split())[:400] or f"codex 退出码 {r.returncode}"


def _send_shortcut(project, cfg: dict, title: str, body: str) -> tuple[bool, str]:
    """跑快捷指令：输入文本第一行是标题，其余是描述。"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(title + "\n" + body)
        path = f.name
    try:
        r = subprocess.run(["/usr/bin/shortcuts", "run", cfg["shortcut"], "--input-path", path],
                           capture_output=True, text=True, timeout=90)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, repr(e)
    finally:
        os.unlink(path)


def run_once(project) -> dict:
    """看一次，有新事就发一条；发成功才把它们从待发里清掉。"""
    events = check(project)
    if not events:
        return {"sent": 0}
    title, body = message(project, events)
    ok, out = send(project, title, body)
    if ok:
        state = _load(project) or {}
        state["pending"] = []
        state["last_sent"] = time.strftime("%Y-%m-%d %H:%M")
        _save(project, state)
        return {"sent": len(events), "title": title}
    return {"sent": 0, "error": out or "没有发出去", "title": title}


def test(project) -> tuple[bool, str]:
    name = str(config.load(Path(project.root))["project"].get("name") or Path(project.root).name)
    return send(project, f"{PREFIX} {name}：测试提醒，看到这条说明通了", "这条可以直接删掉。之后 lab 完成、受阻、任务书等你过目、agent 提问时会在这里提醒你。")
