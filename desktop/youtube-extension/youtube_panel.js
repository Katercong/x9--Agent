const MSG = {
  START_SEARCH: "X9_YOUTUBE_PANEL_START_SEARCH",
  CONTINUE_SEARCH: "X9_YOUTUBE_PANEL_CONTINUE_SEARCH",
  OPEN_NEXT_MANUAL_REVIEW: "X9_YOUTUBE_PANEL_OPEN_NEXT_MANUAL_REVIEW",
  COLLECT_CURRENT_PAGE_EMAIL: "X9_YOUTUBE_PANEL_COLLECT_CURRENT_PAGE_EMAIL",
  BIND_ACTOR: "X9_YOUTUBE_PANEL_BIND_ACTOR",
  OPEN_LOGIN: "X9_YOUTUBE_PANEL_OPEN_LOGIN",
  STOP: "X9_YOUTUBE_PANEL_STOP",
  GET_STATE: "X9_YOUTUBE_PANEL_GET_STATE",
  CLEAR: "X9_YOUTUBE_PANEL_CLEAR"
};

const EXPORT_COLUMNS = [
  "source_type",
  "keyword",
  "video_id",
  "content_type",
  "video_title",
  "video_url",
  "creator_channel_url",
  "comment_author_name",
  "comment_author_channel_url",
  "email",
  "emails_json",
  "email_source",
  "evidence_url",
  "manual_review_url",
  "hidden_email_button_present",
  "captcha_required",
  "review_reason",
  "checked_profile_url",
  "checked_channel_home_url",
  "checked_about_url",
  "checked_video_url",
  "profile_text",
  "video_detail_text",
  "needs_manual_review",
  "collected_at"
];

let currentState = null;
let pollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  bind();
  refresh();
  pollTimer = setInterval(refresh, 1000);
});

window.addEventListener("x9-youtube-lang-change", () => {
  window.X9YoutubeI18n?.apply?.();
  if (currentState) paint(currentState);
});

function bind() {
  document.getElementById("startBtn")?.addEventListener("click", onStart);
  document.getElementById("continueBtn")?.addEventListener("click", onContinue);
  document.getElementById("nextManualReviewBtn")?.addEventListener("click", onOpenNextManualReview);
  document.getElementById("collectCurrentPageEmailBtn")?.addEventListener("click", onCollectCurrentPageEmail);
  document.getElementById("actorBindBtn")?.addEventListener("click", onBindActor);
  document.getElementById("actorLoginBtn")?.addEventListener("click", onOpenLogin);
  document.getElementById("stopBtn")?.addEventListener("click", onStop);
  document.getElementById("clearBtn")?.addEventListener("click", onClear);
  document.getElementById("exportCsvBtn")?.addEventListener("click", () => exportRows("csv"));
  document.getElementById("exportJsonBtn")?.addEventListener("click", () => exportRows("json"));
  document.getElementById("exportManualReviewCsvBtn")?.addEventListener("click", () => exportRows("csv", { manualReviewOnly: true }));
  document.getElementById("exportManualReviewJsonBtn")?.addEventListener("click", () => exportRows("json", { manualReviewOnly: true }));
}

async function onBindActor() {
  paint({ ...(currentState || {}), actor_identity: { state: "checking", code: "binding", blocked: true } });
  const response = await send(MSG.BIND_ACTOR);
  if (!response?.ok) {
    paint(response?.state || { ...(currentState || {}), actor_identity: { state: "error", code: "bind_failed", blocked: true, detail: response?.error || "" } });
    return;
  }
  paint(response.state);
}

async function onOpenLogin() {
  const response = await send(MSG.OPEN_LOGIN);
  if (response?.state) paint(response.state);
}

async function onStart() {
  const settings = readSettings();
  paint({ ...(currentState || {}), status: "running", message: "Starting from current search page..." });
  const response = await send(MSG.START_SEARCH, { settings });
  if (!response?.ok) {
    paint(response?.state || { status: "error", message: response?.error || "Start failed." });
    return;
  }
  paint(response.state);
}

