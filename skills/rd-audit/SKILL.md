---
name: rd-audit
description: 推导、代码与薄层的独立审计步（research-dashboard 课题目录内使用）：把 lab 的 notes.md（推导）或脚本与结果（代码）交给 Codex（config.toml 的 [auditor]）做独立审计，产出三档（typo / 不严谨 / 改变结论）的审计报告放在 labs/NN/audit/；研究 agent 逐条处理后让审计者对当前版本复核到 pass；薄层写完后再做一次科学一致性检查（consistency）；审计标记挂到 report.md、wiki 页和 STATUS.md。当 lab 收尾厚层写完要做推导审计、处理完发现要复核、薄层写完要做一致性检查、用户在 dashboard 点了"推导审计""代码审计""薄层一致性"、或要回应一份审计报告时使用。
---

# rd-audit：让另一个模型挑错，并且只认当前版本

**分工**：审计者是 Codex（`[auditor]`，默认 `gpt-6-astra` + xhigh），它只读、只复算、只写报告；研究 agent（Claude）组提示词、调脚本、**逐条处理发现**、让审计者复核、挂标记。审计者把 notes、代码和薄层都当成待验证的 claim，不当权威；用户自己的 notes/PDF 如果被 lab 引用，也在审计范围内。

**三种审计（kind）**：

| kind | 审什么 | 什么时候 | 谁触发 |
|---|---|---|---|
| `derivation` | `notes.md` 和它引用的 wiki 页、验证脚本与结果 | 厚层齐、交接单还没写之前自动做；处理完发现后再做一次**复核** | rd-lab C1b；lab 页按钮 |
| `code` | 脚本、`results/`、`DATA.md`、画图脚本 | 用户点按钮才做（要跑东西，耗时不可控） | lab 页按钮 |
| `consistency` | 薄层：`report.md`、本 lab 写的 wiki 页、idea 当前回答、`STATUS.md`，对照 notes、交接单、图与证据 | 薄层写完、机械检查通过之后自动做；发现处理完再做一次 | rd-lab C3b；lab 页按钮 |

**为什么要绑版本**：`codex-audit.sh` 启动时用 `--source` 声明审的是哪些文件（记哈希）、用 `--expect` 声明报告路径。作业结束后源文件再被改，这份报告就"过期"（lab 页的标记会打叉），`rd finish` 不认。所以**处理完发现一定要对当前版本复核**，不能自己标一句"已处理"就算通过。

## 1. 组提示词

从本目录 `audit-prompt.md` 填模板，存到 `labs/NN-slug/audit/prompt-<日期>-<kind>[-v2].md`。要填的：
- `{{KIND}}`：`derivation` / `code` / `consistency`；`{{KIND_ZH}}`：推导审计 / 代码审计 / 薄层一致性检查（复核时写"推导审计（复核）"）；
- `{{LAB}}`、`{{TITLE}}`、`{{BRIEF}}`（brief.md 的目标与用户原话，原样粘）；
- `{{TARGETS}}`：审什么文件（推导：`notes.md` 和它引用的 wiki 页；代码：脚本、`results/`、`DATA.md`、画图脚本；一致性：全部薄层文件，并写明"对照 notes.md、handoff.md、notation 与列明的证据"）。**复核**时在这里写明上一份报告路径、哪些发现改了、改在哪些节，请审计者重点查这些处；
- `{{CONTEXT}}`：`wiki/notation.md`、引用的文献卡片与 `references/raw/` 原文、用户的 notes/PDF（lab 引用了就列）；一致性检查还列 handoff.md、已通过的推导审计报告、验证结果；
- `{{COMMIT}}`：`git rev-parse --short HEAD`；
- `{{OUT}}`：报告路径 `labs/NN-slug/audit/<日期>-<模型>-<kind>[-v2].md`；`{{OUT_DIR}}`：它所在目录；
- `{{CORES}}`：`rd free-cores <课题目录>` 的那句话（代码审计要跑东西时照它来；一致性检查写"本次不运行数值"）。

固定部分不要删：三档定义、不吹毛求疵判据、只写 audit/ 目录、不提问、独立复算或对照、报告模板。

## 2. 调用

