const form = document.querySelector("#job-form");
const startButton = document.querySelector("#start-button");
const stopButton = document.querySelector("#stop-button");
const downloadButton = document.querySelector("#download-button");
const downloadVerificationButton = document.querySelector("#download-verification-button");
const statusPill = document.querySelector("#status-pill");
const logsEl = document.querySelector("#logs");
const rowCountEl = document.querySelector("#row-count");
const verificationCountEl = document.querySelector("#verification-count");
const startedAtEl = document.querySelector("#started-at");
const outputPathEl = document.querySelector("#output-path");
const resultBody = document.querySelector("#result-body");
const verificationBody = document.querySelector("#verification-body");
const clearLogButton = document.querySelector("#clear-log-button");
const themeToggle = document.querySelector("#theme-toggle");
const langToggle = document.querySelector("#lang-toggle");

let pollTimer = null;

// 语言包
const translations = {
  zh: {
    title: "YouTube 邮箱抓取工作台",
    subtitle: "关键词搜索、description 邮箱、频道 About 信息、CSV 导出",
    config: "抓取配置",
    keywords: "关键词",
    videosPerKeyword: "每个关键词视频数",
    sort: "排序",
    relevance: "相关度",
    latest: "最新发布",
    afterDate: "发布日期之后",
    interval: "关键词间隔秒数",
    outputFile: "输出文件名",
    ytdlpPath: "yt-dlp.exe 路径",
    optional: "可留空",
    scanAbout: "扫描频道 About",
    keepDuplicates: "保留重复邮箱",
    start: "开始抓取",
    stop: "停止",
    downloadCsv: "下载 CSV",
    downloadQueue: "下载验证队列",
    statusIdle: "待命",
    statusRunning: "运行中",
    statusCompleted: "完成",
    statusFailed: "失败",
    statusStopped: "已停止",
    rowsExported: "导出行数",
    pendingVerification: "待人工验证",
    startTime: "开始时间",
    outputFile: "输出文件",
    logs: "运行日志",
    clear: "清空显示",
    preview: "结果预览",
    maxRows: "最多显示 300 行",
    verificationQueue: "人工验证队列",
    hiddenEmailChannels: "检测到隐藏邮箱按钮的频道",
    action: "操作",
    channel: "频道",
    bio: "简介",
    sourceVideo: "来源视频",
    reason: "原因",
    waitingResults: "等待抓取结果",
    noResults: "暂无结果",
    waitingDetection: "等待检测隐藏邮箱按钮",
    noPending: "暂无待人工验证频道",
    submitting: "任务提交中...",
    startFailed: "任务启动失败。",
    connectionFailed: "无法连接本地服务。",
    openAbout: "Open About",
    video: "视频"
  },
  en: {
    title: "YouTube Email Scraper Dashboard",
    subtitle: "Keyword search, description emails, channel About info, CSV export",
    config: "Scraping Configuration",
    keywords: "Keywords",
    videosPerKeyword: "Videos per keyword",
    sort: "Sort by",
    relevance: "Relevance",
    latest: "Latest",
    afterDate: "Published after",
    interval: "Keyword interval (seconds)",
    outputFile: "Output filename",
    ytdlpPath: "yt-dlp.exe path",
    optional: "Optional",
    scanAbout: "Scan channel About",
    keepDuplicates: "Keep duplicate emails",
    start: "Start Scraping",
    stop: "Stop",
    downloadCsv: "Download CSV",
    downloadQueue: "Download Queue",
    statusIdle: "Idle",
    statusRunning: "Running",
    statusCompleted: "Completed",
    statusFailed: "Failed",
    statusStopped: "Stopped",
    rowsExported: "Rows exported",
    pendingVerification: "Pending verification",
    startTime: "Start time",
    outputFile: "Output file",
    logs: "Run Logs",
    clear: "Clear",
    preview: "Results Preview",
    maxRows: "Max 300 rows shown",
    verificationQueue: "Manual Verification Queue",
    hiddenEmailChannels: "Channels with hidden email buttons detected",
    action: "Action",
    channel: "Channel",
    bio: "Bio",
    sourceVideo: "Source Video",
    reason: "Reason",
    waitingResults: "Waiting for scraping results",
    noResults: "No results yet",
    waitingDetection: "Waiting for hidden email button detection",
    noPending: "No pending manual verification",
    submitting: "Submitting task...",
    startFailed: "Failed to start task.",
    connectionFailed: "Unable to connect to local service.",
    openAbout: "Open About",
    video: "Video"
  }
};