async function onContinue() {
  const settings = readSettings();
  paint({ ...(currentState || {}), status: "running", message: "Continuing from previous results..." });
  const response = await send(MSG.CONTINUE_SEARCH, { settings });
  if (!response?.ok) {
    paint(response?.state || { status: "error", message: response?.error || "Continue failed." });
    return;
  }
  paint(response.state);
}

async function onCollectCurrentPageEmail() {
  paint({ ...(currentState || {}), status: "running", message: "Collecting visible email from current About dialog..." });
  const response = await send(MSG.COLLECT_CURRENT_PAGE_EMAIL);
  if (!response?.ok) {
    paint(response?.state || { ...(currentState || {}), status: "error", message: response?.error || "Current page email collection failed." });
    return;
  }
  paint(response.state);
}

async function onOpenNextManualReview() {
  paint({ ...(currentState || {}), status: "running", message: "Opening next manual review About page..." });
  const response = await send(MSG.OPEN_NEXT_MANUAL_REVIEW);
  if (!response?.ok) {
    paint(response?.state || { ...(currentState || {}), status: "error", message: response?.error || "Open next manual review failed." });
    return;
  }
  paint(response.state);
}

async function onStop() {
  const response = await send(MSG.STOP);
  if (response?.state) paint(response.state);
}

async function onClear() {
  const response = await send(MSG.CLEAR);
  if (response?.state) paint(response.state);
}

async function refresh() {
  const response = await send(MSG.GET_STATE);
  if (response?.state) paint(response.state);
}

function readSettings() {
  return {
    maxVideos: readNumber("maxVideosInput", 1, 100, 5),
    searchScrollRounds: readNumber("searchScrollRoundsInput", 0, 30, 10),
    maxCommentsPerVideo: readNumber("maxCommentsPerVideoInput", 1, 200, 50),
    maxCommenterProfilesPerVideo: readNumber("maxCommenterProfilesPerVideoInput", 0, 200, 50)
  };
}

function send(type, payload) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(Object.assign({ type }, payload || {}), (response) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(response);
      }
    });
  });
}

function paint(state) {
  currentState = state || {};
  const status = currentState.status || "idle";
  const settings = currentState.settings || {};
  window.X9YoutubeI18n?.apply?.();
  paintActorIdentity(currentState.actor_identity || {});
  applyActionButtonState(status, currentState.actor_identity || {});
  setText("statusText", messageText(currentState.message || "Ready."));
  const pill = document.getElementById("statusPill");
  if (pill) {
    pill.dataset.state = status;
    pill.textContent = statusLabel(status);
  }

  const counts = currentState.counts || currentState.result?.counts || {};
  const rows = getRows();
  const manualReviewRows = getManualReviewRows();
  setText("videoCount", String(counts.videos || currentState.videos?.length || currentState.result?.videos?.length || 0));
  setText("commentCount", String(counts.comments || 0));
  setText("profileCount", String(counts.profile_pages || 0));
  setText("rowCount", String(counts.rows || rows.length));
  setText("manualReviewCount", String(counts.manual_review ?? manualReviewRows.length));
  setText("emailCount", String(counts.emails || rows.filter((row) => row.email).length));
  setText("videoMeta", [settings.keyword || t("meta.currentSearch"), `${rows.length} ${t("meta.rows")}`].filter(Boolean).join(" / "));
  paintUpload(currentState.incremental_upload || currentState.ingest_upload);
  paintRows(rows);
}

function paintActorIdentity(identity) {
  const notice = document.getElementById("actorNotice");
  if (!notice) return;
  const state = identity.state || "checking";
  notice.dataset.state = state;
  setText("actorName", actorDisplayName(identity.actor));
  setText("actorStatusPill", actorPill(identity));
  setText("actorMeta", actorMeta(identity));
  setText("actorMessage", actorMessage(identity));
}

