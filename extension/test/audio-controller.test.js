const test = require("node:test");
const assert = require("node:assert/strict");
const { createAudioController } = require("../src/lib/audio-controller");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function setup() {
  const attempts = [];
  const released = [];
  const audio = {
    src: "",
    pauseCalls: 0,
    loadCalls: 0,
    play() {
      const attempt = deferred();
      attempts.push(attempt);
      return attempt.promise;
    },
    pause() { this.pauseCalls += 1; },
    removeAttribute(name) { if (name === "src") this.src = ""; },
    load() { this.loadCalls += 1; }
  };
  const controller = createAudioController({
    audio,
    createSource: () => "blob:test-audio",
    releaseSource: (source) => released.push(source)
  });
  return { attempts, audio, controller, released };
}

test("pause keeps a pending play alive when play rejects with AbortError", async () => {
  const { attempts, controller } = setup();
  const responses = [];
  controller.play({}, (result) => responses.push(result));

  controller.pause();
  const interrupted = new Error("The play() request was interrupted by pause()");
  interrupted.name = "AbortError";
  attempts[0].reject(interrupted);
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(responses, [], "PLAY_AUDIO remains pending while paused");
});

test("resume starts a new attempt and stop resolves PLAY_AUDIO as stopped", async () => {
  const { attempts, audio, controller, released } = setup();
  const responses = [];
  controller.play({}, (result) => responses.push(result));
  controller.pause();

  const interrupted = new Error("interrupted");
  interrupted.name = "AbortError";
  attempts[0].reject(interrupted);
  await new Promise((resolve) => setImmediate(resolve));

  controller.resume();
  assert.equal(attempts.length, 2);
  attempts[1].resolve();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(responses, [], "resuming does not finish the queued chunk");

  controller.stop();
  assert.deepEqual(responses, [{ ok: false, reason: "stopped" }]);
  assert.equal(audio.src, "");
  assert.deepEqual(released, ["blob:test-audio"]);
});

test("natural audio completion resolves PLAY_AUDIO successfully", () => {
  const { controller } = setup();
  const responses = [];
  controller.play({}, (result) => responses.push(result));
  controller.ended();
  assert.deepEqual(responses, [{ ok: true }]);
});
