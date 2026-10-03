# research-dashboard

一个本地 web，用来管理**一个理论物理课题**的文献、当前理解、任务、讨论和想法；agent（Claude Code 或 Codex）直接读写同一套 markdown 文件。

- **文件是唯一真相**：所有内容是带 frontmatter 的 markdown，放在课题文件夹里；web 只是视图，加四个写入口（回答问题、审批文献、速记想法、立刻派任务）。
- **五个页面**：文献（卡片 + arXiv 候选审批）、Wiki（当前理解，互链）、Lab（任务书 → 报告）、讨论（agent 向你提问，你裁决）、想法（层级树 + 速记）。另有首页"需要你处理"和任务页（agent 运行日志）。
- **agent 规则是模板的一部分**：`AGENTS.md`（通用规则）+ `skills/rd-*`（各环节的工作流），Claude Code 和 Codex 都能读。
- **自动化**：用户在网页上的每个动作（回答、批准、升级、速记、立刻执行）当场触发 agent；直接在编辑器里写进 `ideas/inbox/` 或改文件状态的，dashboard 每 15 秒扫一次也会当场开始。launchd 每小时的 tick 只是 dashboard 没开时的兜底。每天扫 arXiv，候选需用户审批后才入库。同一课题同一时间只跑一个 agent，后来的排队。

## 安装（每台机器一次）

```bash
git clone https://github.com/jxzhang97/research-dashboard ~/doc_unsyn/research-dashboard
~/doc_unsyn/research-dashboard/rd install
```

`install` 会建 `.venv`、装依赖、把 `skills/rd-*` 软链接到 `~/.claude/skills`、`~/.codex/skills`、`~/.agents/skills`，并检查依赖的外部 skill `baby-steps-report` 是否已安装（它不在本仓库里：`git clone` 后软链接到 `~/.claude/skills/baby-steps-report`）。

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
├── labs/       NN-slug/ brief.md report.md report.pdf DATA.md
├── src/
├── discussion/ YYYY-MM-DD-slug.md
├── ideas/      slug.md  inbox/
├── log.md
└── .dashboard/ runs/ jobs/ machines/ state.json
```

## 工作循环

1. 你在 `ideas/inbox/` 或网页速记一个想法 → agent 整理挂到想法树（原话不改）。
2. 你点"升级为 lab" → agent 起草任务书 → 你过目批准（或事先说不用过目）→ agent 执行。
3. 执行中遇到要你裁决的问题 → 写进讨论区，任务标 `waiting_answer` → 你在网页回答 → agent 立刻继续。
4. 任务收尾：报告摘要 + PDF、回写文献卡片、更新 wiki、更新想法状态、记日志、git commit。
5. 每天 arXiv 候选进"文献"页等你审批；批准的被下载、精读、建卡。

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
