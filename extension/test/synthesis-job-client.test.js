const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createSynthesisJobClient } = require("../src/lib/synthesis-job-client");
const { EXTENSION_CLIENT_ID_HEADER, createBackendFetch } = require("../src/lib/backend-fetch");

function endpointFor(base, route) {
  return `${base}${route}`;
}

function response(status, body = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return body; }
  };
}

function nextTurn() {
  return new Promise((resolve) => setImmediate(resolve));
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, reject, resolve };
}

function cancelled() {
  const error = new Error("cancelled");
  error.name = "AbortError";
  return error;
}

function controlledRequestTimers() {
  const handles = [];
  return {
    handles,
    schedule(callback, milliseconds) {
      const handle = { callback, milliseconds, cancelled: false };
      handles.push(handle);
      return handle;
    },
    cancel(handle) { handle.cancelled = true; },
    fireActive() {
      const handle = handles.findLast((candidate) => !candidate.cancelled);
      assert.ok(handle, "expected an active request timeout");
      handle.callback();
    }
  };
}

test("creates, polls, parses, and deletes a completed synthesis job", async () => {
  const requests = [];
  const created = [];
  const cleared = [];
  const replies = [
    response(202, { job_id: "job one", status: "pending" }),
    response(200, { job_id: "job one", status: "pending" }),
    response(200, {
      job_id: "job one",
      status: "completed",
      result: { audio_base64: "V0FW", mime_type: "audio/wav" }
    }),
    response(204)
  ];
  const delays = [];
  const fetchImpl = createBackendFetch({
    extensionId: "abcdefghijklmnopabcdefghijklmnop",
    getAccessToken: async () => "test-invite-token",
    async fetchImpl(url, options) {
      requests.push({ url, options });
      return replies.shift();
    }
  });
  const client = createSynthesisJobClient({
    endpointFor,
    delay: async (milliseconds) => { delays.push(milliseconds); },
    fetchImpl
  });

  const result = await client.synthesize({
    backendUrl: "https://tts.example",
    text: "今天天氣真好",
    rate: 0.75,
    token: 7,
    onCreated: (job) => created.push(job),
    onCleared: (job) => cleared.push(job)
  });

  assert.deepEqual(result, { base64: "V0FW", mimeType: "audio/wav" });
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    text: "今天天氣真好",
    source_language: "zh-TW",
    target_language: "nan-TW",
    rate: 0.75
  });
  assert.deepEqual(requests.map(({ url, options }) => [options.method, url]), [
    ["POST", "https://tts.example/v1/synthesis-jobs"],
    ["GET", "https://tts.example/v1/synthesis-jobs/job%20one"],
    ["GET", "https://tts.example/v1/synthesis-jobs/job%20one"],
    ["DELETE", "https://tts.example/v1/synthesis-jobs/job%20one"]
  ]);
  for (const { options } of requests) {
    assert.equal(options.headers.get(EXTENSION_CLIENT_ID_HEADER), "abcdefghijklmnopabcdefghijklmnop");
  }
  assert.equal(requests[0].options.headers.get("Content-Type"), "application/json");
  assert.deepEqual(delays, [1_000]);
  assert.deepEqual(created, [{ jobId: "job one", backendUrl: "https://tts.example", token: 7 }]);
  assert.deepEqual(cleared, created);
});

test("preserves a failed job's original error when DELETE cleanup also fails", async () => {
  const methods = [];
  const client = createSynthesisJobClient({
    endpointFor,
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") return response(202, { job_id: "failed-job", status: "pending" });
      if (options.method === "GET") return response(200, { status: "failed", error: "台語轉換失敗" });
      return response(503, { detail: "清理暫時失敗" });
    }
  });

  await assert.rejects(
    client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 }),
    /台語轉換失敗/
  );
  assert.deepEqual(methods, ["POST", "GET", "DELETE"]);
});

test("preserves GET 404 while still attempting DELETE cleanup", async () => {
  const methods = [];
  const client = createSynthesisJobClient({
    endpointFor,
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") return response(202, { job_id: "missing", status: "pending" });
      if (options.method === "GET") return response(404, { detail: "synthesis job not found" });
      return response(404, { detail: "already gone" });
    }
  });

  await assert.rejects(
    client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 }),
    /synthesis job not found/
  );
  assert.deepEqual(methods, ["POST", "GET", "DELETE"]);
});

