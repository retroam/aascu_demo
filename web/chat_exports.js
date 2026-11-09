import { validChatChart, renderChatChart, renderChatQuery } from "./chat_charts.js";

const escape = value => String(value ?? "Unavailable").replace(/[&<>"']/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function evidenceRows(message) {
  return [
    ["Data", message.notice || "Synthetic demo data; not institutional findings."],
    ["UI scope (SQL may further restrict)", JSON.stringify({ cohort: message.filters?.cohort, population: message.filters?.population })],
    ["Credit threshold context (not an enforced SQL filter)", message.filters?.threshold ?? "Not supplied"],
    ["Result completeness", message.completeness ? JSON.stringify(message.completeness) : "Not captured for this answer; truncation and withheld groups are unknown."],
    ["Chart coverage", "Only plotted returned groups, at most 24; not the full population. Withheld groups may be absent entirely, so connecting lines do not establish continuity."],
    ["Calculation", "Custom reviewed SQL, not automatically a canonical PDP measure. Inspect eligibility and denominator in SQL."],
    ["SQL", message.query?.sql || "Not supplied"],
    ["SQL SHA-256", message.query?.sql_sha256 || "Not supplied"],
    ["Review SHA-256", message.query?.review_sha256 || "Not supplied"],
    ["Generator", message.query?.generator_model || "Not supplied"],
    ["Verifier", message.query?.verifier_model || "Not supplied"],
    ...((message.citations || []).flatMap(c => [
      ["Source reference", c.source || "Not supplied"],
      ["Definition", c.definition || "Not supplied"],
      ["Returned columns / reference fields", Array.isArray(c.columns) ? c.columns.join(", ") : c.columns || "Not supplied"],
    ])),
    ["Limits", "Source references are not a complete record-level lineage audit. No source-data fingerprint is attached to this answer. Model review does not guarantee correctness. Missing and suppressed values are unavailable, not zero."],
  ];
}

export function renderChatEvidence(message) {
  return `<h3>From source to chart</h3><ol><li>Normalized PDP data supplies the scoped views.</li><li>The response's cohort and population filters restrict those views; SQL may narrow them further.</li><li>The reviewed SQL computes result columns. This is not automatically a shared metric calculation.</li><li>The chart plots returned values, with missing and suppressed values withheld.</li></ol><dl>${evidenceRows(message).map(([label, value]) => `<dt><strong>${escape(label)}</strong></dt><dd>${escape(value)}</dd>`).join("")}</dl>`;
}

export function buildChatChartReport(message, chartIndex, format) {
  const chart = message?.charts?.[chartIndex];
  if (message?.status !== "verified" || !Number.isInteger(chartIndex) || chartIndex < 0 ||
      !validChatChart(chart) || !["csv", "html"].includes(format))
    throw new Error("This chart has no exportable server-calculated evidence.");
  const name = `pdp-chart-${chartIndex + 1}.${format}`;
  if (format === "csv") {
    const cell = value => {
      // Only strings can carry spreadsheet formulas; signed numeric findings remain numbers.
      const safe = typeof value === "string" && /^(?:[\s\u0000-\u0020]*[=+@-]|[\t\r\n])/.test(value) ? `'${value}` : value;
      return `"${String(safe ?? "Unavailable").replace(/"/g, '""')}"`;
    };
    const rows = [["Chart", chart.title], ["Units", chart.unit], ["Caption", chart.caption],
      ...evidenceRows(message), [], ["Observation", "Value", "Numerator", "Denominator", "Status"],
      ...chart.points.map(p => [p.label, ...(p.status === "ok"
        ? [p.value, p.numerator, p.denominator] : [null, null, null]), p.status])];
    return { name, format, type: "text/csv;charset=utf-8", content: rows.map(row => row.map(cell).join(",")).join("\r\n") };
  }
  const content = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(chart.title)}</title><style>
    body{font:14px/1.6 system-ui,sans-serif;color:#20251e;background:#fff;max-width:850px;margin:32px auto;padding:0 20px}h1{font-size:24px}svg{width:100%;max-height:380px}svg text{font:12px system-ui;fill:#20251e}.evidence-grid{stroke:#dde2d8}.evidence-line{stroke:#527733;stroke-width:2}.evidence-point,.evidence-bar{fill:#527733}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left}pre,dd,td{white-space:pre-wrap;overflow-wrap:anywhere}dd{margin:0 0 12px}table{table-layout:fixed}details{margin:16px 0}figcaption p{margin-bottom:8px}@media print{body{margin:0;max-width:none}svg{break-inside:avoid}thead{display:table-header-group}}
    </style></head><body><h1>Chart evidence</h1><p>Synthetic demo data · Chart points only, not the full query table.</p>${renderChatChart(chart).replaceAll("<details>", "<details open>")}${renderChatEvidence(message)}${renderChatQuery(message.query).replace("<details ", "<details open ")}</body></html>`;
  return { name, format, type: "text/html;charset=utf-8", content };
}
