"""`rd` 命令行。子命令：install / init / update / serve / run / tick / arxiv-scan / free-cores / jobs / scheduler / doctor"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import TEMPLATE_ROOT, config

SKILL_HOMES = [Path("~/.claude/skills").expanduser(), Path("~/.codex/skills").expanduser(), Path("~/.agents/skills").expanduser()]
REQUIRED_SKILLS = ["baby-steps-report"]


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
    # 依赖的外部 skill
    for name in REQUIRED_SKILLS:
        ok = any((h / name / "SKILL.md").exists() for h in SKILL_HOMES)
        print(f"  依赖 skill {name}: {'已安装' if ok else '缺失！请 git clone 后软链接到 ~/.claude/skills/'}")
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
            out.write_text(text.replace("{{PROJECT_NAME}}", name).replace("{{DATE}}", _today()), encoding="utf-8")
        else:
            shutil.copy2(src, out)
    _sync_rules(dst)
    config.write_machine(dst, claude_bin=config.find_claude_bin() or "")
    if not (dst / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=dst)
        subprocess.run(["git", "add", "-A"], cwd=dst)
        subprocess.run(["git", "commit", "-q", "-m", "rd init: 课题骨架"], cwd=dst, capture_output=True)
    print(f"已创建课题 {name}: {dst}\n下一步：填 PROJECT.md 和 config.toml，然后 rd serve {dst}")


def _sync_rules(dst: Path):
    shutil.copy2(TEMPLATE_ROOT / "AGENTS.md", dst / "AGENTS.md")
    (dst / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")


def cmd_update(args):
    dst = Path(args.path).expanduser().resolve()
    _sync_rules(dst)
    config.write_machine(dst, claude_bin=config.find_claude_bin() or "")
    print(f"已刷新 {dst}/AGENTS.md、CLAUDE.md 和本机配置")


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
    res = run_pending(proj, only=args.only, dry_run=args.dry_run)
    if not res:
        print("没有待处理项")
    for r in res:
        print(json.dumps({k: v for k, v in r.items() if k in ("kind", "id", "status", "prompt")}, ensure_ascii=False))


def cmd_arxiv(args):
    from .arxiv import scan
    proj = _project(args.path)
    res = scan(proj, dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if not args.dry_run and res.get("written") and not args.no_agent:
        from .runner import Runner
        n = len(res["written"])
        prompt = (f"references/inbox/ 里刚新增 {n} 篇 arXiv 候选（status: pending，reason 为空）。请按 rd-arxiv skill："
                  f"读 PROJECT.md 和 wiki/index.md，只凭摘要判断每篇和本课题的关系，给每篇写一两句「为什么可能相关」到 reason 字段"
                  f"和正文对应小节（注明仅基于摘要）；明显无关的直接把 status 改为 rejected 并写明理由；"
                  f"最多保留 {config.load(proj.root)['arxiv']['max_per_day']} 篇 pending 等用户审批。不要下载 PDF。")
        Runner(proj).run(prompt, kind="arxiv_reason", label="arxiv-reason")


# ---------- cores / jobs ----------
def cmd_free_cores(args):
    from . import cores
    st = cores.status(Path(args.path).expanduser().resolve())
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=1))
    else:
        print(st["advice"])
        for j in st["jobs"]:
            print(f"  - {j['label']}: {j['cores']} 核 (pid {j.get('pid')})")


def cmd_jobs(args):
    from . import cores
    proj = Path(args.path).expanduser().resolve()
    if args.action == "claim":
        jid = cores.claim(proj, int(args.cores), args.label or "job", pid=args.pid)
        print(jid)
    elif args.action == "release":
        print("released" if cores.release(proj, args.id) else "not found")
    else:
        print(json.dumps(cores.list_jobs(proj), ensure_ascii=False, indent=1))


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
    p = sub.add_parser("init", help="新建课题目录"); p.add_argument("path"); p.add_argument("--name"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("update", help="刷新课题里的 AGENTS.md"); p.add_argument("path"); p.set_defaults(fn=cmd_update)
    p = sub.add_parser("serve", help="启动 dashboard"); p.add_argument("path"); p.add_argument("--host"); p.add_argument("--port", type=int); p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("run", help="立刻让 agent 干一件事"); p.add_argument("path"); p.add_argument("--prompt", "-p"); p.add_argument("--label"); p.add_argument("--model"); p.add_argument("--effort"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("tick", help="处理所有待办（回答/审批/升级）"); p.add_argument("path"); p.add_argument("--only"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_tick)
    p = sub.add_parser("arxiv-scan", help="扫 arXiv 新文章"); p.add_argument("path"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--no-agent", action="store_true"); p.set_defaults(fn=cmd_arxiv)
    p = sub.add_parser("free-cores", help="现在还能用几个核"); p.add_argument("path", nargs="?", default="."); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_free_cores)
    p = sub.add_parser("jobs", help="作业登记"); p.add_argument("action", choices=["claim", "release", "list"]); p.add_argument("path", nargs="?", default="."); p.add_argument("--cores", default=1); p.add_argument("--label"); p.add_argument("--pid", type=int); p.add_argument("--id"); p.set_defaults(fn=cmd_jobs)
    p = sub.add_parser("scheduler", help="launchd 定时任务"); p.add_argument("action", choices=["install", "uninstall", "status"]); p.add_argument("path"); p.set_defaults(fn=cmd_scheduler)
    p = sub.add_parser("doctor", help="检查断链、缺节、状态"); p.add_argument("path"); p.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except FileNotFoundError as e:
        sys.exit(f"错误：{e}\n（提示：本机是 {config.hostname()}，课题目录要在当前这台机器上存在；demo 在 studio 的 ~/doc_unsyn/rd_demo，笔记本上的是模板目录下的 demo_project）")
    except RuntimeError as e:
        sys.exit(f"错误：{e}")


if __name__ == "__main__":
    main()
