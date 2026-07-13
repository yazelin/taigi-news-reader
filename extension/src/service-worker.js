const { SETTINGS_KEY, endpoint } = require("./lib/settings");
const { initialState, reducePlayerState } = require("./lib/player-state");
const { installActionSidePanel } = require("./lib/action-side-panel");

let state = initialState();
let runId = 0;
let abortController = null;
let creatingOffscreen = null;

installActionSidePanel(chrome, {
  onError(error) {
    console.error("Unable to open the side panel from the extension action.", error);
  }
});

async function ensureOffscreen() {
  const existing = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  if (existing.length) return;
  if (!creatingOffscreen) {
    creatingOffscreen = chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["AUDIO_PLAYBACK"],
      justification: "播放使用者已確認的台語新聞語音"
    }).finally(() => { creatingOffscreen = null; });
  }
  await creatingOffscreen;
}

async function broadcastState(save = true) {
  if (save) await chrome.storage.session.set({ playbackState: state });
  chrome.runtime.sendMessage({ target: "sidepanel", type: "STATE", state }).catch(() => {});
}

async function transition(event, save = true) {
  state = reducePlayerState(state, event);
  await broadcastState(save);
}

function audioPayload(data) {
  const audio = data?.audio_base64 || data?.audio || data?.data?.audio_base64 || data?.data?.audio;
  if (typeof audio !== "string" || !audio) throw new Error("語音服務沒有回傳可播放的音訊。");
  const dataUrl = audio.match(/^data:([^;,]+);base64,(.+)$/s);
  return {
    base64: dataUrl ? dataUrl[2] : audio,
    mimeType: dataUrl ? dataUrl[1] : (data.mime_type || data.content_type || "audio/mpeg")
  };
}

async function readError(response) {
  try {
    const body = await response.json();
    return body.detail || body.error || body.message || `HTTP ${response.status}`;
  } catch {
    return `語音服務回傳錯誤（HTTP ${response.status}）。`;
  }
}

async function synthesize(backendUrl, text, rate, signal) {
  const response = await fetch(endpoint(backendUrl, "/v1/synthesize"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, source_language: "zh-TW", target_language: "nan-TW", rate }),
    signal
  });
  if (!response.ok) throw new Error(await readError(response));
  return audioPayload(await response.json());
}

async function runQueue(id, chunks, title, rate, backendUrl) {
  try {
    await ensureOffscreen();
    for (let index = 0; index < chunks.length; index += 1) {
      if (id !== runId) return;
      abortController = new AbortController();
      await transition({ type: "PREPARING", index });
      const audio = await synthesize(backendUrl, chunks[index], rate, abortController.signal);
      if (id !== runId) return;
      await transition({ type: "PLAYING", index });
      const result = await chrome.runtime.sendMessage({ target: "offscreen", type: "PLAY_AUDIO", ...audio });
      if (id !== runId) return;
      if (!result?.ok && result?.reason !== "stopped") throw new Error(result?.error || "無法播放語音。");
    }
    if (id === runId) await transition({ type: "COMPLETE" });
  } catch (error) {
    if (id !== runId || error?.name === "AbortError") return;
    await transition({ type: "ERROR", error: error?.message || "朗讀失敗。" });
  } finally {
    abortController = null;
  }
}

async function start(message) {
  const settings = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
  if (!settings?.backendUrl) throw new Error("尚未設定台語語音服務。");
  if (!Array.isArray(message.chunks) || !message.chunks.length) throw new Error("沒有可朗讀的文字。");

  runId += 1;
  abortController?.abort();
  chrome.runtime.sendMessage({ target: "offscreen", type: "STOP" }).catch(() => {});
  await transition({ type: "START", total: message.chunks.length, title: message.title, rate: message.rate });
  runQueue(runId, message.chunks, message.title, message.rate, settings.backendUrl);
}

async function stop(clear = false) {
  runId += 1;
  abortController?.abort();
  await chrome.runtime.sendMessage({ target: "offscreen", type: "STOP" }).catch(() => {});
  if (clear) {
    state = reducePlayerState(state, { type: "CLEAR" });
    await chrome.storage.session.clear();
    await broadcastState(false);
  } else {
    await transition({ type: "STOP" });
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.target !== "service-worker") return undefined;
  (async () => {
    switch (message.type) {
      case "START":
        await start(message);
        break;
      case "PAUSE":
        await chrome.runtime.sendMessage({ target: "offscreen", type: "PAUSE" });
        await transition({ type: "PAUSE" });
        break;
      case "RESUME":
        await ensureOffscreen();
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
    sendResponse({ ok: true });
  })().catch((error) => sendResponse({ ok: false, error: error?.message || "操作失敗。" }));
  return true;
});
