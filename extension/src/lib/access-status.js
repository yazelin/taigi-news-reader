function nonNegativeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function utcMilliseconds(value) {
  if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? milliseconds : null;
}

function parseAccessQuota(body) {
  if (body?.authentication_required !== true) return null;
  const remainingJobs = nonNegativeInteger(body?.remaining?.subject_jobs);
  const remainingCharacters = nonNegativeInteger(body?.remaining?.subject_characters);
  const resetsAt = utcMilliseconds(body.resets_at);
  if (remainingJobs === null || remainingCharacters === null || resetsAt === null) return null;
  return {
    remainingJobs,
    remainingCharacters,
    resetsAt
  };
}

function utcResetLabel(milliseconds) {
  if (!Number.isFinite(milliseconds)) return "";
  const date = new Date(milliseconds);
  if (!Number.isFinite(date.getTime())) return "";
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getUTCFullYear()}/${pad(date.getUTCMonth() + 1)}/${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

function formatAccessQuota(quota) {
  if (!quota) return "";
  const jobs = quota.remainingJobs.toLocaleString("zh-TW");
  const characters = quota.remainingCharacters.toLocaleString("zh-TW");
  const reset = utcResetLabel(quota.resetsAt);
  return `今日個人剩餘：${jobs} 段朗讀、${characters} 字${reset ? `；${reset} 重置` : ""}。`;
}

function header(response, name) {
  const value = response?.headers?.get?.(name);
  return typeof value === "string" ? value.trim() : "";
}

function positiveSeconds(value) {
  const seconds = /^\d+$/.test(value) ? Number(value) : NaN;
  return Number.isSafeInteger(seconds) && seconds > 0 ? seconds : null;
}

function rateLimitReset(response, nowMilliseconds) {
  const epochSeconds = positiveSeconds(header(response, "X-RateLimit-Reset"));
  if (epochSeconds !== null) return epochSeconds * 1_000;

  const retryAfter = header(response, "Retry-After");
  const retrySeconds = positiveSeconds(retryAfter);
  if (retrySeconds !== null) return nowMilliseconds + retrySeconds * 1_000;
  const retryDate = Date.parse(retryAfter);
  return Number.isFinite(retryDate) ? retryDate : null;
}

function quotaLimitMessage(response, { nowMilliseconds = Date.now() } = {}) {
  if (response?.status !== 429) return "";
  const scope = header(response, "X-RateLimit-Scope");
  const retrySeconds = positiveSeconds(header(response, "Retry-After"));

  if (scope === "active_jobs") {
    return retrySeconds === null
      ? "目前同時朗讀的工作較多，請稍後再試。"
      : `目前同時朗讀的工作較多，請約 ${retrySeconds.toLocaleString("zh-TW")} 秒後再試。`;
  }

  const reset = utcResetLabel(rateLimitReset(response, nowMilliseconds));
  let prefix = "語音服務目前已達用量限制。";
  if (scope.startsWith("subject_")) prefix = "你的今日私人測試額度已用完。";
  else if (scope.startsWith("global_")) prefix = "今日私人測試服務的總額度已用完。";
  else if (reset) prefix = "今日私人測試額度已用完。";

  if (reset) return `${prefix}可於 ${reset} 後再試。`;
  if (retrySeconds !== null) return `${prefix}請約 ${retrySeconds.toLocaleString("zh-TW")} 秒後再試。`;
  return `${prefix}請稍後再試。`;
}

module.exports = {
  formatAccessQuota,
  parseAccessQuota,
  quotaLimitMessage,
  utcResetLabel
};
