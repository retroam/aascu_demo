import { datasetVersion } from "./dataset-state.js";

export class RequestError extends Error {
  constructor(message, code, status = null, details = null) {
    super(message);
    this.name = "RequestError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}
const connectionMessage =
  "The app server is unavailable. Start npm run dev in the demo folder, then select Reconnect.";
async function request(path, options, consume) {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? 30000,
  );
  try {
    const response = await (options.fetchImpl ?? fetch)(path, {
      method: options.body === undefined ? "GET" : "POST",
      headers: {
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(datasetVersion() ? {"X-PDP-Dataset": datasetVersion()} : {}),
      },
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
      cache: "no-store",
    });
    const version = response.headers.get("X-PDP-Dataset");
    if (version && version !== datasetVersion()) {
      globalThis.location?.reload();
      throw new RequestError("The dataset changed. Reloading this workspace before using new results.", "dataset_changed");
    }
    return await consume(response);
  } catch (error) {
    if (error instanceof RequestError) throw error;
    if (controller.signal.aborted)
      throw new RequestError(
        "The request timed out. Select Retry to try again.",
        "timeout",
      );
    throw new RequestError(connectionMessage, "connection");
  } finally {
    clearTimeout(timeout);
  }
}
async function ensureSuccess(response) {
  if (response.ok) return;
  let message = `The server could not complete the request (HTTP ${response.status}).`;
  let details = null;
  if (response.headers.get("content-type")?.includes("application/json")) {
    try {
      const body = await response.json();
      if (typeof body.error === "string") message = body.error;
      details = body;
    } catch {
      /* Preserve the HTTP error. */
    }
  }
  throw new RequestError(message, "http", response.status, details);
}
export async function requestJSON(path, options = {}) {
  return request(path, options, async (response) => {
    await ensureSuccess(response);
    if (!response.headers.get("content-type")?.includes("application/json"))
      throw new RequestError(
        "This page is not connected to the app server. Open the address printed by npm run dev (normally http://127.0.0.1:8080).",
        "unexpected_response",
      );
    try {
      return await response.json();
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new RequestError(
        "The server returned an unreadable response. Select Retry to try again.",
        "invalid_response",
      );
    }
  });
}
export async function requestReport(path, format, options = {}) {
  if (!["html", "csv"].includes(format))
    throw new RequestError("Choose HTML or CSV.", "format");
  return request(path, options, async (response) => {
    await ensureSuccess(response);
    const expectedType = format === "csv" ? "text/csv" : "text/html";
    if (!response.headers.get("content-type")?.includes(expectedType))
      throw new RequestError(
        "The server did not return a report. No file was downloaded.",
        "invalid_report",
      );
    const content = await response.text();
    if (
      !content.trim() ||
      (format === "csv"
        ? !content.startsWith("metric,")
        : !/^<!doctype html>/i.test(content.trim()))
    )
      throw new RequestError(
        "The report is empty or unreadable. No file was downloaded.",
        "invalid_report",
      );
    const disposition = response.headers.get("content-disposition") || "";
    const requestedName = disposition.match(
      /filename="([A-Za-z0-9._-]+)"/,
    )?.[1];
    if (
      !disposition.startsWith("attachment;") ||
      !requestedName?.endsWith(`.${format}`)
    ) {
      throw new RequestError(
        "This response is not a report from the app server. No file was downloaded.",
        "invalid_report",
      );
    }
    return {
      content,
      name: requestedName,
      type: `${expectedType}; charset=utf-8`,
      format,
    };
  });
}
