const { SETTINGS_KEY, endpoint } = require("./lib/settings");
const { initialState, reducePlayerState, validateState } = require("./lib/player-state");
const { createPlayerStateStore, persistablePlayerState } = require("./lib/player-state-store");
const { installActionSidePanel } = require("./lib/action-side-panel");
const { ACTIVE_JOB_KEY, createActiveJobStore } = require("./lib/active-job-store");
const { createSynthesisJobClient } = require("./lib/synthesis-job-client");
const { createTaskKeepAlive } = require("./lib/task-keep-alive");
const { createBackendIdentityResolver } = require("./lib/backend-identity");
const { createBackendFetch } = require("./lib/backend-fetch");
const {
  DEFAULT_MAX_BYTES,
  byteLengthForBase64,
  createIndexedDbAudioStore,
  createReplayCache,
  resolveReplayStart
} = require("./lib/replay-cache");

const INTERRUPTED_MESSAGE = "上次朗讀工作已中斷，請重新開始。";
const activeJobs = createActiveJobStore(chrome.storage.session);
const backendFetch = createBackendFetch({
  fetchImpl: (...args) => fetch(...args),
  extensionId: chrome.runtime.id
});
const synthesis = createSynthesisJobClient({
  fetchImpl: backendFetch,
  endpointFor: endpoint
});
const replayCache = createReplayCache({
  storageArea: chrome.storage.local,
  audioStore: createIndexedDbAudioStore(indexedDB)
});
const backendIdentities = createBackendIdentityResolver({
  storageArea: chrome.storage.local,
  fetchImpl: backendFetch,
  endpointFor: endpoint
});

const restrictLocalStorageAccess = chrome.storage.local.setAccessLevel
  ? chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }).catch((error) => {
    console.warn("Unable to restrict extension storage access.", error);
  })
  : Promise.resolve();

let runId = 0;
let switchingOffscreen = Promise.resolve();
let commandQueue = Promise.resolve();
const player = createPlayerStateStore({
  initial: initialState(),
  reduce: reducePlayerState,
  currentToken: () => runId,
  save: (next) => chrome.storage.session.set({ playbackState: persistablePlayerState(next) }),
  broadcast: (next) => chrome.runtime.sendMessage({ target: "sidepanel", type: "STATE", state: next }).catch(() => {})
});

const queueKeepAlive = createTaskKeepAlive({
  ping: () => chrome.runtime.getPlatformInfo(),
  intervalMs: 20_000,
  onPingError(error) {
    console.warn("Playback keep-alive ping failed.", error);
  }
});

installActionSidePanel(chrome, {
  onError(error) {
    console.error("Unable to open the side panel from the extension action.", error);
  }
});

function ensureAudioOffscreen() {
  const url = "offscreen.html";
  const desiredUrl = chrome.runtime.getURL(url);
  const operation = switchingOffscreen
    .catch(() => {})
    .then(async () => {
      const existing = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
      if (existing.some((context) => context.documentUrl === desiredUrl)) return;
      if (existing.length) await chrome.offscreen.closeDocument();
      await chrome.offscreen.createDocument({
        url,
        reasons: ["AUDIO_PLAYBACK", "BLOBS"],
        justification: "解碼並播放使用者已確認的台語新聞語音"
      });
    });
  switchingOffscreen = operation;
  return operation;
}

function transition(event, token) {
  return player.transition(event, token === undefined ? {} : { token });
}

async function forgetCurrentReplay(id = "") {
  const currentId = player.getState().replayId;
  if (currentId && (!id || currentId === id)) await transition({ type: "FORGET_REPLAY" });
}

function storedJobValid(job) {
  return Boolean(job && typeof job.jobId === "string" && job.jobId &&
    typeof job.backendUrl === "string" && job.backendUrl && Number.isFinite(job.runId));
}

async function clearStoredJob(job) {
  await activeJobs.clearIfOwner({ jobId: job.jobId, token: job.runId });
}

async function cleanupStoredOrphan() {
  const job = await activeJobs.get();
  if (!job) return { found: false };
  if (!storedJobValid(job)) {
    await activeJobs.remove();
    return { found: false };
  }
  await synthesis.deleteJob(job.backendUrl, job.jobId);
  await clearStoredJob(job);
  return { found: true, job };
}

