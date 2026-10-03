---
name: rd-idea
description: 课题想法树的整理（research-dashboard 课题目录内使用）：把用户在 ideas/inbox 或 dashboard 速记的原话整理成 ideas/<slug>.md 节点、挂到层级树上、维护状态与进展，以及把想法升级成 lab 任务。当 ideas/inbox 有新文件、用户给出模糊想法要记下来、要更新某个想法的进展或状态、或要把想法升级为任务时使用。
---

# rd-idea：想法树

用户的想法分三层，每样东西只写一次：项目默认规则（AGENTS.md）、想法本身（这里）、任务书（rd-lab）。本 skill 只管中间这层。

**铁律：用户的原话一字不改。** agent 只写 `<!-- agent -->` 标记之后的部分。

## 整理 inbox（triage）

`ideas/inbox/<file>.md` 是用户原话。对每个未处理的文件：
1. 读原话，读现有想法树（`ls ideas/*.md`，看各自的 title/parent）。
2. 判断：
   - **新想法** → 新建 `ideas/<slug>.md`（模板见下），原话整段复制到「## 原话」并标日期和来源文件；选 `parent`（最贴切的上级，没有就留空成为根）；`status: seed`。然后删除 inbox 文件（内容已完整保留）。
   - **对已有想法的补充** → 在那个想法的「## 原话」末尾追加一个带日期的小节，内容原样；删除 inbox 文件。
   - **其实是任务** （"帮我算/写/审"）→ 仍建想法节点（想法是"为什么要算"），同时按 rd-lab 起草任务书，`status: lab`。
   - **实在不知道挂哪**：建为根节点，在「agent 备注」说明，不要问用户。
3. `log.md` 追加一条：整理了什么、挂到哪。

## 想法节点模板

```markdown
---
title: <中文短标题>
parent: <上级 slug，根节点留空>
status: seed          # seed / exploring / lab / resolved / parked / dropped
created: 2026-10-02
labs: []
tags: []
---

# <中文短标题>

## 原话
### 2026-10-02（来自 ideas/inbox/2026-10-02-xxx.md）
（原样）

<!-- agent -->
## agent 的理解
一两句话复述问题的核心，列出可能的二义性。

## 进展与结论
- 2026-10-02 · 建立节点。
- （lab 完成后追加：结论一句话 + 链接 [[lab id]]）

## 派生
- [[子想法 slug]]：…
```

## 状态含义

- `seed`：记下了，还没动。
- `exploring`：agent 做过初步阅读/估算，写在「进展与结论」。
- `lab`：已有任务书（`labs` 列表非空）。
- `resolved`：问题有了答案，答案在「进展与结论」并链接到报告。
- `parked`：用户决定先放一放。
- `dropped`：用户否决；写明原因。

## 升级为 lab

用户在 dashboard 点"升级"后 frontmatter 会出现 `promote_requested`（和可选的 `promote_note`）。按 rd-lab 起草任务书，然后在本节点写 `promoted_lab`、`labs`、`status: lab`。用户说"不用过目"的直接执行。

## 层级调整

用户可以直接改 `parent`。agent 整理时如果发现树明显不合理（一个根下几十个平级），可以建中间节点归类，但要在 log 和「agent 备注」说明，并且不改任何「原话」。
