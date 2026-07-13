const EXTENSION_CLIENT_ID_HEADER = "X-Taigi-Extension-Id";

function createBackendFetch({
  fetchImpl,
  extensionId,
  HeadersImpl = Headers
}) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetchImpl must be a function");
  const clientId = typeof extensionId === "string" ? extensionId.trim() : "";
  if (!clientId) throw new TypeError("extensionId must be a non-empty string");

  return function backendFetch(input, init = {}) {
    const headers = new HeadersImpl(init.headers);
    // The Chrome extension ID is a stable client identifier, not a secret or
    // an authentication credential. The backend still owns authorization.
    headers.set(EXTENSION_CLIENT_ID_HEADER, clientId);
    return fetchImpl(input, { ...init, headers });
  };
}

module.exports = { EXTENSION_CLIENT_ID_HEADER, createBackendFetch };
