"""把"待处理工作项"变成一次次 agent 运行。
触发时机：dashboard 上的用户动作之后立刻；dashboard 的文件监视每 watch_seconds 发现新待办时立刻；
launchd 每 tick_minutes 兜底一次（dashboard 没开时）。失败的项在 retry_minutes 内不重试。"""

from __future__ import annotations

import time

from . import config, fm
from .project import Project
from .runner import Runner

PROMPTS = {
    "digest_answer": (
        "用户回答了讨论 {path}（标题「{title}」）。请按 rd-discussion skill 消化这个回答：写出结论与后续，"
        "把受影响的 wiki、卡片、idea 的「当前回答」、STATUS.md、lab 任务书同步更新（改写，不追加）；如果某个 lab 的状态是 waiting_answer 且正等这个回答，"
        "把它改回 approved 并继续执行该任务（按 rd-lab skill）。完成后把讨论状态改为 digested（问题彻底解决则 resolved）。"
    ),
    "answer_user_question": (
        "用户在 {path} 向你提了一个问题（标题「{title}」）。请认真回答：先读 PROJECT.md、相关 wiki 和卡片，"
        "必要时做推导或小计算。把回答写进该文件的「## 回答」一节，status 改为 digested；"
        "如果回答带来了新的理解，更新 wiki；如果你反过来需要用户裁决，再新开一个讨论。"
    ),
    "ingest_reference": (
        "用户批准了 arXiv 候选 {path}（{title}）。请按 rd-reference skill：下载 PDF 到 references/raw/，"
        "通读全文，建立 references/cards/<arxiv id>.md 卡片（read_depth 如实填写），把候选的 status 改为 ingested，"
        "并把它和已有 wiki 概念互链；如果它改变了对课题的理解，更新相关 wiki 页。"
    ),
    "run_lab": (
        "任务书 labs/{id}/brief.md（「{title}」）已被批准。请按 rd-lab skill 执行：先把 status 改为 running，"
        "按任务书做事，推导与讲解写 notes.md（rd-notes skill，中文 markdown，PDF 和英文版按需），数值前先运行 `rd free-cores` 并登记作业，"
        "大数据放 data_root 并留 DATA.md。收尾按 rd-lab C 节：厚层齐 → 写 handoff.md → 按 rd-writer skill 把薄层交给 Codex 写"
        "（report.md、受影响的 wiki 页、idea 当前回答、STATUS.md），只做机械检查不改它的文字 → 卡片两三句、index、log.md，status 改为 done；"
        "遇到必须由用户裁决的问题，按无人值守规则写讨论并把 status 改为 waiting_answer。"
    ),
    "revise_brief": (
        "用户在 dashboard 上对任务书 labs/{id}/brief.md（「{title}」）提了意见，见文末「## 用户意见」里 comments_pending 之后的新条目。"
        "请按 rd-lab skill 第 A.6 条处理：通读全部意见，按意见修改目标、步骤、交付物、特别要求（改写，不留两套），"
        "在每条意见正下方写「**agent 回复 · <时间>**：改了什么、没改的为什么」，把 frontmatter 的 comments_pending 改为 false，"
        "状态保持 awaiting_review 等用户再看；用户在意见里明确说可以/批准/开始的，改为 approved 并按 rd-lab 开始执行。用户原话一字不动。记 log，git commit。"
    ),
    "promote_idea": (
        "用户请求把 idea {path}（「{title}」）升级为 lab 任务。请按 rd-lab skill 起草任务书："
        "新建 labs/<编号>-<slug>/brief.md，用户原话原样保留，结合 AGENTS.md 和 PROJECT.md 的默认规则写出目标、步骤、交付物。"
        "任务书 status 设为 awaiting_review；但如果 idea 的 promote_note 或原话里说了不用过目，直接设为 approved 并立刻开始执行。"
        "在 idea 的 frontmatter 写 promoted_lab: <lab id>，labs 列表加上它，status 改为 lab。"
    ),
    "triage_idea": (
        "ideas/inbox 里有一条新想法 {path}（「{title}」）。请按 rd-idea skill 整理：判断它是新想法还是已有想法的补充，"
        "移到 ideas/<slug>.md 并补上 frontmatter（parent、kind、status、order），用户原话一字不改地放在「## 原话」下，agent 区写「当前回答」；不要替用户发明研究方向；"
        "如果只是对已有 idea 的补充，把原话追加到那个 idea 的「## 原话」下（标注日期）并删除 inbox 文件。"
        "最后在被处理的文件 frontmatter 写 triaged: true。"
        "这是文书任务，AGENTS.md §0 的通读对它放宽：只读 PROJECT.md 的目标段、STATUS.md、ideas/ 各节点的 frontmatter 与标题、wiki/index.md 的目录，"
        "不要通读 wiki 页、卡片、lab notes 或 log。"
    ),
    "resume_lab": (
        "lab labs/{id}/（「{title}」）的任务书状态是 running，但没有活着的运行：上一次运行 {last_run_id}（{last_run_status}）已经结束，"
        "它最后说：「{last_run_result}」。请按 rd-lab skill 的 D 节续跑。本提示是幂等的：先读 labs/{id}/resume.md（续跑单，若有）、brief.md、report.md、"
        "log.md 末尾与本 lab 相关的几条，看 handoff.md 与 audit/ 是否存在，查 .dashboard/auditing 与 .dashboard/writing 里本 lab 记录的 run_info.txt 有无 exit 行"
        "（codex-audit.sh --status / codex-write.sh --status），由此判断停在哪一步：厚层未齐 / 等数值 / 审计被杀或进行中 / 审计报告已出未处理 / 交接单未写 / 薄层未写 / 只差回写与 commit。"
        "从那一步继续，做过的不重做，不要整体重读 notes.md（需要时只读相关小节）。Codex 审计或写作还活着就用 --wait 在前台等；死了没结果就重新启动。"
        "数值批量还在跑就核对进度、更新续跑单后结束运行。收尾按 rd-lab C 节；结束前更新 resume.md；"
        "lab 状态只能停在 done / waiting_answer / awaiting_review / blocked，或仍在等外部进程的 running。"
    ),
}

