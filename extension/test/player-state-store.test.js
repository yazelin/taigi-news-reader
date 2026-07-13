const test = require("node:test");
const assert = require("node:assert/strict");
const { initialState, reducePlayerState } = require("../src/lib/player-state");
const { createPlayerStateStore, persistablePlayerState } = require("../src/lib/player-state-store");

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function nextTurn() {
  return new Promise((resolve) => setImmediate(resolve));
}

test("serializes state persistence so STOP cannot be overwritten by a stale run", async () => {
  const firstSave = deferred();
  const saves = [];
  const broadcasts = [];
  let token = 1;
  const store = createPlayerStateStore({
    initial: initialState(),
    reduce: reducePlayerState,
    currentToken: () => token,
    async save(state) {
      saves.push(state.status);
      if (saves.length === 1) await firstSave.promise;
    },
    async broadcast(state) { broadcasts.push(state.status); }
  });

  const preparing = store.transition(
    { type: "START", total: 1, title: "新聞", rate: 1 },
    { token: 1 }
  );
  await nextTurn();
  token = 2;
  const stopped = store.transition({ type: "STOP" });
  const staleError = store.transition({ type: "ERROR", error: "old failure" }, { token: 1 });
  const staleComplete = store.transition({ type: "COMPLETE" }, { token: 1 });

  assert.deepEqual(saves, ["preparing"], "the STOP write waits behind the older write");
  firstSave.resolve();
  assert.equal(await preparing, true);
  assert.equal(await stopped, true);
  assert.equal(await staleError, false);
  assert.equal(await staleComplete, false);
  assert.deepEqual(saves, ["preparing", "stopped"]);
  assert.deepEqual(broadcasts, ["preparing", "stopped"]);
  assert.equal(store.getState().status, "stopped");
});

test("session-safe playback state omits the article title", () => {
  assert.deepEqual(persistablePlayerState({
    status: "playing",
    index: 0,
    total: 1,
    title: "不應保存的新聞標題",
    error: "",
    rate: 0.8
  }), {
    status: "playing",
    index: 0,
    total: 1,
    error: "",
    rate: 0.8
  });
});
