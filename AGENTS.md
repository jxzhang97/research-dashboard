# 课题工作规则（AGENTS.md）

本文件由 research-dashboard 模板提供，所有课题通用；`rd update <课题目录>` 会用模板最新版覆盖它，**课题特有的内容不要写在这里**，写在 `PROJECT.md`（课题总纲）和 `config.toml`。Claude Code 通过 `CLAUDE.md` 引用本文件，Codex 直接读本文件。

## 0. 开始任何工作前先读

1. `PROJECT.md`：课题动机、目标、假设、必须通过的验证、核心文献。
2. `wiki/index.md` 和 `wiki/notation.md`：当前理解和记号。
3. `log.md` 最近 20 条：别人（包括上一次的你）刚做了什么。
4. 与当前任务相关的 `labs/`、`ideas/`、`discussion/` 文件。

## 1. 目录与职责

| 目录 | 放什么 | 谁写 |
|---|---|---|
| `PROJECT.md` | 课题总纲 | 用户 |
| `references/raw/` | 原始 PDF，只增不改 | agent 下载 / 用户放入 |
| `references/cards/` | 每篇文献一张卡片 `<arxiv id 或 slug>.md` | agent |
| `references/inbox/` | arXiv 扫描候选，等用户审批 | 脚本 + agent |
| `wiki/` | 当前理解的汇编，`[[双括号]]` 互链，随进展重写 | agent |
| `labs/NN-slug/` | 一个任务：`brief.md` 任务书、`report.md` 摘要、`report.pdf`、`DATA.md`、代码、图 | agent 起草，用户过目 |
| `src/` | 从 lab 沉淀出的可复用代码 | agent |
| `discussion/` | 需要用户裁决的问题，以及用户向 agent 提的问题 | 双方 |
| `ideas/` | 想法树；`ideas/inbox/` 是用户的原始速记 | 用户写原话，agent 整理 |
| `log.md` | 时间线，只追加 | 双方 |
| `.dashboard/` | 运行记录、作业登记、本机配置，不是内容 | 程序 |

## 2. 语言与写作

- 全项目默认中文；`config.toml` 的 `project.language = "en"` 时改用英文。文献卡片里的术语可以中英并列。
- **推导、讲解、总结类的内容一律用 `baby-steps-report` skill 写**：LaTeX 编译成 PDF，放在对应 lab 文件夹（`report.pdf`，或多份时按内容命名）。旁边必须有 `report.md`：几十行以内的摘要（frontmatter 里 `pdf:` 指向 PDF，正文列结论），dashboard 只显示摘要。
- 卡片、wiki、讨论、idea、日志用 markdown，公式用 `$…$` 和 `$$…$$`（网页用 KaTeX 渲染，避免只有 LaTeX 包才有的宏）。
- 正式论文不用 baby-steps-report，用 `hardworking-paper-writer`。
- 模型（`config.toml` 的 `[models]`）：默认一律 `claude-fable-5-1`、effort `max`。用户可以单独指定：任务书或 idea 的 frontmatter 写 `model:` / `effort:`，自动运行会照用；用户在对话里说"写报告用 opus"之类的，就把它写进任务书 frontmatter，并在写报告时把那部分交给对应模型的子 agent（Agent 工具的 model 参数）。

## 3. Notation

- `wiki/notation.md` 是全课题记号的唯一来源。写任何公式前先对照它；文献用了不同记号，卡片里给出对应表，正文仍用课题记号。
- 用户改了 `notation.md` 后，受影响的 wiki、卡片要同步改；已编译的旧 PDF 不重编，只在对应 `report.md` 顶部标一行"记号已于 <日期> 更新，PDF 用的是旧记号：…"。
- 发现 notation 内部矛盾或与 PROJECT.md 冲突：不悄悄改，写进 discussion 让用户裁决。

## 4. 文件纪律

- 项目内一律用相对项目根目录的路径。两台机器用户名不同（`/Users/jiaxin` 与 `/Users/jiaxinzhang`），绝对路径会断。
- **不改用户亲手写的东西**：`PROJECT.md`、`ideas/` 里「## 原话」一节、`ideas/inbox/` 的正文、`references/raw/`、用户自己的 notes。要补充就在 agent 维护区追加，要纠正就在 discussion 里说。
- 不删文件。新结果写新文件；旧结论作废时在旧文件顶部标"已被 <新文件> 取代"。
- 写文件前先看有没有同名或同主题的文件，避免重复。
- 每次任务或会话结束：`log.md` 追加一条（格式见第 9 节），然后在课题目录 `git add -A && git commit -m "<一句话>"`。
- 两台机器的 `~/Documents` 经 iCloud 同步。定时任务和 dashboard 只在 studio 上运行；两台机器不要同时让 agent 写同一课题。