test("returns completed audio when DELETE or onCleared cleanup fails", async () => {
  for (const mode of ["delete", "callback"]) {
    const client = createSynthesisJobClient({
      endpointFor,
      async fetchImpl(_url, options) {
        if (options.method === "POST") return response(202, { job_id: mode, status: "pending" });
        if (options.method === "GET") {
          return response(200, {
            status: "completed",
            result: { audio_base64: "UklGRg==", mime_type: "audio/wav" }
          });
        }
        return mode === "delete" ? response(500, { detail: "cleanup failed" }) : response(204);
      }
    });

    assert.deepEqual(await client.synthesize({
      backendUrl: "https://tts.example",
      text: "新聞",
      rate: 1,
      onCleared: mode === "callback" ? async () => { throw new Error("storage failed"); } : undefined
    }), { base64: "UklGRg==", mimeType: "audio/wav" });
  }
});

test("STOP aborts polling and DELETEs the known job", async () => {
  const waiting = deferred();
  const methods = [];
  const cleared = [];
  const client = createSynthesisJobClient({
    endpointFor,
    delay: (_milliseconds, signal) => {
      signal.addEventListener("abort", () => waiting.reject(cancelled()), { once: true });
      return waiting.promise;
    },
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") return response(202, { job_id: "pending-job", status: "pending" });
      if (options.method === "GET") return response(200, { status: "pending" });
      return response(204);
    }
  });

  const synthesis = client.synthesize({
    backendUrl: "https://tts.example",
    text: "新聞",
    rate: 1,
    token: 2,
    onCleared: (job) => cleared.push(job)
  });
  await nextTurn();
  await client.cancel();
  await assert.rejects(synthesis, { name: "AbortError" });
  assert.deepEqual(methods, ["POST", "GET", "DELETE"]);
  assert.deepEqual(cleared, [{ jobId: "pending-job", backendUrl: "https://tts.example", token: 2 }]);
});

test("STOP waits for an in-flight POST and immediately DELETEs its returned job", async () => {
  const createReply = deferred();
  const methods = [];
  let createSignal;
  const client = createSynthesisJobClient({
    endpointFor,
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") {
        createSignal = options.signal;
        return createReply.promise;
      }
      return response(204);
    }
  });

  const synthesis = client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 });
  await nextTurn();
  const stopping = client.cancel();
  await nextTurn();
  assert.equal(createSignal.aborted, false, "STOP must not lose an unknown server-generated job id");
  createReply.resolve(response(202, { job_id: "late-job", status: "pending" }));

  await stopping;
  await assert.rejects(synthesis, { name: "AbortError" });
  assert.deepEqual(methods, ["POST", "DELETE"]);
});

test("STOP bounds a create request that never settles", async () => {
  let fireTimeout;
  let createSignal;
  const client = createSynthesisJobClient({
    endpointFor,
    createSettleTimeoutMs: 25,
    schedule(callback) {
      fireTimeout = callback;
      return 19;
    },
    cancelScheduled() {},
    fetchImpl(_url, options) {
      createSignal = options.signal;
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(cancelled()), { once: true });
      });
    }
  });

  const synthesis = client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 });
  const stopping = client.cancel();
  await nextTurn();
  assert.equal(createSignal.aborted, false);
  fireTimeout();
  await stopping;
  assert.equal(createSignal.aborted, true);
  await assert.rejects(synthesis, { name: "AbortError" });
});

test("a stale run's finally cannot clear a newer active run", async () => {
  const delays = [];
  let jobs = 0;
  const deleted = [];
  const client = createSynthesisJobClient({
    endpointFor,
    delay() {
      const pending = deferred();
      delays.push(pending);
      return pending.promise;
    },
    async fetchImpl(url, options) {
      if (options.method === "POST") {
        jobs += 1;
        return response(202, { job_id: `job-${jobs}`, status: "pending" });
      }
      if (options.method === "GET") return response(200, { status: "pending" });
      deleted.push(url.split("/").at(-1));
      return response(204);
    }
  });

  const first = client.synthesize({ backendUrl: "https://tts.example", text: "第一段", rate: 1 });
  await nextTurn();
  await client.cancel();
  const second = client.synthesize({ backendUrl: "https://tts.example", text: "第二段", rate: 1 });
  await nextTurn();

  delays[0].reject(cancelled());
  await assert.rejects(first, { name: "AbortError" });
  await client.cancel();
  delays[1].reject(cancelled());
  await assert.rejects(second, { name: "AbortError" });
  assert.deepEqual(deleted, ["job-1", "job-2"]);
});

