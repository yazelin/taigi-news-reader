const {
  RECOMMENDED_BACKEND_URL,
  SETTINGS_KEY,
  backendOrigin,
  normalizeBackendUrl,
  normalizeAccessToken,
  originPermission,
  endpoint
} = require("./lib/settings");
const { createBackendFetch } = require("./lib/backend-fetch");

const backendInput = document.getElementById("backendUrl");
const inviteCodeInput = document.getElementById("inviteCode");
const recommendedButton = document.getElementById("recommendedButton");
const saveButton = document.getElementById("saveButton");
const clearButton = document.getElementById("clearButton");
const status = document.getElementById("status");
let inviteCodeOrigin = "";
const trustedStorageReady = chrome.storage.local.setAccessLevel
  ? chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" })
  : Promise.resolve();

async function ensureTrustedStorage() {
  try {
    await trustedStorageReady;
  } catch {
    throw new Error("無法保護本機邀請碼儲存空間，設定未變更。請重新載入擴充套件後再試。");
  }
}

function setStatus(message, error = false) {
  status.textContent = message;
  status.className = error ? "error" : "";
  status.hidden = !message;
}

function candidateBackendFetch(backendUrl, accessToken) {
  const allowedOrigin = backendOrigin(backendUrl);
  return createBackendFetch({
    fetchImpl: (...args) => fetch(...args),
    extensionId: chrome.runtime.id,
    getAccessToken: async (requestUrl) => {
      const target = typeof requestUrl === "string" ? requestUrl : requestUrl?.url;
      if (!target || new URL(target).origin !== allowedOrigin) {
        throw new Error("基於安全考量，邀請碼不會送到其他網域。");
      }
      return accessToken;
    }
  });
}

