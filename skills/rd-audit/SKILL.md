---
name: rd-audit
description: 推导与代码的独立审计步（research-dashboard 课题目录内使用）：把 lab 的 notes.md（推导）或脚本与结果（代码）交给 Codex（config.toml 的 [auditor]）做独立审计，产出三档（typo / 不严谨 / 改变结论）的审计报告放在 labs/NN/audit/，研究 agent 按权限逐条处理并把审计标记挂到 report.md、wiki 页和 STATUS.md。当 lab 收尾厚层写完要做自动推导审计、用户在 dashboard 点了"推导审计"或"代码审计"、或要回应一份审计报告时使用。
---

# rd-audit：让另一个模型挑错

**分工**：审计者是 Codex（`[auditor]`，默认 `gpt-6-astra` + xhigh），它只读、只复算、只写报告；研究 agent（Claude）组提示词、调脚本、**逐条处理发现**、挂标记。审计者把 notes 和代码当成待验证的 claim，不当权威；用户自己的 notes/PDF 如果被 lab 引用，也在审计范围内。

**什么时候审**：
- 推导审计：**每个 lab 收尾时自动做**，时机在 C1（厚层齐）之后、C2 交接单之前——"改变结论"的问题不能先写进 wiki 再回头改。
- 代码审计：只在用户在 dashboard 点"代码审计"时做（它要跑东西，耗时不可控）。
- 两者都可以被用户手动再触发。

## 1. 组提示词

从本目录 `audit-prompt.md` 填模板，存到 `labs/NN-slug/audit/prompt-<日期>-<kind>.md`。要填的：
- `{{KIND}}`：`derivation` 或 `code`；
- `{{LAB}}`、`{{TITLE}}`、`{{BRIEF}}`（brief.md 的目标与用户原话，原样粘）；
- `{{TARGETS}}`：审什么文件（推导：`notes.md` 和它引用的 wiki 页；代码：脚本、`results/`、`DATA.md`、画图脚本）；
- `{{CONTEXT}}`：`wiki/notation.md`、引用的文献卡片与 `references/raw/` 原文、用户的 notes/PDF（lab 引用了就列）；
- `{{COMMIT}}`：`git rev-parse --short HEAD`；
- `{{OUT}}`：报告路径 `labs/NN-slug/audit/<日期>-<模型>-<kind>.md`；
- `{{CORES}}`：`rd free-cores <课题目录>` 的那句话（代码审计要跑东西时照它来）。

固定部分不要删：三档定义、不吹毛求疵判据、只写 audit/ 目录、不提问、独立复算、报告模板。

## 2. 调用

```bash
# 启动：立刻返回，审计在独立会话里跑（不随本次 agent 运行结束而死），打印 pid 与记录目录
~/doc_unsyn/research-dashboard/skills/rd-audit/codex-audit.sh <课题根目录> <提示词文件> <记录目录名>
# 等待：在前台阻塞，最多 540 秒；退出码 0 完成、7 还在跑（再调一次）、6 Codex 工具执行 fail closed、9 进程消失
~/doc_unsyn/research-dashboard/skills/rd-audit/codex-audit.sh --wait <课题根目录> <记录目录名> 540
# 只看状态
~/doc_unsyn/research-dashboard/skills/rd-audit/codex-audit.sh --status <课题根目录> <记录目录名>
```

和 `codex-write.sh` 同一套（底层是 `rd codex start/wait/status`）：读 `[auditor]` 的模型与强度，自动挑可用的 codex（优先 ChatGPT.app 自带的、旁边有 `codex-code-mode-host` 的那个；没有 host 的独立二进制会 fail closed，输出里有这句就判失败），`codex exec -s workspace-write`，记录在 `.dashboard/auditing/<记录目录名>/`（`job.json` 有 pid、`run_info.txt` 有开始行和结束行）。

