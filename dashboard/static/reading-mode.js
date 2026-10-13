/* Optional English reading layer. All writes and workflow state use the original API. */
(() => {
  const requested = new URLSearchParams(location.search).get("lang") === "en" ? "en" : "zh";
  let catalog = { enabled: false, documents: {} };
  let loading = null;
  const english = () => catalog.enabled && requested === "en";
  const url = (lang) => { const u = new URL(location.href); u.searchParams.set("lang", lang); return u.href; };
  const words = {
    "首页":"Overview", "文献":"References", "讨论":"Discussions", "想法":"Questions", "任务":"Activity", "课题":"Project",
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
    "审计修正清单，过目即可，不卡任务：认可就回答“认可”，不认可指出哪一处":"Audit corrections for review. Confirm acceptance or identify the correction you disagree with.",
  };
  const substitutions = [
    [/^← 讨论$/, "← Discussions"], [/^← 文献$/, "← References"], [/^← 任务$/, "← Activity"],
    [/^创建：/, "Created: "], [/^更新：/, "Updated: "], [/^课题状态 · 更新 /, "Project overview · Updated "],
    [/^相关任务 /, "Related task "], [/^来自问题：/, "Related question: "], [/^机器：/, "Machine: "],
    [/^审计：/, "Reviews: "], [/^历史：/, "History: "], [/^全部图 \((\d+)\)$/, "All figures ($1)"],
    [/^文件 \((\d+)\)$/, "Files ($1)"], [/^任务书 brief.md/, "Research plan (Chinese)"],
    [/^📖 推导与分析 /, "📖 Detailed notes (Chinese) "], [/^最近动态（(\d+) 条）$/, "Recent activity ($1 entries; Chinese)"],
    [/^只读 · /, "Read-only · "], [/^需要你处理/, "Needs your attention"], [/^agent 正在运行：/, "Research agent running: "],
    [/^后台数值：/, "Numerical jobs: "], [/^数值作业：/, "Numerical jobs: "], [/^ · 给 AI 读：$/, " · Machine-readable source (Chinese): "],
    [/^\(\d+\)$/, "$&"], [/^（未启动）$/, " (offline)"], [/^ ·待处理$/, " · awaiting action"],
    [/^访客 (.+) 问 agent( · 等你放行)?$/, "Guest question from $1"],
    [/^讨论 /, "Discussion "], [/^收尾门槛（rd finish）还差$/, "Remaining completion checks (Chinese)"],
    [/^(\d+) 条回答等待统一消化$/, "$1 answers awaiting review"],
    [/^已提交，将在 (.+) 左右与其他回答一起消化$/, "Submitted. Your answer will be reviewed with the other answers around $1."],
    [/^· 为了把互相关联的回答放在一起考虑，agent 每 (\d+) 分钟消化一次，下次约 (.+)。$/, "· Related answers are reviewed together every $1 minutes. Next review: $2."],
    [/^访客 (.+) 问 agent（已放行）$/, "Guest question from $1 (approved)"],
    [/^访客 (.+) 问 agent（等放行）$/, "Guest question from $1 (awaiting approval)"],
    [/^agent 问你(?=\s*·|$)/, "Question for the project owner"],
    [/^你问 agent(?=\s*·|$)/, "Question for the research agent"],
  ];
  function t(text) {
    if (!english() || typeof text !== "string") return text;
    const trimmed = text.trim();
    if (Object.prototype.hasOwnProperty.call(words, trimmed)) return text.replace(trimmed, words[trimmed]);
    const counted = trimmed.match(/^(.*?)\s+(\(\d+\))$/);
    if (counted && Object.prototype.hasOwnProperty.call(words, counted[1])) return text.replace(trimmed, words[counted[1]] + " " + counted[2]);
    for (const [pattern, replacement] of substitutions) if (pattern.test(trimmed)) return text.replace(trimmed, trimmed.replace(pattern, replacement));
    return text;
  }
  function translateUI(root = document.body) {
    if (!english()) return;
    const skip = (el) => !el || el.closest(".md, pre, code, textarea, script, style, .translation-info");
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walk.nextNode()) nodes.push(walk.currentNode);
    for (const node of nodes) if (!skip(node.parentElement)) { const value = t(node.nodeValue); if (value !== node.nodeValue) node.nodeValue = value; }
    root.querySelectorAll("[placeholder], [title]").forEach((el) => {
      if (el.closest(".md, .translation-info")) return;
      for (const attr of ["placeholder", "title"]) if (el.hasAttribute(attr)) {
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
      result.title = entry.title;
      if (doc.meta) result.meta = { ...doc.meta, title: entry.title };
      if ("body" in doc) result.body = entry.body;
    }
    return result;
  }
  function section(body, name) {
    const re = new RegExp("^##\\s+" + name + "\\s*\\n([\\s\\S]*?)(?=^##\\s|$(?![\\s\\S]))", "im");
    return (body.match(re) || [])[1]?.trim() || "";
  }
  function lab(doc) {
    const path = `labs/${doc.id}/report.md`, entry = catalog.documents[path];
    const result = { ...doc };
    if (entry) {
      result.title = entry.title; result.short = entry.title;
      result.answer = section(entry.body, "Current answer");
      result.question = section(entry.body, "Question");
      if (doc.report) result.report = translated(doc.report, path);
      if (doc.images) {
        const captions = new Map();
        for (const token of window.markdownit({ html:false }).parse(entry.body, {})) {
          for (const child of token.children || []) if (child.type === "image") {
            captions.set((child.attrGet("src") || "").split("/").pop(), child.content);
          }
        }
        result.images = doc.images.map((im) => ({ ...im, caption: captions.get(im.path.split("/").pop()) || im.name }));
      }
    } else {
      result.answer = "No English summary is available yet."; result.question = "";
    }
    result.translation = info(doc.path); // the plan itself may remain Chinese
    return result;
  }
  function overlay(path, data) {
    if (!english()) return data;
    const pathname = path.split("?")[0];
    if (pathname === "/api/overview") {
      const result = { ...data };
      if (data.status) result.status = translated(data.status, "STATUS.md");
      if (data.attention) result.attention = { ...data.attention, items: data.attention.items.map((item) => {
        const source = item.kind === "discussion" ? `discussion/${item.id}.md` : item.kind === "lab" ? `labs/${item.id}/report.md` : null;
        return { ...item, title: catalog.documents[source]?.title || item.title };
      }) };
      return result;
    }
    if (pathname === "/api/discussion") return data.map((doc) => translated(doc));
    if (pathname.startsWith("/api/discussion/")) return translated(data);
    if (pathname === "/api/labs") return data.map(lab);
    if (pathname.startsWith("/api/labs/")) return lab(data);
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
      details.append(summary, render(entry.source_body, path.includes("/") ? path.slice(0,path.lastIndexOf("/")) : ""));
      container.append(details);
    }
  }
  function decorate(div, translation, render, slugId, md) {
    if (!english() || !translation) return div;
    const banner = document.createElement("div"); banner.dataset.source = translation.path;
    banner._refreshTranslation = () => notice(banner, translation.path, render, translation.body);
    banner._refreshTranslation(); div.prepend(banner);
    if (translation.state === "current") {
      const headings = [...div.querySelectorAll("h1,h2,h3,h4,h5,h6")]; const used = {};
      (translation.source_headings || []).forEach((source, i) => {
        if (!headings[i]) return;
        const scratch = document.createElement("div"); scratch.innerHTML = md.renderInline(source);
        let id = slugId(scratch.textContent); if (used[id]) id = `${id}-${++used[id]}`; else used[id] = 1;
        if (headings.some((h) => h.id === id)) return;
        const alias = document.createElement("span"); alias.id = id; alias.className = "translation-anchor";
        headings[i].before(alias);
      });
    }
    return div;
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
    })().finally(() => { loading = null; });
    return loading;
  }
  let scheduled = false;
  new MutationObserver(() => {
    if (!english() || scheduled) return;
    scheduled = true; queueMicrotask(() => { scheduled = false; translateUI(); });
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  window.ReadingMode = { english, t, refresh, overlay, decorate, info };
})();