WRITE_KINDS = set()  # 目前所有工作项都用 read 模型启动；写报告由 skill 内部交给 write 模型的子 agent


DIGEST_PROMPT = (
    "用户回答了以下 {n} 个讨论（按时间）：\n{items}\n\n"
    "这些回答可能互相关联——用户对一个问题的裁决常常也决定了另一个问题怎么选。所以请**先通读全部回答**，找出它们之间的关联与矛盾，"
    "再按 rd-discussion skill 逐个消化：在每个文件末尾写「## 结论与后续」（引用别的回答时注明来自哪个讨论），"
    "把受影响的 wiki、卡片、idea、lab 任务书同步更新；状态为 waiting_answer 且正在等这些回答的 lab，改回 approved 并按 rd-lab 继续执行。"
    "每个讨论完成后把 status 改为 digested（问题彻底解决则 resolved）。两个回答互相矛盾、你定不了的，新开一个讨论问用户，不要猜。"
)


def answered_threads(project: Project) -> list[dict]:
    return [w for w in project.pending_work() if w["kind"] == "digest_answer"]


def run_digest(project: Project, dry_run: bool = False) -> dict | None:
    """把所有已回答的讨论放进**一次**运行统一消化。没有就返回 None。"""
    threads = answered_threads(project)
    if not threads:
        return None
    items = "\n".join(f"- {w['path']}（「{w['title']}」）" for w in threads)
    prompt = DIGEST_PROMPT.format(n=len(threads), items=items)
    if dry_run:
        return {"kind": "digest_answers", "threads": [w["id"] for w in threads], "prompt": prompt}
    cfg = config.load(project.root)
    meta = Runner(project).run(prompt, kind="digest_answers", label=f"digest:{len(threads)}条回答",
                               model=cfg["models"]["read"], effort=cfg["models"].get("effort"))
    for w in threads:
        project.record_attempt(w["kind"], w["id"], meta["status"])
    return meta


def model_for(cfg: dict, kind: str, path: str | None = None, project: Project | None = None) -> tuple[str, str | None]:
    """某个工作项用什么模型：[models].read/effort → [models.kinds].<kind> → 该文件 frontmatter 的 model/effort。"""
    model = cfg["models"]["write"] if kind in WRITE_KINDS else cfg["models"]["read"]
    effort = cfg["models"].get("effort")
    kc = (cfg["models"].get("kinds") or {}).get(kind) or {}
    model = kc.get("model") or model
    effort = kc.get("effort") or effort
    if path and project is not None:
        # 该工作项对应文件的 frontmatter 可以单独指定 model / effort（例如任务书里写 model: claude-opus-5-5）
        try:
            doc_meta, _ = fm.read(project.root / path)
            model = doc_meta.get("model") or model
            effort = doc_meta.get("effort") or effort
        except (OSError, ValueError):
            pass
    return model, effort


