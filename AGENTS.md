# 课题工作规则（AGENTS.md）

本文件由 research-dashboard 模板提供，所有课题通用；`rd update <课题目录>` 会用模板最新版覆盖它，**课题特有的内容不要写在这里**，写在 `PROJECT.md`（课题总纲）和 `config.toml`。Claude Code 通过 `CLAUDE.md` 引用本文件，Codex 直接读本文件。

## 0. 开始任何工作前先读

1. `PROJECT.md`：课题动机、目标、假设、必须通过的验证、核心文献。
2. `STATUS.md`：课题现在到哪了（问题、当前回答、在跑什么、等用户决定什么）。
3. `wiki/index.md` 和 `wiki/notation.md`：概念页目录和记号。
4. `log.md` 最近 20 条：别人（包括上一次的你）刚做了什么。
5. 与当前任务相关的 `labs/`、`ideas/`、`discussion/` 文件。

## 1. 目录与职责

| 目录 | 放什么 | 谁写 |
|---|---|---|
| `PROJECT.md` | 课题总纲 | 用户 |
| `STATUS.md` | 课题状态：研究问题树、每个问题的当前回答、进行中、等用户决定；每次收尾**重写**，不追加 | agent |
| `references/raw/` | 原始 PDF，只增不改 | agent 下载 / 用户放入 |
| `references/cards/` | 每篇文献一张卡片 `<arxiv id 或 slug>.md` | agent |
| `references/inbox/` | arXiv 扫描候选，等用户审批 | 脚本 + agent |
| `wiki/` | 概念页：对一个概念"我们现在怎么理解"，`[[双括号]]` 互链，随进展重写 | agent |
| `labs/NN-slug/` | 一个任务：`brief.md` 任务书、`report.md` 摘要（Codex 写）、`notes.md` 推导与讲解、`handoff.md` 交接单、`DATA.md`、代码、`fig/` | agent 起草，用户过目 |
| `src/` | 从 lab 沉淀出的可复用代码 | agent |
| `discussion/` | 需要用户裁决的问题，以及用户向 agent 提的问题 | 双方 |
| `ideas/` | 问题树；`ideas/inbox/` 是用户的原始速记 | 用户写原话，agent 整理 |
| `log.md` | 时间线，只追加 | 双方 |
| `.dashboard/` | 运行记录（含 `writing/` 里 Codex 写作步的提示词与输出）、作业登记、本机配置，不是内容 | 程序 |

## 2. 写给谁、写在哪、写多少

**读者**：面向读者的页面（`STATUS.md`、`report.md`、wiki 页、idea 节点）假定读者是刚进组的研究生：懂二次量子化、知道 DMRG 大概是什么，**不认识本课题的任何记号，也没看过任何一次运行**。写之前先想这个人。

**两层内容，两种写法：**

- **厚层**（`notes.md`、代码、数据、验证脚本）：由做推导或跑数值的那个 agent 在同一上下文里写，按 `rd-notes` skill（问题链、无跳步、落盘验证），可以长，可以密。
- **薄层**（`report.md`、wiki 页、idea 节点的「当前回答」、`STATUS.md`）：**单独一步，交给 Codex 写**（`config.toml` 的 `[writer]`，默认 `gpt-6-astra`、reasoning effort xhigh、ChatGPT 账号登录），流程见 `rd-writer` skill：研究 agent 写交接单（`labs/NN-slug/handoff.md`：这次回答了什么、改变了什么认识、哪些话不能说过头、材料在哪、每张图的角色），用 `codex-write.sh` 调 Codex，写完**只做机械检查**（文件在指定位置、没碰别的文件、图和链接能打开、`rd doctor` 无断链），**不核对、不改写它的文字**；科学限定靠交接单的"不能说过头"清单把关。Codex 不可用（没装、没登录）时记 log、把薄层留到下次，不用别的模型代写。

**薄层首屏固定四段**，顺序不变：

1. **问题**：这页要回答什么，一两句。
2. **当前回答**：一到三句能直接理解的判断，带适用范围（模型、参数、尺寸、方法）。
3. **为什么信**：一张主图加一句"看哪里、看到什么、说明什么"，或一条链接到 notes 对应小节。
4. **边界**：会改变判断的未完成检查、已知的局限。

