/** Synthetic student records and browser-local demonstration follow-up. */
import { requestJSON } from "./transport.js";
import { datasetStorageKey } from "./dataset-state.js";

const STORE = "aascu-synthetic-followups-v1";
const TEAMS = { unassigned: "Choose a team", advising: "Advising", "student-success": "Student success", "financial-aid": "Financial aid" };
const TASKS = { "review-plan": "Review academic plan", "review-credits": "Review credit progress", "review-gateway": "Review gateway course progress", "review-enrollment": "Review enrollment history" };
const STATUSES = { planned: "Planned", "in-progress": "In progress", completed: "Completed" };
const OUTCOMES = { "not-recorded": "Not recorded", "review-completed": "Record review completed", "referral-planned": "Referral planned", "no-further-action": "No further action identified" };
const ENTRY_TYPES = { all: "All entry types", transfer: "Transfer students", "first-time": "First-time students", readmit: "Readmitted students", continuing: "Continuing students" };
const REVIEWS = { all: "All records", "low-credits": "Below credit momentum threshold", "gateway-math": "Math gateway not completed", "gateway-english": "English gateway not completed", "low-gpa": "First-term GPA below 2.0" };
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const number = value => value == null || !Number.isFinite(Number(value)) ? "Not recorded" : Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
const outcome = value => value == null ? "Not recorded" : value ? "Yes" : "No";
const options = (map, selected) => Object.entries(map).map(([value, label]) => `<option value="${esc(value)}" ${selected === value ? "selected" : ""}>${esc(label)}</option>`).join("");
const normalizedFilters = (filters = {}) => ({ cohort: filters.cohort || "all", population: filters.population || "all", threshold: Number(filters.threshold) === 30 ? 30 : 24 });
const scopeKey = filters => JSON.stringify(normalizedFilters(filters));
const requestError = (error, fallback) => error.status === 404 && /API route not found/i.test(error.message || "")
  ? "Restart the demo server to load the new student endpoints, then select Retry."
  : error.message || fallback;