function applyActionButtonState(status, identity) {
  const blocked = identity.blocked !== false;
  const busy = status === "running" || status === "stopping";
  setDisabled("startBtn", blocked || busy);
  setDisabled("continueBtn", blocked || busy);
  setDisabled("nextManualReviewBtn", blocked || busy);
  setDisabled("collectCurrentPageEmailBtn", blocked || busy);
  setDisabled("stopBtn", status !== "running" && status !== "stopping");
  setDisabled("actorBindBtn", busy || identity.code === "binding");
}

function actorDisplayName(actor) {
  if (!actor) return t("actor.notBound");
  return actor.display_name || actor.username || actor.email || actor.id || t("actor.boundUser");
}

function actorMeta(identity) {
  const actor = identity.actor;
  if (!actor) return "";
  const parts = [];
  if (actor.department_code) parts.push(`${t("actor.department")}:${actor.department_code}`);
  if (actor.id) parts.push(`ID:${actor.id}`);
  if (identity.downloaded_at) parts.push(`${t("actor.boundAt")}:${formatActorTime(identity.downloaded_at)}`);
  return parts.join(" | ");
}

function actorPill(identity) {
  const code = identity.code || "";
  if (code === "verified") return t("actor.verified");
  if (code === "binding" || code === "checking") return t("actor.checking");
  if (code === "not_bound") return t("actor.blocked");
  if (identity.state === "warn") return t("actor.notVerified");
  if (identity.state === "error") return t("actor.blocked");
  return t("actor.checking");
}

function actorMessage(identity) {
  const code = identity.code || "";
  if (code === "verified") {
    return t("actor.heartbeatOk").replace("{time}", identity.heartbeat_at || t("actor.justNow"));
  }
  if (code === "binding") return t("actor.binding");
  if (code === "not_bound") return t("actor.notBoundMessage");
  if (code === "login_required") return t("actor.loginRequired");
  if (code === "backend_unavailable") return `${t("actor.backendUnavailable")}${identity.detail ? ` ${identity.detail}` : ""}`;
  if (code === "heartbeat_failed") return `${t("actor.heartbeatFailed")}${identity.detail ? ` ${identity.detail}` : ""}`;
  if (code === "bind_failed") return `${t("actor.bindFailed")}${identity.detail ? ` ${identity.detail}` : ""}`;
  return t("actor.waitingHeartbeat");
}

function formatActorTime(value) {
  try {
    return new Date(value).toLocaleString(window.X9YoutubeI18n?.getLang?.() === "en" ? "en-US" : "zh-CN");
  } catch {
    return String(value || "");
  }
}

function paintUpload(upload) {
  const el = document.getElementById("uploadStatusText");
  if (!el) return;
  if (!upload) {
    el.textContent = t("upload.none");
    return;
  }
  if ("attempted" in upload || "skipped_duplicates" in upload) {
    const attempted = upload.attempted ?? 0;
    const succeeded = upload.succeeded ?? 0;
    const failed = upload.failed ?? 0;
    const skipped = upload.skipped_duplicates ?? 0;
    if (!attempted && !succeeded && !failed && !skipped && upload.status === "idle") {
      el.textContent = t("upload.none");
      return;
    }
    const prefix = upload.status === "uploading" ? t("upload.uploading") : t("upload.incremental");
    const suffix = upload.last_error ? `, error=${upload.last_error}` : "";
    el.textContent = `${prefix} attempted=${attempted}, succeeded=${succeeded}, failed=${failed}, skipped=${skipped}${suffix}`;
    return;
  }
  if (upload.status === "uploading") {
    el.textContent = t("upload.uploading");
    return;
  }
  if (upload.ok) {
    const result = upload.result || {};
    const kept = result.kept ?? 0;
    const inserted = result.inserted ?? 0;
    const updated = result.updated ?? 0;
    el.textContent = `${t("upload.uploaded")} kept=${kept}, inserted=${inserted}, updated=${updated}`;
    return;
  }
  el.textContent = `${t("upload.error")}: ${upload.error || "unknown error"}`;
}