首屏之后才是细节。数字在薄层里每个论断最多出现一个代表值，其余放表格或 notes 并链接。lab 标题不超过二十个字，长的写进副标题或 `report.md` 的「问题」。

**wiki 页像讲课，不像报告**：「我们现在怎么理解」先给图像再给公式，用一个课堂例子（toy）把概念说透，每个论断后面跟一句"这意味着什么 / 排除了什么 / 与原问题的关系"，可以直接对读者说话（"你可以这样想"）；少罗列、不重复 lab 报告的结论清单，数字和证据一句话链接到 lab。

**图注要具体**：按"看哪里 → 看到什么 → 说明什么 / 不能说明什么"写，落到面板 (a)(b)(c)、曲线或标记（颜色、实心/空心、方块/圆点）、参数区间或色带、眼睛该看到的形状（峰、平台、陡降、重合、贴零）。写作者必须看着图写，看不清的不写。

**每样东西只写一次。** 一个事实只有一个权威位置，别处用一句话加链接：

| 事实 | 权威位置 | 别处怎么提 |
|---|---|---|
| 数字、表格、收敛检查 | lab 的 `notes.md` / `results/` | 一个代表值 + 链接 |
| 推导 | lab 的 `notes.md`；可复用的通用推导可移到 wiki 页的详细节 | 结论一句 + 链接到小节 |
| 对一个概念的当前理解 | wiki 页 | 链接 |
| 一个问题的当前回答 | idea 节点「当前回答」（frontmatter `verdict:` 是它的一句话结论，卡片上显示） | `STATUS.md` 引用一句 |
| 决定及理由 | discussion | 链接 |
| 发生了什么 | `log.md` | 不复制 |

收尾时**改写**受影响页面的当前回答，不要往每个页面追加一段同样的进度。卡片「与本课题的联系」每个 lab 最多两三句，不抄数字。

**语言与格式**：全项目默认中文；`config.toml` 的 `project.language = "en"` 时改用英文。推导和讲解写 markdown（`rd-notes`），公式用 `$…$` 和 `$$…$$`（网页用 KaTeX 渲染，不用自定义宏，编号用 `\tag{}`）。PDF 和英文版都**按需**生成（用户要分享、打印或明确要求时），不是完成任务的条件。正式论文用 `hardworking-paper-writer`，不用 rd-notes。

**专有名词中英并列**：读者可能只认识英文术语。所有面向读者的页面和 notes 里，专有名词、方法名、物理量名**首次出现时写成「中文（English）」**，例如 非稳定子性（magic / nonstabilizerness）、稳定子态（stabilizer state）、鲁棒性（robustness of magic）、费米子高斯态（fermionic Gaussian state）、混态（mixed state）、自然占据数（natural occupation number）；`notation.md` 登记记号时也附英文名；同一页后面可以只用其中一种。

**图**：每个 lab 的图放 `labs/NN-slug/fig/`，PNG 或 SVG，`report.md` 和 `notes.md` 用 `![图注](fig/xxx.png)` 内嵌，图注写"看哪里 → 看到什么 → 说明什么"，网页上 alt 文字就是图注。图分四种角色：问题设定、主结果、机制解释、可靠性检查；首屏只放主结果和设定。wiki 概念页尽量配一张示意图（`wiki/fig/<slug>-*.svg|png`）。数据图用 matplotlib（`savefig(..., dpi=160, bbox_inches="tight")`），示意图手画 SVG 或 matplotlib；每张图坐标轴有标签和单位；原始数据和脚本留在 lab 文件夹。

**模型**：`[models].read` 跑研究（默认 `claude-fable-5-1`、effort `xhigh`）；`[writer]` 写薄层（默认 `backend = "codex"`、`model = "gpt-6-astra"`、`reasoning_effort = "xhigh"`，跑自动任务的机器上要先 `codex login`）。用户可以在任务书或 idea 的 frontmatter 写 `model:` / `effort:` 单独指定研究模型；用户在对话里说"写报告用 X"之类的，写进任务书 frontmatter。

## 3. Notation

