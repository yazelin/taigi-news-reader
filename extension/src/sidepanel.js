const { chunkText, normalizeText } = require("./lib/chunk");
const { SETTINGS_KEY, endpoint, originPermission, storedAccessToken } = require("./lib/settings");
const { initialState } = require("./lib/player-state");
const { describeService } = require("./lib/backend-identity");
const { createBackendFetch } = require("./lib/backend-fetch");
const { formatAccessQuota, parseAccessQuota } = require("./lib/access-status");

const backendFetch = createBackendFetch({
  fetchImpl: (...args) => fetch(...args),
  extensionId: chrome.runtime.id,
  getAccessToken: (requestUrl) => storedAccessToken(chrome.storage.local, requestUrl)
});

const elements = Object.fromEntries([
  "message", "quotaStatus", "setupCard", "setupButton", "settingsButton", "extractButton", "previewCard", "title",
  "sourceChooser", "preview", "textStats", "rate", "startButton", "playerCard", "progress",
  "pauseButton", "resumeButton", "stopButton", "replayButton", "replayService", "replayEnabled", "historyEmpty",
  "historyList", "clearHistoryButton", "clearButton"
].map((id) => [id, document.getElementById(id)]));

let extraction = null;
let playbackState = initialState();
let replayHistory = [];
const trustedStorageReady = chrome.storage.local.setAccessLevel
  ? chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" })
  : Promise.resolve();

function showMessage(text, kind = "error") {
  elements.message.textContent = text;
  elements.message.className = `message ${kind === "info" ? "info" : ""}`;
  elements.message.hidden = !text;
}

function showSetup(show, reason = "") {
  elements.setupCard.hidden = !show;
  if (show && reason) showMessage(reason);
}

function showQuota(body) {
  const message = formatAccessQuota(parseAccessQuota(body));
  elements.quotaStatus.textContent = message;
  elements.quotaStatus.hidden = !message;
}

function hideQuota() {
  elements.quotaStatus.textContent = "";
  elements.quotaStatus.hidden = true;
}

async function getSettings() {
  try {
    await trustedStorageReady;
  } catch {
    throw new Error("無法保護本機邀請碼儲存空間，請重新載入擴充套件後再試。");
  }
  const result = await chrome.storage.local.get(SETTINGS_KEY);
  return result[SETTINGS_KEY] || { backendUrl: "" };
}

async function checkBackend() {
  hideQuota();
  let settings;
  try {
    settings = await getSettings();
  } catch (error) {
    showSetup(true, error.message || "無法讀取台語語音服務設定。");
    return false;
  }
  if (!settings.backendUrl) {
    showSetup(true, "尚未設定台語語音服務。請先完成設定。");
    return false;
  }
  if (!settings.accessToken) {
    showSetup(true, "尚未設定私人測試邀請碼。請到設定頁輸入邀請碼並完成驗證。");
    return false;
  }
  const hasPermission = await chrome.permissions.contains({ origins: [originPermission(settings.backendUrl)] });
  if (!hasPermission) {
    showSetup(true, "語音服務權限尚未完成，請到設定頁重新儲存網址。");
    return false;
  }
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4500);
    try {
      const response = await backendFetch(endpoint(settings.backendUrl, "/v1/access"), { signal: controller.signal });
      if (response.status === 401 || response.status === 403) {
        showSetup(true, "私人測試邀請碼無效或已撤銷，請到設定頁重新輸入。");
        return false;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      try {
        showQuota(await response.json());
      } catch {
        hideQuota();
      }
    } finally {
      clearTimeout(timer);
    }
    showSetup(false);
    return true;
  } catch {
    showSetup(true, "目前無法連上台語語音服務。請檢查設定或稍後再試。");
    return false;
  }
}

function selectedSource() {
  return document.querySelector("input[name='source']:checked")?.value || "article";
}

function updatePreview() {
  if (!extraction) return;
  const source = selectedSource();
  elements.preview.value = source === "selection" ? extraction.selectedText : extraction.body;
  updateStats();
}

function updateStats() {
  const chunks = chunkText(elements.preview.value);
  elements.textStats.textContent = `共 ${elements.preview.value.length.toLocaleString("zh-TW")} 字，將分成 ${chunks.length} 段朗讀。`;
}