## 5. 计算

- 任务书的 `machine` 字段指定在哪跑，没写就是 studio。只在用户明确说时用笔记本或集群。
- **并行不设固定预算，按当时空闲决定**：跑数值前先执行 `rd free-cores <课题目录>`，它会报告性能核数、当前负载、已登记作业，以及"现在最多再用几个核"。按它说的来，并显式设线程数（`OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、Julia `-t`、Mathematica `$ProcessorCount` 相关设置），然后 `rd jobs claim <课题目录> --cores N --label "<lab id>"` 登记，跑完 `rd jobs release <课题目录> --id <jid>`。
- 中间数据和大文件放 `config.toml` 的 `data_root`（studio 上 `~/doc_unsyn/<课题名>/<lab id>/`），项目里只留图、汇总结果和 `DATA.md`（机器、路径、内容、日期、怎么重新生成）。
- 代码能复用的放 `src/`，一次性的留在 lab 文件夹。

## 6. 任务流程

1. **想法**：用户写在 `ideas/inbox/` 或 dashboard 速记。agent 按 `rd-idea` skill 整理进想法树，原话不动。
2. **任务书**：用户请求升级（或 agent 判断该动手并征得同意）时，按 `rd-lab` skill 起草 `labs/NN-slug/brief.md`，用户原话原样保留，结合本文件和 PROJECT.md 写出目标、步骤、交付物、机器。状态 `awaiting_review`。**用户说了不用过目的，直接 `approved` 并开始。**
3. **执行**：状态改 `running`，按任务书做；推导报告按第 2 节；数值按第 5 节。
4. **收尾清单**（缺一不可）：
   - `report.md` 摘要 + PDF / 图；
   - 更新相关文献卡片的「与本课题的联系」；
   - 更新 wiki（新概念建页，旧理解改写，`index.md` 加链接）；
   - 更新来源 idea 的状态和「进展与结论」；
   - 有新问题就写 discussion；
   - `log.md` 追加；状态改 `done`；git commit。

## 7. 什么时候、怎么向用户提问

- **该问的**：两条物理上都说得通的路线要选一条；idea 有两种读法；推导结果和用户 notes 或 PROJECT.md 矛盾；需要用户补充只有他知道的信息。
- **不该问的**：能靠读文献、算一算、查 wiki 自己定的事；措辞和格式。
- 格式按 `rd-discussion` skill：背景、问题、我看到的选项（每个选项意味着接下来怎么做）、我的倾向、它卡住了什么。一个文件一个问题。
- 交互会话里可以当面问（AskUserQuestion），但得到的裁决也要落盘到 `discussion/`，否则下一次运行不知道。
- 无人值守运行（dashboard 或定时触发）时没有人回答：写 discussion，把当前任务状态改 `waiting_answer`，记 log，结束运行。用户回答后系统会再次调用。

## 8. 文献卡片

- `read_depth` 如实填：`abstract`（只读了摘要）、`skim`（翻过全文）、`full`（通读）。没读的部分不要总结。
- 「与本课题的联系」是活的：每个 lab 收尾时回头看相关卡片，补一句"lab NN 的结果表明…"。
- arXiv 候选在用户批准前只能基于摘要写理由，并注明；批准后才下载、精读、建卡。

## 9. 状态与格式速查

- lab：`draft → awaiting_review → approved → running → done`；旁路 `waiting_answer`、`blocked`、`parked`。
- discussion：`open → answered → digested → resolved`；`asked_by: agent | user`。
- idea：`seed / exploring / lab / resolved / parked / dropped`；inbox 里未整理的没有状态。
- inbox 候选：`pending → approved → ingested`，或 `rejected`。
- `log.md` 条目：`## YYYY-MM-DD HH:MM · <谁> · <做了什么>`，下一行可放链接。

## 10. 常用命令

```
rd free-cores <课题目录>                 # 现在能用几个核
rd jobs claim <课题目录> --cores N --label X / rd jobs release <课题目录> --id J
rd doctor <课题目录>                     # 断链、卡片缺节、状态异常
rd tick <课题目录>                       # 处理所有待办（回答、审批、升级）
```