async function verifyAccess(backendUrl, accessToken) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await candidateBackendFetch(backendUrl, accessToken)(endpoint(backendUrl, "/v1/access"), {
      signal: controller.signal
    });
    if (response.status === 401 || response.status === 403) {
      throw new Error("邀請碼無效、已撤銷或不屬於這個服務。");
    }
    if (!response.ok) throw new Error(`語音服務驗證失敗（HTTP ${response.status}）。`);
  } catch (error) {
    if (error?.name === "AbortError") throw new Error("語音服務驗證逾時，請確認網路後再試一次。");
    if (error?.name === "TypeError") throw new Error("無法安全連上語音服務，請確認網址與 HTTPS 設定。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function prepareSettingsChange() {
  try {
    const response = await chrome.runtime.sendMessage({
      target: "service-worker",
      type: "PREPARE_SETTINGS_CHANGE"
    });
    return response?.ok === true;
  } catch {
    return false;
  }
}

async function removeOrigin(backendUrl) {
  if (!backendUrl) return true;
  const origins = [originPermission(backendUrl)];
  try {
    await chrome.permissions.remove({ origins });
    return !(await chrome.permissions.contains({ origins }));
  } catch {
    return false;
  }
}

async function save() {
  saveButton.disabled = true;
  recommendedButton.disabled = true;
  clearButton.disabled = true;
  setStatus("正在驗證網址與私人測試邀請碼…");
  let newlyGrantedOrigin = "";
  let saved = false;
  try {
    await ensureTrustedStorage();
    const backendUrl = normalizeBackendUrl(backendInput.value);
    if (!backendUrl) throw new Error("請填入台語語音服務網址。");
    const accessTokenOrigin = backendOrigin(backendUrl);
    const accessToken = normalizeAccessToken(inviteCodeInput.value);
    if (inviteCodeOrigin !== accessTokenOrigin) {
      throw new Error("服務網域已變更，請重新輸入這個網域專用的邀請碼。");
    }
    const origins = [originPermission(backendUrl)];
    const previous = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
    const alreadyGranted = await chrome.permissions.contains({ origins });
    const granted = await chrome.permissions.request({ origins });
    if (!granted) throw new Error("未取得連線權限，因此沒有儲存設定。");
    if (!alreadyGranted) newlyGrantedOrigin = origins[0];

    await verifyAccess(backendUrl, accessToken);
    const changed = previous?.backendUrl !== backendUrl || previous?.accessToken !== accessToken;
    const cleanupComplete = !changed || await prepareSettingsChange();
    await chrome.storage.local.set({ [SETTINGS_KEY]: { backendUrl, accessToken, accessTokenOrigin } });
    saved = true;
    if (previous?.backendUrl && originPermission(previous.backendUrl) !== origins[0]) {
      await removeOrigin(previous.backendUrl);
    }
    backendInput.value = backendUrl;
    inviteCodeInput.value = accessToken;
    inviteCodeOrigin = accessTokenOrigin;
    setStatus(cleanupComplete
      ? "邀請碼有效，私人測試服務已儲存並可使用。"
      : "邀請碼有效且設定已儲存；舊的背景工作可能尚待伺服器自動清理。", !cleanupComplete);
  } catch (error) {
    if (!saved && newlyGrantedOrigin) {
      try {
        await chrome.permissions.remove({ origins: [newlyGrantedOrigin] });
      } catch {
        // Keep the previous settings intact even if Chrome retains the newly granted origin.
      }
    }
    setStatus(error.message || "設定失敗。", true);
  } finally {
    saveButton.disabled = false;
    recommendedButton.disabled = false;
    clearButton.disabled = false;
  }
}

async function clear() {
  saveButton.disabled = true;
  recommendedButton.disabled = true;
  clearButton.disabled = true;
  try {
    await ensureTrustedStorage();
    const current = (await chrome.storage.local.get(SETTINGS_KEY))[SETTINGS_KEY];
    const cleanupComplete = await prepareSettingsChange();
    await chrome.storage.local.remove(SETTINGS_KEY);
    backendInput.value = "";
    inviteCodeInput.value = "";
    inviteCodeOrigin = "";
    const originRemoved = await removeOrigin(current?.backendUrl);
    setStatus(cleanupComplete && originRemoved
      ? "服務網址與本機邀請碼已清除，連線權限也已撤銷。"
      : "本機設定與邀請碼已清除；舊工作或 Chrome 連線權限可能尚待清理。", !(cleanupComplete && originRemoved));
  } catch {
    setStatus("設定清除失敗，請稍後再試。", true);
  } finally {
    saveButton.disabled = false;
    recommendedButton.disabled = false;
    clearButton.disabled = false;
  }
}

saveButton.addEventListener("click", save);
recommendedButton.addEventListener("click", () => {
  backendInput.value = RECOMMENDED_BACKEND_URL;
  clearInviteCodeForChangedOrigin();
  setStatus("已填入建議服務網址。請輸入測試管理者提供的邀請碼，再按「同意並儲存、測試」。");
  inviteCodeInput.focus();
});
clearButton.addEventListener("click", clear);

function currentBackendOrigin() {
  try {
    return backendOrigin(backendInput.value);
  } catch {
    return "";
  }
}

function clearInviteCodeForChangedOrigin() {
  if (!inviteCodeInput.value || currentBackendOrigin() === inviteCodeOrigin) return;
  inviteCodeInput.value = "";
  inviteCodeOrigin = "";
  setStatus("服務網域已變更。為避免洩漏，舊邀請碼已從欄位清除；請輸入新網域的邀請碼。", true);
}

backendInput.addEventListener("input", clearInviteCodeForChangedOrigin);
inviteCodeInput.addEventListener("input", () => {
  inviteCodeOrigin = currentBackendOrigin();
});

ensureTrustedStorage().then(() => chrome.storage.local.get(SETTINGS_KEY)).then((result) => {
  const settings = result[SETTINGS_KEY] || {};
  backendInput.value = settings.backendUrl || "";
  const configuredOrigin = currentBackendOrigin();
  if (settings.accessToken && settings.accessTokenOrigin === configuredOrigin) {
    inviteCodeInput.value = settings.accessToken;
    inviteCodeOrigin = configuredOrigin;
  } else {
    inviteCodeInput.value = "";
    inviteCodeOrigin = "";
    if (settings.accessToken || settings.accessTokenOrigin) {
      chrome.storage.local.set({ [SETTINGS_KEY]: { backendUrl: settings.backendUrl || "" } }).catch(() => {});
    }
  }
}).catch((error) => setStatus(error.message || "無法讀取設定。", true));
