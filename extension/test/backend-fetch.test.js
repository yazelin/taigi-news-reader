const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  AUTHORIZATION_HEADER,
  EXTENSION_CLIENT_ID_HEADER,
  createBackendFetch
} = require("../src/lib/backend-fetch");

const EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop";

test("backend fetch strips auth from public health and immutably authenticates access, jobs, and cleanup", async () => {
  const requests = [];
  const originalHeaders = new Headers({
    "Content-Type": "application/json",
    [EXTENSION_CLIENT_ID_HEADER]: "caller-supplied-value",
    [AUTHORIZATION_HEADER]: "Bearer caller-supplied-secret"
  });
  const backendFetch = createBackendFetch({
    extensionId: EXTENSION_ID,
    getAccessToken: async () => "private-tester-token",
    async fetchImpl(url, options) {
      requests.push({ url, options });
      return { ok: true };
    }
  });

  await backendFetch("https://tts.example/health");
  await backendFetch("https://tts.example/v1/access");
  await backendFetch("https://tts.example/v1/synthesis-jobs/one", { method: "GET" });
  await backendFetch("https://tts.example/v1/synthesis-jobs/one", { method: "DELETE" });
  await backendFetch("https://tts.example/v1/synthesis-jobs", {
    method: "POST",
    headers: originalHeaders,
    credentials: "include",
    redirect: "follow"
  });

  assert.deepEqual(requests.map(({ url, options }) => [options.method || "GET", url]), [
    ["GET", "https://tts.example/health"],
    ["GET", "https://tts.example/v1/access"],
    ["GET", "https://tts.example/v1/synthesis-jobs/one"],
    ["DELETE", "https://tts.example/v1/synthesis-jobs/one"],
    ["POST", "https://tts.example/v1/synthesis-jobs"]
  ]);
  for (const { options } of requests) {
    assert.equal(options.headers.get(EXTENSION_CLIENT_ID_HEADER), EXTENSION_ID);
    assert.equal(options.credentials, "omit");
    assert.equal(options.redirect, "error");
  }
  assert.equal(requests[0].options.headers.get(AUTHORIZATION_HEADER), null, "public health never receives the token");
  for (const { options } of requests.slice(1)) {
    assert.equal(options.headers.get(AUTHORIZATION_HEADER), "Bearer private-tester-token");
  }
  assert.equal(requests[4].options.headers.get("Content-Type"), "application/json");
  assert.equal(originalHeaders.get(EXTENSION_CLIENT_ID_HEADER), "caller-supplied-value", "caller headers are not mutated");
  assert.equal(originalHeaders.get(AUTHORIZATION_HEADER), "Bearer caller-supplied-secret", "caller auth is not mutated");
});

test("backend fetch resolves the locally stored token for every request and never sends a missing token", async () => {
  const seen = [];
  let token = "first-token";
  const backendFetch = createBackendFetch({
    extensionId: EXTENSION_ID,
    getAccessToken: async () => token,
    async fetchImpl(_url, options) {
      seen.push(options.headers.get(AUTHORIZATION_HEADER));
      return { ok: true };
    }
  });

  await backendFetch("https://tts.example/v1/access");
  token = "token-after-worker-restart";
  await backendFetch("https://tts.example/v1/synthesis-jobs/orphan", { method: "DELETE" });
  token = "";
  await backendFetch("https://tts.example/health");
  await assert.rejects(backendFetch("https://tts.example/v1/access"), /邀請碼/);
  assert.deepEqual(seen, ["Bearer first-token", "Bearer token-after-worker-restart", null]);
});

test("all extension backend composition roots use the shared fetch wrapper", () => {
  const source = path.join(__dirname, "..", "src");
  const worker = fs.readFileSync(path.join(source, "service-worker.js"), "utf8");
  const sidepanel = fs.readFileSync(path.join(source, "sidepanel.js"), "utf8");
  const options = fs.readFileSync(path.join(source, "options.js"), "utf8");

  assert.match(worker, /const backendFetch = createBackendFetch/);
  assert.match(worker, /getAccessToken: \(requestUrl\) => storedAccessToken\(chrome\.storage\.local, requestUrl\)/);
  assert.equal(worker.match(/fetchImpl: backendFetch/g)?.length, 2);
  assert.match(sidepanel, /backendFetch\(endpoint\(settings\.backendUrl, "\/v1\/access"\)/);
  assert.match(options, /candidateBackendFetch\(backendUrl, accessToken\)\(endpoint\(backendUrl, "\/v1\/access"\)/);
});
