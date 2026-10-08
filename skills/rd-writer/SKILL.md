---
name: rd-writer
description: 薄层写作步（research-dashboard 课题目录内使用）：把面向读者的页面——lab 的 report.md、wiki 概念页、idea 节点的「当前回答」、STATUS.md——交给 Codex（config.toml 的 [writer]）按交接单写；研究 agent 负责写交接单、组提示词、调用 codex-write.sh、做机械检查，不核对也不改写 Codex 的文字。当 lab 收尾、讨论消化、文献入库后需要写或改写任何薄层页面时使用。
---

# rd-writer：薄层交给 Codex

**分工**：研究 agent（Claude）做研究、写厚层（notes.md、代码、数据）、写交接单；**薄层一律由 Codex 写**，研究 agent 只做机械检查，不核对科学限定、不润色文字。科学限定靠交接单里的"不能说过头"清单把关，写得够具体就够用。

## 1. 交接单（研究 agent 写）

`labs/NN-slug/handoff.md`（wiki 整体改写时放 `wiki/handoff/<日期>-<slug>.md`）。内容：

1. 读者是谁（刚进组的研究生，不认识本课题任何记号）。
2. 用户原来问什么（原话）。
3. 这次回答了什么，分三档：**已证明 / 数值支持 / 解释与猜测**，每条带适用范围（模型、参数、尺寸、方法）。
4. **哪些话不能说过头**，逐条（例如：不能说"相变"；有限尺寸的峰不能说成非解析；某参数线的结论不能推广；每个数字带 $L$ 与参数；不替用户决定待裁决的事）。
5. 材料在哪：notes 节号、表、每张图的**角色**（问题设定 / 主结果 / 机制 / 可靠性）和各面板画的是什么、颜色与标记代表什么（写作者要看图写图注，这里先把图例说清）。
6. 要写哪些文件、各用什么模板（report.md 模板见 rd-lab；wiki 模板见 rd-wiki；idea 只改「当前回答」；STATUS 只改相关行）。

## 2. 提示词（从模板填）

模板在本目录 `prompt-template.md`。固定部分不要删（读者、首屏四段、讲课体、图注具体、七条限定、只写指定文件、不跑计算、不提问、回报三件事）；填入：交接单路径、目标文件与模板、附图清单。一次调用写一到两个文件；图随提示词附上（`-i`），让 Codex 真的看着图写图注。

## 3. 调用

```bash
# 启动：立刻返回，写作在独立会话里跑（不随本次 agent 运行结束而死）
~/doc_unsyn/research-dashboard/skills/rd-writer/codex-write.sh <课题根目录> <提示词文件> <记录目录名> [图1.png 图2.png …]
# 等待：前台阻塞最多 540 秒；退出码 0 完成、7 还在跑（再调一次）、6 Codex 工具执行 fail closed、9 进程消失
~/doc_unsyn/research-dashboard/skills/rd-writer/codex-write.sh --wait <课题根目录> <记录目录名> 540
# 只看状态
~/doc_unsyn/research-dashboard/skills/rd-writer/codex-write.sh --status <课题根目录> <记录目录名>
```

脚本做的事（底层是 `rd codex start/wait/status`）：从 `config.toml` 的 `[writer]` 读模型与强度；自动挑可用的 codex（优先 ChatGPT.app 自带的、旁边有 `codex-code-mode-host` 的；没有 host 的独立二进制会 fail closed，输出里出现这句就判失败）；`codex exec -C <根> -m <model> -c model_reasoning_effort=<effort> -s workspace-write -i <图>… -o last_message.txt "<提示词>" < /dev/null`；把提示词、完整输出、最后回复、`job.json`（pid）和 `run_info.txt`（模型、强度、起止时间、耗时、退出码）存到 `.dashboard/writing/<记录目录名>/`。也可用环境变量 `CODEX_BIN` 指定可执行文件。

**等的规矩**：不要用 run_in_background 启动、不要靠"等通知"（本次运行一结束它们就被清掉）；用 `--wait`，Bash timeout 设 600000，循环到退出码不是 7。几份页面可以一起启动（各自一个记录目录名），再逐个 `--wait`。退出码 9 或 6 就换个记录目录名重启一次。万一必须在写作结束前退出，先把记录目录名写进 `labs/NN-slug/resume.md` 续跑单，系统会派续跑运行接着做机械检查。

已知的坑：`codex exec` 必须 `< /dev/null`，否则会停在 "Reading additional input from stdin" 不动；0.160 的 `exec` 不认 `--full-auto`，用 `-s workspace-write`；输出开头的 `skills scan reached its traversal limit` 是无害的；每台机器要各自 `codex login`（ChatGPT 账号），`codex login status` 能看。

## 4. 机械检查（研究 agent 做，只做这些）

- 目标文件存在、frontmatter 完整、长度在模板范围内。
- 没碰别的文件：`git status --short` 只有目标文件（和 `.dashboard/writing/`）。
- 图和链接能打开：图路径相对正确（report.md 相对 lab 目录，wiki 页相对 `wiki/`）；`rd doctor <课题目录>` 无断链。
- idea 节点的「## 原话」一字未动（`git diff` 看）。
- 记 log：写了哪些文件、记录目录名、耗时。

不做：逐句核对科学限定、改写措辞、补数字。发现交接单漏了限定导致写过头：改交接单，再让 Codex 重写那一段，不要自己改文字。

## 5. Codex 不可用时

没装、没登录、调用失败：在 log 写明原因，lab 状态按情况 `blocked` 或保持，薄层留到下次运行；**不用别的模型代写薄层**。安装：`npm install -g @openai/codex`；登录：在那台机器上 `codex login`（浏览器）或 `codex login --device-auth`。
