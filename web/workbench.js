const WORKBENCH_URL = "/workbench-ui/workbench";
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);

/** Mount the actual Workbench once; unrelated demo renders must not reset an upload. */
export function mountWorkbench(main) {
  if (main.querySelector(".workbench-view")) return;
  main.innerHTML = `<section class="workbench-view" aria-labelledby="workbench-title">
    <div class="workbench-heading"><div><h1 id="workbench-title">Workbench</h1>
      <p>Upload and explore synthetic PDP files. Sync only when you want to replace dashboard data.</p></div>
      <div class="workbench-actions" hidden><a class="button" href="${WORKBENCH_URL}" target="_blank" rel="noopener">Open separately</a><button class="button primary" type="button" data-workbench-sync>Sync to dashboards…</button></div></div>
    <div class="workbench-status" role="status">Connecting to Workbench…</div>
    <div class="workbench-frame-host"></div>
  </section>`;
  connect(main.querySelector(".workbench-view"));
  main.querySelector("[data-workbench-sync]").addEventListener("click", showSync);
}

/** Probe the isolated services before mounting; offer an explicit retry on failure. */
async function connect(view) {
  const status = view.querySelector(".workbench-status");
  status.textContent = "Connecting to Workbench…";
  try {
    const response = await fetch("/api/workbench", { cache: "no-store", signal: AbortSignal.timeout(15000) });
    const health = await response.json();
    if (!response.ok || !health.ready) throw new Error("unavailable");
    if (!view.isConnected) return;
    if (!health.authenticated) {
      if (!health.configured) {
        status.textContent = "Workbench is running. To enable remote access, set WORKBENCH_ADMIN_TOKEN to at least 32 random characters in the server environment, then restart the app.";
        return;
      }
      showLogin(view);
      return;
    }
    view.querySelector(".workbench-actions").hidden = false;
    status.textContent = "Separate workspace · synthetic data only · uploading alone does not update dashboards";
    const iframe = document.createElement("iframe");
    iframe.title = "PDP Workbench: upload, explore, and field guide";
    iframe.src = WORKBENCH_URL;
    iframe.referrerPolicy = "no-referrer";
    // This is trusted same-origin app code, not an isolation boundary for untrusted pages.
    view.querySelector(".workbench-frame-host").replaceChildren(iframe);
  } catch {
    if (!view.isConnected) return;
    status.innerHTML = '<strong>Workbench is unavailable.</strong><span>It starts with the main app. Restart the app and check its service logs, then retry.</span><button class="button" type="button">Retry connection</button>';
    status.querySelector("button").addEventListener("click", () => connect(view), { once: true });
  }
}

/** Unlock remote uploads with a short-lived HttpOnly session, never browser storage. */
function showLogin(view) {
  const status = view.querySelector(".workbench-status");
  status.innerHTML = `<form class="workbench-login"><div><strong>Unlock Workbench</strong><p>Uploads and dashboard replacement require the server's Workbench credential.</p></div>
    <label>Admin credential <input type="password" name="token" required autocomplete="current-password"></label>
    <button class="button primary" type="submit">Unlock Workbench</button><p role="alert"></p></form>`;
  const form = status.querySelector("form");
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector("button"), input = form.querySelector("input");
    button.disabled = true;
    try {
      const response = await fetch("/api/workbench/login", {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:input.value}), signal:AbortSignal.timeout(10000)});
      const value = await response.json();
      input.value = "";
      if (!response.ok) throw new Error(value.error || "Could not unlock Workbench.");
      await connect(view);
    } catch (error) {
      input.value = "";
      form.querySelector('[role="alert"]').textContent = error.message;
      button.disabled = false;
    }
  });
}

/** Preview both dataset versions and require an explicit synthetic-data confirmation. */
async function showSync() {
  if (document.querySelector(".workbench-sync-dialog")) return;
  const dialog = document.createElement("dialog");
  dialog.className = "workbench-sync-dialog";
  dialog.setAttribute("aria-labelledby", "sync-title");
  dialog.innerHTML = '<h2 id="sync-title">Replace all dashboard data?</h2><div class="sync-preview" role="status">Reading completed datasets…</div><div class="workbench-actions"><button type="button" class="button" data-cancel>Cancel</button></div>';
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.querySelector("[data-cancel]").addEventListener("click", () => dialog.close());
  dialog.showModal();
  const panel = dialog.querySelector(".sync-preview");
  try {
    const response = await fetch("/api/workbench/dataset", {cache:"no-store", signal:AbortSignal.timeout(10000)});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || "Could not preview the dataset.");
    if (value.busy) throw new Error("Workbench is still loading. Wait for it to finish, then reopen this preview.");
    if (!value.workbench.available) throw new Error("Load files in Workbench before syncing.");
    const next = value.workbench, previous = value.current;
    panel.innerHTML = `<p>This replaces <strong>all dashboard tables</strong>, not just the current selection. Workbench keeps its own copy. The last dashboard database is kept as a local backup.</p>
      <dl><dt>Current dashboard</dt><dd>${esc(previous.cohort_rows)} cohort records · ${esc(previous.course_rows)} course enrollments<br><code>${esc(previous.run_id)}</code></dd>
      <dt>Completed Workbench load</dt><dd>${esc(next.students)} students · ${esc(next.cohort_rows)} cohort records · ${esc(next.course_rows)} course enrollments<br><code>${esc(next.run_id)}</code></dd>
      <dt>Entry cohorts</dt><dd>${esc(next.cohorts.join(", "))}</dd><dt>Source files</dt><dd>${next.sources.map(s=>esc(s.file)).join("<br>")}</dd></dl>
      <p>The page will reload. Filters and chat reset; saved views and student follow-ups remain stored with their original dataset. Modeling may be unavailable if this dataset is too small.</p>
      <label class="sync-attestation"><input type="checkbox" data-synthetic> These files contain only synthetic data, not real student records.</label>
      <p class="sync-error" role="alert"></p>`;
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "button primary";
    confirm.textContent = "Replace dashboard data";
    confirm.disabled = true;
    dialog.querySelector(".workbench-actions").append(confirm);
    panel.querySelector("[data-synthetic]").addEventListener("change", event => { confirm.disabled = !event.target.checked; });
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      dialog.querySelector("[data-cancel]").disabled = true;
      panel.querySelector("[data-synthetic]").disabled = true;
      confirm.textContent = "Replacing…";
      const preventClose = event => event.preventDefault();
      dialog.addEventListener("cancel", preventClose);
      try {
        const response = await fetch("/api/workbench/sync", {
          method:"POST", headers:{"Content-Type":"application/json", "X-PDP-Action":"replace-dashboard"},
          body:JSON.stringify({confirm:"REPLACE ALL DASHBOARD DATA", synthetic:true, workbench_run_id:next.run_id, current_run_id:previous.run_id}),
          signal:AbortSignal.timeout(90000),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Sync failed. Reopen the preview before retrying.");
        location.hash = "evidence";
        location.reload();
      } catch (error) {
        panel.querySelector(".sync-error").textContent = `${error.message} Close this dialog and reopen the preview to check the current dataset before retrying.`;
        confirm.textContent = "Preview again before retrying";
        dialog.querySelector("[data-cancel]").disabled = false;
      } finally { dialog.removeEventListener("cancel", preventClose); }
    });
  } catch (error) { panel.textContent = error.message; }
}