```bash
RD=~/doc_unsyn/research-dashboard/skills/rd-audit/codex-audit.sh
# 推导审计：--source 列审的源文件（至少 notes.md；引用的 wiki 页、验证脚本也列），--expect 报告路径
$RD <课题根> <提示词> <记录目录名> --source labs/NN-slug/notes.md --source labs/NN-slug/scripts/check.py --expect labs/NN-slug/audit/<日期>-gpt-6-astra-derivation.md
# 复核：同上，换新的记录目录名和报告路径（…-derivation-v2.md）
# 薄层一致性检查：--kind consistency；--source 覆盖 notes、handoff、report、本 lab 写的每个 wiki/idea 文件、STATUS.md
$RD <课题根> <提示词> <记录目录名> --kind consistency --source labs/NN-slug/notes.md --source labs/NN-slug/handoff.md --source labs/NN-slug/report.md --source wiki/<页>.md --source ideas/<slug>.md --source STATUS.md --expect labs/NN-slug/audit/<日期>-gpt-6-astra-consistency.md
# 等待：前台阻塞，最多 540 秒；退出码 0 完成、7 还在跑（再调一次）、6 工具执行 fail closed、9 进程消失、10 报告没产出、11 审核期间源文件被改
$RD --wait <课题根> <记录目录名> 540          # 一致性作业的等待/状态要带 CODEX_KIND=consistency 环境变量
$RD --status <课题根> <记录目录名>
```

和 `codex-write.sh` 同一套（底层是 `rd codex start/wait/status`）：读 `[auditor]` 的模型与强度，自动挑可用的 codex（优先 ChatGPT.app 自带的、旁边有 `codex-code-mode-host` 的那个），`codex exec -s workspace-write`，记录在 `.dashboard/auditing/<记录目录名>/`（`job.json` 有 pid、声明的输出和源文件哈希；`outcome.json` 有结束状态与报告 verdict）。记录目录名用 `<日期>-<lab>-<kind>[-v2]`，每次新作业换新名字。

**等的规矩**（无人值守运行尤其重要）：
- **不要用 run_in_background 启动，不要靠"等通知"。** 用上面的 `--wait`，Bash 的 timeout 设 600000，循环调用直到退出码不是 7。推导审计通常 10–20 分钟，一致性检查 5–15 分钟。
- 等的间隙可以做不依赖审计结果的收尾（C4 的卡片回写、`wiki/index.md`），但薄层不能写、被审的源文件不能改（改了作业会以 11 结束，白等）。
- 退出码 9（进程消失）或 6（fail closed）：重新启动一次（换个记录目录名）；再失败就记 log、`report.md` 的 `audits` 留空、继续收尾到能做的一步为止，**不用别的模型代审**，lab 停在 `running` 并写清续跑单（`rd finish` 不会通过）。
- 万一本次运行必须在审计结束前退出（例如额度告急）：更新 `labs/NN-slug/resume.md` 续跑单写明记录目录名，系统会在审计结束后派续跑运行接着处理报告。

Codex 不可用（没装、没登录、失败）：记 log，`report.md` 的 `audits` 留空，能做的收尾做完，lab 不能 done，**不用别的模型代审**。

## 2b. 报告长什么样

报告是给人在网页上读的（dashboard 的文档页会渲染公式）。按 `audit-prompt.md` 的格式：「总评」最多五句 → 「发现一览」一行一条按等级从重到轻 → 每条发现一个小节（问题 / 依据 / 建议）→ 「独立复算」→ 「拿不准的」。复核报告 frontmatter 多一行 `previous: <上一份报告>`。链接报告时用站内路径（dashboard 的 `#/doc/<路径>`）。

## 3. 逐条处理（研究 agent 做，这是关键一步）

读报告，对每条发现 F1…Fn 决定，并在报告末尾追加「## 处理」一节，一行一条：

| 等级 | 怎么处理 |
|---|---|
| `typo` | 直接改 notes/代码，写"已修（commit）" |
| `不严谨` | 先判断是不是**吹毛求疵**（判据见 AGENTS.md 审计一节）：是 → 写"不予处理：<一句理由>"；不是 → 补论证/标假设/补收敛检查，写"已修（commit）" |
| `改变结论`，**修正方向唯一**（符号错、漏项、展开错、精度说过头、把论证当定理、适用范围要收窄……改法只有一种） | **自己改**，重跑验证脚本，写"已修（commit）：改成了什么"。然后新开一个讨论（asked_by: agent）把所有这类修正列成一张清单请用户过目（标题"lab NN 推导审计的 n 处改变结论修正，请过目"；每条：审计说什么、改成了什么、物理表述有没有变），在 `brief.md` frontmatter 写 `pending_review: <讨论 id>`。**不停下、不改 status**：复核通过后照常写薄层、收尾；薄层由交接单告知写作者在 report「边界」和 STATUS 对应行写明"审计修正待过目，见 [[讨论]]"。用户不认可某处时，消化回答的运行再改那一处并重走复核 → 薄层。 |
| `改变结论`，**方向不唯一**（两种物理上都说得通的改法、要不要撤回一个主结果、涉及用户在 PROJECT.md 的判断） | **不自己改**。开讨论（引审计原文、你的判断、各选项意味着接下来怎么做）；`brief.md` 的 `status: waiting_answer`；**停在这里不写薄层**。 |
| 不同意审计 | 写"不同意：<理由>"，并开讨论让用户看一眼（审计者和你意见相左的地方正是用户该知道的）；只要该发现是改变结论，按上一行停下等裁决。 |

