const test = require("node:test");
const assert = require("node:assert/strict");
const {
  RECOMMENDED_BACKEND_URL,
  normalizeBackendUrl,
  normalizeAccessToken,
  originPermission,
  endpoint,
  storedAccessToken
} = require("../src/lib/settings");

test("accepts HTTPS and removes trailing slashes", () => {
  assert.equal(normalizeBackendUrl(" https://tts.example.com/// "), "https://tts.example.com");
  assert.equal(endpoint("https://tts.example.com/", "/health"), "https://tts.example.com/health");
});

test("allows HTTP only for local development", () => {
  assert.equal(normalizeBackendUrl("http://127.0.0.1:8765"), "http://127.0.0.1:8765");
  assert.throws(() => normalizeBackendUrl("http://tts.example.com"), /HTTPS/);
});

test("requests only the selected origin", () => {
  assert.equal(originPermission("https://tts.example.com/api"), "https://tts.example.com/*");
});

test("recommended hosted service uses the reviewed HTTPS path", () => {
  assert.equal(
    normalizeBackendUrl(RECOMMENDED_BACKEND_URL),
    "https://ching-tech.ddns.net/taigi-tts"
  );
  assert.equal(
    endpoint(RECOMMENDED_BACKEND_URL, "/health"),
    "https://ching-tech.ddns.net/taigi-tts/health"
  );
});

test("invite tokens are opaque, trimmed, bounded, and read only from local settings", async () => {
  assert.equal(normalizeAccessToken("  private_test-token.123  "), "private_test-token.123");
  assert.throws(() => normalizeAccessToken(""), /邀請碼/);
  assert.throws(() => normalizeAccessToken("token with spaces"), /格式不正確/);
  assert.throws(() => normalizeAccessToken("x".repeat(513)), /512 bytes/);

  const calls = [];
  const storageArea = {
    async get(key) {
      calls.push(key);
      return {
        [key]: {
          backendUrl: "https://tts.example/base",
          accessToken: "stored-token",
          accessTokenOrigin: "https://tts.example"
        }
      };
    }
  };
  assert.equal(await storedAccessToken(storageArea, "https://tts.example/base/v1/access"), "stored-token");
  await assert.rejects(
    storedAccessToken(storageArea, "https://attacker.example/v1/access"),
    /不會送到其他網域/
  );
  assert.deepEqual(calls, ["taigiSettings", "taigiSettings"]);
});