- `wiki/notation.md` 是全课题记号的唯一来源。写任何公式前先对照它；文献用了不同记号，卡片里给出对应表，正文仍用课题记号。
- 用户改了 `notation.md` 后，受影响的 wiki、卡片、notes 要同步改；已导出的旧 PDF 不重编，只在对应 `report.md` 顶部标一行"记号已于 <日期> 更新，PDF 用的是旧记号：…"。
- 发现 notation 内部矛盾或与 PROJECT.md 冲突：不悄悄改，写进 discussion 让用户裁决。

## 4. 文件纪律

- 项目内一律用相对项目根目录的路径。两台机器用户名不同（`/Users/jiaxin` 与 `/Users/jiaxinzhang`），绝对路径会断。
- **不改用户亲手写的东西**：`PROJECT.md`、`ideas/` 里「## 原话」一节、`ideas/inbox/` 的正文、`references/raw/`、用户自己的 notes。要补充就在 agent 维护区追加，要纠正就在 discussion 里说。
- **不替用户发明研究方向**：问题树里只放用户说过的问题和它们的直接拆分；agent 自己想到的方向写在节点的「agent 备注」或 discussion，标明"agent 建议"，用户认可后才成为节点。
- 不删文件。新结果写新文件；旧结论作废时在旧文件顶部标"已被 <新文件> 取代"。
- 写文件前先看有没有同名或同主题的文件，避免重复。
- 每次任务或会话结束：`log.md` 追加一条（格式见第 9 节），然后在课题目录 `git add -A && git commit -m "<一句话>"`。
- 两台机器的 `~/Documents` 经 iCloud 同步。定时任务和 dashboard 只在 studio 上运行；两台机器不要同时让 agent 写同一课题。

## 5. 计算

