const { SETTINGS_KEY, normalizeBackendUrl, originPermission, endpoint } = require("./lib/settings");

const input = document.getElementById("backendUrl");
const saveButton = document.getElementById("saveButton");
const clearButton = document.getElementById("clearButton");
const status = document.getElementById("status");

function setStatus(message, error = false) {
  status.textContent = message;
  status.className = error ? "error" : "";
  status.hidden = !message;
}

async function healthCheck(backendUrl) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(endpoint(backendUrl, "/health"), { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } finally {
    clearTimeout(timer);
  }
}

async function save() {
  saveButton.disabled = true;
  setStatus("正在檢查網址與連線…");
  try {
    const backendUrl = normalizeBackendUrl(input.value);
    if (!backendUrl) throw new Error("請填入台語語音服務網址。");
    const origins = [originPermission(backendUrl)];
    const granted = await chrome.permissions.request({ origins });
    if (!granted) throw new Error("未取得連線權限，因此沒有儲存設定。");
    const previous = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
    await chrome.storage.local.set({ [SETTINGS_KEY]: { backendUrl } });
    if (previous?.backendUrl && originPermission(previous.backendUrl) !== origins[0]) {
      await chrome.permissions.remove({ origins: [originPermission(previous.backendUrl)] });
    }
    input.value = backendUrl;
    try {
      await healthCheck(backendUrl);
      setStatus("設定已儲存，語音服務連線正常。");
    } catch {
      setStatus("設定已儲存，但目前無法連上服務。請確認網址或服務狀態。", true);
    }
  } catch (error) {
    setStatus(error.message || "設定失敗。", true);
  } finally {
    saveButton.disabled = false;
  }
}

async function clear() {
  const current = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
  await chrome.storage.local.remove(SETTINGS_KEY);
  input.value = "";
  if (current?.backendUrl) {
    try {
      await chrome.permissions.remove({ origins: [originPermission(current.backendUrl)] });
    } catch {
      // The setting is cleared even if Chrome retains a previously granted origin.
    }
  }
  setStatus("設定已清除。");
}

saveButton.addEventListener("click", save);
clearButton.addEventListener("click", clear);

chrome.storage.local.get(SETTINGS_KEY).then((result) => {
  input.value = result[SETTINGS_KEY]?.backendUrl || "";
});