function paintRows(rows) {
  const body = document.getElementById("rowsBody");
  if (!body) return;
  const visible = Array.isArray(rows) ? rows.slice(0, 120) : [];
  if (!visible.length) {
    body.innerHTML = `<tr><td colspan="4" class="empty">${escapeHtml(t("table.empty"))}</td></tr>`;
    return;
  }
  body.replaceChildren(...visible.map(rowElement));
}

function rowElement(row) {
  const tr = document.createElement("tr");
  tr.appendChild(cell(sourceLabel(row.source_type || "")));
  tr.appendChild(cell(row.video_title || row.video_id || ""));
  tr.appendChild(cell(row.creator_channel_url || row.comment_author_channel_url || ""));
  tr.appendChild(cell(contactPreview(row)));
  return tr;
}

function contactPreview(row) {
  if (row.email) return row.email;
  if (isManualReviewRow(row)) {
    return row.review_reason || row.manual_review_url || t("table.manualReview");
  }
  return t("table.noPublicEmail");
}

function isManualReviewRow(row) {
  if (row?.review_reason) return true;
  const reasons = window.X9YoutubeReviewQueue?.reviewReasons?.(row) || [];
  return Array.isArray(reasons) && reasons.length > 0;
}

function cell(value) {
  const td = document.createElement("td");
  td.textContent = String(value || "");
  return td;
}

function exportRows(format, options = {}) {
  const rows = options.manualReviewOnly ? getManualReviewRows() : getRows();
  if (!rows.length) {
    paint({ ...(currentState || {}), message: options.manualReviewOnly ? "No manual review rows to export." : "No rows to export." });
    return;
  }
  const keyword = (currentState?.settings?.keyword || "youtube_search").replace(/[^\w.-]+/g, "_");
  const prefix = options.manualReviewOnly ? "x9-youtube-manual-review" : "x9-youtube";
  if (format === "json") {
    downloadFile(`${prefix}-${keyword}.json`, "application/json", JSON.stringify(rows, null, 2));
    return;
  }
  downloadFile(`${prefix}-${keyword}.csv`, "text/csv", toCsv(rows));
}

function getRows() {
  return currentState?.rows || currentState?.result?.rows || [];
}

function getManualReviewRows() {
  const stored = currentState?.manual_review_rows || currentState?.result?.manual_review_rows;
  if (Array.isArray(stored)) return stored;
  return window.X9YoutubeReviewQueue?.buildManualReviewRows?.(getRows()) || [];
}

function toCsv(rows) {
  const lines = [EXPORT_COLUMNS.join(",")];
  for (const row of rows) {
    lines.push(EXPORT_COLUMNS.map((column) => csvCell(row[column])).join(","));
  }
  return lines.join("\r\n");
}

function csvCell(value) {
  const raw = String(value ?? "");
  return `"${raw.replace(/"/g, '""')}"`;
}

function downloadFile(filename, mimeType, content) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({ url, filename, saveAs: true }, () => {
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  });
}

function readNumber(id, min, max, fallback) {
  const raw = Number(document.getElementById(id)?.value);
  if (!Number.isFinite(raw)) return fallback;
  return Math.max(min, Math.min(max, Math.round(raw)));
}

function statusLabel(status) {
  const key = `status.${status}`;
  const label = t(key);
  return label === key ? status : label;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setDisabled(id, disabled) {
  const el = document.getElementById(id);
  if (el) el.disabled = Boolean(disabled);
}

function t(key) {
  return window.X9YoutubeI18n?.t?.(key) || key;
}

function messageText(value) {
  return window.X9YoutubeI18n?.message?.(value) || value;
}

function sourceLabel(value) {
  const key = `source.${value}`;
  const label = window.X9YoutubeI18n?.t?.(key) || key;
  return label === key ? value : label;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

window.addEventListener("unload", () => {
  if (pollTimer) clearInterval(pollTimer);
});
