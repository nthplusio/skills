/* Business-rules explorer. Vanilla ES2020, no build step. */
(function () {
  "use strict";

  const D = window.BR_DATA || {};
  const META = D.meta || { counts: {} };
  const STAGES = D.stages || [];
  const FLAG_TYPES = D.flagTypes || [];
  const GLOSSARY = D.glossary || {};
  const PACKAGES = D.packages || [];
  const MODULES = (D.modules || []).filter(Boolean);
  const SURFACES = D.surfaces || [];
  const FILES = D.files || [];
  const RULES = (D.rules || []).filter(Boolean);

  // Lifecycle map layout comes from each stage's `lane` in scope.json: main row, side lane, or band.
  const laneOf = (s) => s.lane || "main";
  const MAP_ORDER = STAGES.filter((s) => laneOf(s) === "main").map((s) => s.id);
  const SIDE_STAGES = STAGES.filter((s) => laneOf(s) === "side");
  const BAND_STAGES = STAGES.filter((s) => laneOf(s) === "band");
  const VERDICTS = ["correct", "wrong", "unsure"];
  const VERDICT_LABEL = { correct: "Correct", wrong: "Wrong", unsure: "Unsure", unreviewed: "Unreviewed" };
  const SURFACE_KINDS = (D.surfaceKinds || [{ id: "internal", label: "Internal", icon: "•" }])
    .map((k) => [k.id, k.label, k.icon || "•"]);
  const PROJECT = META.project || { name: "", slug: "project" };
  const LINKS = META.links || null; // {file, line, commit} URL templates; null when the host is unknown
  // Rule IDs are stable for one commit only, so stored reviews are keyed by it.
  const COMMIT_SHORT = String(META.commit || "").slice(0, 9);
  const KEY_REVIEWS = `br:${PROJECT.slug}:reviews:${COMMIT_SHORT}`;
  const KEY_REVIEWER = "br:reviewer";
  const KEY_MAP = "br:map-hidden";

  // ---------- lookups ----------
  const byId = (list) => new Map(list.map((x) => [x.id, x]));
  const ruleById = byId(RULES);
  const moduleById = byId(MODULES);
  const pkgById = byId(PACKAGES);
  const stageById = byId(STAGES);
  const flagById = byId(FLAG_TYPES);

  // ---------- escaping: the only place data becomes HTML ----------
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  /** Escaped text with `backticked` spans rendered as code chips. */
  function rich(text) {
    return String(text == null ? "" : text).split("`")
      .map((part, i) => (i % 2 ? `<code>${esc(part)}</code>` : esc(part))).join("");
  }
  const $ = (sel) => document.querySelector(sel);

  // ---------- storage ----------
  function loadJSON(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (e) { return fallback; }
  }
  let reviews = loadJSON(KEY_REVIEWS, {});
  let reviewer = localStorage.getItem(KEY_REVIEWER) || "";
  const saveReviews = () => localStorage.setItem(KEY_REVIEWS, JSON.stringify(reviews));
  const statusOf = (ruleId) => (reviews[ruleId] && reviews[ruleId].verdict) || "unreviewed";

  // ---------- state ----------
  const state = {
    filters: { q: "", stage: "", status: "", flag: "", inferred: false },
    sel: null,               // {type: "package"|"module"|"rule", id}
    userOpen: new Set(),     // tree-walk state chosen by the user
    filterOpen: new Set(),   // tree-walk state while a filter is active
    focus: null,             // node id with keyboard focus
    pendingVerdict: null,
  };

  // ---------- tree model ----------
  function buildTree() {
    const groups = [
      { id: "g:business", label: "Business logic", tier: "business" },
      { id: "g:platform", label: "Platform (summary)", tier: "platform" },
    ];
    return groups.map((g) => ({
      id: g.id, type: "group", label: g.label,
      children: PACKAGES.filter((p) => p.tier === g.tier).map(buildPackageNode),
    }));
  }
  function buildPackageNode(pkg) {
    const mods = (pkg.modules || []).map((id) => moduleById.get(id)).filter(Boolean);
    const loose = mods.filter((m) => !m.folder).map(buildModuleNode);
    const folders = [];
    mods.filter((m) => m.folder).forEach((m) => {
      let f = folders.find((x) => x.folder === m.folder);
      if (!f) { f = { id: `f:${pkg.id}/${m.folder}`, type: "folder", folder: m.folder, label: m.folder, children: [] }; folders.push(f); }
      f.children.push(buildModuleNode(m));
    });
    return { id: `p:${pkg.id}`, type: "package", ref: pkg, children: loose.concat(folders) };
  }
  function buildModuleNode(mod) {
    const children = (mod.rules || []).filter((id) => ruleById.has(id))
      .map((id) => ({ id: `r:${id}`, type: "rule", ref: ruleById.get(id), children: [] }));
    return { id: `m:${mod.id}`, type: "module", ref: mod, children };
  }
  const TREE = buildTree();
  const nodeIndex = new Map();
  const parentOf = new Map();
  (function index(nodes, parent) {
    nodes.forEach((n) => {
      nodeIndex.set(n.id, n);
      if (parent) parentOf.set(n.id, parent.id);
      n.ruleIds = n.type === "rule" ? [n.ref.id] : [];
      index(n.children, n);
      n.children.forEach((c) => n.ruleIds.push(...c.ruleIds));
    });
  })(TREE, null);
  const TREE_RULE_ORDER = TREE.flatMap((g) => g.ruleIds);

  // ---------- filters ----------
  function filtersActive() {
    const f = state.filters;
    return !!(f.q || f.stage || f.status || f.flag || f.inferred);
  }
  function searchText(rule) {
    if (!rule._search) {
      const mod = moduleById.get(rule.m) || {};
      const pkg = pkgById.get(mod.package) || {};
      rule._search = [rule.id, rule.t, rule.s, rule.aw, rule.eg, mod.title, mod.path, pkg.title, pkg.id, pkg.code]
        .join("\n").toLowerCase();
    }
    return rule._search;
  }
  function ruleMatches(rule) {
    const f = state.filters;
    if (f.stage && rule.st !== f.stage) return false;
    if (f.status && statusOf(rule.id) !== f.status) return false;
    if (f.flag === "any" && !(rule.fl || []).length) return false;
    if (f.flag && f.flag !== "any" && !(rule.fl || []).some((x) => x[0] === f.flag)) return false;
    if (f.inferred && rule.c !== "medium") return false;
    if (f.q && !searchText(rule).includes(f.q.toLowerCase())) return false;
    return true;
  }
  let matchSet = new Set(RULES.map((r) => r.id));
  function recomputeMatches() {
    matchSet = new Set(RULES.filter(ruleMatches).map((r) => r.id));
    state.filterOpen = new Set();
    if (filtersActive()) {
      nodeIndex.forEach((n) => {
        if (n.type !== "rule" && n.ruleIds.some((id) => matchSet.has(id))) state.filterOpen.add(n.id);
      });
    }
  }
  const orderedMatches = () => TREE_RULE_ORDER.filter((id) => matchSet.has(id));
  const openSet = () => (filtersActive() ? state.filterOpen : state.userOpen);
  function nodeVisible(n) {
    if (!filtersActive()) return true;
    return n.ruleIds.some((id) => matchSet.has(id));
  }

  // ---------- small view helpers ----------
  function countFlagged(ruleIds) {
    return ruleIds.filter((id) => (ruleById.get(id).fl || []).length).length;
  }
  function progressBar(ruleIds, cls) {
    const done = ruleIds.filter((id) => statusOf(id) !== "unreviewed").length;
    const pct = ruleIds.length ? Math.round((done / ruleIds.length) * 100) : 0;
    return `<span class="bar ${cls || ""}" title="${done} of ${ruleIds.length} reviewed"><span style="width:${pct}%"></span></span>`;
  }
  const dot = (ruleId) => `<span class="dot dot-${statusOf(ruleId)}" title="${esc(VERDICT_LABEL[statusOf(ruleId)])}"></span>`;
  // Stage colours come from a fixed palette by position, so any repository's stages get distinct colours.
  const stageClass = (stageId) => {
    const i = STAGES.findIndex((s) => s.id === stageId);
    return isBand(stageId) ? "sc-band" : `sc-${(i < 0 ? 0 : i) % 10}`;
  };
  const isBand = (stageId) => (stageById.get(stageId) || {}).lane === "band";
  function stagePill(stageId) {
    const s = stageById.get(stageId);
    return `<span class="pill ${stageClass(stageId)}" title="${esc(s ? s.description : "")}">${esc(s ? s.label : stageId)}</span>`;
  }
  function flagBadges(rule) {
    return (rule.fl || []).map((f) => {
      const t = flagById.get(f[0]);
      return `<span class="flagbadge flag-${esc(f[0])}" title="${esc(t ? t.description : "")}">⚑ ${esc(t ? t.label : f[0])}</span>`;
    }).join("");
  }
  function link(attrs, label) {
    return `<a href="#" ${attrs}>${label}</a>`;
  }
  /** A link to `path` at the catalogue's commit, or null when the code host is unknown. */
  function repoLink(path, lines) {
    if (!LINKS || !LINKS.file) return null;
    const fill = (tpl, vars) => tpl.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : ""));
    const m = /^(\d+)(?:\s*-\s*(\d+))?/.exec(String(lines || "").trim());
    const anchor = m && LINKS.line ? fill(LINKS.line, { start: m[1], end: m[2] || m[1] }) : "";
    return fill(LINKS.file, { commit: META.commit, path }) + anchor;
  }
  function codeRef(path, lines, label) {
    const href = repoLink(path, lines);
    return href ? `<a href="${esc(href)}" target="_blank" rel="noopener" class="mono">${esc(label)}</a>` : `<span class="mono">${esc(label)}</span>`;
  }
  function evidenceLink(ev) {
    const i = ev.lastIndexOf(":");
    const hasLine = i > 0 && /^\d/.test(ev.slice(i + 1));
    return hasLine ? codeRef(ev.slice(0, i), ev.slice(i + 1), ev) : codeRef(ev, "", ev);
  }
  function commitRef() {
    const short = esc(String(META.commit || "").slice(0, 10));
    if (!LINKS || !LINKS.commit) return `<span class="mono">${short}</span>`;
    return `<a href="${esc(LINKS.commit.replace("{commit}", META.commit))}" target="_blank" rel="noopener" class="mono">${short}</a>`;
  }

  // ---------- header ----------
  function renderHeader() {
    const total = RULES.length;
    const done = RULES.filter((r) => statusOf(r.id) !== "unreviewed").length;
    $("#totals").textContent = `${plural(total, "rule")} · ${plural(META.counts.flags || 0, "flag")}`;
    $("#progressLabel").textContent = `Reviewed ${done}/${total}`;
    $("#progressBar").style.width = `${total ? (done / total) * 100 : 0}%`;
  }
  function renderBanner() {
    const loaded = D.loaded || [];
    const expected = D.expected || 0;
    if (loaded.length >= expected) return;
    const missing = [];
    for (let i = 1; i <= expected; i++) if (!loaded.includes(i)) missing.push(i);
    const b = $("#banner");
    b.hidden = false;
    b.textContent = `Some rule data did not load (chunks ${missing.join(", ")} missing). Counts below are incomplete.`;
  }

  // ---------- lifecycle map ----------
  function stageBox(stageId, extraClass) {
    const s = stageById.get(stageId);
    if (!s) return "";
    const ids = RULES.filter((r) => r.st === stageId).map((r) => r.id);
    const active = state.filters.stage === stageId ? " active" : "";
    const loop = s.loop ? `<span class="loop" title="${esc(s.loop.title || "")}">⟲ ${esc(s.loop.label)}</span>` : "";
    const note = s.note;
    const entries = s.entries || [];
    const title = s.description + (entries.length ? `\nEntry points: ${entries.join(" · ")}` : "");
    const dags = entries.length ? `<div class="dags" title="Entry points">${entries.map(esc).join("<br>")}</div>` : "";
    return `<div class="stagecell ${extraClass || ""}"><button type="button" class="stagebox ${stageClass(stageId)}${active}" data-stage="${esc(stageId)}" title="${esc(title)}" aria-pressed="${!!active}">
      <span class="stagelabel">${esc(s.label)}</span>
      <span class="stagecounts">${plural(ids.length, "rule")} · ⚑${countFlagged(ids)}</span>
      ${progressBar(ids)}${loop}${note ? `<span class="lanenote">${esc(note)}</span>` : ""}</button>${extraClass ? "" : dags}</div>`;
  }
  function renderMap() {
    const main = MAP_ORDER.map((id, i) => (i ? `<div class="arrow" aria-hidden="true">→</div>` : "") + stageBox(id)).join("");
    const lanes = SIDE_STAGES.map((s) => {
      const from = Math.max(0, MAP_ORDER.indexOf(s.laneFrom));
      return `<div class="lane" style="margin-left: calc(${from} * (100% / ${MAP_ORDER.length || 1}))">${stageBox(s.id, "lanebox")}</div>`;
    }).join("");
    const bands = BAND_STAGES.map((s) => `<div class="band">${stageBox(s.id, "bandbox")}</div>`).join("");
    $("#map").innerHTML = `<div class="mapgrid">
      <div class="maprow">${main}</div>${lanes}${bands}
    </div>`;
  }
  function applyMapHidden(hidden) {
    $("#map").hidden = hidden;
    $("#mapContainer").classList.toggle("docked", hidden);
    $("#mapToggle").setAttribute("aria-expanded", String(!hidden));
    $("#mapToggleText").textContent = hidden ? "Show" : "Hide";
    localStorage.setItem(KEY_MAP, hidden ? "1" : "0");
  }

  // ---------- tree ----------
  function nodeLabel(n) {
    if (n.type === "group") return `<span class="nm group">${esc(n.label)}</span>`;
    if (n.type === "package") return `<span class="nm">${esc(n.ref.title)}</span> <span class="code">${esc(n.ref.code)}</span>`;
    if (n.type === "folder") return `<span class="nm mono">${esc(n.label)}/</span>`;
    if (n.type === "module") return `<span class="nm">${esc(n.ref.title)}</span> <span class="muted">· ${esc(n.ref.name)}</span>`;
    const r = n.ref;
    return `<span class="rid mono">${esc(r.id)}</span> <span class="nm">${esc(String(r.t).replace(/`/g, ""))}</span>`;
  }
  function nodeBadges(n) {
    if (n.type === "rule") {
      const r = n.ref;
      return dot(r.id) + ((r.fl || []).length ? `<span class="flagmark" title="Flagged">⚑</span>` : "") +
        (r.c === "medium" ? `<span class="inferred">inferred</span>` : "");
    }
    if (n.type === "module" && !n.ruleIds.length) return `<span class="muted small">no rules</span>`;
    const ids = filtersActive() ? n.ruleIds.filter((id) => matchSet.has(id)) : n.ruleIds;
    const flagged = countFlagged(ids);
    const cnt = filtersActive() ? `<span class="cnt" title="${ids.length} of ${n.ruleIds.length} rules match the filters">${ids.length}/${n.ruleIds.length}</span>` : `<span class="cnt">${ids.length}</span>`;
    return cnt + (flagged ? `<span class="flagcnt">⚑${flagged}</span>` : "") + progressBar(ids, "thin");
  }
  function isSelected(n) {
    const s = state.sel;
    if (!s) return false;
    return (n.type === "rule" && s.type === "rule" && s.id === n.ref.id) ||
      (n.type === "module" && s.type === "module" && s.id === n.ref.id) ||
      (n.type === "package" && s.type === "package" && s.id === n.ref.id);
  }
  function renderNode(n, depth, out) {
    if (!nodeVisible(n)) return;
    const hasKids = n.children.some(nodeVisible) || (n.children.length && !filtersActive());
    const open = hasKids && openSet().has(n.id);
    const glyph = hasKids ? `<span class="glyph" aria-hidden="true">${open ? "⊟" : "⊞"}</span>` : `<span class="glyph-space"></span>`;
    const cls = ["node", `node-${n.type}`, isSelected(n) ? "selected" : "", state.focus === n.id ? "focused" : ""].join(" ");
    out.push(`<div class="${cls}" role="treeitem" id="tn-${esc(cssId(n.id))}" data-node="${esc(n.id)}" aria-level="${depth + 1}"` +
      (hasKids ? ` aria-expanded="${open}"` : "") + ` aria-selected="${isSelected(n)}" style="padding-left:${depth * 16 + 6}px">` +
      `${glyph}<span class="label">${nodeLabel(n)}</span><span class="badges">${nodeBadges(n)}</span></div>`);
    if (open) n.children.forEach((c) => renderNode(c, depth + 1, out));
  }
  const cssId = (id) => id.replace(/[^A-Za-z0-9_-]/g, "_");
  function renderTree() {
    const out = [];
    TREE.forEach((g) => renderNode(g, 0, out));
    $("#tree").innerHTML = out.join("") || `<p class="muted pad">No rules match these filters.</p>`;
    if (state.focus) $("#tree").setAttribute("aria-activedescendant", `tn-${cssId(state.focus)}`);
    $("#count").textContent = `${matchSet.size} of ${RULES.length} rules`;
  }
  const visibleNodeIds = () => Array.from($("#tree").querySelectorAll("[data-node]")).map((el) => el.dataset.node);
  function treeWalk(nodeId, forceOpen) {
    const set = openSet();
    const open = forceOpen === undefined ? !set.has(nodeId) : forceOpen;
    if (open) set.add(nodeId); else set.delete(nodeId);
  }
  function selectNode(n) {
    if (n.type === "package") select({ type: "package", id: n.ref.id });
    else if (n.type === "module") select({ type: "module", id: n.ref.id });
    else if (n.type === "rule") select({ type: "rule", id: n.ref.id });
  }
  function onTreeClick(e) {
    const el = e.target.closest("[data-node]");
    if (!el) return;
    const n = nodeIndex.get(el.dataset.node);
    state.focus = n.id;
    if (n.children.length) treeWalk(n.id);
    if (n.type === "group" || n.type === "folder") { renderTree(); return; }
    selectNode(n);
  }
  function onTreeKey(e) {
    const ids = visibleNodeIds();
    if (!ids.length) return;
    let i = ids.indexOf(state.focus);
    const n = nodeIndex.get(state.focus);
    const handled = { ArrowDown: 1, ArrowUp: 1, ArrowRight: 1, ArrowLeft: 1, Enter: 1 };
    if (!handled[e.key]) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "ArrowDown") state.focus = ids[Math.min(ids.length - 1, i + 1)];
    else if (e.key === "ArrowUp") state.focus = ids[Math.max(0, i - 1)];
    else if (e.key === "ArrowRight" && n && n.children.length) treeWalk(n.id, true);
    else if (e.key === "ArrowLeft" && n) {
      if (openSet().has(n.id)) treeWalk(n.id, false); else if (parentOf.has(n.id)) state.focus = parentOf.get(n.id);
    } else if (e.key === "Enter" && n) { selectNode(n); return; }
    if (i < 0 && !state.focus) state.focus = ids[0];
    renderTree();
    const el = document.getElementById(`tn-${cssId(state.focus)}`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }
  /** Open every ancestor of a node in the user's tree-walk state so the selection is visible. */
  function revealNode(nodeId) {
    let p = parentOf.get(nodeId);
    while (p) { state.userOpen.add(p); state.filterOpen.add(p); p = parentOf.get(p); }
  }

  // ---------- detail: home ----------
  function renderHome() {
    const flagCounts = FLAG_TYPES.map((t) => ({ t, n: RULES.filter((r) => (r.fl || []).some((f) => f[0] === t.id)).length }));
    const verdictCounts = ["unreviewed"].concat(VERDICTS).map((v) => `<li>${dotFor(v)} ${esc(VERDICT_LABEL[v])}: <b>${RULES.filter((r) => statusOf(r.id) === v).length}</b></li>`).join("");
    const byStage = STAGES.map((s) => `<li>${link(`data-stage-filter="${esc(s.id)}"`, stagePill(s.id))} ${RULES.filter((r) => r.st === s.id).length}</li>`).join("");
    const c = META.counts || {};
    return `<div class="prose">
      <h2>${esc(META.title || "Business rules")}</h2>
      <div class="note"><b>How to review</b>
        <ol><li>Walk the tree on the left, or click a stage in the lifecycle map.</li>
        <li>Read each rule and mark it Correct, Wrong or Unsure; write what the rule should be.</li>
        <li>Export your review (CSV, Markdown or JSON) and send the file to engineering.</li></ol></div>
      <div class="stats">
        <div><b>${RULES.length}</b> rules</div><div><b>${MODULES.length}</b> modules</div>
        <div><b>${PACKAGES.length}</b> areas</div><div><b>${c.flags || 0}</b> flags</div></div>
      ${accuracyNote()}
      <h3>Flags by type</h3>
      <div class="flagchips">${flagCounts.map(({ t, n }) => `<button type="button" class="flagchip flag-${esc(t.id)}" data-flag-filter="${esc(t.id)}"><b>⚑ ${esc(t.label)} · ${n}</b><span>${esc(t.description)}</span></button>`).join("")}</div>
      <h3>Rules by stage</h3><ul class="plain cols">${byStage}</ul>
      <h3>Your review progress</h3><ul class="plain">${verdictCounts}</ul>
      <p class="footnote">Generated ${esc(META.generated)} from commit ${commitRef()}.
        The rules were derived from what the code enforces, not from comments or documentation.</p>
    </div>`;
  }
  const dotFor = (v) => `<span class="dot dot-${v}"></span>`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  function accuracyNote() {
    const v = META.verification || {};
    if (!v.rules_checked) return "";
    return `<div class="note accuracy"><b>How far to trust a rule</b>
      <p>Every rule was read from the code that enforces it. A second reader then re-checked ${plural(v.rules_checked, "rule")}
      against the code: ${v.rules_correct} correct as written, ${v.rules_revised} needing a correction and
      ${v.rules_removed} wrong. Of ${plural(v.flags_checked, "flag")} re-checked, ${v.flags_confirmed} held,
      ${v.flags_revised} were reworded and ${v.flags_removed} were removed.</p>
      <p>In the re-checked set, ${Math.round((100 * v.rules_revised) / v.rules_checked)}% of rules needed a correction;
      expect a similar share among the rest. Finding those is what this review is for. Rules marked <span class="pill okpill">Second read ✓</span> have been re-checked.
      <span class="pill inferredpill">Inferred</span> means the reader had to infer the rule across calls they did
      not fully trace.</p></div>`;
  }

  // ---------- detail: package ----------
  function renderPackage(pkg) {
    const node = nodeIndex.get(`p:${pkg.id}`);
    const ids = node ? node.ruleIds : [];
    const flags = FLAG_TYPES.map((t) => [t, ids.filter((id) => (ruleById.get(id).fl || []).some((f) => f[0] === t.id)).length])
      .filter(([, n]) => n).map(([t, n]) => `<span class="flagbadge flag-${esc(t.id)}" title="${esc(t.description)}">⚑ ${esc(t.label)} ${n}</span>`).join("") || `<span class="muted">No flags</span>`;
    const done = ids.filter((id) => statusOf(id) !== "unreviewed").length;
    const mods = (pkg.modules || []).map((id) => moduleById.get(id)).filter(Boolean).map((m) => {
      const rids = (m.rules || []).filter((id) => ruleById.has(id));
      return `<li>${link(`data-module="${esc(m.id)}"`, `<b>${esc(m.title)}</b>`)} <span class="muted mono">${esc(m.path)}</span> ${stagePill(m.stage)}
        <span class="cnt">${rids.length ? `${rids.length} rules` : "no rules"}</span>${countFlagged(rids) ? `<span class="flagcnt">⚑${countFlagged(rids)}</span>` : ""}</li>`;
    }).join("");
    return `<div class="prose">
      <h2>${esc(pkg.title)} <span class="code">${esc(pkg.code)}</span></h2>
      <p><span class="pill">${esc(pkg.tier === "business" ? "Business logic" : "Platform")}</span></p>
      <p>${rich(pkg.summary)}</p>
      <div class="stats"><div><b>${ids.length}</b> rules</div><div><b>${done}</b> of ${ids.length} reviewed ${progressBar(ids)}</div></div>
      <div class="flagrow">${flags}</div>
      <h3>Modules</h3><ul class="modlist">${mods}</ul></div>`;
  }

  // ---------- detail: module ----------
  function ruleCard(rule) {
    return `<button type="button" class="rulecard" data-rule="${esc(rule.id)}">
      <span class="cardhead">${dot(rule.id)}<span class="rid mono">${esc(rule.id)}</span> <b>${rich(rule.t)}</b></span>
      <span class="preview">${rich(rule.s)}</span><span class="flagrow">${flagBadges(rule)}</span></button>`;
  }
  function rulesRunHere(mod) {
    return RULES.filter((r) => r.m !== mod.id && (r.en || []).some((e) =>
      (e[0] === "executes" || e[0] === "calls") && String(FILES[e[1]] || "").endsWith(mod.path)));
  }
  function renderModule(mod) {
    const own = (mod.rules || []).map((id) => ruleById.get(id)).filter(Boolean);
    const elsewhere = rulesRunHere(mod);
    const pkg = pkgById.get(mod.package);
    return `<div class="prose">
      <p class="crumbs">${pkg ? link(`data-package="${esc(pkg.id)}"`, esc(pkg.title)) : ""}${mod.folder ? ` › ${esc(mod.folder)}` : ""}</p>
      <h2>${esc(mod.title)}</h2>
      <p><span class="mono muted">${esc(mod.path)}</span> ${stagePill(mod.stage)}</p>
      <p>${rich(mod.summary)}</p>
      <h3>Rules decided here</h3>
      ${own.length ? `<div class="cards">${own.map(ruleCard).join("")}</div>` : `<p class="muted">No rules: this module decides nothing. If you think it should, mark that in your notes to engineering.</p>`}
      ${elsewhere.length ? `<h3>Also runs rules decided elsewhere</h3><div class="cards">${elsewhere.map(ruleCard).join("")}</div>` : ""}
    </div>`;
  }

  // ---------- detail: rule ----------
  function ruleHeader(rule, mod, pkg) {
    const crumbs = [pkg ? link(`data-package="${esc(pkg.id)}"`, esc(pkg.title)) : "",
      mod && mod.folder ? link(`data-node-open="${esc(`f:${pkg.id}/${mod.folder}`)}"`, esc(mod.folder)) : "",
      mod ? link(`data-module="${esc(mod.id)}"`, esc(mod.title)) : ""].filter(Boolean).join(" › ");
    return `<p class="crumbs">${crumbs}</p>
      <div class="idline"><span class="rid mono big">${esc(rule.id)}</span>
        <button type="button" class="small" data-copy="${esc(rule.id)}">Copy ID</button></div>
      <h2>${rich(rule.t)}</h2>
      <p class="pills">${stagePill(rule.st)}<span class="pill">${esc(rule.k)}</span>
        ${rule.c === "medium" ? `<span class="pill inferredpill" title="Inferred: the code implies this rule rather than stating it directly">Inferred</span>` : ""}
        ${rule.v ? `<span class="pill okpill" title="Checked by a second reader">Second read ✓</span>` : ""}</p>`;
  }
  function ruleFlags(rule) {
    return (rule.fl || []).map((f) => {
      const t = flagById.get(f[0]) || { label: f[0], description: "" };
      const ev = (f[2] || []).map(evidenceLink).join(" ");
      return `<div class="callout flag-${esc(f[0])}"><b title="${esc(t.description)}">⚑ ${esc(t.label)}</b>
        ${f[3] ? `<span class="pill okpill">verified</span>` : ""}<div>${rich(f[1])}</div>${ev ? `<div class="evidence">${ev}</div>` : ""}</div>`;
    }).join("");
  }
  function ruleSurfaces(rule) {
    const items = (rule.su || []).map((i) => SURFACES[i]).filter(Boolean);
    if (!items.length) return `<p class="muted">Not visible on any surface.</p>`;
    return SURFACE_KINDS.map(([kind, label, icon]) => {
      const group = items.filter((s) => s[0] === kind);
      if (!group.length) return "";
      return `<div class="surfgroup"><div class="surfkind"><span class="icon mono">${esc(icon)}</span> ${esc(label)}</div>
        <ul class="plain">${group.map((s) => `<li>${rich(s[1])}${s[2] ? ` <span class="mono muted small">${esc(s[2])}</span>` : ""}</li>`).join("")}</ul></div>`;
    }).join("");
  }
  function ruleTerms(rule) {
    if (!(rule.tm || []).length) return "";
    return `<h3>Terms</h3><div class="terms">${rule.tm.map((t) => `<button type="button" class="termchip" data-term="${esc(t)}" aria-expanded="false">${esc(t)}</button>`).join("")}</div><div id="termdef"></div>`;
  }
  function ruleRelated(rule) {
    const rel = (rule.re || []).map((id) => ruleById.get(id)).filter(Boolean);
    if (!rel.length) return "";
    return `<h3>Related rules</h3><ul class="plain">${rel.map((r) => `<li>${link(`data-rule="${esc(r.id)}"`, `<span class="mono">${esc(r.id)}</span> ${rich(r.t)}`)}</li>`).join("")}</ul>`;
  }
  function ruleEngineering(rule) {
    const rows = (rule.en || []).map(([role, fi, symbol, lines]) => {
      const path = FILES[fi] || "";
      return `<tr><td>${esc(role)}</td><td>${codeRef(path, lines, path)}</td>
        <td class="mono">${esc(symbol)}</td><td class="mono">${esc(lines)}</td></tr>`;
    }).join("");
    return `<details class="eng"><summary>Engineering</summary>
      <table><thead><tr><th>Role</th><th>File</th><th>Symbol</th><th>Lines</th></tr></thead><tbody>${rows}</tbody></table></details>`;
  }
  function reviewPanel(rule) {
    const r = reviews[rule.id] || {};
    const btns = VERDICTS.map((v, i) => `<button type="button" class="verdict v-${v}${r.verdict === v ? " on" : ""}" data-verdict="${v}" aria-pressed="${r.verdict === v}" title="Shortcut ${i + 1}">${esc(VERDICT_LABEL[v])}</button>`).join("");
    return `<div class="review" id="review">
      <div class="verdicts"><span class="reviewlabel">Your verdict</span>${btns}<span id="saved" class="muted small">${savedText(r)}</span>
        <span class="navs"><button type="button" data-nav="prev" title="Previous rule (k)">‹ Prev</button><button type="button" data-nav="next" title="Next rule (j)">Next ›</button><button type="button" data-nav="unreviewed">Next unreviewed</button></span></div>
      <div id="namePrompt" class="nameprompt" hidden><label>Before saving, enter your name <input id="namePromptInput" type="text"></label> <button type="button" id="namePromptSave">Save name</button></div>
    </div>`;
  }
  function reviewNote(rule) {
    const r = reviews[rule.id] || {};
    return `<div class="notebox"><label class="notelabel" for="note">Your correction: what should this rule be? Notes for engineering</label>
      <textarea id="note" rows="3" placeholder="Leave empty if the rule is correct as written">${esc(r.note || "")}</textarea></div>`;
  }
  function savedText(r) {
    if (!r || !r.at) return "Not reviewed yet";
    return `Saved · ${new Date(r.at).toLocaleTimeString()} · ${esc(r.reviewer || "anonymous")}`;
  }
  function renderRule(rule) {
    const mod = moduleById.get(rule.m);
    const pkg = mod && pkgById.get(mod.package);
    const ex = (rule.ex || []).length ? `<ul>${rule.ex.map((x) => `<li>${rich(x)}</li>`).join("")}</ul>` : `<p class="muted">None</p>`;
    return `<article class="prose rule">
      ${ruleHeader(rule, mod, pkg)}
      ${ruleFlags(rule)}
      <h3>The rule</h3><p class="statement">${rich(rule.s)}</p>
      <h3>Applies when</h3><p>${rich(rule.aw)}</p>
      <h3>Exceptions</h3>${ex}
      ${rule.eg ? `<h3>Example</h3><div class="example">${rich(rule.eg)}</div>` : ""}
      ${rule.ov ? `<h3>If violated</h3><p>${rich(rule.ov)}</p>` : ""}
      ${reviewNote(rule)}
      <h3>Where you see this</h3>${ruleSurfaces(rule)}
      ${ruleTerms(rule)}
      ${ruleRelated(rule)}
      ${ruleEngineering(rule)}
    </article>${reviewPanel(rule)}`;
  }

  // ---------- detail dispatch ----------
  function renderDetail() {
    const s = state.sel;
    let html = renderHome();
    if (s && s.type === "rule" && ruleById.has(s.id)) html = renderRule(ruleById.get(s.id));
    else if (s && s.type === "module" && moduleById.has(s.id)) html = renderModule(moduleById.get(s.id));
    else if (s && s.type === "package" && pkgById.has(s.id)) html = renderPackage(pkgById.get(s.id));
    $("#detail").innerHTML = html;
  }
  function select(sel, opts) {
    state.sel = sel;
    if (sel) {
      const nodeId = { rule: "r:", module: "m:", package: "p:" }[sel.type] + sel.id;
      revealNode(nodeId);
      state.focus = nodeId;
    }
    renderDetail();
    renderTree();
    writeHash();
    if (!(opts && opts.keepScroll)) $("#detail").scrollTop = 0;
    const el = state.focus && document.getElementById(`tn-${cssId(state.focus)}`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }

  // ---------- reviews ----------
  function setVerdict(verdict) {
    if (!state.sel || state.sel.type !== "rule") return;
    if (!reviewer) {
      state.pendingVerdict = verdict;
      $("#namePrompt").hidden = false;
      $("#namePromptInput").focus();
      return;
    }
    const id = state.sel.id;
    const prev = reviews[id] || {};
    reviews[id] = { verdict: prev.verdict === verdict ? "" : verdict, note: prev.note || "", reviewer, at: new Date().toISOString() };
    if (!reviews[id].verdict && !reviews[id].note) delete reviews[id];
    afterReviewChange(id);
    const note = $("#note");
    if (note && reviews[id] && (reviews[id].verdict === "wrong" || reviews[id].verdict === "unsure") && !note.value) {
      note.scrollIntoView({ block: "center", behavior: "smooth" });
      note.focus({ preventScroll: true });
    }
  }
  function setNote(note) {
    const id = state.sel.id;
    const prev = reviews[id] || { verdict: "" };
    reviews[id] = { verdict: prev.verdict || "", note, reviewer: reviewer || prev.reviewer || "", at: new Date().toISOString() };
    afterReviewChange(id, true);
  }
  function afterReviewChange(id, quiet) {
    saveReviews();
    renderHeader();
    renderMap();
    if (state.filters.status) recomputeMatches();
    renderTree();
    if (quiet) { $("#saved").innerHTML = savedText(reviews[id]); return; }
    document.querySelectorAll("[data-verdict]").forEach((b) => {
      const on = reviews[id] && reviews[id].verdict === b.dataset.verdict;
      b.classList.toggle("on", !!on);
      b.setAttribute("aria-pressed", String(!!on));
    });
    $("#saved").innerHTML = savedText(reviews[id]);
  }
  function setReviewer(name) {
    reviewer = name.trim();
    localStorage.setItem(KEY_REVIEWER, reviewer);
    $("#reviewer").value = reviewer;
  }
  function navigate(kind) {
    const order = orderedMatches();
    if (!order.length) return;
    const cur = state.sel && state.sel.type === "rule" ? order.indexOf(state.sel.id) : -1;
    let target;
    if (kind === "next") target = order[Math.min(order.length - 1, cur + 1)];
    else if (kind === "prev") target = order[Math.max(0, cur < 0 ? 0 : cur - 1)];
    else {
      const rotated = order.slice(cur + 1).concat(order.slice(0, cur + 1));
      target = rotated.find((id) => statusOf(id) === "unreviewed");
      if (!target) { toast("Every rule in view is reviewed"); return; }
    }
    select({ type: "rule", id: target });
  }

  // ---------- export / import ----------
  function download(name, text, mime) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: mime }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }
  const today = () => new Date().toISOString().slice(0, 10);
  const fileBase = () => `${PROJECT.slug}-business-rules-review-${(reviewer || "anonymous").replace(/[^A-Za-z0-9_-]+/g, "-")}-${today()}-${COMMIT_SHORT}`;
  const reviewedRules = () => TREE_RULE_ORDER.filter((id) => reviews[id] && (reviews[id].verdict || reviews[id].note)).map((id) => ruleById.get(id));
  const flagText = (rule) => (rule.fl || []).map((f) => `${(flagById.get(f[0]) || { label: f[0] }).label}: ${f[1]}`).join("; ");
  function csvCell(v) {
    const s = String(v == null ? "" : v);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }
  function exportCSV() {
    const head = ["Rule ID", "Area", "Module", "Stage", "Title", "Statement", "Verdict", "Correction note", "Reviewer", "Reviewed at", "Flags"];
    const rows = reviewedRules().map((r) => {
      const m = moduleById.get(r.m) || {};
      const p = pkgById.get(m.package) || {};
      const rv = reviews[r.id];
      return [r.id, p.title, m.path, (stageById.get(r.st) || {}).label, r.t, r.s, VERDICT_LABEL[rv.verdict] || "", rv.note, rv.reviewer, rv.at, flagText(r)];
    });
    const text = "\uFEFF" + [head].concat(rows).map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
    download(`${fileBase()}.csv`, text, "text/csv;charset=utf-8");
  }
  function exportMarkdown() {
    const rules = reviewedRules();
    const count = (v) => rules.filter((r) => reviews[r.id].verdict === v).length;
    const lines = [`# ${META.title || "Business rules"} review`, "",
      `- Reviewer: ${reviewer || "anonymous"}`, `- Date: ${today()}`, `- Commit: ${META.commit}`,
      `- Reviewed: ${rules.length} of ${RULES.length} (Wrong ${count("wrong")}, Unsure ${count("unsure")}, Correct ${count("correct")})`, ""];
    [["wrong", "Wrong"], ["unsure", "Unsure"], ["correct", "Correct"], ["", "Notes without a verdict"]].forEach(([v, label]) => {
      const group = rules.filter((r) => (reviews[r.id].verdict || "") === v);
      if (!group.length) return;
      lines.push(`## ${label}`, "");
      group.forEach((r) => {
        const m = moduleById.get(r.m) || {};
        lines.push(`### ${r.id} ${r.t}`, "", `Module: \`${m.package}/${m.path}\``, "", `> ${String(r.s).replace(/\n/g, "\n> ")}`, "");
        lines.push(`**Reviewer note:** ${reviews[r.id].note || "(none)"}`, "");
        if ((r.fl || []).length) lines.push(`**Flags:** ${flagText(r)}`, "");
      });
    });
    download(`${fileBase()}.md`, lines.join("\n"), "text/markdown;charset=utf-8");
  }
  function exportJSON() {
    const body = { reviewer, exportedAt: new Date().toISOString(), commit: META.commit, reviews };
    download(`${fileBase()}.json`, JSON.stringify(body, null, 2), "application/json");
  }
  function importJSON(file) {
    file.text().then((text) => {
      const parsed = JSON.parse(text);
      if (parsed.commit && META.commit && parsed.commit !== META.commit) {
        toast(`Not imported: that file reviews commit ${String(parsed.commit).slice(0, 9)}, this catalogue is commit ${COMMIT_SHORT}, and rule IDs differ between commits.`);
        return;
      }
      const incoming = parsed.reviews || parsed;
      let n = 0;
      Object.keys(incoming).forEach((id) => {
        const r = incoming[id];
        if (!r || typeof r !== "object") return;
        if (!reviews[id] || String(r.at || "") > String(reviews[id].at || "")) { reviews[id] = r; n++; }
      });
      saveReviews();
      toast(`Imported ${n} review${n === 1 ? "" : "s"}`);
      refreshAll();
    }).catch(() => toast("That file is not a reviews JSON export"));
  }
  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.textContent = ""; }, 4000);
  }

  // ---------- URL hash ----------
  function writeHash() {
    const p = new URLSearchParams();
    const s = state.sel;
    if (s) p.set({ rule: "rule", module: "mod", package: "pkg" }[s.type], s.id);
    const f = state.filters;
    if (f.q) p.set("q", f.q);
    if (f.stage) p.set("stage", f.stage);
    if (f.status) p.set("status", f.status);
    if (f.flag) p.set("flag", f.flag);
    if (f.inferred) p.set("inferred", "1");
    const h = p.toString();
    if (location.hash.slice(1) !== h) history.replaceState(null, "", h ? `#${h}` : location.pathname + location.search);
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.filters = { q: p.get("q") || "", stage: p.get("stage") || "", status: p.get("status") || "",
      flag: p.get("flag") || "", inferred: p.get("inferred") === "1" };
    state.sel = p.get("rule") ? { type: "rule", id: p.get("rule") } : p.get("mod") ? { type: "module", id: p.get("mod") }
      : p.get("pkg") ? { type: "package", id: p.get("pkg") } : null;
  }

  // ---------- filter controls ----------
  function fillSelects() {
    $("#fStage").innerHTML = `<option value="">Any stage</option>` + STAGES.map((s) => `<option value="${esc(s.id)}">${esc(s.label)}</option>`).join("");
    $("#fFlag").innerHTML = `<option value="">All rules</option><option value="any">Flagged only</option>` +
      FLAG_TYPES.map((t) => `<option value="${esc(t.id)}">⚑ ${esc(t.label)}</option>`).join("");
  }
  function syncControls() {
    const f = state.filters;
    $("#search").value = f.q;
    $("#fStage").value = f.stage;
    $("#fStatus").value = f.status;
    $("#fFlag").value = f.flag;
    $("#fInferred").checked = f.inferred;
  }
  function setFilter(patch) {
    Object.assign(state.filters, patch);
    syncControls();
    recomputeMatches();
    renderMap();
    renderTree();
    writeHash();
  }
  function refreshAll() {
    recomputeMatches();
    renderHeader();
    renderMap();
    syncControls();
    renderTree();
    renderDetail();
  }

  // ---------- events ----------
  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }
  const saveNoteDebounced = debounce((v) => setNote(v), 500);
  const isTyping = (el) => el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);

  function onDetailClick(e) {
    const t = e.target.closest("[data-rule],[data-module],[data-package],[data-node-open],[data-copy],[data-term],[data-verdict],[data-nav],[data-flag-filter],[data-stage-filter],#namePromptSave");
    if (!t) return;
    if (t.tagName === "A") e.preventDefault();
    const d = t.dataset;
    if (d.rule) select({ type: "rule", id: d.rule });
    else if (d.module) select({ type: "module", id: d.module });
    else if (d.package) select({ type: "package", id: d.package });
    else if (d.nodeOpen) { revealNode(d.nodeOpen); treeWalk(d.nodeOpen, true); state.focus = d.nodeOpen; renderTree(); }
    else if (d.copy) copyText(d.copy);
    else if (d.term) showTerm(t);
    else if (d.verdict) setVerdict(d.verdict);
    else if (d.nav) navigate(d.nav === "unreviewed" ? "unreviewed" : d.nav);
    else if (d.flagFilter) setFilter({ flag: d.flagFilter });
    else if (d.stageFilter) setFilter({ stage: d.stageFilter });
    else if (t.id === "namePromptSave") saveNameFromPrompt();
  }
  function saveNameFromPrompt() {
    const name = $("#namePromptInput").value.trim();
    if (!name) return;
    setReviewer(name);
    $("#namePrompt").hidden = true;
    if (state.pendingVerdict) { const v = state.pendingVerdict; state.pendingVerdict = null; setVerdict(v); }
  }
  function copyText(text) {
    const done = () => toast(`Copied ${text}`);
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => toast("Copy failed"));
  }
  function showTerm(chip) {
    const box = $("#termdef");
    const open = chip.getAttribute("aria-expanded") === "true";
    document.querySelectorAll("[data-term]").forEach((c) => c.setAttribute("aria-expanded", "false"));
    if (open) { box.innerHTML = ""; return; }
    chip.setAttribute("aria-expanded", "true");
    const term = chip.dataset.term;
    const def = GLOSSARY[term];
    box.innerHTML = `<div class="termbox"><b>${esc(term)}</b>: ${def ? rich(def) : `<span class="muted">No definition in CONTEXT.md.</span>`}</div>`;
  }
  function onGlobalKey(e) {
    if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (state.sel && state.sel.type === "rule" && ["1", "2", "3"].includes(e.key)) { setVerdict(VERDICTS[Number(e.key) - 1]); e.preventDefault(); }
    else if (e.key === "j") navigate("next");
    else if (e.key === "k") navigate("prev");
  }
  function bindEvents() {
    $("#tree").addEventListener("click", onTreeClick);
    $("#tree").addEventListener("keydown", onTreeKey);
    $("#tree").addEventListener("focus", () => { if (!state.focus) { state.focus = visibleNodeIds()[0]; renderTree(); } });
    $("#detail").addEventListener("click", onDetailClick);
    $("#detail").addEventListener("input", (e) => { if (e.target.id === "note") saveNoteDebounced(e.target.value); });
    $("#detail").addEventListener("keydown", (e) => { if (e.target.id === "namePromptInput" && e.key === "Enter") saveNameFromPrompt(); });
    $("#map").addEventListener("click", (e) => {
      const b = e.target.closest("[data-stage]");
      if (b) setFilter({ stage: state.filters.stage === b.dataset.stage ? "" : b.dataset.stage });
    });
    $("#mapToggle").addEventListener("click", () => applyMapHidden(!$("#map").hidden));
    $("#search").addEventListener("input", debounce((e) => setFilter({ q: e.target.value.trim() }), 250));
    $("#fStage").addEventListener("change", (e) => setFilter({ stage: e.target.value }));
    $("#fStatus").addEventListener("change", (e) => setFilter({ status: e.target.value }));
    $("#fFlag").addEventListener("change", (e) => setFilter({ flag: e.target.value }));
    $("#fInferred").addEventListener("change", (e) => setFilter({ inferred: e.target.checked }));
    $("#clearFilters").addEventListener("click", () => setFilter({ q: "", stage: "", status: "", flag: "", inferred: false }));
    $("#reviewer").addEventListener("change", (e) => setReviewer(e.target.value));
    $("#nextUnreviewedTop").addEventListener("click", () => navigate("unreviewed"));
    document.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => {
      ({ csv: exportCSV, md: exportMarkdown, json: exportJSON })[b.dataset.export]();
      $("#exportMenu").open = false;
    }));
    $("#importFile").addEventListener("change", (e) => { if (e.target.files[0]) importJSON(e.target.files[0]); e.target.value = ""; $("#exportMenu").open = false; });
    document.addEventListener("keydown", onGlobalKey);
    window.addEventListener("hashchange", () => { readHash(); refreshAll(); });
  }

  // ---------- boot ----------
  function init() {
    document.title = META.title || "Business rules";
    $("#title").textContent = META.title || "Business rules";
    renderBanner();
    fillSelects();
    $("#reviewer").value = reviewer;
    TREE.forEach((g) => state.userOpen.add(g.id));
    readHash();
    applyMapHidden(localStorage.getItem(KEY_MAP) === "1");
    bindEvents();
    recomputeMatches();
    if (state.sel) select(state.sel); else refreshAll();
    renderHeader();
    renderMap();
    syncControls();
  }
  init();
})();
