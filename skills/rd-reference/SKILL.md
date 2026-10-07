---
name: rd-reference
description: 课题文献卡片的建立与更新（research-dashboard 课题目录内使用）。当需要为一篇文献建卡、把 references/inbox 里批准的 arXiv 候选下载并入库、在 lab 收尾时回写卡片的「与本课题的联系」、或用户把 PDF 放进 references/raw 要求整理时使用。
---

# rd-reference：文献卡片

卡片是 agent 对一篇文献"读懂了什么、和本课题有什么关系"的记录，随课题推进不断更新。一篇文献一张卡，放在 `references/cards/<key>.md`，`key` 用 arXiv id（如 `2104.14257`），没有 arXiv 的用 `<第一作者><年份>-<短题>`。

## 流程

1. **拿到原文**：PDF 放 `references/raw/<key>.pdf`。arXiv 的用 `https://arxiv.org/pdf/<id>` 下载（`curl -L -o`）。用户自己放进 raw 的文件不要改名，卡片 `file:` 指向它。
2. **读**：先读摘要、引言、结论，再读与 PROJECT.md 目标相关的章节和附录。读了多少如实填 `read_depth`：`abstract` / `skim` / `full`。
3. **对照记号**：文献记号与 `wiki/notation.md` 不同的，在卡片「记号对应」列表。
4. **写卡**（模板见下）。「与本课题的联系」要具体到"我们哪一步可以用它的哪个结果/方法"，而不是泛泛的"相关"。「内容总结」3–8 段是上限不是目标：读者先看「一句话」和「与本课题的联系」，总结只写与课题相关的部分。
5. **互链**：卡片里用 `[[概念]]` 链接 wiki 页；相关 wiki 页的「文献」小节加上这张卡。新概念值得单独一页的，按 rd-wiki 建页。
6. **记录**：`log.md` 追加一条；如果是 inbox 候选，把 `references/inbox/<id>.md` 的 `status` 改为 `ingested`。

## 更新卡片的时机

- lab 收尾：回头看该 lab 引用过的卡片，在「与本课题的联系」追加一条带日期的话，**两三句、不抄数字**，例如"2026-10-02 · lab 03 的 ED 结果与其式 (12) 的 bound 一致，见 lab 03 notes §4"。数字和表格的权威位置是 lab 的 notes/results，卡片只链接。
- 用户在讨论里纠正了对某篇文献的理解：改「可靠性与疑点」并记日期。
- 每次更新都改 frontmatter 的 `updated`，并在「更新记录」加一行。

## 术语

- 专有名词、方法名、物理量名首次出现写「中文（English）」；读者可能只认识英文。

## 不做的事

- 没读过的章节不总结；不确定的结论标"（待核实）"。
- 不把文献的记号直接搬进 wiki 正文；wiki 正文用课题记号。

## 卡片模板

```markdown
---
title: <原题>
authors: [<姓 名>, …]
year: 2024
arxiv: 2104.14257
doi:
source: user | agent | arxiv-scan
read_depth: full
file: references/raw/2104.14257.pdf
tags: [flat-band, quantum-geometry]
updated: 2026-10-02
related_labs: []
---

# <原题>

## 一句话
它证明/提出/计算了什么。

## 内容总结
按文章结构，3–8 段。每段末尾标出处（节号或式号）。

## 方法
用了什么方法、近似、模型；关键假设是什么。

## 与本课题的联系
- 可以直接用的结果：…（式号）
- 可以借鉴的推导思路：…
- 与我们假设不同的地方：…
- 2026-10-02 · 建卡时的判断。

## 关键公式与记号对应
| 文献记号 | 课题记号 | 说明 |
|---|---|---|

## 可靠性与疑点
哪些结论有数值/实验支持，哪些是推测；我看到的可疑步骤。

## 更新记录
- 2026-10-02 建卡（read_depth: full）
```
