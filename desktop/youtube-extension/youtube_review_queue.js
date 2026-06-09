(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.X9YoutubeReviewQueue = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const LOGIN_REQUIRED_PATTERNS = [
    /sign\s*in[\s\S]{0,80}view[\s\S]{0,40}email/i,
    /log\s*in[\s\S]{0,80}view[\s\S]{0,40}email/i,
    /\u9700\s*\u767b\u5f55[\s\S]{0,40}\u67e5\u770b[\s\S]{0,20}(\u7535\u5b50\u90ae\u4ef6\u5730\u5740|\u90ae\u7bb1)/,
    /\u9700\u8981\s*\u767b\u5f55[\s\S]{0,40}\u67e5\u770b[\s\S]{0,20}(\u7535\u5b50\u90ae\u4ef6\u5730\u5740|\u90ae\u7bb1)/,
    /\u767b\u5f55[\s\S]{0,40}\u67e5\u770b[\s\S]{0,20}(\u7535\u5b50\u90ae\u4ef6\u5730\u5740|\u90ae\u7bb1)/,
    /需登录[\s\S]{0,40}查看[\s\S]{0,20}(电子邮件地址|邮箱)/,
    /需要登录[\s\S]{0,40}查看[\s\S]{0,20}(电子邮件地址|邮箱)/,
    /登录[\s\S]{0,40}查看[\s\S]{0,20}(电子邮件地址|邮箱)/
  ];

  function buildManualReviewRows(rows) {
    const out = [];
    const seen = new Set();
    for (const row of rows || []) {
      const reasons = reviewReasons(row);
      if (!reasons.length) continue;
      const key = reviewKey(row);
      if (key && seen.has(key)) continue;
      if (key) seen.add(key);
      out.push({
        ...row,
        review_reason: reasons.join(","),
        needs_manual_review: true,
        manual_review_url: row.manual_review_url || bestReviewUrl(row)
      });
    }
    return out;
  }

  function reviewReasons(row) {
    if (!row || hasEmail(row)) return [];
    const reasons = [];
    if (truthy(row.captcha_required)) reasons.push("captcha_required");
    if (truthy(row.hidden_email_button_present)) reasons.push("hidden_email_button_present");
    if (requiresLoginForEmail(row)) reasons.push("login_required");
    return unique(reasons);
  }

  function requiresLoginForEmail(row) {
    const value = [
      row.profile_text,
      row.video_detail_text,
      row.manual_review_url,
      row.checked_profile_url,
      row.checked_about_url
    ].map((item) => String(item || "")).join("\n");
    return LOGIN_REQUIRED_PATTERNS.some((pattern) => pattern.test(value));
  }

  function hasEmail(row) {
    if (String(row?.email || "").trim()) return true;
    try {
      const parsed = JSON.parse(row?.emails_json || "[]");
      return Array.isArray(parsed) && parsed.some((email) => String(email || "").trim());
    } catch {
      return false;
    }
  }

  function truthy(value) {
    return value === true || value === 1 || String(value || "").toLowerCase() === "true";
  }

  function reviewKey(row) {
    return [
      row.source_type,
      row.creator_channel_url || row.comment_author_channel_url || "",
      row.checked_about_url || row.checked_profile_url || row.manual_review_url || "",
      row.video_url || ""
    ].join("|");
  }

  function bestReviewUrl(row) {
    return row.checked_about_url
      || row.checked_profile_url
      || row.manual_review_url
      || row.creator_channel_url
      || row.comment_author_channel_url
      || row.video_url
      || "";
  }

  function unique(values) {
    const seen = new Set();
    const out = [];
    for (const value of values) {
      if (!value || seen.has(value)) continue;
      seen.add(value);
      out.push(value);
    }
    return out;
  }

  return {
    buildManualReviewRows,
    reviewReasons,
    requiresLoginForEmail,
    bestReviewUrl
  };
});