async function recordActiveJob(job) {
  await activeJobs.recordLatest(job);
}

async function recoverStartup() {
  await restrictLocalStorageAccess;
  const stored = await chrome.storage.session.get("playbackState");
  if (stored.playbackState && validateState(stored.playbackState)) player.hydrate(stored.playbackState);

  const orphan = await activeJobs.get();
  if (storedJobValid(orphan)) runId = Math.max(runId, orphan.runId);
  let cleanupError = null;
  if (orphan) {
    try {
      await cleanupStoredOrphan();
    } catch (error) {
      cleanupError = error;
      console.warn("Unable to clean up an interrupted synthesis job.", error);
    }
  }

  const interrupted = orphan || ["preparing", "playing", "paused"].includes(player.getState().status);
  if (interrupted) {
    await chrome.runtime.sendMessage({ target: "offscreen", type: "STOP" }).catch(() => {});
    const detail = cleanupError ? " 背景工作尚待清理，請稍後再試。" : "";
    await transition({ type: "ERROR", error: `${INTERRUPTED_MESSAGE}${detail}` });
  }

  try {
    if (await replayCache.enabled()) {
      await replayCache.cleanupOrphans();
    } else {
      await backendIdentities.clear();
      await replayCache.clear();
    }
  } catch (error) {
    console.warn("Unable to clean up the local replay cache.", error);
  }
}

const startupRecovery = recoverStartup().catch(async (error) => {
  console.error("Unable to recover playback state.", error);
  try {
    await transition({ type: "ERROR", error: INTERRUPTED_MESSAGE });
  } catch (storageError) {
    console.error("Unable to save recovery state.", storageError);
  }
});

async function cancelCurrentWork() {
  const cancellation = synthesis.cancel().then(() => null, (error) => error);
  await chrome.runtime.sendMessage({ target: "offscreen", type: "STOP" }).catch(() => {});
  const cancellationError = await cancellation;
  if (cancellationError) throw cancellationError;
}

function notifySidepanel(message) {
  return chrome.runtime.sendMessage({ target: "sidepanel", type: "NOTICE", message }).catch(() => {});
}

async function runQueue(id, {
  chunks,
  rate,
  backendUrl,
  title,
  cacheKey,
  cacheEnabled,
  cacheWriteEnabled,
  service,
  cachedAudio = null
}) {
  const generatedAudio = [];
  let generatedBytes = 0;
  let exceededCacheLimit = false;
  let cacheable = cacheWriteEnabled && !cachedAudio;
  try {
    for (let index = 0; index < chunks.length; index += 1) {
      if (id !== runId) return;
      if (!cachedAudio) {
        await cleanupStoredOrphan();
        if (id !== runId) return;
      }
      await transition({ type: "PREPARING", index }, id);
      if (id !== runId) return;
      const audio = cachedAudio ? cachedAudio[index] : await synthesis.synthesize({
        backendUrl,
        text: chunks[index],
        rate,
        token: id,
        onCreated: recordActiveJob,
        onCleared: (job) => activeJobs.clearIfOwner(job)
      });
      if (id !== runId) return;
      if (cacheable) {
        generatedBytes += byteLengthForBase64(audio.base64);
        if (generatedBytes > DEFAULT_MAX_BYTES) {
          cacheable = false;
          exceededCacheLimit = true;
          generatedAudio.length = 0;
        } else {
          generatedAudio.push(audio);
        }
      }
      await ensureAudioOffscreen();
      if (id !== runId) return;
      await transition({ type: "PLAYING", index }, id);
      if (id !== runId) return;
      const result = await chrome.runtime.sendMessage({ target: "offscreen", type: "PLAY_AUDIO", ...audio });
      if (id !== runId) return;
      if (!result?.ok && result?.reason !== "stopped") throw new Error(result?.error || "無法播放語音。");
    }
    if (id !== runId) return;

    let replayId = "";
    if (cachedAudio) {
      try {
        if (await replayCache.enabled()) {
          const history = await replayCache.list();
          if (history.some((entry) => entry.id === cacheKey)) replayId = cacheKey;
        }
      } catch (error) {
        console.warn("Unable to refresh replay history after playback.", error);
      }
    }
    if (cacheable) {
      try {
        const saved = await replayCache.put({ id: cacheKey, title, rate, chunks: generatedAudio, service });
        if (saved.saved) {
          replayId = cacheKey;
          await notifySidepanel(saved.cleanupError
            ? "已保存這篇重播音訊，但舊記錄清理失敗；請稍後使用「清除所有重播記錄」再試一次。"
            : "已保留在這台電腦，可直接重新播放，不會再次呼叫語音服務。");
        }
      } catch (error) {
        console.warn("Unable to save replay audio.", error);
        await notifySidepanel("新聞已朗讀完畢，但本機重播記錄儲存失敗；本次仍可正常使用。");
      }
    } else if (cacheWriteEnabled && exceededCacheLimit) {
      await notifySidepanel("這篇音訊超過 50 MiB，已完成播放但不會保存重播記錄。");
    } else if (cacheEnabled && !cachedAudio && !cacheWriteEnabled) {
      await notifySidepanel("目前無法確認語音服務身分，已完成播放但不會保存重播記錄。");
    }

    await transition({ type: "COMPLETE", replayId }, id);
    if (replayId) {
      await chrome.runtime.sendMessage({ target: "sidepanel", type: "HISTORY_CHANGED" }).catch(() => {});
    }
  } catch (error) {
    if (id !== runId || error?.name === "AbortError") return;
    await transition({ type: "ERROR", error: error?.message || "朗讀失敗。" }, id);
  }
}

