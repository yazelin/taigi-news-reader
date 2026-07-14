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

function sessionStorage() {
  const values = {};
  return {
    values,
    async get(key) { return { [key]: values[key] }; },
    async remove(key) { delete values[key]; },
    async set(items) { Object.assign(values, items); }
  };
}

test("opens the side panel from action.onClicked for the clicked tab", async () => {
  let listener;
  let messageListener;
  const behaviorCalls = [];
  const openCalls = [];
  const pending = new Map();
  const storage = sessionStorage();
  const chromeApi = {
    action: { onClicked: { addListener(callback) { listener = callback; } } },
    runtime: {
      onMessage: { addListener(callback) { messageListener = callback; } },
      sendMessage() { return Promise.resolve(); }
    },
    storage: { session: storage },
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

  listener({ id: 42, windowId: 7 });
  listener({ id: 42, windowId: 7 });
  listener({});
  assert.deepEqual(openCalls, [{ tabId: 42 }], "duplicate clicks do not race the same tab");
  assert.equal(typeof messageListener, "function");

  pending.get(42).resolve();
  await new Promise((resolve) => setImmediate(resolve));
  listener({ id: 42, windowId: 7 });
  assert.deepEqual(openCalls, [{ tabId: 42 }, { tabId: 42 }], "a later click may reopen the panel");
});

test("keeps only tab identifiers until a newly opened side panel claims the action request", async () => {
  let actionListener;
  const notices = [];
  const storage = sessionStorage();
  const chromeApi = {
    action: { onClicked: { addListener(callback) { actionListener = callback; } } },
    runtime: {
      onMessage: { addListener() {} },
      sendMessage(message) {
        notices.push(message);
        return Promise.reject(new Error("Receiving end does not exist."));
      }
    },
    storage: { session: storage },
    sidePanel: {
      setPanelBehavior() { return Promise.resolve(); },
      open() { return Promise.resolve(); }
    }
  };

  installActionSidePanel(chromeApi);
  actionListener({ id: 42, windowId: 7, url: "https://news.example/private-path" });
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(notices, [{
    target: "sidepanel",
    type: "READ_PAGE_AVAILABLE",
    windowId: 7,
    requestId: 1
  }]);

  let messageListener;
  installActionSidePanel({
    ...chromeApi,
    action: { onClicked: { addListener() {} } },
    runtime: {
      onMessage: { addListener(callback) { messageListener = callback; } },
      sendMessage() { return Promise.resolve(); }
    }
  });
  const firstResponse = await new Promise((resolve) => {
    const handled = messageListener({
      target: "action-side-panel",
      type: "TAKE_PENDING_PAGE_READ",
      windowId: 7
    }, {}, resolve);
    assert.equal(handled, true);
  });
  assert.deepEqual(firstResponse, {
    ok: true,
    request: { requestId: 1, tabId: 42, windowId: 7 }
  });
  assert.equal("url" in firstResponse.request, false);
  assert.equal("text" in firstResponse.request, false);

  const secondResponse = await new Promise((resolve) => messageListener({
    target: "action-side-panel",
    type: "TAKE_PENDING_PAGE_READ",
    windowId: 7
  }, {}, resolve));
  assert.deepEqual(secondResponse, { ok: true, request: null }, "the request is claimed atomically");
});

test("expires an unclaimed page-read request and isolates requests by window", async () => {
  let actionListener;
  let currentTime = 1_000;
  const storage = sessionStorage();
  const chromeApi = {
    action: { onClicked: { addListener(callback) { actionListener = callback; } } },
    runtime: {
      onMessage: { addListener() {} },
      sendMessage() { return Promise.resolve(); }
    },
    storage: { session: storage },
    sidePanel: {
      setPanelBehavior() { return Promise.resolve(); },
      open() { return Promise.resolve(); }
    }
  };
  const bridge = installActionSidePanel(chromeApi, {
    now: () => currentTime,
    pendingReadTtlMs: 100
  });

  actionListener({ id: 11, windowId: 1 });
  actionListener({ id: 22, windowId: 2 });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(await bridge.takePendingRead(2), { requestId: 2, tabId: 22, windowId: 2 });
  currentTime += 101;
  assert.equal(await bridge.takePendingRead(1), null);
});

test("service worker wires the explicit handler and never reenables interception", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "service-worker.js"), "utf8");
  assert.match(source, /installActionSidePanel\(chrome/);
  assert.doesNotMatch(source, /openPanelOnActionClick:\s*true/);
});