async function extractCurrentPage() {
  showMessage("");
  elements.extractButton.disabled = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("找不到目前的網頁分頁。");
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["extractor.js"] });
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => globalThis.TaigiNewsExtractor.extract()
    });
    extraction = results[0]?.result;
    if (!extraction || normalizeText(extraction.body).length < 20) {
      throw new Error("找不到足夠的新聞文字。你可以先在網頁上選取要朗讀的段落，再按一次「讀取這一頁」。");
    }
    elements.title.value = extraction.title;
    elements.sourceChooser.hidden = !extraction.selectedText || extraction.selectedText === extraction.body;
    const defaultSource = extraction.source === "selection" ? "selection" : "article";
    const defaultRadio = document.querySelector(`input[name='source'][value='${defaultSource}']`);
    if (defaultRadio) defaultRadio.checked = true;
    elements.previewCard.hidden = false;
    updatePreview();
    showMessage("新聞內容已讀取。請先確認內容，再開始朗讀。", "info");
  } catch (error) {
    const restricted = /Cannot access|chrome:\/\/|Missing host permission/i.test(error?.message || "");
    showMessage(restricted ? "這個頁面不允許擴充套件讀取。請改開一般新聞網站後再試。" : error.message);
  } finally {
    elements.extractButton.disabled = false;
  }
}

async function startReading() {
  showMessage("");
  const text = normalizeText(elements.preview.value);
  const chunks = chunkText(text);
  if (!chunks.length) {
    showMessage("沒有可朗讀的內容，請先讀取新聞或輸入文字。");
    return;
  }
  elements.startButton.disabled = true;
  try {
    const response = await chrome.runtime.sendMessage({
      target: "service-worker",
      type: "START",
      chunks,
      title: normalizeText(elements.title.value) || "未命名新聞",
      rate: Number(elements.rate.value)
    });
    if (!response?.ok) throw new Error(response?.error || "無法開始朗讀。");
  } catch (error) {
    showMessage(error.message);
    elements.startButton.disabled = false;
  }
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function historyItem(entry) {
  const item = document.createElement("li");
  item.className = "history-item";

  const details = document.createElement("div");
  details.className = "history-details";
  const title = document.createElement("strong");
  title.textContent = entry.title;
  const service = document.createElement("span");
  service.className = `service-badge${entry.service?.mode === "mock" ? " mock" : ""}`;
  service.textContent = describeService(entry.service);
  const metadata = document.createElement("span");
  metadata.className = "muted";
  metadata.textContent = `${new Date(entry.lastPlayedAt).toLocaleString("zh-TW")}・${entry.rate} 倍・${formatBytes(entry.bytes)}`;
  details.append(title, service, metadata);

  const actions = document.createElement("div");
  actions.className = "history-actions";
  const replay = document.createElement("button");
  replay.type = "button";
  replay.className = "primary";
  replay.dataset.action = "replay";
  replay.dataset.id = entry.id;
  replay.textContent = "重播";
  replay.setAttribute("aria-label", `重播：${entry.title}`);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "secondary";
  remove.dataset.action = "delete";
  remove.dataset.id = entry.id;
  remove.textContent = "刪除";
  remove.setAttribute("aria-label", `刪除重播記錄：${entry.title}`);
  actions.append(replay, remove);
  item.append(details, actions);
  return item;
}

function renderHistory(enabled, history = []) {
  replayHistory = history;
  elements.replayEnabled.checked = enabled;
  elements.historyList.replaceChildren(...history.map(historyItem));
  elements.historyList.hidden = !enabled || history.length === 0;
  elements.clearHistoryButton.hidden = !enabled || history.length === 0;
  elements.historyEmpty.hidden = enabled && history.length > 0;
  elements.historyEmpty.textContent = enabled
    ? "還沒有可重播的新聞；完整朗讀一篇後會顯示在這裡。"
    : "尚未開啟本機重播記錄。";
  renderReplayService();
}

function renderReplayService() {
  const entry = replayHistory.find(({ id }) => id === playbackState.replayId);
  const visible = playbackState.status === "completed" && Boolean(entry);
  elements.replayService.hidden = !visible;
  if (!visible) return;
  elements.replayService.className = `service-disclosure${entry.service?.mode === "mock" ? " mock" : ""}`;
  elements.replayService.textContent = `語音來源：${describeService(entry.service)}`;
}

async function sendCommand(type, payload = {}) {
  const response = await chrome.runtime.sendMessage({ target: "service-worker", type, ...payload });
  if (!response?.ok) throw new Error(response?.error || "操作失敗。");
  return response;
}

async function loadReplayHistory() {
  try {
    const response = await sendCommand("GET_REPLAY_HISTORY");
    renderHistory(response.enabled, response.history);
    if (response.warning) showMessage(response.warning);
  } catch (error) {
    showMessage(error.message);
  }
}

async function setReplayEnabled() {
  const enabled = elements.replayEnabled.checked;
  if (!enabled && !window.confirm("關閉後會立即刪除這台電腦上的所有重播音訊。確定要關閉嗎？")) {
    elements.replayEnabled.checked = true;
    return;
  }
  elements.replayEnabled.disabled = true;
  try {
    const response = await sendCommand("SET_REPLAY_ENABLED", { enabled });
    renderHistory(response.enabled, response.history);
    showMessage(response.warning || (enabled
      ? "已開啟本機重播記錄；下一篇完整朗讀後即可免 API 重播。"
      : "已關閉並刪除所有本機重播記錄。"), "info");
  } catch (error) {
    showMessage(error.message);
    await loadReplayHistory();
  } finally {
    elements.replayEnabled.disabled = false;
  }
}

async function replayEntry(id) {
  showMessage("");
  try {
    await sendCommand("REPLAY", { id });
  } catch (error) {
    showMessage(error.message);
    await loadReplayHistory();
  }
}

async function handleHistoryAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  button.disabled = true;
  try {
    if (button.dataset.action === "replay") {
      await replayEntry(button.dataset.id);
    } else if (button.dataset.action === "delete") {
      const response = await sendCommand("DELETE_REPLAY", { id: button.dataset.id });
      renderHistory(true, response.history);
      showMessage("已刪除這筆重播記錄。", "info");
    }
  } catch (error) {
    showMessage(error.message);
  } finally {
    button.disabled = false;
  }
}

