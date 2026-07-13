const { normalizeText } = require("./chunk");
const { validService } = require("./backend-identity");

const REPLAY_PREFERENCES_KEY = "taigiReplayPreferences";
const REPLAY_HISTORY_KEY = "taigiReplayHistory";
const CACHE_SCHEMA_VERSION = 2;
const DEFAULT_MAX_ENTRIES = 5;
const DEFAULT_MAX_BYTES = 50 * 1024 * 1024;
const DEFAULT_TTL_MS = 7 * 24 * 60 * 60 * 1_000;

function byteLengthForBase64(value) {
  if (typeof value !== "string" || !value) return 0;
  const padding = value.endsWith("==") ? 2 : (value.endsWith("=") ? 1 : 0);
  return Math.max(0, Math.floor(value.length * 3 / 4) - padding);
}

function base64ToArrayBuffer(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

function arrayBufferToBase64(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  const chunkSize = 32_768;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function safeTitle(value) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  return (normalized || "未命名新聞").slice(0, 200);
}

function safeService(value) {
  if (validService(value)) {
    return {
      mode: value.mode,
      translator: value.translator,
      synthesizer: value.synthesizer
    };
  }
  return { mode: "unknown", translator: "", synthesizer: "" };
}

function validHistoryEntryBase(entry) {
  return Boolean(entry &&
    typeof entry.id === "string" && entry.id &&
    typeof entry.title === "string" &&
    Number.isFinite(entry.createdAt) &&
    Number.isFinite(entry.lastPlayedAt) &&
    Number.isFinite(entry.rate) &&
    Number.isInteger(entry.chunkCount) && entry.chunkCount > 0 &&
    Number.isFinite(entry.bytes) && entry.bytes > 0);
}

function validHistory(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter(validHistoryEntryBase)
    .map((entry) => ({ ...entry, service: safeService(entry.service) }));
}

async function createReplayCacheKey({ chunks, rate, backendUrl, backendIdentity, subtle = crypto.subtle }) {
  const canonical = JSON.stringify({
    version: CACHE_SCHEMA_VERSION,
    sourceLanguage: "zh-TW",
    targetLanguage: "nan-TW",
    backendUrl: String(backendUrl || ""),
    backendIdentity: String(backendIdentity || ""),
    rate: Number(rate),
    chunks: Array.isArray(chunks) ? chunks.map((chunk) => normalizeText(String(chunk))) : []
  });
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function resolveReplayStart({
  cacheEnabled,
  chunks,
  rate,
  backendUrl,
  identityResolver,
  getCached,
  keyFor = createReplayCacheKey
}) {
  if (!cacheEnabled) {
    return { cacheKey: "", cached: null, backendIdentity: null, cacheWriteEnabled: false };
  }

  async function lookup(identity) {
    const cacheKey = await keyFor({
      chunks,
      rate,
      backendUrl,
      backendIdentity: identity.identity
    });
    return { cacheKey, cached: await getCached(cacheKey) };
  }

  const storedIdentity = await identityResolver.stored(backendUrl);
  let cacheKey = "";
  let cached = null;
  let backendIdentity = null;
  if (storedIdentity && storedIdentity.service.mode !== "unknown") {
    ({ cacheKey, cached } = await lookup(storedIdentity));
    if (cached) backendIdentity = storedIdentity;
  }

  if (!cached) {
    backendIdentity = await identityResolver.resolve(backendUrl);
    if (backendIdentity.service.mode !== "unknown" && backendIdentity.identity !== storedIdentity?.identity) {
      ({ cacheKey, cached } = await lookup(backendIdentity));
    }
  }

  return {
    cacheKey,
    cached,
    backendIdentity,
    cacheWriteEnabled: Boolean(!cached && backendIdentity && backendIdentity.service.mode !== "unknown")
  };
}

function createIndexedDbAudioStore(databaseFactory, {
  databaseName = "taigi-news-reader-replay",
  storeName = "audioEntries"
} = {}) {
  let opening;

  function database() {
    if (!opening) {
      const attempt = new Promise((resolve, reject) => {
        const request = databaseFactory.open(databaseName, 1);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(storeName)) db.createObjectStore(storeName, { keyPath: "id" });
        };
        request.onsuccess = () => {
          request.result.onversionchange = () => {
            request.result.close();
            if (opening === attempt) opening = undefined;
          };
          resolve(request.result);
        };
        request.onerror = () => reject(request.error || new Error("無法開啟朗讀音訊儲存空間。"));
        request.onblocked = () => reject(new Error("朗讀音訊儲存空間目前無法開啟。"));
      });
      opening = attempt;
      attempt.catch(() => {
        if (opening === attempt) opening = undefined;
      });
    }
    return opening;
  }

  async function request(mode, operation) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, mode);
      const result = operation(transaction.objectStore(storeName));
      let requestResult;
      result.onsuccess = () => {
        requestResult = result.result;
        if (mode === "readonly") resolve(requestResult);
      };
      result.onerror = () => reject(result.error || new Error("朗讀音訊儲存失敗。"));
      transaction.onabort = () => reject(transaction.error || new Error("朗讀音訊儲存失敗。"));
      transaction.onerror = () => reject(transaction.error || new Error("朗讀音訊儲存失敗。"));
      if (mode !== "readonly") transaction.oncomplete = () => resolve(requestResult);
    });
  }

  return {
    get: (id) => request("readonly", (store) => store.get(id)),
    put: (entry) => request("readwrite", (store) => store.put(entry)),
    delete: (id) => request("readwrite", (store) => store.delete(id)),
    clear: () => request("readwrite", (store) => store.clear()),
    keys: () => request("readonly", (store) => store.getAllKeys())
  };
}

