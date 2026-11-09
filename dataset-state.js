let current = null;

/** Initialize the dataset before restoring any browser-local records or saved views. */
export async function initializeDataset() {
  current = null;
  try {
    const response = await fetch("/api/health", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (response.ok) current = (await response.json()).dataset ?? null;
  } catch { /* The app's existing connection state presents failures. */ }
}

/** Preserve old browser data without attaching it to records in a different upload. */
export function datasetStorageKey(base) {
  if (!current?.run_id) throw new Error("Dataset identity is not known yet.");
  return current?.origin === "workbench" ? `${base}:${current.run_id}` : base;
}

/** Match every API response to the dataset whose browser state is currently mounted. */
export function datasetVersion() {
  return current?.run_id ? `${current.origin}:${current.run_id}` : null;
}

/** Detect a replacement in another tab before reusing its previous dataset context. */
export function datasetChanged(next) {
  if (!next?.run_id) return false;
  if (!current) return true;
  return current.run_id !== next.run_id || current.origin !== next.origin;
}