**等的规矩**（无人值守运行尤其重要）：
- **不要用 run_in_background 启动，不要靠"等通知"。** 本次运行一结束，后台任务一起被清掉；lab 02 的审计就是这样死的。用上面的 `--wait`，Bash 的 timeout 设 600000，循环调用直到退出码不是 7。推导审计通常 10–20 分钟。
- 等的间隙可以做不依赖审计结果的收尾（C4 的卡片回写、`wiki/index.md`），但薄层不能写。
- 退出码 9（进程消失）或 6（fail closed）：重新启动一次（换个记录目录名）；再失败就记 log、`report.md` 的 `audits` 留空、继续收尾，**不用别的模型代审**。
- 万一本次运行必须在审计结束前退出（例如额度告急）：更新 `labs/NN-slug/resume.md` 续跑单写明记录目录名，系统会在审计结束后派续跑运行接着处理报告（调度器看到该 lab 的 codex 作业还活着会先等）。

Codex 不可用（没装、没登录、失败）：记 log，`report.md` 的 `audits` 留空，继续收尾，**不用别的模型代审**。

## 2b. 报告长什么样

报告是给人在网页上读的（dashboard 的文档页会渲染公式，并把带「等级」列的旧式表格自动转成一条一卡）。新报告按 `audit-prompt.md` 的格式：「总评」最多五句 → 「发现一览」一行一条按等级从重到轻 → 每条发现一个小节（问题 / 依据 / 建议，各一到三句，长推导放 `scratch/` 链接）→ 「独立复算」→ 「拿不准的」。链接报告时用站内路径（dashboard 的 `#/doc/<路径>`），不要给 `/api/file` 原文件链接。

## 3. 逐条处理（研究 agent 做，这是关键一步）

读报告，对每条发现 F1…Fn 决定，并在报告末尾追加「## 处理」一节，一行一条：

| 等级 | 怎么处理 |
|---|---|
| `typo` | 直接改 notes/代码，写"已修（commit）" |
| `不严谨` | 先判断是不是**吹毛求疵**（判据见 AGENTS.md 审计一节）：是 → 写"不予处理：<一句理由>"；不是 → 补论证/标假设/补收敛检查，写"已修（commit）" |
| `改变结论` | **不自己改**。新开一个讨论（asked_by: agent）：引审计原文、你自己的判断、两种可能的处理；`brief.md` 的 `status: awaiting_review`；首页会提醒用户。写"待用户裁决：[[讨论 id]]" |
| 不同意审计 | 写"不同意：<理由>"，并且也开讨论让用户看一眼（审计者和你意见相左的地方正是用户该知道的） |

改完 notes 后，报告 frontmatter 加 `handled: true`、`handled_at`。改动的推导要重新跑一遍它附带的验证脚本。

## 4. 挂标记

- `labs/NN-slug/report.md` frontmatter：`audits: [audit/<文件名>, …]`（最新的放最后）。dashboard 的 lab 页据此显示 ✅/⚠️/❌。
- 由这个 lab 编译出的 wiki 页 frontmatter：`audited_by: [lab:NN-slug/audit/<文件名>]`；交接单里告诉写作者在页脚加一行"依据的推导已审计（日期）：<一句总评>"。
- `STATUS.md` 对应问题行末尾加"（推导已审 ✅ / ⚠️ n / ❌）"。
- `log.md` 一条：审了什么、几条发现各几档、处理结果、记录目录名。

## 5. 等级定义（提示词和处理都按这个）

- `typo`：笔误、漏字、下标错，上下文能看出本意，后续推导没受影响。
- `不严谨`：这一步的结论是对的，但依赖没交代的假设或条件、极限/求和/积分次序交换没检查、适用范围（模型、参数、尺寸）没标、用了没定义的记号、数值结论没展示收敛性——**读者照 notes 自己重推会在这一步卡住或得出不同的适用范围**。
- `改变结论`：这一步错了，或结论并不从推导中得出，或代码算的量不是文字说的那个量，或数值不支持所声称的结论。

**不是发现的东西**（审计者不该报，报了研究 agent 可不予理会）：换种写法更清楚、可以多加一句解释、记号偏好、教科书通常省略的中间步、与结论无关的细节、"建议补充一节讨论"。判据只有一条：**不改，读者会被误导或结论会错吗？** 答不上来就不算。
