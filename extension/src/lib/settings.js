const SETTINGS_KEY = "taigiSettings";
const RECOMMENDED_BACKEND_URL = "https://ching-tech.ddns.net/taigi-tts";

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

module.exports = {
  RECOMMENDED_BACKEND_URL,
  SETTINGS_KEY,
  normalizeBackendUrl,
  originPermission,
  endpoint
};
