# research-dashboard

一个本地 web，用来管理**一个理论物理课题**的文献、当前理解、任务、讨论和想法；agent（Claude Code 或 Codex）直接读写同一套 markdown 文件。

- **文件是唯一真相**：所有内容是带 frontmatter 的 markdown，放在课题文件夹里；web 只是视图，加四个写入口（回答问题、审批文献、速记想法、立刻派任务）。
- **首页是课题状态**：`STATUS.md`（研究问题与当前回答、正在进行、等你决定），agent 每次收尾重写。其余页面：文献（卡片 + arXiv 候选审批）、Wiki（概念页，互链）、Lab（任务书 → 摘要首屏 → notes）、讨论（agent 向你提问，你裁决）、问题树（卡片分支图：每张卡片是一个研究问题，标题加 frontmatter `verdict:` 的一句结论；点卡片看完整回答、证据、子问题、原话与历史；节点多时只展开选中分支；可缩放；顶部速记）、任务页（agent 运行日志）。任意项目内 markdown 都能在 `#/doc/<路径>` 站内阅读（目录、锚点、相对链接）。
- **写给谁**：面向读者的页面假定读者是刚进组的研究生；厚层（notes、代码、数据）由做研究的 agent（Claude）写，薄层（lab 摘要、wiki 页、问题的当前回答、STATUS）单独一步交给 Codex（`config.toml` 的 `[writer]`，默认 gpt-6-astra xhigh，ChatGPT 登录）按交接单写，研究 agent 只做机械检查、不改它的文字（`rd-writer` skill）。wiki 像讲课，图注具体到面板和标记。每个事实只有一个权威位置。
- **agent 规则是模板的一部分**：`AGENTS.md`（通用规则）+ `skills/rd-*`（各环节的工作流），Claude Code 和 Codex 都能读。
- **自动化**：用户在网页上的每个动作（回答、批准、升级、速记、立刻执行）当场触发 agent；直接在编辑器里写进 `ideas/inbox/` 或改文件状态的，dashboard 每 15 秒扫一次也会当场开始。launchd 每小时的 tick 只是 dashboard 没开时的兜底。每天扫 arXiv，候选需用户审批后才入库。同一课题同一时间只跑一个 agent，后来的排队。

## 安装（每台机器一次）

```bash
git clone https://github.com/jxzhang97/research-dashboard ~/doc_unsyn/research-dashboard
~/doc_unsyn/research-dashboard/rd install
```

`install` 会建 `.venv`、装依赖、把 `skills/rd-*` 软链接到 `~/.claude/skills`、`~/.codex/skills`、`~/.agents/skills`，并检查可选的外部 skill `baby-steps-report` 是否已安装（只在用户明确要双语 LaTeX 报告时用；日常推导走本仓库的 `rd-notes`，输出网页可读的中文 markdown）。

建议把 `rd` 加进 PATH：`ln -s ~/doc_unsyn/research-dashboard/rd ~/.local/bin/rd` 或在 shell 配置里加 alias。

## 新建课题

最省事的方式：在课题文件夹里开一个 Claude Code（或 Codex）窗口，说

> 这是一个新课题，文件夹就是当前目录，课题名 XXX，我的初始 idea 写在了 YYYY.md 里。请用 research-dashboard 模板初始化成课题目录，并完成任务。

`rd-init` skill 会接手：初始化目录、从 idea 整理 PROJECT.md 和 arXiv 关键词、把 idea 挂进想法树、在 studio 上装 dashboard 和定时任务、起草第一个任务书并执行。

手动方式：

```bash
rd init ~/Documents/Project/<课题名> --name <课题名>
```

然后填 `PROJECT.md`（课题总纲）和 `config.toml`（arXiv 关键词、模型等）。课题文件夹本身可以放在 iCloud 同步的目录里，两台机器共用；大的中间数据放 `config.toml` 的 `data_root`（默认 `~/doc_unsyn/<课题名>`，不同步）。

## 日常

```bash
rd serve <课题目录>                   # 打开 http://localhost:8010
rd run <课题目录> -p "读一下 xxx"      # 命令行直接派一件事
rd tick <课题目录>                    # 处理所有待办
rd arxiv-scan <课题目录> --dry-run    # 看看今天会抓到什么
rd free-cores <课题目录>              # 现在能用几个核
rd doctor <课题目录>                  # 断链、卡片缺节
rd update <课题目录>                  # 模板更新后刷新 AGENTS.md
```

在 studio 上装定时任务（常驻 dashboard + 每小时 tick + 每天 arXiv）：

