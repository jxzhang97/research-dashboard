---
name: rd-idea
description: 课题问题树的整理（research-dashboard 课题目录内使用）：把用户在 ideas/inbox 或 dashboard 速记的原话整理成 ideas/<slug>.md 节点、挂到以研究问题为单位的层级树上、维护每个节点的「当前回答」与状态，以及把想法升级成 lab 任务。当 ideas/inbox 有新文件、用户给出模糊想法要记下来、要更新某个想法的当前回答或状态、或要把想法升级为任务时使用。
---

# rd-idea：问题树

`ideas/` 是课题的**问题树**：每个节点是一个要回答的研究问题（或一条为回答问题而选的路线、方法），节点上写着它的当前回答。用户的想法分三层，每样东西只写一次：项目默认规则（AGENTS.md）、问题本身（这里）、任务书（rd-lab）。本 skill 只管中间这层。

**铁律：用户的原话一字不改。** agent 只写 `<!-- agent -->` 标记之后的部分。
**第二条铁律：不替用户发明研究方向。** 树里只放用户说过的问题和它们的直接拆分；agent 自己想到的方向写在「agent 备注」或 discussion，标明"agent 建议"。

## 树怎么长

- 根是课题的总问题（通常一个，也可以几个）。下面两到三层：大问题 → 子问题 → 为回答它选的路线或方法。超过三层说明该拆 lab 了，不是该加层。
- 节点是**问题形**的："算谁的 magic？""热力学极限下 X 在相边界是否非解析？"路线和方法节点写 `kind: route` / `kind: method`（默认 `question`），标题也写成"用 1D 链回答 Q3"这种能看出它服务于哪个问题的样子。
- 一个节点值得存在，是因为它有独立的答案、独立的证据、或可以单独决定做不做。一个参数点、一次重跑、一个脚本不是节点。
- 平级节点用 frontmatter `order` 排序；跨分支的联系用 `related: [slug, …]` 加一句原因，不建别的关系类型。
- 用户可以直接改 `parent`。agent 发现一个根下十几个平级时可以建中间问题归类，但要在 log 和「agent 备注」说明，不改任何「原话」。

## 整理 inbox（triage）

`ideas/inbox/<file>.md` 是用户原话。对每个未处理的文件：
1. 读原话，读现有树（`ls ideas/*.md`，看各自的 title/parent/kind）。
2. 判断：
   - **新问题** → 新建 `ideas/<slug>.md`，原话整段复制到「## 原话」并标日期和来源文件；选 `parent`（最贴切的上级问题）；`status: seed`。然后删除 inbox 文件（内容已完整保留）。
   - **对已有问题的补充** → 在那个节点的「## 原话」末尾追加一个带日期的小节，内容原样；删除 inbox 文件。
   - **其实是任务**（"帮我算/写/审"）→ 仍建节点（节点是"为什么要算"），同时按 rd-lab 起草任务书，`status: lab`。
   - **实在不知道挂哪**：建为根节点，在「agent 备注」说明，不要问用户。
3. `log.md` 追加一条：整理了什么、挂到哪。

## 节点模板

```markdown
---
title: <问题形的中文短标题，二十字以内>
parent: <上级 slug，根节点留空>
kind: question        # question / route / method
status: seed          # seed / exploring / lab / resolved / parked / dropped
order: 10
created: 2026-10-02
labs: []
related: []
tags: []
---

# <标题>

## 原话
### 2026-10-02（来自 ideas/inbox/2026-10-02-xxx.md）
（原样）

<!-- agent -->
## agent 的理解
一两句话复述问题的核心，列出可能的二义性。

## 当前回答
（两到四行。有答案就直接写答案和适用范围；没答案就写"未回答，等 lab NN"。每次收尾**重写**这一段，不追加。）

## 证据与链接
- lab [[NN-slug]] 报告 → 哪一节/哪张图
- 讨论 [[YYYY-MM-DD-slug]]：用户裁决了什么
- wiki [[概念页]]

## 历史
- 2026-10-02 · 建立节点。
- （每次有实质进展加一行，一行一句，不放数字表；细节在 lab 报告和 log）

## 派生
- [[子问题 slug]]：…

## agent 备注
（agent 建议的方向、树的调整说明。）
```

## 状态含义

- `seed`：记下了，还没动。
- `exploring`：agent 做过初步阅读/估算，写在「当前回答」。
- `lab`：已有任务书（`labs` 列表非空）。
- `resolved`：问题有了答案，答案在「当前回答」并链接到报告。
- `parked`：用户决定先放一放。
- `dropped`：用户否决；写明原因。

## 升级为 lab

用户在 dashboard 点"升级"后 frontmatter 会出现 `promote_requested`（和可选的 `promote_note`）。按 rd-lab 起草任务书，然后在本节点写 `promoted_lab`、`labs`、`status: lab`。用户说"不用过目"的直接执行。

## lab 收尾时怎么改节点

由薄层写作步（rd-lab C3）改写「当前回答」；研究 agent 核对后在「历史」加一行、更新「证据与链接」和 `status`。`STATUS.md` 里该问题的一行与这里的「当前回答」保持一致（STATUS 更短，引用这里）。
