const ACTIVE_JOB_KEY = "activeSynthesisJob";

function createActiveJobStore(storage, key = ACTIVE_JOB_KEY) {
  let operations = Promise.resolve();

  function enqueue(operation) {
    const result = operations.then(operation, operation);
    operations = result.catch(() => {});
    return result;
  }

  function get() {
    return enqueue(async () => (await storage.get(key))[key] || null);
  }

  function record({ jobId, backendUrl, token }) {
    return enqueue(() => storage.set({
      [key]: { jobId, backendUrl, runId: token }
    }));
  }

  function recordLatest({ jobId, backendUrl, token }) {
    return enqueue(async () => {
      const current = (await storage.get(key))[key];
      if (Number.isFinite(current?.runId) && current.runId > token) return false;
      await storage.set({ [key]: { jobId, backendUrl, runId: token } });
      return true;
    });
  }

  function clearIfOwner({ jobId, token }) {
    return enqueue(async () => {
      const current = (await storage.get(key))[key];
      if (current?.jobId !== jobId || current?.runId !== token) return false;
      await storage.remove(key);
      return true;
    });
  }

  function remove() {
    return enqueue(() => storage.remove(key));
  }

  return { clearIfOwner, get, record, recordLatest, remove };
}

module.exports = { ACTIVE_JOB_KEY, createActiveJobStore };
