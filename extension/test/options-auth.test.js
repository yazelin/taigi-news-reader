const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const sourceRoot = path.join(__dirname, "..", "src");

test("options page keeps the private tester invite code masked and explains local storage", () => {
  const markup = fs.readFileSync(path.join(sourceRoot, "options.html"), "utf8");
  const document = new JSDOM(markup).window.document;
  const input = document.getElementById("inviteCode");

  assert.equal(input.type, "password");
  assert.equal(input.autocomplete, "off");
  assert.equal(input.getAttribute("spellcheck"), "false");
  assert.equal(input.maxLength, 512);
  assert.equal(document.getElementById("quotaStatus").hidden, true);
  assert.match(document.getElementById("inviteCodeHint").textContent, /只會保存在這個 Chrome 使用者設定檔/);
  assert.match(document.querySelector(".privacy").textContent, /供應商金鑰只放在伺服器/);
  assert.match(document.querySelector(".privacy").textContent, /不會寫入朗讀記錄或音訊/);
});

test("recommended service asks for an invite code instead of automatically saving", () => {
  const script = fs.readFileSync(path.join(sourceRoot, "options.js"), "utf8");
  const handler = script.match(/recommendedButton\.addEventListener\("click", \(\) => \{([\s\S]*?)\n\}\);/)?.[1] || "";

  assert.match(handler, /RECOMMENDED_BACKEND_URL/);
  assert.match(handler, /inviteCodeInput\.focus\(\)/);
  assert.doesNotMatch(handler, /\bsave\s*\(/);
  assert.match(script, /chrome\.storage\.local\.set\(\{ \[SETTINGS_KEY\]: \{ backendUrl, accessToken, accessTokenOrigin \} \}\)/);
  assert.match(script, /backendInput\.addEventListener\("input", clearInviteCodeForChangedOrigin\)/);
  assert.match(script, /舊邀請碼已從欄位清除/);
  assert.match(script, /formatAccessQuota\(quota\)/);
  assert.match(script, /parseAccessQuota\(await response\.json\(\)\)/);
  assert.doesNotMatch(script, /chrome\.storage\.session/);
});

test("invite credentials never enter replay, playback, or active-job records", () => {
  for (const relative of [
    "lib/active-job-store.js",
    "lib/player-state-store.js",
    "lib/replay-cache.js"
  ]) {
    const source = fs.readFileSync(path.join(sourceRoot, relative), "utf8");
    assert.doesNotMatch(source, /accessToken|inviteCode|Authorization/i, relative);
  }
});
