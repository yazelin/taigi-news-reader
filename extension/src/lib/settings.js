const SETTINGS_KEY = "taigiSettings";
const RECOMMENDED_BACKEND_URL = "https://ching-tech.ddns.net/taigi-tts";
const MAX_ACCESS_TOKEN_BYTES = 512;

function normalizeBackendUrl(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";

  let url;
  try {
    url = new URL(trimmed);
  } catch {
    throw new Error("服務網址格式不正確。例：https://tts.example.com");
  }

  const local = url.hostname === "127.0.0.1" || url.hostname === "localhost";
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) {
    throw new Error("服務網址必須使用 HTTPS；本機 localhost 可使用 HTTP。");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("服務網址不可包含帳密、查詢參數或網址片段。");
  }
  return url.toString().replace(/\/$/, "");
}

function originPermission(backendUrl) {
  const url = new URL(normalizeBackendUrl(backendUrl));
  return `${url.origin}/*`;
}

function endpoint(backendUrl, path) {
  return `${normalizeBackendUrl(backendUrl)}${path}`;
}

function backendOrigin(backendUrl) {
  return new URL(normalizeBackendUrl(backendUrl)).origin;
}

function normalizeAccessToken(value) {
  const token = String(value || "").trim();
  if (!token) throw new Error("請填入私人測試邀請碼。");
  if (/\s/.test(token)) throw new Error("邀請碼格式不正確，請確認沒有空白或換行。");
  if (new TextEncoder().encode(token).byteLength > MAX_ACCESS_TOKEN_BYTES) {
    throw new Error("邀請碼格式不正確，長度不可超過 512 bytes。");
  }
  return token;
}

async function storedAccessToken(storageArea, requestUrl) {
  const result = await storageArea.get(SETTINGS_KEY);
  const settings = result[SETTINGS_KEY];
  if (!settings?.backendUrl || !settings?.accessToken) {
    throw new Error("尚未設定私人測試邀請碼。");
  }
  const configuredOrigin = backendOrigin(settings?.backendUrl);
  if (settings?.accessTokenOrigin !== configuredOrigin) {
    throw new Error("私人測試邀請碼未綁定到目前的語音服務，請重新完成設定。");
  }
  const target = typeof requestUrl === "string" ? requestUrl : requestUrl?.url;
  if (!target || new URL(target).origin !== configuredOrigin) {
    throw new Error("基於安全考量，私人測試邀請碼不會送到其他網域。");
  }
  return normalizeAccessToken(settings.accessToken);
}

module.exports = {
  MAX_ACCESS_TOKEN_BYTES,
  RECOMMENDED_BACKEND_URL,
  SETTINGS_KEY,
  backendOrigin,
  normalizeBackendUrl,
  normalizeAccessToken,
  originPermission,
  endpoint,
  storedAccessToken
};
