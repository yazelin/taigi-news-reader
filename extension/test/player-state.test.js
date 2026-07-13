const test = require("node:test");
const assert = require("node:assert/strict");
const { initialState, reducePlayerState, validateState } = require("../src/lib/player-state");

test("follows the normal playback lifecycle", () => {
  let state = reducePlayerState(initialState(), { type: "START", total: 3, title: "新聞", rate: 1 });
  state = reducePlayerState(state, { type: "PREPARING", index: 0 });
  state = reducePlayerState(state, { type: "PLAYING", index: 0 });
  state = reducePlayerState(state, { type: "PAUSE" });
  assert.equal(state.status, "paused");
  state = reducePlayerState(state, { type: "RESUME" });
  state = reducePlayerState(state, { type: "COMPLETE" });
  assert.equal(state.status, "completed");
  assert.equal(state.index, 3);
  assert.ok(validateState(state));
});

test("clear restores an empty session", () => {
  const playing = { status: "playing", index: 1, total: 2, title: "新聞", error: "", rate: 1.25, replayId: "" };
  assert.deepEqual(reducePlayerState(playing, { type: "CLEAR" }), initialState());
});

test("pause is ignored unless audio is playing", () => {
  const state = initialState();
  assert.equal(reducePlayerState(state, { type: "PAUSE" }), state);
});

test("completed playback exposes only its opaque replay id and can forget it", () => {
  const started = reducePlayerState(initialState(), { type: "START", total: 1, title: "新聞", rate: 1 });
  const completed = reducePlayerState(started, { type: "COMPLETE", replayId: "opaque-cache-id" });
  assert.equal(completed.replayId, "opaque-cache-id");
  assert.equal(reducePlayerState(completed, { type: "FORGET_REPLAY" }).replayId, "");
});
