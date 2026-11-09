import test from "node:test";
import assert from "node:assert/strict";
import { renderChatChart, renderChatCharts, validChatChart, renderChatTable, renderChatQuery } from "../web/chat_charts.js";
import { buildChatChartReport, renderChatEvidence } from "../web/chat_exports.js";

const point = (value, status = "ok") => ({ label: "Cohort", value, numerator: 12.375, denominator: 25, status });
const chart = (points, extra = {}) => ({ type: "line", title: "Completion", unit: "percent", caption: "Eligible enrollments", points, ...extra });

test("all text is escaped, fractional numerator and exact values retained", () => {
  const attack = '<img src=x onerror="alert(1)">&';
  const html = renderChatChart(chart([{ ...point(49.5), label: attack }], { title: attack, caption: attack }));
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
  assert.ok(html.includes("&quot;"));
  assert.ok(html.includes("12.375"));
  assert.ok(html.includes("49.5%"));
  assert.ok(html.includes('<th scope="row">'));
});

test("nulls and suppressed nonzero values never draw marks or bridge lines", () => {
  const html = renderChatChart(chart([point(10), point(null), point(88, "suppressed"), point(20)]));
  assert.equal((html.match(/class="evidence-point"/g) || []).length, 2);
  assert.ok(!html.includes('class="evidence-line"'));
  assert.ok(!html.includes("88%"));
  assert.ok(html.includes("unavailable, not zero"));
  const bars = renderChatChart(chart([point(null), point(88, "suppressed")], { type: "bar" }));
  assert.ok(!bars.includes('class="evidence-bar"'));
});

test("signed pp bars extend below zero and rates use a 0–100 scale", () => {
  const html = renderChatChart(chart([point(-50), point(50)], { unit: "pp", type: "bar" }));
  assert.ok(html.includes('y="97" width="90.24" height="39.5"'));
  assert.ok(html.includes("-50 pp"));
  assert.ok(html.includes("-100 pp"));
  assert.ok(renderChatChart(chart([point(0)])).includes("100%"));
});

test("malformed and unsupported specifications fail closed without throwing", () => {
  for (const c of [null, {}, chart([]), chart([point(NaN)]), chart([point(Infinity)]),
    chart([point(-1)]), chart([point(101)]), chart([point(-101)], { unit: "pp" }),
    chart([point(-1)], { unit: "count" }), chart([point("20")]),
    chart(Array.from({ length: 25 }, () => point(1))), chart([point(2)], { type: "script" }),
    chart([point(2)], { unit: "dollars" }), chart([{ ...point(2), denominator: -1 }])]) {
    assert.equal(validChatChart(c), false);
    assert.match(renderChatChart(c), /Chart unavailable/);
  }
  assert.equal(renderChatCharts(undefined), "");
  assert.match(renderChatCharts({}), /Chart unavailable/);
  assert.match(renderChatCharts(Array(8).fill(chart([point(2)]))), /Chart unavailable/);
});

test("counts are nonnegative and not constrained to percentages", () => {
  const html = renderChatChart(chart([point(1500), point(0)], { unit: "count" }));
  assert.ok(html.includes("1500"));
  assert.ok(!html.includes("NaN"));
  assert.equal((html.match(/class="evidence-point"/g) || []).length, 2);
});

test("number units support signed, fractional, and extreme finite scales", () => {
  for (const values of [[-250, 250], [-3.5, -1], [0, 0], [2.75, 3.1],
    [-Number.MAX_VALUE, Number.MAX_VALUE], [-Number.MIN_VALUE, Number.MIN_VALUE]]) {
    const c = chart(values.map((v) => point(v)), { unit: "number", type: "bar" });
    assert.equal(validChatChart(c), true);
    const html = renderChatChart(c);
    assert.ok(!/NaN|Infinity/.test(html));
    assert.equal((html.match(/class="evidence-bar"/g) || []).length, 2);
    for (const v of values) assert.ok(html.includes(String(v)));
  }
  const signed = renderChatChart(chart([point(-250), point(250)], { unit: "number", type: "bar" }));
  assert.ok(signed.includes('y="97" width="90.24" height="79"'));
  for (const v of [Infinity, -Infinity, NaN, "3"])
    assert.equal(validChatChart(chart([point(v)], { unit: "number" })), false);
});

