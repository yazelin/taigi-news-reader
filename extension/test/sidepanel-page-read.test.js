const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "..", "src", "sidepanel.js"), "utf8");

test("side panel claims action reads on startup and when an already-open panel is notified", () => {
  assert.match(source, /type:\s*"TAKE_PENDING_PAGE_READ"/);
  assert.match(source, /message\.type === "READ_PAGE_AVAILABLE"\) schedulePendingPageRead\(\)/);
  assert.match(source, /checkBackend\(\);\s*schedulePendingPageRead\(\);/);
  assert.match(source, /schedulePageExtraction\(request\.tabId, \{ grantedByAction: true \}\)/);
});

test("side panel invalidates old extraction on tab switches and navigation", () => {
  assert.match(source, /chrome\.tabs\.onActivated\.addListener/);
  assert.match(source, /chrome\.tabs\.onUpdated\.addListener/);
  assert.match(source, /shouldInvalidatePageContext\(activeTabId, tabId, changeInfo\)/);
  assert.match(source, /頁面已切換，舊內容已清除/);
});
