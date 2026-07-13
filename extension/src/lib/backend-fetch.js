const EXTENSION_CLIENT_ID_HEADER = "X-Taigi-Extension-Id";
const AUTHORIZATION_HEADER = "Authorization";

function requiresAccessToken(input) {
  const target = typeof input === "string" ? input : input?.url;
  if (!target) return true;
  try {
    return /\/v1(?:\/|$)/.test(new URL(target).pathname);
  } catch {
    return true;
  }
}

function createBackendFetch({
  fetchImpl,
  extensionId,
  getAccessToken,
  HeadersImpl = Headers
}) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetchImpl must be a function");
  const clientId = typeof extensionId === "string" ? extensionId.trim() : "";
  if (!clientId) throw new TypeError("extensionId must be a non-empty string");
  if (typeof getAccessToken !== "function") throw new TypeError("getAccessToken must be a function");

  return async function backendFetch(input, init = {}) {
    const headers = new HeadersImpl(init.headers);
    // The Chrome extension ID is a stable client identifier, not a secret or
    // an authentication credential. The backend still owns authorization.
    headers.set(EXTENSION_CLIENT_ID_HEADER, clientId);
    if (requiresAccessToken(input)) {
      const accessToken = await getAccessToken(input);
      if (typeof accessToken !== "string" || !accessToken) {
        throw new Error("尚未設定私人測試邀請碼。");
      }
      // Callers cannot replace the invite credential or opt into redirecting it.
      headers.set(AUTHORIZATION_HEADER, `Bearer ${accessToken}`);
    } else {
      // Public health probes must never inherit a caller-provided credential.
      headers.delete(AUTHORIZATION_HEADER);
    }
    return fetchImpl(input, {
      ...init,
      credentials: "omit",
      redirect: "error",
      headers
    });
  };
}

module.exports = {
  AUTHORIZATION_HEADER,
  EXTENSION_CLIENT_ID_HEADER,
  createBackendFetch,
  requiresAccessToken
};
