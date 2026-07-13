const test = require("node:test");
const assert = require("node:assert/strict");

const {
  BACKEND_IDENTITY_KEY,
  createBackendIdentityResolver,
  describeService,
  identityFor
} = require("../src/lib/backend-identity");
const { EXTENSION_CLIENT_ID_HEADER, createBackendFetch } = require("../src/lib/backend-fetch");

function memoryStorage(initial = {}) {
  const values = structuredClone(initial);
  return {
    values,
    async get(key) {
      return { [key]: values[key] };
    },
    async set(next) {
      Object.assign(values, structuredClone(next));
    },
    async remove(key) {
      delete values[key];
    }
  };
}

function resolver({ storageArea, fetchImpl, now = () => 1_234 } = {}) {
  return createBackendIdentityResolver({
    storageArea,
    fetchImpl,
    endpointFor: (base, path) => `${base}${path}`,
    now
  });
}

test("live health identity includes mode, translator, and synthesizer and is stored", async () => {
  const storageArea = memoryStorage();
  const service = {
    mode: "concrete",
    translator: "gemini:gemini-3.5-flash",
    synthesizer: "huggingface:facebook/mms-tts-nan"
  };
  const seen = [];
  const fetchImpl = createBackendFetch({
    extensionId: "abcdefghijklmnopabcdefghijklmnop",
    fetchImpl: async (url, options) => {
      seen.push({ url, signal: options.signal, headers: options.headers });
      return { ok: true, json: async () => service };
    }
  });
  const identities = resolver({ storageArea, fetchImpl });

  const result = await identities.resolve("https://tts.example");

  assert.equal(seen.length, 1);
  assert.equal(seen[0].url, "https://tts.example/health");
  assert.ok(seen[0].signal instanceof AbortSignal);
  assert.equal(seen[0].headers.get(EXTENSION_CLIENT_ID_HEADER), "abcdefghijklmnopabcdefghijklmnop");
  assert.deepEqual(result.service, service);
  assert.equal(result.identity, identityFor("https://tts.example", service));
  assert.deepEqual(storageArea.values[BACKEND_IDENTITY_KEY], result);
});

test("stored identity is canonicalized and scoped to the selected backend URL", async () => {
  const service = { mode: "mock", translator: "mock:translator", synthesizer: "mock:beep" };
  const storageArea = memoryStorage({
    [BACKEND_IDENTITY_KEY]: {
      backendUrl: "https://tts.example",
      identity: "untrusted-stored-value",
      service,
      checkedAt: 99
    }
  });
  const identities = resolver({ storageArea, fetchImpl: async () => { throw new Error("unused"); } });

  assert.deepEqual(await identities.stored("https://tts.example"), {
    backendUrl: "https://tts.example",
    identity: identityFor("https://tts.example", service),
    service,
    checkedAt: 99
  });
  assert.equal(await identities.stored("https://other.example"), null);
});

test("offline resolution reuses the stored provider identity", async () => {
  const service = {
    mode: "concrete",
    translator: "ollama:qwen",
    synthesizer: "huggingface:facebook/mms-tts-nan"
  };
  const storageArea = memoryStorage({
    [BACKEND_IDENTITY_KEY]: {
      backendUrl: "https://tts.example",
      identity: identityFor("https://tts.example", service),
      service,
      checkedAt: 88
    }
  });
  const identities = resolver({
    storageArea,
    fetchImpl: async () => { throw new TypeError("offline"); }
  });

  const result = await identities.resolve("https://tts.example");

  assert.deepEqual(result.service, service);
  assert.equal(result.identity, identityFor("https://tts.example", service));
  assert.equal(result.stale, true);
});

test("offline resolution without a stored identity is explicitly unknown", async () => {
  const identities = resolver({
    storageArea: memoryStorage(),
    fetchImpl: async () => { throw new TypeError("offline"); }
  });

  const result = await identities.resolve("https://tts.example");

  assert.deepEqual(result.service, { mode: "unknown", translator: "", synthesizer: "" });
  assert.equal(result.stale, true);
  assert.equal(result.checkedAt, 0);
});

test("mock replay disclosure states that it is not Taiwanese TTS", () => {
  assert.equal(
    describeService({ mode: "mock", translator: "mock:translator", synthesizer: "mock:beep" }),
    "測試音訊（不是台語 TTS）"
  );
});
