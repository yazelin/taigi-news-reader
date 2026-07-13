function createPlayerStateStore({ initial, reduce, save, broadcast = async () => {}, currentToken = () => undefined }) {
  let state = initial;
  let operations = Promise.resolve();

  function enqueue(operation) {
    const result = operations.then(operation, operation);
    operations = result.catch(() => {});
    return result;
  }

  function transition(event, options = {}) {
    const hasToken = Object.prototype.hasOwnProperty.call(options, "token");
    return enqueue(async () => {
      if (hasToken && options.token !== currentToken()) return false;
      const next = reduce(state, event);
      state = next;
      await save(next);
      await broadcast(next);
      return true;
    });
  }

  function hydrate(next) {
    state = next;
  }

  function getState() {
    return state;
  }

  return { getState, hydrate, transition };
}

function persistablePlayerState(state) {
  return {
    status: state.status,
    index: state.index,
    total: state.total,
    error: state.error,
    rate: state.rate,
    replayId: state.replayId || ""
  };
}

module.exports = { createPlayerStateStore, persistablePlayerState };