function createReplayCache({
  storageArea,
  audioStore,
  now = Date.now,
  maxEntries = DEFAULT_MAX_ENTRIES,
  maxBytes = DEFAULT_MAX_BYTES,
  ttlMs = DEFAULT_TTL_MS
}) {
  let operations = Promise.resolve();

  function serialize(operation) {
    const result = operations.then(operation, operation);
    operations = result.catch(() => {});
    return result;
  }

  async function storedHistory() {
    const stored = await storageArea.get(REPLAY_HISTORY_KEY);
    const raw = stored[REPLAY_HISTORY_KEY];
    const history = validHistory(raw);
    const invalidIds = Array.isArray(raw) ? raw
      .filter((entry) => !validHistoryEntryBase(entry))
      .map((entry) => entry?.id)
      .filter((id) => typeof id === "string" && id) : [];
    return {
      history,
      invalidIds,
      sanitized: raw !== undefined && (!Array.isArray(raw) || history.length !== raw.length ||
        raw.some((entry) => validHistoryEntryBase(entry) && !validService(entry.service)))
    };
  }

  async function writeHistory(history) {
    if (history.length) await storageArea.set({ [REPLAY_HISTORY_KEY]: history });
    else await storageArea.remove(REPLAY_HISTORY_KEY);
  }

  async function removeAudio(ids) {
    await Promise.all([...new Set(ids)].map((id) => audioStore.delete(id)));
  }

  function pruneHistory(history, currentTime = now()) {
    const expired = history.filter((entry) => currentTime - entry.lastPlayedAt >= ttlMs);
    let kept = history.filter((entry) => currentTime - entry.lastPlayedAt < ttlMs)
      .sort((left, right) => right.lastPlayedAt - left.lastPlayedAt);
    const evicted = [...expired];
    let bytes = 0;
    const bounded = [];
    for (const entry of kept) {
      if (bounded.length >= maxEntries || bytes + entry.bytes > maxBytes) {
        evicted.push(entry);
      } else {
        bounded.push(entry);
        bytes += entry.bytes;
      }
    }
    kept = bounded;
    return { history: kept, evicted };
  }

  async function commitPrune({ history, invalidIds = [], sanitized = false }, currentTime = now()) {
    const pruned = pruneHistory(history, currentTime);
    if (sanitized || pruned.evicted.length) await writeHistory(pruned.history);
    const cleanupIds = [...invalidIds, ...pruned.evicted.map(({ id }) => id)];
    if (cleanupIds.length) await removeAudio(cleanupIds);
    return pruned.history;
  }

  async function preferences() {
    const stored = await storageArea.get(REPLAY_PREFERENCES_KEY);
    return { enabled: stored[REPLAY_PREFERENCES_KEY]?.enabled === true };
  }

  async function enabled() {
    return (await preferences()).enabled;
  }

  async function setEnabled(value) {
    return serialize(async () => {
      const next = value === true;
      if (!next) {
        await audioStore.clear();
        await storageArea.remove(REPLAY_HISTORY_KEY);
        await storageArea.set({ [REPLAY_PREFERENCES_KEY]: { enabled: false } });
        return false;
      }
      await storageArea.set({ [REPLAY_PREFERENCES_KEY]: { enabled: true } });
      return true;
    });
  }

  async function list() {
    return serialize(async () => {
      return commitPrune(await storedHistory());
    });
  }

  async function get(id, { touch = true } = {}) {
    return serialize(async () => {
      const history = await commitPrune(await storedHistory());
      let entry = history.find((candidate) => candidate.id === id);
      if (!entry) return null;
      const stored = await audioStore.get(id);
      const chunksValid = stored && Array.isArray(stored.chunks) &&
        stored.chunks.length === entry.chunkCount && stored.chunks.every((chunk) =>
          chunk && typeof chunk.mimeType === "string" &&
          (chunk.bytes instanceof ArrayBuffer || ArrayBuffer.isView(chunk.bytes)));
      if (!chunksValid) {
        await audioStore.delete(id);
        await writeHistory(history.filter((candidate) => candidate.id !== id));
        const error = new Error("本機重播音訊已損毀或遺失，不會自動重新呼叫語音服務。");
        error.code = "REPLAY_CACHE_CORRUPT";
        throw error;
      }
      if (touch) {
        entry = { ...entry, lastPlayedAt: now() };
        const next = history.map((candidate) => candidate.id === id ? entry : candidate)
          .sort((left, right) => right.lastPlayedAt - left.lastPlayedAt);
        await writeHistory(next);
      }
      return {
        metadata: entry,
        chunks: stored.chunks.map((chunk) => ({
          base64: arrayBufferToBase64(chunk.bytes),
          mimeType: chunk.mimeType
        }))
      };
    });
  }

  async function put({ id, title, rate, chunks, service }) {
    return serialize(async () => {
      if (!(await enabled())) return { saved: false, reason: "disabled" };
      if (!Array.isArray(chunks) || !chunks.length) return { saved: false, reason: "empty" };
      const bytes = chunks.reduce((total, chunk) => total + byteLengthForBase64(chunk.base64), 0);
      if (!bytes || bytes > maxBytes) return { saved: false, reason: "too_large", bytes };

      const currentTime = now();
      const stored = await storedHistory();
      const currentHistory = stored.history;
      const existing = currentHistory.find((entry) => entry.id === id);
      const history = currentHistory.filter((entry) => entry.id !== id);
      const metadata = {
        id,
        title: safeTitle(title),
        createdAt: existing?.createdAt || currentTime,
        lastPlayedAt: currentTime,
        rate: Number(rate),
        chunkCount: chunks.length,
        bytes,
        service: safeService(service)
      };
      const pruned = pruneHistory([metadata, ...history], currentTime);
      const audioEntry = {
        id,
        chunks: chunks.map((chunk) => ({
          mimeType: chunk.mimeType,
          bytes: base64ToArrayBuffer(chunk.base64)
        }))
      };
      await audioStore.put(audioEntry);
      try {
        await writeHistory(pruned.history);
      } catch (error) {
        try {
          await audioStore.delete(id);
        } catch (cleanupError) {
          error.cleanupError = cleanupError;
        }
        throw error;
      }
      let cleanupError = null;
      try {
        await removeAudio(pruned.evicted.map(({ id: evictedId }) => evictedId));
      } catch (error) {
        cleanupError = error;
      }
      const saved = pruned.history.some((entry) => entry.id === id);
      if (!saved) await audioStore.delete(id);
      return {
        saved,
        reason: saved ? "saved" : "evicted",
        metadata: saved ? metadata : undefined,
        cleanupError
      };
    });
  }

  async function remove(id) {
    return serialize(async () => {
      await audioStore.delete(id);
      const { history } = await storedHistory();
      await writeHistory(history.filter((entry) => entry.id !== id));
    });
  }

  async function clear() {
    return serialize(async () => {
      await audioStore.clear();
      await storageArea.remove(REPLAY_HISTORY_KEY);
    });
  }

  async function cleanupOrphans() {
    return serialize(async () => {
      const history = await commitPrune(await storedHistory());
      const keys = await audioStore.keys();
      const audioIds = new Set(keys);
      const missingAudio = history.filter(({ id }) => !audioIds.has(id));
      const reconciled = history.filter(({ id }) => audioIds.has(id));
      if (missingAudio.length) await writeHistory(reconciled);
      const metadataIds = new Set(reconciled.map(({ id }) => id));
      const orphanAudio = keys.filter((id) => !metadataIds.has(id));
      if (orphanAudio.length) await removeAudio(orphanAudio);
      return {
        removedMetadata: missingAudio.map(({ id }) => id),
        removedAudio: orphanAudio
      };
    });
  }

  return { cleanupOrphans, clear, enabled, get, list, put, remove, setEnabled };
}

module.exports = {
  CACHE_SCHEMA_VERSION,
  DEFAULT_MAX_BYTES,
  DEFAULT_MAX_ENTRIES,
  DEFAULT_TTL_MS,
  REPLAY_HISTORY_KEY,
  REPLAY_PREFERENCES_KEY,
  arrayBufferToBase64,
  base64ToArrayBuffer,
  byteLengthForBase64,
  createIndexedDbAudioStore,
  createReplayCache,
  createReplayCacheKey,
  resolveReplayStart,
  safeService
};