function getCurrentLang() {
  return document.documentElement.getAttribute('data-lang') || 'zh';
}

function setLanguage(lang) {
  document.documentElement.setAttribute('data-lang', lang);
  localStorage.setItem('preferred-language', lang);
  updateUIText();
}

function updateUIText() {
  const lang = getCurrentLang();
  const t = translations[lang];

  document.title = t.title;
  document.querySelector('h1').textContent = t.title;
  document.querySelector('.subtle').textContent = t.subtitle;
  document.querySelector('.panel-header h2').textContent = t.config;
  document.querySelector('label[for="queries"]').textContent = t.keywords;
  document.querySelector('label[for="max-results"]').textContent = t.videosPerKeyword;
  document.querySelector('label[for="order"]').textContent = t.sort;
  document.querySelector('option[value="relevance"]').textContent = t.relevance;
  document.querySelector('option[value="date"]').textContent = t.latest;
  document.querySelector('label[for="published-after"]').textContent = t.afterDate;
  document.querySelector('label[for="sleep"]').textContent = t.interval;
  document.querySelector('label[for="output-filename"]').textContent = t.outputFile;
  document.querySelector('label[for="yt-dlp-path"]').textContent = t.ytdlpPath;
  document.querySelector('#yt-dlp-path').placeholder = t.optional;
  document.querySelectorAll('.switch span')[0].textContent = t.scanAbout;
  document.querySelectorAll('.switch span')[1].textContent = t.keepDuplicates;
  startButton.textContent = t.start;
  stopButton.textContent = t.stop;
  downloadButton.textContent = t.downloadCsv;
  downloadVerificationButton.textContent = t.downloadQueue;
  document.querySelectorAll('.metric-label')[0].textContent = t.rowsExported;
  document.querySelectorAll('.metric-label')[1].textContent = t.pendingVerification;
  document.querySelectorAll('.metric-label')[2].textContent = t.startTime;
  document.querySelectorAll('.metric-label')[3].textContent = t.outputFile;
  document.querySelector('.log-panel .panel-head h2').textContent = t.logs;
  clearLogButton.textContent = t.clear;
  document.querySelector('.table-panel .panel-head h2').textContent = t.preview;
  document.querySelector('#preview-note').textContent = t.maxRows;
  document.querySelector('.queue-panel .panel-head h2').textContent = t.verificationQueue;
  document.querySelector('.queue-panel .panel-head span').textContent = t.hiddenEmailChannels;
  document.querySelectorAll('th')[0].textContent = 'Email';
  document.querySelectorAll('th')[1].textContent = t.action;
  document.querySelectorAll('th')[2].textContent = t.channel;
  document.querySelectorAll('th')[3].textContent = t.bio;
  document.querySelectorAll('th')[4].textContent = t.video;
  document.querySelectorAll('.queue-panel th')[0].textContent = t.action;
  document.querySelectorAll('.queue-panel th')[1].textContent = t.channel;
  document.querySelectorAll('.queue-panel th')[2].textContent = t.bio;
  document.querySelectorAll('.queue-panel th')[3].textContent = t.sourceVideo;
  document.querySelectorAll('.queue-panel th')[4].textContent = t.reason;

  langToggle.textContent = lang === 'zh' ? 'EN' : '中文';
}

function collectPayload() {
  return {
    queries: document.querySelector("#queries").value,
    max_results: document.querySelector("#max-results").value,
    order: document.querySelector("#order").value,
    published_after: document.querySelector("#published-after").value,
    sleep: document.querySelector("#sleep").value,
    output_filename: document.querySelector("#output-filename").value,
    yt_dlp_path: document.querySelector("#yt-dlp-path").value,
    scan_about: document.querySelector("#scan-about").checked,
    keep_duplicates: document.querySelector("#keep-duplicates").checked,
  };
}

