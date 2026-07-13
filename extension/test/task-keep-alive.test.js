const test = require("node:test");
const assert = require("node:assert/strict");
const { createTaskKeepAlive } = require("../src/lib/task-keep-alive");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function nextTurn() {
  return new Promise((resolve) => setImmediate(resolve));
}

test("pings only while a task is active and clears its timer in finally", async () => {
  const task = deferred();
  const scheduled = [];
  const cancelled = [];
  let pingCalls = 0;
  const keepAlive = createTaskKeepAlive({
    ping: async () => { pingCalls += 1; },
    schedule(callback, delay) {
      scheduled.push({ callback, delay, id: 7 });
      return 7;
    },
    cancel: (id) => cancelled.push(id)
  });

  const running = keepAlive.run(() => task.promise);
  await nextTurn();
  assert.equal(pingCalls, 1, "an active task pings immediately");
  assert.equal(scheduled[0].delay, 20_000);

  scheduled[0].callback();
  await nextTurn();
  assert.equal(pingCalls, 2);
  assert.deepEqual(cancelled, []);

  task.resolve("done");
  assert.equal(await running, "done");
  assert.deepEqual(cancelled, [7]);

  scheduled[0].callback();
  await nextTurn();
  assert.equal(pingCalls, 2, "a completed task never pings again");
});

test("ping failures are handled without stopping the active task", async () => {
  const task = deferred();
  const errors = [];
  const keepAlive = createTaskKeepAlive({
    ping: async () => { throw new Error("platform unavailable"); },
    schedule: () => 9,
    cancel: () => {},
    onPingError: (error) => errors.push(error.message)
  });

  const running = keepAlive.run(() => task.promise);
  await nextTurn();
  assert.deepEqual(errors, ["platform unavailable"]);

  task.resolve("still completed");
  assert.equal(await running, "still completed");
});

test("task rejection propagates to its handler and still clears the timer", async () => {
  const cancelled = [];
  const keepAlive = createTaskKeepAlive({
    ping: async () => {},
    schedule: () => 11,
    cancel: (id) => cancelled.push(id)
  });

  await assert.rejects(keepAlive.run(async () => { throw new Error("queue failed"); }), /queue failed/);
  assert.deepEqual(cancelled, [11]);
});
