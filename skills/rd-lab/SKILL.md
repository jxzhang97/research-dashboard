---
name: rd-lab
description: 课题 lab 任务的起草、执行与收尾（research-dashboard 课题目录内使用）。当要把一个 idea 升级成任务书、执行一个已批准的 labs/NN-slug/brief.md、写 notes.md 与 report.md、做薄层写作步（交接单 → Codex 写 → 机械检查，见 rd-writer）、或做任务收尾回写（STATUS、wiki、idea、卡片、log）时使用。
---

# rd-lab：任务从起草到收尾

一个 lab 就是一个有明确交付物的任务，住在 `labs/NN-slug/`。`NN` 是两位递增编号（用 `ls labs/` 看最大编号）。

## A. 起草任务书

输入：一个 idea（`ideas/<slug>.md`，或 `ideas/inbox/` 里的原话）+ 用户可能附的说明（idea 的 `promote_note`）。

1. 读 idea 原话、PROJECT.md、STATUS.md、AGENTS.md、相关 wiki 和卡片。
2. 把用户原话**一字不改**复制到「## 用户原话」。
3. 写出目标、步骤、交付物、机器。默认规则（语言、rd-notes、notation、并行、数据去向）不用重复，只写与默认不同的。标题二十字以内，细节放副标题或目标。
4. 判断是否需要用户过目：默认 `status: awaiting_review`；用户原话或 promote_note 里说了"不用过目 / 直接做"就 `approved` 并立即进入 B。
5. 在来源 idea 的 frontmatter 写 `promoted_lab: <lab id>`、`labs: [<lab id>]`、`status: lab`。记 log。
6. **用户的意见**：用户在 dashboard 任务页写的意见会由程序追加到任务书末尾的「## 用户意见」（带时间，原话不动），并把 frontmatter `comments_pending` 设为 true；系统随即派一次 `revise_brief` 运行。处理：通读全部意见；按意见修改目标、步骤、交付物、特别要求（改写，不留两套）；在每条意见正下方写一段「**agent 回复 · <时间>**：改了什么、没改的为什么」；把 `comments_pending` 改为 false；状态保持 `awaiting_review` 等用户再看——除非用户在意见里明确说"可以 / 批准 / 开始"，那就 `approved` 并进入 B。运行中（`running`）的任务也可能收到意见：下一次运行开始时先读「用户意见」，按它调整，回复写在意见下面。

任务书模板：

```markdown
---
title: <二十字以内>
status: awaiting_review
idea: <idea slug>
machine: studio
created: 2026-10-02
# model: claude-opus-5-5   # 可选：用户指定了才写
# effort: max
---

# <标题>

## 目标
一两句：做完后我们会知道什么（直接对应 idea 的问题）。

## 用户原话
> （原样复制，含日期）

## 任务步骤
1. …（每步说明产出什么、用什么验证）

## 交付物
- notes.md（rd-notes）+ report.md 首屏 + fig/
- 代码、数据：…

## 特别要求
（与 AGENTS.md 默认不同的；没有就写"无"。）

## 我对任务书的疑问
（起草时发现 idea 有二义性，列在这里；严重到不能开工的，同时写 discussion。）

## 用户意见
（用户在 dashboard 任务页写的意见由程序追加到这里；agent 在每条下面回复并修改任务书。）
```

## B. 执行

1. `status: running`，记 log。
2. 开工前做一次三方对照：任务书 ↔ PROJECT.md/notation ↔ 你打算走的路线。有分歧按 rd-discussion 提问（无人值守时写 discussion 并把 status 改 `waiting_answer`，结束）。
3. 推导、分析、方法说明都进 `notes.md`，按 rd-notes skill，在同一上下文里写（谁推导谁写）。
4. 数值：先 `rd free-cores <课题目录>`，按建议设线程数并 `rd jobs claim … --pid <批量进程>`；大数据写到 `data_root/<lab id>/`，跑完 `rd jobs release`。脚本放本 lab 文件夹，可复用的提到 `src/`。
5. 中途的小结论随时写进 `report.md`（草稿状态，首屏可以先只有「问题」和「当前回答（初步）」），避免运行中断什么都没留下。

## C. 收尾

### C1. 厚层齐
- `notes.md`、`fig/`（关键图至少一张结果图加一张问题设定示意图）、`results/`、`DATA.md`（有大数据时：机器、绝对路径、内容、日期、重新生成命令）。

### C2. 交接单 `handoff.md`
给写作步用，写作者没看过任何一次运行。内容：读者是谁；用户原来问什么；这次回答了什么（分**已证明 / 数值支持 / 解释与猜测**三档，每档带适用范围）；**哪些话不能说过头**（逐条）；材料在哪（notes 节号、表、图及每张图的角色）；要写哪些文件、用什么模板。

### C3. 薄层写作步（交给 Codex，按 rd-writer skill）
研究 agent 不写薄层。按 `rd-writer`：用 handoff.md 和它列的材料组一份提示词，`codex-write.sh` 调 Codex（`[writer]` 的模型与强度，附上主图），让它写：
- `report.md`（模板见下）；
- 受影响的 wiki 页（整页，按 rd-wiki 模板；讲课体）；
- 来源 idea 的「当前回答」与 frontmatter `verdict:`（只改这两处，原话不动）；
- `STATUS.md` 里对应问题的那一行和「进行中 / 等你决定」。

多个目标可以分几次调用（每次一两个文件，图随提示词附上）。写完后研究 agent **只做机械检查**：目标文件在、没碰别的文件、图和链接能打开、`rd doctor` 无断链；不核对、不改写它的文字。Codex 不可用时记 log，薄层留到下次。

### C4. 其余回写（每样一句话加链接）
- 卡片「与本课题的联系」：本 lab 用到的每张卡片加两三句，不抄数字。
- `wiki/index.md`：新页加一行。
- 新问题 → discussion。
- `log.md` 追加；`brief.md` 的 `status: done`；git commit。

### report.md 模板

```markdown
---
title: <短标题>
status: done
notes: notes.md
updated: 2026-10-02
---

# <短标题>

## 问题
这个 lab 要回答什么，一两句。

## 当前回答
一到三句能直接理解的判断，带适用范围（模型、参数、尺寸、方法）。

## 为什么信
![看哪里 → 看到什么 → 说明什么](fig/main.png)
一句话，或"见 notes.md#某节"。

## 边界
- 会改变判断的未完成检查、局限、待裁决（链接 discussion）。

## 结论与证据
1. …（见 notes.md#x / 图 y）

## 没做完或没定的
- …

## 文件
- notes.md；代码；数据（见 DATA.md）；按需导出的 PDF（注明日期）
```
