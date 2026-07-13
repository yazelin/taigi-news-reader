const statuses = new Set(["idle", "preparing", "playing", "paused", "stopped", "completed", "error"]);

function initialState() {
  return { status: "idle", index: 0, total: 0, title: "", error: "", rate: 1 };
}

function reducePlayerState(state, event) {
  const next = { ...state };
  switch (event.type) {
    case "START":
      return { ...initialState(), status: "preparing", total: event.total, title: event.title || "", rate: event.rate };
    case "PREPARING":
      return { ...next, status: "preparing", index: event.index, error: "" };
    case "PLAYING":
      return { ...next, status: "playing", index: event.index, error: "" };
    case "PAUSE":
      if (state.status !== "playing") return state;
      return { ...next, status: "paused" };
    case "RESUME":
      if (state.status !== "paused") return state;
      return { ...next, status: "playing" };
    case "STOP":
      return { ...next, status: "stopped" };
    case "COMPLETE":
      return { ...next, status: "completed", index: state.total };
    case "ERROR":
      return { ...next, status: "error", error: event.error || "發生未知錯誤" };
    case "CLEAR":
      return initialState();
    default:
      return state;
  }
}

function validateState(state) {
  return statuses.has(state.status) && state.index >= 0 && state.index <= state.total;
}

module.exports = { initialState, reducePlayerState, validateState };
