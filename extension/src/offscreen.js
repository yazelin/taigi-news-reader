const audio = new Audio();
let objectUrl = "";
let pendingResponse = null;

function releaseUrl() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = "";
}

function finish(result) {
  const respond = pendingResponse;
  pendingResponse = null;
  releaseUrl();
  respond?.(result);
}

function stop() {
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  finish({ ok: false, reason: "stopped" });
}

function decode(base64, mimeType) {
  const binary = atob(base64.replace(/\s/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], { type: mimeType });
}

audio.addEventListener("ended", () => finish({ ok: true }));
audio.addEventListener("error", () => finish({ ok: false, error: "音訊格式無法播放。" }));

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.target !== "offscreen") return undefined;
  if (message.type === "PLAY_AUDIO") {
    stop();
    pendingResponse = sendResponse;
    try {
      objectUrl = URL.createObjectURL(decode(message.base64, message.mimeType));
      audio.src = objectUrl;
      audio.play().catch((error) => finish({ ok: false, error: error.message }));
    } catch (error) {
      finish({ ok: false, error: error.message });
    }
    return true;
  }
  if (message.type === "PAUSE") audio.pause();
  if (message.type === "RESUME") audio.play().catch(() => {});
  if (message.type === "STOP") stop();
  sendResponse({ ok: true });
  return undefined;
});
