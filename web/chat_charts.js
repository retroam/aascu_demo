// Only render declarative, server-calculated evidence. Never evaluate model code.
const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[c]);
const text = (v, max) => typeof v === "string" && v.length <= max;
const nullableNumber = (v) => v === null || (typeof v === "number" && Number.isFinite(v));

export function validChatChart(c) {
  return !!c && ["bar", "line"].includes(c.type) &&
    ["percent", "count", "pp", "number"].includes(c.unit) &&
    text(c.title, 200) && text(c.caption, 2000) &&
    Array.isArray(c.points) && c.points.length > 0 && c.points.length <= 24 &&
    c.points.every((p) => p && text(p.label, 200) && text(p.status, 100) &&
      p.status.length > 0 && nullableNumber(p.value) &&
      nullableNumber(p.numerator) && nullableNumber(p.denominator) &&
      (p.numerator === null || p.numerator >= 0) &&
      (p.denominator === null || p.denominator >= 0) &&
      (c.unit === "number" || p.value === null || (p.value >= (c.unit === "pp" ? -100 : 0) &&
        (c.unit === "count" || p.value <= 100))));
}

export function renderChatChart(c) {
  if (!validChatChart(c)) return '<p class="chat-chart-unavailable">Chart unavailable: unsupported or malformed evidence specification.</p>';
  const suffix = c.unit === "percent" ? "%" : c.unit === "pp" ? " pp" : "";
  // A suppressed/nonavailable observation must not leak a value, even if supplied.
  const points = c.points.map((p) => p.status === "ok" ? p :
    { ...p, value: null, numerator: null, denominator: null });
  const exact = (v) => v === null ? "Unavailable" : escape(v);
  const value = (p) => p.value === null ? "Unavailable" : `${exact(p.value)}${suffix}`;
  const values = points.map((p) => p.value ?? 0);
  const low = c.unit === "number" ? Math.min(0, ...values) : c.unit === "pp" ? -100 : 0;
  const high = c.unit === "number" ? Math.max(0, ...values) || (low === 0 ? 1 : 0) : c.unit === "count" ? Math.max(1, ...values) : 100;
  const left = 58, right = 340, top = 18, bottom = 176;
  // Normalize before subtracting so signed finite extremes cannot overflow.
  const magnitude = Math.max(Math.abs(low), Math.abs(high));
  const y = (v) => bottom - ((v / magnitude - low / magnitude) / (high / magnitude - low / magnitude)) * (bottom - top);
  const step = (right - left) / points.length;
  const x = (i) => left + step * (i + 0.5);
  const ticks = [...new Set([low, 0, high])];
  const namedTicks = points.length <= 4 && points.every((p) => p.label.length <= 16);
  let previous = null;
  const marks = points.map((p, i) => {
    if (p.value === null) { previous = null; return ""; }
    const title = `<title>${escape(p.label)}: ${value(p)}</title>`;
    if (c.type === "bar") return `<rect class="evidence-bar" x="${x(i) - step * .32}" y="${Math.min(y(0), y(p.value))}" width="${step * .64}" height="${Math.abs(y(p.value) - y(0))}">${title}</rect>`;
    const line = previous === null ? "" : `<line class="evidence-line" x1="${x(previous)}" y1="${y(points[previous].value)}" x2="${x(i)}" y2="${y(p.value)}"/>`;
    previous = i;
    return `${line}<circle class="evidence-point" cx="${x(i)}" cy="${y(p.value)}" r="3">${title}</circle>`;
  }).join("");
  return `<figure class="chat-evidence-chart"><figcaption><strong>${escape(c.title)}</strong><p>${escape(c.caption)}</p></figcaption><svg viewBox="0 0 352 204" role="img" aria-label="${escape(c.title)}. ${escape(c.unit)}. Exact values in the table below."><title>${escape(c.title)}</title>${ticks.map((v) => `<line class="evidence-grid" x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left - 5}" y="${y(v) + 4}" text-anchor="end">${escape(v)}${suffix}</text>`).join("")}${marks}${points.map((p, i) => `<text x="${x(i)}" y="194" text-anchor="middle">${namedTicks ? escape(p.label) : i + 1}</text>`).join("")}</svg><p class="chart-missing-note">${points.some((p) => p.value === null) ? "Missing or suppressed observations are unavailable, not zero. " : ""}${namedTicks ? "Exact values and eligibility are available below." : "Numbers identify observations in the table."}</p><details><summary>Exact values and denominators (${points.length})</summary><div class="chat-chart-table" tabindex="0" role="region" aria-label="${escape(c.title)} exact values"><table><caption>${escape(c.title)} · ${escape(c.unit)}. Units and eligibility follow the caption and sources.</caption><thead><tr><th scope="col"># / Observation</th><th scope="col">Value</th><th scope="col">Numerator</th><th scope="col">Denominator</th><th scope="col">Status</th></tr></thead><tbody>${points.map((p, i) => `<tr><th scope="row">${i + 1}. ${escape(p.label)}</th><td>${value(p)}</td><td>${exact(p.numerator)}</td><td>${exact(p.denominator)}</td><td>${escape(p.status)}</td></tr>`).join("")}</tbody></table></div></details></figure>`;
}

