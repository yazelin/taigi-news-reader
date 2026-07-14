const test = require("node:test");
const assert = require("node:assert/strict");
const manifest = require("../src/manifest.json");
const {
  extractPage,
  pageReadErrorMessage,
  shouldInvalidatePageContext
} = require("../src/lib/page-reader");

test("extractPage injects and reads from the exact action tab", async () => {
  const calls = [];
  const extraction = { title: "新聞", body: "這是一段足夠長的新聞正文內容。" };
  const chromeApi = {
    scripting: {
      async executeScript(injection) {
        calls.push(injection);
        return injection.files ? [] : [{ result: extraction }];
      }
    }
  };

  assert.equal(await extractPage(chromeApi, 42), extraction);
  assert.deepEqual(calls[0], { target: { tabId: 42 }, files: ["extractor.js"] });
  assert.deepEqual(calls[1].target, { tabId: 42 });
  assert.equal(typeof calls[1].func, "function");
  await assert.rejects(() => extractPage(chromeApi, undefined), /找不到目前的網頁分頁/);
});

test("page-read access errors distinguish a revoked activeTab grant from restricted pages", () => {
  const error = new Error("Cannot access contents of url. Missing host permission.");
  assert.match(pageReadErrorMessage(error), /再按一次瀏覽器工具列/);
  assert.match(pageReadErrorMessage(error), /側欄不用關閉/);
  assert.match(pageReadErrorMessage(error, { grantedByAction: true }), /頁面在授權後已切換/);
  assert.equal(pageReadErrorMessage(new Error("找不到足夠的新聞文字。")), "找不到足夠的新聞文字。");
});

test("tab activation and navigation can invalidate stale preview without tabs host access", () => {
  assert.equal(shouldInvalidatePageContext(42, 42, { status: "loading" }), true);
  assert.equal(shouldInvalidatePageContext(42, 42, { url: "https://example.test/next" }), true);
  assert.equal(shouldInvalidatePageContext(42, 42, { status: "complete" }), false);
  assert.equal(shouldInvalidatePageContext(42, 99, { status: "loading" }), false);
  assert.equal(shouldInvalidatePageContext(null, 42, { status: "loading" }), false);
});

test("page reading keeps activeTab instead of adding persistent page host access", () => {
  assert.equal(manifest.host_permissions, undefined);
  assert.ok(manifest.permissions.includes("activeTab"));
  assert.ok(manifest.permissions.includes("scripting"));
});
