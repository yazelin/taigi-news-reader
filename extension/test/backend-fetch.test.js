const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  EXTENSION_CLIENT_ID_HEADER,
  createBackendFetch
} = require("../src/lib/backend-fetch");

const EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop";

test("backend fetch adds the non-secret extension ID to health, GET, and DELETE requests", async () => {
  const requests = [];
  const originalHeaders = new Headers({
    "Content-Type": "application/json",
    [EXTENSION_CLIENT_ID_HEADER]: "caller-supplied-value"
  });
  const backendFetch = createBackendFetch({
    extensionId: EXTENSION_ID,
    async fetchImpl(url, options) {
      requests.push({ url, options });
      return { ok: true };
    }
  });

  await backendFetch("https://tts.example/health");
  await backendFetch("https://tts.example/v1/synthesis-jobs/one", { method: "GET" });
  await backendFetch("https://tts.example/v1/synthesis-jobs/one", { method: "DELETE" });
  await backendFetch("https://tts.example/v1/synthesis-jobs", { method: "POST", headers: originalHeaders });

  assert.deepEqual(requests.map(({ url, options }) => [options.method || "GET", url]), [
    ["GET", "https://tts.example/health"],
    ["GET", "https://tts.example/v1/synthesis-jobs/one"],
    ["DELETE", "https://tts.example/v1/synthesis-jobs/one"],
    ["POST", "https://tts.example/v1/synthesis-jobs"]
  ]);
  for (const { options } of requests) {
    assert.equal(options.headers.get(EXTENSION_CLIENT_ID_HEADER), EXTENSION_ID);
  }
  assert.equal(requests[3].options.headers.get("Content-Type"), "application/json");
  assert.equal(originalHeaders.get(EXTENSION_CLIENT_ID_HEADER), "caller-supplied-value", "caller headers are not mutated");
});

test("all extension backend composition roots use the shared fetch wrapper", () => {
  const source = path.join(__dirname, "..", "src");
  const worker = fs.readFileSync(path.join(source, "service-worker.js"), "utf8");
  const sidepanel = fs.readFileSync(path.join(source, "sidepanel.js"), "utf8");
  const options = fs.readFileSync(path.join(source, "options.js"), "utf8");

  assert.match(worker, /const backendFetch = createBackendFetch/);
  assert.equal(worker.match(/fetchImpl: backendFetch/g)?.length, 2);
  assert.match(sidepanel, /backendFetch\(endpoint\(settings\.backendUrl, "\/health"\)/);
  assert.match(options, /backendFetch\(endpoint\(backendUrl, "\/health"\)/);
});
