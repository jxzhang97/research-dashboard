---
name: rd-init
description: 用 research-dashboard 模板把当前文件夹初始化成一个新课题目录并开始第一个任务。当用户说"这是一个新课题 / 文件夹就是当前目录 / 课题名是 X / 初始 idea 写在 Y.md / 用 research-dashboard 模板初始化 / rd init"时使用。覆盖：rd init、根据 idea 起草 PROJECT.md 和 config.toml、把 idea 挂进想法树、在 studio 上装 dashboard 与定时任务、起草并执行第一个 lab 任务书。
---

# rd-init：从一句话到一个在跑的课题

用户的话通常长这样：**"这是一个新课题，文件夹就是当前目录，课题名 XXX，我的初始 idea 写在了 YYYY.md 里。请用 research-dashboard 模板初始化成课题目录，并完成任务。"**

模板在两台机器都装在 `~/doc_unsyn/research-dashboard`，命令是 `~/doc_unsyn/research-dashboard/rd`（下文简写 `rd`）。dashboard 和定时任务只在 studio 上跑（`ssh studio`，用户名 jiaxin）；课题文件夹在 iCloud 同步的 `~/Documents` 下，两台机器路径只差用户名，所以跨机器一律用 `~/` 相对路径。

## 第 0 步：确认输入

从用户的话里取三样：课题名、idea 文件、是否说了"不用过目"。缺课题名就用文件夹名；缺 idea 文件就 `ls *.md` 找，仍没有就问。**不要改用户的 idea 文件。**

## 第 1 步：初始化目录

```bash
~/doc_unsyn/research-dashboard/rd init . --name "<课题名>"
```

它只补缺失的文件，不碰已有的（用户的 idea、PDF、已有 CLAUDE.md 都保留）。然后 `ls` 确认：`AGENTS.md CLAUDE.md PROJECT.md config.toml references/ wiki/ labs/ discussion/ ideas/ log.md`。

用户文件夹里已经有的东西归位：PDF → `references/raw/`（保留原文件名）；别的 notes 保留在原处，在 PROJECT.md 里登记路径。

## 第 2 步：读 idea，写 PROJECT.md 和 config.toml

1. 通读 idea 文件和用户给的 notes / 文献。
2. **PROJECT.md**：按模板的小节（目标与动机 / 系统与假设 / 我目前的判断与不确定的地方 / 必须通过的验证 / 核心参考文献 / 写作与推导的特别要求）从 idea 里整理，用户原话能直接用的直接用，不要润色成另一种说法。顶部加一行"由 agent 根据 `<idea 文件>` 整理于 <日期>，用户可改"。
3. **config.toml**：`[arxiv]` 的 `keywords`（5–10 个英文短语，从 idea 的核心概念来）、`authors`（idea 提到的关键作者）、`categories`；`[project]` 的 `language`（用户用英文写 idea 也默认 zh，除非他说了要英文）。端口见第 4 步。
4. 把 idea 文件**原样复制**一份到 `ideas/inbox/<日期>-<slug>.md`（加 frontmatter `title`、`source: <原文件路径>`），再按 rd-idea 整理成根节点 `ideas/<slug>.md`，原话一字不改。
5. 把 idea 里提到的文献按 rd-reference 建卡；没有全文的先 `read_depth: abstract`。
6. `wiki/notation.md` 里登记 idea / notes 已经在用的记号。
7. `log.md` 记一条；`git add -A && git commit -m "课题初始化"`。

做完向用户用五六行汇报：PROJECT.md 的要点、arXiv 关键词、建了哪些卡片。**不需要等用户确认再往下走**，但要说清楚哪些是你替他定的。

## 第 3 步：想法 → 第一个任务书

按 rd-lab 第 A 节起草 `labs/01-<slug>/brief.md`：目标、用户原话（整段）、步骤、交付物、机器（默认 studio）。

- 用户说了"不用过目 / 直接做"：`status: approved`，直接进第 5 步。
- 否则：`status: awaiting_review`，把任务书给用户看（AskUserQuestion 或直接贴出来问），等他说改或可以。

## 第 4 步：在 studio 上装 dashboard 和定时任务

先看自己在哪台机器：`hostname`。

**在笔记本上**（主机名不含 Studio）：

```bash
REL="${PWD#$HOME/}"      # 例如 Documents/Project/XXX
# 等 iCloud 把 config.toml 同步到 studio（通常几十秒）
for i in $(seq 1 24); do ssh studio "test -f ~/$REL/config.toml" && break; sleep 5; done
ssh studio "~/doc_unsyn/research-dashboard/rd scheduler install ~/$REL && ~/doc_unsyn/research-dashboard/rd scheduler status ~/$REL"
```

**在 studio 上**：直接 `rd scheduler install .`。

端口：`rd scheduler install` 会自动避开本机其他课题占用的端口（冲突就换下一个并写回 `config.toml`），输出的最后一行是实际地址。把它换成 Tailscale 地址告诉用户：`http://100.120.253.99:<端口>`。`ssh studio "~/doc_unsyn/research-dashboard/rd projects"` 能看本机所有课题和端口。

验证：`ssh studio "curl -s localhost:<端口>/api/overview | head -c 200"` 有 JSON 即可。

## 第 5 步：执行任务

按 rd-lab 第 B、C 节做：`status: running`，三方对照，推导报告用 baby-steps-report（它自带的 gap-check 阶段在交互窗口里可以当面问用户；得到的裁决同时写进 `discussion/`），数值先 `rd free-cores`，收尾清单一项不漏，`status: done`，git commit。

交互窗口里跑长任务时，每完成一个大步骤就把 `report.md` 的草稿更新一次，这样 dashboard 上随时能看到进展。

## 常见坑

- 不要在 ssh 会话里直接 `rd run`：ssh 看不到钥匙串会报未登录。要在 studio 上派任务走 `curl -X POST localhost:<端口>/api/runs`，或者让用户在网页上点。
- 两台机器不要同时让 agent 写同一课题。你在笔记本窗口里干活时，studio 上的 dashboard 只读不写（它的文件监视会在 15 秒内发现待办并执行，所以你起草的任务书如果直接写成 `approved`，studio 会立刻接手执行；交互窗口里自己要做的任务，先保持 `running` 并在 log 里写明"笔记本交互会话执行中"）。
- 绝对路径只允许出现在 `DATA.md`。
