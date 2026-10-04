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
        "大数据放 data_root 并留 DATA.md。收尾按 rd-lab C 节：厚层齐 → 写 handoff.md → 用 write 模型子 agent 做薄层写作步"
        "（report.md 首屏、受影响 wiki 页首屏、idea 当前回答、STATUS.md）并核对科学限定 → 卡片两三句、index、log.md，status 改为 done；"
        "遇到必须由用户裁决的问题，按无人值守规则写讨论并把 status 改为 waiting_answer。"
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


def actionable(project: Project, cfg: dict | None = None, only: str | None = None) -> tuple[list[dict], list[dict]]:
    """返回 (现在可以做的, 因为刚失败而暂缓的)。回答的消化不在这里，它走 run_digest 的两小时节奏。"""
    cfg = cfg or config.load(project.root)
    retry = int(cfg["schedule"].get("retry_minutes", 30)) * 60
    work = [w for w in project.pending_work() if w["kind"] != "digest_answer"]
    if only:
        work = [w for w in work if w["kind"] == only]
    ready, deferred = [], []
    for w in work:
        info = project.attempt_info(w["kind"], w["id"])
        if info and info.get("status") != "done" and time.time() - info["t"] < retry:
            w = {**w, "last_status": info["status"], "retry_in_s": int(retry - (time.time() - info["t"]))}
            deferred.append(w)
        else:
            ready.append(w)
    return ready, deferred


def run_pending(project: Project, only: str | None = None, dry_run: bool = False, force: bool = False) -> list[dict]:
    cfg = config.load(project.root)
    ready, deferred = actionable(project, cfg, only)
    if force:
        ready, deferred = ready + deferred, []
    results = []
    for w in deferred:
        results.append({"kind": w["kind"], "id": w["id"], "status": "deferred", "last_status": w["last_status"], "retry_in_s": w["retry_in_s"]})
    for w in ready:
        prompt = PROMPTS[w["kind"]].format(**w)
        if dry_run:
            results.append({"kind": w["kind"], "id": w["id"], "status": "ready", "prompt": prompt})
            continue
        model = cfg["models"]["write"] if w["kind"] in WRITE_KINDS else cfg["models"]["read"]
        effort = cfg["models"].get("effort")
        # 该工作项对应文件的 frontmatter 可以单独指定 model / effort（例如任务书里写 model: claude-opus-5-5）
        try:
            doc_meta, _ = fm.read(project.root / w["path"])
            model = doc_meta.get("model") or model
            effort = doc_meta.get("effort") or effort
        except (OSError, ValueError):
            pass
        meta = Runner(project).run(prompt, kind=w["kind"], label=f"{w['kind']}:{w['id']}", model=model, effort=effort)
        project.record_attempt(w["kind"], w["id"], meta["status"])
        results.append(meta)
    return results