```bash
rd scheduler install <课题目录>
rd scheduler status <课题目录>
```

笔记本用浏览器打开 `http://<studio 的 Tailscale IP>:8010` 即可。

## 课题目录结构

```
<课题>/
├── AGENTS.md / CLAUDE.md   agent 规则（模板提供，rd update 刷新）
├── PROJECT.md              课题总纲（用户写）
├── config.toml             语言、模型、arXiv 检索、端口
├── references/ raw/ cards/ inbox/
├── wiki/       index.md notation.md …
├── STATUS.md               课题状态（agent 每次收尾重写，首页）
├── labs/       NN-slug/ brief.md report.md notes.md handoff.md fig/ DATA.md
├── src/
├── discussion/ YYYY-MM-DD-slug.md
├── ideas/      slug.md  inbox/
├── log.md
└── .dashboard/ runs/ jobs/ machines/ state.json
```

## 工作循环

1. 你在 `ideas/inbox/` 或网页速记一个想法 → agent 整理挂到想法树（原话不改）。
2. 你点"升级为 lab" → agent 起草任务书 → 你过目：批准，或在任务页写意见（agent 按意见改任务书、在意见下回复，再请你看）；事先说不用过目的直接执行。
3. 执行中遇到要你裁决的问题 → 写进讨论区，任务标 `waiting_answer` → 你在网页回答。回答**不当场消化**：每五小时（`schedule.digest_minutes`）把这段时间所有已回答的讨论放进一次运行统一消化，互相关联的裁决一起考虑；讨论页可以"现在就消化"。
4. 任务收尾：notes.md 与 fig/ 齐 → 交接单 handoff.md → 薄层写作步交给 Codex（report.md、wiki 页、问题的当前回答、STATUS.md）→ 机械检查 → 卡片两三句、index、日志、git commit。PDF 与英文版按需导出。
5. 每天 arXiv 候选进"文献"页等你审批；批准的被下载、精读、建卡。

## 多个课题同时跑

每个课题一个文件夹、一个 dashboard、一套 launchd 任务，互不干扰；机器级的东西统一在 `~/.rd/`（每台机器一份，不进 iCloud）：

- `projects.json`：本机课题登记表，`rd init` / `rd serve` / `rd scheduler install` 自动维护，端口自动错开（8010、8011…），课题名不许重复。`rd projects` 查看。
- `machine.toml`：`max_agents`（全机同时最多几个 agent，默认 2，超出排队）、`reserve_cores`（跑数值时留给系统的核）。
- `jobs.json`：所有课题共用的数值作业登记，`rd free-cores` 看的是全机的占用。
- arXiv 扫描按课题名错开分钟，不会同时打 arXiv。

dashboard 右上角可以在本机的课题之间切换。

## 审计

每个 lab 的推导在收尾时自动交给另一个模型（`[auditor]`，Codex `gpt-6-astra`）独立审计；代码审计在 lab 页点按钮。报告在 `labs/NN/audit/`，发现只分三档：`typo`、`不严谨`、`改变结论`，并明确不吹毛求疵。前两档由研究 agent 直接改（吹毛求疵的可以不予理会，但要写明），第三档开讨论让你裁决、不写薄层。lab 页、wiki 页、STATUS.md 上都有审计标记。见 `skills/rd-audit`。

## 把网址给别人看

dashboard 监听所有网卡，但**只有 `config.toml` 里 `server.write_from` 网段（默认本机 + Tailscale 100.64.0.0/10）来的请求能操作**；其他地址（校园网、公网）自动变成只读：看得到全部内容，页面上没有任何按钮，POST 一律 403。所以同一个网址可以直接给别人看，自己从 Tailscale 地址进就是完整版。要让某个固定 IP 也能操作，把它加进 `write_from`。

## 自动运行的权限与登录

`rd run` / `rd tick` 用 `claude -p --permission-mode bypassPermissions` 在课题目录里无人值守运行。护栏在 `AGENTS.md`：只写课题目录和 `data_root`，不改用户亲手写的文件，不删文件，每次运行 git commit。

**命令行版 Claude Code 必须单独登录**（桌面 app 的登录不共享给命令行）。在要跑自动任务的机器上开一个终端：

```bash
claude auth status
```

显示 `"loggedIn": false` 就运行 `claude`，在里面输入 `/login` 按提示登录，然后再 `rd run <课题目录> -p "回复 ok"` 验证。launchd 启动的任务运行在登录用户的 GUI 会话里，登录一次即可。

## 开发

```bash
.venv/bin/pytest
```
