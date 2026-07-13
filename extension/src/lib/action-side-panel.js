function installActionSidePanel(chromeApi, { onError = () => {} } = {}) {
  const openingTabs = new Set();

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
    if (!Number.isInteger(tabId) || openingTabs.has(tabId)) return;

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
  });

  return { openingTabs };
}

module.exports = { installActionSidePanel };
