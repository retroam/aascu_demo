import test from "node:test";
import assert from "node:assert/strict";
import { createStudentWorkspace, readFollowups } from "../web/students.js";
import { initializeDataset } from "../web/dataset-state.js";

const originalFetch = globalThis.fetch;
globalThis.fetch = async () => ({ok:true, json:async()=>({dataset:{origin:"starter",run_id:"fixture"}})});
await initializeDataset();
globalThis.fetch = originalFetch;

const ID = "006F3FF4E1F908EFE0535964C70A009A";
const row = { student_id: ID, cohort: "2024-25", enrollment_intensity: "Part-Time", enrollment_type: "Transfer-In", credits_attempted: 12, credits_earned: 12, gpa: 4, retention: true, persistence: false, gateway_math: "Not completed", gateway_math_requirement: "Required", gateway_english: "Unknown", gateway_english_requirement: "Unknown", review_reasons: [{ id: "low-credits", label: "Year-one earned credits below 24" }] };
const roster = (extra = {}) => ({ rows: [row], page: 1, total_pages: 2, total: 26, synthetic: true, ...extra });
const detail = (extra = {}) => ({ student_id: ID, cohorts: [{ ...row, credit_history: [{ year: 1, attempted: 12, earned: 12 }] }], courses: [], course_count: 0, synthetic: true, ...extra });
const record = (extra = {}) => ({ team: "advising", task: "review-plan", status: "planned", outcome: "not-recorded", updated_at: "2026-11-05T12:00:00.000Z", ...extra });
const settle = () => new Promise(resolve => setImmediate(resolve));
function harness(options = {}) {
  const calls = [], pending = [], writes = [];
  const storage = options.storage ?? { getItem: () => null, setItem: (key, value) => writes.push({ key, value }) };
  const workspace = createStudentWorkspace({ request: url => { calls.push(url); return new Promise((resolve, reject) => pending.push({ resolve, reject })); }, storage });
  const click = (action, values = {}) => workspace.handleClick({ closest: () => ({ dataset: { studentAction: action, ...values } }) });
  const submit = (type, values) => workspace.handleSubmit({ preventDefault() {}, target: { closest: () => ({ dataset: { studentForm: type }, elements: Object.fromEntries(Object.entries(values).map(([name, value]) => [name, { value }])) }) } });
  const ready = async (filters = {}, data = roster()) => { const loading = workspace.load(filters); pending.shift().resolve(data); await loading; };
  const open = async (data = detail()) => { click("open", { studentId: ID }); pending.shift().resolve(data); await settle(); };
  return { workspace, calls, pending, writes, click, submit, ready, open };
}

test("malformed storage and invalid records are ignored; restored fields are allowlisted", () => {
  assert.equal(Object.keys(readFollowups({ getItem: () => "{broken" })).length, 0);
  assert.equal(Object.keys(readFollowups({ getItem: () => "[]" })).length, 0);
  const restored = readFollowups({ getItem: () => JSON.stringify({ [ID]: { ...record(), arbitrary: "<script>" }, wrong: record({ team: "made-up" }) }) });
  assert.deepEqual(restored[ID], record());
  assert.equal(Object.hasOwn(restored, "wrong"), false);
});

test("requests preserve selected scope, entry type, and submitted search filters", async () => {
  const h = harness(); h.workspace.setEntryType("transfer");
  await h.ready({ cohort: "2024-25", population: "part-time", threshold: 30 });
  let url = new URL(h.calls[0], "http://demo.local");
  assert.equal(url.searchParams.get("cohort"), "2024-25");
  assert.equal(url.searchParams.get("population"), "part-time");
  assert.equal(url.searchParams.get("threshold"), "30");
  assert.equal(url.searchParams.get("entry_type"), "transfer");
  h.submit("search", { search: "  006f  ", review: "low-gpa", entry_type: "readmit" });
  url = new URL(h.calls.at(-1), "http://demo.local");
  assert.equal(url.searchParams.get("search"), "006f");
  assert.equal(url.searchParams.get("review"), "low-gpa");
  assert.equal(url.searchParams.get("entry_type"), "readmit");
  assert.equal(url.searchParams.get("page"), "1");
  h.pending.shift().resolve(roster()); await settle(); await h.open();
  url = new URL(h.calls.at(-1), "http://demo.local");
  assert.equal(url.pathname, "/api/student");
  assert.equal(url.searchParams.get("entry_type"), "readmit");
  assert.equal(url.searchParams.get("population"), "part-time");
  assert.equal(url.searchParams.get("id"), ID);
});

