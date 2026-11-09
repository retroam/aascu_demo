import test from "node:test";
import assert from "node:assert/strict";
import {initializeDataset, datasetStorageKey, datasetChanged} from "../web/dataset-state.js";

test("browser data is scoped by dataset and other-tab replacement is detected", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({ok:true, json:async()=>({dataset:{run_id:"original", origin:"starter"}})});
    await initializeDataset();
    assert.equal(datasetStorageKey("followups"), "followups");
    assert.equal(datasetChanged({run_id:"original", origin:"starter"}), false);
    assert.equal(datasetChanged({run_id:"upload-a", origin:"workbench"}), true);
    globalThis.fetch = async () => ({ok:true, json:async()=>({dataset:{run_id:"upload-a", origin:"workbench"}})});
    await initializeDataset();
    assert.equal(datasetStorageKey("followups"), "followups:upload-a");
    assert.equal(datasetChanged({run_id:"upload-b", origin:"workbench"}), true);
    assert.equal(datasetChanged({run_id:"upload-a", origin:"workbench"}), false);
    globalThis.fetch = async () => { throw new Error("offline"); };
    await initializeDataset();
    assert.throws(() => datasetStorageKey("followups"), /dataset/i);
    assert.equal(datasetChanged({run_id:"upload-a", origin:"workbench"}), true);
  } finally { globalThis.fetch = original; }
});
