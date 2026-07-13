const test = require("node:test");
const assert = require("node:assert/strict");
const {
  REPLAY_HISTORY_KEY,
  REPLAY_PREFERENCES_KEY,
  arrayBufferToBase64,
  base64ToArrayBuffer,
  createReplayCache,
  createReplayCacheKey,
  resolveReplayStart
} = require("../src/lib/replay-cache");

function memoryStorage(initial = {}) {
  const values = structuredClone(initial);
  return {
    values,
    async get(key) { return { [key]: structuredClone(values[key]) }; },
    async set(next) { Object.assign(values, structuredClone(next)); },
    async remove(key) { delete values[key]; }
  };
}

function memoryAudioStore() {
  const values = new Map();
  return {
    values,
    async get(id) { return values.has(id) ? structuredClone(values.get(id)) : undefined; },
    async put(entry) { values.set(entry.id, structuredClone(entry)); },
    async delete(id) { values.delete(id); },
    async clear() { values.clear(); },
    async keys() { return [...values.keys()]; }
  };
}

function fixture({ now = () => 1_000, maxEntries = 5, maxBytes = 1024, ttlMs = 10_000 } = {}) {
  const storageArea = memoryStorage();
  const audioStore = memoryAudioStore();
  const cache = createReplayCache({ storageArea, audioStore, now, maxEntries, maxBytes, ttlMs });
  return { audioStore, cache, storageArea };
}

function audio(text = "WAV") {
  return { base64: Buffer.from(text).toString("base64"), mimeType: "audio/wav" };
}

test("replay history is opt-in and disabling it deletes metadata and audio", async () => {
  const { audioStore, cache, storageArea } = fixture();
  assert.equal(await cache.enabled(), false);
  assert.deepEqual(await cache.put({ id: "one", title: "新聞", rate: 1, chunks: [audio()] }), {
    saved: false,
    reason: "disabled"
  });

  await cache.setEnabled(true);
  assert.equal(storageArea.values[REPLAY_PREFERENCES_KEY].enabled, true);
  assert.equal((await cache.put({ id: "one", title: "新聞", rate: 1, chunks: [audio()] })).saved, true);
  assert.equal(audioStore.values.size, 1);

  await cache.setEnabled(false);
  assert.equal(storageArea.values[REPLAY_PREFERENCES_KEY].enabled, false);
  assert.equal(storageArea.values[REPLAY_HISTORY_KEY], undefined);
  assert.equal(audioStore.values.size, 0);
});

test("stores only bounded display metadata and reconstructs ordered audio chunks", async () => {
  const { cache, storageArea } = fixture();
  await cache.setEnabled(true);
  const result = await cache.put({
    id: "opaque-hash",
    title: "  測試   新聞  ",
    rate: 0.75,
    chunks: [audio("first"), audio("second")]
  });
  assert.equal(result.saved, true);
  assert.deepEqual(await cache.list(), [{
    id: "opaque-hash",
    title: "測試 新聞",
    createdAt: 1_000,
    lastPlayedAt: 1_000,
    rate: 0.75,
    chunkCount: 2,
    bytes: 11,
    service: { mode: "unknown", translator: "", synthesizer: "" }
  }]);
  assert.equal(JSON.stringify(storageArea.values).includes("first"), false);
  assert.equal(JSON.stringify(storageArea.values).includes("https://"), false);

  const replay = await cache.get("opaque-hash", { touch: false });
  assert.deepEqual(replay.chunks, [audio("first"), audio("second")]);
});

test("cache key is deterministic and separates rate, normalized content, URL, and provider identity", async () => {
  const base = {
    chunks: ["第一段", "第二段"],
    rate: 1,
    backendUrl: "https://one.example",
    backendIdentity: '{"mode":"concrete","translator":"gemini","synthesizer":"mms"}'
  };
  const first = await createReplayCacheKey(base);
  assert.match(first, /^[a-f0-9]{64}$/);
  assert.equal(await createReplayCacheKey({ ...base }), first);
  assert.equal(await createReplayCacheKey({ ...base, chunks: ["  第一段  ", "第二段"] }), first);
  assert.notEqual(await createReplayCacheKey({ ...base, rate: 0.75 }), first);
  assert.notEqual(await createReplayCacheKey({ ...base, chunks: ["不同內容"] }), first);
  assert.notEqual(await createReplayCacheKey({ ...base, backendUrl: "https://two.example" }), first);
  assert.notEqual(await createReplayCacheKey({
    ...base,
    backendIdentity: '{"mode":"mock","translator":"mock","synthesizer":"mock"}'
  }), first);
});