export function renderChatCharts(charts, messageIndex = null) {
  if (charts == null) return "";
  if (!Array.isArray(charts) || charts.length > 7)
    return '<p class="chat-chart-unavailable">Chart unavailable: unsupported evidence specification.</p>';
  return charts.map((chart, index) => renderChatChart(chart) +
    (validChatChart(chart) && Number.isInteger(messageIndex) && messageIndex >= 0
      ? `<div class="chat-chart-actions"><button class="button text" data-action="chat-chart-export" data-index="${messageIndex}" data-chart="${index}" data-format="csv">Export CSV</button><button class="button text" data-action="chat-chart-export" data-index="${messageIndex}" data-chart="${index}" data-format="html">Print / PDF</button><button class="button text" data-action="citations" data-index="${messageIndex}">Where this came from</button></div>` : "")).join("");
}

export function renderChatTable(table) {
  if (table == null) return "";
  if (Array.isArray(table.columns) && !table.columns.length && Array.isArray(table.rows) && !table.rows.length) return "";
  const cell = (v) => v === null || typeof v === "boolean" || text(v, 10000) ||
    (typeof v === "number" && Number.isFinite(v));
  if (!table || !Array.isArray(table.columns) || !table.columns.length || table.columns.length > 16 ||
      !table.columns.every((c) => text(c, 200) && c.length) || new Set(table.columns).size !== table.columns.length ||
      !Array.isArray(table.rows) || table.rows.length > 200 ||
      !table.rows.every((r) => r && typeof r === "object" && !Array.isArray(r) &&
        table.columns.every((c) => Object.hasOwn(r, c) && cell(r[c]))))
    return '<p class="chat-chart-unavailable">Results table unavailable: malformed or oversized result.</p>';
  return `<div class="chat-chart-table chat-query-results" tabindex="0" role="region" aria-label="SQL query results"><table><caption>Query results · ${table.rows.length} rows. Null values are unavailable, not zero.</caption><thead><tr>${table.columns.map((c) => `<th scope="col">${escape(c)}</th>`).join("")}</tr></thead><tbody>${table.rows.map((r) => `<tr>${table.columns.map((c) => `<td>${r[c] === null ? "Unavailable" : escape(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>${table.rows.length ? "" : '<p>No rows returned for this scope.</p>'}</div>`;
}

export function renderChatQuery(query) {
  if (query == null) return "";
  const feedback = (v) => text(v, 10000) ||
    (Array.isArray(v) && v.length <= 32 && v.every((s) => text(s, 1000)));
  if (!query || !(query.sql === null || text(query.sql, 50000)) || !text(query.generator_model, 200) ||
      !text(query.verifier_model, 200) || !Array.isArray(query.attempts) || query.attempts.length > 32 ||
      !query.attempts.every((a) => a && Number.isInteger(a.attempt) && a.attempt >= 0 &&
        text(a.stage, 200) && text(a.status, 100) && feedback(a.feedback)))
    return '<p class="chat-chart-unavailable">SQL and check history unavailable: malformed or oversized metadata.</p>';
  return `<details class="chat-query-details"><summary>SQL and validation history</summary><p>Generator: ${escape(query.generator_model)}<br>Verifier: ${escape(query.verifier_model)}</p><p>Model review and server checks do not guarantee the interpretation or numerical results are correct. SQL views enforce the active UI cohort and population; SQL may further restrict them. Change UI filters to broaden scope.</p><h4>Exact SQL</h4>${query.sql === null ? '<p>No SQL returned.</p>' : `<pre tabindex="0" aria-label="Exact generated SQL"><code>${escape(query.sql)}</code></pre>`}<h4>Check history — not query results</h4><ol>${query.attempts.map((a) => `<li><strong>Attempt ${a.attempt} · ${escape(a.stage)} · ${escape(a.status)}</strong><p>${escape(Array.isArray(a.feedback) ? a.feedback.join("\n") : a.feedback)}</p></li>`).join("")}</ol></details>`;
}

// Deliberately bounded Markdown: model HTML is always text, never executable markup.
export function renderChatMarkdown(value) {
  const source = typeof value === "string" ? value : String(value ?? "");
  function inline(text, depth = 0) {
    if (depth > 4) return escape(text);
    const pattern = /(`+)([^\n]*?)\1|\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^\n]+?)\*\*|__([^\n]+?)__|\*([^*\n]+)\*|_([^_\n]+)_/g;
    let output = "", end = 0;
    for (const match of text.matchAll(pattern)) {
      output += escape(text.slice(end, match.index));
      if (match[1]) output += `<code>${escape(match[2])}</code>`;
      else if (match[3]) {
        let url;
        try { url = new URL(match[4]); } catch { /* Unsupported links stay text. */ }
        output += url && ["https:", "http:"].includes(url.protocol)
          ? `<a href="${escape(url.href)}" target="_blank" rel="noopener noreferrer">${inline(match[3], depth + 1)}</a>`
          : escape(match[0]);
      } else if (match[5] || match[6]) output += `<strong>${inline(match[5] || match[6], depth + 1)}</strong>`;
      else output += `<em>${inline(match[7] || match[8], depth + 1)}</em>`;
      end = match.index + match[0].length;
    }
    return output + escape(text.slice(end));
  }
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const cells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
  const divider = line => line.includes("|") && cells(line).every(cell => /^:?-{3,}:?$/.test(cell));
  const block = line => /^\s*$|^ {0,3}(?:#{1,6}\s|```|~~~|>\s?|[-+*]\s|\d+\.\s)/.test(line);
  let html = "";
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (fence) {
      const code = []; i++;
      const close = new RegExp(`^ {0,3}${fence[1][0]}{${fence[1].length},}\\s*$`);
      while (i < lines.length && !close.test(lines[i])) code.push(lines[i++]);
      if (i < lines.length) i++;
      html += `<pre tabindex="0"><code>${escape(code.join("\n"))}</code></pre>`; continue;
    }
    const heading = line.match(/^ {0,3}(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = Math.min(6, heading[1].length + 2);
      html += `<h${level}>${inline(heading[2])}</h${level}>`; i++; continue;
    }
    if (i + 1 < lines.length && line.includes("|") && divider(lines[i + 1])) {
      const headers = cells(line), rows = []; i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) rows.push(cells(lines[i++]));
      html += `<div class="chat-markdown-table" role="region" aria-label="Answer table" tabindex="0"><table><thead><tr>${headers.map(h => `<th scope="col">${inline(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${headers.map((_, j) => `<td>${inline(row[j] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`; continue;
    }
    const item = line.match(/^\s*([-+*]|\d+\.)\s+(.+)$/);
    if (item) {
      const ordered = /\d/.test(item[1]), tag = ordered ? "ol" : "ul";
      const items = [];
      while (i < lines.length) {
        const next = lines[i].match(/^\s*([-+*]|\d+\.)\s+(.+)$/);
        if (!next || /\d/.test(next[1]) !== ordered) break;
        items.push(`<li>${inline(next[2])}</li>`); i++;
      }
      html += `<${tag}>${items.join("")}</${tag}>`; continue;
    }
    if (/^ {0,3}>/.test(line)) {
      const quote = [];
      while (i < lines.length && /^ {0,3}>/.test(lines[i])) quote.push(lines[i++].replace(/^ {0,3}> ?/, ""));
      html += `<blockquote>${inline(quote.join("\n")).replace(/\n/g, "<br>")}</blockquote>`; continue;
    }
    const paragraph = [line]; i++;
    while (i < lines.length && !block(lines[i]) && !(i + 1 < lines.length && divider(lines[i + 1]))) paragraph.push(lines[i++]);
    html += `<p>${inline(paragraph.join("\n")).replace(/\n/g, "<br>")}</p>`;
  }
  return html;
}


export function renderChatTables(tables) {
  if (tables == null) return "";
  if (!Array.isArray(tables) || tables.length > 3) return '<p>Example tables unavailable.</p>';
  return tables.map(table => table && text(table.title, 200)
    ? `<section class="chat-sample-table"><h3>${escape(table.title)}</h3>${renderChatTable(table)}</section>`
    : '<p>Example table unavailable.</p>').join("");
}