test("poll deadline is enforced and its timeout survives cleanup failure", async () => {
  let clock = 0;
  const methods = [];
  const client = createSynthesisJobClient({
    endpointFor,
    now: () => clock,
    deadlineMs: 5,
    delay: async () => { clock = 5; },
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") return response(202, { job_id: "slow", status: "pending" });
      if (options.method === "GET") return response(200, { status: "pending" });
      return response(500, { detail: "delete failed" });
    }
  });

  await assert.rejects(
    client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 }),
    /等候逾時/
  );
  assert.deepEqual(methods, ["POST", "GET", "DELETE"]);
});

test("request timeout covers a GET body that stalls after headers", async () => {
  const timers = controlledRequestTimers();
  const methods = [];
  const client = createSynthesisJobClient({
    endpointFor,
    requestTimeoutMs: 25,
    requestSchedule: timers.schedule,
    cancelRequestScheduled: timers.cancel,
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") return response(202, { job_id: "slow-body", status: "pending" });
      if (options.method === "GET") {
        return { ok: true, status: 200, json: () => new Promise(() => {}) };
      }
      return response(204);
    }
  });

  const synthesis = client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 });
  await nextTurn();
  timers.fireActive();
  await assert.rejects(synthesis, { name: "TimeoutError", message: /請求逾時/ });
  assert.deepEqual(methods, ["POST", "GET", "DELETE"]);
});

test("STOP aborts a GET body that stalls after headers", async () => {
  const methods = [];
  const client = createSynthesisJobClient({
    endpointFor,
    async fetchImpl(_url, options) {
      methods.push(options.method);
      if (options.method === "POST") return response(202, { job_id: "body-stop", status: "pending" });
      if (options.method === "GET") {
        return { ok: true, status: 200, json: () => new Promise(() => {}) };
      }
      return response(204);
    }
  });

  const synthesis = client.synthesize({ backendUrl: "https://tts.example", text: "新聞", rate: 1 });
  await nextTurn();
  await client.cancel();
  await assert.rejects(synthesis, { name: "AbortError" });
  assert.deepEqual(methods, ["POST", "GET", "DELETE"]);
});

test("a DELETE request that never returns is bounded", async () => {
  const timers = controlledRequestTimers();
  const client = createSynthesisJobClient({
    endpointFor,
    requestTimeoutMs: 25,
    requestSchedule: timers.schedule,
    cancelRequestScheduled: timers.cancel,
    fetchImpl(_url, options) {
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(cancelled()), { once: true });
      });
    }
  });

  const deletion = client.deleteJob("https://tts.example", "hung-delete");
  timers.fireActive();
  await assert.rejects(deletion, { name: "TimeoutError", message: /請求逾時/ });
});

test("service worker owns only short job requests and offscreen owns only audio", () => {
  const root = path.join(__dirname, "..", "src");
  const worker = fs.readFileSync(path.join(root, "service-worker.js"), "utf8");
  const offscreen = fs.readFileSync(path.join(root, "offscreen.js"), "utf8");
  assert.match(worker, /createSynthesisJobClient/);
  assert.match(worker, /getPlatformInfo/);
  assert.match(worker, /activeSynthesisJob|ACTIVE_JOB_KEY/);
  assert.match(worker, /\["preparing", "playing", "paused"\]/);
  assert.match(worker, /if \(interrupted\)[\s\S]*target: "offscreen", type: "STOP"/);
  assert.match(worker, /async function stop[\s\S]*cleanupStoredOrphan\(\)/);
  assert.match(worker, /PREPARING", index \}, id\);\s*if \(id !== runId\) return;\s*const audio/);
  assert.match(worker, /PLAYING", index \}, id\);\s*if \(id !== runId\) return;\s*const result/);
  assert.match(worker, /reasons:\s*\["AUDIO_PLAYBACK", "BLOBS"\]/);
  assert.doesNotMatch(worker, /type:\s*"SYNTHESIZE"|case "KEEP_ALIVE"/);
  assert.match(offscreen, /new Blob/);
  assert.doesNotMatch(offscreen, /\bfetch\b|SYNTHESIZE|createSynthesisJobClient|createTaskKeepAlive/);
});
