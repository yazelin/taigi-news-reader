const test = require("node:test");
const assert = require("node:assert/strict");
const {
  RECOMMENDED_BACKEND_URL,
  normalizeBackendUrl,
  originPermission,
  endpoint
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