test("stored provider cache hit skips the live health resolver", async () => {
  const stored = {
    identity: "stored-provider",
    service: { mode: "concrete", translator: "gemini", synthesizer: "mms" }
  };
  let resolveCalls = 0;
  const cached = { chunks: [audio()] };

  const result = await resolveReplayStart({
    cacheEnabled: true,
    chunks: ["新聞"],
    rate: 1,
    backendUrl: "https://tts.example",
    identityResolver: {
      stored: async () => stored,
      resolve: async () => { resolveCalls += 1; return stored; }
    },
    keyFor: async ({ backendIdentity }) => backendIdentity,
    getCached: async () => cached
  });

  assert.equal(resolveCalls, 0);
  assert.equal(result.cacheKey, "stored-provider");
  assert.equal(result.cached, cached);
  assert.equal(result.backendIdentity, stored);
  assert.equal(result.cacheWriteEnabled, false);
});

test("cache miss probes health and separates a changed provider identity", async () => {
  const stored = {
    identity: "provider-a",
    service: { mode: "concrete", translator: "translator-a", synthesizer: "tts-a" }
  };
  const live = {
    identity: "provider-b",
    service: { mode: "concrete", translator: "translator-b", synthesizer: "tts-b" }
  };
  const lookups = [];
  const cached = { chunks: [audio()] };

  const result = await resolveReplayStart({
    cacheEnabled: true,
    chunks: ["新聞"],
    rate: 1,
    backendUrl: "https://tts.example",
    identityResolver: { stored: async () => stored, resolve: async () => live },
    keyFor: async ({ backendIdentity }) => backendIdentity,
    getCached: async (id) => {
      lookups.push(id);
      return id === "provider-b" ? cached : null;
    }
  });

  assert.deepEqual(lookups, ["provider-a", "provider-b"]);
  assert.equal(result.cacheKey, "provider-b");
  assert.equal(result.cached, cached);
  assert.equal(result.backendIdentity, live);
});

test("offline fallback reuses the stored identity without a duplicate lookup", async () => {
  const stored = {
    identity: "stored-provider",
    service: { mode: "concrete", translator: "gemini", synthesizer: "mms" }
  };
  const lookups = [];

  const result = await resolveReplayStart({
    cacheEnabled: true,
    chunks: ["新聞"],
    rate: 1,
    backendUrl: "https://tts.example",
    identityResolver: {
      stored: async () => stored,
      resolve: async () => ({ ...stored, stale: true })
    },
    keyFor: async ({ backendIdentity }) => backendIdentity,
    getCached: async (id) => { lookups.push(id); return null; }
  });

  assert.deepEqual(lookups, ["stored-provider"]);
  assert.equal(result.cacheKey, "stored-provider");
  assert.equal(result.backendIdentity.stale, true);
  assert.equal(result.cacheWriteEnabled, true);
});

test("unknown provider identity is never looked up or written to replay cache", async () => {
  let cacheCalls = 0;
  const result = await resolveReplayStart({
    cacheEnabled: true,
    chunks: ["新聞"],
    rate: 1,
    backendUrl: "https://tts.example",
    identityResolver: {
      stored: async () => null,
      resolve: async () => ({
        identity: "unknown-provider",
        service: { mode: "unknown", translator: "", synthesizer: "" },
        stale: true
      })
    },
    keyFor: async ({ backendIdentity }) => backendIdentity,
    getCached: async () => { cacheCalls += 1; return null; }
  });

  assert.equal(cacheCalls, 0);
  assert.equal(result.cacheKey, "");
  assert.equal(result.cached, null);
  assert.equal(result.cacheWriteEnabled, false);
});

