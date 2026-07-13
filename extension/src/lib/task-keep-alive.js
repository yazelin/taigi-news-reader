function createTaskKeepAlive({
  ping,
  intervalMs = 20_000,
  schedule = setInterval,
  cancel = clearInterval,
  onPingError = () => {}
}) {
  if (typeof ping !== "function") throw new TypeError("ping must be a function");

  return {
    run(task) {
      if (typeof task !== "function") return Promise.reject(new TypeError("task must be a function"));

      let active = true;
      let pingPending = false;
      const pingNow = () => {
        if (!active || pingPending) return;
        pingPending = true;
        Promise.resolve()
          .then(ping)
          .catch((error) => {
            try {
              onPingError(error);
            } catch {
              // A diagnostic callback must never create an unhandled rejection.
            }
          })
          .finally(() => { pingPending = false; });
      };

      // The original message event keeps the worker alive initially. This
      // immediate ping plus the interval cover long translation/TTS requests.
      pingNow();
      const timer = schedule(pingNow, intervalMs);

      return Promise.resolve()
        .then(task)
        .finally(() => {
          active = false;
          cancel(timer);
        });
    }
  };
}

module.exports = { createTaskKeepAlive };