改完后：报告 frontmatter 加 `handled: true`、`handled_at`；改动的推导重新跑一遍它附带的验证脚本。`handled` 只表示**作者处理了**，不表示审计者认可。

## 3b. 复核（修改过源文件就必须做）

只要为处理发现改了被审的源文件（notes、脚本、结果），就按 §1–§2 再启动一次审计（kind 不变，记录目录名与报告加 `-v2`、`-v3`），提示词里写明上一份报告路径、改了哪些发现、改在哪些节。复核报告必须是 `verdict: pass`、不严谨与改变结论都为 0（有 typo 就处理后标 handled），`rd finish` 才认。

- 复核又报出新的发现：按 §3 处理，再复核；一般两轮内收敛。
- 复核仍坚持一条你认为吹毛求疵、或你们实质分歧的发现：开讨论请用户裁决，`status: waiting_answer`。
- 没改过源文件（全部发现都是"不予处理"且审计者原报告已是 pass/只有 typo）：不用复核，但要在「处理」里逐条写理由。

## 3c. 薄层一致性检查（consistency）

薄层全部写完、机械检查通过（rd-writer §4）之后，按 §1–§2 以 `--kind consistency` 启动。发现的处理和推导审计不同——**研究 agent 不改薄层文字**：
- `typo` / `不严谨` / `改变结论` 都先定位到交接单：是交接单漏了限定或材料指错 → 改交接单，让写作者（rd-writer）**重写对应页**；是写作者没照交接单写 → 直接让写作者按发现重写；是厚层本身的问题 → 回到 §3 改 notes 并复核推导审计，再重写薄层。
- 薄层或 notes 任何一个改了，一致性检查就过期：再做一次，直到 pass。
- 每轮在报告末尾追加「## 处理」。

## 4. 挂标记与收尾门槛

- `labs/NN-slug/report.md` frontmatter：`audits: [audit/<文件名>, …]`（最新的放最后；写作者按交接单填）。dashboard 的 lab 页据此和作业记录显示 ✅ / ⚠️ / ❌ / 已过期。
- 由这个 lab 编译出的 wiki 页 frontmatter：`audited_by: [lab:NN-slug/audit/<文件名>]`；交接单里告诉写作者在页脚加一行"依据的推导已审计（日期）：<一句总评>"。
- `STATUS.md` 对应问题行末尾加"（推导已审 ✅ / ⚠️ n / ❌；一致性 ✅）"，有 `pending_review` 的加"审计修正待过目"。
- `log.md` 一条：审了什么、几条发现各几档、处理结果、记录目录名。
- 最后 `~/doc_unsyn/research-dashboard/rd finish <课题根> <lab id>`：它核对当前版本有没有通过的推导审核与一致性报告、薄层是否由写作作业产出、doctor 是否干净，通过才把 `status` 改为 done。`rd finish --check` 只列还差什么。**不要自己把 status 改成 done。**

## 5. 等级定义（提示词和处理都按这个）

- `typo`：笔误、漏字、下标错，上下文能看出本意，后续推导没受影响。
- `不严谨`：这一步的结论是对的，但依赖没交代的假设或条件、极限/求和/积分次序交换没检查、适用范围（模型、参数、尺寸）没标、用了没定义的记号、数值结论没展示收敛性——**读者照 notes 自己重推会在这一步卡住或得出不同的适用范围**。薄层里对应：丢了交接单列明的适用条件、把数值支持写成已证明。
- `改变结论`：这一步错了，或结论并不从推导中得出，或代码算的量不是文字说的那个量，或数值不支持所声称的结论。薄层里对应：当前回答与 notes 的结论相反或超出其范围、图注与图不符。

**不是发现的东西**（审计者不该报，报了研究 agent 可不予理会）：换种写法更清楚、可以多加一句解释、记号偏好、教科书通常省略的中间步、与结论无关的细节、"建议补充一节"。判据只有一条：**不改，读者会被误导或结论会错吗？** 答不上来就不算。
