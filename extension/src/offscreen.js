const { createAudioController } = require("./lib/audio-controller");

const audio = new Audio();

function decode(base64, mimeType) {
  const binary = atob(base64.replace(/\s/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new Blob([bytes], { type: mimeType });
}

const controller = createAudioController({
  audio,
  createSource({ base64, mimeType }) {
    return URL.createObjectURL(decode(base64, mimeType));
  },
  releaseSource(source) {
    URL.revokeObjectURL(source);
  }
});

audio.addEventListener("ended", controller.ended);
audio.addEventListener("error", controller.audioError);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.target !== "offscreen") return undefined;
  if (message.type === "PLAY_AUDIO") {
    controller.play(message, sendResponse);
    return true;
  }
  if (message.type === "PAUSE") controller.pause();
  if (message.type === "RESUME") controller.resume();
  if (message.type === "STOP") controller.stop();
  sendResponse({ ok: true });
  return undefined;
});
