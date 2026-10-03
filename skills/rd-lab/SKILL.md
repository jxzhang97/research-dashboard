---
name: rd-lab
description: 课题 lab 任务的起草、执行与收尾（research-dashboard 课题目录内使用）。当要把一个 idea 升级成任务书、执行一个已批准的 labs/NN-slug/brief.md、写 report.md 摘要与 DATA.md、或做任务收尾回写（卡片、wiki、idea、log）时使用。
---

# rd-lab：任务从起草到收尾

一个 lab 就是一个有明确交付物的任务，住在 `labs/NN-slug/`。`NN` 是两位递增编号（用 `ls labs/` 看最大编号）。

## A. 起草任务书

输入：一个 idea（`ideas/<slug>.md`，或 `ideas/inbox/` 里的原话）+ 用户可能附的说明（idea 的 `promote_note`）。

1. 读 idea 原话、PROJECT.md、AGENTS.md、相关 wiki 和卡片。
2. 把用户原话**一字不改**复制到「## 用户原话」。
3. 写出目标、步骤、交付物、机器。默认规则（语言、baby-steps-report、notation、并行、数据去向）不用重复，只写与默认不同的。
4. 判断是否需要用户过目：默认 `status: awaiting_review`；用户原话或 promote_note 里说了"不用过目 / 直接做"就 `approved` 并立即进入 B。
5. 在来源 idea 的 frontmatter 写 `promoted_lab: <lab id>`、`labs: [<lab id>]`、`status: lab`。记 log。

任务书模板：

```markdown
---
title: <任务标题>
status: awaiting_review
idea: <idea slug>
machine: studio
created: 2026-10-02
# model: claude-opus-5-5   # 可选：用户指定了才写；不写就用 config.toml 的默认（Fable 5.1 + max）
# effort: max
---

# <任务标题>

## 目标
一两句：做完后我们会知道什么。

## 用户原话
> （原样复制，含日期）

## 任务步骤
1. …（每步说明产出什么、用什么验证）
2. …

## 交付物
- report.pdf（baby-steps-report）+ report.md 摘要
- 图：…
- 代码：…

## 特别要求
（与 AGENTS.md 默认不同的；没有就写"无"。）

## 我对任务书的疑问
（起草时发现 idea 有二义性，列在这里；严重到不能开工的，同时写 discussion。）
```

## B. 执行

1. `status: running`，记 log。
2. 开工前做一次三方对照：任务书 ↔ PROJECT.md/notation ↔ 你打算走的路线。有分歧按 rd-discussion 提问（无人值守时写 discussion 并把 status 改 `waiting_answer`，结束）。
3. 推导与写作：按 baby-steps-report skill；报告正文由 `write` 模型的子 agent 写。PDF 放本 lab 文件夹。
4. 数值：先 `rd free-cores <课题目录>`，按建议设线程数并 `rd jobs claim`；大数据写到 `data_root/<lab id>/`，跑完 `rd jobs release`。脚本放本 lab 文件夹，可复用的提到 `src/`。
5. 中途产生的小结论随时写进 `report.md`（可以是草稿状态），避免运行中断什么都没留下。

## C. 收尾清单（必须逐项做完才改 done）

- [ ] `report.md`：frontmatter `pdf:`、`status: done`、`conclusions:` 列表；正文 = 结论 + 每条结论的证据 + 没做完的事。
- [ ] **图**：关键图（结果图至少一张，加一张说明问题设定的示意图）导出到 `fig/`（PNG/SVG），在 `report.md` 里 `![图注](fig/xxx.png)` 内嵌；PDF 里的图不能只存在于 PDF。
- [ ] `DATA.md`（有大数据时）：机器、绝对路径（这一处允许绝对路径）、内容、日期、重新生成命令。
- [ ] 回写卡片：本 lab 用到的每张卡片「与本课题的联系」追加一条。
- [ ] 更新 wiki：按 rd-wiki ingest。
- [ ] 来源 idea：「进展与结论」追加，状态按情况改（`resolved` / 仍 `lab`）。
- [ ] 新问题 → discussion。
- [ ] `log.md` 追加；`brief.md` 的 `status: done`；git commit。

report.md 模板：

```markdown
---
title: <任务标题> · 报告摘要
status: done
pdf: report.pdf
conclusions:
  - <一句话结论 1>
  - <一句话结论 2>
updated: 2026-10-02
---

# 摘要

## 结论
1. …（证据：报告 §x / 图 y）

## 图
![问题设定示意：两副本 Creutz 梯子与配对通道](fig/setup.svg)

![ED 谱随 L 的变化，nmax=3；零能态在 L≥10 出现](fig/spectrum.png)

## 没做完或没定的
- …

## 文件
- [report.pdf](report.pdf)
- 图脚本：`fig/plot_spectrum.py`
```

DATA.md 模板：

```markdown
# 数据去向

- 机器：studio
- 路径：/Users/jiaxin/doc_unsyn/<课题>/<lab id>/
- 内容：ED 谱（L=8–16，nmax=3），npz；原始日志
- 生成：`python run_ed.py --L 12 …`（本文件夹）
- 日期：2026-10-02
```
