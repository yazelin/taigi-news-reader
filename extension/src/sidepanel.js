const { chunkText, normalizeText } = require("./lib/chunk");
const { SETTINGS_KEY, endpoint, originPermission } = require("./lib/settings");
const { initialState } = require("./lib/player-state");

const elements = Object.fromEntries([
  "message", "setupCard", "setupButton", "settingsButton", "extractButton", "previewCard", "title",
  "sourceChooser", "preview", "textStats", "rate", "startButton", "playerCard", "progress",
  "pauseButton", "resumeButton", "stopButton", "clearButton"
].map((id) => [id, document.getElementById(id)]));

let extraction = null;
let playbackState = initialState();

function showMessage(text, kind = "error") {
  elements.message.textContent = text;
  elements.message.className = `message ${kind === "info" ? "info" : ""}`;
  elements.message.hidden = !text;
}

function showSetup(show, reason = "") {
  elements.setupCard.hidden = !show;
  if (show && reason) showMessage(reason);
}

async function getSettings() {
  const result = await chrome.storage.local.get(SETTINGS_KEY);
  return result[SETTINGS_KEY] || { backendUrl: "" };
}

async function checkBackend() {
  const settings = await getSettings();
  if (!settings.backendUrl) {
    showSetup(true, "尚未設定台語語音服務。請先完成設定。");
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
      const response = await fetch(endpoint(settings.backendUrl, "/health"), { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
  if (!(await checkBackend())) return;
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

function renderPlayer(state) {
  playbackState = state || initialState();
  const active = !["idle", "stopped"].includes(playbackState.status);
  elements.playerCard.hidden = !active;
  elements.startButton.disabled = ["preparing", "playing", "paused"].includes(playbackState.status);
  elements.pauseButton.disabled = playbackState.status !== "playing";
  elements.resumeButton.disabled = playbackState.status !== "paused";
  elements.stopButton.disabled = !["preparing", "playing", "paused"].includes(playbackState.status);

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
  const response = await chrome.runtime.sendMessage({ target: "service-worker", type });
  if (!response?.ok) showMessage(response?.error || "操作失敗。");
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
elements.clearButton.addEventListener("click", clearSession);
elements.setupButton.addEventListener("click", () => chrome.runtime.openOptionsPage());
elements.settingsButton.addEventListener("click", () => chrome.runtime.openOptionsPage());
elements.preview.addEventListener("input", updateStats);
elements.sourceChooser.addEventListener("change", updatePreview);

chrome.runtime.onMessage.addListener((message) => {
  if (message.target === "sidepanel" && message.type === "STATE") renderPlayer(message.state);
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[SETTINGS_KEY]) checkBackend();
});

chrome.storage.session.get("playbackState").then(({ playbackState: stored }) => renderPlayer(stored || initialState()));
checkBackend();