def actionable(project: Project, cfg: dict | None = None, only: str | None = None) -> tuple[list[dict], list[dict]]:
    """返回 (现在可以做的, 暂缓的)。暂缓的三种情况：刚失败还在退避期；Claude 额度用尽还没到重置时刻（last_status=limit）；
    续跑的 lab 还有 Codex 审计/写作在跑（last_status=codex）。回答的消化不在这里，它走 run_digest 的 digest_minutes 节奏。"""
    cfg = cfg or config.load(project.root)
    retry = int(cfg["schedule"].get("retry_minutes", 30)) * 60
    work = [w for w in project.pending_work() if w["kind"] != "digest_answer"]
    if only:
        work = [w for w in work if w["kind"] == only]
    ready, deferred = [], []
    pause = project.pause_info()
    codex_live = None
    for w in work:
        info = project.attempt_info(w["kind"], w["id"])
        if pause:
            deferred.append({**w, "last_status": "limit", "retry_in_s": int(pause["until"] - time.time()), "reason": pause["reason"]})
            continue
        if info and info.get("status") != "done" and time.time() - info["t"] < retry:
            deferred.append({**w, "last_status": info["status"], "retry_in_s": int(retry - (time.time() - info["t"]))})
            continue
        if w["kind"] == "resume_lab":
            if codex_live is None:
                from .codex import live_jobs
                try:
                    codex_live = live_jobs(project.root)
                except OSError:
                    codex_live = []
            job = next((j for j in codex_live if j.get("lab") == w["id"]), None)
            if job:
                deferred.append({**w, "last_status": "codex", "retry_in_s": 300, "reason": f"{job['kind']} {job['name']} 还在跑（pid {job.get('pid')}）"})
                continue
        ready.append(w)
    return ready, deferred


def run_pending(project: Project, only: str | None = None, dry_run: bool = False, force: bool = False) -> list[dict]:
    cfg = config.load(project.root)
    ready, deferred = actionable(project, cfg, only)
    if force:
        ready, deferred = ready + deferred, []
    results = []
    for w in deferred:
        results.append({"kind": w["kind"], "id": w["id"], "status": "deferred", "last_status": w["last_status"], "retry_in_s": w["retry_in_s"],
                        **({"reason": w["reason"]} if w.get("reason") else {})})
    max_fail = int(cfg["schedule"].get("max_resume_failures", 3))
    for w in ready:
        prompt = PROMPTS[w["kind"]].format(**w)
        model, effort = model_for(cfg, w["kind"], w.get("path"), project)
        if dry_run:
            results.append({"kind": w["kind"], "id": w["id"], "status": "ready", "prompt": prompt, "model": model, "effort": effort})
            continue
        if w["kind"] == "resume_lab":
            info = project.attempt_info(w["kind"], w["id"]) or {}
            if int(info.get("fails", 0)) >= max_fail:
                # 连续几次续跑都失败：不再自动试，改 blocked 让首页提醒用户
                project.set_lab_status(w["id"], "blocked")
                project.append_log("agent", f"lab {w['id']} 连续 {info.get('fails')} 次续跑失败，改为 blocked 等用户处理", f"labs/{w['id']}/brief.md")
                project.record_attempt(w["kind"], w["id"], "blocked")
                results.append({"kind": w["kind"], "id": w["id"], "status": "blocked", "fails": info.get("fails")})
                continue
        meta = Runner(project).run(prompt, kind=w["kind"], label=f"{w['kind']}:{w['id']}", model=model, effort=effort)
        project.record_attempt(w["kind"], w["id"], meta["status"])
        results.append(meta)
    return results


# 用户在 lab 页点的审计按钮（推导 / 代码）；自动的推导审计在 rd-lab 收尾里做，不走这里
AUDIT_PROMPTS = {
    "audit_derivation": (
        "用户在 dashboard 点了 labs/{id}/ 的「推导审计」。请按 rd-audit skill 执行：组提示词（kind=derivation，对象 notes.md 及其引用的 wiki 页，"
        "上下文含 notation、引用的卡片与原文、用户 notes）→ codex-audit.sh 启动，用 --wait 在前台等到结束（不要放后台）→ 读报告 → 逐条处理（typo 和非吹毛求疵的不严谨直接改并重跑验证；"
        "改变结论开讨论并把 brief.md 状态改 awaiting_review，不要自己改结论）→ 在 report.md 的 audits、相关 wiki 页的 audited_by、STATUS.md 挂标记 → 记 log → git commit。"
    ),
    "audit_code": (
        "用户在 dashboard 点了 labs/{id}/ 的「代码审计」。请按 rd-audit skill 执行：组提示词（kind=code，对象是脚本、results/、DATA.md、画图脚本；"
        "先 `rd free-cores` 并把那句话填进 CORES）→ codex-audit.sh 启动，用 --wait 在前台等到结束（不要放后台）→ 读报告 → 逐条处理（typo 和非吹毛求疵的不严谨直接改代码并重跑受影响的小尺寸检查；"
        "改变结论开讨论并把 brief.md 状态改 awaiting_review，不要自己改结论或结果）→ 在 report.md 的 audits、STATUS.md 挂标记 → 记 log → git commit。"
    ),
}