test("history keeps only non-sensitive service identity for honest replay labels", async () => {
  const { cache, storageArea } = fixture();
  await cache.setEnabled(true);
  await cache.put({
    id: "mock-entry",
    title: "測試新聞",
    rate: 1,
    chunks: [audio()],
    service: {
      mode: "mock",
      translator: "mock:translator",
      synthesizer: "mock:beep",
      backendUrl: "https://secret.example",
      apiKey: "do-not-store"
    }
  });

  assert.deepEqual((await cache.list())[0].service, {
    mode: "mock",
    translator: "mock:translator",
    synthesizer: "mock:beep"
  });
  const serialized = JSON.stringify(storageArea.values);
  assert.doesNotMatch(serialized, /新聞全文|https:\/\/|do-not-store/);
});

test("least recently used entries are evicted by count", async () => {
  let clock = 1_000;
  const { audioStore, cache } = fixture({ now: () => clock, maxEntries: 2 });
  await cache.setEnabled(true);
  await cache.put({ id: "one", title: "一", rate: 1, chunks: [audio("1")] });
  clock += 1;
  await cache.put({ id: "two", title: "二", rate: 1, chunks: [audio("2")] });
  clock += 1;
  await cache.get("one");
  clock += 1;
  await cache.put({ id: "three", title: "三", rate: 1, chunks: [audio("3")] });

  assert.deepEqual((await cache.list()).map(({ id }) => id), ["three", "one"]);
  assert.equal(audioStore.values.has("two"), false);
});

test("byte limit evicts older entries and skips an oversized single entry", async () => {
  let clock = 1_000;
  const { audioStore, cache } = fixture({ now: () => clock, maxBytes: 5 });
  await cache.setEnabled(true);
  await cache.put({ id: "old", title: "舊", rate: 1, chunks: [audio("1234")] });
  clock += 1;
  await cache.put({ id: "new", title: "新", rate: 1, chunks: [audio("5678")] });
  assert.deepEqual((await cache.list()).map(({ id }) => id), ["new"]);
  assert.equal(audioStore.values.has("old"), false);

  assert.deepEqual(await cache.put({ id: "large", title: "過大", rate: 1, chunks: [audio("123456")] }), {
    saved: false,
    reason: "too_large",
    bytes: 6
  });
  assert.equal(audioStore.values.has("large"), false);
});

test("expired, corrupt, and orphan audio are removed without an API fallback", async () => {
  let clock = 1_000;
  const { audioStore, cache } = fixture({ now: () => clock, ttlMs: 50 });
  await cache.setEnabled(true);
  await cache.put({ id: "expired", title: "過期", rate: 1, chunks: [audio()] });
  clock = 1_050;
  assert.deepEqual(await cache.list(), []);
  assert.equal(audioStore.values.has("expired"), false);

  clock = 2_000;
  await cache.put({ id: "corrupt", title: "損毀", rate: 1, chunks: [audio()] });
  audioStore.values.delete("corrupt");
  await assert.rejects(cache.get("corrupt"), { code: "REPLAY_CACHE_CORRUPT", message: /不會自動重新呼叫/ });
  assert.deepEqual(await cache.list(), []);

  audioStore.values.set("orphan", { id: "orphan", chunks: [] });
  await cache.cleanupOrphans();
  assert.equal(audioStore.values.has("orphan"), false);
});

test("startup crash recovery reconciles missing audio and orphan audio in both directions", async () => {
  const { audioStore, cache, storageArea } = fixture();
  const metadata = (id, lastPlayedAt) => ({
    id,
    title: id,
    createdAt: lastPlayedAt,
    lastPlayedAt,
    rate: 1,
    chunkCount: 1,
    bytes: 3,
    service: { mode: "concrete", translator: "gemini", synthesizer: "mms" }
  });
  storageArea.values[REPLAY_HISTORY_KEY] = [
    metadata("metadata-without-audio", 1_000),
    metadata("complete", 999)
  ];
  audioStore.values.set("complete", {
    id: "complete",
    chunks: [{ mimeType: "audio/wav", bytes: base64ToArrayBuffer(audio().base64) }]
  });
  audioStore.values.set("audio-without-metadata", {
    id: "audio-without-metadata",
    chunks: [{ mimeType: "audio/wav", bytes: base64ToArrayBuffer(audio().base64) }]
  });

  assert.deepEqual(await cache.cleanupOrphans(), {
    removedMetadata: ["metadata-without-audio"],
    removedAudio: ["audio-without-metadata"]
  });
  assert.deepEqual((await cache.list()).map(({ id }) => id), ["complete"]);
  assert.deepEqual([...audioStore.values.keys()], ["complete"]);
});