test("a late roster response cannot replace the newly selected population", async () => {
  const h = harness();
  const oldLoad = h.workspace.load({ population: "part-time" }); const oldRequest = h.pending.shift();
  const newLoad = h.workspace.load({ population: "pell" });
  h.pending.shift().resolve(roster({ total: 73 })); await newLoad;
  oldRequest.resolve(roster({ total: 999 })); await oldLoad;
  const view = h.workspace.render({ population: "pell" });
  assert.match(view, /73 matching records/); assert.doesNotMatch(view, /999 matching records/);
});

test("a late profile response cannot reopen a student after a scope change", async () => {
  const h = harness(); await h.ready();
  h.click("open", { studentId: ID }); const oldDetail = h.pending.shift();
  const freshLoad = h.workspace.load({ cohort: "2023-24" });
  h.pending.shift().resolve(roster()); await freshLoad;
  oldDetail.resolve(detail()); await settle();
  assert.doesNotMatch(h.workspace.render({ cohort: "2023-24" }), /Plan a follow-up/);
});

test("untrusted record values are escaped in roster and profile output", async () => {
  const h = harness(); const malicious = '<img src=x onerror="alert(1)">';
  await h.ready({}, roster({ rows: [{ ...row, enrollment_type: malicious, review_reasons: [{ label: malicious }] }] }));
  assert.doesNotMatch(h.workspace.render({}), /<img/); assert.match(h.workspace.render({}), /&lt;img/);
  await h.open(detail({ courses: [{ course_name: malicious, grade: malicious, cohort: row.cohort }] }));
  assert.doesNotMatch(h.workspace.render({}), /<img/); assert.match(h.workspace.render({}), /&lt;img/);
});

test("completion requires a result and saves retain only the chosen demo fields", async () => {
  const h = harness(); await h.ready(); await h.open();
  h.submit("followup", { team: "advising", task: "review-plan", status: "completed", outcome: "not-recorded" });
  assert.equal(h.writes.length, 0); assert.match(h.workspace.render({}), /Choose a follow-up result/);
  h.submit("followup", { team: "advising", task: "review-plan", status: "completed", outcome: "review-completed" });
  assert.equal(h.writes.length, 1);
  const saved = JSON.parse(h.writes[0].value)[ID];
  assert.deepEqual(Object.keys(saved).sort(), ["outcome", "status", "task", "team", "updated_at"]);
  assert.equal(saved.status, "completed"); assert.equal(saved.outcome, "review-completed");
  assert.match(h.workspace.render({}), /No assignment or message was sent/);
});

test("failed browser storage saves preserve the prior stored follow-up", async () => {
  const original = record({ status: "completed", outcome: "review-completed" });
  const h = harness({ storage: { getItem: () => JSON.stringify({ [ID]: original }), setItem() { throw new Error("Quota exceeded"); } } });
  await h.ready(); await h.open();
  h.submit("followup", { team: "financial-aid", task: "review-enrollment", status: "in-progress", outcome: "not-recorded" });
  assert.match(h.workspace.render({}), /could not be saved/);
  h.click("back"); const view = h.workspace.render({});
  assert.match(view, /Completed/); assert.match(view, /Advising/); assert.doesNotMatch(view, />In progress</);
});

test("search and pagination focus results, but initial or background scope loading does not", async t => {
  const previousDocument = globalThis.document, focused = [];
  globalThis.document = { querySelector: selector => ({ focus: () => focused.push(selector) }) };
  t.after(() => { if (previousDocument === undefined) delete globalThis.document; else globalThis.document = previousDocument; });
  const h = harness(); await h.ready(); await settle(); assert.deepEqual(focused, []);
  h.click("next"); h.pending.shift().resolve(roster({ page: 2 })); await settle();
  assert.equal(focused.at(-1), ".student-workspace .student-results-heading");
  h.submit("search", { search: "006F", review: "all", entry_type: "all" }); h.pending.shift().resolve(roster()); await settle();
  assert.equal(focused.length, 2); assert.equal(focused.at(-1), ".student-workspace .student-results-heading");
  await h.ready({ population: "pell" }); await settle(); assert.equal(focused.length, 2);
});

test("missing API route explains restart while genuine not-found errors retain their meaning", async () => {
  const h = harness(); const loading = h.workspace.load({});
  h.pending.shift().reject({ status: 404, message: "API route not found." }); await loading;
  assert.match(h.workspace.render({}), /Restart the demo server/);
  h.click("retry"); h.pending.shift().resolve(roster()); await settle();
  h.click("open", { studentId: ID });
  h.pending.shift().reject({ status: 404, message: "Student not found in the selected cohort and population." }); await settle();
  assert.match(h.workspace.render({}), /Student not found in the selected cohort and population/);
  assert.doesNotMatch(h.workspace.render({}), /Restart the demo server/);
});
