"""`rd` 命令行。子命令：install / init / update / serve / run / tick / arxiv-scan / free-cores / jobs / scheduler / doctor"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import TEMPLATE_ROOT, config, registry

SKILL_HOMES = [Path("~/.claude/skills").expanduser(), Path("~/.codex/skills").expanduser(), Path("~/.agents/skills").expanduser()]
OPTIONAL_SKILLS = ["baby-steps-report"]  # 只在用户明确要双语 LaTeX 报告时用；日常推导走 rd-notes


def _project(path: str):
    from .project import Project
    return Project(Path(path))


# ---------- install（每台机器一次） ----------
def cmd_install(args):
    venv = TEMPLATE_ROOT / ".venv"
    py = venv / "bin" / "python"
    if not py.exists():
        print(f"创建 venv: {venv}")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    print("安装依赖 …")
    subprocess.check_call([str(py), "-m", "pip", "install", "-q", "-e", f"{TEMPLATE_ROOT}[dev]"])
    # skills：软链接到各个 agent 的用户级 skills 目录
    src = TEMPLATE_ROOT / "skills"
    for home in SKILL_HOMES:
        if not home.parent.exists():
            continue
        home.mkdir(parents=True, exist_ok=True)
        for sk in sorted(src.iterdir()):
            if not (sk / "SKILL.md").exists():
                continue
            dst = home / sk.name
            if dst.is_symlink() or dst.exists():
                if dst.is_symlink() and dst.resolve() == sk.resolve():
                    continue
                print(f"  跳过 {dst}（已存在且不是指向模板的链接）")
                continue
            dst.symlink_to(sk)
            print(f"  链接 {dst} → {sk}")
    # 可选的外部 skill
    for name in OPTIONAL_SKILLS:
        ok = any((h / name / "SKILL.md").exists() for h in SKILL_HOMES)
        print(f"  可选 skill {name}: {'已安装' if ok else '未安装（只在用户要双语 LaTeX 报告时需要）'}")
    cb = config.find_claude_bin()
    print(f"  claude: {cb or '未找到（自动运行需要）'}")
    print("完成。接下来: rd init <课题目录> --name <课题名>")


# ---------- init / update ----------
def cmd_init(args):
    dst = Path(args.path).expanduser().resolve()
    name = args.name or dst.name
    tpl = TEMPLATE_ROOT / "template"
    if (dst / "config.toml").exists():
        sys.exit(f"{dst} 已经是课题目录；要刷新规则请用 rd update")
    dst.mkdir(parents=True, exist_ok=True)
    for src in tpl.rglob("*"):
        rel = src.relative_to(tpl)
        out = dst / rel
        if src.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if out.exists():
            continue
        text = src.read_text(encoding="utf-8") if src.suffix in (".md", ".toml", ".txt", "") or src.name.startswith(".") else None
        if text is not None:
            text = text.replace("{{PROJECT_NAME}}", name).replace("{{DATE}}", _today())
            if src.name == "config.toml":
                port = int(args.port) if args.port else registry.free_port(exclude=dst)
                text = text.replace("port = 8010", f"port = {port}")
            out.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, out)
    _sync_rules(dst)
    config.write_machine(dst, claude_bin=config.find_claude_bin() or "")
    registry.register(dst, name, int(config.load(dst)["server"]["port"]))
    if not (dst / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=dst)
        subprocess.run(["git", "add", "-A"], cwd=dst)
        subprocess.run(["git", "commit", "-q", "-m", "rd init: 课题骨架"], cwd=dst, capture_output=True)
    print(f"已创建课题 {name}: {dst}\n下一步：填 PROJECT.md 和 config.toml，然后 rd serve {dst}")


def _sync_rules(dst: Path):
    shutil.copy2(TEMPLATE_ROOT / "AGENTS.md", dst / "AGENTS.md")
    # 模板新增的顶层文件（如 STATUS.md）补进旧课题；已有的不动
    for name in ("STATUS.md",):
        src, out = TEMPLATE_ROOT / "template" / name, dst / name
        if src.exists() and not out.exists():
            out.write_text(src.read_text(encoding="utf-8").replace("{{DATE}}", _today()).replace("{{PROJECT_NAME}}", dst.name), encoding="utf-8")
    claude_md = dst / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text("@AGENTS.md\n", encoding="utf-8")
    elif "@AGENTS.md" not in claude_md.read_text(encoding="utf-8"):
        # 用户自己的 CLAUDE.md 保留，只补一行引用
        with claude_md.open("a", encoding="utf-8") as f:
            f.write("\n@AGENTS.md\n")


def cmd_update(args):
    dst = Path(args.path).expanduser().resolve()
    _sync_rules(dst)
    config.write_machine(dst, claude_bin=config.find_claude_bin() or "")
    print(f"已刷新 {dst}/AGENTS.md、CLAUDE.md 和本机配置（缺的 STATUS.md 已补）")


def _today():
    import datetime
    return datetime.date.today().isoformat()


# ---------- serve ----------
def cmd_serve(args):
    import uvicorn
    from .server import create_app
    proj = _project(args.path)
    cfg = config.load(proj.root)
    host = args.host or cfg["server"]["host"]
    port = args.port or int(cfg["server"]["port"])
    taken = registry.port_taken(port, exclude=proj.root)
    if taken:
        sys.exit(f"端口 {port} 已被「{taken}」占用；用 --port 指定别的端口，或 rd projects 看本机课题")
    registry.register(proj.root, cfg["project"]["name"], port)
    print(f"dashboard: http://localhost:{port}  （课题 {cfg['project']['name']}）")
    uvicorn.run(create_app(proj), host=host, port=port, log_level="warning")


# ---------- run / tick / arxiv ----------
def cmd_run(args):
    from .runner import Runner
    proj = _project(args.path)
    prompt = args.prompt or sys.stdin.read()
    meta = Runner(proj).run(prompt, kind="manual", label=args.label or "manual", model=args.model, effort=args.effort,
                            on_line=lambda s: print(s, end=""))
    print(json.dumps({k: meta[k] for k in ("id", "status", "model", "started", "ended")}, ensure_ascii=False))


def cmd_tick(args):
    from .tick import run_pending
    proj = _project(args.path)
    pause = proj.pause_info()
    if pause and not args.force:
        print(f"⏸ Claude 额度用尽，暂停派发到 {pause['until_str']}（{pause['reason']}）；--force 可无视")
    res = run_pending(proj, only=args.only, dry_run=args.dry_run, force=args.force)
    if not res:
        print("没有待处理项")
    for r in res:
        print(json.dumps({k: v for k, v in r.items() if k in ("kind", "id", "status", "prompt", "last_status", "retry_in_s", "reason", "model", "effort", "fails")}, ensure_ascii=False))


def cmd_digest(args):
    from .tick import run_digest
    proj = _project(args.path)
    # server 在跑时它自己的定时器会消化；launchd 兜底只在 server 不在时动手，避免两边同时跑
    if not args.force and not args.dry_run:
        cfg = config.load(proj.root)
        if registry.port_listening(int(cfg["server"]["port"])):
            print("dashboard 在运行，由它的定时器统一消化；--force 可强制现在跑")
            return
    res = run_digest(proj, dry_run=args.dry_run)
    if res is None:
        print("没有待消化的回答")
    else:
        print(json.dumps({k: v for k, v in res.items() if k in ("kind", "threads", "id", "status", "prompt")}, ensure_ascii=False))


def cmd_arxiv(args):
    from .arxiv import scan
    proj = _project(args.path)
    res = scan(proj, dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if not args.dry_run and res.get("written") and not args.no_agent:
        from .runner import Runner
        from .tick import model_for
        n = len(res["written"])
        cfg = config.load(proj.root)
        prompt = (f"references/inbox/ 里刚新增 {n} 篇 arXiv 候选（status: pending，reason 为空）。请按 rd-arxiv skill："
                  f"读 PROJECT.md 和 wiki/index.md，只凭摘要判断每篇和本课题的关系，给每篇写一两句「为什么可能相关」到 reason 字段"
                  f"和正文对应小节（注明仅基于摘要）；明显无关的直接把 status 改为 rejected 并写明理由；"
                  f"最多保留 {cfg['arxiv']['max_per_day']} 篇 pending 等用户审批。不要下载 PDF。"
                  f"这是文书任务，AGENTS.md §0 的通读对它放宽：除 PROJECT.md、STATUS.md、wiki/index.md 和候选文件本身外，不要通读 wiki 页、卡片、lab notes 或 log。")
        model, effort = model_for(cfg, "arxiv_reason")
        Runner(proj).run(prompt, kind="arxiv_reason", label="arxiv-reason", model=model, effort=effort)


# ---------- cores / jobs ----------
def cmd_free_cores(args):
    from . import cores
    proj = Path(args.path).expanduser().resolve() if args.path else None
    st = cores.status(proj)
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=1))
    else:
        print(st["advice"])
        for j in st["jobs"]:
            print(f"  - [{j.get('project', '')}] {j['label']}: {j['cores']} 核 (pid {j.get('pid')})")


def cmd_jobs(args):
    from . import cores
    proj = Path(args.path).expanduser().resolve() if args.path else None
    if args.action == "claim":
        jid = cores.claim(proj, int(args.cores), args.label or "job", pid=args.pid)
        print(jid)
    elif args.action == "release":
        print("released" if cores.release(args.id) else "not found")
    else:
        print(json.dumps(cores.list_jobs(), ensure_ascii=False, indent=1))


def cmd_projects(args):
    rows = registry.list_projects()
    if not rows:
        print("本机还没有登记的课题（rd init / rd serve / rd scheduler install 会登记）")
        return
    ms = registry.machine_settings()
    print(f"本机 {config.hostname()}：同时最多 {ms['max_agents']} 个 agent，留 {ms['reserve_cores']} 核（~/.rd/machine.toml）")
    for r in rows:
        state = "在跑" if r["listening"] else ("目录不存在" if not r["exists"] else "未启动")
        print(f"  {r['name']:<24} :{r['port']}  {state:<6} {r['path']}")


# ---------- scheduler ----------
def cmd_scheduler(args):
    from . import scheduler
    proj = Path(args.path).expanduser().resolve()
    fn = {"install": scheduler.install, "uninstall": scheduler.uninstall, "status": scheduler.status}[args.action]
    for line in fn(proj):
        print(line)


# ---------- doctor ----------
def cmd_doctor(args):
    proj = _project(args.path)
    problems = []
    table = proj.link_table()
    for d in proj.wiki_pages() + proj.cards():
        for t in d.extra.get("links", []):
            if t not in table:
                problems.append(f"断链 [[{t}]] in {d.path}")
    for d in proj.cards():
        for sec in ("## 与本课题的联系", "## 内容总结"):
            if sec not in d.body:
                problems.append(f"卡片缺少「{sec[3:]}」: {d.path}")
        if d.meta.get("read_depth") not in ("abstract", "skim", "full"):
            problems.append(f"卡片 read_depth 未填或非法: {d.path}")
    for d in proj.labs():
        if d.meta.get("status") == "done" and not d.extra.get("has_report"):
            problems.append(f"lab 已完成但没有 report.md: {d.path}")
    for d in proj.ideas():
        p = d.meta.get("parent")
        if p and p not in {x.id for x in proj.ideas()}:
            problems.append(f"idea parent 不存在: {d.path} → {p}")
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("没有发现问题")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rd", description="research-dashboard")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("install", help="本机安装：venv、依赖、skills 软链接").set_defaults(fn=cmd_install)
    p = sub.add_parser("init", help="新建课题目录（已有文件一律保留）"); p.add_argument("path"); p.add_argument("--name"); p.add_argument("--port", type=int, help="dashboard 端口，默认 8010"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("update", help="刷新课题里的 AGENTS.md"); p.add_argument("path"); p.set_defaults(fn=cmd_update)
    p = sub.add_parser("serve", help="启动 dashboard"); p.add_argument("path"); p.add_argument("--host"); p.add_argument("--port", type=int); p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("run", help="立刻让 agent 干一件事"); p.add_argument("path"); p.add_argument("--prompt", "-p"); p.add_argument("--label"); p.add_argument("--model"); p.add_argument("--effort"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("tick", help="处理所有待办（回答/审批/升级）"); p.add_argument("path"); p.add_argument("--only"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--force", action="store_true", help="忽略失败退避，立刻重试"); p.set_defaults(fn=cmd_tick)
    p = sub.add_parser("digest", help="统一消化所有已回答的讨论（默认每五小时由 dashboard 自动做）"); p.add_argument("path"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_digest)
    p = sub.add_parser("arxiv-scan", help="扫 arXiv 新文章"); p.add_argument("path"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--no-agent", action="store_true"); p.set_defaults(fn=cmd_arxiv)
    p = sub.add_parser("free-cores", help="现在还能用几个核（本机所有课题合计）"); p.add_argument("path", nargs="?"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_free_cores)
    p = sub.add_parser("jobs", help="数值作业登记（机器级）"); p.add_argument("action", choices=["claim", "release", "list"]); p.add_argument("path", nargs="?"); p.add_argument("--cores", default=1); p.add_argument("--label"); p.add_argument("--pid", type=int); p.add_argument("--id"); p.set_defaults(fn=cmd_jobs)
    p = sub.add_parser("projects", help="本机登记的课题、端口和运行状态"); p.set_defaults(fn=cmd_projects)
    p = sub.add_parser("scheduler", help="launchd 定时任务"); p.add_argument("action", choices=["install", "uninstall", "status"]); p.add_argument("path"); p.set_defaults(fn=cmd_scheduler)
    p = sub.add_parser("doctor", help="检查断链、缺节、状态"); p.add_argument("path"); p.set_defaults(fn=cmd_doctor)
    from .codex import add_parser as _codex_parser
    _codex_parser(sub)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except FileNotFoundError as e:
        sys.exit(f"错误：{e}\n（提示：本机是 {config.hostname()}，课题目录要在当前这台机器上存在；demo 在 studio 的 ~/doc_unsyn/rd_demo，笔记本上的是模板目录下的 demo_project）")
    except RuntimeError as e:
        sys.exit(f"错误：{e}")


if __name__ == "__main__":
    main()