const field = (label, value) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`;
const action = (name, label, extra = "", primary = false) => `<button type="button" class="button${primary ? " primary" : ""}" data-student-action="${name}" ${extra}>${label}</button>`;

export function validFollowup(value) {
  return !!value && typeof value === "object" && !Array.isArray(value)
    && Object.hasOwn(TEAMS, value.team) && value.team !== "unassigned"
    && Object.hasOwn(TASKS, value.task) && Object.hasOwn(STATUSES, value.status)
    && Object.hasOwn(OUTCOMES, value.outcome)
    && typeof value.updated_at === "string" && Number.isFinite(Date.parse(value.updated_at));
}
export function readFollowups(storage) {
  try {
    const parsed = JSON.parse(storage.getItem(datasetStorageKey(STORE)) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return Object.create(null);
    return Object.fromEntries(Object.entries(parsed).filter(([id, value]) => /^[A-Za-z0-9_-]{1,128}$/.test(id) && validFollowup(value)).slice(-500).map(([id, value]) => [id, {team:value.team, task:value.task, status:value.status, outcome:value.outcome, updated_at:value.updated_at}]));
  } catch { return Object.create(null); }
}
function getStorage() { try { return globalThis.localStorage; } catch { return null; } }
function reasons(row) {
  return row.review_reasons?.length
    ? `<ul class="student-reasons">${row.review_reasons.map(reason => `<li>${esc(reason.label)}</li>`).join("")}</ul>`
    : '<span class="student-muted">No selected review indicators</span>';
}
function freshness(data) {
  const f = data?.freshness;
  return `<details class="student-data-note"><summary>Data timing and coverage</summary><p>${esc(f?.detail || "The source extraction date and follow-up completeness are not verified. These are historical synthetic records, not current alerts.")}</p>${f?.normalized_loaded_at ? `<p>Local normalized data loaded: ${esc(f.normalized_loaded_at)}. This is a processing date, not the date student information was collected.</p>` : ""}<p>Missing values mean not recorded, not zero. Record indicators are observations for staff review, not predictions or reasons a student left.</p></details>`;
}

export function createStudentWorkspace({ request = requestJSON, onChange = () => {}, storage = getStorage() } = {}) {
  const state = { filters: normalizedFilters(), scope: null, entryType: "all", page: 1, search: "", review: "all", roster: null, detail: null, selectedId: null, loading: false, error: null, followups: readFollowups(storage), message: "", saveError: false, draft: null };
  let version = 0;
  const redraw = () => onChange();
  const focus = selector => queueMicrotask(() => {
    if (typeof document === "undefined") return;
    document.querySelector(`.student-workspace ${selector}`)?.focus({ preventScroll: false });
  });
  const query = () => new URLSearchParams({ ...state.filters, entry_type: state.entryType });

  async function fetchRoster({ focusResults = false } = {}) {
    const current = ++version;
    state.loading = true; state.error = null; redraw();
    const params = query();
    params.set("page", state.page); params.set("page_size", "25");
    params.set("review", state.review);
    if (state.search) params.set("search", state.search);
    try {
      const data = await request(`/api/students?${params}`);
      if (current !== version) return;
      if (!data || !Array.isArray(data.rows)) throw new Error("Student records could not be read. Try again.");
      state.roster = data;
    } catch (error) { if (current === version) state.error = requestError(error, "Student records could not be loaded."); }
    finally { if (current === version) { state.loading = false; redraw(); if (focusResults) focus(state.error ? ".student-error" : ".student-results-heading"); } }
  }
  async function fetchDetail(id) {
    const current = ++version;
    state.selectedId = id; state.detail = null; state.draft = null; state.loading = true; state.error = null; state.message = ""; redraw();
    const params = query(); params.set("id", id);
    try {
      const data = await request(`/api/student?${params}`);
      if (current !== version) return;
      if (!data || !Array.isArray(data.cohorts) || !Array.isArray(data.courses)) throw new Error("This student record could not be read. Try again.");
      state.detail = data;
    } catch (error) { if (current === version) state.error = requestError(error, "This student record could not be loaded."); }
    finally { if (current === version) { state.loading = false; redraw(); focus(state.error ? ".student-error" : ".student-profile-header h2"); } }
  }
  function reset() {
    ++version; state.page = 1; state.search = ""; state.review = "all"; state.entryType = "all"; state.scope = null;
    state.selectedId = null; state.detail = null; state.roster = null; state.error = null; state.loading = false; state.message = "";
  }
  async function load(filters = {}) {
    const key = scopeKey(filters);
    if (state.scope === key && (state.roster || state.loading)) return;
    if (state.scope !== key) {
      ++version; state.filters = normalizedFilters(filters); state.scope = key;
      state.page = 1; state.detail = null; state.selectedId = null; state.roster = null; state.message = "";
    }
    return fetchRoster();
  }

  function renderRoster() {
    const data = state.roster;
    return `<form class="student-search" data-student-form="search"><div><label for="student-search">Find a synthetic student ID</label><input id="student-search" name="search" type="search" maxlength="32" pattern="[A-Fa-f0-9]*" title="Use up to 32 hexadecimal characters (0–9 and A–F)." autocomplete="off" placeholder="Enter an ID prefix" value="${esc(state.search)}"/></div><div><label for="student-review">Records to review</label><select id="student-review" name="review">${options(REVIEWS, state.review)}</select></div><div><label for="student-entry-type">Entry type</label><select id="student-entry-type" name="entry_type">${options(ENTRY_TYPES, state.entryType)}</select></div><button class="button primary" type="submit">Apply</button>${state.search || state.review !== "all" ? action("clear", "Clear search") : ""}</form>
      <div class="student-context"><p>Browse records in the selected cohort and population. Entry type: ${esc(ENTRY_TYPES[state.entryType])}. Choose an observed indicator, open a student, then record a demonstration follow-up.</p><p>One row per student × entry cohort. Indicators use first-term GPA and year-one credit or gateway outcomes; they do not describe a student's current circumstances.</p></div>
      ${state.loading ? '<div class="page-loader" role="status">Loading student records…</div>' : ""}
      ${state.error ? errorPanel() : ""}
      ${!state.loading && !state.error && data ? `<section class="panel"><div class="panel-header"><div><h2 class="student-results-heading" tabindex="-1">${number(data.total)} matching records</h2><p>After entry type, ID, and review filters. Sorted by newest entry cohort, then student ID. Open a record to review the evidence.</p></div></div>${data.rows.length ? `<div class="table-scroll"><table class="data-table student-table"><caption class="student-sr-only">Synthetic students in the selected scope</caption><thead><tr><th scope="col">Student / entry cohort</th><th scope="col">Enrollment</th><th scope="col">Year-one credits earned</th><th scope="col">Observed indicators</th><th scope="col">Demo follow-up</th><th scope="col">Profile</th></tr></thead><tbody>${data.rows.map(row => {
        const followup = state.followups[row.student_id];
        return `<tr><td><span class="student-id">${esc(row.student_id)}</span><small>${esc(row.cohort)}</small></td><td>${esc(row.enrollment_intensity || "Not recorded")}<small>${esc(row.enrollment_type || "")}</small></td><td>${number(row.credits_earned)}<small>${number(row.credits_attempted)} attempted</small></td><td>${reasons(row)}</td><td>${followup ? `<span class="badge neutral">${esc(STATUSES[followup.status])}</span><small>${esc(TEAMS[followup.team])}</small>` : '<span class="student-muted">Not planned</span>'}</td><td>${action("open", "View student", `data-student-id="${esc(row.student_id)}" aria-label="View synthetic student ${esc(row.student_id)}"`)}</td></tr>`;
      }).join("")}</tbody></table></div><div class="student-pagination">${action("previous", "Previous", state.page <= 1 ? "disabled" : "")}<span>Page ${number(data.page)} of ${number(data.total_pages)}</span>${action("next", "Next", state.page >= data.total_pages ? "disabled" : "")}</div>` : `<div class="empty-state"><h3>No matching student records</h3><p>Try a different ID prefix or review indicator. The cohort and population filters also limit this list.</p>${action("clear", "Clear search and review indicator")}</div>`}</section>${freshness(data)}` : ""}`;
  }
  function errorPanel() {
    return `<section class="student-error" role="alert" tabindex="-1"><h2>Unable to load records</h2><p>${esc(state.error)}</p>${action("retry", "Retry")}</section>`;
  }
  function renderFollowup(id) {
    const saved = state.followups[id];
    const value = state.draft || saved || {team:"unassigned", task:"review-plan", status:"planned", outcome:"not-recorded"};
    return `<section class="panel student-followup"><div class="panel-header"><div><h2>Plan a follow-up</h2><p>Practice the handoff from evidence to action.</p></div><span class="badge neutral">Browser-local demo</span></div><div class="panel-body"><p class="student-muted">One plan per synthetic student, shared across their entry-cohort records. This plan is saved only in this browser. It does not assign work in a campus system, contact anyone, or establish that an intervention occurred.</p><form data-student-form="followup"><div class="student-form-grid"><div><label for="student-team">Responsible team</label><select id="student-team" name="team" required>${options(TEAMS, value.team)}</select></div><div><label for="student-task">Next step</label><select id="student-task" name="task">${options(TASKS, value.task)}</select></div><div><label for="student-status">Demo status</label><select id="student-status" name="status">${options(STATUSES, value.status)}</select></div><div><label for="student-outcome">Demo follow-up result</label><select id="student-outcome" name="outcome">${options(OUTCOMES, value.outcome)}</select></div></div><div class="student-save-row"><button class="button primary" type="submit">Save demo follow-up</button>${saved ? `<span class="student-muted">Last saved ${esc(new Date(saved.updated_at).toLocaleString())}</span>` : ""}</div><p class="student-save-message${state.saveError ? " is-error" : ""}" tabindex="-1" role="${state.saveError ? "alert" : "status"}">${esc(state.message)}</p></form></div></section>`;
  }
  function renderDetail() {
    const d = state.detail;
    return `<div class="student-back">${action("back", "← Back to student records")}</div>${state.loading ? '<div class="page-loader" role="status">Loading student profile…</div>' : ""}${state.error ? errorPanel() : ""}${d && !state.loading && !state.error ? `<div class="student-profile-header"><div><h2 tabindex="-1">Synthetic student <span class="student-id">${esc(d.student_id)}</span></h2><p>History within the selected cohort and population. Broaden the filters to see other eligible entry-cohort records.</p></div><span class="badge neutral">Historical record</span></div>
      <div class="student-profile-grid"><div class="student-history">${d.cohorts.map(row => `<section class="panel"><div class="panel-header"><div><h3>${esc(row.cohort)} entry cohort</h3><p>${esc(row.enrollment_type || "Entry type not recorded")} · ${esc(row.enrollment_intensity || "Enrollment intensity not recorded")}</p></div></div><div class="panel-body"><h4>Observed indicators to review</h4>${reasons(row)}<dl class="student-facts">${field("First-term GPA", number(row.gpa))}${field("Year-one credits earned", number(row.credits_earned))}${field("Year-one credits attempted", number(row.credits_attempted))}${field("Math gateway outcome", row.gateway_math || "Not recorded")}${field("Math gateway requirement", row.gateway_math_requirement || "Unknown")}${field("English gateway outcome", row.gateway_english || "Not recorded")}${field("English gateway requirement", row.gateway_english_requirement || "Unknown")}${field("Year-two retention recorded", outcome(row.retention))}${field("Persistence elsewhere recorded", outcome(row.persistence))}</dl>${row.credit_history?.length ? `<details class="student-credit-history"><summary>Credit history by year</summary><div class="table-scroll"><table class="data-table"><thead><tr><th scope="col">Year</th><th scope="col">Attempted</th><th scope="col">Earned</th></tr></thead><tbody>${row.credit_history.map(year => `<tr><th scope="row">${esc(year.year)}</th><td>${number(year.attempted)}</td><td>${number(year.earned)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}</div></section>`).join("")}</div>${renderFollowup(d.student_id)}</div>
      <section class="panel student-courses"><div class="panel-header"><div><h2>Course history</h2><p>Course records linked by student ID and entry cohort. This extract may not be a complete transcript.</p></div></div>${d.courses.length ? `<div class="table-scroll"><table class="data-table"><caption class="student-sr-only">Course records in the selected student scope</caption><thead><tr><th scope="col">Course</th><th scope="col">Term / cohort</th><th scope="col">Grade recorded</th><th scope="col">Credits attempted</th><th scope="col">Credits earned</th></tr></thead><tbody>${d.courses.map(course => `<tr><td>${esc(course.course_name || "Course name not recorded")}${course.gateway ? `<small>${esc(course.gateway)}</small>` : ""}</td><td>${esc(course.term || "Term not recorded")}<small>${esc(course.cohort)}</small>${course.begin_date || course.end_date ? `<small>${esc(course.begin_date || "Unknown start")} – ${esc(course.end_date || "Unknown end")}</small>` : ""}</td><td>${esc(course.grade ?? "Not recorded")}</td><td>${number(course.credits_attempted)}</td><td>${number(course.credits_earned)}</td></tr>`).join("")}</tbody></table></div>${d.courses_truncated ? `<p class="student-table-note">Showing ${number(d.courses.length)} of ${number(d.course_count)} linked course records.</p>` : ""}` : '<div class="empty-state"><h3>No linked courses in this scope</h3><p>No course history was returned for the selected student and entry cohort.</p></div>'}</section>${freshness(d)}` : ""}`;
  }
  function render(filters = state.filters) {
    return `<div class="student-workspace"><div class="student-demo-notice"><strong>Synthetic student walkthrough</strong><span>Explore historical records and practice a follow-up. No real student identities or live campus records are connected.</span></div>${scopeKey(filters) !== state.scope ? '<div class="page-loader" role="status">Loading selected student records…</div>' : state.selectedId ? renderDetail() : renderRoster()}</div>`;
  }
  function handleClick(element) {
    const button = element?.closest?.("[data-student-action]");
    if (!button) return false;
    const name = button.dataset.studentAction;
    if (button.disabled) return true;
    if (name === "open") void fetchDetail(button.dataset.studentId);
    else if (name === "back") { ++version; state.selectedId = null; state.detail = null; state.loading = false; state.error = null; state.message = ""; state.draft = null; redraw(); focus("#student-search"); }
    else if (name === "retry") { if (state.selectedId) void fetchDetail(state.selectedId); else void fetchRoster({ focusResults: true }); }
    else if (name === "clear") { state.search = ""; state.review = "all"; state.page = 1; void fetchRoster({ focusResults: true }); }
    else if (name === "previous" && state.page > 1) { state.page--; void fetchRoster({ focusResults: true }); }
    else if (name === "next" && state.page < state.roster?.total_pages) { state.page++; void fetchRoster({ focusResults: true }); }
    else return false;
    return true;
  }
  function handleSubmit(event) {
    const form = event.target?.closest?.("form[data-student-form]");
    if (!form) return false;
    event.preventDefault();
    if (form.dataset.studentForm === "search") {
      state.search = String(form.elements.search.value || "").trim().slice(0,32);
      state.review = Object.hasOwn(REVIEWS, form.elements.review.value) ? form.elements.review.value : "all";
      state.entryType = Object.hasOwn(ENTRY_TYPES, form.elements.entry_type.value) ? form.elements.entry_type.value : "all";
      state.page = 1; state.selectedId = null; void fetchRoster({ focusResults: true }); return true;
    }
    if (form.dataset.studentForm === "followup" && state.detail) {
      const record = { team:form.elements.team.value, task:form.elements.task.value, status:form.elements.status.value, outcome:form.elements.outcome.value, updated_at:new Date().toISOString() };
      state.saveError = false; state.draft = record;
      if (!validFollowup(record)) { state.message = "Choose a responsible team before saving the demo follow-up."; state.saveError = true; redraw(); focus(".student-save-message"); return true; }
      if (record.status === "completed" && record.outcome === "not-recorded") { state.message = "Choose a follow-up result before marking the demo complete."; state.saveError = true; redraw(); focus(".student-save-message"); return true; }
      const previous = state.followups[state.detail.student_id];
      state.followups[state.detail.student_id] = record;
      try {
        if (!storage) throw new Error("Storage unavailable");
        storage.setItem(datasetStorageKey(STORE), JSON.stringify(state.followups));
        state.message = "Demo follow-up saved in this browser. No assignment or message was sent.";
      } catch {
        if (previous) state.followups[state.detail.student_id] = previous; else delete state.followups[state.detail.student_id];
        state.message = "The follow-up could not be saved because browser storage is unavailable. Enable local storage and try again."; state.saveError = true;
      }
      redraw(); focus(".student-save-message"); return true;
    }
    return false;
  }
  function setEntryType(value) {
    ++version; state.loading = false;
    state.entryType = Object.hasOwn(ENTRY_TYPES, value) ? value : "all";
    state.page = 1; state.roster = null; state.detail = null; state.selectedId = null;
  }
  return { render, load, reset, handleClick, handleSubmit, setEntryType };
}
