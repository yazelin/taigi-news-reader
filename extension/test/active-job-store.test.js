const test = require("node:test");
const assert = require("node:assert/strict");
const { ACTIVE_JOB_KEY, createActiveJobStore } = require("../src/lib/active-job-store");
const { createSynthesisJobClient } = require("../src/lib/synthesis-job-client");

function memoryStorage() {
  const values = {};
  return {
    values,
    async get(key) { return { [key]: values[key] }; },
    async set(update) { Object.assign(values, update); },
    async remove(key) { delete values[key]; }
  };
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

test("persists only the active job identity needed for restart cleanup", async () => {
  const storage = memoryStorage();
  const store = createActiveJobStore(storage);
  await store.record({
    jobId: "job-7",
    backendUrl: "https://tts.example",
    token: 9,
    text: "不得保存的新聞",
    audio: "不得保存的音訊"
  });

  assert.deepEqual(storage.values, {
    [ACTIVE_JOB_KEY]: {
      jobId: "job-7",
      backendUrl: "https://tts.example",
      runId: 9
    }
  });
});

test("a stale callback cannot clear a newer job", async () => {
  const storage = memoryStorage();
  const store = createActiveJobStore(storage);
  const oldJob = { jobId: "old", backendUrl: "https://old.example", token: 1 };
  const newJob = { jobId: "new", backendUrl: "https://new.example", token: 2 };

  await store.record(oldJob);
  const recording = store.record(newJob);
  const staleClear = store.clearIfOwner(oldJob);
  await recording;
  assert.equal(await staleClear, false);
  assert.deepEqual(await store.get(), { jobId: "new", backendUrl: "https://new.example", runId: 2 });
});

test("late job identities never overwrite a newer run", async () => {
  const storage = memoryStorage();
  const store = createActiveJobStore(storage);
  const newer = { jobId: "new", backendUrl: "https://new.example", token: 8 };
  const lateOld = { jobId: "old", backendUrl: "https://old.example", token: 7 };

  assert.equal(await store.recordLatest(newer), true);
  assert.equal(await store.recordLatest(lateOld), false);
  assert.deepEqual(await store.get(), { jobId: "new", backendUrl: "https://new.example", runId: 8 });
});

test("record and matching clear are serialized during a START/STOP race", async () => {
  const storage = memoryStorage();
  const store = createActiveJobStore(storage);
  const job = { jobId: "late-create", backendUrl: "https://tts.example", token: 4 };

  const recording = store.record(job);
  const clearing = store.clearIfOwner(job);
  await Promise.all([recording, clearing]);
  assert.equal(await store.get(), null);
});

test("a retained cleanup orphan can be retried by STOP or startup", async () => {
  const storage = memoryStorage();
  const store = createActiveJobStore(storage);
  let deletes = 0;
  const client = createSynthesisJobClient({
    endpointFor: (base, route) => `${base}${route}`,
    async fetchImpl(_url, options) {
      if (options.method === "POST") {
        return { ok: true, status: 202, async json() { return { job_id: "retry-me", status: "pending" }; } };
      }
      if (options.method === "GET") {
        return {
          ok: true,
          status: 200,
          async json() {
            return { status: "completed", result: { audio_base64: "V0FW", mime_type: "audio/wav" } };
          }
        };
      }
      deletes += 1;
      return deletes === 1
        ? { ok: false, status: 503, async json() { return { detail: "retry later" }; } }
        : { ok: true, status: 204, async json() { return {}; } };
    }
  });
  const identity = { jobId: "retry-me", backendUrl: "https://tts.example", token: 3 };

  const audio = await client.synthesize({
    backendUrl: identity.backendUrl,
    text: "新聞",
    rate: 1,
    token: identity.token,
    onCreated: (job) => store.record(job),
    onCleared: (job) => store.clearIfOwner(job)
  });
  assert.deepEqual(audio, { base64: "V0FW", mimeType: "audio/wav" });
  assert.deepEqual(await store.get(), { jobId: "retry-me", backendUrl: "https://tts.example", runId: 3 });

  await client.deleteJob(identity.backendUrl, identity.jobId);
  await store.clearIfOwner(identity);
  assert.equal(await store.get(), null);
  assert.equal(deletes, 2);
});

test("late POST plus failed STOP cleanup retains the orphan identity", async () => {
  const storage = memoryStorage();
  const store = createActiveJobStore(storage);
  const createReply = deferred();
  let deletes = 0;
  const client = createSynthesisJobClient({
    endpointFor: (base, route) => `${base}${route}`,
    async fetchImpl(_url, options) {
      if (options.method === "POST") return createReply.promise;
      deletes += 1;
      return {
        ok: false,
        status: 503,
        async json() { return { detail: "DELETE cleanup failed" }; }
      };
    }
  });
  const run = client.synthesize({
    backendUrl: "https://tts.example",
    text: "新聞",
    rate: 1,
    token: 4,
    onCreated: (job) => store.recordLatest(job),
    onCleared: (job) => store.clearIfOwner(job)
  });
  const stopping = client.cancel();
  createReply.resolve({
    ok: true,
    status: 202,
    async json() { return { job_id: "late-job", status: "pending" }; }
  });

  await assert.rejects(stopping, /DELETE cleanup failed/);
  await assert.rejects(run, { name: "AbortError" });
  assert.deepEqual(await store.get(), {
    jobId: "late-job",
    backendUrl: "https://tts.example",
    runId: 4
  });
  await assert.rejects(client.deleteJob("https://tts.example", "late-job"), /DELETE cleanup failed/);
  assert.equal(deletes, 2);
  assert.equal((await store.get()).jobId, "late-job");
});