function setStatus(status, running) {
  const lang = getCurrentLang();
  const t = translations[lang];
  const labels = {
    idle: t.statusIdle,
    running: t.statusRunning,
    completed: t.statusCompleted,
    failed: t.statusFailed,
    stopped: t.statusStopped,
  };
  statusPill.textContent = labels[status] || status || t.statusIdle;
  statusPill.className = `status-pill ${status || ""}`;
  startButton.disabled = Boolean(running);
  stopButton.disabled = !running;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderLink(url, label) {
  if (!url) {
    return "";
  }
  const safeUrl = escapeHtml(url);
  const safeLabel = escapeHtml(label || url);
  return `<a href="${safeUrl}" target="_blank" rel="noreferrer">${safeLabel}</a>`;
}

function renderRows(rows) {
  const lang = getCurrentLang();
  const t = translations[lang];

  if (!rows || rows.length === 0) {
    resultBody.innerHTML = `<tr><td colspan="5" class="empty">${t.noResults}</td></tr>`;
    return;
  }

  resultBody.innerHTML = rows
    .map((row) => {
      const sourceLabel = row.source === "channel_about" ? "About" : "Description";
      const channel = row.profile_handle || row.channel_title || row.channel_id || "";
      const videoLabel = row.video_title || row.video_id || t.video;
      return `
        <tr>
          <td class="email">${escapeHtml(row.email)}</td>
          <td>${renderLink(row.source_url, sourceLabel)}</td>
          <td>${renderLink(row.channel_url, channel)}</td>
          <td class="bio">${escapeHtml(row.profile_bio)}</td>
          <td>${renderLink(row.video_url, videoLabel)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderVerificationRows(rows) {
  const lang = getCurrentLang();
  const t = translations[lang];

  if (!rows || rows.length === 0) {
    verificationBody.innerHTML = `<tr><td colspan="5" class="empty">${t.noPending}</td></tr>`;
    return;
  }

  verificationBody.innerHTML = rows
    .map((row) => {
      const channel = row.profile_handle || row.channel_title || row.channel_id || "";
      const videoLabel = row.source_video_title || row.source_video_id || t.video;
      return `
        <tr>
          <td>${renderLink(row.about_url, t.openAbout)}</td>
          <td>${renderLink(row.channel_url, channel)}</td>
          <td class="bio">${escapeHtml(row.profile_bio)}</td>
          <td>${renderLink(row.source_video_url, videoLabel)}</td>
          <td>${escapeHtml(row.reason)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderState(state) {
  setStatus(state.status, state.running);
  logsEl.textContent = (state.logs || []).join("\n");
  logsEl.scrollTop = logsEl.scrollHeight;
  rowCountEl.textContent = state.row_count || 0;
  verificationCountEl.textContent = state.verification_count || 0;
  startedAtEl.textContent = state.started_at || "-";
  outputPathEl.textContent = state.output_path || "-";
  downloadButton.classList.toggle("disabled", !state.has_output);
  downloadVerificationButton.classList.toggle("disabled", !state.has_verification_output);
  renderRows(state.rows || []);
  renderVerificationRows(state.verification_rows || []);
}

async function fetchStatus() {
  const response = await fetch("/api/status");
  const state = await response.json();
  renderState(state);
  if (!state.running && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
  }
  pollTimer = setInterval(fetchStatus, 1200);
}

// 主题切换
function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('preferred-theme', newTheme);
  updateThemeIcon();
}

function updateThemeIcon() {
  const theme = document.documentElement.getAttribute('data-theme');
  const icon = themeToggle.querySelector('svg');
  if (theme === 'dark') {
    icon.innerHTML = `
      <circle cx="12" cy="12" r="5"></circle>
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"></path>
    `;
  } else {
    icon.innerHTML = `
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
    `;
  }
}

// 初始化主题和语言
function initPreferences() {
  const savedTheme = localStorage.getItem('preferred-theme') || 'light';
  const savedLang = localStorage.getItem('preferred-language') || 'zh';
  document.documentElement.setAttribute('data-theme', savedTheme);
  document.documentElement.setAttribute('data-lang', savedLang);
  updateThemeIcon();
  updateUIText();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const lang = getCurrentLang();
  const t = translations[lang];
  setStatus("running", true);
  logsEl.textContent = t.submitting;
  resultBody.innerHTML = `<tr><td colspan="5" class="empty">${t.waitingResults}</td></tr>`;
  verificationBody.innerHTML = `<tr><td colspan="5" class="empty">${t.waitingDetection}</td></tr>`;

  const response = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectPayload()),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    logsEl.textContent = payload.error || t.startFailed;
    setStatus("failed", false);
    return;
  }
  renderState(payload.state);
  startPolling();
});

stopButton.addEventListener("click", async () => {
  await fetch("/api/stop", { method: "POST" });
  await fetchStatus();
});

clearLogButton.addEventListener("click", () => {
  logsEl.textContent = "";
});

themeToggle.addEventListener("click", toggleTheme);
langToggle.addEventListener("click", () => {
  const currentLang = getCurrentLang();
  setLanguage(currentLang === 'zh' ? 'en' : 'zh');
});

// 初始化
initPreferences();
fetchStatus().catch(() => {
  const lang = getCurrentLang();
  const t = translations[lang];
  logsEl.textContent = t.connectionFailed;
});