- 任务书的 `machine` 字段指定在哪跑，没写就是 studio。只在用户明确说时用笔记本或集群。
- **并行不设固定预算，按当时空闲决定**：跑数值前先执行 `rd free-cores <课题目录>`，它会报告性能核数、当前负载、**本机所有课题**已登记的作业，以及"现在最多再用几个核"。按它说的来，并显式设线程数（`OMP_NUM_THREADS`、`MKL_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、Julia `-t`、Mathematica `$ProcessorCount` 相关设置），然后 `rd jobs claim <课题目录> --cores N --label "<lab id>" --pid <长寿命批量进程>` 登记，跑完 `rd jobs release --id <jid>`。登记表是机器级的（`~/.rd/jobs.json`），别的课题的数值也在里面，所以不同课题不会互相抢核。
- 同一台机器上可能同时有好几个课题的 dashboard 和 agent。规矩：每个课题自己的 agent 串行；全机同时最多 `~/.rd/machine.toml` 里 `max_agents` 个 agent（默认 2），超出的排队；不要跨课题写文件。
- 中间数据和大文件放 `config.toml` 的 `data_root`（studio 上 `~/doc_unsyn/<课题名>/<lab id>/`），项目里只留图、汇总结果和 `DATA.md`（机器、路径、内容、日期、怎么重新生成）。
- 代码能复用的放 `src/`，一次性的留在 lab 文件夹。

## 6. 任务流程

1. **想法**：用户写在 `ideas/inbox/` 或 dashboard 速记。agent 按 `rd-idea` skill 整理进问题树，原话不动。
2. **任务书**：用户请求升级（或 agent 判断该动手并征得同意）时，按 `rd-lab` skill 起草 `labs/NN-slug/brief.md`，用户原话原样保留，结合本文件和 PROJECT.md 写出目标、步骤、交付物、机器。状态 `awaiting_review`。**用户说了不用过目的，直接 `approved` 并开始。** 用户可以在 dashboard 的任务页对任务书写意见（追加到任务书的「## 用户意见」，原话不动）；系统会派一次 `revise_brief` 运行，agent 按意见修改任务书、在每条意见下回复，状态保持 `awaiting_review` 等用户再看。
3. **执行**：状态改 `running`，按任务书做；推导和讲解进 `notes.md`（`rd-notes`）；数值按第 5 节；中途的小结论随时写进 `report.md` 草稿。
4. **收尾**（缺一不可，但每样只写一次）：
   - 厚层齐：`notes.md`、`fig/`、`DATA.md`、`results/`；
   - 交接单 `handoff.md`，然后**薄层写作步**（第 2 节，`rd-writer`，Codex）：`report.md`、受影响的 wiki 页、来源 idea 的「当前回答」、`STATUS.md`；主 agent 只做机械检查；
   - 卡片「与本课题的联系」加两三句；wiki `index.md` 加新页链接；
   - 有新问题就写 discussion；`log.md` 追加；状态改 `done`；git commit。

## 7. 什么时候、怎么向用户提问

- **该问的**：两条物理上都说得通的路线要选一条；idea 有两种读法；推导结果和用户 notes 或 PROJECT.md 矛盾；需要用户补充只有他知道的信息。
- **不该问的**：能靠读文献、算一算、查 wiki 自己定的事；措辞和格式。
- 格式按 `rd-discussion` skill：背景、问题、我看到的选项（每个选项意味着接下来怎么做）、我的倾向、它卡住了什么。一个文件一个问题。
- 交互会话里可以当面问（AskUserQuestion），但得到的裁决也要落盘到 `discussion/`，否则下一次运行不知道。
- 无人值守运行（dashboard 或定时触发）时没有人回答：写 discussion，把当前任务状态改 `waiting_answer`，记 log，结束运行。用户回答后系统会再次调用。
- 用户的回答**不是当场消化**的：系统每 `digest_minutes`（默认五小时）把这段时间内所有已回答的讨论放进一次运行统一消化，因为用户对几个相关问题的裁决要放在一起看。消化时先通读全部回答再动手；引用别的讨论的裁决要注明。

## 8. 文献卡片

- `read_depth` 如实填：`abstract`（只读了摘要）、`skim`（翻过全文）、`full`（通读）。没读的部分不要总结。
- 「与本课题的联系」是活的：每个 lab 收尾时回头看相关卡片，补两三句"lab NN 的结果表明…"，不抄数字。
- arXiv 候选在用户批准前只能基于摘要写理由，并注明；批准后才下载、精读、建卡。

## 9. 状态与格式速查

- lab：`draft → awaiting_review → approved → running → done`；旁路 `waiting_answer`、`blocked`、`parked`。
- discussion：`open → answered → digested → resolved`；`asked_by: agent | user`。
- idea：`seed / exploring / lab / resolved / parked / dropped`；inbox 里未整理的没有状态。节点可选 `kind: question | route | method`，默认 question。
- inbox 候选：`pending → approved → ingested`，或 `rejected`。
- `log.md` 条目：`## YYYY-MM-DD HH:MM · <谁> · <做了什么>`，下一行可放链接。

## 10. 常用命令

```
rd free-cores <课题目录>                 # 现在能用几个核
rd jobs claim <课题目录> --cores N --label X --pid P / rd jobs release <课题目录> --id J
rd doctor <课题目录>                     # 断链、卡片缺节、状态异常
rd tick <课题目录>                       # 处理所有待办（回答、审批、升级）
```

## 11. 审计

- 每个 lab 的推导（`notes.md`）在收尾时由另一个模型（`config.toml` 的 `[auditor]`，Codex）独立审计一次；代码审计只在用户点按钮时做。流程和报告格式见 rd-audit skill，报告在 `labs/NN/audit/`。
- 发现分三档。`typo` 和 `不严谨` 由你直接改，改完在报告「处理」一节记一行；`改变结论` 不自己改，开讨论让用户裁决，lab 状态 `awaiting_review`，并且不写薄层。
- **什么算不严谨、什么算吹毛求疵**：不严谨 = 读者照 notes 自己重推会在这一步卡住或得出不同的适用范围（假设没交代、极限交换没检查、范围没标、记号没定义、收敛没展示）。吹毛求疵 = 换种写法更清楚、可以多加一句、记号偏好、教科书通常省略的中间步、与结论无关的细节。判据只有一条：不改，读者会被误导或结论会错吗？答不上来的发现可以不予理会，但要在「处理」里写一句为什么。
- 审计标记要挂到看得见的地方：`report.md` 的 `audits:`、wiki 页的 `audited_by:`、`STATUS.md` 问题行末尾。
