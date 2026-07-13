const { SETTINGS_KEY, endpoint } = require("./lib/settings");
const { initialState, reducePlayerState, validateState } = require("./lib/player-state");
const { createPlayerStateStore, persistablePlayerState } = require("./lib/player-state-store");
const { installActionSidePanel } = require("./lib/action-side-panel");
const { ACTIVE_JOB_KEY, createActiveJobStore } = require("./lib/active-job-store");
const { createSynthesisJobClient } = require("./lib/synthesis-job-client");
const { createTaskKeepAlive } = require("./lib/task-keep-alive");

const INTERRUPTED_MESSAGE = "上次朗讀工作已中斷，請重新開始。";
const activeJobs = createActiveJobStore(chrome.storage.session);
const synthesis = createSynthesisJobClient({
  fetchImpl: (...args) => fetch(...args),
  endpointFor: endpoint
});

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

async function runQueue(id, chunks, rate, backendUrl) {
  try {
    for (let index = 0; index < chunks.length; index += 1) {
      if (id !== runId) return;
      await cleanupStoredOrphan();
      if (id !== runId) return;
      await transition({ type: "PREPARING", index }, id);
      if (id !== runId) return;
      const audio = await synthesis.synthesize({
        backendUrl,
        text: chunks[index],
        rate,
        token: id,
        onCreated: recordActiveJob,
        onCleared: (job) => activeJobs.clearIfOwner(job)
      });
      if (id !== runId) return;
      await ensureAudioOffscreen();
      if (id !== runId) return;
      await transition({ type: "PLAYING", index }, id);
      if (id !== runId) return;
      const result = await chrome.runtime.sendMessage({ target: "offscreen", type: "PLAY_AUDIO", ...audio });
      if (id !== runId) return;
      if (!result?.ok && result?.reason !== "stopped") throw new Error(result?.error || "無法播放語音。");
    }
    if (id === runId) await transition({ type: "COMPLETE" }, id);
  } catch (error) {
    if (id !== runId || error?.name === "AbortError") return;
    await transition({ type: "ERROR", error: error?.message || "朗讀失敗。" }, id);
  }
}

async function start(message) {
  if (!Array.isArray(message.chunks) || !message.chunks.length) throw new Error("沒有可朗讀的文字。");
  const settings = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
  if (!settings?.backendUrl) throw new Error("尚未設定台語語音服務。");

  const id = ++runId;
  try {
    await cancelCurrentWork();
    if (id !== runId) return;
    await cleanupStoredOrphan();
    if (id !== runId) return;
    await transition({ type: "START", total: message.chunks.length, title: message.title, rate: message.rate }, id);
  } catch (error) {
    if (id === runId) await transition({ type: "ERROR", error: error?.message || "無法開始朗讀。" }, id);
    throw error;
  }

  queueKeepAlive
    .run(() => runQueue(id, message.chunks, message.rate, settings.backendUrl))
    .catch((error) => {
      console.error("Playback queue failed outside its normal error handling.", error);
      if (id !== runId) return;
      transition({ type: "ERROR", error: error?.message || "朗讀失敗。" }, id)
        .catch((stateError) => console.error("Unable to report playback failure.", stateError));
    });
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
      await start(message);
      break;
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
    .then(() => sendResponse({ ok: true }))
    .catch((error) => sendResponse({ ok: false, error: error?.message || "操作失敗。" }));
  return true;
});

module.exports = { ACTIVE_JOB_KEY };
