function createAudioController({ audio, createSource, releaseSource }) {
  let source = "";
  let pendingResponse = null;
  let paused = false;
  let playGeneration = 0;

  function release() {
    if (source) releaseSource(source);
    source = "";
  }

  function finish(result) {
    playGeneration += 1;
    paused = false;
    const respond = pendingResponse;
    pendingResponse = null;
    release();
    respond?.(result);
  }

  function playError(error, generation) {
    if (generation !== playGeneration || !pendingResponse) return;
    if (paused && error?.name === "AbortError") return;
    finish({ ok: false, error: error?.message || "無法播放音訊。" });
  }

  function attemptPlay() {
    const generation = ++playGeneration;
    try {
      Promise.resolve(audio.play()).catch((error) => playError(error, generation));
    } catch (error) {
      playError(error, generation);
    }
  }

  function stop() {
    playGeneration += 1;
    paused = false;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    finish({ ok: false, reason: "stopped" });
  }

  function play(payload, respond) {
    stop();
    pendingResponse = respond;
    try {
      source = createSource(payload);
      audio.src = source;
      attemptPlay();
    } catch (error) {
      finish({ ok: false, error: error?.message || "無法載入音訊。" });
    }
  }

  function pause() {
    if (!pendingResponse) return;
    // Set intent first: pause() can reject an unresolved play() promise in the
    // same task, and that AbortError is a successful pause rather than failure.
    paused = true;
    audio.pause();
  }

  function resume() {
    if (!pendingResponse || !paused) return;
    paused = false;
    attemptPlay();
  }

  function ended() {
    if (pendingResponse) finish({ ok: true });
  }

  function audioError() {
    if (pendingResponse) finish({ ok: false, error: "音訊格式無法播放。" });
  }

  return { play, pause, resume, stop, ended, audioError };
}

module.exports = { createAudioController };
