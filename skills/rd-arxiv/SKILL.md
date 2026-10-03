---
name: rd-arxiv
description: 每日 arXiv 候选的筛选与说明（research-dashboard 课题目录内使用）：对 references/inbox 里扫描脚本新写入的 pending 候选，只凭摘要判断与课题的关系、写出"为什么可能相关"、淘汰明显无关的，把最终候选留给用户审批；批准后的入库交给 rd-reference。当 references/inbox 有 reason 为空的 pending 文件、或用户要求调整 arXiv 检索范围时使用。
---

# rd-arxiv：候选筛选

`rd arxiv-scan` 每天按 `config.toml [arxiv]` 的分类与关键词拉新文章，写到 `references/inbox/<id>.md`（`status: pending`，`reason` 为空）。本 skill 负责第二步：**只凭摘要**给每篇写理由或淘汰。用户在 dashboard 审批，批准的才下载精读（rd-reference）。

## 流程

1. 读 `PROJECT.md` 的目标与假设、`wiki/index.md` 的当前认识。
2. 对每篇 `reason` 为空的候选：
   - 读 frontmatter 和正文里的摘要。**不要下载 PDF，不要读全文。**
   - 判断：与课题的方法、模型、结论有没有可用的交集。
   - 有：在 frontmatter `reason` 写一两句具体的话（"它给出平带 Bose 气体 stiffness 的 quantum metric 上界，可能与 lab 03 的 bound 直接比较"），并在正文「## 为什么可能相关」展开 2–4 句，末尾注明"（仅基于摘要）"。
   - 无：`status: rejected`，`reason` 写一句为什么（"综述性质 / 费米子体系且无几何量 / 实验"）。
3. 保留的 `pending` 不超过 `config.toml` 的 `max_per_day`；超出的按相关性淘汰为 `rejected`，理由写"本日额度已满，相关性较低"。
4. `log.md` 追加：扫描结果，保留几篇。

## 调整检索范围

用户觉得候选太多/太少/不对路时，改 `config.toml [arxiv]` 的 `categories`、`keywords`、`authors`、`max_per_day`。关键词写英文、小写无所谓（匹配时忽略大小写）；标题命中比摘要命中权重高。被用户拒绝过的文章记录在 `.seen.json`，不会再出现。

## 不做的事

- 不替用户决定入库；`approved` 只能由用户在 dashboard 设。
- 不根据摘要改 wiki。
