/* Optional English reading layer. All writes and workflow state use the original API. */
(() => {
  const requested = new URLSearchParams(location.search).get("lang") === "en" ? "en" : "zh";
  let catalog = { enabled: false, documents: {} };
  let loading = null;
  const english = () => catalog.enabled && requested === "en";
  const url = (lang) => { const u = new URL(location.href); u.searchParams.set("lang", lang); return u.href; };
  const words = {
    "pod（studio 只做后处理与画图）":"pod (postprocessing and plotting on studio)",
    "问题：":"Question: ",
    "已升级为":"Research task created:",
    "加载失败：":"Could not load: ",
    "过目即可，不卡任务。":"For review; this does not block the task.",
    "放行后 agent 下次运行就回答；回答只写进这条讨论，不改 wiki 或 lab。":"Once approved, the research agent will answer here in its next session. The answer is saved in this discussion; Wiki and Lab pages are unchanged.",
    "放行后 agent 下次运行把它整理进问题树（原话不改）。":"Once approved, the research agent will organize this submission into the idea tree, preserving the original wording.",
    "放行，交给 agent 整理":"Approve for organization", "已放行":"Approved",
    "已放行，agent 已整理":"Approved and organized", "已放行，等 agent 整理":"Approved; awaiting organization",
    "发现待处理":"Findings awaiting action", "发现已处理":"Findings addressed", "无待处理发现":"No findings awaiting action",
    "← 回到 lab":"← Back to Lab",
    "任务书等你过目":"Research plan awaiting your review",
    "任务卡在一个问题上，见讨论":"The task is waiting for a decision; see the discussion",
    "任务完成，未查看":"Task completed; not yet viewed", "任务受阻，未查看":"Task blocked; not yet viewed",
    "审计修正已按唯一方向改并复核通过，过目即可，不卡任务":"Audit corrections have been made and independently reviewed; your review does not block the task",
    "还没有":"Not yet available:",
    "（课题状态页）。agent 在下次收尾时会建立它；也可以":" (project status page). It will be created when the research agent next completes a task. You can also use",
    "补一个空模板。":"to add an empty template.",
    "Reading language / 阅读语言":"Reading language",
    "agent 向你提问，等你回答":"The research agent is waiting for your answer",
    "把这个网址丢给任何 AI，它顺着链接就能读完全部内容":"Share this address with an AI assistant to access the project content through its links.",
    "只读摘要":"Abstract only", "略读":"Skimmed", "精读":"Read in full", "阅读深度未填":"Reading depth not recorded",
    "阅读深度：只读摘要":"Reading depth: abstract only", "阅读深度：略读":"Reading depth: skimmed", "阅读深度：精读":"Reading depth: read in full", "阅读深度：未填":"Reading depth: not recorded",
    "没有待审批的候选。每天定时扫描，通过的才会精读入库。":"No candidates await approval. The daily scan adds candidates; only approved papers are read in full and added to the library.",
    "卡片":"Reference notes", "还没有卡片":"No reference notes yet", "已通过，agent 将下载并精读":"Approved. The paper will be downloaded and read in full.",
    "通过，下载并精读":"Approve and read in full",
    "首页":"Overview", "文献":"References", "讨论":"Discussions", "想法":"Ideas", "任务":"Activity", "课题":"Project",
    "加载中…":"Loading…", "目录":"Contents", "全文":"Full page", "课题状态":"Project overview", "课题总纲":"Project aims",
    "草稿":"Draft", "待过目":"Awaiting review", "已批准":"Approved", "进行中":"In progress", "等你回答":"Awaiting your answer",
    "完成":"Completed", "受阻":"Blocked", "搁置":"On hold", "萌芽":"New question", "探索中":"Under investigation", "已立 lab":"Research task created",
    "已解决":"Resolved", "否决":"Dropped", "待回答":"Awaiting an answer", "已回答":"Answered", "已消化":"Answers incorporated",
    "待审批":"Awaiting approval", "已拒绝":"Rejected", "已入库":"Added to library", "未整理":"Unsorted", "排队":"Queued", "失败":"Failed", "已停止":"Stopped",
    "推导审计":"Derivation review", "代码审计":"Code review", "薄层一致性":"Summary consistency review", "已过期":"Out of date",
    "审计修正待过目":"Review the audit corrections", "过目即可":"For review", "还没审计":"Not yet reviewed",
    "运行中断·等续跑":"Paused; awaiting continuation", "需要你处理":"Needs your attention", "没有待处理的事":"Nothing needs attention",
    "agent 与数值":"Research activity", "agent 空闲":"Research agent idle", "任务页":"Activity", "没有登记中的后台数值":"No registered numerical jobs",
    "文献卡片":"Reference notes", "wiki 页":"Wiki pages", "问题":"Questions", "你问 agent":"Question for the research agent", "agent 问你":"Question for the project owner",
    "向 agent 提问":"Ask the research agent", "向 agent 提问（访客投稿）":"Ask a question as a guest", "标题":"Title", "你的名字":"Your name",
    "你的名字（必填）":"Your name (required)", "问题内容，可以写公式 $…$":"Your question. Use $…$ for equations.",
    "提交":"Submit", "提交问题":"Submit question", "提交回答":"Submit answer", "你的回答":"Your answer", "补充":"Add a comment",
    "标记已解决":"Mark resolved", "相关问题":"Related question", "现在就消化":"Incorporate answers now",
    "等你放行（访客提问）":"Guest questions awaiting approval", "等 agent 回答":"Awaiting the research agent",
    "你已回答，等待统一消化":"Answered; awaiting incorporation", "agent 已消化":"Answers incorporated into the research record",
    "过目即可 · 审计修正清单（对应任务已修正、复核通过并收尾，不卡任务）":"Audit corrections for review (the work has been corrected and completed)",
    "留下名字和问题。课题负责人放行后 agent 才会回答，回答会出现在这条讨论页里。":"Leave your name and question. Once the project owner approves it, the research agent will respond in this discussion.",
    "还没有讨论。agent 在遇到需要你裁决的问题时会在这里提问。":"There are no discussions yet. Questions requiring the project owner's decision will appear here.",
    "写下你的裁决或想法。回答不会当场处理：agent 每五小时把这段时间的所有回答放在一起统一消化（讨论列表页可以手动“现在就消化”）。":"Enter your decision or comment. Answers are incorporated together on the scheduled review cycle, rather than immediately. You can also start this from the discussion list.",
    "只读：这个地址只能看，不能操作":"Read-only access: project controls are disabled.",
    "切换课题…":"Switch project…", "交接单":"Writing brief", "续跑单":"Continuation notes", "对任务书的意见":"Comments on the research plan",
    "提交意见":"Submit comments", "原话会原样追加到任务书的「用户意见」一节":"Your comment will be saved verbatim in the research plan.",
    "数据去向 DATA.md":"Data locations (DATA.md)", "还没有报告摘要（report.md）。":"No research summary is available yet.",
    "每个任务一个文件夹：任务书 brief.md、摘要 report.md（首屏：问题 / 当前回答 / 为什么信 / 边界）、推导与分析 notes.md、数据去向 DATA.md。想法页里可以把问题升级成 lab。":"Each research task has a plan, a summary, detailed notes, and data documentation. Summaries explain the question, current answer, evidence, and limitations.",
    "这个 lab 还没有图（agent 应把图放在 fig/ 并嵌进 report.md）。":"No figures are available for this research task yet.",
    "还没有任务":"No research tasks yet", "批准，开始执行":"Approve and start", "恢复为待过目":"Return to review",
    "通过":"Approve", "拒绝":"Reject", "只读":"Read-only", "已提交":"Submitted", "先写意见":"Enter a comment first",
    "标题和内容都要填":"Enter both a title and a question", "请留下你的名字":"Please enter your name",
    "已提交，等课题负责人放行":"Submitted; awaiting the project owner's approval",
    "放行，让 agent 回答":"Approve this question", "给 AI 读":"Machine-readable source (Chinese)",
    "agent 消化了你的回答":"Your answer has been incorporated into the research record",
    "agent 向你问问题，等你回答":"The research agent is waiting for your answer",
    "arXiv 候选，等你审批":"arXiv candidate awaiting approval",
    "已开始统一消化":"The scheduled review of answers has started", "消化已在队列里":"The review of answers is already queued",
    "已记录":"Saved", "已放行，agent 下次运行回答":"Approved. The research agent will answer on its next run.",
    "原文件":"Original file", "同文件夹":"In this folder",
    "左侧选择一页。wiki 是当前理解的汇编，由 agent 维护并随进展重写；[[双括号]] 互相链接。课题到哪了看":"Choose a page on the left. The Wiki explains our current understanding and links related concepts. For project progress, see the ",
    "还没有页面":"No pages yet", "依据已审计":"Supporting work reviewed",
    "问题树":"Ideas", "路线":"Research approach", "方法":"Method", "缩小":"Zoom out", "放大":"Zoom in",
    "按宽度适应":"Fit to width", "实际大小":"Actual size", "适应":"Fit", "全部展开":"Expand all", "只看选中分支":"Selected branch",
    "画布比窗口宽，可以横向滚动或缩小":"Scroll horizontally or zoom out to see the rest of the tree.",
    "还没有当前回答":"No current answer yet", "当前回答":"Current answer", "未回答":"Unanswered", "关闭 ✕":"Close ✕",
    "完整页面 ↗":"Full page ↗", "关键证据与链接":"Key evidence and links", "子问题":"Subquestions", "原话与历史":"Original wording and history",
    "原话":"Original wording", "agent 的理解":"Research interpretation", "历史":"History", "派生":"Derived questions", "agent 备注":"Research notes",
    "记下":"Save", "投稿":"Submit", "升级为 lab 任务":"Create a research task", "让 agent 起草任务书":"Request a research plan",
    "给任务书的补充说明（可空）；写「不用过目」则直接执行":"Optional instructions for the research plan. Say “no review needed” to authorize immediate execution.",
    "速记一个想法：模糊的也行，原话会被原样保存；agent 会整理挂到树上，不会改你的话。":"Capture an idea, even if it is tentative. Your wording will be saved as written and organized into the idea tree.",
    "访客投稿：留下名字和想法，原话会原样保存；课题负责人放行后 agent 才会整理挂到问题树上。":"Guest submissions: leave your name and idea. Your wording is saved as written; the project owner must approve it before it is added to the idea tree.",
    "你的想法或问题：模糊的也行。":"Your idea or question; tentative thoughts are welcome.",
    "任务已在进行：意见会记进任务书，agent 下次运行时先读它。":"This task is already in progress. Your comment will be saved with the plan for the next research session.",
    "写下你对这份任务书的意见（要改什么、加什么、删什么）。提交后 agent 会按意见修改任务书并在意见下回复，改完仍等你过目；写「可以开始」就直接执行。":"Describe any changes, additions or removals you want. The plan will be revised for your review. Say “ready to start” to authorize execution.",
    "上次运行已结束但任务没收尾；系统会自动派续跑（额度用尽时等重置）":"The previous session ended before completion. Work will resume automatically when available.",
    "改变结论的审计发现已按唯一方向修正并复核通过；不认可就在讨论里说":"Corrections affecting the conclusions have been made and reviewed. Raise any disagreement in the discussion.",
    "rd jobs claim / rd cluster submit 登记的作业；结束后调度器派续跑":"Registered numerical jobs. Research work resumes when a job finishes.",
    "已记下":"Saved", "已请求":"Requested", "已投稿，等课题负责人放行":"Submitted; awaiting project-owner approval.",
    "已记下，agent 下次运行会读到":"Saved for the next research session.", "已记下，agent 开始按意见修改任务书":"Saved. Revision of the research plan has started.",
    "已批准，agent 开始执行":"Approved. Work is starting.",
    "studio（一、二期）+ pod（三期 L=9）":"studio (phases 1–2) + pod (phase 3, L=9)",
    "薄层写作尚未通过独立写作作业完成（codex-write.sh 启动时要用 --expect 声明每个输出文件，含 report.md）":"The reader-facing pages have not yet been completed through an independent writing job. Each output, including report.md, must be registered with --expect.",
    "审计修正清单，过目即可，不卡任务：认可就回答“认可”，不认可指出哪一处":"Audit corrections for review. Confirm acceptance or identify the correction you disagree with.",
    "立刻执行":"Start a task", "运行":"Run", "处理所有待办":"Process pending tasks", "状态":"Status",
    "空闲":"Idle", "停止":"Stop", "提示词":"Task instructions", "日志":"Log", "默认":"default",
    "还没有运行记录":"No task history yet", "已请求停止":"Stop requested", "队列里已有待办处理":"Pending tasks are already queued",
    "直接告诉 agent 要做什么（在课题目录里无人值守运行，遵守 AGENTS.md）":"Describe the task. The research agent will work independently in the project folder, following AGENTS.md.",
    "标签（针对某个 lab 的写 manual:<lab id>）":"Label (manual:<lab id> for a lab)",
  };
  const substitutions = [
    [/^找不到 /, "Not found: "], [/^加载失败：/, "Could not load: "],
    [/^只读：这个地址只能看，不能操作；但可以留名字投想法、向 agent 提问$/, "Read-only access. You can submit ideas or questions as a guest by leaving your name."],
    [/对应任务已按唯一方向修正、复核通过并收尾[:：]?/, "The related task has been corrected, reviewed and completed: "],
    [/ · 另 (\d+) 项过目即可/, " · $1 additional items for review"], [/，排队 (\d+)/, "; queued: $1"],
    [/^(\d+) 条回答$/, "$1 answers"], [/^等待统一消化，预计 /, "awaiting review, expected around "],
    [/^访客 (.+) 的投稿，等你放行$/, "Submission from $1, awaiting approval"],
    [/^访客 (.+) 的投稿$/, "Submission from $1"], [/^访客 (.+) 的提问，等你放行$/, "Question from $1, awaiting approval"],
    [/^访客 (.+) 投了想法，等你放行$/, "Idea submitted by $1, awaiting approval"],
    [/^访客 (.+) 向 agent 提问，等你放行$/, "Question from $1, awaiting approval"],
    [/^这是 lab (.+) 的审计修正清单：改变结论的发现修正方向唯一，agent 已经改好、经审计者复核通过并完成收尾。认可就在下面回答“认可”（消化后讨论关闭）；不认可指出哪一处，agent 会改那一处并重走复核与薄层。$/, "These are the audit corrections for lab $1. Findings affecting the conclusions had unambiguous corrections, which have been made and independently reviewed, and the task is complete. Reply below to confirm acceptance; the discussion will close after the response is incorporated. If you disagree, identify the correction so it can be revised and reviewed again."],
    [/❌ 有改变结论的发现/, "❌ Findings affect the conclusions"], [/⚠️ 有不严谨之处/, "⚠️ Missing qualifications"], [/✅ 通过/, "✅ Passed"],
    [/^agent 空闲(?=\s|$)/, "Research agent idle"], [/ · (\d+) 核(?=\s|$)/g, " · $1 cores"],
    [/^· 给 AI 读：$/, "· Machine-readable source (Chinese): "],
    [/^已处理 (\d+)$/, "Processed: $1"], [/^来源：/, "Source: "], [/ · 命中 /, " · Matched terms: "], [/作者[:：]/g, "Author: "],
    [/^模型（空 = 默认）$/, "Model (project default)"], [/^effort（空 = 默认）$/, "Reasoning effort (project default)"],
    [/^模型（空 = (.+)）$/, "Model (default: $1)"], [/^effort（空 = (.+)）$/, "Reasoning effort (default: $1)"],
    [/^· 正在运行$/, "· Running"], [/^· 空闲$/, "· Idle"], [/^· 排队 /, "· Queued: "],
    [/^已加入队列，待办 (\d+) 项$/, "Queued. Pending tasks: $1"], [/^出错了：/, "Error: "],
    [/^本机 (\d+) 个性能核，当前负载 ([\d.]+)，所有课题已登记 (\d+) 核/, "Local performance cores: $1; current load: $2; cores reserved by jobs across all projects: $3"],
    [/（其中别的课题 (\d+) 核）/, " ($1 for other projects)"],
    [/，留 (\d+) 核；现在最多再用 (\d+) 核。/, "; system reserve: $1 cores. Maximum additional cores available now: $2."],
    [/另有 (\d+) 个集群作业（(\d+) 核，不占本机）。/, "Cluster jobs: $1 ($2 cores; no local cores used)."],
    [/核在打架：(\d+) 个数值进程共 (\d+) 个线程在跑，超过 (\d+) 个性能核。减少并行数（WORKERS）或每个进程的线程数（Julia -t、OPENBLAS\/MKL\/OMP_NUM_THREADS）。/, "CPU oversubscription: $1 numerical processes have $2 running threads, exceeding $3 performance cores. Reduce parallel workers (WORKERS) or threads per process (Julia -t, OPENBLAS/MKL/OMP_NUM_THREADS)."],
    [/CPU 的 system 占比 ([\d.]+)%（user ([\d.]+)%）：这么高多半是线程超额争抢（自旋、调度）或内存压缩\/交换在吃 CPU，不是在算数。先查上面的线程数和下面的内存。/, "CPU time: $1% system, $2% user. High system usage often indicates thread contention or memory compression/swapping. Check thread counts and memory usage before adding jobs."],
    [/内存吃紧：可用 ([\w.]+)%，压缩区 ([\d.]+) GB、交换区已用 ([\d.]+) GB（物理内存 ([\d.]+) GB）。再加并行只会更慢；减少同时跑的作业数。/, "Memory pressure: $1% available; $2 GB compressed; $3 GB swap used; $4 GB physical memory. Reduce concurrent jobs."],
    [/Memory pressure: None% available;/, "Memory pressure: available-memory percentage unknown;"],
    [/^← 讨论$/, "← Discussions"], [/^← 文献$/, "← References"], [/^← 任务$/, "← Activity"],
    [/^创建：/, "Created: "], [/^更新：/, "Updated: "], [/^课题状态 · 更新 /, "Project overview · Updated "],
    [/^相关任务 /, "Related task "], [/^来自问题：/, "Related question: "], [/^机器：/, "Machine: "],
    [/^审计：/, "Reviews: "], [/^历史：/, "History: "], [/^全部图 \((\d+)\)$/, "All figures ($1)"],
    [/^文件 \((\d+)\)$/, "Files ($1)"], [/^任务书 brief.md/, "Research plan (brief.md)"],
    [/^📖 推导与分析 /, "📖 Detailed notes (Chinese) "], [/^最近动态（(\d+) 条）$/, "Recent activity ($1 entries; Chinese)"],
    [/^只读 · /, "Read-only · "], [/^需要你处理/, "Needs your attention"], [/^agent 正在运行：/, "Research agent running: "],
    [/^后台数值：/, "Numerical jobs: "], [/^数值作业：/, "Numerical jobs: "], [/^ · 给 AI 读：$/, " · Machine-readable source (Chinese): "],
    [/^\(\d+\)$/, "$&"], [/^（未启动）$/, " (offline)"], [/^ ·待处理$/, " · awaiting action"],
    [/^访客 (.+) 问 agent( · 等你放行)?$/, "Guest question from $1"],
    [/^讨论 /, "Discussion "], [/^收尾门槛（rd finish）还差$/, "Remaining completion checks"],
    [/^(\d+) 条回答等待统一消化$/, "$1 answers awaiting review"],
    [/^已提交，将在 (.+) 左右与其他回答一起消化$/, "Submitted. Your answer will be reviewed with the other answers around $1."],
    [/^· 为了把互相关联的回答放在一起考虑，agent 每 (\d+) 分钟消化一次，下次约 (.+)。$/, "· Related answers are reviewed together every $1 minutes. Next review: $2."],
    [/^访客 (.+) 问 agent（已放行）$/, "Guest question from $1 (approved)"],
    [/^访客 (.+) 问 agent（等放行）$/, "Guest question from $1 (awaiting approval)"],
    [/^agent 问你(?=\s*·|$)/, "Question for the project owner"],
    [/^你问 agent(?=\s*·|$)/, "Question for the research agent"],
    [/^← 问题树$/, "← Ideas"], [/^上级：/, "Parent: "], [/^相关：/, "Related: "], [/^反向链接：/, "Linked from: "],
    [/^▾ 收起$/, "▾ Collapse"], [/^▸ (\d+) 个子问题$/, "▸ $1 subquestions"],
    [/^(\d+) 个节点 · (\d+) 个显示中 · /, "$1 ideas · $2 visible · "],
    [/自动：只展开选中分支$/, "Auto: selected branch"], [/自动：全部展开$/, "Auto: expand all"],
    [/全部展开$/, "Expand all"], [/只看选中分支$/, "Selected branch"],
    [/^已升级为 /, "Research task created: "], [/^已请求升级（(.+)），agent 正在起草任务书。$/, "Research plan requested ($1); preparation is in progress."],
    [/ · 有你的意见待 agent 处理$/, " · comments awaiting review"],
    [/推导审计/g, "Derivation review"], [/代码审计/g, "Code review"], [/薄层一致性/g, "Summary consistency review"],
    [/改变结论/g, "conclusion-changing findings"], [/不严谨/g, "missing qualifications"], [/已过期/g, "Out of date"],
    [/ · 审核后源文件又改过，要重审$/, " · source changed; a new review is needed"], [/ · 发现未处理$/, " · findings awaiting action"],
    [/ ·待处理$/, " · awaiting action"], [/^已加入队列：/, "Queued: "],
    [/^缺少 (.+)$/, "Missing $1"],
    [/^(推导审核|薄层一致性检查): 没有覆盖当前文件版本的通过报告（还没有这类作业）。实质修改后要对当前版本复核$/, "$1: no passing review covers the current files. A new review is needed after substantive changes."],
    [/Summary consistency review检查: 没有覆盖当前文件版本的通过报告（还没有这类作业）。实质修改后要对当前版本复核$/, "Summary consistency review: no passing review covers the current files. A new review is needed after substantive changes."],
    [/推导审核/g, "Derivation review"], [/，(\d+) 核/g, ", $1 cores"],
    [/（pid ([^)]+)）/g, "(pid $1)"], [/（(pod #[^）]+)）/g, "($1)"],
    [/studio（一、二期）\+ pod（三期 L=9）/g, "studio (phases 1–2) + pod (phase 3, L=9)"],
  ];
  function t(text) {
    if (!english() || typeof text !== "string") return text;
    const trimmed = text.trim();
    if (Object.prototype.hasOwnProperty.call(words, trimmed)) return text.replace(trimmed, words[trimmed]);
    const counted = trimmed.match(/^(.*?)\s+(\(\d+\))$/);
    if (counted && Object.prototype.hasOwnProperty.call(words, counted[1])) {
      const label = counted[1] === "arXiv 候选，等你审批" ? "arXiv candidates awaiting approval" : words[counted[1]];
      return text.replace(trimmed, label + " " + counted[2]);
    }
    let value = trimmed;
    for (const [pattern, replacement] of substitutions) value = value.replace(pattern, replacement);
    return text.replace(trimmed, value);
  }
  // Reviewed translations of text annotations only; never used for original source views.
  const mathLabels = {
    "\\text{窗口外}": "\\text{outside the window}",
    "\\text{（此例）}": "\\text{(in this example)}",
    "\\text{ 的窗口外}": "\\text{ outside the window}",
    "\\text{（全态纯且层交换对称）}": "\\text{(full state pure and symmetric under layer exchange)}",
    "\\text{nat/格点}": "\\text{nat/site}",
    "\\rm 左": "\\rm left",
    "\\rm 右": "\\rm right",
    "\\text{链间散布}": "\\text{between-chain spread}"
  };
  function mathText(src) {
    if (!english()) return src;
    const formula = /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<![\\$])\$(?!\s)[^$\n]+?(?<!\s)\$(?!\d)/g;
    const localize = (math) => {
      for (const [source, label] of Object.entries(mathLabels)) {
        if (source.startsWith("\\rm ")) {
          const escaped = source.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          math = math.replace(new RegExp(escaped + "(?=\\s*})", "g"), () => label);
        } else math = math.split(source).join(label);
      }
      return math.replace(/\\text\{式 (\d[^}]*)\}/g, (_, refs) => `\\text{${refs.includes(",") ? "Eqs." : "Eq."} ${refs}}`);
    };
    // Code examples retain their exact source spelling.
    return src.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)/g)
      .map((part, i) => i % 2 ? part : part.replace(formula, localize)).join("");
  }
  function decorateSources(div) {
    if (!english()) return;
    const walk = document.createTreeWalker(div, NodeFilter.SHOW_TEXT), nodes = [];
    while (walk.nextNode()) if (!walk.currentNode.parentElement.closest("a, pre, code, .katex, .translation-info")) nodes.push(walk.currentNode);
    for (const node of nodes) {
      const matches = [...node.nodeValue.matchAll(/ideas\/inbox\/\d{4}-\d{2}-\d{2}-[^\s()<>]+\.md/g)];
      if (!matches.length) continue;
      const fragment = document.createDocumentFragment(); let end = 0;
      for (const match of matches) {
        fragment.append(node.nodeValue.slice(end, match.index));
        // Historical inbox notes may already have been incorporated into this page.
        const label = document.createElement("span"); label.textContent = "original note";
        label.dataset.originalSourcePath = match[0]; fragment.append(label);
        end = match.index + match[0].length;
      }
      fragment.append(node.nodeValue.slice(end)); node.replaceWith(fragment);
    }
  }
  function translateUI(root = document.body) {
    if (!english()) return;
    const skip = (el) => !el || el.closest(".md, .log, [data-original-text], pre, code, textarea, script, style, .translation-info");
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walk.nextNode()) nodes.push(walk.currentNode);
    for (const node of nodes) if (!skip(node.parentElement)) { const value = t(node.nodeValue); if (value !== node.nodeValue) node.nodeValue = value; }
    root.querySelectorAll("[placeholder], [title], [aria-label]").forEach((el) => {
      if (el.closest(".md, .log, [data-original-text], .translation-info")) return;
      for (const attr of ["placeholder", "title", "aria-label"]) if (el.hasAttribute(attr)) {
        const value = t(el.getAttribute(attr)); if (value !== el.getAttribute(attr)) el.setAttribute(attr, value);
      }
    });
  }
  function info(path) {
    const entry = catalog.documents[path];
    return { path, state: entry ? entry.state : "missing", ...(entry || {}) };
  }
  function translated(doc, path = doc.path) {
    if (!doc || !path) return doc;
    const entry = catalog.documents[path];
    const result = { ...doc, translation: info(path) };
    if (entry) {
      result.title = entry.title || doc.title;
      if (doc.meta) result.meta = { ...doc.meta, ...entry.fields, title: entry.title || doc.meta.title };
      if ("body" in doc) {
        result.translation.original_body = doc.body;
        result.body = entry.body;
      }
    }
    return result;
  }
  function section(body, name) {
    const re = new RegExp("^##\\s+" + name + "(?:[ \t]*[（(][^\\n]*[）)])?[ \t]*\\r?\\n([\\s\\S]*?)(?=^##\\s|$(?![\\s\\S]))", "im");
    return (body.match(re) || [])[1]?.trim() || "";
  }
  function lab(doc) {
    const path = `labs/${doc.id}/report.md`, entry = catalog.documents[path];
    const result = translated(doc);
    if (entry) {
      result.title = entry.title; result.short = entry.title;
      result.answer = section(entry.body, "Current answer");
      result.question = section(entry.body, "Question");
      if (doc.report) result.report = translated(doc.report, path);
      if (doc.images) {
        const captions = new Map();
        for (const token of window.markdownit({ html:false }).parse(entry.body, {})) {
          for (const child of token.children || []) if (child.type === "image") {
            captions.set(new URL(child.attrGet("src") || "", "https://project.invalid/labs/" + doc.id + "/").pathname.slice(1), child.content);
          }
        }
        result.images = doc.images.map((im) => {
          const reportCaption = captions.get(im.path);
          const galleryCaption = catalog.captions?.[im.path];
          if (reportCaption) return { ...im, caption: reportCaption, captionTranslation: info(path).state };
          if (galleryCaption) return { ...im, caption: galleryCaption.text, captionTranslation: galleryCaption.state };
          return { ...im, caption: im.caption || im.name, captionTranslation: im.caption && /[\u4e00-\u9fff]/.test(im.caption) ? "missing" : null };
        });
      }
    } else {
      result.short = result.title;
      result.answer = "No research summary is available yet."; result.question = "";
    }
    if (doc.data) result.data = translated(doc.data, `labs/${doc.id}/DATA.md`);
    return result;
  }
  function question(doc) {
    const result = translated(doc), entry = catalog.documents[doc.path];
    if (entry) result.answer = section(entry.body, "Current answer");
    if (doc.children) result.children = doc.children.map(question);
    return result;
  }
  function activity(run) {
    const kinds = {
      manual: "Manual task", tick: "Process pending tasks", digest: "Review answered discussions",
      digest_answers: "Incorporate discussion answers", arxiv_reason: "Screen arXiv candidates",
      triage_idea: "Organize an idea", run_lab: "Run research task", resume_lab: "Resume research task",
      revise_brief: "Revise research plan", promote_idea: "Draft research plan", ingest_reference: "Add reference to library",
      answer_user_question: "Answer a question", audit_derivation: "Derivation review", audit_code: "Code review",
      audit_consistency: "Summary consistency review",
    };
    let label = run.label || run.kind || "";
    const answers = label.match(/^digest:(\d+)条回答$/);
    if (answers) label = `Incorporate ${answers[1]} discussion ${answers[1] === "1" ? "answer" : "answers"}`;
    else if (kinds[label]) label = kinds[label];
    else if (label === "arxiv-reason") label = kinds.arxiv_reason;
    else {
      const split = label.indexOf(":"), kind = label.slice(0, split), id = label.slice(split + 1);
      if (split > 0 && kinds[kind]) {
        const source = kind === "triage_idea" || kind === "promote_idea" ? `ideas/${id}.md` :
          kind === "answer_user_question" ? `discussion/${id}.md` : `labs/${id}/report.md`;
        // Historical submission slugs can contain Chinese; show their date when no translated title exists.
        const title = catalog.documents[source]?.title || (/[\u4e00-\u9fff]/.test(id) ? id.match(/\d{4}-\d{2}-\d{2}/)?.[0] || "Original submission" : id);
        label = `${kinds[kind]}: ${title}`;
      }
    }
    return { ...run, label, display_kind: kinds[run.kind] || run.kind };
  }
  function overlay(path, data) {
    if (!english()) return data;
    const pathname = path.split("?")[0];
    if (pathname === "/api/runs") return { ...data, runs: data.runs.map(activity), queue: {
      ...data.queue, current: data.queue.current ? activity(data.queue.current) : null, pending: data.queue.pending.map(activity),
    } };
    if (pathname.startsWith("/api/runs/")) return activity(data);
    if (pathname === "/api/overview") {
      const result = { ...data };
      if (data.queue) result.queue = { ...data.queue, current: data.queue.current ? activity(data.queue.current) : null, pending: data.queue.pending.map(activity) };
      if (data.status) result.status = translated(data.status, "STATUS.md");
      if (data.attention) result.attention = { ...data.attention, items: data.attention.items.map((item) => {
        const source = item.kind === "discussion" ? `discussion/${item.id}.md` : item.kind === "lab" ? `labs/${item.id}/report.md` : item.kind === "inbox" ? `references/inbox/${item.id}.md` : null;
        return { ...item, title: catalog.documents[source]?.title || item.title };
      }) };
      return result;
    }
    if (pathname === "/api/references") return { ...data, cards: data.cards.map((doc) => translated(doc)), inbox: data.inbox.map((doc) => translated(doc)) };
    if (pathname === "/api/discussion") return data.map((doc) => translated(doc));
    if (pathname.startsWith("/api/discussion/")) return translated(data);
    if (pathname === "/api/labs") return data.map(lab);
    if (pathname.startsWith("/api/labs/")) return lab(data);
    if (pathname === "/api/wiki") return data.map((doc) => translated(doc));
    if (pathname.startsWith("/api/wiki/")) {
      const result = translated(data);
      if (data.backlinks) result.backlinks = data.backlinks.map((link) => ({ ...link, title: catalog.documents[`wiki/${link.id}.md`]?.title || link.title }));
      return result;
    }
    if (pathname === "/api/ideas") return { ...data, tree: data.tree.map(question) };
    if (pathname.startsWith("/api/ideas/")) return question(data);
    if (pathname === "/api/raw" || (data && "body" in data && data.path)) return translated(data);
    return data;
  }
  function notice(container, path, render, shownBody) {
    const entry = info(path);
    container.className = "translation-info " + entry.state;
    container.replaceChildren();
    if (entry.body && entry.body !== shownBody) {
      container.className = "translation-info updated";
      container.append("An updated English translation is available. ");
      const reload = document.createElement("a"); reload.href = url("en"); reload.textContent = "Reload the English text";
      reload.onclick = (event) => { event.preventDefault(); location.reload(); };
      container.append(reload);
      return;
    }
    const label = document.createElement("span");
    label.textContent = entry.state === "stale" ? "Translation needs updating: the Chinese source has changed. " :
      entry.state === "missing" ? "No separate English translation is available for this page. The latest original is shown below. " : "English translation · ";
    const link = document.createElement("a"); link.href = url("zh"); link.textContent = "中文原文";
    container.append(label, link);
    if (entry.state === "stale" && entry.source_body) {
      const details = document.createElement("details"), summary = document.createElement("summary");
      summary.textContent = "Latest original, including any new answers";
      details.append(summary);
      if (entry.source_fields?.verdict) {
        const verdict = document.createElement("p"); verdict.textContent = "Current source verdict: " + entry.source_fields.verdict;
        details.append(verdict);
      }
      if (entry.source_fields?.reason) {
        const reason = document.createElement("p"); reason.textContent = "Current source relevance note: " + entry.source_fields.reason;
        details.append(reason);
      }
      details.append(render(entry.source_body, path.includes("/") ? path.slice(0,path.lastIndexOf("/")) : ""));
      container.append(details);
    }
  }
  function decorate(div, translation, render, slugId, md) {
    if (!english() || !translation) return div;
    const banner = document.createElement("div"); banner.dataset.source = translation.path;
    banner._refreshTranslation = () => notice(banner, translation.path, render, translation.body);
    banner._refreshTranslation(); div.prepend(banner);
    if (translation.state === "current") {
      const headings = [...div.querySelectorAll("h1,h2,h3,h4")]; const used = {};
      const sources = translation.source_heading_texts || (translation.source_headings || []).map((source) => {
        const scratch = document.createElement("div"); scratch.innerHTML = md.renderInline(source);
        return scratch.textContent;
      });
      sources.forEach((source, i) => {
        if (!headings[i]) return;
        let id = slugId(source); if (used[id]) id = `${id}-${++used[id]}`; else used[id] = 1;
        if (headings.some((h) => h.id === id)) return;
        const alias = document.createElement("span"); alias.id = id; alias.className = "translation-anchor";
        headings[i].before(alias);
      });
    }
    return div;
  }
  function translateImages(root = document.body) {
    if (!english()) return;
    root.querySelectorAll('img[src*="/api/file?"]').forEach((img) => {
      if (img.closest('.translation-info')) return; // Latest-original previews stay original.
      const current = new URL(img.src, location.href);
      const source = img.dataset.originalImage || current.searchParams.get('path');
      const entry = catalog.images?.[source];
      if (!entry) {
        if (img.dataset.originalImage) {
          const previous = img.src;
          img.src = '/api/file?path=' + encodeURIComponent(source);
          const link = img.closest('a');
          if (link?.href === previous) link.href = img.src;
          (img.closest('figure') || img.parentElement).querySelector('.image-translation-status')?.remove();
          delete img.dataset.originalImage;
        }
        return;
      }
      img.dataset.originalImage = source;
      const destination = new URL('/api/file', location.href);
      destination.searchParams.set('path', entry.path);
      destination.searchParams.set('v', entry.asset_sha256.slice(0, 16));
      const previous = img.src;
      if (previous !== destination.href) img.src = destination.href;
      const link = img.closest('a');
      if (link && (link.href === previous || new URL(link.href).searchParams.get('path') === source)) link.href = destination.href;
      const figure = img.closest('figure') || img.parentElement;
      let warning = figure.querySelector('.image-translation-status');
      if (entry.state === 'stale' && !warning) {
        warning = document.createElement('div'); warning.className = 'translation-info stale image-translation-status';
        warning.append('English figure needs updating. ');
        const original = document.createElement('a'); original.href = '/api/file?path=' + encodeURIComponent(source); original.target = '_blank';
        original.textContent = 'View the latest original'; warning.append(original); figure.append(warning);
      } else if (entry.state !== 'stale' && warning) warning.remove();
    });
  }
  async function refresh() {
    if (loading) return loading;
    loading = (async () => {
      try {
        const r = await fetch("/api/translations", { cache: "no-store" });
        if (r.ok) {
          const next = await r.json();
          if (next && typeof next.enabled === "boolean" && next.documents && typeof next.documents === "object") catalog = next;
        }
      } catch (_) { /* Original Chinese view remains usable. */ }
      const control = document.querySelector("#reading-language");
      if (control) {
        control.hidden = !catalog.enabled;
        control.querySelectorAll("button").forEach((button) => {
          button.setAttribute("aria-pressed", String(button.dataset.lang === (english() ? "en" : "zh")));
          button.onclick = () => { if (button.dataset.lang !== (english() ? "en" : "zh")) location.href = url(button.dataset.lang); };
        });
      }
      document.documentElement.lang = english() ? "en" : "zh-CN";
      document.body.classList.toggle("english-reading", !!english());
      document.querySelectorAll(".translation-info").forEach((node) => node._refreshTranslation?.());
      translateUI();
      translateImages();
    })().finally(() => { loading = null; });
    return loading;
  }
  let scheduled = false;
  new MutationObserver(() => {
    if (!english() || scheduled) return;
    scheduled = true; queueMicrotask(() => { scheduled = false; translateUI(); translateImages(); });
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["placeholder", "title", "aria-label"] });
  window.ReadingMode = { english, t, mathText, decorateSources, refresh, overlay, decorate, info };
})();
