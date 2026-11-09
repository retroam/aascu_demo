import { tutorialStepForRoute } from "./tutorial_state.js";
import { requestJSON, requestReport } from "./transport.js";
import { renderChatCharts, renderChatTable, renderChatQuery, renderChatMarkdown, renderChatTables } from "./chat_charts.js";
import { buildChatChartReport, renderChatEvidence } from "./chat_exports.js";
import { createStudentWorkspace } from "./students.js";
import { mountWorkbench } from "./workbench.js";

import { initializeDataset, datasetStorageKey, datasetChanged } from "./dataset-state.js";

await initializeDataset();

const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  model:
    '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  trend: '<path d="M3 18 9 12l4 3 8-10M15 5h6v6"/>',
  report:
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
  database:
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  sparkles:
    '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4M18 4h4"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  up: '<path d="M12 20V4m-6 6 6-6 6 6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield:
    '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.5 2.5 0 0 1 5 .7c0 2-2.5 2.3-2.5 4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  chevrondown: '<path d="m6 9 6 6 6-6"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
  users:
    '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 4v2"/>',
  building:
    '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M15 9h.01M9 13h.01M15 13h.01M10 21v-4h4v4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  refresh: '<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
  book: '<path d="M12 5c-3-3-8-2-10-1v15c3-1 7-2 10 1 3-3 7-2 10-1V4c-2-1-7-2-10 1Zm0 0v15"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="m12 3 10 18H2Z"/><path d="M12 9v5M12 17h.01"/>',
  sliders: '<path d="M4 7h6m4 0h6M4 17h10m4 0h2M10 4v6M14 14v6"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
};
const icon = (name, cls = "") =>
  `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.info}</svg>`;
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const num = (v) => (v == null ? "—" : Number(v).toLocaleString("en-US"));
const fixed = (v, d = 1) =>
  v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d);
const pct = (v, d = 1) => (v == null ? "Suppressed" : `${fixed(v, d)}%`);
const money = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v || 0);
const popNames = {
  all: "All students",
  "full-time": "Full-time students",
  "part-time": "Part-time students",
  pell: "Pell recipients",
  adult: "Students older than 24",
};
const routeNames = {
  evidence: "Student success",
  students: "Students",
  gaps: "Equity gaps",
  models: "Modeling",
  trends: "Trends",
  reports: "Reports",
  sources: "Data & definitions",
  workbench: "Workbench",
};
const metricNames = {
  retention: "Year-two retention",
  momentum: "Credit momentum",
  gateway_math: "Gateway math completion",
  persistence: "Persistence elsewhere",
};
function validView(v) {
  return (
    v &&
    typeof v.title === "string" &&
    v.title.length <= 160 &&
    Array.isArray(v.metrics) &&
    v.metrics.length > 0 &&
    v.metrics.every((m) => Object.hasOwn(metricNames, m)) &&
    v.filters &&
    (v.filters.cohort === "all" || /^[0-9]{4}-[0-9]{2}$/.test(v.filters.cohort)) &&
    Object.hasOwn(popNames, v.filters.population) &&
    [24, 30].includes(Number(v.filters.threshold))
  );
}
const safeViews = () => {
  try {
    return JSON.parse(localStorage.getItem(datasetStorageKey("waypoint-views")) || "[]")
      .filter((v) => validView(v))
      .slice(0, 12);
  } catch {
    return [];
  }
};
const state = {
  route: routeNames[location.hash.slice(1)]
    ? location.hash.slice(1)
    : "evidence",
  filters: { cohort: "all", population: "all", threshold: 24 },
  dashboard: null,
  sharedMeasures: null,
  gaps: null,
  definitions: null,
  gapMeasure: "retention",
  gapBreakdown: "race",
  assistantOpen: innerWidth >= 1400,
  sidebarCollapsed: false,
  dark: false,
  trends: null,
  model: null,
  scenario: null,
  scenarioDirty: false,
  chart: "retention",
  messages: [],
  chatPending: false,
  chatDetails: false,
  chatConcise: true,
  chatContext: null,
  chatDraft: "",
  chatProvider: null,
  connection: "checking",
  exportPending: false,
  loading: true,
  error: null,
  custom: null,
  saved: safeViews(),
  scenarioInput: {
    capacity: 250,
    budget: 25000,
    cost_per_student: 100,
    assumed_lift: 8,
    target: "high",
  },
};
const studentWorkspace = createStudentWorkspace({ request: api, onChange: () => { if (state.route === "students") renderPage(); } });
let requestVersion = 0,
  toastTimer;
const qs = (f = state.filters) => new URLSearchParams(f).toString();
async function api(path, body) {
  try {
    const value = await requestJSON(path, { body, timeoutMs: path === "/api/chat" ? 120000 : 30000 });
    setConnection("connected");
    return value;
  } catch (error) {
    if (path === "/api/chat" && error.code === "timeout")
      void checkConnection(); // A slow provider does not establish an HTTP server outage.
    else if (["connection", "timeout", "unexpected_response"].includes(error.code))
      setConnection("offline");
    throw error;
  }
}

function setConnection(value) {
  state.connection = value;
  const host = document.querySelector("#connection-banner");
  if (host) host.innerHTML = connectionBanner();
  const provider = document.querySelector("#chat-provider-status");
  if (provider) provider.innerHTML = chatProviderStatus();
}

function chatProviderStatus() {
  if (state.connection === "offline") return "App server unavailable. Provider status cannot be checked.";
  if (state.chatProvider?.configuration_error)
    return `${esc(state.chatProvider.configuration_error)} Configure DO_MODEL_INFERENCE_KEY and a distinct SANDBOX_VERIFY_MODEL in the server environment, then restart. No browser credentials are needed.`;
  if (state.chatProvider?.configured === false)
    return 'LLM not configured. Set <code>DO_MODEL_INFERENCE_KEY</code> and a distinct <code>SANDBOX_VERIFY_MODEL</code> in the server environment and restart the server. No browser credentials are needed.';
  if (state.chatProvider?.configured === true)
    return !state.chatDetails ? "" : `SQL generator: ${esc(state.chatProvider.model)}. Independent verifier: ${esc(state.chatProvider.verifier_model || "not configured")}. Availability is checked when you send a question.`;
  return "LLM configuration not yet confirmed by the app server.";
}

function connectionBanner() {
  if (state.connection !== "offline") return "";
  return `<div class="connection-notice" role="status">${icon("alert")}<div><strong>Server connection lost</strong><p>Chat, exports, and new calculations are unavailable. Displayed results remain from the last successful request.</p><details><summary>Start the server</summary><p>Run <code>npm run dev</code> in the <code>demo</code> folder and keep it running.</p></details></div><button class="button" data-action="reconnect">${icon("refresh")}Reconnect</button></div>`;
}

async function checkConnection() {
  if (document.hidden) return;
  try {
    const value = await requestJSON("/api/health", { timeoutMs: 5000 });
    if (value.status !== "ok") throw Error("Unexpected health response");
    if (datasetChanged(value.dataset)) { location.reload(); return; }
    state.chatProvider = value.chat || null;
    setConnection("connected");
  } catch {
    setConnection("offline");
  }
}
function toast(message) {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("visible"), 3500);
}
function scope(f = state.filters) {
  return `${f.cohort === "all" ? "All entry cohorts" : f.cohort} · ${popNames[f.population]} · ${f.threshold}-credit threshold`;
}
const button = (label, action, ic = "arrow", style = "") =>
  `<button class="button ${style}" data-action="${action}">${icon(ic)}${label}</button>`;
