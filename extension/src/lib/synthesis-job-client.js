const { quotaLimitMessage } = require("./access-status");

function abortError() {
  const error = new Error("Synthesis job was cancelled.");
  error.name = "AbortError";
  return error;
}

function abortableDelay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(done, milliseconds);
    function done() {
      signal.removeEventListener("abort", aborted);
      resolve();
    }
    function aborted() {
      clearTimeout(timer);
      signal.removeEventListener("abort", aborted);
      reject(abortError());
    }
    if (signal.aborted) aborted();
    else signal.addEventListener("abort", aborted, { once: true });
  });
}

function errorText(body, status) {
  const detail = body?.error ?? body?.detail ?? body?.message;
  if (typeof detail === "string" && detail) return detail;
  if (detail !== undefined) {
    try {
      return JSON.stringify(detail);
    } catch {
      // Fall through to the status-based message.
    }
  }
  return `語音服務回傳錯誤（HTTP ${status}）。`;
}

async function responseBody(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function audioPayload(data) {
  const audio = data?.audio_base64 || data?.audio || data?.data?.audio_base64 || data?.data?.audio;
  if (typeof audio !== "string" || !audio) throw new Error("語音服務沒有回傳可播放的音訊。");
  const dataUrl = audio.match(/^data:([^;,]+);base64,(.+)$/s);
  return {
    base64: dataUrl ? dataUrl[2] : audio,
    mimeType: dataUrl ? dataUrl[1] : (data.mime_type || data.content_type || "audio/mpeg")
  };
}

function settleWithin(promise, milliseconds, schedule = setTimeout, cancel = clearTimeout) {
  return new Promise((resolve) => {
    let settled = false;
    let timer;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      cancel(timer);
      resolve(value);
    };
    timer = schedule(() => finish(false), milliseconds);
    promise.then(() => finish(true), () => finish(true));
  });
}

function createSynthesisJobClient({
  fetchImpl,
  endpointFor,
  delay = abortableDelay,
  now = Date.now,
  pollIntervalMs = 1_000,
  deadlineMs = 10 * 60_000,
  createSettleTimeoutMs = 8_000,
  requestTimeoutMs = 15_000,
  schedule = setTimeout,
  cancelScheduled = clearTimeout,
  requestSchedule = setTimeout,
  cancelRequestScheduled = clearTimeout,
  createController = () => new AbortController()
}) {
  let activeRun = null;

  async function withRequestTimeout(signal, task) {
    const controller = createController();
    let timer;
    let rejectBoundary;
    let boundarySettled = false;
    const boundary = new Promise((_resolve, reject) => { rejectBoundary = reject; });
    const fail = (error) => {
      if (boundarySettled) return;
      boundarySettled = true;
      rejectBoundary(error);
      controller.abort();
    };
    const abort = () => fail(abortError());
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
    timer = requestSchedule(() => {
      const timeout = new Error("語音服務請求逾時，請稍後再試。");
      timeout.name = "TimeoutError";
      fail(timeout);
    }, requestTimeoutMs);
    try {
      return await Promise.race([task(controller.signal), boundary]);
    } finally {
      boundarySettled = true;
      cancelRequestScheduled(timer);
      signal?.removeEventListener("abort", abort);
    }
  }

  function requestWithBody(url, options, signal) {
    return withRequestTimeout(signal, async (requestSignal) => {
      const response = await fetchImpl(url, { ...options, signal: requestSignal });
      const body = await responseBody(response);
      return { response, body };
    });
  }

  async function deleteJob(backendUrl, jobId) {
    const { response, body } = await requestWithBody(endpointFor(backendUrl, `/v1/synthesis-jobs/${encodeURIComponent(jobId)}`), {
      method: "DELETE"
    });
    if (response.status === 204 || response.status === 404) return;
    throw new Error(errorText(body, response.status));
  }

  async function clearRun(run) {
    if (!run.jobId) return;
    if (!run.cleanupPromise) {
      run.cleanupPromise = (async () => {
        await deleteJob(run.backendUrl, run.jobId);
        await run.onCleared?.({ jobId: run.jobId, backendUrl: run.backendUrl, token: run.token });
      })();
    }
    await run.cleanupPromise;
  }

  async function clearRunBestEffort(run) {
    try {
      await clearRun(run);
    } catch {
      // The job remains in session storage so startup or the next run can retry.
    }
  }

  async function cancel() {
    const run = activeRun;
    if (!run) return;
    if (!run.cancelPromise) {
      run.cancelRequested = true;
      run.workController.abort();
      run.cancelPromise = (async () => {
        if (!run.jobId) {
          const settled = await settleWithin(
            run.createPromise,
            createSettleTimeoutMs,
            schedule,
            cancelScheduled
          );
          if (!settled && !run.jobId) run.createController.abort();
        }
        if (run.jobId) await clearRun(run);
      })().finally(() => {
        if (activeRun === run) activeRun = null;
      });
    }
    await run.cancelPromise;
  }

  async function requestJson(url, options, signal) {
    const { response, body } = await requestWithBody(url, options, signal);
    if (!response.ok) {
      const error = new Error(quotaLimitMessage(response) || errorText(body, response.status));
      error.status = response.status;
      throw error;
    }
    return { body, status: response.status };
  }

  async function createJob(run, text, rate) {
    const created = await requestJson(
      endpointFor(run.backendUrl, "/v1/synthesis-jobs"),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source_language: "zh-TW", target_language: "nan-TW", rate })
      },
      run.createController.signal
    );
    if (created.status !== 202 || created.body?.status !== "pending" || !created.body?.job_id) {
      throw new Error("語音服務建立工作時回傳了無效結果。");
    }
    run.jobId = String(created.body.job_id);
    await run.onCreated?.({ jobId: run.jobId, backendUrl: run.backendUrl, token: run.token });
  }

  async function synthesize({ backendUrl, text, rate, token, onCreated, onCleared }) {
    if (activeRun) throw new Error("已有語音工作正在執行。");
    const run = {
      backendUrl,
      token,
      createController: createController(),
      workController: createController(),
      createPromise: null,
      jobId: "",
      cleanupPromise: null,
      cancelPromise: null,
      cancelRequested: false,
      onCreated,
      onCleared
    };
    activeRun = run;
    run.createPromise = createJob(run, text, rate);

    try {
      await run.createPromise;
      if (run.cancelRequested) {
        await clearRunBestEffort(run);
        throw abortError();
      }
      const deadline = now() + deadlineMs;

      while (true) {
        if (now() >= deadline) throw new Error("語音合成等候逾時，請稍後再試。");
        const polled = await requestJson(
          endpointFor(backendUrl, `/v1/synthesis-jobs/${encodeURIComponent(run.jobId)}`),
          { method: "GET" },
          run.workController.signal
        );
        const status = polled.body?.status;
        if (status === "completed") {
          const audio = audioPayload(polled.body.result);
          await clearRunBestEffort(run);
          return audio;
        }
        if (status === "failed") throw new Error(errorText(polled.body, polled.status));
        if (status !== "pending") throw new Error("語音服務回傳了未知的工作狀態。");
        await delay(pollIntervalMs, run.workController.signal);
      }
    } catch (error) {
      if (run.cancelRequested) {
        await clearRunBestEffort(run);
        throw abortError();
      }
      await clearRunBestEffort(run);
      throw error;
    } finally {
      if (activeRun === run) activeRun = null;
    }
  }

  return { synthesize, cancel, deleteJob };
}

module.exports = { abortableDelay, audioPayload, createSynthesisJobClient, errorText, settleWithin };