async function clearReplayHistory() {
  if (!window.confirm("確定要刪除這台電腦上的所有重播音訊嗎？")) return;
  try {
    await sendCommand("CLEAR_REPLAY_HISTORY");
    renderHistory(true, []);
    showMessage("已清除所有本機重播記錄。", "info");
  } catch (error) {
    showMessage(error.message);
  }
}

function renderPlayer(state) {
  playbackState = state || initialState();
  const active = !["idle", "stopped"].includes(playbackState.status);
  elements.playerCard.hidden = !active;
  elements.startButton.disabled = ["preparing", "playing", "paused"].includes(playbackState.status);
  elements.pauseButton.disabled = playbackState.status !== "playing";
  elements.resumeButton.disabled = playbackState.status !== "paused";
  elements.stopButton.disabled = !["preparing", "playing", "paused"].includes(playbackState.status);
  const completed = playbackState.status === "completed";
  elements.pauseButton.hidden = completed;
  elements.resumeButton.hidden = completed;
  elements.stopButton.hidden = completed;
  elements.replayButton.hidden = !completed || !playbackState.replayId;
  renderReplayService();

  const labels = {
    preparing: "正在準備語音…",
    playing: `正在播放第 ${Math.min(playbackState.index + 1, playbackState.total)} 段，共 ${playbackState.total} 段`,
    paused: `已暫停在第 ${Math.min(playbackState.index + 1, playbackState.total)} 段`,
    completed: "新聞已朗讀完畢。",
    error: "朗讀中斷。"
  };
  elements.progress.textContent = labels[playbackState.status] || "";
  if (playbackState.status === "error") showMessage(playbackState.error || "朗讀失敗，請稍後再試。");
}

async function command(type) {
  try {
    await sendCommand(type);
  } catch (error) {
    showMessage(error.message);
  }
}

async function clearSession() {
  await command("CLEAR");
  extraction = null;
  elements.title.value = "";
  elements.preview.value = "";
  elements.previewCard.hidden = true;
  showMessage("");
  renderPlayer(initialState());
}

elements.extractButton.addEventListener("click", extractCurrentPage);
elements.startButton.addEventListener("click", startReading);
elements.pauseButton.addEventListener("click", () => command("PAUSE"));
elements.resumeButton.addEventListener("click", () => command("RESUME"));
elements.stopButton.addEventListener("click", () => command("STOP"));
elements.replayButton.addEventListener("click", () => replayEntry(playbackState.replayId));
elements.replayEnabled.addEventListener("change", setReplayEnabled);
elements.historyList.addEventListener("click", handleHistoryAction);
elements.clearHistoryButton.addEventListener("click", clearReplayHistory);
elements.clearButton.addEventListener("click", clearSession);
elements.setupButton.addEventListener("click", () => chrome.runtime.openOptionsPage());
elements.settingsButton.addEventListener("click", () => chrome.runtime.openOptionsPage());
elements.preview.addEventListener("input", updateStats);
elements.sourceChooser.addEventListener("change", updatePreview);

chrome.runtime.onMessage.addListener((message) => {
  if (message.target === "sidepanel" && message.type === "STATE") renderPlayer(message.state);
  if (message.target === "sidepanel" && message.type === "NOTICE") showMessage(message.message, "info");
  if (message.target === "sidepanel" && message.type === "HISTORY_CHANGED") loadReplayHistory();
  if (message.target === "sidepanel" && message.type === "QUOTA_CHANGED") checkBackend();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[SETTINGS_KEY]) checkBackend();
});

chrome.storage.session.get("playbackState").then(({ playbackState: stored }) => renderPlayer(stored || initialState()));
loadReplayHistory();
checkBackend();
