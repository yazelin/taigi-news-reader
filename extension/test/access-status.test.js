const test = require("node:test");
const assert = require("node:assert/strict");
const {
  formatAccessQuota,
  parseAccessQuota,
  quotaLimitMessage,
  utcResetLabel
} = require("../src/lib/access-status");

function response(status, values = {}) {
  const headers = new Headers(values);
  return { status, headers };
}

test("access quota keeps only per-user remaining counts and the UTC reset", () => {
  const quota = parseAccessQuota({
    authentication_required: true,
    subject: "private-tester-name",
    remaining: {
      subject_jobs: 12,
      subject_characters: 3456,
      global_jobs: 999,
      global_characters: 999999
    },
    used: { subject_jobs: 8, global_jobs: 100 },
    resets_at: "2026-07-14T00:00:00Z"
  });

  assert.deepEqual(quota, {
    remainingJobs: 12,
    remainingCharacters: 3456,
    resetsAt: Date.parse("2026-07-14T00:00:00Z")
  });
  assert.equal(
    formatAccessQuota(quota),
    "今日個人剩餘：12 段朗讀、3,456 字；2026/07/14 00:00 UTC 重置。"
  );
  assert.doesNotMatch(JSON.stringify(quota), /subject|global|used|private-tester-name/i);
});

test("invalid or unmetered access responses do not invent quota information", () => {
  assert.equal(parseAccessQuota({ authentication_required: false }), null);
  assert.equal(parseAccessQuota({ authentication_required: true, remaining: {}, resets_at: "invalid" }), null);
  assert.equal(parseAccessQuota({
    authentication_required: true,
    remaining: { subject_jobs: 1, subject_characters: 2 },
    resets_at: "invalid"
  }), null);
  assert.equal(utcResetLabel(null), "");
});

test("daily 429 messages distinguish personal and service quotas and show the UTC reset", () => {
  const reset = String(Date.parse("2026-07-14T00:00:00Z") / 1_000);
  assert.equal(
    quotaLimitMessage(response(429, {
      "X-RateLimit-Scope": "subject_characters",
      "X-RateLimit-Reset": reset,
      "Retry-After": "3600"
    })),
    "你的今日私人測試額度已用完。可於 2026/07/14 00:00 UTC 後再試。"
  );
  assert.equal(
    quotaLimitMessage(response(429, {
      "X-RateLimit-Scope": "global_jobs",
      "X-RateLimit-Reset": reset
    })),
    "今日私人測試服務的總額度已用完。可於 2026/07/14 00:00 UTC 後再試。"
  );
});

test("temporary capacity and generic 429 responses stay clear without exposing response bodies", () => {
  assert.equal(
    quotaLimitMessage(response(429, { "X-RateLimit-Scope": "active_jobs", "Retry-After": "5" })),
    "目前同時朗讀的工作較多，請約 5 秒後再試。"
  );
  assert.equal(
    quotaLimitMessage(response(429)),
    "語音服務目前已達用量限制。請稍後再試。"
  );
  assert.equal(quotaLimitMessage(response(503, { "Retry-After": "5" })), "");
});