test("dynamic result tables escape headers/cells and distinguish null from zero", () => {
  const attack = '<script>"&</script>';
  const html = renderChatTable({ columns: [attack, "mean"], rows: [
    { [attack]: attack, mean: null }, { [attack]: 0, mean: -2.75 },
  ] });
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;&quot;&amp;"));
  assert.ok(html.includes("<td>Unavailable</td>"));
  assert.ok(html.includes("<td>0</td>"));
  assert.ok(html.includes("<td>-2.75</td>"));
  assert.ok(html.includes('scope="col"'));
  assert.match(renderChatTable({ columns: ["mean"], rows: [] }), /No rows returned/);
  assert.equal(renderChatTable({ columns: [], rows: [] }), "");
});

test("dynamic result tables reject malformed data and enforce row/column limits", () => {
  for (const value of [{}, { columns: [], rows: [{}] }, { columns: ["x", "x"], rows: [] },
    { columns: ["x"], rows: [{}] }, { columns: ["x"], rows: [{ x: {} }] },
    { columns: ["x"], rows: [{ x: Infinity }] },
    { columns: Array.from({ length: 17 }, (_, i) => String(i)), rows: [] },
    { columns: ["x"], rows: Array(201).fill({ x: 1 }) }])
    assert.match(renderChatTable(value), /table unavailable/);
  assert.match(renderChatTable({ columns: ["x"], rows: Array(200).fill({ x: 1 }) }), /200 rows/);
  assert.equal(renderChatTable(null), "");
});

test("query history escapes exact SQL and check feedback without endorsing results", () => {
  const attack = '</code><script>alert("x")</script>';
  const query = { sql: `SELECT '${attack}'\nFROM students`, generator_model: attack,
    verifier_model: "different-model", attempts: [
      { attempt: 1, stage: attack, status: "rejected", feedback: [attack, "Check denominator"] },
      { attempt: 2, stage: "domain", status: "passed", feedback: "Checks passed" },
    ] };
  const html = renderChatQuery(query);
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;/code&gt;&lt;script&gt;"));
  assert.ok(html.includes("\nFROM students"));
  assert.ok(html.includes("not query results"));
  assert.ok(html.includes("do not guarantee"));
  assert.ok(html.includes("SQL may further restrict"));
  assert.match(renderChatQuery({ ...query, sql: null }), /No SQL returned/);
  assert.match(renderChatQuery({ ...query, attempts: Array(33).fill(query.attempts[0]) }), /history unavailable/);
  assert.match(renderChatQuery({ ...query, attempts: [{ ...query.attempts[0], feedback: {} }] }), /history unavailable/);
  assert.equal(renderChatQuery(undefined), "");
});

test("chart exports retain response scope, exact numbers and suppression across formats", () => {
  const m = { status: "verified", filters: { cohort: "2021-22", population: "pell" },
    charts: [chart([{ ...point(-2.75), label: '=HYPERLINK("https://example.com")' },
      { ...point(98765, "suppressed"), numerator: 87654 }, point(null)], { unit: "number" })],
    query: { sql: "SELECT AVG(credits) FROM cohort_records", sql_sha256: "snapshot-hash", generator_model: "generator",
      verifier_model: "verifier", attempts: [] },
    citations: [{ source: "Synthetic normalized view", definition: "Mean known credits", columns: ["mean"] }] };
  const csv = buildChatChartReport(m, 0, "csv").content;
  assert.ok(csv.includes('"-2.75","12.375","25","ok"'));
  assert.ok(csv.includes("'=HYPERLINK"));
  for (const format of ["html", "csv"]) {
    const output = buildChatChartReport(m, 0, format).content;
    for (const expected of ["2021-22", "pell", "snapshot-hash", "Mean known credits", "Unavailable"])
      assert.ok(output.includes(expected));
    assert.ok(!output.includes("98765"));
    assert.ok(!output.includes("87654"));
  }
  assert.match(buildChatChartReport(m, 0, "html").content, /<details open>/);
  assert.match(renderChatCharts(m.charts, 3), /data-index="3" data-chart="0"/);
  assert.ok(!renderChatCharts(m.charts).includes("chat-chart-export"));
  assert.throws(() => buildChatChartReport({ ...m, status: "error" }, 0, "html"));
  assert.throws(() => buildChatChartReport(m, 1, "html"));
  assert.throws(() => buildChatChartReport(m, 0, "svg"));
});

test("exported source details are escaped and do not claim complete lineage", () => {
  const attack = '</title><script>alert("x")</script>';
  const m = { status: "verified", filters: { population: attack },
    charts: [chart([point(42)], { title: attack })], citations: [{ source: attack, definition: attack }] };
  const html = buildChatChartReport(m, 0, "html").content;
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.match(renderChatEvidence(m), /not a complete record-level lineage audit/);
  assert.match(html, /Chart points only, not the full query table/);
});
