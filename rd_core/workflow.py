"""收尾门槛：`rd finish <课题目录> <lab>` 核对**当前版本**的文件有没有独立通过的审核，再把 lab 标为 done。

把审核绑在被发布的文件版本上，而不是 agent 自己改一个状态：
- 推导审核：某次 `audit` 作业（--kind audit）声明的源文件至少含 notes.md，作业结束后源文件哈希未变，
  产出的报告 frontmatter kind: derivation、verdict: pass、不严谨与改变结论均为 0（有 typo 则须 handled: true），
  且报告 frontmatter 与作业结束时记下的一致（没被手改）。
- 薄层：report.md 必须由 `write` 作业用 --expect 声明产出；写作作业声明的所有输出都算薄层。
- 一致性：某次 `consistency` 作业声明的源文件覆盖 notes、handoff、report 和全部薄层输出，哈希未变，报告 verdict: pass。
- doctor 无问题。
源文件再改动，旧报告自动过期（哈希不匹配），得重新审。"""

from __future__ import annotations

import json
from pathlib import Path

from . import config, fm
from .codex import REVIEW_KINDS, _hash, done_jobs

REQUIRED = ("notes.md", "handoff.md", "report.md")


def _report_passes(root: Path, job: dict, outcome: dict, report: str) -> tuple[bool, str]:
    try:
        meta, _ = fm.read(root / report)
    except (OSError, ValueError):
        return False, f"报告不存在或无法读取: {report}"
    want_kind = REVIEW_KINDS[job["kind"]]
    if job["kind"] == "audit" and meta.get("kind") == "code":
        return False, "代码审计不能代替推导审核"
    if meta.get("kind") != want_kind:
        return False, f"{report} 的 kind 是 {meta.get('kind')}，不是 {want_kind}"
    recorded = (outcome.get("review_verdicts") or {}).get(report)
    if recorded is None:
        return False, f"{report} 没有作业结束时的 verdict 记录（旧作业或未用 --expect 声明）"
    current = {k: meta.get(k) for k in ("kind", "verdict", "counts", "handled")}
    # 处理过的报告允许把 handled 从 false 改成 true；其余字段不能变
    if any(recorded.get(k) != current.get(k) for k in ("kind", "verdict", "counts")):
        return False, f"{report} 的 frontmatter 在作业结束后被改过"
    if meta.get("verdict") != "pass":
        return False, f"{report} 的 verdict 是 {meta.get('verdict')}，不是 pass"
    counts = meta.get("counts") or {}
    if any(int(counts.get(k, 0) or 0) for k in ("不严谨", "改变结论")):
        return False, f"{report} 还有不严谨/改变结论的发现"
    if int(counts.get("typo", 0) or 0) and not meta.get("handled"):
        return False, f"{report} 的 typo 还没标 handled"
    return True, ""


def review_evidence(root: Path, lab: str) -> dict:
    """本 lab 成功结束的作业，按种类分：{'audit': [(job, outcome)...], 'consistency': [...], 'write': [...]}。"""
    out: dict[str, list] = {"audit": [], "consistency": [], "write": []}
    for job, oc in done_jobs(root):
        if job.get("lab") == lab and job.get("kind") in out:
            out[job["kind"]].append((job, oc))
    return out


def completion_errors(root: Path, lab: str, project=None) -> list[str]:
    root = Path(root).resolve()
    lab_dir = (root / "labs" / lab).resolve()
    if lab_dir.parent != (root / "labs").resolve() or not (lab_dir / "brief.md").is_file():
        return ["非法的 lab 路径或没有 brief.md"]
    cfg = config.load(root)
    errors: list[str] = []
    base = f"labs/{lab}/"
    required = {base + n for n in REQUIRED}
    errors += [f"缺少 {p}" for p in sorted(required) if not (root / p).is_file()]
    ev = review_evidence(root, lab)
    thin: set[str] = set()
    for job, _ in ev["write"]:
        thin |= set(job.get("expected") or [])
    if base + "report.md" not in thin:
        errors.append("薄层写作尚未通过独立写作作业完成（codex-write.sh 启动时要用 --expect 声明每个输出文件，含 report.md）")
    missing_thin = sorted(p for p in thin if not (root / p).is_file())
    errors += [f"写作作业声明的输出不存在: {p}" for p in missing_thin]
    required |= thin
    checks = [
        ("audit", bool(cfg["auditor"].get("auto_derivation", True)), {base + "notes.md"}, "推导审核"),
        ("consistency", bool(cfg["auditor"].get("auto_consistency", True)), required, "薄层一致性检查"),
    ]
    for kind, enabled, targets, zh in checks:
        if not enabled:
            continue
        found, why = False, []
        for job, oc in ev[kind]:
            hashes = job.get("source_hashes") or {}
            if not targets.issubset(hashes):
                why.append(f"{job['name']}: 声明的源文件没覆盖 {sorted(targets - set(hashes))}")
                continue
            if _hash(root, hashes) != hashes:
                why.append(f"{job['name']}: 审核后源文件又改过（报告已过期）")
                continue
            for report in job.get("expected") or []:
                ok, reason = _report_passes(root, job, oc, report)
                if ok:
                    found = True
                    break
                why.append(f"{job['name']}: {reason}")
            if found:
                break
        if not found:
            hint = "；".join(why[-3:]) if why else "还没有这类作业"
            errors.append(f"{zh}: 没有覆盖当前文件版本的通过报告（{hint}）。实质修改后要对当前版本复核")
    if project is not None:
        errors += doctor_problems(project)
    else:
        from .project import Project
        errors += doctor_problems(Project(root))
    return errors


def doctor_problems(project) -> list[str]:
    """`rd doctor` 的检查：断链、卡片缺节、read_depth、done 却没 report、idea parent 不存在。"""
    problems = []
    table = project.link_table()
    for d in project.wiki_pages() + project.cards():
        for t in d.extra.get("links", []):
            if t not in table:
                problems.append(f"断链 [[{t}]] in {d.path}")
    for d in project.cards():
        for sec in ("## 与本课题的联系", "## 内容总结"):
            if sec not in d.body:
                problems.append(f"卡片缺少「{sec[3:]}」: {d.path}")
        if d.meta.get("read_depth") not in ("abstract", "skim", "full"):
            problems.append(f"卡片 read_depth 未填或非法: {d.path}")
    for d in project.labs():
        if d.meta.get("status") == "done" and not d.extra.get("has_report"):
            problems.append(f"lab 已完成但没有 report.md: {d.path}")
    ids = {x.id for x in project.ideas()}
    for d in project.ideas():
        p = d.meta.get("parent")
        if p and p not in ids:
            problems.append(f"idea parent 不存在: {d.path} → {p}")
    return problems


def finish(root: Path, lab: str) -> dict:
    """全部门槛通过才把 brief.md 的 status 改为 done；否则抛 RuntimeError（每行一个原因）。"""
    from .project import Project, now_str
    root = Path(root).resolve()
    project = Project(root)
    errors = completion_errors(root, lab, project)
    if errors:
        raise RuntimeError("\n".join(errors))
    meta = fm.update(root / "labs" / lab / "brief.md", status="done", finished=now_str())
    project.append_log("agent", f"lab {lab} 通过收尾门槛（推导审核、薄层一致性检查、doctor 均覆盖当前版本），status: done", f"labs/{lab}/brief.md")
    return {"lab": lab, "status": "done", "pending_review": meta.get("pending_review")}