function shell() {
  if (!document.querySelector(".shell")) {
  document.querySelector("#app").innerHTML =
    `<div class="mobile-overlay" data-action="menu-close"></div><aside class="sidebar" aria-label="Main navigation"><a href="#evidence" class="brand" aria-label="AASCU home"><span class="brand-mark">A</span><span class="nav-text">AASCU</span></a><div class="brand-sub">Institutional analytics</div><div class="nav-label">Workspace</div><nav class="navigation">${Object.entries(
      routeNames,
    )
      .map(
        ([k, label]) =>
          `<a href="#${k}" title="${label}" aria-label="${label}" class="nav-item ${state.route === k ? "active" : ""}" ${state.route === k ? 'aria-current="page"' : ""}>${icon({ evidence: "grid", students: "users", gaps: "users", models: "model", trends: "trend", reports: "report", sources: "database", workbench: "database" }[k])}<span class="nav-text">${label}</span></a>`,
      )
      .join(
        "",
      )}</nav><div class="sidebar-bottom"><div class="sidebar-foot">${icon("database")}<div class="nav-text"><strong>Synthetic PDP data</strong><small>Shared model · local workspace</small></div></div><button class="nav-item" data-action="trust" title="Answer validation">${icon("shield")}<span class="nav-text">Answer validation</span></button></div></aside><div class="shell"><header class="topbar"><button class="icon-button" data-action="menu" aria-label="Toggle navigation" aria-expanded="${!state.sidebarCollapsed}">${icon("menu")}</button><div class="breadcrumb"><span>Workspace</span>${icon("chevron")}<strong>${routeNames[state.route]}</strong></div><div class="top-actions"><button class="button" data-action="start-tutorial" aria-label="Quick tour" title="Quick tour">${icon("help")}<span>Quick tour</span></button><button class="icon-button" data-action="theme" aria-label="Toggle dark theme" aria-pressed="${state.dark}">${icon("sliders")}</button><button class="button" data-action="toggle-assistant" aria-expanded="${state.assistantOpen}">${icon("sparkles")}<span>Assistant</span></button><button class="icon-button" data-action="help" aria-label="About this workspace">${icon("help")}</button></div></header><div id="connection-banner">${connectionBanner()}</div><div class="workspace-body"><main class="content" id="main" tabindex="-1"></main><aside class="assistant-dock" aria-label="Data assistant" ${state.assistantOpen ? "" : "hidden"}>${chatPanel()}</aside></div></div>`;
  }
  document.querySelectorAll(".navigation a").forEach(link => {
    const active = link.hash === `#${state.route}`;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.querySelector(".breadcrumb strong").textContent = routeNames[state.route];
  document.body.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
  document.body.classList.toggle("assistant-open", state.assistantOpen);
  document.documentElement.classList.toggle("dark", state.dark);
  syncNavigation();
  renderPage();
}
// Offscreen mobile navigation must not remain in the keyboard tab order.
function syncNavigation() {
  const expanded = innerWidth < 900 ? document.body.classList.contains("nav-open") : !state.sidebarCollapsed;
  document.querySelector(".sidebar").inert = innerWidth < 900 && !expanded;
  document.querySelector('.topbar [data-action="menu"]').setAttribute("aria-expanded", expanded);
}
function heading(eyebrow, title, subtitle, actions = "") {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${actions}</div></div>`;
}
function filterBar({ momentum = true } = {}) {
  return `<div class="filter-bar"><div class="filter-control">${icon("calendar")}<select data-filter="cohort" aria-label="Entry cohort">${["all", ...(state.dashboard?.meta.cohorts || [])].map((v) => `<option value="${v}" ${state.filters.cohort === v ? "selected" : ""}>${v === "all" ? "All entry cohorts" : v + " entry cohort"}</option>`).join("")}</select></div><div class="filter-control">${icon("users")}<select data-filter="population" aria-label="Student population">${Object.entries(
    popNames,
  )
    .map(
      ([v, l]) =>
        `<option value="${v}" ${state.filters.population === v ? "selected" : ""}>${l}</option>`,
    )
    .join(
      "",
    )}</select></div>${momentum ? `<div class="filter-control"><label for="threshold-filter">Momentum</label><select id="threshold-filter" data-filter="threshold" aria-label="Credit momentum threshold"><option value="24" ${Number(state.filters.threshold) === 24 ? "selected" : ""}>24 credits</option><option value="30" ${Number(state.filters.threshold) === 30 ? "selected" : ""}>30 credits</option></select></div>` : ""}${state.filters.cohort !== "all" || state.filters.population !== "all" ? '<button class="reset-button" data-action="reset-filters">Reset</button>' : ""}<span class="scope-caption">${icon("database")}${num(state.dashboard?.meta.filtered_rows)} student-cohort records${state.route === "students" ? " before list filters" : ""}</span></div>`;
}
function footer() {
  return `<div class="bottom-note"><span>${icon("info")}Synthetic PDP data. No real student or institutional records.</span><button data-action="sources">View sources & definitions ${icon("arrow")}</button></div>`;
}
function renderPage() {
  const root = document.querySelector("#main");
  if (!root) return;
  if (!root.querySelector(".dashboard-content")) root.innerHTML = '<div class="dashboard-content"></div><div class="workbench-content" hidden></div>';
  const main = root.querySelector(".dashboard-content");
  const workbench = root.querySelector(".workbench-content");
  main.hidden = state.route === "workbench";
  workbench.hidden = state.route !== "workbench";
  document.title = `${routeNames[state.route]} | AASCU`;
  document.body.classList.toggle("workbench-open", state.route === "workbench");
  if (state.route === "workbench") {
    mountWorkbench(workbench);
    return;
  }
  const dock = document.querySelector(".assistant-dock");
  if (dock) dock.innerHTML = chatPanel();
  scrollChat();
  if (state.error) {
    main.innerHTML = `${heading("Workspace", "Data unavailable", "The analysis could not be loaded.")}<div class="error-box">${esc(state.error)}<br>${button("Try again", "retry", "refresh")}</div>`;
    renderTutorial();
    return;
  }
  if (state.loading || !state.dashboard) {
    main.innerHTML = `<div class="page-loader"><span class="loading-mark"></span>Loading data…</div>`;
    renderTutorial();
    return;
  }
  main.innerHTML =
    {
      evidence: renderEvidence,
      students: renderStudents,
      gaps: renderGaps,
      models: renderModels,
      trends: renderTrends,
      reports: renderReports,
      sources: renderSources,
    }[state.route]() + footer();
  setExportPending(state.exportPending);
  renderTutorial();
}
const tutorialSteps = [
  {route:"evidence", target:".filter-bar", title:"Choose who you want to understand", text:"Start with Student success. Choose an entry cohort and student population. The cards and tables update to reflect your selection."},
  {route:"evidence", target:".guided-starts", title:"Start with a question", text:"Open this dropdown for a trend summary and suggested next steps. Close it again when you want more room to read the chart.", open:true},
  {route:"students", target:".navigation", title:"Move from a finding to student records", text:"Choose Students to search synthetic records and review academic history. Open View student to inspect a profile and plan a local demonstration follow-up."},
  {route:"trends", routes:["gaps", "models"], target:".navigation", title:"Explore the pattern", text:"Use Trends for changes across cohorts and Equity gaps for group comparisons. Modeling is a separate historical analysis; its estimates are not ready for student decisions."},
  {route:"sources", target:".navigation", title:"Check what a measure means", text:"Data & definitions explains the source fields, calculations, and missing data. Check definitions before drawing a conclusion or comparing groups."},
  {route:"evidence", target:".assistant-dock", title:"Ask the data assistant", text:"Ask about a measure, request example records, or explore a trend. Concise responses starts on; Analysis details starts off. The selected cohort and population still apply.", chat:true},
  {route:"reports", target:".navigation", title:"Share the evidence", text:"Use Reports to prepare a brief or export evidence. Save a useful view from Student success to revisit it later in this browser. All data in this demo is synthetic."},
];
let tutorialStep = null;
let tutorialOriginalAssistant = false;
let tutorialPendingRoute = null;
function renderTutorial() {
  const restoreAction = document.activeElement?.closest("#quick-tutorial") ? document.activeElement.dataset.action : null;
  document.querySelectorAll(".tutorial-highlight").forEach(el => el.classList.remove("tutorial-highlight"));
  document.querySelector("#quick-tutorial")?.remove();
  if (tutorialStep === null) return;
  tutorialStep = tutorialStepForRoute(tutorialSteps, tutorialStep, state.route, tutorialPendingRoute);
  if (state.route === tutorialPendingRoute) tutorialPendingRoute = null;
  const step = tutorialSteps[tutorialStep];
  const target = document.querySelector(step.target);
  target?.classList.add("tutorial-highlight");
  if (step.open && target) target.open = true;
  document.body.insertAdjacentHTML("beforeend", `<aside id="quick-tutorial" class="quick-tutorial" role="region" aria-label="Quick tutorial"><div class="tutorial-top"><span>QUICK TOUR · ${tutorialStep + 1} / ${tutorialSteps.length}</span><button class="icon-button" data-action="close-tutorial" aria-label="Close tutorial">${icon("close")}</button></div><div aria-live="polite"><h2>${esc(step.title)}</h2><p>${esc(step.text)}</p></div><div class="tutorial-controls"><button class="button" data-action="tutorial-back" ${tutorialStep === 0 ? "disabled" : ""}>Back</button><button class="button primary" data-action="tutorial-next">${tutorialStep === tutorialSteps.length - 1 ? "Finish" : "Next"} ${icon("arrow")}</button></div></aside>`);
  if (restoreAction) document.querySelector(`#quick-tutorial [data-action="${restoreAction}"]`)?.focus({preventScroll:true});
}
function showTutorial(index) {
  tutorialStep = index;
  const step = tutorialSteps[index];
  tutorialPendingRoute = step.route;
  state.assistantOpen = !!step.chat;
  const dock = document.querySelector(".assistant-dock");
  if (dock) dock.hidden = !state.assistantOpen;
  document.body.classList.toggle("assistant-open", state.assistantOpen);
  document.querySelector('.topbar [data-action="toggle-assistant"]')?.setAttribute("aria-expanded", String(state.assistantOpen));
  if (state.route === "evidence") document.querySelector(".guided-starts")?.removeAttribute("open");
  navigate(step.route);
  renderTutorial();
  window.scrollTo({top:0, behavior:"instant"});
  document.querySelector('[data-action="tutorial-next"]')?.focus({preventScroll:true});
}
function closeTutorial() {
  tutorialStep = null;
  tutorialPendingRoute = null;
  state.assistantOpen = tutorialOriginalAssistant;
  document.querySelector(".assistant-dock").hidden = !state.assistantOpen;
  document.body.classList.toggle("assistant-open", state.assistantOpen);
  document.querySelector('.topbar [data-action="toggle-assistant"]')?.setAttribute("aria-expanded", String(state.assistantOpen));
  renderTutorial();
  document.querySelector('[data-action="start-tutorial"]')?.focus();
}
function sparkline(id) {
  const values = state.dashboard.timeline.map((d) => d[id]);
  if (values.some((v) => v == null)) return "";
  const min = Math.min(...values) - 5,
    max = Math.max(...values) + 5;
  const pts = values.map(
    (v, i) => `${2 + i * 24},${29 - ((v - min) / (max - min)) * 24}`,
  );
  return `<svg class="sparkline" viewBox="0 0 79 33" aria-hidden="true"><path d="M${pts.join(" L")} L74 33 L2 33Z" fill="currentColor" opacity=".06"/><path d="M${pts.join(" L")}" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="74" cy="${29 - ((values.at(-1) - min) / (max - min)) * 24}" r="2.2" fill="currentColor"/></svg>`;
}
function metricCards() {
  const metrics = state.dashboard.metrics.filter(
    (m) => !state.custom || state.custom.metrics.includes(m.id),
  );
  return `<div class="metric-grid ${state.custom ? "custom-metrics" : ""}" style="--metric-count:${metrics.length}">${metrics.map((m) => `<article class="metric-card"><div class="metric-top"><h2>${esc(m.label)}</h2><button data-action="metric" data-id="${m.id}" aria-label="Definition of ${esc(m.label)}">${icon("info")}</button></div><div class="metric-value-row"><div class="metric-value">${fixed(m.value)}${m.value == null ? "" : "<em>%</em>"}</div>${sparkline(m.id)}</div><div class="metric-bottom"><span class="metric-pill">Observed</span><strong>${num(m.numerator)}</strong> of ${num(m.denominator)} eligible records</div><div class="metric-note">${m.id === "gateway_math" ? "Required to take gateway math" : m.id === "momentum" ? `${num(m.missing)} missing credit values excluded` : m.id === "persistence" ? "Enrolled or credentialed elsewhere" : "Enrollment or credential at cohort institution"}</div></article>`).join("")}</div>`;
}
function lineChart(metric = state.chart) {
  const chartWidth = window.innerWidth < 700 ? 430 : 660;
  const rows = state.dashboard.timeline,
    left = 43,
    right = chartWidth - 33,
    top = 25,
    bottom = 190;
  const y = (v) => bottom - (v / 100) * (bottom - top),
    x = (i) => left + (i * (right - left)) / 3;
  const valid = rows.map((r, i) =>
    r[metric] != null ? [x(i), y(r[metric])] : null,
  );
  const path = valid
    .map((p, i) =>
      p ? `${i === 0 || !valid[i - 1] ? "M" : "L"}${p[0]},${p[1]}` : "",
    )
    .join(" ");
  return `<svg class="line-chart" viewBox="0 0 ${chartWidth} 235" role="img" aria-label="${esc(metricNames[metric])} across four entry cohorts"><title>${esc(rows.map((r) => `${r.cohort}: ${pct(r[metric])}`).join("; "))}</title>${[0, 25, 50, 75, 100].map((v) => `<line class="grid-line" x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left - 11}" y="${y(v) + 3}" text-anchor="end">${v}%</text>`).join("")}${valid.every(Boolean) ? `<path d="${path} L${right},${bottom} L${left},${bottom}Z" fill="#eff4e8" opacity=".8"/>` : ""}<path d="${path}" stroke="#739553" stroke-width="2.2" fill="none"/>${rows.map((r, i) => `<g role="button" tabindex="0" data-action="cohort-point" data-cohort="${r.cohort}" aria-label="Filter to ${r.cohort}, ${pct(r[metric])}">${r[metric] != null ? `<circle cx="${x(i)}" cy="${y(r[metric])}" r="11" fill="${state.filters.cohort === r.cohort ? "#e0ebca" : "transparent"}"/><circle cx="${x(i)}" cy="${y(r[metric])}" r="4" fill="#fff" stroke="#739553" stroke-width="2"/><text class="point-label" x="${x(i)}" y="${y(r[metric]) - 13}" text-anchor="middle">${pct(r[metric])}</text>` : ""}<text x="${x(i)}" y="212" text-anchor="middle">${r.cohort}</text><text x="${x(i)}" y="228" text-anchor="middle" style="font-size:8px">eligible n = ${num(r[metric + "_denominator"])}</text></g>`).join("")}</svg>`;
}
function chartPanel() {
  const allowed = state.custom
    ? state.custom.metrics
    : ["retention", "momentum", "gateway_math"];
  if (!allowed.includes(state.chart)) state.chart = allowed[0];
  return `<section class="panel chart-panel"><div class="panel-header"><div><h2>Cohort trends</h2><p>Compare outcomes across entry cohorts.</p></div><button class="button" data-action="trends">View trends ${icon("arrow")}</button></div><div class="chart-toolbar"><div class="segmented" aria-label="Chart metric">${allowed.map((m) => `<button data-action="chart" data-metric="${m}" class="${state.chart === m ? "active" : ""}" aria-pressed="${state.chart === m}">${m === "retention" ? "Retention" : m === "momentum" ? "Credit momentum" : m === "persistence" ? "Persistence" : "Gateway math"}</button>`).join("")}</div><div class="chart-key"><span></span>${popNames[state.filters.population]}</div></div><div class="chart-wrap">${lineChart()}</div><p class="chart-caption">${icon("info")}Select a cohort to update the summary. The chart shows all cohorts for the selected population.</p></section>`;
}
function segmentPanel() {
  const cols = state.custom ? state.custom.metrics : ["retention", "momentum"];
  const rows = state.dashboard.segments.filter((segment) => segment.n > 0);
  const intensityOnly = ["full-time", "part-time"].includes(state.filters.population);
  return `<section class="panel segment-panel"><div class="panel-header"><div><h2>Enrollment intensity</h2><p>First-term enrollment intensity · selected scope</p></div>${cols.includes("momentum") ? `<span class="badge neutral">${state.filters.threshold}-credit threshold</span>` : ""}</div><div class="panel-body">${intensityOnly ? `<div class="scope-explanation"><p>You selected ${esc(popNames[state.filters.population].toLowerCase())}. Other enrollment groups are outside this selection.</p>${button("Compare both groups · all students", "compare-intensity", "users")}</div>` : ""}<div class="table-scroll"><table class="data-table"><thead><tr><th scope="col">Student group</th><th scope="col">Records</th>${cols.map((m) => `<th scope="col">${m === "retention" ? "Retention" : m === "momentum" ? "Momentum" : m === "gateway_math" ? "Math" : "Elsewhere"}</th>`).join("")}<th scope="col">Explore</th></tr></thead><tbody>${rows.map((segment) => `<tr><td><span class="segment-name ${esc(segment.population)}"><i></i>${esc(segment.name)}</span></td><td>${num(segment.n)}</td>${cols.map((m) => `<td>${segment[m] == null ? "—" : pct(segment[m])}</td>`).join("")}<td>${state.filters.population === "all" && ["full-time", "part-time"].includes(segment.population) ? `<button class="button text" data-action="student-group" data-population="${esc(segment.population)}" aria-label="View ${esc(segment.name.toLowerCase())} student records">View students ${icon("arrow")}</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="${cols.length + 3}">No records in this selection.</td></tr>`}</tbody></table></div><p class="table-footnote">Rates use eligible denominators; groups with fewer than 20 eligible records are suppressed. A student list contains the whole selected group, including records excluded from a particular measure.</p>${button("View students in this selection", "students", "users")}</div></section>`;
}
function chatPanel() {
  return `<section class="panel assistant-panel ${state.chatDetails ? "show-chat-details" : ""}" aria-label="Evidence assistant"><div class="assistant-header"><div class="assistant-symbol">${icon("sparkles")}</div><div><h2>Data assistant</h2><p>Explore PDP data and definitions</p></div><button class="icon-button" data-action="clear-chat" aria-label="Start a new conversation">${icon("refresh")}</button><button class="icon-button" data-action="toggle-assistant" aria-label="Close assistant">${icon("close")}</button></div><button class="chat-details-toggle" data-action="toggle-chat-concise" role="switch" aria-checked="${state.chatConcise}" title="Use brief, plain-language answers for future responses">Concise responses <span>${state.chatConcise ? "On" : "Off"}</span></button><button class="chat-details-toggle" data-action="toggle-chat-details" role="switch" aria-checked="${state.chatDetails}">Analysis details <span>${state.chatDetails ? "On" : "Off"}</span></button><div id="chat-provider-status" class="chat-provider-status" role="status">${chatProviderStatus()}</div><div class="chat-feed" id="chat-feed" aria-live="polite" aria-relevant="additions text">${chatMessages()}</div><form class="chat-compose" id="chat-form"><div class="chat-input-wrap"><textarea id="chat-question" aria-label="Ask a question about the data" placeholder="Ask about fields, definitions, or trends…" rows="2" maxlength="1000" ${state.chatPending ? "disabled" : ""}>${esc(state.chatDraft)}</textarea><div class="compose-bottom"><small>${icon("lock")}${esc(scope(state.filters))}</small><button class="send-button" type="submit" aria-label="Send question" ${state.chatPending ? "disabled" : ""}>${icon("up")}</button></div></div></form><div class="assistant-bottom">Synthetic demo data · AI checks can make mistakes.</div></section>`;
}
function chatMessages() {
  if (!state.messages.length)
    return `<div class="chat-welcome"><h3>What would you like to explore?</h3><p>Ask about the schema, understand a measure, or analyze your selected data.</p></div>${["What tables and fields are available?", "How is retention defined?", "Chart average earned credits by cohort"].map((q) => `<button class="suggestion" data-action="suggest" data-question="${esc(q)}">${esc(q)}${icon("arrow")}</button>`).join("")}`;
  return (
    state.messages
      .map((m, i) =>
        m.role === "user"
          ? `<div class="chat-message user">${esc(m.text)}</div>`
          : `<div class="chat-message assistant"><div class="answer-text">${renderChatMarkdown(m.answer)}</div><div class="chat-technical"><div class="answer-status ${m.status === "verified" ? "" : "unsupported"}">${icon(m.status === "verified" ? "shield" : "info")}${m.status === "verified" ? "Server-calculated evidence" : m.status === "error" ? "Request failed" : m.status === "explained" ? "Catalog explanation reviewed" : m.status === "help" ? "Guidance" : "Request needs clarification"}</div>${m.cache?.response_hit ? `<p class="answer-scope">Reused a checked answer for the same question, context, scope and data version.</p>` : m.cache?.plan_hits ? `<p class="answer-scope">Reused ${num(m.cache.plan_hits)} checked planning/review step(s); local SQL checks still ran.</p>` : ""}${m.engine ? `<p class="answer-scope">Generator: ${esc(m.engine.model)} · Verifier: ${esc(m.engine.verifier_model || "not reported")}. Review SQL and results; model review is not a correctness guarantee.</p>` : ""}</div>${renderChatCharts(m.charts, m.status === "verified" ? i : null)}${renderChatTables(m.tables)}${m.charts?.length ? `<div class="chat-technical">${renderChatTable(m.table)}</div>` : renderChatTable(m.table)}<div class="chat-technical"><div class="answer-scope">${m.query ? "UI scope (SQL may further restrict): " : ""}${esc(scope(m.filters))}</div>${m.citations?.length ? `<button class="citation-button" data-action="citations" data-index="${i}">${icon("book")}${m.citations.length} source ${m.citations.length === 1 ? "reference" : "references"}</button>` : ""}${renderChatQuery(m.query)}</div>${m.retryQuestion ? `<button class="button soft" data-action="retry-chat" data-index="${i}">${icon("refresh")}Retry question</button>` : ""}${
              ["unsupported", "help"].includes(m.status) &&
              m.suggestions?.length
                ? `<div class="chat-suggestions">${m.suggestions
                    .slice(0, 3)
                    .map(
                      (q) =>
                        `<button class="suggestion" data-action="suggest" data-question="${esc(q)}">${esc(q)}${icon("arrow")}</button>`,
                    )
                    .join("")}</div>`
                : ""
            }${m.dashboard ? `<div class="dashboard-preview"><span class="badge">${icon("grid")}Custom dashboard</span><h3>${esc(m.dashboard.title)}</h3><p>${m.dashboard.metrics.map((v) => esc(metricNames[v])).join(" · ")}</p><button class="button primary" data-action="open-dashboard" data-index="${i}">${icon("grid")}Open this dashboard</button></div>` : ""}</div>`,
      )
      .join("") +
    (state.chatPending
      ? '<div class="pending-dots" role="status">Interpreting your question and calculating evidence…</div>'
      : "")
  );
}
function customBanner() {
  return state.custom
    ? `<div class="custom-banner"><span>${icon("grid")}<strong>Custom dashboard</strong> · ${state.custom.metrics.length} selected metrics</span><div><button data-action="save-view">${icon("save")}Save view</button><button data-action="clear-view">Reset view ${icon("close")}</button></div></div>`
    : "";
}
function decisionSummary() {
  const signals = state.dashboard.signals.filter((signal) => !state.custom || state.custom.metrics.includes(signal.metric));
  const signal = signals.find((signal) => signal.metric === "retention") || signals[0];
  return `<section class="decision-summary" aria-label="Finding and next steps"><div><span class="step-label">1 · What changed</span><h2>${signal ? esc(signal.title) : "Start with the selected population"}</h2><p>${signal ? esc(signal.detail) : "Review the outcomes below, then inspect the students represented in this selection."}</p></div><div><span class="step-label">2 · What it means</span><p>${signal ? "This is an observed difference between entry cohorts. Unequal follow-up can affect the result; it does not identify why outcomes changed." : "These records describe historical outcomes. Missing information is excluded from each measure according to its definition."}</p></div><div><span class="step-label">3 · What to do next</span><p>Confirm the evidence, then open a student record to plan a demonstration follow-up.</p><div class="decision-actions">${button("Review evidence", "trends", "trend")}${button("View students", "students", "users", "primary")}</div></div></section>`;
}
function guidedStarts() {
  return `<details class="disclosure guided-starts"><summary>Start with a question</summary>${decisionSummary()}<div class="guided-grid"><article><h3>Who is missing from the headline?</h3><p>Explore adult learners or inspect transfer-in records. This extract has no campus identifier or official IPEDS comparison.</p><div class="decision-actions">${button("Explore students older than 24", "explore-adults", "users")}${button("View transfer-in students", "explore-transfers", "users")}</div></article><article><h3>How do part-time outcomes compare?</h3><p>Compare both enrollment groups using all students in the selected cohort. The comparison cannot explain the effect of changing financial aid.</p>${button("Compare both groups · all students", "compare-intensity", "trend")}</article><article><h3>What happens after a finding?</h3><p>Open the selected student list, inspect academic history, and record a local demonstration follow-up.</p>${button("Open student records", "students", "arrow")}</article></div></details>`;
}
function renderStudents() {
  return heading("Student records", "Students", "Inspect synthetic academic records and plan a local demonstration follow-up.") + filterBar() + studentWorkspace.render(state.filters);
}
function renderEvidence() {
  return heading("Student outcomes", state.custom?.title || "Student success", "Understand a finding, inspect the records, and plan a next step.",
    (state.custom ? "" : button("Save view", "save-current-view", "save")) + button("Saved views", "saved-views", "grid") + button("Export brief", "export-brief", "download", "primary")) +
    customBanner() + filterBar() + guidedStarts() + metricCards() +
    `<div class="evidence-grid"><div class="evidence-left">${chartPanel()}${segmentPanel()}</div></div><div class="method-notice">${icon("info")}Shared PDP measures power these results. Gateway completion excludes unknown outcomes. ${button("Review definitions", "sources", "book", "text")}</div>` +
    (state.custom ? "" : sharedMeasurePanel());
}

// These measures have different units and stay separate from the four dashboard metrics.
function sharedMeasurePanel() {
  if (!state.sharedMeasures) return '<div class="page-loader">Loading additional shared measures…</div>';
  return `<div class="section-heading"><div><h2>Additional shared measures</h2><p>Selected scope. Ask the assistant about these measures; saved dashboards and evidence exports retain the four core metrics.</p></div></div><div class="shared-measures">${state.sharedMeasures.metrics.map(m => `<section class="panel"><div class="panel-body"><h3>${esc(m.label)}</h3><div class="shared-value">${pct(m.value)}</div><p class="small muted">${num(m.denominator)} eligible ${esc(m.unit)} · ${num(m.missing)} excluded</p><details><summary>Definition and limits</summary><p>${esc(m.definition)}</p>${m.id === "credit_completion" ? '<p>This is an average of individual earned/attempted ratios, not the share earning 24 or 30 credits. Ratios above 1 are capped by the shared measure.</p>' : m.id === "dfw_rate" ? '<p>Counts enrollments across terms. The shared numeric-grade cutoff is below 2.0; this cutoff is still an open definition decision.</p>' : ""}</details></div></section>`).join("")}</div>`;
}

// Shared gap-finder results remain separate from adjacent-cohort changes.
function renderGaps() {
  const g = state.gaps;
  return heading("Group comparisons", "Equity gaps", "Find differences worth investigating within the selected population.") + filterBar({ momentum: false }) +
    `<div class="gap-controls"><label>Measure<select data-gap="measure" aria-label="Gap measure">${Object.entries({retention: "Retention", persistence: "Persistence elsewhere", gateway_math: "Gateway math", gateway_english: "Gateway English"}).map(([v,l]) => `<option value="${v}" ${state.gapMeasure === v ? "selected" : ""}>${l}</option>`).join("")}</select></label><label>Breakdown<select data-gap="breakdown" aria-label="Gap breakdown">${Object.entries({race: "Race", gender: "Gender", pell: "Pell status", age_band: "Age band", enrollment_intensity: "Enrollment intensity", "race,gender": "Race × gender", "pell,enrollment_intensity": "Pell × enrollment intensity"}).map(([v,l]) => `<option value="${v}" ${state.gapBreakdown === v ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>` +
    (!g ? '<div class="page-loader">Calculating group comparisons…</div>' :
    `<section class="panel"><div class="panel-header"><div><h2>Where outcomes differ</h2><p>Each row compares one group with all other eligible records in the current selection. A negative difference means a lower rate; percentage points describe the distance between two rates.</p></div></div><p class="gap-guidance">Use these results to ask about access and support. A group difference does not explain its cause or assign a priority to an individual student.</p><div class="table-scroll"><table class="data-table gap-table"><thead><tr><th scope="col">Student group</th><th scope="col">Eligible records</th><th scope="col">Group rate</th><th scope="col">Other students</th><th scope="col">Difference (points)</th><th scope="col">How to read it</th></tr></thead><tbody>${g.rows.map(r => `<tr><td>${esc(r.group_values.join(" × "))}</td><td>${num(r.denominator)}</td><td>${r.metric_rate == null ? "—" : pct(r.metric_rate * 100)}</td><td>${r.comparison_rate == null ? "—" : pct(r.comparison_rate * 100)}</td><td class="gap-value ${r.gap_pts < 0 ? "negative" : ""}">${r.gap_pts == null ? "—" : (r.gap_pts > 0 ? "+" : "") + fixed(r.gap_pts, 2)}</td><td><span class="badge ${r.status === "ok" && !r.likely_noise ? "amber" : "neutral"}">${r.suppressed ? "Too few records to display" : r.status === "unknown_group" ? "Group information missing" : r.status !== "ok" || r.likely_noise ? "Difference uncertain" : "Worth investigating"}</span>${r.ci_low == null && r.q_value == null ? "" : `<details class="gap-statistics"><summary>Statistical detail</summary><p>95% interval: ${r.ci_low == null ? "Unavailable" : `${fixed(r.ci_low, 2)} to ${fixed(r.ci_high, 2)} points`}. ${r.q_value == null ? "" : `Adjusted q-value: ${fixed(r.q_value, 4)}.`}</p><p>Uncertain does not mean equal outcomes. The interval and multiple-comparison check limit what this sample supports.</p></details>`}</td></tr>`).join("") || '<tr><td colspan="6">No comparisons for this selection.</td></tr>'}</tbody></table></div></section><details class="disclosure"><summary>How comparisons are calculated</summary><div class="disclosure-content"><p>${esc(g.method)}</p><p>Eligible counts depend on the selected measure. Small groups and small comparison groups are hidden. Rows follow the shared affected-student ranking; this is an order for reviewing aggregate differences, not a student outreach ranking.</p></div></details>`);
}
function calibrationChart(m) {
  const x = (v) => 45 + v * 3.9,
    y = (v) => 205 - v * 1.7;
  return `<svg class="model-chart" viewBox="0 0 470 245" role="img" aria-label="Predicted versus observed retention calibration"><title>Perfect calibration follows the diagonal. The observed points fall below the diagonal, indicating overestimated retention.</title>${[0, 25, 50, 75, 100].map((v) => `<line class="grid-line" x1="45" x2="435" y1="${y(v)}" y2="${y(v)}"/><text x="35" y="${y(v) + 4}" text-anchor="end">${v}%</text><text x="${x(v)}" y="224" text-anchor="middle">${v}%</text>`).join("")}<path d="M45 205L435 35" stroke="#cdd8c1" stroke-dasharray="5 5" fill="none"/><text x="230" y="244" text-anchor="middle">Predicted retention</text>${m.calibration
    .filter((b) => b.predicted != null)
    .map(
      (b) =>
        `<circle cx="${x(b.predicted)}" cy="${y(b.observed)}" r="6" fill="#91a873" stroke="#fff" stroke-width="2"><title>${esc(b.bin)}: predicted ${pct(b.predicted)}, observed ${pct(b.observed)}, n=${b.n}</title></circle>`,
    )
    .join("")}<text x="48" y="17">Observed retention</text></svg>`;
}
function renderModels() {
  const m = state.model;
  if (m?.available === false) return heading("Retention analysis", "Modeling unavailable", m.reason) + '<p>The dashboard, student browser, and reports still use the current dataset.</p>';
  return heading("Retention analysis", "Modeling", "Explore a historical model and size a hypothetical support pilot.", button("Model card", "model-card", "book") + button("Export analysis", "export-model", "download", "primary")) +
    (!m ? '<div class="page-loader"><span class="loading-mark"></span>Evaluating the historical model…</div>' :
    `<section class="model-readiness"><div><span class="badge amber">Historical demonstration · not ready for student decisions</span><h2>Useful for planning questions; verify probability calibration</h2><p>The model predicted ${pct(m.test.predicted_retention)} retention, while ${pct(m.test.observed_retention)} was recorded: a difference of ${fixed(m.test.calibration_gap)} percentage points (predicted minus recorded). Verify follow-up completeness before applying it to real students.</p><p><strong>Fixed scope:</strong> ${num(m.test.rows)} synthetic records from the ${esc(m.test.cohort)} test cohort. Dashboard filters do not change this evaluation or the scenario population.</p></div><div class="model-next-step"><h3>For a student follow-up</h3><p>Inspect recorded academic history in Students. The student list does not use these model bands to rank people.</p>${button("Open student records", "students", "users")}</div></section>
    <details class="disclosure model-diagnostics"><summary>Model performance and statistical diagnostics</summary><div class="disclosure-content"><p>Train: ${esc(m.training.cohorts.join(", "))} · Validate: ${esc(m.validation.cohorts.join(", "))} · Test: ${esc(m.test.cohort)}. Uses entry characteristics and first-term GPA.</p><div class="model-metrics"><div class="mini-metric"><span class="label">Ranking ability · AUC</span><strong>${fixed(m.test.auc, 3)}</strong><small>0.5 = random; 1.0 = perfect ranking</small></div><div class="mini-metric"><span class="label">Probability error · Brier</span><strong>${fixed(m.test.brier, 3)}</strong><small>Baseline ${fixed(m.test.baseline_brier, 3)} · lower is better</small></div><div class="mini-metric"><span class="label">Calibration gap</span><strong>${fixed(m.test.calibration_gap)}<small class="inline-unit"> points</small></strong><small>Predicted minus recorded retention</small></div><div class="mini-metric"><span class="label">Test records</span><strong>${num(m.test.rows)}</strong><small>${num(m.split.removed_overlap_rows)} repeated-student rows removed from earlier cohorts</small></div></div><div class="two-columns"><section class="panel"><div class="panel-header"><div><h2>Predicted versus recorded retention</h2><p>Each point represents a probability band.</p></div></div><div class="panel-body">${calibrationChart(m)}</div></section><section class="panel"><div class="panel-header"><div><h2>Historical model bands</h2><p>Grouped by predicted nonretention; these are not outreach assignments.</p></div></div><div class="panel-body">${m.risk_bands.map((band) => `<div class="risk-row"><span class="name">${band.id === "high" ? "Higher prediction" : band.id === "medium" ? "Middle prediction" : "Lower prediction"}</span><div class="risk-bar"><span style="width:${band.share}%"></span></div><span class="count">${num(band.n)}</span></div><p class="risk-detail">${fixed(band.share)}% of test cohort · ${pct(band.observed_retention)} recorded retention</p>`).join("")}</div></section></div></div></details>
<div class="section-heading"><div><h2>Outreach scenario</h2><p>Set staff capacity, budget, and an assumed retention improvement.</p></div><span class="badge amber">User-supplied assumptions</span></div><section class="panel"><div class="panel-body"><div class="scenario-layout"><form id="scenario-form"><div class="scenario-control"><label for="capacity">Staff capacity <output id="capacity-output">${num(state.scenarioInput.capacity)}</output></label><input id="capacity" name="capacity" type="range" min="0" max="1000" step="10" value="${state.scenarioInput.capacity}"/><div class="range-ends"><span>0 students</span><span>1,000 students</span></div></div><div class="scenario-control"><label for="assumed-lift">Assumed retention improvement <output id="assumed-lift-output">${state.scenarioInput.assumed_lift} pp</output></label><input id="assumed-lift" name="assumed_lift" type="range" min="0" max="25" step="1" value="${state.scenarioInput.assumed_lift}"/><div class="range-ends"><span>0 percentage points</span><span>25 percentage points</span></div></div><div class="field-row"><div class="number-field"><label for="budget">Pilot budget ($)</label><input id="budget" name="budget" type="number" min="0" max="1000000000" step="100" required value="${state.scenarioInput.budget}"/></div><div class="number-field"><label for="cost-per-student">Cost per student ($)</label><input id="cost-per-student" name="cost_per_student" type="number" min="1" max="1000000" step="1" required value="${state.scenarioInput.cost_per_student}"/></div></div><div class="number-field" style="margin-top:15px"><label for="target">Historical scenario population</label><select name="target" id="target"><option value="high" ${state.scenarioInput.target === "high" ? "selected" : ""}>Higher predicted nonretention band (historical)</option><option value="all" ${state.scenarioInput.target === "all" ? "selected" : ""}>All ${esc(m.test.cohort)} test records</option></select></div><p class="field-hint">Enter the expected cost and retention improvement. The extract contains no intervention records.</p><div class="scenario-submit"><button class="button primary" type="submit">${icon("sliders")}Run scenario</button><small id="scenario-dirty">${state.scenarioDirty ? "Inputs changed. Run to update the result." : "Change inputs, then run to update."}</small></div></form><div id="scenario-result" class="${state.scenarioDirty ? "stale-result" : ""}">${scenarioResult()}</div></div></div></section><details class="disclosure"><summary>Model inputs, methods, and limitations</summary><div class="disclosure-content"><p>Regularized logistic regression uses training-set imputation and a later test cohort. Coefficients describe conditional associations.</p><table class="data-table feature-table"><thead><tr><th>Feature (reference in brackets)</th><th>Odds ratio</th></tr></thead><tbody>${m.features.map((f) => `<tr><td>${esc(f.name)}<br><span class="muted">[${esc(f.reference)}]</span></td><td>${fixed(f.odds_ratio, 2)}</td></tr>`).join("")}</tbody></table><ul>${[...m.methodology, ...m.limitations].map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div></details>`);
}
function scenarioResult() {
  const s = state.scenario;
  if (!s)
    return '<div class="scenario-result"><p class="small">Run a scenario to calculate reach and expected outcomes.</p></div>';
  return `<div class="scenario-result"><span class="eyebrow">Scenario result</span><div class="big-number">+${fixed(s.expected_additional_retained, 1)}</div><p class="result-label">additional retained students, if the assumed lift holds</p><div class="divider"></div><div class="result-row"><span>Students reached</span><strong>${num(s.reach)} of ${num(s.eligible_students)} eligible</strong></div><div class="result-row"><span>Estimated cost</span><strong>${money(s.cost)}</strong></div><div class="result-row"><span>Budget remaining</span><strong>${money(s.budget_remaining)}</strong></div><div class="result-row"><span>Limiting factor</span><strong>${esc(s.binding_constraint)}</strong></div><p class="assumption-note">${num(s.reach)} reached × ${s.assumed_lift} percentage-point assumed improvement. Assumes full participation. The assumed improvement requires an intervention evaluation.</p></div>`;
}
function dag() {
  return `<svg class="causal-dag" viewBox="0 0 520 185" role="img" aria-label="Hypothesized causal graph: entry background and unmeasured work, finances, and support affect enrollment intensity and retention"><defs><marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6" fill="#a7b891"/></marker></defs><path class="arrow" d="M220 40L115 90M295 40L413 90M145 110H365" marker-end="url(#arrowhead)"/><path class="arrow dashed" d="M220 157L115 130M295 157L413 130" marker-end="url(#arrowhead)"/><rect class="node" x="180" y="10" width="160" height="33" rx="6"/><text x="260" y="31" text-anchor="middle">Entry background</text><rect class="node" x="10" y="92" width="160" height="35" rx="6"/><text x="90" y="114" text-anchor="middle">Enrollment intensity</text><rect class="node" x="365" y="92" width="140" height="35" rx="6"/><text x="435" y="114" text-anchor="middle">Retention</text><rect x="165" y="150" width="190" height="32" fill="#fbf4e9" stroke="#e7d8be" rx="6"/><text x="260" y="170" text-anchor="middle">Work, finances & support</text><text x="267" y="103" text-anchor="middle" style="font-size:9px">Hypothesized link</text></svg>`;
}
function renderTrends() {
  const t = state.trends;
  return (
    heading(
      "Cohort analysis",
      "Trends",
      "Compare cohort outcomes and examine differences between student groups.",
      button("Export investigation", "export-trends", "download", "primary"),
    ) +
    filterBar() +
    (!t
      ? '<div class="page-loader"><span class="loading-mark"></span>Comparing cohorts and adjusting associations…</div>'
      : `<div class="trend-summary">${icon("trend")}<div><h2>Comparison limits</h2><p>These comparisons use adjacent entry cohorts. Unequal follow-up periods may affect the rates; verify outcome completeness before interpreting a change.</p></div></div><div class="section-heading"><div><h2>${t.signals.length ? "Largest cohort changes" : "Earliest cohort"}</h2><p>${t.signals.length ? "Up to three changes ranked by absolute percentage-point difference." : "The earliest cohort has no earlier cohort in this extract."}</p></div><span class="badge neutral">Observed differences</span></div><div class="signals-grid">${t.signals
          .slice(0, 3)
          .map(
            (s) =>
              `<article class="signal-card"><span class="badge ${s.direction === "down" ? "amber" : "neutral"}">${icon(s.direction === "down" ? "alert" : "trend")}${esc(s.category)}</span><h3>${esc(metricNames[s.metric])}</h3><div class="signal-value">${s.value > 0 ? "+" : ""}${fixed(s.value)}<span>pp</span></div><p>${esc(s.detail)}</p><button class="button text" data-action="signal" data-id="${s.id}">Inspect evidence ${icon("arrow")}</button></article>`,
          )
          .join(
            "",
          )}</div><section class="panel"><div class="panel-header"><div><h2>Full-time and part-time retention</h2><p>Compare rates, then account for measured background differences.</p></div><span class="badge amber">Causal effect not identified</span></div><div class="panel-body">${t.association.available ? associationPanel(t.association) : `<div class="empty-state"><h2>Comparison unavailable</h2><p>${esc(t.association.reason)}</p><p>Comparing enrollment groups requires both full-time and part-time records. The button below changes the population filter to All students and keeps the selected cohort.</p>${button("Compare both groups · all students", "all-population", "users")}</div>`}</div></section><div class="two-columns" style="margin-top:20px"><section class="panel"><div class="panel-header"><div><h2>Causal assumptions</h2><p>Proposed relationships for planning an evaluation</p></div></div><div class="panel-body">${dag()}<p class="table-footnote">Solid: candidate relationships involving observed variables. Dashed: unmeasured influences. First-term GPA may be downstream of intensity and is excluded from adjustment.</p></div></section><section class="panel"><div class="panel-header"><div><h2>Evaluation requirements</h2><p>Collect intervention and outcome data before estimating impact.</p></div></div><div class="panel-body"><div class="causal-item">${icon("check")}<div><strong>Define the intervention.</strong><br>Specify the intervention, eligible students, and outcome window.</div></div><div class="causal-item">${icon("check")}<div><strong>Record participation and timing.</strong><br>Collect participation, assignment, timing, and work or financial constraints.</div></div><div class="causal-item">${icon("check")}<div><strong>Select a comparison design.</strong><br>Plan a randomized or justified quasi-experimental pilot before estimating impact.</div></div>${button("Create outreach scenario", "models", "arrow", "soft")}</div></section></div><details class="disclosure"><summary>Methods, coverage, and uncertainty</summary><div class="disclosure-content"><p>${esc(t.association.method)}</p><ul>${[...t.methodology, ...t.association.limitations].map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div></details>`)
  );
}
function associationPanel(a) {
  const max = Math.max(Math.abs(a.raw_gap), Math.abs(a.adjusted_gap), 1) * 1.15;
  return `<div class="association-grid"><div>${[
    { label: "Unadjusted difference", value: a.raw_gap, ci: a.raw_ci, n: a.n },
    {
      label: "Adjusted association",
      value: a.adjusted_gap,
      ci: a.adjusted_ci,
      n: a.overlap_n,
    },
  ]
    .map(
      (r) =>
        `<div class="comparison-row"><div class="comparison-label"><span>${r.label}</span><strong>${r.value > 0 ? "+" : ""}${fixed(r.value)} pp</strong></div><div class="comparison-track"><span style="width:${(Math.abs(r.value) / max) * 100}%"></span></div><small>95% interval ${fixed(r.ci[0])} to ${fixed(r.ci[1])} pp · ${num(r.n)} distinct students</small></div>`,
    )
    .join(
      "",
    )}<div class="comparison-foot">Adjusted for entry cohort, age band, and entry type. ${fixed(a.coverage_pct)}% of known-intensity students fall in ${a.strata} shared strata. The raw and adjusted populations differ.</div></div><div class="causal-notes"><h3>Interpretation</h3><div class="causal-item">${icon("check")}<div><strong>Observed full-time retention: ${pct(a.full_time_rate)}.</strong><br>Part-time retention: ${pct(a.part_time_rate)}.</div></div><div class="causal-item">${icon("info")}<div>Adjustment includes measured background differences. Work, finances, and other unmeasured factors may still affect retention.</div></div><div class="causal-item">${icon("alert")}<div>Estimating the effect of changing enrollment intensity requires an evaluation design.</div></div></div></div>`;
}
function paperMock() {
  return `<div class="report-illustration" aria-hidden="true"><div class="paper-mock"><div class="paper-title"></div><div class="paper-line"></div><div class="paper-line"></div><div class="paper-line" style="width:75%"></div><div class="paper-chart"><span style="height:45%"></span><span style="height:80%"></span><span style="height:55%"></span><span style="height:95%"></span><span style="height:70%"></span></div><div class="paper-line"></div><div class="paper-line" style="width:65%"></div></div></div>`;
}
function renderReports() {
  return (
    heading(
      "Downloads",
      "Reports",
      "Download the selected evidence, model results, and scenario assumptions.",
    ) +
    filterBar() +
    `${state.custom ? `<div class="custom-banner"><span>${icon("grid")}Exporting custom view: <strong>${esc(state.custom.title)}</strong></span><button data-action="clear-view">Use all metrics</button></div>` : ""}<div class="report-grid"><article class="report-card">${paperMock()}<h2>Leadership brief</h2><p>Selected metrics, cohort comparisons, definitions, and follow-up questions.</p><div class="report-meta"><span>HTML · Print to PDF</span><span>Current filters</span></div>${button("Export brief", "export-brief", "download", "primary")}</article><article class="report-card">${paperMock()}<h2>Metric data</h2><p>Metric values, numerators, denominators, missing values, and definitions.</p><div class="report-meta"><span>CSV spreadsheet</span><span>Current filters</span></div>${button("Export CSV", "export-csv", "download")}</article><article class="report-card">${paperMock()}<h2>Model & scenario brief</h2><p>Historical evaluation, calibration limits, support bands, and the assumptions behind your latest pilot scenario.</p><div class="report-meta"><span>HTML · Print to PDF</span><span>Latest eligible cohort holdout</span></div>${button("Export analysis", "export-model", "download")}</article></div><section class="panel" style="margin-top:23px"><div class="panel-header"><div><h2>Report contents</h2><p>Reports include the selected filters, calculations, and source details.</p></div>${icon("shield")}</div><div class="panel-body report-contents"><div>${["Cohort and population filters", "Metric definitions and denominators", "Synthetic-data notice"].map((s) => `<div class="report-check">${icon("check")}${s}</div>`).join("")}</div><div>${["Unknown values and small-cell suppression", "Source filenames and provenance", "Stated model and scenario assumptions"].map((s) => `<div class="report-check">${icon("check")}${s}</div>`).join("")}</div></div></section><div class="section-heading"><div><h2>Saved dashboards</h2><p>Existing four-metric views remain in this browser. SQL chat results are separate.</p></div>${button("Explore in chat", "ask-build", "sparkles", "soft")}</div><section class="panel"><div class="panel-body">${savedViewsList()}</div></section>`
  );
}
function savedViewsList() {
  return state.saved.length
    ? `<div class="saved-list">${state.saved.map((v, i) => `<div class="saved-view"><div><strong>${esc(v.title)}</strong><p>${esc(scope(v.filters))} · ${v.metrics.length} metrics</p></div><button class="button" data-action="load-view" data-index="${i}">Open ${icon("arrow")}</button><button class="icon-button" data-action="delete-view" data-index="${i}" aria-label="Delete ${esc(v.title)}">${icon("trash")}</button></div>`).join("")}</div>`
    : '<div class="empty-state"><h2>No saved dashboards</h2><p>Existing four-metric views appear here. Explore custom queries in chat without creating a saved dashboard.</p></div>';
}
function renderSources() {
  const d = state.dashboard;
  return (
    heading(
      "Data documentation",
      "Data and definitions",
      "Source files, quality checks, and metric definitions.",
      button("Answer validation", "trust", "shield"),
    ) +
    filterBar() +
    normalizedModelPanel() +
    sharedDocumentation() +
    `<section class="panel"><div class="panel-header"><div><h2>PDP source data</h2><p>Synthetic data · ${num(d.meta.cohorts.length)} entry cohorts · ${esc(d.meta.cohorts.join(", "))}</p></div><span class="badge neutral">${d.meta.dataset.origin === "workbench" ? "Synced from Workbench" : "Starter data"}</span></div><div class="panel-body"><p>Loaded run: <code>${esc(d.meta.dataset.run_id)}</code>${d.meta.dataset.synced_at ? ` · Synced ${esc(d.meta.dataset.synced_at)}. Uploader attested that these files contain only synthetic data.` : ""}</p><div class="source-stats"><div class="source-stat"><strong>${num(d.meta.cohort_rows)}</strong><span>Student-cohort records</span></div><div class="source-stat"><strong>${num(d.meta.unique_students)}</strong><span>Distinct student IDs</span></div><div class="source-stat"><strong>${num(d.meta.course_rows)}</strong><span>Loaded course enrollments</span></div></div><p class="small muted">Counts describe the currently loaded database. Source-file counts below may include rows held back by validation.</p><div class="quality-list">${d.quality.map((q) => `<div class="quality-row">${icon(q.severity === "warning" ? "alert" : "info")}<div><h3>${esc(q.label)}</h3><p>${esc(q.detail)}</p></div><span class="badge ${q.severity === "warning" ? "amber" : "neutral"}">${num(q.count)} records</span></div>`).join("")}</div><p class="table-footnote">Quality counts reflect the selected filters. Unknown values remain in the source data.</p></div></section><div class="section-heading"><div><h2>Metric definitions</h2><p>Open any dashboard metric to inspect its source, calculation, and uncertainty.</p></div></div><section class="panel"><div class="panel-body">${d.metrics.map((m) => `<div class="definition-card"><h3>${esc(m.label)}</h3><p>${esc(m.definition)}</p><code>${esc(m.column)}</code></div>`).join("")}</div></section><details class="disclosure"><summary>Source files and data limits</summary><div class="disclosure-content"><p>${esc(d.meta.follow_up)}</p><p>Join course and cohort data on both Student_GUID and Cohort. Students may enter more than one cohort; counting student-cohort records and counting distinct students are different operations.</p>${d.meta.provenance.map((p) => `<div class="provenance" style="margin-top:15px"><strong>${esc(p.file)}</strong> · ${num(p.rows)} records<br>SHA-256: <code>${esc(p.sha256)}</code></div>`).join("")}<p style="margin-top:15px">The legacy first-generation definition needs clarification, so first-generation comparisons are not offered. No real institution performance, peer rankings, live student alerts, or intervention effects can be inferred from this extract.</p></div></details>`
  );
}
// Inspect the shared schema and composite joins without maintaining a second ER model.
function normalizedModelPanel() {
  const docs = state.definitions;
  if (!docs?.model) return "";
  const tables = Object.values(docs.model.tables);
  return `<section class="panel normalized-model"><div class="panel-header"><div><h2>Normalized data model</h2><p>The starter’s ER model: ${tables.length} tables, their keys, and the meaning of each record.</p></div><span class="badge neutral">Shared schema</span></div><div class="panel-body"><p class="small muted">Read directly from the starter’s schema and MCP metadata helper. The Mermaid file documents this same contract. Definitions cover the full model; chat queries use scoped views rather than unrestricted table access.</p><div class="model-table-list">${tables.map(t => `<details><summary><code>${esc(t.name)}</code><span>${t.columns.length} fields</span></summary><div class="model-table-body"><p>One record per ${esc(t.description || t.name)}</p><p><strong>Primary key:</strong> <code>${esc(t.primary_key.join(" + ") || "None declared")}</code></p>${t.foreign_keys.length ? `<h3>Relationships</h3><ul>${t.foreign_keys.map(k => `<li><code>${esc(k.columns.join(" + "))}</code> → <code>${esc(k.references_table)} (${esc(k.references_columns.join(" + "))})</code></li>`).join("")}</ul>` : ""}<div class="table-scroll"><table class="data-table"><thead><tr><th>Field</th><th>Stored type</th><th>Missing values</th></tr></thead><tbody>${t.columns.map(c => `<tr><td><code>${esc(c.name)}</code>${c.primary_key ? ' <span class="badge neutral">Key</span>' : ""}</td><td>${esc(c.model_type)}</td><td>${c.nullable ? "Allowed" : "Required"}</td></tr>`).join("")}</tbody></table></div></div></details>`).join("")}</div><details class="disclosure"><summary>Original Mermaid ER diagram source</summary><div class="disclosure-content"><p class="small">${esc(docs.model.diagram.path)}</p><pre class="model-diagram-source">${esc(docs.diagram_source)}</pre><p class="provenance">SHA-256: ${esc(docs.model.diagram.sha256)}</p></div></details><p class="table-footnote">Chat supports cohort records, course records with academic terms, and student attributes such as housing. Attribute terms are not entry cohorts; missing housing records do not mean “no housing.” Institution events and loader provenance are documented, not student outcomes.</p></div></section>`;
}
// Dictionary and quality findings come from the starter, not copied descriptions.
function sharedDocumentation() {
  const docs = state.definitions;
  if (!docs) return '<div class="page-loader">Loading shared definitions…</div>';
  return `<div class="method-notice">${icon("database")}<div><strong>Normalized PDP model</strong><p>Loaded ${esc(docs.load.finished_at || docs.load.started_at)}. Corrections and validation run before analytics; the original files are unchanged.</p></div></div><details class="disclosure"><summary>Shared column dictionary · ${docs.dictionary.length} fields</summary><div class="disclosure-content dictionary-list">${docs.dictionary.map(e => `<details><summary><code>${esc(e.table)}.${esc(e.column)}</code></summary><p>${esc(e.description)}</p><p class="small">Stored type: ${esc(e.stored?.type)} · ${e.stored?.nullable ? "Can be blank" : "Required"}</p>${e.dictionary_values?.length ? `<p class="small">${e.dictionary_values.map(v => `${esc(v.code)}: ${esc(v.meaning)}`).join("; ")}</p>` : ""}<p class="provenance">${e.sources.map(s => `${esc(s.source_file)} / ${esc(s.source_column)}`).join("; ")}</p></details>`).join("")}</div></details><details class="disclosure"><summary>Published data quality findings · ${docs.findings.length} issues</summary><div class="disclosure-content"><p>${esc(docs.quality_scope)}</p><div class="quality-list">${docs.findings.map(f => `<div class="quality-row">${icon("info")}<div><h3>${esc(f.id)} · ${esc(f.finding)}</h3><p>${esc(f.impact)}</p><p><strong>Recommended action:</strong> ${esc(f.proposed_fix)}</p><code>${esc(f.file)} / ${esc(f.columns)}</code></div><span class="badge neutral">${esc(f.count)}</span></div>`).join("")}</div></div></details>`;
}
function modal(title, body) {
  const el = document.querySelector("#detail-dialog");
  el.classList.remove("report-dialog");
  el.innerHTML = `<div class="dialog-header"><h2 id="dialog-title">${esc(title)}</h2><button class="icon-button" data-action="close-dialog" aria-label="Close dialog">${icon("close")}</button></div><div class="dialog-body">${body}</div>`;
  if (!el.open) el.showModal();
}
function closeModal() {
  document.querySelector("#detail-dialog").close();
}
function trustDialog() {
  modal(
    "Answer validation",
    `<span class="badge">${icon("shield")}Generated SQL · reviewed and checked</span><p>Every question requires the provider. Configure DO_MODEL_INFERENCE_KEY and a distinct SANDBOX_VERIFY_MODEL in the server environment, never in the browser.</p><h3>1. Generate and review SQL</h3><p>A model generates SQL for averages, intersections, and custom formulas. A different model reviews it. Server schema and domain checks and bounded correction attempts constrain execution; none guarantee semantic or numerical correctness.</p><h3>2. Respect the UI scope</h3><p>SQL views enforce the active UI cohort and population. SQL may narrow this scope further. Change the UI filters to broaden it. Inspect the exact SQL, model identities, and check history beside each response; check feedback is not query output.</p><h3>3. Inspect results and units</h3><p>Tables and charts contain server-calculated query results. Missing and suppressed values are not zero. Check denominators, join grain, missing-value treatment, and formulas. DFW uses enrollments, not students; a sum of credit ratios may be fractional.</p><h3>4. Keep preset analyses separate</h3><p>Modeling and the Equity gaps finder remain separate preset analyses. Chat can explore raw differences, but does not inherit their intervals or q-values unless explicitly computed. Existing saved dashboards and evidence reports retain four core metrics; SQL chat charts do not create saved dashboard views.</p><p style="margin-top:16px">Review the interpretation and results independently. Source completeness and causal assumptions require separate review. All data is synthetic.</p>`,
  );
}
function metricDialog(id) {
  const m = state.dashboard.metrics.find((m) => m.id === id);
  if (!m) return;
  modal(
    m.label,
    `<span class="badge">Observed metric</span><div class="metric-value">${pct(m.value)}</div><p>${esc(scope())}</p><div class="definition-math">${num(m.numerator)} qualifying records ÷ ${num(m.denominator)} eligible records × 100</div><h3>Definition</h3><p>${esc(m.definition)}</p><h3>Missing values & uncertainty</h3><p>${num(m.missing)} missing or unknown values. ${m.suppressed ? "Suppressed because the eligible group has fewer than 20 records." : `95% Wilson interval: ${pct(m.interval[0])}–${pct(m.interval[1])}.`}</p><h3>Source columns</h3><code>${esc(m.column)}</code><p class="provenance" style="margin-top:14px">${esc(m.source)}</p><p class="small" style="margin-top:14px">${esc(state.dashboard.meta.follow_up)} This rate describes synthetic data.</p>`,
  );
}
function citationsDialog(index) {
  const m = state.messages[index];
  if (m.status === "verified" && m.query) {
    modal("Where this came from", `<div class="chat-evidence-details">${renderChatEvidence(m)}${renderChatQuery(m.query)}</div>`);
    return;
  }
  const scopePrefix = m.query ? "UI scope (SQL may further restrict): " : "";
  modal(
    "Answer sources and calculations",
    `<span class="badge ${m.validation?.passed ? "" : "amber"}">${icon("shield")}${m.validation?.passed ? "Server checks passed" : "Scope checks"}</span><p>These checks do not guarantee interpretation or numerical correctness. Review SQL, scope, and source definitions.</p><p>${scopePrefix}${esc(scope(m.filters))}</p>${(m.citations || []).map((c) => `<h3>${esc(c.label)}</h3><p>${esc(c.definition || "Source-derived result")}</p>${c.denominator != null ? `<div class="definition-math">${esc(c.numerator ?? "Unavailable")} / ${esc(c.denominator)} eligible units (see definition)${c.missing != null ? ` · ${num(c.missing)} missing` : ""}</div>` : ""}<p>${scopePrefix}${esc(scope(c.filters || m.filters))}</p><code>${esc(Array.isArray(c.columns) ? c.columns.join(" · ") : c.columns)}</code><p class="provenance">${esc(c.source)}</p>`).join("")}<h3>Validation checks</h3><ul>${(m.validation?.checks || []).map((c) => `<li>${esc(typeof c === "string" ? c : JSON.stringify(c))}</li>`).join("")}</ul>${m.query ? renderChatQuery(m.query) : `<details><summary>View query details</summary><pre>${esc(JSON.stringify(m.plan, null, 2))}</pre></details>`}`,
  );
}
function modelDialog() {
  if (!state.model) return;
  const m = state.model;
  modal(
    "First-term retention model card",
    `<span class="badge amber">Historical model · requires validation</span><p>${esc(m.description)}</p><h3>Target and timing</h3><p>${esc(m.target)} ${esc(m.prediction_time)}</p><h3>Evaluation design</h3><p>Training: ${num(m.training.rows)} records; validation: ${num(m.validation.rows)}; held-out test: ${num(m.test.rows)}. No student IDs overlap across the three sets.</p><h3>Held-out performance</h3><p>AUC ${fixed(m.test.auc, 3)}; Brier ${fixed(m.test.brier, 3)} vs ${fixed(m.test.baseline_brier, 3)} for a training-rate baseline. Predicted ${pct(m.test.predicted_retention)} vs observed ${pct(m.test.observed_retention)} retention.</p><h3>Predictors</h3><p>${m.predictor_columns.map((c) => `<code>${esc(c)}</code>`).join(" ")}</p><h3>Limitations</h3><ul>${m.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>${button("Export model and scenario brief", "export-model", "download")}`,
  );
}
function signalDialog(id) {
  const s = state.trends?.signals.find((s) => s.id === id);
  if (!s) return;
  modal(
    s.title,
    `<span class="badge neutral">${esc(s.evidence)}</span><p>${esc(s.detail)}</p><div class="definition-math">${pct(s.current)} − ${pct(s.previous)} = ${fixed(s.value)} percentage points</div><p>Current eligible records: ${num(s.n)} · Previous eligible records: ${num(s.previous_n)}</p><p>Approximate 95% interval: ${fixed(s.interval[0])} to ${fixed(s.interval[1])} pp.</p><h3>Interpretation limits</h3><p>${esc(s.caution)}</p><p>These exploratory comparisons are not corrected for multiple testing.</p><h3>Next step</h3><p>Verify the completeness of both cohorts and compare equivalent outcome windows with your institutional research team.</p><p class="provenance" style="margin-top:15px">${esc(s.source)}</p>`,
  );
}
let chatVersion = 0;
let filterVersion = 0;
async function sendQuestion(question, retry = null) {
  question = question.trim();
  if (!question || state.chatPending) return;
  const version = ++chatVersion,
    filters = { ...state.filters };
  const sameRetryScope = retry && Object.keys(filters).every((key) => retry.filters?.[key] === filters[key]);
  const context = retry ? (sameRetryScope ? retry.retryContext : null) : state.chatContext;
  const currentFilterVersion = filterVersion;
  state.chatDraft = "";
  state.messages.push({ role: "user", text: question });
  state.chatPending = true;
  renderPage();
  try {
    const result = await api("/api/chat", {
      question,
      filters,
      context,
      concise: state.chatConcise,
    });
    if (version !== chatVersion) return;
    const df = result.dashboard;
    if (df && !validView(df))
      throw Error("The returned dashboard did not pass local validation.");
    if (currentFilterVersion === filterVersion && qs(filters) === qs(state.filters))
      state.chatContext = result.context ?? null;
    state.messages.push({
      ...result,
      role: "assistant",
      filters: df?.filters || result.plan?.filters || filters,
    });
  } catch (error) {
    if (version === chatVersion) {
      state.chatDraft = question;
      if (error.status === 503) void checkConnection();
      state.messages.push({
        role: "assistant",
        status: "error",
        answer: error.message,
        query: error.details?.query,
        engine: error.details?.engine,
        retryQuestion: question,
        retryContext: context,
        filters,
        citations: [],
      });
    }
  } finally {
    if (version === chatVersion) {
      state.chatPending = false;
      renderPage();
      document.querySelector("#chat-question")?.focus();
    }
  }
}
function scrollChat() {
  const feed = document.querySelector("#chat-feed");
  if (feed && state.messages.length) feed.scrollTop = feed.scrollHeight;
}
async function loadData() {
  const version = ++requestVersion;
  state.error = null;
  try {
    const [data, shared] = await Promise.all([api(`/api/dashboard?${qs()}`), api(`/api/measures?${qs()}`)]);
    if (version !== requestVersion) return;
    state.dashboard = data;
    state.sharedMeasures = shared;
    state.filters = { ...data.filters };
    state.loading = false;
    renderPage();
    await loadRouteData();
  } catch (error) {
    if (version === requestVersion) {
      state.loading = false;
      state.error = error.message;
      renderPage();
    }
  }
}
async function loadRouteData() {
  const route = state.route;
  try {
    if (route === "students") await studentWorkspace.load(state.filters);
    if (route === "sources" && !state.definitions) {
      state.definitions = await api("/api/definitions");
    }
    if (route === "gaps") {
      const query = `${qs()}&measure=${state.gapMeasure}&breakdown=${encodeURIComponent(state.gapBreakdown)}`;
      const data = await api(`/api/gaps?${query}`);
      if (query === `${qs()}&measure=${state.gapMeasure}&breakdown=${encodeURIComponent(state.gapBreakdown)}`) state.gaps = data;
    }
    if (route === "models" && !state.model) {
      state.model = await api("/api/model");
      state.scenario = await api("/api/scenario", state.scenarioInput);
    }
    if (route === "trends") {
      const filters = qs();
      const data = await api(`/api/trends?${filters}`);
      if (filters === qs()) state.trends = data;
    }
    if (state.route === route) renderPage();
  } catch (error) {
    if (state.route === route) {
      state.error = error.message;
      renderPage();
    }
  }
}
function navigate(route) {
  if (state.route === route) {
    renderPage();
    return;
  }
  location.hash = route;
}
async function updateFilters(newFilters) {
  filterVersion++;
  state.chatContext = null;
  state.filters = { ...state.filters, ...newFilters };
  state.trends = null;
  state.gaps = null;
  if (state.custom) {
    state.custom = { ...state.custom, filters: { ...state.filters } };
    state.custom.title = `${popNames[state.filters.population]} · ${state.custom.metrics.map((m) => (m === "momentum" ? `${state.filters.threshold}-credit momentum` : metricNames[m])).join(" & ")}`;
  }
  state.loading = true;
  renderPage();
  await loadData();
}
async function openView(view) {
  if (!validView(view)) {
    toast("This saved view has an unsupported configuration.");
    return;
  }
  closeModal();
  const normalized = {
    title: view.title,
    metrics: [...new Set(view.metrics)],
    filters: {
      cohort: view.filters.cohort,
      population: view.filters.population,
      threshold: Number(view.filters.threshold),
    },
  };
  state.custom = normalized;
  filterVersion++;
  state.chatContext = null;
  state.filters = { ...normalized.filters };
  state.chart = normalized.metrics[0];
  state.trends = null;
  state.gaps = null;
  state.route = "evidence";
  history.replaceState(null, "", "#evidence");
  state.loading = true;
  shell();
  await loadData();
  toast("Dashboard opened with the selected filters.");
}
function saveView(specification = state.custom) {
  if (!specification) return;
  const view = { ...specification, filters: { ...state.filters } };
  state.saved = state.saved.filter(
    (v) => JSON.stringify(v) !== JSON.stringify(view),
  );
  state.saved.unshift(view);
  state.saved = state.saved.slice(0, 12);
  try {
    localStorage.setItem(datasetStorageKey("waypoint-views"), JSON.stringify(state.saved));
    toast("View saved in this browser.");
  } catch {
    toast(
      "Browser storage is unavailable. This view is only saved for this session.",
    );
  }
}
function setExportPending(value) {
  state.exportPending = value;
  document.querySelectorAll('button[data-action^="export-"]').forEach((el) => {
    el.disabled = value;
    el.setAttribute("aria-busy", String(value));
  });
}

function exportError(error, kind) {
  if (["connection", "timeout", "unexpected_response"].includes(error.code))
    setConnection("offline");
  modal(
    "Export failed",
    `<div class="export-error" role="alert"><p>${esc(error.message)}</p><p>No report was downloaded.</p><button class="button primary" data-action="retry-export" data-kind="${kind}">${icon("refresh")}Retry export</button></div>`,
  );
}

let reportURL = null;
function showReport(report, reportScope) {
  if (reportURL) URL.revokeObjectURL(reportURL);
  reportURL = URL.createObjectURL(
    new Blob([report.content], { type: report.type }),
  );
  modal(
    "Report ready",
    `<p>${esc(reportScope)}</p><div class="export-actions"><a id="report-download" class="button primary" href="${reportURL}" download="${esc(report.name)}">${icon("download")}Download ${report.format.toUpperCase()}</a>${report.format === "html" ? `<button class="button" data-action="print-report">${icon("report")}Print / Save as PDF</button>` : ""}</div><p class="export-note">${report.format === "html" ? "Download the HTML file or print the report as a PDF." : "Download the CSV file to open it in a spreadsheet."}</p>${report.format === "html" ? '<iframe id="report-preview" class="report-preview" title="Report preview" sandbox="allow-same-origin allow-modals"></iframe>' : `<pre class="csv-preview" aria-label="CSV preview">${esc(report.content)}</pre>`}`,
  );
  document.querySelector("#detail-dialog").classList.add("report-dialog");
  const frame = document.querySelector("#report-preview");
  if (frame)
    frame.srcdoc = report.content.replace(
      /<button\b[^>]*onclick=[^>]*>[^<]*<\/button>/gi,
      "",
    );
}

async function exportEvidence(format) {
  if (state.exportPending) return;
  setExportPending(true);
  const filters = { ...state.filters };
  const query = new URLSearchParams(filters);
  query.set("format", format);
  if (state.custom) query.set("metrics", state.custom.metrics.join(","));
  try {
    const report = await requestReport(`/api/report?${query}`, format);
    setConnection("connected");
    showReport(report, scope(filters));
  } catch (error) {
    exportError(error, format);
  } finally {
    setExportPending(false);
  }
}
function reportDocument(title, subtitle, body) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)} | AASCU</title><style>body{font:14px/1.75 system-ui,sans-serif;color:#171717;max-width:900px;margin:45px auto;padding:0 25px}h1{font-size:32px;letter-spacing:-1px}h2{font-size:20px;margin-top:30px}p{color:#666}.brand{font-weight:700;color:#171717}.notice{padding:15px;background:#fafafa;border:1px solid #e5e5e5;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid #e5e5e5}code{font-size:11px;overflow-wrap:anywhere}button{float:right;padding:10px 15px;border:1px solid #e5e5e5;background:#171717;color:white;border-radius:7px;cursor:pointer}footer{margin-top:40px;font-size:11px;color:#666}@media print{button{display:none}body{margin:0;max-width:none}table{break-inside:avoid}}</style></head><body><button onclick="window.print()">Print / Save as PDF</button><div class="brand">AASCU · Institutional analytics</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p><div class="notice">This report uses synthetic PDP data. It contains no findings about real institutions.</div>${body}<h2>Source provenance</h2>${state.dashboard.meta.provenance.map((p) => `<p>${esc(p.file)} · ${num(p.rows)} records<br><code>SHA-256 ${esc(p.sha256)}</code></p>`).join("")}<footer>Generated ${esc(new Date().toISOString())}. Source extraction date and outcome maturity are not supplied.</footer></body></html>`;
}
async function exportModel() {
  if (state.exportPending) return;
  setExportPending(true);
  try {
    if (!state.model) state.model = await api("/api/model");
    if (state.model.available === false) throw new Error(state.model.reason);
    if (!state.scenario)
      state.scenario = await api("/api/scenario", state.scenarioInput);
    const m = state.model,
      s = state.scenario;
    const html = reportDocument(
      "Model & scenario brief",
      `Fixed ${m.test.cohort} held-out cohort · independent of dashboard filters`,
      `<h2>Historical retention evaluation</h2><p>${esc(m.description)} ${esc(m.prediction_time)}</p><table><tr><th>Test records</th><th>AUC</th><th>Brier / baseline</th><th>Calibration gap</th></tr><tr><td>${num(m.test.rows)}</td><td>${fixed(m.test.auc, 3)}</td><td>${fixed(m.test.brier, 3)} / ${fixed(m.test.baseline_brier, 3)}</td><td>${fixed(m.test.calibration_gap)} pp</td></tr></table><p>Predicted retention ${pct(m.test.predicted_retention)}; observed ${pct(m.test.observed_retention)}. This historical model is not ready for student decisions. Follow-up completeness and calibration need review before real-world use.</p><h2>Last calculated pilot scenario</h2><p>${num(s.reach)} students reached from ${s.target === "high" ? "the higher predicted nonretention band (historical)" : `all ${esc(m.test.cohort)} test records`}; ${money(s.cost)} estimated cost; ${money(s.budget_remaining)} budget remaining. Staff capacity ${num(s.capacity)}, budget ${money(s.budget)}, cost per student ${money(s.cost_per_student)}.</p><p><strong>${fixed(s.expected_additional_retained)} additional retained students</strong> under a user-assumed ${s.assumed_lift} percentage-point improvement. The assumed improvement requires evaluation.</p><ul>${s.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul><h2>Method & limitations</h2><ul>${[...m.methodology, ...m.limitations].map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`,
    );
    showReport(
      {
        content: html,
        name: "aascu-model-scenario.html",
        type: "text/html; charset=utf-8",
        format: "html",
      },
      `${m.test.cohort} test cohort and last calculated scenario`,
    );
  } catch (error) {
    exportError(error, "model");
  } finally {
    setExportPending(false);
  }
}
async function exportTrends() {
  if (state.exportPending) return;
  setExportPending(true);
  const reportFilters = { ...state.filters };
  const reportScope = scope(reportFilters);
  const cachedTrends = state.trends;
  try {
    const t = cachedTrends || (await api(`/api/trends?${qs(reportFilters)}`)),
      a = t.association;
    const html = reportDocument(
      "Trend investigation brief",
      reportScope,
      `<h2>Adjacent-cohort signals</h2>${t.signals.length ? `<table><tr><th>Metric</th><th>Comparison</th><th>Change</th><th>95% interval</th></tr>${t.signals.map((s) => `<tr><td>${esc(metricNames[s.metric])}</td><td>${esc(s.previous_cohort)} → ${esc(s.current_cohort)}</td><td>${fixed(s.value)} pp</td><td>${fixed(s.interval[0])} to ${fixed(s.interval[1])}</td></tr>`).join("")}</table>` : "<p>No earlier comparison cohort is available.</p>"}<h2>Full-time vs part-time retention</h2>${a.available ? `<p>Raw gap ${fixed(a.raw_gap)} pp (95% CI ${fixed(a.raw_ci[0])}–${fixed(a.raw_ci[1])}); adjusted association ${fixed(a.adjusted_gap)} pp (95% CI ${fixed(a.adjusted_ci[0])}–${fixed(a.adjusted_ci[1])}). Overlap coverage ${fixed(a.coverage_pct)}%, ${num(a.overlap_n)} students in ${a.strata} strata.</p>` : `<p>${esc(a.reason)}</p>`}<p>${esc(a.method)} Causal identification requires a suitable evaluation design.</p><h2>Recommended next step</h2><p>${esc(a.next_step)}</p><h2>Method & limitations</h2><ul>${[...t.methodology, ...a.limitations].map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`,
    );
    showReport(
      {
        content: html,
        name: "aascu-trend-investigation.html",
        type: "text/html; charset=utf-8",
        format: "html",
      },
      reportScope,
    );
  } catch (error) {
    exportError(error, "trends");
  } finally {
    setExportPending(false);
  }
}
document.addEventListener("click", async (event) => {
  const studentAction = event.target.closest("[data-student-action]");
  if (studentAction) { await studentWorkspace.handleClick(studentAction); return; }
  if (event.target.closest(".skip-link")) {
    event.preventDefault();
    document.querySelector("#main")?.focus();
    return;
  }
  const el = event.target.closest("[data-action]");
  if (event.target.closest(".navigation a, .brand, .sidebar-bottom>a"))
    document.body.classList.remove("nav-open");
  if (!el) return;
  const action = el.dataset.action;
  if (["sources", "models", "trends", "reports", "evidence", "students"].includes(action)) {
    closeModal();
    if (action === "students") {
      studentWorkspace.reset();
      if (state.route === "students") await studentWorkspace.load(state.filters);
    }
    navigate(action);
    return;
  }
  switch (action) {
    case "start-tutorial":
      tutorialOriginalAssistant = state.assistantOpen;
      showTutorial(0);
      break;
    case "close-tutorial": closeTutorial(); break;
    case "tutorial-back": if (tutorialStep > 0) showTutorial(tutorialStep - 1); break;
    case "tutorial-next":
      if (tutorialStep === null) break;
      if (tutorialStep === tutorialSteps.length - 1) closeTutorial();
      else showTutorial(tutorialStep + 1);
      break;
    case "explore-transfers":
      studentWorkspace.reset();
      studentWorkspace.setEntryType("transfer");
      navigate("students");
      if (state.route === "students") await studentWorkspace.load(state.filters);
      break;
    case "explore-adults":
      await updateFilters({ population: "adult" });
      navigate("evidence");
      break;
    case "compare-intensity":
      await updateFilters({ population: "all" });
      navigate("trends");
      toast("Comparison includes both groups. Population changed to All students; cohort retained.");
      break;
    case "student-group":
      if (["full-time", "part-time"].includes(el.dataset.population)) {
        studentWorkspace.reset();
        await updateFilters({ population: el.dataset.population });
        navigate("students");
      }
      break;
    case "save-current-view":
      saveView(state.custom || { title: `${popNames[state.filters.population]} · ${state.filters.cohort === "all" ? "All entry cohorts" : state.filters.cohort}`, metrics: Object.keys(metricNames), filters: { ...state.filters } });
      break;
    case "menu":
      if (innerWidth < 900) {
        document.body.classList.toggle("nav-open");
      } else {
        state.sidebarCollapsed = !state.sidebarCollapsed;
        document.body.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
      }
      syncNavigation();
      break;
    case "theme":
      state.dark = !state.dark;
      document.documentElement.classList.toggle("dark", state.dark);
      el.setAttribute("aria-pressed", state.dark);
      break;
    case "toggle-assistant":
      state.assistantOpen = !state.assistantOpen;
      document.querySelector(".assistant-dock").hidden = !state.assistantOpen;
      document.body.classList.toggle("assistant-open", state.assistantOpen);
      document.querySelector('.topbar [data-action="toggle-assistant"]').setAttribute("aria-expanded", state.assistantOpen);
      if (state.assistantOpen) document.querySelector("#chat-question")?.focus();
      else document.querySelector('.topbar [data-action="toggle-assistant"]').focus();
      break;
    case "menu-close":
      document.body.classList.remove("nav-open");
      syncNavigation();
      break;
    case "close-dialog":
      closeModal();
      break;
    case "trust":
      trustDialog();
      break;
    case "help":
      modal(
        "About AASCU",
        `<p>AASCU explores synthetic PDP data.</p><h3>SQL evidence assistant</h3><p>Ask for average GPA or earned credits, intersect race and enrollment groups, or describe a custom formula. A generator model writes SQL; a different model reviews it with server schema/domain checks and bounded corrections. Inspect exact SQL, check history, and results. Review is not a guarantee of accuracy.</p><p>SQL views enforce the active UI cohort and population, and queries may narrow them further. To broaden scope, change the UI filters. Configure DO_MODEL_INFERENCE_KEY and a distinct SANDBOX_VERIFY_MODEL server-side; HTTP reachability is separate from provider availability.</p><h3>Preset analyses and saved views</h3><p>Modeling and Equity gaps remain separate analyses. Raw SQL group differences do not automatically include shared intervals or q-values. Existing saved dashboards and evidence exports keep four core metrics; chat results are not saved dashboard specifications.</p>`,
      );
      break;
    case "metric":
      metricDialog(el.dataset.id);
      break;
    case "chart":
      state.chart = el.dataset.metric;
      renderPage();
      break;
    case "cohort-point":
      await updateFilters({ cohort: el.dataset.cohort });
      break;
    case "reset-filters":
      await updateFilters({ cohort: "all", population: "all", threshold: 24 });
      break;
    case "all-population":
      await updateFilters({ population: "all" });
      break;
    case "suggest":
      await sendQuestion(el.dataset.question);
      break;
    case "retry-chat": {
      const failed = state.messages[Number(el.dataset.index)];
      if (failed?.retryQuestion) await sendQuestion(failed.retryQuestion, failed);
      break;
    }
    case "toggle-chat-concise":
      state.chatConcise = !state.chatConcise;
      document.querySelector(".assistant-dock").innerHTML = chatPanel();
      document.querySelector('[data-action="toggle-chat-concise"]')?.focus();
      break;
    case "toggle-chat-details":
      state.chatDetails = !state.chatDetails;
      document.querySelector(".assistant-dock").innerHTML = chatPanel();
      document.querySelector('[data-action="toggle-chat-details"]')?.focus();
      break;
    case "clear-chat":
      if (state.chatPending) break;
      chatVersion++;
      state.messages = [];
      state.chatContext = null;
      state.chatDraft = "";
      state.chatPending = false;
      renderPage();
      break;
    case "citations":
      citationsDialog(Number(el.dataset.index));
      break;
    case "chat-chart-export": {
      const message = state.messages[Number(el.dataset.index)];
      try {
        const report = buildChatChartReport(message, Number(el.dataset.chart), el.dataset.format);
        showReport(report, `UI scope (SQL may further restrict): ${scope(message.filters)}`);
      } catch (error) {
        modal("Chart export unavailable", `<p>${esc(error.message)}</p>`);
      }
      break;
    }
    case "signal":
      signalDialog(el.dataset.id);
      break;
    case "model-card":
      modelDialog();
      break;
    case "open-dashboard":
      await openView(state.messages[Number(el.dataset.index)].dashboard);
      break;
    case "save-view":
      saveView();
      break;
    case "clear-view":
      state.custom = null;
      state.chart = "retention";
      renderPage();
      break;
    case "saved-views":
      modal(
        "Saved dashboard views",
        `<p>Views are stored only in this browser.</p>${savedViewsList()}`,
      );
      break;
    case "load-view":
      await openView(state.saved[Number(el.dataset.index)]);
      break;
    case "delete-view":
      state.saved.splice(Number(el.dataset.index), 1);
      try {
        localStorage.setItem(datasetStorageKey("waypoint-views"), JSON.stringify(state.saved));
      } catch {}
      if (document.querySelector("#detail-dialog").open)
        modal("Saved dashboard views", savedViewsList());
      else renderPage();
      toast("Saved view removed.");
      break;
    case "ask-build":
      state.assistantOpen = true;
      navigate("evidence");
      setTimeout(() => {
        document.querySelector(".assistant-dock").hidden = false;
        document.body.classList.add("assistant-open");
        document.querySelector('.topbar [data-action="toggle-assistant"]').setAttribute("aria-expanded", "true");
        const input = document.querySelector("#chat-question");
        if (input) {
          state.chatDraft = "Chart retention and credit momentum";
          input.value = state.chatDraft;
          input.focus();
          input.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      }, 100);
      break;
    case "export-brief":
      await exportEvidence("html");
      break;
    case "export-csv":
      await exportEvidence("csv");
      break;
    case "export-model":
      await exportModel();
      break;
    case "export-trends":
      await exportTrends();
      break;
    case "reconnect":
      await checkConnection();
      if (state.connection === "connected") {
        state.error = null;
        await loadData();
        toast("Server connected.");
      } else
        toast(
          "The server is still unavailable. Start npm run dev in demo, then reconnect.",
        );
      break;
    case "print-report": {
      const frame = document.querySelector("#report-preview");
      if (frame) {
        frame.contentWindow.focus();
        frame.contentWindow.print();
      }
      break;
    }
    case "retry-export":
      closeModal();
      if (el.dataset.kind === "model") await exportModel();
      else if (el.dataset.kind === "trends") await exportTrends();
      else await exportEvidence(el.dataset.kind);
      break;
    case "retry":
      state.loading = true;
      state.error = null;
      renderPage();
      await loadData();
      break;
  }
});
document.addEventListener("change", (event) => {
  if (event.target.matches("[data-gap]")) {
    state[event.target.dataset.gap === "measure" ? "gapMeasure" : "gapBreakdown"] = event.target.value;
    state.gaps = null;
    renderPage();
    loadRouteData();
  }
  if (event.target.matches("[data-filter]"))
    updateFilters({
      [event.target.dataset.filter]:
        event.target.dataset.filter === "threshold"
          ? Number(event.target.value)
          : event.target.value,
    });
});
document.addEventListener("input", (event) => {
  if (event.target.id === "chat-question") state.chatDraft = event.target.value;
  if (event.target.closest("#scenario-form")) {
    const form = document.querySelector("#scenario-form");
    state.scenarioDirty = true;
    state.scenarioInput = {
      capacity: Number(form.capacity.value),
      assumed_lift: Number(form.assumed_lift.value),
      budget: Number(form.budget.value),
      cost_per_student: Number(form.cost_per_student.value),
      target: form.target.value,
    };
    document.querySelector("#capacity-output").textContent = num(
      state.scenarioInput.capacity,
    );
    document.querySelector("#assumed-lift-output").textContent =
      `${state.scenarioInput.assumed_lift} pp`;
    document.querySelector("#scenario-dirty").textContent =
      "Inputs changed. Run to update the result.";
    document.querySelector("#scenario-result").classList.add("stale-result");
  }
});
document.addEventListener("submit", async (event) => {
  if (event.target.matches("form[data-student-form]")) { await studentWorkspace.handleSubmit(event); return; }
  if (event.target.id === "chat-form") {
    event.preventDefault();
    await sendQuestion(document.querySelector("#chat-question").value);
  }
  if (event.target.id === "scenario-form") {
    event.preventDefault();
    const submit = event.target.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      state.scenario = await api("/api/scenario", state.scenarioInput);
      state.scenarioDirty = false;
      document.querySelector("#scenario-result").innerHTML = scenarioResult();
      document
        .querySelector("#scenario-result")
        .classList.remove("stale-result");
      document.querySelector("#scenario-dirty").textContent =
        "Scenario updated using the assumptions shown.";
      toast("Scenario calculated. Assumed benefits are labeled.");
    } catch (error) {
      toast(error.message);
    } finally {
      submit.disabled = false;
    }
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && tutorialStep !== null) { closeTutorial(); return; }
  if (event.key === "Escape") {
    document.body.classList.remove("nav-open");
    syncNavigation();
  }
  if ((event.metaKey || event.ctrlKey) && ["b", "j"].includes(event.key.toLowerCase())) {
    event.preventDefault();
    document.querySelector(`.topbar [data-action="${event.key.toLowerCase() === "b" ? "menu" : "toggle-assistant"}"]`)?.click();
  }
  if (event.key === "Escape" && state.assistantOpen && innerWidth < 1400 && !document.querySelector("dialog[open]")) {
    document.querySelector('.topbar [data-action="toggle-assistant"]')?.click();
  }
  if (
    event.target.id === "chat-question" &&
    event.key === "Enter" &&
    !event.shiftKey
  ) {
    event.preventDefault();
    sendQuestion(event.target.value);
  }
  if (
    event.target.matches('[role="button"][data-action="cohort-point"]') &&
    ["Enter", " "].includes(event.key)
  ) {
    event.preventDefault();
    event.target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }
});
document.querySelector("#detail-dialog").addEventListener("click", (event) => {
  if (event.target.id === "detail-dialog") {
    const r = event.target.getBoundingClientRect();
    if (
      event.clientX < r.left ||
      event.clientX > r.right ||
      event.clientY < r.top ||
      event.clientY > r.bottom
    )
      closeModal();
  }
});
window.addEventListener("hashchange", () => {
  state.route = routeNames[location.hash.slice(1)]
    ? location.hash.slice(1)
    : "evidence";
  state.error = null;
  document.body.classList.remove("nav-open");
  shell();
  window.scrollTo(0, 0);
  loadRouteData();
});
shell();
if (location.protocol === "file:") {
  state.loading = false;
  state.error =
    "Start npm run dev in the demo folder, then open http://127.0.0.1:8080. Chat and exports require the app server.";
  renderPage();
} else loadData();
setInterval(checkConnection, 20000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) checkConnection();
});
window.addEventListener("online", checkConnection);

let chartCompact = innerWidth < 700;
window.addEventListener("resize", () => {
  syncNavigation();
  const compact = innerWidth < 700;
  if (compact !== chartCompact) {
    chartCompact = compact;
    const wrap = document.querySelector(".chart-wrap");
    if (wrap && state.dashboard) wrap.innerHTML = lineChart();
  }
});