async function beginPlayback({
  chunks,
  title,
  rate,
  backendUrl = "",
  cacheKey = "",
  cacheEnabled = false,
  cacheWriteEnabled = false,
  service = { mode: "unknown", translator: "", synthesizer: "" },
  cachedAudio = null
}) {
  const id = ++runId;
  try {
    await cancelCurrentWork();
    if (id !== runId) return;
    if (cachedAudio) {
      try {
        await cleanupStoredOrphan();
      } catch (error) {
        console.warn("Unable to clean an older backend job before local replay.", error);
      }
    } else {
      await cleanupStoredOrphan();
    }
    if (id !== runId) return;
    await transition({ type: "START", total: chunks.length, title, rate }, id);
  } catch (error) {
    if (id === runId) await transition({ type: "ERROR", error: error?.message || "無法開始朗讀。" }, id);
    throw error;
  }

  queueKeepAlive
    .run(() => runQueue(id, {
      chunks,
      rate,
      backendUrl,
      title,
      cacheKey,
      cacheEnabled,
      cacheWriteEnabled,
      service,
      cachedAudio
    }))
    .catch((error) => {
      console.error("Playback queue failed outside its normal error handling.", error);
      if (id !== runId) return;
      transition({ type: "ERROR", error: error?.message || "朗讀失敗。" }, id)
        .catch((stateError) => console.error("Unable to report playback failure.", stateError));
    });
}

async function start(message) {
  if (!Array.isArray(message.chunks) || !message.chunks.length) throw new Error("沒有可朗讀的文字。");
  const settings = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
  if (!settings?.backendUrl) throw new Error("尚未設定台語語音服務。");

  const cacheEnabled = await replayCache.enabled();
  const {
    cacheKey,
    cached,
    backendIdentity,
    cacheWriteEnabled
  } = await resolveReplayStart({
    cacheEnabled,
    chunks: message.chunks,
    rate: message.rate,
    backendUrl: settings.backendUrl,
    identityResolver: backendIdentities,
    getCached: async (id) => {
      try {
        return await replayCache.get(id);
      } catch (error) {
        await forgetCurrentReplay(id);
        throw error;
      }
    }
  });
  await beginPlayback({
    chunks: message.chunks,
    title: message.title,
    rate: message.rate,
    backendUrl: settings.backendUrl,
    cacheKey,
    cacheEnabled,
    cacheWriteEnabled,
    service: cached?.metadata.service || backendIdentity?.service,
    cachedAudio: cached?.chunks || null
  });
  return { cacheHit: Boolean(cached) };
}

