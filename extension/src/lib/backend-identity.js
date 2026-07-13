const BACKEND_IDENTITY_KEY = "taigiReplayBackendIdentity";
const IDENTITY_SCHEMA_VERSION = 1;

function validService(value) {
  return Boolean(value &&
    ["mock", "concrete", "unknown"].includes(value.mode) &&
    typeof value.translator === "string" && value.translator.length <= 200 &&
    typeof value.synthesizer === "string" && value.synthesizer.length <= 200);
}

function identityFor(backendUrl, service) {
  return JSON.stringify({
    version: IDENTITY_SCHEMA_VERSION,
    backendUrl,
    mode: service.mode,
    translator: service.translator,
    synthesizer: service.synthesizer
  });
}

function describeService(service) {
  if (service?.mode === "mock") return "測試音訊（不是台語 TTS）";
  if (service?.mode === "concrete") {
    return service.synthesizer ? `台語 TTS・${service.synthesizer}` : "台語 TTS";
  }
  return "語音服務資訊不明";
}

function fallbackIdentity(backendUrl) {
  const service = { mode: "unknown", translator: "", synthesizer: "" };
  return { backendUrl, identity: identityFor(backendUrl, service), service, checkedAt: 0, stale: true };
}

function createBackendIdentityResolver({
  storageArea,
  fetchImpl,
  endpointFor,
  now = Date.now,
  cachedProbeTimeoutMs = 1_500,
  initialProbeTimeoutMs = 4_500,
  createController = () => new AbortController(),
  schedule = setTimeout,
  cancelScheduled = clearTimeout
}) {
  async function storedIdentity(backendUrl) {
    const stored = (await storageArea.get(BACKEND_IDENTITY_KEY))[BACKEND_IDENTITY_KEY];
    if (!stored || stored.backendUrl !== backendUrl || typeof stored.identity !== "string" ||
        !validService(stored.service) || !Number.isFinite(stored.checkedAt)) return null;
    return {
      ...stored,
      identity: identityFor(backendUrl, stored.service)
    };
  }

  async function probe(backendUrl, timeoutMs) {
    const controller = createController();
    const timer = schedule(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(endpointFor(backendUrl, "/health"), { signal: controller.signal });
      if (!response.ok) throw new Error(`health request failed with HTTP ${response.status}`);
      const body = await response.json();
      const service = {
        mode: body?.mode,
        translator: body?.translator,
        synthesizer: body?.synthesizer
      };
      if (!validService(service) || service.mode === "unknown") throw new Error("health response has no provider identity");
      const result = {
        backendUrl,
        identity: identityFor(backendUrl, service),
        service,
        checkedAt: now()
      };
      try {
        await storageArea.set({ [BACKEND_IDENTITY_KEY]: result });
      } catch {
        // The current request can still use the live identity. A later offline
        // request simply cannot reuse it until storage becomes available.
      }
      return result;
    } finally {
      cancelScheduled(timer);
    }
  }

  async function resolve(backendUrl) {
    const stored = await storedIdentity(backendUrl);
    try {
      return await probe(backendUrl, stored ? cachedProbeTimeoutMs : initialProbeTimeoutMs);
    } catch {
      return stored ? { ...stored, stale: true } : fallbackIdentity(backendUrl);
    }
  }

  async function clear() {
    await storageArea.remove(BACKEND_IDENTITY_KEY);
  }

  return { clear, resolve, stored: storedIdentity };
}

module.exports = {
  BACKEND_IDENTITY_KEY,
  IDENTITY_SCHEMA_VERSION,
  createBackendIdentityResolver,
  describeService,
  fallbackIdentity,
  identityFor,
  validService
};
