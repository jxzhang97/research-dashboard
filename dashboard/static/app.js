/* 课题 dashboard 前端：hash 路由 + fetch JSON + markdown-it/KaTeX 渲染。无构建步骤。 */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const main = $("#main");
  let LINKS = {};
  let OVERVIEW = null;
  const STATUS_ZH = {
    draft: "草稿", awaiting_review: "待过目", approved: "已批准", running: "进行中", waiting_answer: "等你回答",
    done: "完成", blocked: "受阻", parked: "搁置", seed: "萌芽", exploring: "探索中", lab: "已立 lab",
    resolved: "已解决", dropped: "否决", open: "待回答", answered: "已回答", digested: "已消化",
    pending: "待审批", rejected: "已拒绝", ingested: "已入库", inbox: "未整理", queued: "排队", failed: "失败", stopped: "已停止",
  };
  const zh = (s) => STATUS_ZH[s] || s || "";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chip = (s, extra = "") => `<span class="chip ${esc(s)} ${extra}">${esc(zh(s))}</span>`;

  // ---------- 网络 ----------
  async function api(path, opts) {
    const r = await fetch(path, opts && { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opts) });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  }
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("on"); setTimeout(() => t.classList.remove("on"), 2200);
  }

  // ---------- markdown ----------
  const md = window.markdownit({ html: false, linkify: true, breaks: false });
  // markdown-it 会把 \u0000 换成 U+FFFD，所以占位符用纯字母数字
  function protectMath(src) {
    const store = [];
    const keep = (m) => { store.push(m); return `MATHPH${store.length - 1}ENDPH`; };
    src = src.replace(/\$\$[\s\S]+?\$\$/g, keep).replace(/\\\[[\s\S]+?\\\]/g, keep).replace(/\\\([\s\S]+?\\\)/g, keep)
      .replace(/(^|[^\\$])\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g, (m, pre, body) => pre + keep("$" + body + "$"));
    return { src, store };
  }
  function restoreMath(html, store) {
    return html.replace(/MATHPH(\d+)ENDPH/g, (_, i) => store[+i].replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])));
  }
  // [[目标|标签]] → 普通 markdown 链接，用 title 做标记，渲染后再换成 class
  function wikilinks(src) {
    return src.replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]/g, (_, target, label) => {
      const t = target.trim(); const r = LINKS[t];
      const href = r ? routeFor(r.kind, r.id) : "#/wiki/" + encodeURIComponent(t);
      return `[${(label || t).replace(/[\[\]]/g, "")}](${href} "${r ? "wikilink" : "wikilink-missing"}")`;
    });
  }
  function routeFor(kind, id) {
    return { wiki: "#/wiki/", card: "#/refs/", lab: "#/labs/", idea: "#/ideas/", discussion: "#/discussion/", inbox: "#/inbox/" }[kind] + id;
  }
  function render(src, baseDir = "") {
    const { src: s1, store } = protectMath(src || "");
    let html = md.render(wikilinks(s1));
    html = restoreMath(html, store);
    const div = document.createElement("div"); div.className = "md"; div.innerHTML = html;
    div.querySelectorAll('a[title^="wikilink"]').forEach((a) => { a.className = a.title === "wikilink" ? "wikilink" : "wikilink missing"; a.removeAttribute("title"); });
    div.querySelectorAll("img, a").forEach((el) => {
      const attr = el.tagName === "IMG" ? "src" : "href"; const v = el.getAttribute(attr) || "";
      if (!v || /^(https?:|#|mailto:|\/)/.test(v)) return;
      el.setAttribute(attr, "/api/file?path=" + encodeURIComponent((baseDir ? baseDir + "/" : "") + v.replace(/^\.\//, "")));
      if (el.tagName === "A") el.target = "_blank";
    });
    if (window.renderMathInElement) {
      renderMathInElement(div, { delimiters: [{ left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true }, { left: "\\(", right: "\\)", display: false }, { left: "$", right: "$", display: false }], throwOnError: false });
    }
    return div;
  }
  const dirOf = (p) => p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";

  // ---------- 总览 / 红点 ----------
  async function refreshOverview() {
    try {
      OVERVIEW = await api("/api/overview");
      LINKS = await api("/api/links");
    } catch (e) { console.error(e); return; }
    const a = OVERVIEW.attention;
    $("#brand-name").textContent = OVERVIEW.project.name || "课题";
    $("#host").textContent = OVERVIEW.host;
    document.title = (a.total ? `(${a.total}) ` : "") + (OVERVIEW.project.name || "课题");
    const running = (OVERVIEW.queue.current ? 1 : 0) + OVERVIEW.queue.pending.length;
    const counts = { ...a.counts, runs: running };
    document.querySelectorAll(".badge").forEach((b) => { const n = counts[b.dataset.badge] || 0; b.textContent = n; b.classList.toggle("on", n > 0); });
  }

  // ---------- 页面 ----------
  const pages = {};

  pages.home = async () => {
    await refreshOverview();
    const o = OVERVIEW; const a = o.attention;
    const items = a.items.map((it) => `<li><a href="${routeFor(it.kind, it.id)}"><b>${esc(it.title)}</b></a><span class="t muted">${esc(it.why)}</span></li>`).join("");
    const log = o.log.map((e) => `<li><span class="muted small">${esc(e.time)}</span><span class="t">${esc(e.who)} · ${esc(e.what)}</span></li>`).join("");
    const q = o.queue; const cur = q.current ? `正在运行：<a href="#/runs/${q.current.id}">${esc(q.current.label)}</a>` : "没有正在运行的任务";
    main.innerHTML = `
      <h1>${esc(o.project.name)}</h1>
      <div class="stats">
        <a class="stat" href="#/refs"><b>${o.counts.cards}</b><span>文献卡片</span></a>
        <a class="stat" href="#/wiki"><b>${o.counts.wiki}</b><span>wiki 页</span></a>
        <a class="stat" href="#/labs"><b>${o.counts.labs}</b><span>lab</span></a>
        <a class="stat" href="#/discussion"><b>${o.counts.discussion}</b><span>讨论</span></a>
        <a class="stat" href="#/ideas"><b>${o.counts.ideas}</b><span>想法</span></a>
      </div>
      <div class="row">
        <div class="col">
          <div class="panel ${a.total ? "attn" : ""}"><h2 style="margin-top:0">需要你处理 ${a.total ? `<span class="chip unread">${a.total}</span>` : ""}</h2>
            ${a.total ? `<ul class="list">${items}</ul>` : `<p class="muted">暂时没有。</p>`}</div>
          <div class="panel"><h2 style="margin-top:0">agent</h2><p>${cur}${q.pending.length ? `，排队 ${q.pending.length}` : ""} · <a href="#/runs">任务页</a></p></div>
        </div>
        <div class="col"><div class="panel"><h2 style="margin-top:0">最近动态</h2><ul class="list small">${log || "<li class='muted'>还没有记录</li>"}</ul></div></div>
      </div>
      <details class="panel"><summary>课题总纲 PROJECT.md</summary><div id="pm"></div></details>`;
    $("#pm").appendChild(render(o.project_md));
  };

  pages.refs = async (key) => {
    if (key) return pages.card(key);
    const d = await api("/api/references");
    const inbox = d.inbox.filter((x) => x.meta.status === "pending");
    const decided = d.inbox.filter((x) => x.meta.status !== "pending");
    const inboxHtml = inbox.map((x) => `<li data-key="${esc(x.id)}"><span class="t"><a href="#/inbox/${esc(x.id)}"><b>${esc(x.title)}</b></a><br><span class="small muted">${esc((x.meta.authors || []).slice(0, 3).join(", "))} · ${esc(x.meta.published || "")} · 命中 ${esc((x.meta.hits || []).join(" "))}</span>${x.meta.reason ? `<br><span class="small">${esc(x.meta.reason)}</span>` : ""}</span>
        <button class="primary" data-act="approved">通过</button><button data-act="rejected">拒绝</button></li>`).join("");
    const cards = d.cards.map((x) => `<li><span class="t"><a href="#/refs/${esc(x.id)}"><b>${esc(x.title)}</b></a><br><span class="small muted">${esc((x.meta.authors || []).slice(0, 3).join(", "))}${x.meta.year ? " · " + esc(x.meta.year) : ""}${x.meta.arxiv ? " · arXiv:" + esc(x.meta.arxiv) : ""}</span></span>
        <span class="chip">${esc({ abstract: "只读摘要", skim: "略读", full: "精读" }[x.meta.read_depth] || "阅读深度未填")}</span><span class="small muted">${esc(x.updated)}</span></li>`).join("");
    main.innerHTML = `<h1>文献</h1>
      <div class="panel ${inbox.length ? "attn" : ""}"><h2 style="margin-top:0">arXiv 候选，等你审批 (${inbox.length})</h2>
        ${inbox.length ? `<ul class="list" id="inbox">${inboxHtml}</ul>` : `<p class="muted">没有待审批的候选。每天定时扫描，通过的才会精读入库。</p>`}
        ${decided.length ? `<details><summary>已处理 ${decided.length}</summary><ul class="list small">${decided.map((x) => `<li><span class="t"><a href="#/inbox/${esc(x.id)}">${esc(x.title)}</a></span>${chip(x.meta.status)}</li>`).join("")}</ul></details>` : ""}</div>
      <div class="panel"><h2 style="margin-top:0">卡片 (${d.cards.length})</h2><ul class="list">${cards || "<li class='muted'>还没有卡片</li>"}</ul></div>`;
    main.querySelectorAll("#inbox button").forEach((b) => b.onclick = async () => {
      const li = b.closest("li"); b.disabled = true;
      await api(`/api/inbox/${encodeURIComponent(li.dataset.key)}/${b.dataset.act}`);
      toast(b.dataset.act === "approved" ? "已通过，agent 将下载并精读" : "已拒绝"); li.remove(); refreshOverview();
    });
  };

  pages.card = async (key) => {
    const d = await api(`/api/references/${encodeURIComponent(key)}`);
    const m = d.meta;
    main.innerHTML = `<p><a href="#/refs">← 文献</a></p><h1>${esc(d.title)}</h1>
      <div class="meta"><span>${esc((m.authors || []).join(", "))}</span>${m.year ? `<span>${esc(m.year)}</span>` : ""}
        ${m.arxiv ? `<a href="https://arxiv.org/abs/${esc(m.arxiv)}" target="_blank">arXiv:${esc(m.arxiv)}</a>` : ""}
        ${m.file ? `<a href="/api/file?path=${encodeURIComponent(m.file)}" target="_blank">PDF</a>` : ""}
        <span>阅读深度：${esc({ abstract: "只读摘要", skim: "略读", full: "精读" }[m.read_depth] || "未填")}</span><span>来源：${esc(m.source || "")}</span><span>更新：${esc(d.updated)}</span></div>
      <div class="panel" id="body"></div>`;
    $("#body").appendChild(render(d.body, dirOf(d.path)));
  };

  pages.inbox = async (key) => {
    const d = await api(`/api/inbox/${encodeURIComponent(key)}`); const m = d.meta;
    main.innerHTML = `<p><a href="#/refs">← 文献</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${chip(m.status)}<a href="${esc(m.url || "https://arxiv.org/abs/" + m.arxiv)}" target="_blank">arXiv:${esc(m.arxiv)}</a><span>${esc(m.published || "")}</span></div>
      ${m.status === "pending" ? `<p><button class="primary" id="ok">通过，下载并精读</button> <button id="no">拒绝</button></p>` : ""}
      <div class="panel" id="body"></div>`;
    $("#body").appendChild(render(d.body, dirOf(d.path)));
    const act = (s) => async () => { await api(`/api/inbox/${encodeURIComponent(key)}/${s}`); toast("已记录"); location.hash = "#/refs"; };
    if ($("#ok")) { $("#ok").onclick = act("approved"); $("#no").onclick = act("rejected"); }
  };

  pages.wiki = async (slug) => {
    const list = await api("/api/wiki");
    const side = list.map((p) => `<a href="#/wiki/${esc(p.id)}" class="${p.id === slug ? "cur" : ""}">${esc(p.title)}</a>`).join("");
    let content = `<p class="muted">左侧选择一页。wiki 是当前理解的汇编，由 agent 维护并随进展重写；[[双括号]] 互相链接。</p>`;
    main.innerHTML = `<h1>Wiki</h1><div class="two"><div class="side panel">${side || "<span class='muted'>还没有页面</span>"}</div><div id="content">${content}</div></div>`;
    if (slug) {
      const d = await api(`/api/wiki/${slug}`);
      const back = (d.backlinks || []).map((b) => `<a href="#/wiki/${esc(b.id)}">${esc(b.title)}</a>`).join(" · ");
      const c = $("#content"); c.innerHTML = `<h2 style="margin-top:0">${esc(d.title)}</h2><div class="meta"><span>更新：${esc(d.updated)}</span>${(d.meta.tags || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div><div class="panel" id="body"></div>${back ? `<p class="small muted">反向链接：${back}</p>` : ""}`;
      $("#body").appendChild(render(d.body, dirOf(d.path)));
    }
  };

  pages.labs = async (id) => {
    if (id) return pages.lab(id);
    const list = await api("/api/labs");
    const rows = list.map((x) => `<li><span class="t"><a href="#/labs/${esc(x.id)}"><b>${esc(x.title)}</b></a> <span class="small muted">${esc(x.id)}</span></span>${chip(x.meta.status)}${x.meta.machine ? `<span class="chip">${esc(x.meta.machine)}</span>` : ""}<span class="small muted">${esc(x.updated)}</span></li>`).join("");
    main.innerHTML = `<h1>Lab</h1><p class="muted small">每个任务一个文件夹：任务书 brief.md、报告 report.md（+PDF）、数据去向 DATA.md。想法页里可以把 idea 升级成 lab。</p><div class="panel"><ul class="list">${rows || "<li class='muted'>还没有任务</li>"}</ul></div>`;
  };

  pages.lab = async (id) => {
    const d = await api(`/api/labs/${encodeURIComponent(id)}`); const m = d.meta; const st = m.status;
    const pdfs = (d.pdfs || []).map((p) => `<a class="btn" href="/api/file?path=${encodeURIComponent(d.path.replace("brief.md", p))}" target="_blank">📄 ${esc(p)}</a>`).join(" ");
    const files = (d.files || []).map((f) => `<li><a href="/api/file?path=${encodeURIComponent(f.path)}" target="_blank">${esc(f.name)}</a> <span class="muted small">${(f.size / 1024).toFixed(1)} KB</span></li>`).join("");
    main.innerHTML = `<p><a href="#/labs">← Lab</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${chip(st)}<span>${esc(id)}</span>${m.idea ? `<a href="#/ideas/${esc(m.idea)}">来自想法：${esc(m.idea)}</a>` : ""}${m.machine ? `<span>机器：${esc(m.machine)}</span>` : ""}<span>更新：${esc(d.updated)}</span></div>
      <p>${st === "awaiting_review" ? `<button class="primary" id="approve">批准，开始执行</button> ` : ""}
         ${["running", "approved"].includes(st) ? "" : `<button id="park">搁置</button> `}${st === "parked" ? `<button id="unpark">恢复为待过目</button>` : ""} ${pdfs}</p>
      ${d.report ? `<h2>报告摘要</h2><div class="panel" id="report"></div>` : ""}
      <h2>任务书</h2><div class="panel" id="brief"></div>
      ${d.data ? `<h2>数据去向 DATA.md</h2><div class="panel" id="data"></div>` : ""}
      <details><summary>文件 (${(d.files || []).length})</summary><ul class="list small">${files}</ul></details>`;
    $("#brief").appendChild(render(d.body, dirOf(d.path)));
    if (d.report) $("#report").appendChild(render(d.report.body, dirOf(d.path)));
    if (d.data) $("#data").appendChild(render(d.data.body, dirOf(d.path)));
    if ($("#approve")) $("#approve").onclick = async () => { await api(`/api/labs/${encodeURIComponent(id)}/approve`); toast("已批准，agent 开始执行"); pages.lab(id); refreshOverview(); };
    if ($("#park")) $("#park").onclick = async () => { await api(`/api/labs/${encodeURIComponent(id)}/status/parked`); pages.lab(id); };
    if ($("#unpark")) $("#unpark").onclick = async () => { await api(`/api/labs/${encodeURIComponent(id)}/status/awaiting_review`); pages.lab(id); };
    api("/api/seen", { kind: "lab", id }).then(refreshOverview);
  };

  pages.discussion = async (id) => {
    if (id) return pages.thread(id);
    const list = await api("/api/discussion");
    const grp = (s) => list.filter((x) => x.meta.status === s);
    const row = (x) => `<li><span class="t"><a href="#/discussion/${esc(x.id)}"><b>${esc(x.title)}</b></a> <span class="small muted">${x.meta.asked_by === "user" ? "你问 agent" : "agent 问你"}${x.meta.lab ? " · " + esc(x.meta.lab) : ""}</span></span>${chip(x.meta.status)}<span class="small muted">${esc(x.updated)}</span></li>`;
    const sec = (title, arr) => arr.length ? `<h2>${title} (${arr.length})</h2><div class="panel"><ul class="list">${arr.map(row).join("")}</ul></div>` : "";
    main.innerHTML = `<h1>讨论</h1>
      <div class="panel"><b>向 agent 提问</b><div class="form-row"><input id="qt" placeholder="标题"></div><textarea id="qb" placeholder="问题内容，可以写公式 $…$"></textarea><div class="form-row"><button class="primary" id="ask">提交</button><span class="muted small">提交后 agent 会去读相关材料并回答</span></div></div>
      ${sec("等你回答", grp("open").filter((x) => x.meta.asked_by === "agent"))}${sec("等 agent 回答", grp("open").filter((x) => x.meta.asked_by === "user"))}${sec("你已回答，agent 还没消化", grp("answered"))}${sec("agent 已消化", grp("digested"))}${sec("已解决", grp("resolved"))}
      ${list.length ? "" : "<p class='muted'>还没有讨论。agent 在遇到需要你裁决的问题时会在这里提问。</p>"}`;
    $("#ask").onclick = async () => {
      const title = $("#qt").value.trim(), text = $("#qb").value.trim(); if (!title || !text) return toast("标题和内容都要填");
      const r = await api("/api/discussion", { title, text }); location.hash = "#/discussion/" + r.id;
    };
  };

  pages.thread = async (id) => {
    const d = await api(`/api/discussion/${encodeURIComponent(id)}`); const m = d.meta;
    main.innerHTML = `<p><a href="#/discussion">← 讨论</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${chip(m.status)}<span>${m.asked_by === "user" ? "你问 agent" : "agent 问你"}</span>${m.lab ? `<a href="#/labs/${esc(m.lab)}">相关任务 ${esc(m.lab)}</a>` : ""}${m.idea ? `<a href="#/ideas/${esc(m.idea)}">相关想法</a>` : ""}<span>创建：${esc(m.created || "")}</span></div>
      <div class="panel" id="body"></div>
      <div class="panel"><b>${m.asked_by === "agent" ? "你的回答" : "补充"}</b><textarea id="ans" placeholder="写下你的裁决或想法。提交后 agent 会立刻处理。"></textarea>
        <div class="form-row"><button class="primary" id="send">提交回答</button>${m.status !== "resolved" ? `<button id="resolve">标记已解决</button>` : ""}</div></div>`;
    $("#body").appendChild(render(d.body, dirOf(d.path)));
    $("#send").onclick = async () => { const t = $("#ans").value.trim(); if (!t) return; await api(`/api/discussion/${encodeURIComponent(id)}/answer`, { text: t }); toast("已提交，agent 开始处理"); pages.thread(id); refreshOverview(); };
    if ($("#resolve")) $("#resolve").onclick = async () => { await api(`/api/discussion/${encodeURIComponent(id)}/resolve`); pages.thread(id); refreshOverview(); };
    api("/api/seen", { kind: "discussion", id }).then(refreshOverview);
  };

  pages.ideas = async (slug) => {
    if (slug) return pages.idea(slug);
    const d = await api("/api/ideas");
    const node = (n) => `<li><a href="#/ideas/${esc(n.id)}">${esc(n.title)}</a> ${chip(n.meta.status)}${n.meta.promoted_lab ? ` <a class="small" href="#/labs/${esc(n.meta.promoted_lab)}">→ lab</a>` : ""}${n.children.length ? `<ul>${n.children.map(node).join("")}</ul>` : ""}</li>`;
    const tree = d.tree.filter((n) => !n.id.startsWith("inbox/"));
    const inbox = d.tree.filter((n) => n.id.startsWith("inbox/"));
    main.innerHTML = `<h1>想法</h1>
      <div class="panel"><b>速记一个想法</b><textarea id="cap" placeholder="模糊的也行，原话会被原样保存；agent 会整理挂到树上，不会改你的话。"></textarea><div class="form-row"><button class="primary" id="save">记下</button></div></div>
      ${inbox.length ? `<div class="panel"><b>未整理 (${inbox.length})</b><ul class="list small">${inbox.map((n) => `<li><a href="#/ideas/${esc(n.id)}">${esc(n.title)}</a><span class="muted small">${esc(n.updated)}</span></li>`).join("")}</ul></div>` : ""}
      <div class="panel tree"><ul>${tree.map(node).join("") || "<li class='muted'>还没有想法树</li>"}</ul></div>`;
    $("#save").onclick = async () => { const t = $("#cap").value.trim(); if (!t) return; await api("/api/ideas", { text: t }); toast("已记下"); pages.ideas(); };
  };

  pages.idea = async (slug) => {
    const d = await api(`/api/ideas/${slug}`); const m = d.meta;
    main.innerHTML = `<p><a href="#/ideas">← 想法</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${chip(m.status)}${m.parent ? `<a href="#/ideas/${esc(m.parent)}">上级：${esc(m.parent)}</a>` : ""}${(m.labs || []).map((l) => `<a href="#/labs/${esc(l)}">lab ${esc(l)}</a>`).join("")}<span>创建：${esc(m.created || "")}</span></div>
      <div class="panel" id="body"></div>
      ${m.promoted_lab ? `<p>已升级为 <a href="#/labs/${esc(m.promoted_lab)}">${esc(m.promoted_lab)}</a></p>` : m.promote_requested ? `<p class="muted">已请求升级（${esc(m.promote_requested)}），agent 正在起草任务书。</p>` :
        `<div class="panel"><b>升级为 lab 任务</b><div class="form-row"><input id="note" placeholder="给任务书的补充说明（可空）；写「不用过目」则直接执行"></div><div class="form-row"><button class="primary" id="promote">让 agent 起草任务书</button></div></div>`}`;
    $("#body").appendChild(render(d.body, dirOf(d.path)));
    if ($("#promote")) $("#promote").onclick = async () => { await api(`/api/ideas/${slug}/promote`, { note: $("#note").value }); toast("已请求"); pages.idea(slug); };
  };

  pages.runs = async (id) => {
    if (id) return pages.run(id);
    const [d, cores] = await Promise.all([api("/api/runs"), api("/api/cores").catch(() => null)]);
    const rows = d.runs.map((r) => `<li><span class="t"><a href="#/runs/${esc(r.id)}"><b>${esc(r.label || r.kind)}</b></a> <span class="small muted">${esc(r.kind)} · ${esc(r.model || "")}</span></span>${chip(r.status)}<span class="small muted">${esc(r.started || "")}</span></li>`).join("");
    const q = d.queue;
    main.innerHTML = `<h1>任务</h1>
      <div class="panel"><b>立刻执行</b><textarea id="prompt" placeholder="直接告诉 agent 要做什么（在课题目录里无人值守运行，遵守 AGENTS.md）"></textarea>
        <div class="form-row"><input id="label" placeholder="标签（可空）"><input id="model" list="models" placeholder="模型（空 = ${esc((OVERVIEW && OVERVIEW.models && OVERVIEW.models.read) || "默认")}）"><datalist id="models"><option value="claude-fable-5-1"><option value="claude-opus-5-5"><option value="claude-sonnet-5-5"></datalist>
          <select id="effort"><option value="">effort（空 = ${esc((OVERVIEW && OVERVIEW.models && OVERVIEW.models.effort) || "默认")}）</option><option>max</option><option>xhigh</option><option>high</option><option>medium</option><option>low</option></select><button class="primary" id="go">运行</button><button id="tick">处理所有待办</button></div></div>
      <div class="panel"><b>状态</b> · ${q.current ? `正在运行 <a href="#/runs/${q.current.id}">${esc(q.current.label)}</a>` : "空闲"}${q.pending.length ? ` · 排队 ${q.pending.map((p) => esc(p.label)).join(", ")}` : ""}
        ${cores ? `<br><span class="small muted">${esc(cores.advice)}</span>` : ""}</div>
      <div class="panel"><ul class="list">${rows || "<li class='muted'>还没有运行记录</li>"}</ul></div>`;
    $("#go").onclick = async () => {
      const prompt = $("#prompt").value.trim(); if (!prompt) return;
      const model = $("#model").value.trim() || null; const effort = $("#effort").value || null;
      const r = await api("/api/runs", { prompt, label: $("#label").value || "manual", model, effort }); location.hash = "#/runs/" + r.id;
    };
    $("#tick").onclick = async () => { const r = await api("/api/tick", {}); toast(r.id ? `已加入队列，待办 ${r.pending.length} 项` : "队列里已有待办处理"); pages.runs(); };
  };

  pages.run = async (id) => {
    const r = await api(`/api/runs/${encodeURIComponent(id)}`);
    main.innerHTML = `<p><a href="#/runs">← 任务</a></p><h1>${esc(r.label || r.kind)}</h1>
      <div class="meta"><span id="st">${chip(r.status)}</span><span>${esc(r.kind)}</span><span>${esc(r.model || "")}</span><span>${esc(r.started || "")}${r.ended ? " → " + esc(r.ended) : ""}</span>${r.cost_usd != null ? `<span>$${r.cost_usd.toFixed(2)}</span>` : ""}
        ${["running", "queued"].includes(r.status) ? `<button class="danger" id="stop">停止</button>` : ""}</div>
      <details><summary>提示词</summary><pre class="log">${esc(r.prompt || "")}</pre></details>
      <h2>日志</h2><div class="log" id="log">${esc(r.log || "")}</div>`;
    if ($("#stop")) $("#stop").onclick = async () => { await api(`/api/runs/${encodeURIComponent(id)}/stop`, {}); toast("已请求停止"); };
    if (["running", "queued"].includes(r.status)) {
      const log = $("#log"); log.textContent = "";
      const es = new EventSource(`/api/runs/${encodeURIComponent(id)}/stream`);
      es.onmessage = (e) => { log.textContent += JSON.parse(e.data) + "\n"; log.scrollTop = log.scrollHeight; };
      es.addEventListener("end", (e) => { es.close(); $("#st").innerHTML = chip(JSON.parse(e.data)); refreshOverview(); });
      window._es = es;
    }
  };

  // ---------- 路由 ----------
  async function route() {
    if (window._es) { window._es.close(); window._es = null; }
    const parts = location.hash.replace(/^#\/?/, "").split("/");
    const key = parts[0] || "home"; const rest = parts.slice(1).join("/");
    document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.key === key || (key === "inbox" && a.dataset.key === "refs")));
    const fn = pages[key] || pages.home;
    try { await fn(rest ? decodeURIComponent(rest) : undefined); } catch (e) { main.innerHTML = `<p class="muted">出错了：${esc(e.message)}</p>`; }
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  refreshOverview().then(route);
  setInterval(refreshOverview, 30000);
})();
