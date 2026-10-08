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
  const KIND_ZH = { route: "路线", method: "方法" };
  const zh = (s) => STATUS_ZH[s] || s || "";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // 审计标记：{derivation: {verdict,counts,...}, code: {...}}（见 rd-audit skill）
  const AUDIT_KIND_ZH = { derivation: "推导审计", code: "代码审计" };
  const auditChip = (a) => {
    if (!a) return "";
    return Object.entries(a).map(([k, v]) => {
      const c = v.counts || {}; let cls = "pass", txt = "✅";
      if (v.verdict === "major") { cls = "major"; txt = `❌ 改变结论 ${c["改变结论"] || ""}`; }
      else if (v.verdict === "minor") { cls = "minor"; txt = `⚠️ 不严谨 ${c["不严谨"] || ""}`; }
      return `<a class="chip audit ${cls}" href="${docRoute(v.path)}" title="${esc(v.date)} ${esc(v.model)}${v.handled ? "" : " · 发现未处理"}">${AUDIT_KIND_ZH[k] || k} ${txt}${v.handled ? "" : " ·待处理"}</a>`;
    }).join(" ");
  };
  const chip = (s, extra = "") => `<span class="chip ${esc(s)} ${extra}">${esc(zh(s))}</span>`;
  const kindChip = (k) => KIND_ZH[k] ? `<span class="chip kind">${KIND_ZH[k]}</span>` : "";

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
  const docRoute = (path, frag) => "#/doc/" + path.split("/").map(encodeURIComponent).join("/") + (frag ? "?h=" + encodeURIComponent(frag) : "");
  const slugId = (text) => text.trim().toLowerCase().replace(/[\s]+/g, "-").replace(/[^\p{L}\p{N}\-_]/gu, "").slice(0, 80) || "sec";
  function joinPath(baseDir, v) {
    const parts = (baseDir ? baseDir.split("/") : []);
    for (const seg of v.split("/")) {
      if (seg === "." || seg === "") continue;
      if (seg === "..") parts.pop(); else parts.push(seg);
    }
    return parts.join("/");
  }
  function render(src, baseDir = "") {
    const { src: s1, store } = protectMath(src || "");
    let html = md.render(wikilinks(s1));
    html = restoreMath(html, store);
    const div = document.createElement("div"); div.className = "md"; div.innerHTML = html;
    div.querySelectorAll('a[title^="wikilink"]').forEach((a) => { a.className = a.title === "wikilink" ? "wikilink" : "wikilink missing"; a.removeAttribute("title"); });
    // 标题锚点（目录和 notes.md#节 链接用）
    const used = {};
    div.querySelectorAll("h1, h2, h3, h4").forEach((h) => {
      let id = slugId(h.textContent); if (used[id]) id = `${id}-${++used[id]}`; else used[id] = 1;
      h.id = id;
    });
    div.querySelectorAll("img, a").forEach((el) => {
      const attr = el.tagName === "IMG" ? "src" : "href"; const v = el.getAttribute(attr) || "";
      if (!v || /^(https?:|mailto:|\/)/.test(v)) return;
      if (v.startsWith("#")) {
        // 页内锚点：hash 路由下 href="#x" 会被当成路由，改成滚动
        if (el.tagName === "A" && !v.startsWith("#/")) {
          const target = decodeURIComponent(v.slice(1));
          el.addEventListener("click", (e) => { e.preventDefault(); const t = div.querySelector(`[id="${CSS.escape(target)}"]`) || div.querySelector(`[id="${CSS.escape(slugId(target))}"]`); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); });
        }
        return;
      }
      const [pathPart, frag] = v.split("#");
      const full = joinPath(baseDir, pathPart.replace(/^\.\//, ""));
      if (el.tagName === "A" && /\.md$/i.test(pathPart)) {
        el.setAttribute("href", docRoute(full, frag)); // 项目内 markdown 站内打开
        return;
      }
      el.setAttribute(attr, "/api/file?path=" + encodeURIComponent(full));
      if (el.tagName === "A") el.target = "_blank";
    });
    // 图：alt 文字当图注，点开看原图
    div.querySelectorAll("img").forEach((img) => {
      if (img.closest("a")) return;
      const fig = document.createElement("figure"); fig.className = "fig";
      const a = document.createElement("a"); a.href = img.src; a.target = "_blank";
      img.replaceWith(fig); a.appendChild(img); fig.appendChild(a);
      if (img.alt) { const cap = document.createElement("figcaption"); cap.textContent = img.alt; fig.appendChild(cap); }
    });
    // 审计发现表（有「等级」列）→ 一条发现一张卡；旧格式的报告也能读
    div.querySelectorAll("table").forEach((t) => {
      const heads = [...t.querySelectorAll("thead th")].map((th) => th.textContent.trim());
      const gi = heads.indexOf("等级"); if (gi < 0 || heads.length < 4) return;
      const wrap = document.createElement("div"); wrap.className = "findings";
      t.querySelectorAll("tbody tr").forEach((tr) => {
        const cells = [...tr.children]; if (!cells.length) return;
        const grade = (cells[gi] ? cells[gi].textContent : "").trim();
        const cls = grade === "改变结论" ? "major" : grade === "不严谨" ? "minor" : "typo";
        const li = heads.indexOf("位置"); const idx = heads.indexOf("#") >= 0 ? heads.indexOf("#") : 0;
        const sec = document.createElement("section"); sec.className = `finding ${cls}`;
        let html = `<div class="finding-head"><span class="chip audit ${cls}">${esc(grade)}</span> <b>${cells[idx] ? cells[idx].innerHTML : ""}</b>${li >= 0 && cells[li] ? ` · <span class="loc">${cells[li].innerHTML}</span>` : ""}</div>`;
        heads.forEach((h, i) => { if (i === gi || i === idx || i === li || !cells[i]) return; html += `<p><b>${esc(h)}</b>${cells[i].innerHTML}</p>`; });
        sec.innerHTML = html; wrap.appendChild(sec);
      });
      t.replaceWith(wrap);
    });
    if (window.renderMathInElement) {
      renderMathInElement(div, { delimiters: [{ left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true }, { left: "\\(", right: "\\)", display: false }, { left: "$", right: "$", display: false }], throwOnError: false });
    }
    return div;
  }
  // 长文的目录：h2/h3 超过 3 个才显示
  function tocFor(div, min = 4) {
    const hs = [...div.querySelectorAll("h2, h3")];
    if (hs.length < min) return null;
    const nav = document.createElement("nav"); nav.className = "toc";
    nav.innerHTML = `<b>目录</b>` + hs.map((h) => `<a class="${h.tagName.toLowerCase()}" data-id="${esc(h.id)}">${esc(h.textContent)}</a>`).join("");
    nav.querySelectorAll("a").forEach((a) => a.onclick = (e) => { e.preventDefault(); const t = div.querySelector(`[id="${CSS.escape(a.dataset.id)}"]`); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); });
    return nav;
  }
  function scrollToFrag(div, frag) {
    if (!frag) return;
    const t = div.querySelector(`[id="${CSS.escape(frag)}"]`) || div.querySelector(`[id="${CSS.escape(slugId(frag))}"]`);
    if (t) setTimeout(() => t.scrollIntoView({ block: "start" }), 50);
  }
  const dirOf = (p) => p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";
  // 列表/树里的一行预览（当前回答）：渲染 markdown 与公式；用 data-md 延迟渲染
  const answerHtml = (text, cls = "answer") => text ? `<div class="${cls}" data-md="${esc(text)}"></div>` : "";
  function renderAnswers(root = main) {
    root.querySelectorAll("[data-md]").forEach((el) => { el.replaceChildren(render(el.dataset.md)); el.removeAttribute("data-md"); });
  }
  const clip = (s, n = 160) => { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

  // ---------- 总览 / 红点 ----------
  async function refreshOverview() {
    try {
      OVERVIEW = await api("/api/overview");
      LINKS = await api("/api/links");
    } catch (e) { console.error(e); return; }
    const a = OVERVIEW.attention;
    $("#brand-name").textContent = OVERVIEW.project.name || "课题";
    // 只读访客（不在 config.toml server.write_from 网段内）：隐藏所有操作控件
    document.body.classList.toggle("readonly", !!OVERVIEW.readonly);
    $("#host").textContent = (OVERVIEW.readonly ? "只读 · " : "") + OVERVIEW.host;
    document.title = (a.total ? `(${a.total}) ` : "") + (OVERVIEW.project.name || "课题");
    const running = (OVERVIEW.queue.current ? 1 : 0) + OVERVIEW.queue.pending.length;
    const counts = { ...a.counts, runs: running };
    document.querySelectorAll(".badge").forEach((b) => { const n = counts[b.dataset.badge] || 0; b.textContent = n; b.classList.toggle("on", n > 0); });
    // 本机其他课题的 dashboard：同一主机、不同端口
    try {
      const others = (await api("/api/projects")).filter((p) => p.name !== OVERVIEW.project.name && p.exists);
      const sel = $("#projects");
      if (others.length) {
        sel.innerHTML = `<option value="">切换课题…</option>` + others.map((p) => `<option value="${p.port}">${esc(p.name)}${p.listening ? "" : "（未启动）"}</option>`).join("");
        sel.style.display = "";
        sel.onchange = () => { if (sel.value) location.href = `${location.protocol}//${location.hostname}:${sel.value}/`; };
      } else { sel.style.display = "none"; }
    } catch (e) { /* 注册表不可用就不显示 */ }
  }

  // ---------- 页面 ----------
  const pages = {};

  pages.home = async () => {
    await refreshOverview();
    const o = OVERVIEW; const a = o.attention;
    let cores = null; try { cores = await api("/api/cores"); } catch (e) { /* 可选 */ }
    const items = a.items.map((it) => `<li><a href="${routeFor(it.kind, it.id)}"><b>${esc(it.title)}</b></a><span class="t muted">${esc(it.why)}</span></li>`).join("");
    const log = o.log.map((e) => `<li><span class="muted small">${esc(e.time)}</span><span class="t">${esc(e.who)} · ${esc(clip(e.what, 220))}</span></li>`).join("");
    const q = o.queue; const cur = q.current ? `agent 正在运行：<a href="#/runs/${q.current.id}">${esc(q.current.label)}</a>` : "agent 空闲";
    const jobs = (cores && cores.jobs || []).filter((j) => !o.project.name || j.project === o.project.name);
    const jobsHtml = jobs.length ? `后台数值：${jobs.map((j) => `<span class="chip running">${esc(j.label)} · ${j.cores} 核</span>`).join(" ")}` : "没有登记中的后台数值";
    main.innerHTML = `
      <div class="row">
        <div class="col" style="flex:2">
          ${o.status ? `<div class="panel status" id="status"></div>` : `<div class="panel"><p class="muted">还没有 <code>STATUS.md</code>（课题状态页）。agent 在下次收尾时会建立它；也可以 <code>rd update</code> 补一个空模板。</p></div>`}
        </div>
        <div class="col">
          <div class="panel ${a.total ? "attn" : ""}"><h2 style="margin-top:0">需要你处理${a.total ? ` (${a.total})` : ""}</h2><ul class="list">${items || "<li class='muted'>没有待处理的事</li>"}</ul></div>
          <div class="panel"><h2 style="margin-top:0">agent 与数值</h2><p>${cur}${q.pending.length ? `，排队 ${q.pending.length}` : ""} · <a href="#/runs">任务页</a></p>
            <p class="small">${jobsHtml}</p>
            ${o.digest && o.digest.answered.length ? `<p class="small"><a href="#/discussion">${o.digest.answered.length} 条回答</a>等待统一消化，预计 ${esc(o.digest.next_digest_str)}</p>` : ""}</div>
          <div class="stats small">
            <a class="stat" href="#/refs"><b>${o.counts.cards}</b><span>文献卡片</span></a>
            <a class="stat" href="#/wiki"><b>${o.counts.wiki}</b><span>wiki 页</span></a>
            <a class="stat" href="#/labs"><b>${o.counts.labs}</b><span>lab</span></a>
            <a class="stat" href="#/ideas"><b>${o.counts.ideas}</b><span>问题</span></a>
          </div>
        </div>
      </div>
      <details class="panel"><summary>最近动态（${o.log.length} 条）</summary><ul class="list small">${log}</ul></details>`;
    if (o.status) {
      const box = $("#status");
      box.innerHTML = `<div class="meta"><span>课题状态 · 更新 ${esc(o.status.updated)}</span><a href="${docRoute("STATUS.md")}">全文</a></div>`;
      box.appendChild(render(o.status.body, ""));
    }
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
      await api(`/api/inbox/${encodeURIComponent(li.dataset.key)}/${b.dataset.act}`, {});
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
    const body = render(d.body, dirOf(d.path)); $("#body").appendChild(body);
    const toc = tocFor(body, 5); if (toc) $("#body").prepend(toc);
  };

  pages.inbox = async (key) => {
    const d = await api(`/api/inbox/${encodeURIComponent(key)}`); const m = d.meta;
    main.innerHTML = `<p><a href="#/refs">← 文献</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${chip(m.status)}<a href="${esc(m.url || "https://arxiv.org/abs/" + m.arxiv)}" target="_blank">arXiv:${esc(m.arxiv)}</a><span>${esc(m.published || "")}</span></div>
      ${m.status === "pending" ? `<p><button class="primary" id="ok">通过，下载并精读</button> <button id="no">拒绝</button></p>` : ""}
      <div class="panel" id="body"></div>`;
    $("#body").appendChild(render(d.body, dirOf(d.path)));
    const act = (s) => async () => { await api(`/api/inbox/${encodeURIComponent(key)}/${s}`, {}); toast("已记录"); location.hash = "#/refs"; };
    if ($("#ok")) { $("#ok").onclick = act("approved"); $("#no").onclick = act("rejected"); }
  };

  pages.wiki = async (slug) => {
    const list = await api("/api/wiki");
    const side = list.map((p) => `<a href="#/wiki/${esc(p.id)}" class="${p.id === slug ? "cur" : ""}">${esc(p.title)}</a>`).join("");
    let content = `<p class="muted">左侧选择一页。wiki 是当前理解的汇编，由 agent 维护并随进展重写；[[双括号]] 互相链接。课题到哪了看<a href="#/">首页</a>。</p>`;
    main.innerHTML = `<h1>Wiki</h1><div class="two"><div class="side panel">${side || "<span class='muted'>还没有页面</span>"}</div><div id="content">${content}</div></div>`;
    if (slug) {
      const d = await api(`/api/wiki/${slug}`);
      const back = (d.backlinks || []).map((b) => `<a href="#/wiki/${esc(b.id)}">${esc(b.title)}</a>`).join(" · ");
      const c = $("#content"); c.innerHTML = `<h2 style="margin-top:0">${esc(d.title)}</h2><div class="meta"><span>更新：${esc(d.updated)}</span>${(d.meta.tags || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("")}${(d.meta.audited_by || []).length ? `<span class="chip audit pass" title="${esc((d.meta.audited_by || []).join(", "))}">依据已审计</span>` : ""}</div><div id="toc-top"></div><div class="panel" id="body"></div>${back ? `<p class="small muted">反向链接：${back}</p>` : ""}`;
      const body = render(d.body, dirOf(d.path)); $("#body").appendChild(body);
      const toc = tocFor(body, 5); if (toc) $("#toc-top").appendChild(toc);
    }
  };

  pages.labs = async (id) => {
    if (id) return pages.lab(id);
    const list = await api("/api/labs");
    const rows = list.map((x) => `<li class="lab-row"><span class="t"><a href="#/labs/${esc(x.id)}"><b>${esc(x.short || x.title)}</b></a> <span class="small muted">${esc(x.id)}</span>
        ${x.answer ? answerHtml(x.answer) : x.question ? answerHtml("问题：" + x.question, "answer muted") : ""}</span>${chip(x.meta.status)}${auditChip(x.audit)}${x.meta.machine ? `<span class="chip">${esc(x.meta.machine)}</span>` : ""}<span class="small muted">${esc(x.updated)}</span></li>`).join("");
    main.innerHTML = `<h1>Lab</h1><p class="muted small">每个任务一个文件夹：任务书 brief.md、摘要 report.md（首屏：问题 / 当前回答 / 为什么信 / 边界）、推导与分析 notes.md、数据去向 DATA.md。想法页里可以把问题升级成 lab。</p><div class="panel"><ul class="list">${rows || "<li class='muted'>还没有任务</li>"}</ul></div>`;
    renderAnswers();
  };

  pages.lab = async (id) => {
    const d = await api(`/api/labs/${encodeURIComponent(id)}`); const m = d.meta; const st = m.status;
    const labDir = dirOf(d.path);
    const auditLine = `${auditChip(d.audit) || "<span class='muted'>还没审计</span>"} <button id="audit-der" class="small">推导审计</button> <button id="audit-code" class="small">代码审计</button>${(d.audits || []).length ? ` <span class="small muted">历史：${d.audits.map((a) => `<a href="${docRoute(a.path)}">${esc(a.date)} ${esc(AUDIT_KIND_ZH[a.kind] || a.kind)}</a>`).join(" · ")}</span>` : ""}`;
    const pdfs = (d.pdfs || []).map((p) => `<a class="btn" href="/api/file?path=${encodeURIComponent(labDir + "/" + p)}" target="_blank">📄 ${esc(p)}</a>`).join(" ");
    const notesBtn = d.notes && /\.md$/i.test(d.notes) ? `<a class="btn primary" href="${docRoute(joinPath(labDir, d.notes))}">📖 推导与分析 ${esc(d.notes)}</a>` : "";
    const handoff = (d.files || []).some((f) => f.name === "handoff.md") ? `<a class="btn" href="${docRoute(labDir + "/handoff.md")}">交接单</a>` : "";
    const files = (d.files || []).map((f) => /\.md$/i.test(f.name) ? `<li><a href="${docRoute(f.path)}">${esc(f.name)}</a> <span class="muted small">${(f.size / 1024).toFixed(1)} KB</span></li>` : `<li><a href="/api/file?path=${encodeURIComponent(f.path)}" target="_blank">${esc(f.name)}</a> <span class="muted small">${(f.size / 1024).toFixed(1)} KB</span></li>`).join("");
    const short = d.short && d.short !== d.title ? d.short : d.title;
    main.innerHTML = `<p><a href="#/labs">← Lab</a></p><h1>${esc(short)}</h1>${short !== d.title ? `<p class="subtitle muted">${esc(d.title)}</p>` : ""}
      <div class="meta">${chip(st)}<span>${esc(id)}</span>${m.idea ? `<a href="#/ideas/${esc(m.idea)}">来自问题：${esc(m.idea)}</a>` : ""}${(m.discussions || []).map((x) => `<a href="#/discussion/${esc(x)}">讨论 ${esc(x)}</a>`).join("")}${m.machine ? `<span>机器：${esc(m.machine)}</span>` : ""}<span>更新：${esc(d.updated)}</span></div>
      <p>${st === "awaiting_review" ? `<button class="primary" id="approve">批准，开始执行</button> ` : ""}
         ${["running", "approved"].includes(st) ? "" : `<button id="park">搁置</button> `}${st === "parked" ? `<button id="unpark">恢复为待过目</button>` : ""} ${notesBtn} ${pdfs} ${handoff}</p>
      <p class="small">审计：${auditLine}</p>
      ${d.report ? `<div class="panel" id="report"></div>` : `<div class="panel muted">还没有报告摘要（report.md）。</div>`}
      ${(d.images || []).length ? `<details class="panel" ${d.report ? "" : "open"}><summary>全部图 (${d.images.length})</summary><div class="gallery">${d.images.map((im) => `<figure class="fig"><a href="/api/file?path=${encodeURIComponent(im.path)}" target="_blank"><img src="/api/file?path=${encodeURIComponent(im.path)}" alt="${esc(im.caption || im.name)}" loading="lazy"></a><figcaption>${esc(im.caption || im.name)}</figcaption></figure>`).join("")}</div></details>` : `<p class="muted small">这个 lab 还没有图（agent 应把图放在 fig/ 并嵌进 report.md）。</p>`}
      <details class="panel" ${["awaiting_review", "draft", "parked"].includes(st) ? "open" : ""}><summary>任务书 brief.md${m.comments_pending ? " · 有你的意见待 agent 处理" : ""}</summary><div id="brief"></div></details>
      <div class="panel write-only"><b>对任务书的意见</b><textarea id="cmt" placeholder="${["awaiting_review", "draft", "parked"].includes(st) ? "写下你对这份任务书的意见（要改什么、加什么、删什么）。提交后 agent 会按意见修改任务书并在意见下回复，改完仍等你过目；写「可以开始」就直接执行。" : "任务已在进行：意见会记进任务书，agent 下次运行时先读它。"}"></textarea>
        <div class="form-row"><button class="primary" id="comment">提交意见</button><span class="muted small">原话会原样追加到任务书的「用户意见」一节</span></div></div>
      ${d.data ? `<details class="panel"><summary>数据去向 DATA.md</summary><div id="data"></div></details>` : ""}
      <details class="panel"><summary>文件 (${(d.files || []).length})</summary><ul class="list small">${files}</ul></details>`;
    $("#brief").appendChild(render(d.body, labDir));
    if (d.report) $("#report").appendChild(render(d.report.body, labDir));
    if (d.data) $("#data").appendChild(render(d.data.body, labDir));
    if ($("#approve")) $("#approve").onclick = async () => { await api(`/api/labs/${encodeURIComponent(id)}/approve`, {}); toast("已批准，agent 开始执行"); pages.lab(id); refreshOverview(); };
    if ($("#park")) $("#park").onclick = async () => { await api(`/api/labs/${encodeURIComponent(id)}/status/parked`, {}); pages.lab(id); };
    if ($("#comment")) $("#comment").onclick = async () => { const t = $("#cmt").value.trim(); if (!t) return toast("先写意见"); await api(`/api/labs/${encodeURIComponent(id)}/comment`, { text: t }); toast(["awaiting_review", "draft", "parked"].includes(st) ? "已记下，agent 开始按意见修改任务书" : "已记下，agent 下次运行会读到"); pages.lab(id); refreshOverview(); };
    if ($("#unpark")) $("#unpark").onclick = async () => { await api(`/api/labs/${encodeURIComponent(id)}/status/awaiting_review`, {}); pages.lab(id); };
    const auditGo = (kind) => async () => { const r = await api(`/api/labs/${encodeURIComponent(id)}/audit/${kind}`, {}); toast(kind === "code" ? "已加入队列：代码审计（Codex）" : "已加入队列：推导审计（Codex）"); location.hash = "#/runs/" + r.id; };
    if ($("#audit-der")) $("#audit-der").onclick = auditGo("derivation");
    if ($("#audit-code")) $("#audit-code").onclick = auditGo("code");
    api("/api/seen", { kind: "lab", id }).then(refreshOverview);
  };

  // 通用文档页：项目内任意 markdown（notes.md、handoff.md、STATUS.md、writing-test/…）
  // base：相对链接按哪个目录解析（草稿、试写等"为别的位置写的" markdown 用 ?base=<目录> 或 frontmatter base: 指定）
  pages.doc = async (path, frag, base) => {
    let d;
    try { d = await api(`/api/raw?path=${encodeURIComponent(path)}`); }
    catch (e) { main.innerHTML = `<p class="muted">找不到 ${esc(path)}</p>`; return; }
    const parts = path.split("/");
    const crumbs = [`<a href="#/">课题</a>`];
    if (parts[0] === "labs" && parts[1]) crumbs.push(`<a href="#/labs">Lab</a>`, `<a href="#/labs/${esc(parts[1])}">${esc(parts[1])}</a>`);
    else if (parts[0] === "wiki") crumbs.push(`<a href="#/wiki">Wiki</a>`);
    else if (parts[0] === "ideas") crumbs.push(`<a href="#/ideas">问题</a>`);
    else if (parts[0] === "discussion") crumbs.push(`<a href="#/discussion">讨论</a>`);
    for (let i = (parts[0] === "labs" ? 2 : 1); i < parts.length - 1; i++) crumbs.push(`<span>${esc(parts[i])}</span>`);
    crumbs.push(`<span>${esc(parts[parts.length - 1])}</span>`);
    const title = d.meta.title || (d.body.match(/^#\s+(.+)$/m) || [])[1] || parts[parts.length - 1];
    const sib = (d.siblings || []).map((s) => `<a href="${docRoute(dirOf(path) ? dirOf(path) + "/" + s : s)}">${esc(s)}</a>`).join("");
    let auditBanner = "";
    if ((d.meta.kind === "derivation" || d.meta.kind === "code") && path.includes("/audit/")) {
      const c = d.meta.counts || {}; const v = d.meta.verdict || "pass";
      const vtxt = v === "major" ? "❌ 有改变结论的发现" : v === "minor" ? "⚠️ 有不严谨之处" : "✅ 通过";
      auditBanner = `<div class="audit-banner ${esc(v)}"><b>${esc(vtxt)}</b>
        <span class="chip audit major">改变结论 ${c["改变结论"] ?? 0}</span><span class="chip audit minor">不严谨 ${c["不严谨"] ?? 0}</span><span class="chip audit typo">typo ${c["typo"] ?? 0}</span>
        <span class="small muted">${esc(d.meta.model || "")} · ${esc(String(d.meta.date || ""))} · commit ${esc(String(d.meta.commit || ""))}</span>
        <span class="chip ${d.meta.handled ? "done" : "open"}">${d.meta.handled ? "发现已处理" : "发现待处理"}</span>
        ${d.meta.lab ? `<a href="#/labs/${esc(d.meta.lab)}">← 回到 lab</a>` : ""}</div>`;
    }
    main.innerHTML = `<p class="crumbs small">${crumbs.join(" / ")}</p><h1>${esc(title)}</h1>
      <div class="meta"><span>更新：${esc(d.updated || "")}</span>${d.meta.status ? chip(d.meta.status) : ""}<a href="/api/file?path=${encodeURIComponent(path)}" target="_blank">原文件</a></div>
      ${auditBanner}<div class="two"><div class="side panel" id="toc-side">${sib ? `<div class="small muted" style="margin-top:10px">同文件夹</div>${sib}` : ""}</div><div class="panel" id="body"></div></div>`;
    const baseDir = base || d.meta.base || dirOf(path);
    const body = render(d.body, baseDir); $("#body").appendChild(body);
    const toc = tocFor(body, 3); if (toc) $("#toc-side").prepend(toc);
    if (!toc && !sib) { $("#toc-side").remove(); $("#body").parentElement.style.gridTemplateColumns = "1fr"; }
    scrollToFrag(body, frag);
  };

  pages.discussion = async (id) => {
    if (id) return pages.thread(id);
    const [list, dg] = await Promise.all([api("/api/discussion"), api("/api/digest").catch(() => null)]);
    const grp = (s) => list.filter((x) => x.meta.status === s);
    const digestBar = dg && dg.answered.length ? `<div class="panel attn"><b>${dg.answered.length} 条回答等待统一消化</b> · 为了把互相关联的回答放在一起考虑，agent 每 ${dg.digest_minutes} 分钟消化一次，下次约 ${esc(dg.next_digest_str)}。
        <button id="digest-now" style="margin-left:8px">现在就消化</button></div>` : "";
    const row = (x) => `<li><span class="t"><a href="#/discussion/${esc(x.id)}"><b>${esc(x.title)}</b></a> <span class="small muted">${x.meta.asked_by === "user" ? "你问 agent" : "agent 问你"}${x.meta.lab ? " · " + esc(x.meta.lab) : ""}</span></span>${chip(x.meta.status)}<span class="small muted">${esc(x.updated)}</span></li>`;
    const sec = (title, arr) => arr.length ? `<h2>${title} (${arr.length})</h2><div class="panel"><ul class="list">${arr.map(row).join("")}</ul></div>` : "";
    main.innerHTML = `<h1>讨论</h1>${digestBar}
      <div class="panel"><b>向 agent 提问</b><div class="form-row"><input id="qt" placeholder="标题"></div><textarea id="qb" placeholder="问题内容，可以写公式 $…$"></textarea><div class="form-row"><button class="primary" id="ask">提交</button><span class="muted small">提交后 agent 会去读相关材料并回答</span></div></div>
      ${sec("等你回答", grp("open").filter((x) => x.meta.asked_by === "agent"))}${sec("等 agent 回答", grp("open").filter((x) => x.meta.asked_by === "user"))}${sec("你已回答，等待统一消化", grp("answered"))}${sec("agent 已消化", grp("digested"))}${sec("已解决", grp("resolved"))}
      ${list.length ? "" : "<p class='muted'>还没有讨论。agent 在遇到需要你裁决的问题时会在这里提问。</p>"}`;
    if ($("#digest-now")) $("#digest-now").onclick = async () => { const r = await api("/api/digest", {}); toast(r.id ? "已开始统一消化" : "消化已在队列里"); pages.discussion(); };
    $("#ask").onclick = async () => {
      const title = $("#qt").value.trim(), text = $("#qb").value.trim(); if (!title || !text) return toast("标题和内容都要填");
      const r = await api("/api/discussion", { title, text }); location.hash = "#/discussion/" + r.id;
    };
  };

  pages.thread = async (id) => {
    const d = await api(`/api/discussion/${encodeURIComponent(id)}`); const m = d.meta;
    main.innerHTML = `<p><a href="#/discussion">← 讨论</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${chip(m.status)}<span>${m.asked_by === "user" ? "你问 agent" : "agent 问你"}</span>${m.lab ? `<a href="#/labs/${esc(m.lab)}">相关任务 ${esc(m.lab)}</a>` : ""}${m.idea ? `<a href="#/ideas/${esc(m.idea)}">相关问题</a>` : ""}<span>创建：${esc(m.created || "")}</span></div>
      <div class="panel" id="body"></div>
      <div class="panel"><b>${m.asked_by === "agent" ? "你的回答" : "补充"}</b><textarea id="ans" placeholder="写下你的裁决或想法。回答不会当场处理：agent 每五小时把这段时间的所有回答放在一起统一消化（讨论列表页可以手动“现在就消化”）。"></textarea>
        <div class="form-row"><button class="primary" id="send">提交回答</button>${m.status !== "resolved" ? `<button id="resolve">标记已解决</button>` : ""}</div></div>`;
    $("#body").appendChild(render(d.body, dirOf(d.path)));
    $("#send").onclick = async () => { const t = $("#ans").value.trim(); if (!t) return; await api(`/api/discussion/${encodeURIComponent(id)}/answer`, { text: t }); const dg = await api("/api/digest").catch(() => null); toast(dg && dg.next_digest_str ? `已提交，将在 ${dg.next_digest_str} 左右与其他回答一起消化` : "已提交"); pages.thread(id); refreshOverview(); };
    if ($("#resolve")) $("#resolve").onclick = async () => { await api(`/api/discussion/${encodeURIComponent(id)}/resolve`, {}); pages.thread(id); refreshOverview(); };
    api("/api/seen", { kind: "discussion", id }).then(refreshOverview);
  };

  // ---------- 想法页：问题树的卡片分支图 ----------
  // 每个节点一张固定宽度的卡片（编号、状态、标题两行、frontmatter verdict 一句结论）；点卡片在右侧打开详情（宽屏一列、窄屏抽屉）；
  // 节点超过 24 个时自动只展开选中分支；可缩放。原话一字不动地保存在节点里，agent 只整理结构和回答。
  function mdSections(body) {
    const out = {}; let cur = null;
    for (const line of (body || "").split("\n")) {
      const m = line.match(/^##\s+(.+?)\s*$/);
      if (m) { cur = m[1]; out[cur] = []; continue; }
      if (cur) out[cur].push(line);
    }
    for (const k in out) out[k] = out[k].join("\n").trim();
    return out;
  }
  const firstSentence = (t) => (t || "").replace(/\*\*/g, "").split(/[。；！？\n]/)[0].slice(0, 40);
  const inlineMd = (text) => { const d = render(text || "", "ideas"); return d.innerHTML.replace(/^<p>|<\/p>\s*$/g, ""); };

  pages.ideas = async (slug) => {
    if (slug) return pages.idea(slug);
    const d = await api("/api/ideas");
    const ROOTS = d.tree.filter((n) => !n.id.startsWith("inbox/")); const INBOX = d.tree.filter((n) => n.id.startsWith("inbox/"));
    const NODES = {}; let SEL = null, MODE = "auto", ZOOM = null, USER_ZOOM = false;
    const CW = 232, CH = 150, GX = 18, GY = 56;
    const count = (ns) => ns.reduce((n, x) => n + 1 + count(x.children), 0);
    (function index(ns, parent = null, depth = 0) { for (const n of ns) { n.parent = parent; n.depth = depth; n.open = true; NODES[n.id] = n; index(n.children, n, depth + 1); } })(ROOTS);
    const focusOn = () => MODE === "focus" || (MODE === "auto" && count(ROOTS) > 24);
    const applyFocus = () => { const open = new Set(); for (let n = SEL; n; n = n.parent) open.add(n.id); (function w(ns) { for (const n of ns) { n.open = open.has(n.id) || n.depth === 0; w(n.children); } })(ROOTS); };
    const isDesc = (n, anc) => { for (let p = n.parent; p; p = p.parent) if (p.id === anc.id) return true; return false; };

    main.innerHTML = `<div class="qtree" id="qtree">
      <div class="qbar"><h1>问题树</h1><span class="legend" id="legend"></span><span class="spacer"></span>
        <span class="zoom"><button id="z-out" title="缩小">−</button><span class="pct" id="z-pct">100%</span><button id="z-in" title="放大">＋</button><button id="z-fit" title="按宽度适应">适应</button><button id="z-100" title="实际大小">1:1</button></span>
        <button id="mode-all">全部展开</button><button id="mode-focus">只看选中分支</button></div>
      <div class="capture"><textarea id="cap" placeholder="速记一个想法：模糊的也行，原话会被原样保存；agent 会整理挂到树上，不会改你的话。"></textarea><div><button class="primary" id="save">记下</button></div></div>
      ${INBOX.length ? `<div class="inbox"><b>未整理 (${INBOX.length})</b> ${INBOX.map((n) => `<a href="#/ideas/${esc(n.id)}">${esc(n.title)}</a>`).join("")}</div>` : ""}
      <div class="wrap" id="wrap">
        <div class="canvas-outer" id="outer"><div class="fit-note" id="fit-note"></div><div class="canvas-scale" id="scale"><div class="canvas" id="canvas"><svg id="links"></svg></div></div></div>
        <aside class="qdetail" id="detail"></aside>
      </div></div>`;

    const measure = (n) => { n.w = (n.open && n.children.length) ? n.children.reduce((s, c) => s + measure(c), 0) : 1; return n.w; };
    const place = (n, x0) => { n.x = x0 + n.w / 2; let x = x0; if (n.open) for (const c of n.children) { place(c, x); x += c.w; } };
    function draw() {
      const canvas = $("#canvas"), svg = $("#links"), outer = $("#outer"); if (!canvas) return;
      $("#wrap").classList.toggle("wide", window.innerWidth >= 1100); $("#wrap").classList.toggle("open", !!SEL);
      canvas.querySelectorAll(".qcard").forEach((c) => c.remove()); svg.innerHTML = "";
      let x = 0; for (const r of ROOTS) { measure(r); place(r, x); x += r.w; }
      const colW = CW + GX, rowH = CH + GY; let maxDepth = 0;
      const visible = []; (function walk(ns) { for (const n of ns) { visible.push(n); maxDepth = Math.max(maxDepth, n.depth); if (n.open) walk(n.children); } })(ROOTS);
      const W = Math.max(x * colW, CW), H = (maxDepth + 1) * rowH - GY;
      canvas.style.width = W + "px"; canvas.style.height = H + "px"; svg.setAttribute("width", W); svg.setAttribute("height", H + GY);
      const avail = outer.clientWidth - 40; const fit = Math.max(0.75, Math.min(1, avail / W));
      if (!USER_ZOOM) ZOOM = fit;
      const k = ZOOM; const sc = $("#scale");
      sc.style.transform = `scale(${k})`; sc.style.width = W + "px"; sc.style.height = (H * k) + "px"; sc.style.marginLeft = Math.max(0, (avail - W * k) / 2) + "px";
      $("#z-pct").textContent = Math.round(k * 100) + "%";
      $("#fit-note").textContent = (W * k > avail) ? "画布比窗口宽，可以横向滚动或缩小" : "";
      const px = (n) => n.x * colW - CW / 2, py = (n) => n.depth * rowH;
      const onPath = new Set(); for (let n = SEL; n; n = n.parent) onPath.add(n.id);
      for (const n of visible) {
        if (n.parent && n.parent.open) {
          const x1 = px(n.parent) + CW / 2, y1 = py(n.parent) + CH, x2 = px(n) + CW / 2, y2 = py(n), ym = y1 + GY / 2;
          const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
          p.setAttribute("d", `M${x1},${y1} V${ym} H${x2} V${y2}`); if (onPath.has(n.id) && onPath.has(n.parent.id)) p.classList.add("hot"); svg.appendChild(p);
        }
        const card = document.createElement("div"); card.dataset.id = n.id;
        card.className = "qcard" + (n.depth === 0 ? " root" : "") + (SEL && SEL.id === n.id ? " sel" : "") + (SEL && !onPath.has(n.id) && !isDesc(n, SEL) ? " dim" : "");
        card.style.left = px(n) + "px"; card.style.top = py(n) + "px";
        const q = (n.title.match(/^(Q\d+[a-z]?)\s/) || [])[1] || ""; const title = q ? n.title.slice(q.length + 1) : n.title;
        const verdict = n.meta.verdict;
        card.innerHTML = `<div class="top">${q ? `<span class="q">${esc(q)}</span>` : ""}${kindChip(n.meta.kind)}${chip(n.meta.status)}</div>
          <div class="title" title="${esc(n.title)}">${esc(title)}</div>
          <div class="verdict${verdict ? "" : " fallback"}">${verdict ? inlineMd(verdict) : (n.answer ? inlineMd(firstSentence(n.answer)) : "<i>还没有当前回答</i>")}</div>
          <div class="foot"><span>${(n.meta.labs || []).map((l) => `<a href="#/labs/${esc(l)}" title="${esc(l)}">lab ${esc(l.slice(0, 2))}</a>`).join(" ")}</span>
            ${n.children.length ? `<span class="tog">${n.open ? "▾ 收起" : `▸ ${count(n.children)} 个子问题`}</span>` : ""}</div>`;
        card.onclick = (e) => { if (e.target.classList.contains("tog")) { n.open = !n.open; draw(); return; } if (e.target.tagName === "A") return; select(n); };
        canvas.appendChild(card);
      }
      $("#legend").textContent = `${count(ROOTS)} 个节点 · ${visible.length} 个显示中 · ${MODE === "auto" ? (focusOn() ? "自动：只展开选中分支" : "自动：全部展开") : MODE === "all" ? "全部展开" : "只看选中分支"}`;
      $("#mode-all").classList.toggle("on", MODE === "all"); $("#mode-focus").classList.toggle("on", MODE === "focus");
    }
    function revealCard(n) {
      const el = $(`.qcard[data-id="${CSS.escape(n.id)}"]`); if (!el) return;
      el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
      if (!$("#wrap").classList.contains("wide")) { const r = el.getBoundingClientRect(); const limit = window.innerWidth - 420 - 16; if (r.right > limit) $("#outer").scrollBy({ left: r.right - limit, behavior: "smooth" }); }
    }
    async function select(n) {
      SEL = n; if (focusOn()) { applyFocus(); n.open = true; } draw(); revealCard(n);
      const dt = $("#detail");
      dt.innerHTML = `<button class="close" id="close">关闭 ✕</button><h2>${esc(n.title)}</h2>
        <div class="meta">${kindChip(n.meta.kind)}${chip(n.meta.status)}${n.parent ? `<a href="#" data-sel="${esc(n.parent.id)}">上级：${esc(n.parent.title.replace(/^Q\d+[a-z]?\s/, "").slice(0, 16))}…</a>` : ""}${(n.meta.labs || []).map((l) => `<a href="#/labs/${esc(l)}">lab ${esc(l)}</a>`).join("")}<a href="#/ideas/${esc(n.id)}">完整页面 ↗</a></div>
        ${n.meta.verdict ? `<div class="verdict-line">${inlineMd(n.meta.verdict)}</div>` : ""}
        <h3>当前回答</h3><div class="answer-box" id="ans"><span class="muted small">加载中…</span></div><div id="rest"></div>`;
      const wire = () => { dt.querySelectorAll("a[data-sel]").forEach((a) => a.onclick = (e) => { e.preventDefault(); select(NODES[a.dataset.sel]); }); $("#close").onclick = () => { SEL = null; dt.innerHTML = ""; draw(); }; };
      wire();
      try {
        const full = await api(`/api/ideas/${encodeURIComponent(n.id)}`); if (SEL !== n) return;
        const S = mdSections(full.body); const ans = $("#ans"); ans.innerHTML = ""; ans.appendChild(render(S["当前回答"] || "_（还没有当前回答）_", "ideas"));
        let html = "";
        if (S["证据与链接"]) html += `<h3>关键证据与链接</h3><div id="ev"></div>`;
        if (n.children.length) html += `<h3>子问题</h3><div class="kids">${n.children.map((c) => `<a href="#" data-sel="${esc(c.id)}">${esc(c.title)}<br><span class="v">→ ${esc(c.meta.verdict || firstSentence(c.answer) || "未回答")}</span></a>`).join("")}</div>`;
        html += `<h3>原话与历史</h3>`;
        for (const h of ["原话", "agent 的理解", "历史", "派生", "agent 备注"]) if (S[h]) html += `<details ${h === "原话" ? "open" : ""}><summary>${esc(h)}</summary><div data-sec="${esc(h)}"></div></details>`;
        const rest = $("#rest"); rest.innerHTML = html;
        if (S["证据与链接"]) $("#ev").appendChild(render(S["证据与链接"], "ideas"));
        rest.querySelectorAll("[data-sec]").forEach((el) => el.appendChild(render(S[el.dataset.sec], "ideas")));
        wire();
      } catch (e) { const a = $("#ans"); if (a) a.textContent = "加载失败：" + e.message; }
    }
    const setZoom = (z) => { USER_ZOOM = true; ZOOM = Math.min(2, Math.max(0.4, z)); draw(); };
    $("#z-in").onclick = () => setZoom(ZOOM * 1.15); $("#z-out").onclick = () => setZoom(ZOOM / 1.15);
    $("#z-100").onclick = () => setZoom(1); $("#z-fit").onclick = () => { USER_ZOOM = false; draw(); };
    $("#mode-all").onclick = () => { MODE = "all"; (function w(ns) { for (const n of ns) { n.open = true; w(n.children); } })(ROOTS); draw(); };
    $("#mode-focus").onclick = () => { MODE = "focus"; applyFocus(); if (SEL) SEL.open = true; draw(); };
    $("#outer").addEventListener("wheel", (e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); setZoom(ZOOM * (e.deltaY < 0 ? 1.08 : 1 / 1.08)); } }, { passive: false });
    window.addEventListener("resize", draw);
    $("#save").onclick = async () => { const t = $("#cap").value.trim(); if (!t) return; await api("/api/ideas", { text: t }); toast("已记下"); pages.ideas(); };
    if (focusOn()) applyFocus();
    draw();
  };

  pages.idea = async (slug) => {
    const d = await api(`/api/ideas/${slug}`); const m = d.meta;
    main.innerHTML = `<p><a href="#/ideas">← 问题树</a></p><h1>${esc(d.title)}</h1>
      <div class="meta">${kindChip(m.kind)}${chip(m.status)}${m.parent ? `<a href="#/ideas/${esc(m.parent)}">上级：${esc(m.parent)}</a>` : ""}${(m.labs || []).map((l) => `<a href="#/labs/${esc(l)}">lab ${esc(l)}</a>`).join("")}${(m.related || []).map((r) => `<a href="#/ideas/${esc(r)}">相关：${esc(r)}</a>`).join("")}<span>创建：${esc(m.created || "")}</span></div>
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
    const hash = location.hash.replace(/^#\/?/, "");
    if (hash.startsWith("doc/")) {
      // 通用文档页：#/doc/<项目内路径>?h=<节锚点>
      const [p, qs] = hash.slice(4).split("?");
      const path = p.split("/").map((x) => { try { return decodeURIComponent(x); } catch (e) { return x; } }).join("/");
      const params = new URLSearchParams(qs || ""); const frag = params.get("h"); const base = params.get("base");
      const top = { labs: "labs", wiki: "wiki", ideas: "ideas", discussion: "discussion", references: "refs" }[path.split("/")[0]] || "home";
      document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.key === top));
      try { await pages.doc(path, frag, base); } catch (e) { main.innerHTML = `<p class="muted">出错了：${esc(e.message)}</p>`; }
      window.scrollTo(0, 0);
      return;
    }
    const parts = hash.split("/");
    const key = parts[0] || "home"; const rest = parts.slice(1).join("/");
    document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.key === key || (key === "inbox" && a.dataset.key === "refs")));
    main.classList.toggle("full", key === "ideas" && !rest);  // 想法页的卡片图用全宽
    const fn = pages[key] || pages.home;
    try { await fn(rest ? decodeURIComponent(rest) : undefined); } catch (e) { main.innerHTML = `<p class="muted">出错了：${esc(e.message)}</p>`; }
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  refreshOverview().then(route);
  setInterval(refreshOverview, 30000);
})();
