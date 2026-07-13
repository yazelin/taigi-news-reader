const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { installActionSidePanel } = require("../src/lib/action-side-panel");

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("opens the side panel from action.onClicked for the clicked tab", async () => {
  let listener;
  const behaviorCalls = [];
  const openCalls = [];
  const pending = new Map();
  const chromeApi = {
    action: { onClicked: { addListener(callback) { listener = callback; } } },
    sidePanel: {
      setPanelBehavior(options) {
        behaviorCalls.push(options);
        return Promise.resolve();
      },
      open(options) {
        openCalls.push(options);
        const operation = deferred();
        pending.set(options.tabId, operation);
        return operation.promise;
      }
    }
  };

  installActionSidePanel(chromeApi);
  assert.deepEqual(behaviorCalls, [{ openPanelOnActionClick: false }]);

  listener({ id: 42 });
  listener({ id: 42 });
  listener({});
  assert.deepEqual(openCalls, [{ tabId: 42 }], "duplicate clicks do not race the same tab");

  pending.get(42).resolve();
  await new Promise((resolve) => setImmediate(resolve));
  listener({ id: 42 });
  assert.deepEqual(openCalls, [{ tabId: 42 }, { tabId: 42 }], "a later click may reopen the panel");
});

test("service worker wires the explicit handler and never reenables interception", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "service-worker.js"), "utf8");
  assert.match(source, /installActionSidePanel\(chrome/);
  assert.doesNotMatch(source, /openPanelOnActionClick:\s*true/);
});
