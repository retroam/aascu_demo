import test from "node:test";
import assert from "node:assert/strict";
import { requestJSON, requestReport } from "./transport.js";
import { initializeDataset } from "./dataset-state.js";
const respond =
  (body, type, status = 200, extra = {}) =>
  async () =>
    new Response(body, { status, headers: { "Content-Type": type, ...extra } });
test("JSON requests preserve a validated server response", async () => {
  assert.deepEqual(
    await requestJSON("/api/health", {
      fetchImpl: respond('{"status":"ok"}', "application/json"),
    }),
    { status: "ok" },
  );
});
test("a changed dataset cannot enter JSON views or downloaded reports", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ok:true, json:async()=>({dataset:{origin:"starter",run_id:"baseline"}})});
    await initializeDataset();
    assert.deepEqual(await requestJSON("/api/dashboard", {fetchImpl:respond('{"rows":10313}', "application/json", 200,
      {"X-PDP-Dataset":"starter:baseline"})}), {rows:10313});
    await assert.rejects(requestJSON("/api/measures", {fetchImpl:respond('{"rows":11}', "application/json", 200,
      {"X-PDP-Dataset":"workbench:upload-a"})}), error=>error.code === "dataset_changed");
    await assert.rejects(requestReport("/api/report", "csv", {fetchImpl:respond('metric,value\nretention,42', "text/csv", 200,
      {"X-PDP-Dataset":"workbench:upload-a", "Content-Disposition":'attachment; filename="report.csv"'})}), error=>error.code === "dataset_changed");
  } finally { globalThis.fetch = original; }
});
test("connection failures explain how to reconnect", async () => {
  await assert.rejects(
    requestJSON("/api/chat", {
      fetchImpl: async () => {
        throw new TypeError("Failed to fetch");
      },
    }),
    (e) => e.code === "connection" && e.message.includes("Reconnect"),
  );
});
test("request timeouts release the pending action", async () => {
  const pending = (_, options) =>
    new Promise((_, reject) =>
      options.signal.addEventListener("abort", () =>
        reject(new Error("aborted")),
      ),
    );
  await assert.rejects(
    requestJSON("/api/chat", { fetchImpl: pending, timeoutMs: 10 }),
    (e) => e.code === "timeout",
  );
});
test("a static server HTML fallback is not treated as an API result", async () => {
  await assert.rejects(
    requestJSON("/api/chat", {
      fetchImpl: respond("<html>app</html>", "text/html"),
    }),
    (e) => e.code === "unexpected_response",
  );
});
test("failed SQL checks remain available for the chat validation history", async () => {
  const query = { sql: null, attempts: [{ attempt: 1, stage: "guard", status: "rejected", feedback: ["Unknown column"] }] };
  await assert.rejects(
    requestJSON("/api/chat", { fetchImpl: respond(JSON.stringify({ error: "No candidate passed", query }), "application/json", 422) }),
    (error) => {
      assert.equal(error.message, "No candidate passed");
      assert.equal(error.status, 422);
      assert.deepEqual(error.details.query, query);
      return true;
    },
  );
});
test("an HTTP error cannot become a downloaded report", async () => {
  await assert.rejects(
    requestReport("/api/report", "html", {
      fetchImpl: respond(
        '{"error":"Unsupported scope"}',
        "application/json",
        400,
      ),
    }),
    (e) => e.code === "http" && e.message === "Unsupported scope",
  );
});
test("empty and unexpected report content is rejected", async () => {
  await assert.rejects(
    requestReport("/api/report", "html", {
      fetchImpl: respond("", "text/html"),
    }),
    (e) => e.code === "invalid_report",
  );
  await assert.rejects(
    requestReport("/api/report", "csv", {
      fetchImpl: respond("<html>fallback</html>", "text/html"),
    }),
    (e) => e.code === "invalid_report",
  );
});
test("CSV content and filename survive the download path", async () => {
  const content = "metric,value_percent\r\nRetention,49.59\r\n";
  const report = await requestReport("/api/report", "csv", {
    fetchImpl: respond(content, "text/csv; charset=utf-8", 200, {
      "Content-Disposition": 'attachment; filename="evidence-pell.csv"',
    }),
  });
  assert.equal(report.content, content);
  assert.equal(report.name, "evidence-pell.csv");
});
test("HTML reports are available for preview and download", async () => {
  const content = "<!doctype html><html><body>Student success</body></html>";
  const report = await requestReport("/api/report", "html", {
    fetchImpl: respond(content, "text/html", 200, {
      "Content-Disposition": 'attachment; filename="evidence.html"',
    }),
  });
  assert.equal(report.content, content);
  assert.equal(report.format, "html");
});
test("a successful static-server fallback cannot masquerade as a report", async () => {
  await assert.rejects(
    requestReport("/api/report", "html", {
      fetchImpl: respond(
        "<!doctype html><html><body>App shell</body></html>",
        "text/html",
      ),
    }),
    (e) => e.code === "invalid_report",
  );
});
