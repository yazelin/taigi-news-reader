const PAGE_ACCESS_ERROR = /Cannot access|Missing host permission|extensions gallery cannot be scripted/i;

async function extractPage(chromeApi, tabId) {
  if (!Number.isInteger(tabId)) throw new Error("找不到目前的網頁分頁。");
  await chromeApi.scripting.executeScript({ target: { tabId }, files: ["extractor.js"] });
  const results = await chromeApi.scripting.executeScript({
    target: { tabId },
    func: () => globalThis.TaigiNewsExtractor.extract()
  });
  return results[0]?.result || null;
}

function pageReadErrorMessage(error, { grantedByAction = false } = {}) {
  const message = error?.message || "無法讀取這一頁。";
  if (!PAGE_ACCESS_ERROR.test(message)) return message;
  if (!grantedByAction) {
    return "這一頁需要重新授權。請再按一次瀏覽器工具列的「台語新聞朗讀」圖示；側欄不用關閉。";
  }
  return "這個頁面不允許擴充套件讀取，或頁面在授權後已切換。若是一般新聞頁，請等載入完成後再按一次工具列圖示。";
}

function shouldInvalidatePageContext(activeTabId, tabId, changeInfo = {}) {
  return Number.isInteger(activeTabId) && tabId === activeTabId &&
    (changeInfo.status === "loading" || typeof changeInfo.url === "string");
}

module.exports = { extractPage, pageReadErrorMessage, shouldInvalidatePageContext };