async function replay(message) {
  if (!(await replayCache.enabled())) throw new Error("本機重播記錄尚未開啟。");
  if (typeof message.id !== "string" || !message.id) throw new Error("找不到要重播的新聞。");
  let cached;
  try {
    cached = await replayCache.get(message.id);
  } catch (error) {
    await forgetCurrentReplay(message.id);
    throw error;
  }
  if (!cached) {
    await forgetCurrentReplay(message.id);
    throw new Error("這筆重播音訊已失效或被清除，不會自動重新呼叫語音服務。");
  }
  await beginPlayback({
    chunks: cached.chunks.map(() => ""),
    title: cached.metadata.title,
    rate: cached.metadata.rate,
    cacheKey: message.id,
    cacheEnabled: true,
    service: cached.metadata.service,
    cachedAudio: cached.chunks
  });
  return { cacheHit: true };
}

async function stop(clear = false) {
  const id = ++runId;
  let cancellationError = null;
  try {
    await cancelCurrentWork();
  } catch (error) {
    cancellationError = error;
  }
  try {
    const cleanup = await cleanupStoredOrphan();
    if (cleanup.found) cancellationError = null;
  } catch (error) {
    cancellationError = error;
  }
  if (id !== runId) return;

  if (clear) {
    await transition({ type: "CLEAR" });
  } else {
    await transition({ type: "STOP" });
  }
  if (cancellationError) throw cancellationError;
}

async function handleCommand(message) {
  await startupRecovery;
  switch (message.type) {
    case "START":
      return start(message);
    case "REPLAY":
      return replay(message);
    case "PAUSE":
      await chrome.runtime.sendMessage({ target: "offscreen", type: "PAUSE" });
      await transition({ type: "PAUSE" });
      break;
    case "RESUME":
      await ensureAudioOffscreen();
      await chrome.runtime.sendMessage({ target: "offscreen", type: "RESUME" });
      await transition({ type: "RESUME" });
      break;
    case "STOP":
      await stop(false);
      break;
    case "CLEAR":
      await stop(true);
      break;
    case "GET_REPLAY_HISTORY": {
      const enabled = await replayCache.enabled();
      try {
        const history = await replayCache.list();
        const replayId = player.getState().replayId;
        if (replayId && !history.some((entry) => entry.id === replayId)) await forgetCurrentReplay(replayId);
        return { enabled, history };
      } catch (error) {
        console.warn("Unable to load or prune replay history.", error);
        return { enabled, history: [], warning: "目前無法讀取或清理本機重播記錄，請稍後再試。" };
      }
    }
    case "SET_REPLAY_ENABLED": {
      if (message.enabled !== true) await backendIdentities.clear();
      const enabled = await replayCache.setEnabled(message.enabled === true);
      if (!enabled) await forgetCurrentReplay();
      await chrome.runtime.sendMessage({ target: "sidepanel", type: "HISTORY_CHANGED" }).catch(() => {});
      if (!enabled) return { enabled, history: [] };
      try {
        const history = await replayCache.list();
        return { enabled, history };
      } catch (error) {
        console.warn("Replay was enabled but its history could not be loaded.", error);
        return { enabled, history: [], warning: "已開啟本機重播，但目前無法讀取既有記錄。" };
      }
    }
    case "DELETE_REPLAY":
      await replayCache.remove(message.id);
      await forgetCurrentReplay(message.id);
      await chrome.runtime.sendMessage({ target: "sidepanel", type: "HISTORY_CHANGED" }).catch(() => {});
      return { history: await replayCache.list() };
    case "CLEAR_REPLAY_HISTORY":
      await replayCache.clear();
      await forgetCurrentReplay();
      await chrome.runtime.sendMessage({ target: "sidepanel", type: "HISTORY_CHANGED" }).catch(() => {});
      return { history: [] };
    default:
      throw new Error("不支援的操作。");
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.target !== "service-worker") return undefined;
  const operation = commandQueue
    .catch(() => {})
    .then(() => handleCommand(message));
  commandQueue = operation.catch(() => {});
  operation
    .then((result) => sendResponse({ ok: true, ...(result || {}) }))
    .catch((error) => sendResponse({ ok: false, error: error?.message || "操作失敗。" }));
  return true;
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes[SETTINGS_KEY]) return;
  const before = changes[SETTINGS_KEY].oldValue?.backendUrl || "";
  const after = changes[SETTINGS_KEY].newValue?.backendUrl || "";
  if (before !== after) {
    backendIdentities.clear().catch((error) => {
      console.warn("Unable to clear the previous replay backend identity.", error);
    });
  }
});

module.exports = { ACTIVE_JOB_KEY };
