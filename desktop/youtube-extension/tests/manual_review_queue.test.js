const assert = require("assert");
const reviewQueue = require("../youtube_review_queue");

function row(overrides = {}) {
  return {
    source_type: "creator_channel",
    creator_channel_url: "https://www.youtube.com/@demo",
    checked_about_url: "https://www.youtube.com/@demo/about",
    manual_review_url: "https://www.youtube.com/@demo/about",
    email: "",
    emails_json: "[]",
    hidden_email_button_present: false,
    captcha_required: false,
    profile_text: "",
    ...overrides
  };
}

const withEmail = reviewQueue.buildManualReviewRows([
  row({ email: "creator@example.com", captcha_required: true })
]);
assert.strictEqual(withEmail.length, 0, "rows with email should not enter manual review queue");

const captchaRows = reviewQueue.buildManualReviewRows([
  row({ captcha_required: true })
]);
assert.strictEqual(captchaRows.length, 1, "captcha rows should enter manual review queue");
assert.strictEqual(captchaRows[0].review_reason, "captcha_required");

const hiddenButtonRows = reviewQueue.buildManualReviewRows([
  row({ hidden_email_button_present: true })
]);
assert.strictEqual(hiddenButtonRows.length, 1, "hidden email button rows should enter manual review queue");
assert.strictEqual(hiddenButtonRows[0].review_reason, "hidden_email_button_present");

const shortsRows = reviewQueue.buildManualReviewRows([
  row({ content_type: "shorts", video_url: "https://www.youtube.com/shorts/abc123", captcha_required: true })
]);
assert.strictEqual(shortsRows.length, 1, "shorts rows should enter manual review queue when verification is required");
assert.strictEqual(shortsRows[0].content_type, "shorts");

const plainNoEmailRows = reviewQueue.buildManualReviewRows([
  row({ manual_review_url: "", needs_manual_review: false })
]);
assert.strictEqual(plainNoEmailRows.length, 0, "plain no-email rows should stay out of verification review queue");

const plainCommenterNoEmailRows = reviewQueue.buildManualReviewRows([
  row({
    source_type: "comment_author_channel",
    creator_channel_url: "https://www.youtube.com/@creator",
    comment_author_name: "Commenter",
    comment_author_channel_url: "https://www.youtube.com/@commenter",
    checked_profile_url: "https://www.youtube.com/@commenter/about",
    checked_about_url: "https://www.youtube.com/@commenter/about",
    manual_review_url: "",
    needs_manual_review: false
  })
]);
assert.strictEqual(plainCommenterNoEmailRows.length, 0, "plain no-email commenter rows should stay out of manual review");

const hiddenCommenterRows = reviewQueue.buildManualReviewRows([
  row({
    source_type: "comment_author_channel",
    comment_author_channel_url: "https://www.youtube.com/@commenter",
    checked_about_url: "https://www.youtube.com/@commenter/about",
    manual_review_url: "",
    hidden_email_button_present: true
  })
]);
assert.strictEqual(hiddenCommenterRows.length, 1, "commenters with hidden email buttons should enter manual review");
assert.strictEqual(hiddenCommenterRows[0].review_reason, "hidden_email_button_present");
assert.strictEqual(hiddenCommenterRows[0].manual_review_url, "https://www.youtube.com/@commenter/about");

const screenshotLikeRows = reviewQueue.buildManualReviewRows([
  row({
    creator_channel_url: "https://www.youtube.com/@AssessAdepts",
    checked_about_url: "https://www.youtube.com/@AssessAdepts/about",
    manual_review_url: "",
    profile_text: "AssessAdepts More info www.youtube.com/@AssessAdepts United States 7490 subscribers 301 videos",
    hidden_email_button_present: false,
    captcha_required: false,
    needs_manual_review: false
  })
]);
assert.strictEqual(screenshotLikeRows.length, 0, "channels with no public email and no verification signal should not enter manual review");

const loginRows = reviewQueue.buildManualReviewRows([
  row({ profile_text: "需登录才能查看电子邮件地址" })
]);
assert.strictEqual(loginRows.length, 1, "login-required email rows should enter manual review queue");
assert.strictEqual(loginRows[0].review_reason, "login_required");
assert.strictEqual(loginRows[0].needs_manual_review, true, "manual review rows should set needs_manual_review");
assert.strictEqual(loginRows[0].manual_review_url, "https://www.youtube.com/@demo/about", "manual review rows should keep an actionable review URL");

const dedupedRows = reviewQueue.buildManualReviewRows([
  row({ captcha_required: true }),
  row({ captcha_required: true })
]);
assert.strictEqual(dedupedRows.length, 1, "manual review queue should dedupe the same channel target");

console.log("manual review queue tests passed");