test("invalid metadata is sanitized and its referenced audio is removed", async () => {
  const { audioStore, cache, storageArea } = fixture();
  storageArea.values[REPLAY_HISTORY_KEY] = [{ id: "invalid", title: "缺欄位" }];
  audioStore.values.set("invalid", { id: "invalid", chunks: [audio()] });

  assert.deepEqual(await cache.list(), []);
  assert.equal(storageArea.values[REPLAY_HISTORY_KEY], undefined);
  assert.equal(audioStore.values.has("invalid"), false);
});

test("explicit deletion propagates an audio-store failure instead of claiming success", async () => {
  const { audioStore, cache } = fixture();
  await cache.setEnabled(true);
  await cache.put({ id: "one", title: "新聞", rate: 1, chunks: [audio()] });
  audioStore.delete = async () => { throw new Error("disk delete failed"); };

  await assert.rejects(cache.remove("one"), /disk delete failed/);
  assert.deepEqual((await cache.list()).map(({ id }) => id), ["one"]);
});

test("metadata write failure cannot evict the previous valid audio", async () => {
  let clock = 1_000;
  const { audioStore, cache, storageArea } = fixture({ now: () => clock, maxEntries: 1 });
  await cache.setEnabled(true);
  await cache.put({ id: "old", title: "舊", rate: 1, chunks: [audio("old")] });
  const originalSet = storageArea.set;
  let failNextHistoryWrite = true;
  storageArea.set = async (next) => {
    if (failNextHistoryWrite && next[REPLAY_HISTORY_KEY]) {
      failNextHistoryWrite = false;
      throw new Error("metadata write failed");
    }
    return originalSet(next);
  };
  clock += 1;

  await assert.rejects(
    cache.put({ id: "new", title: "新", rate: 1, chunks: [audio("new")] }),
    /metadata write failed/
  );
  assert.equal(audioStore.values.has("old"), true);
  assert.equal(audioStore.values.has("new"), false);
  assert.deepEqual((await cache.list()).map(({ id }) => id), ["old"]);
});

test("a failed disable leaves the opt-in visibly enabled so cleanup can be retried", async () => {
  const { audioStore, cache, storageArea } = fixture();
  await cache.setEnabled(true);
  await cache.put({ id: "one", title: "新聞", rate: 1, chunks: [audio()] });
  audioStore.clear = async () => { throw new Error("clear failed"); };

  await assert.rejects(cache.setEnabled(false), /clear failed/);
  assert.equal(await cache.enabled(), true);
  assert.equal(storageArea.values[REPLAY_PREFERENCES_KEY].enabled, true);
});

test("post-commit eviction failure is returned as a cleanup warning", async () => {
  let clock = 1_000;
  const { audioStore, cache } = fixture({ now: () => clock, maxEntries: 1 });
  await cache.setEnabled(true);
  await cache.put({ id: "old", title: "舊", rate: 1, chunks: [audio("old")] });
  const originalDelete = audioStore.delete;
  audioStore.delete = async (id) => {
    if (id === "old") throw new Error("old cleanup failed");
    return originalDelete(id);
  };
  clock += 1;

  const result = await cache.put({ id: "new", title: "新", rate: 1, chunks: [audio("new")] });
  assert.equal(result.saved, true);
  assert.match(result.cleanupError.message, /old cleanup failed/);
  assert.deepEqual((await cache.list()).map(({ id }) => id), ["new"]);
});

test("base64 conversion handles audio larger than a JavaScript argument chunk", () => {
  const original = Buffer.alloc(70_000);
  for (let index = 0; index < original.length; index += 1) original[index] = index % 251;
  const encoded = original.toString("base64");
  const decoded = base64ToArrayBuffer(encoded);
  assert.equal(arrayBufferToBase64(decoded), encoded);
});
