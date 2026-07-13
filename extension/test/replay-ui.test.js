const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

test("side panel exposes an explicit local-only replay opt-in and clear controls", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "sidepanel.html"), "utf8");
  const document = new JSDOM(source).window.document;

  assert.equal(document.getElementById("replayEnabled").checked, false);
  assert.equal(document.querySelector("label[for='replayEnabled']").textContent.trim(), "在這台電腦保留朗讀音訊");
  assert.match(document.querySelector(".privacy-note").textContent, /預設關閉/);
  assert.match(document.querySelector(".privacy-note").textContent, /最近 5 篇、50 MiB、7 天/);
  assert.match(document.querySelector(".privacy-note").textContent, /不保存新聞全文、網址或 API key/);
  assert.equal(document.getElementById("replayButton").textContent.trim(), "重新播放");
  assert.equal(document.getElementById("clearHistoryButton").textContent.trim(), "清除所有重播記錄");
  assert.equal(document.getElementById("quotaStatus").hidden, true);
  assert.notEqual(document.getElementById("clearButton"), document.getElementById("clearHistoryButton"));
});

test("side panel displays only parsed per-user quota and refreshes it after remote work", () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "src", "sidepanel.js"), "utf8");
  const worker = fs.readFileSync(path.join(__dirname, "..", "src", "service-worker.js"), "utf8");

  assert.match(script, /formatAccessQuota\(parseAccessQuota\(body\)\)/);
  assert.match(script, /message\.type === "QUOTA_CHANGED"/);
  assert.match(worker, /if \(!cachedAudio\)[\s\S]*type: "QUOTA_CHANGED"/);
});

test("cached START and history replay are not gated on a backend health request", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "sidepanel.js"), "utf8");
  const startReading = source.match(/async function startReading\(\) \{([\s\S]*?)\n\}/)?.[1] || "";
  const replayEntry = source.match(/async function replayEntry\(id\) \{([\s\S]*?)\n\}/)?.[1] || "";

  assert.doesNotMatch(startReading, /checkBackend/);
  assert.match(startReading, /type: "START"/);
  assert.doesNotMatch(replayEntry, /checkBackend|fetch\(/);
  assert.match(replayEntry, /sendCommand\("REPLAY"/);
});

test("mock replay audio is clearly disclosed as not Taiwanese TTS", () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "src", "sidepanel.js"), "utf8");
  const identity = fs.readFileSync(path.join(__dirname, "..", "src", "lib", "backend-identity.js"), "utf8");
  const markup = fs.readFileSync(path.join(__dirname, "..", "src", "sidepanel.html"), "utf8");
  const document = new JSDOM(markup).window.document;

  assert.match(script, /describeService\(entry\.service\)/);
  assert.match(script, /entry\.service\?\.mode === "mock"/);
  assert.match(identity, /測試音訊（不是台語 TTS）/);
  assert.ok(document.getElementById("replayService"));
});
