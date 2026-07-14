const DEFAULT_PENDING_READ_TTL_MS = 30_000;
const PENDING_READ_KEY_PREFIX = "taigiPendingPageRead:";

function installActionSidePanel(chromeApi, {
  onError = () => {},
  now = () => Date.now(),
  pendingReadTtlMs = DEFAULT_PENDING_READ_TTL_MS
} = {}) {
  const openingTabs = new Set();
  let nextRequestId = 0;
  let pendingReadClaimQueue = Promise.resolve();

  function pendingReadKey(windowId) {
    return `${PENDING_READ_KEY_PREFIX}${windowId}`;
  }

  async function queuePageRead(tab) {
    if (!Number.isInteger(tab?.id) || !Number.isInteger(tab?.windowId)) return;
    const request = {
      requestId: ++nextRequestId,
      tabId: tab.id,
      windowId: tab.windowId,
      createdAt: now()
    };
    await chromeApi.storage.session.set({ [pendingReadKey(tab.windowId)]: request });
    try {
      await chromeApi.runtime.sendMessage({
        target: "sidepanel",
        type: "READ_PAGE_AVAILABLE",
        windowId: request.windowId,
        requestId: request.requestId
      });
    } catch {
      // The first action click can arrive before the side panel has loaded. Its
      // tab-only session request remains available after a service-worker restart.
    }
  }

  function takePendingRead(windowId) {
    const operation = pendingReadClaimQueue
      .catch(() => {})
      .then(async () => {
        if (!Number.isInteger(windowId)) return null;
        const key = pendingReadKey(windowId);
        const stored = await chromeApi.storage.session.get(key);
        await chromeApi.storage.session.remove(key);
        const request = stored[key];
        if (!request || !Number.isFinite(request.createdAt) ||
            now() - request.createdAt > pendingReadTtlMs) return null;
        if (!Number.isInteger(request.requestId) || !Number.isInteger(request.tabId) ||
            request.windowId !== windowId) return null;
        return {
          requestId: request.requestId,
          tabId: request.tabId,
          windowId: request.windowId
        };
      });
    pendingReadClaimQueue = operation.catch(() => {});
    return operation;
  }

  // Older builds enabled Chrome's automatic action interception. Disable it so
  // the action click reaches onClicked and Chrome grants activeTab to that tab.
  try {
    Promise.resolve(
      chromeApi.sidePanel.setPanelBehavior({ openPanelOnActionClick: false })
    ).catch(onError);
  } catch (error) {
    onError(error);
  }

  chromeApi.action.onClicked.addListener((tab) => {
    const tabId = tab?.id;
    if (!Number.isInteger(tabId)) return;

    if (!openingTabs.has(tabId)) {
      openingTabs.add(tabId);
      try {
        // Keep this call synchronous inside the user-gesture callback. Besides
        // satisfying sidePanel.open(), this aligns the activeTab grant with tabId.
        const opening = chromeApi.sidePanel.open({ tabId });
        Promise.resolve(opening)
          .catch(onError)
          .finally(() => openingTabs.delete(tabId));
      } catch (error) {
        openingTabs.delete(tabId);
        onError(error);
      }
    }

    // The action invocation grants activeTab for this exact tab. Queue only its
    // numeric identifiers so an already-open or newly-loaded panel can read it.
    queuePageRead(tab).catch(onError);
  });

  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.target !== "action-side-panel" || message?.type !== "TAKE_PENDING_PAGE_READ") {
      return undefined;
    }
    takePendingRead(message.windowId)
      .then((request) => sendResponse({ ok: true, request }))
      .catch((error) => {
        onError(error);
        sendResponse({ ok: false, request: null });
      });
    return true;
  });

  return { openingTabs, takePendingRead };
}

module.exports = { DEFAULT_PENDING_READ_TTL_MS, PENDING_READ_KEY_PREFIX, installActionSidePanel };
