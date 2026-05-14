const STORAGE_KEY = 'tclabState';
const EXPORT_FIELDS = [
  'platform',
  'search_keyword',
  'matched_keywords',
  'username',
  'nickname',
  'profile_url',
  'bio',
  'followers_raw',
  'followers_count',
  'following_raw',
  'likes_raw',
  'email',
  'emails_json',
  'external_links',
  'source_video_url',
  'source_video_title',
  'source_video_description',
  'contact_source',
  'lead_status',
  'collected_at',
  'last_seen_at',
  'notes'
];

const IS_SIDE_PANEL = true;
const FAST_SPEED_PROFILE_VERSION = 3;
const FAST_AUTO_SETTINGS = {
  maxScrolls: 10,
  maxProfiles: 20,
  minDelaySeconds: 1,
  maxDelaySeconds: 3,
  restEveryProfiles: 30,
  restMinSeconds: 5,
  restMaxSeconds: 10
};
const FAST_PAGE_SETTLE_MS = 350;
const FAST_SEARCH_SETTLE_MS = 800;
const FAST_TAB_SETTLE_MS = 700;
const X9_BACKEND_BASE_URL = 'http://127.0.0.1:8000';
const X9_OBSERVATION_URL = `${X9_BACKEND_BASE_URL}/api/local/collector/observations`;
const X9_HEARTBEAT_URL = `${X9_BACKEND_BASE_URL}/api/local/extension/heartbeat`;
const X9_EXTENSION_ID = 'tiktok_creator_lead_browser_1_0_19';
const X9_WORKER_ID = 'tiktok_creator_lead_browser_1_0_19';
const X9_ACCOUNT_ID = 'local_tiktok_account';
const X9_HEARTBEAT_INTERVAL_MS = 5_000;
const DEFAULT_LANGUAGE = 'zh';
const I18N = {
  zh: {
    'app.title': 'TikTok 线索',
    'app.subtitle': '公开可见联系方式采集',
    'badge.manual': '手动',
    'badge.sidePanel': '侧边栏',
    'language.label': '语言',
    'keyword.label': '当前搜索关键词',
    'keyword.placeholder': '从已打开搜索页读取',
    'stats.leads': '线索',
    'stats.queue': '队列',
    'stats.skipped': '跳过',
    'timer.label': '本次运行',
    'timer.notStarted': '未开始',
    'timer.running': '运行中',
    'timer.ended': '已结束',
    'actions.openPanel': '打开侧边栏',
    'actions.panelReady': '侧边栏就绪',
    'actions.search': '搜索并点视频',
    'actions.scan': '扫描当前页',
    'actions.openNext': '打开下个主页',
    'actions.start': '开始自动运行',
    'actions.openSidePanelStart': '打开侧边栏后开始',
    'actions.stop': '停止自动',
    'actions.exportCsv': '导出 CSV',
    'actions.exportExcel': '导出 Excel',
    'actions.exportJson': '导出 JSON',
    'actions.exportBackup': '导出备份',
    'actions.clear': '清空本地数据',
    'auto.title': '自动设置',
    'auto.subtitle': '快速人工节奏',
    'auto.scrolls': '滚动次数',
    'auto.target': '任务目标',
    'auto.minDelay': '最短延迟',
    'auto.maxDelay': '最长延迟',
    'auto.restEvery': '每 N 个休息',
    'auto.restMin': '最短休息',
    'auto.restMax': '最长休息',
    'filters.title': '线索筛选',
    'filters.subtitle': '只保存符合条件的账号',
    'filters.email': '必须有可见联系方式（邮箱/WhatsApp/IG/Telegram/LINE/链接/电话/私信）',
    'filters.minFollowers': '最低粉丝数',
    'status.default': '打开已登录的 TikTok 搜索结果页，然后从这里开始。',
    'queue.title': '下一个队列',
    'queue.copy': '复制链接',
    'queue.empty': '暂无待处理主页。',
    'queue.emptyMeta': '扫描搜索页后会加入队列。',
    'leads.title': '最近线索',
    'leads.empty': '暂无邮箱线索。',
    'leads.emptyMeta': '只保存有可见联系方式且粉丝达标的主页。',
    'notice.compliance': '不点赞、不评论、不关注、不私信、不发帖、不绕过验证码、不使用代理、不采集隐藏数据。',
    'message.openLoggedIn': '打开已登录的 TikTok 搜索结果页，然后从侧边栏开始。',
    'message.popupNeedsPanel': '自动运行请先打开侧边栏。',
    'message.noKeyword': '请先打开一个带搜索关键词的 TikTok 搜索结果页。',
    'message.keywordFromPage': '已从当前搜索页读取关键词：{keyword}',
    'message.filterUpdated': '筛选条件已更新：最低粉丝数 {count}。',
    'message.stopRequested': '已请求停止，当前步骤结束后会停止。',
    'message.noPending': '暂无待处理主页。请先扫描 TikTok 搜索结果页。',
    'message.noCopy': '暂无可复制的主页链接。',
    'message.copied': '已复制下一个链接：@{username}',
    'message.exportCsv': '已导出 CSV，共 {count} 条邮箱线索。',
    'message.exportExcel': '已导出 Excel，共 {count} 条邮箱线索。',
    'message.exportJson': '已导出 JSON，共 {count} 条邮箱线索。',
    'message.exportBackup': '已导出完整本地备份。',
    'message.cleared': '本地数据已清空。',
    'message.busy': '正在执行...',
    'confirm.clear': '确定清空所有线索、队列、跳过记录和日志吗？'
  },
  en: {
    'app.title': 'TikTok Leads',
    'app.subtitle': 'Public creator contact collection',
    'badge.manual': 'Manual',
    'badge.sidePanel': 'Side Panel',
    'language.label': 'Language',
    'keyword.label': 'Current Search Keyword',
    'keyword.placeholder': 'Read from open search page',
    'stats.leads': 'Leads',
    'stats.queue': 'Queue',
    'stats.skipped': 'Skipped',
    'timer.label': 'Run Time',
    'timer.notStarted': 'Not started',
    'timer.running': 'Running',
    'timer.ended': 'Ended',
    'actions.openPanel': 'Open Side Panel',
    'actions.panelReady': 'Panel Ready',
    'actions.search': 'Search and Open Video Tab',
    'actions.scan': 'Scan Current Page',
    'actions.openNext': 'Open Next Profile',
    'actions.start': 'Start Auto Run',
    'actions.openSidePanelStart': 'Open Side Panel First',
    'actions.stop': 'Stop Auto',
    'actions.exportCsv': 'Export CSV',
    'actions.exportExcel': 'Export Excel',
    'actions.exportJson': 'Export JSON',
    'actions.exportBackup': 'Export Backup',
    'actions.clear': 'Clear Local Data',
    'auto.title': 'Auto Settings',
    'auto.subtitle': 'Fast supervised pace',
    'auto.scrolls': 'Scrolls',
    'auto.target': 'Task Target',
    'auto.minDelay': 'Min Delay',
    'auto.maxDelay': 'Max Delay',
    'auto.restEvery': 'Rest Every N',
    'auto.restMin': 'Min Rest',
    'auto.restMax': 'Max Rest',
    'filters.title': 'Lead Filters',
    'filters.subtitle': 'Only save qualified accounts',
    'filters.email': 'Require any contact method (email/WhatsApp/IG/Telegram/LINE/link/phone/DM)',
    'filters.minFollowers': 'Min Followers',
    'status.default': 'Open a logged-in TikTok search results page, then start here.',
    'queue.title': 'Next Queue',
    'queue.copy': 'Copy Link',
    'queue.empty': 'No pending profiles.',
    'queue.emptyMeta': 'Scan a search page to add profiles.',
    'leads.title': 'Recent Leads',
    'leads.empty': 'No email leads yet.',
    'leads.emptyMeta': 'Only profiles with at least one contact method and enough followers are saved.',
    'notice.compliance': 'No likes, comments, follows, messages, posts, CAPTCHA bypass, proxies, or hidden data access.',
    'message.openLoggedIn': 'Open a logged-in TikTok search results page, then start from the side panel.',
    'message.popupNeedsPanel': 'Open the side panel before auto run.',
    'message.noKeyword': 'Open a TikTok search results page with a search keyword first.',
    'message.keywordFromPage': 'Read keyword from current search page: {keyword}',
    'message.filterUpdated': 'Filter updated: minimum followers {count}.',
    'message.stopRequested': 'Stop requested. The run will stop after the current step.',
    'message.noPending': 'No pending profiles. Scan a TikTok search results page first.',
    'message.noCopy': 'No profile link to copy.',
    'message.copied': 'Copied next link: @{username}',
    'message.exportCsv': 'CSV exported with {count} email leads.',
    'message.exportExcel': 'Excel exported with {count} email leads.',
    'message.exportJson': 'JSON exported with {count} email leads.',
    'message.exportBackup': 'Full local backup exported.',
    'message.cleared': 'Local data cleared.',
    'message.busy': 'Running...',
    'confirm.clear': 'Clear all leads, queue items, skipped records, and logs?'
  }
};
let autoRunActive = false;
let autoStopRequested = false;
let runTimerIntervalId = null;

const elements = {
  languageSelect: document.getElementById('languageSelect'),
  keywordInput: document.getElementById('keywordInput'),
  leadCount: document.getElementById('leadCount'),
  pendingCount: document.getElementById('pendingCount'),
  skippedCount: document.getElementById('skippedCount'),
  runTimer: document.getElementById('runTimer'),
  runTimerMeta: document.getElementById('runTimerMeta'),
  openPanelBtn: document.getElementById('openPanelBtn'),
  openSearchBtn: document.getElementById('openSearchBtn'),
  scanPageBtn: document.getElementById('scanPageBtn'),
  openNextBtn: document.getElementById('openNextBtn'),
  startAutoBtn: document.getElementById('startAutoBtn'),
  stopAutoBtn: document.getElementById('stopAutoBtn'),
  exportCsvBtn: document.getElementById('exportCsvBtn'),
  exportExcelBtn: document.getElementById('exportExcelBtn'),
  exportJsonBtn: document.getElementById('exportJsonBtn'),
  exportBackupBtn: document.getElementById('exportBackupBtn'),
  autoScrollsInput: document.getElementById('autoScrollsInput'),
  autoProfilesInput: document.getElementById('autoProfilesInput'),
  autoMinDelayInput: document.getElementById('autoMinDelayInput'),
  autoMaxDelayInput: document.getElementById('autoMaxDelayInput'),
  restEveryInput: document.getElementById('restEveryInput'),
  restMinInput: document.getElementById('restMinInput'),
  restMaxInput: document.getElementById('restMaxInput'),
  requireEmailInput: document.getElementById('requireEmailInput'),
  minFollowersInput: document.getElementById('minFollowersInput'),
  copyNextBtn: document.getElementById('copyNextBtn'),
  clearBtn: document.getElementById('clearBtn'),
  queueList: document.getElementById('queueList'),
  leadList: document.getElementById('leadList'),
  status: document.getElementById('status')
};

document.addEventListener('DOMContentLoaded', async () => {
  const state = await getState();
  if (state.settings.speedProfileVersion !== FAST_SPEED_PROFILE_VERSION) {
    state.settings.autoSettings = { ...FAST_AUTO_SETTINGS };
    state.settings.speedProfileVersion = FAST_SPEED_PROFILE_VERSION;
    await setState(state);
  }

  elements.keywordInput.value = state.settings.currentKeyword || '';
  elements.languageSelect.value = state.settings.language || DEFAULT_LANGUAGE;
  applyLanguage(state.settings.language || DEFAULT_LANGUAGE);
  applyAutoSettingsToInputs(state.settings.autoSettings);
  applyLeadFiltersToInputs(state.settings.leadFilters);
  elements.openPanelBtn.disabled = IS_SIDE_PANEL;
  setPopupModeControls();
  elements.stopAutoBtn.disabled = true;
  render(state, IS_SIDE_PANEL
    ? t('message.openLoggedIn')
    : t('message.popupNeedsPanel'));
  if (state.runTimer.running) {
    startRunTimerTicker();
  }
  startX9BackendHeartbeat();
  postX9BackendHeartbeat('panel_open').catch(() => undefined);
});

elements.languageSelect.addEventListener('change', async () => {
  const state = await getState();
  state.settings.language = normalizeLanguage(elements.languageSelect.value);
  await setState(state);
  applyLanguage(state.settings.language);
  render(state);
});

elements.openPanelBtn.addEventListener('click', async () => {
  const state = await getState();
  const opened = await openSidePanel();
  render(state, opened
    ? (getLanguage() === 'zh' ? '侧边栏已打开，请在侧边栏里点击开始自动运行。' : 'Side panel opened. Click Start Auto Run in the side panel.')
    : (getLanguage() === 'zh' ? '当前浏览器无法打开侧边栏，自动运行需要侧边栏保持打开。' : 'Unable to open the side panel. Auto run needs the side panel to stay open.'));
});

elements.keywordInput.addEventListener('input', async () => {
  const state = await getState();
  state.settings.currentKeyword = elements.keywordInput.value.trim();
  await setState(state);
  render(state);
});

for (const input of [
  elements.autoProfilesInput
]) {
  input.addEventListener('change', async () => {
    const state = await getState();
    state.settings.autoSettings = getAutoSettingsFromInputs();
    await setState(state);
    render(state);
  });
}

for (const input of [elements.minFollowersInput]) {
  input.addEventListener('change', async () => {
    const state = await getState();
    state.settings.leadFilters = getLeadFiltersFromInputs();
    await setState(state);
    render(state, t('message.filterUpdated', { count: state.settings.leadFilters.minFollowers }));
  });
}

elements.openSearchBtn.addEventListener('click', async () => {
  await withBusy(async () => {
    const state = await getState();
    if (!(await ensureSidePanelForPageAction(state))) {
      return;
    }

    const keyword = elements.keywordInput.value.trim() || state.settings.currentKeyword;
    if (!keyword) {
      render(state, t('message.noKeyword'));
      return;
    }

    state.settings.currentKeyword = keyword;
    await setState(state);
    await searchTikTokKeyword(keyword);
    await delay(1_000);
    const scanResult = await scanCurrentPageIntoState(keyword);
    if (await shouldPauseForGate(scanResult.pageData, keyword)) {
      return;
    }

    render(scanResult.state, t('message.keywordFromPage', { keyword }));
    await runSearchResultsPageWorkflow(keyword, getAutoSettingsFromInputs(), scanResult.pageData);
  });
});

elements.scanPageBtn.addEventListener('click', async () => {
  await withBusy(async () => {
    const state = await getState();
    if (!(await ensureSidePanelForPageAction(state))) {
      return;
    }

    const pageData = await collectActiveTikTokPage();
    const keyword = resolveKeyword(state, pageData);
    const videosAdded = addSourceVideosAndPendingProfiles(state, pageData.videos, keyword);
    let profileMessage = '';

    if (pageData.profile && pageData.isProfilePage) {
      profileMessage = saveProfileFromPage(state, pageData.profile, keyword, pageData.url, pageData.title);
    }

    addTaskLog(state, keyword, 'scan_page', `videos_added=${videosAdded}`);
    pruneHandledQueue(state);
    await setState(state);

    const message = profileMessage || `已扫描当前页，新增 ${videosAdded} 个主页到队列。`;
    render(state, message);
  });
});

elements.openNextBtn.addEventListener('click', async () => {
  await withBusy(async () => {
    const state = await getState();
    if (!(await ensureSidePanelForPageAction(state))) {
      return;
    }

    const next = getNextPendingProfile(state);
    if (!next) {
      render(state, t('message.noPending'));
      return;
    }

    next.opened = true;
    next.opened_at = now();
    addTaskLog(state, next.search_keyword, 'open_profile', next.profile_url);
    await setState(state);
    await openProfileTabForCollection(next.profile_url);
    render(state, getLanguage() === 'zh'
      ? `已在新标签打开 @${next.creator_username}。页面加载后点击“扫描当前页”。`
      : `Opened @${next.creator_username} in a new tab. Click Scan Current Page after it loads.`);
  });
});

elements.startAutoBtn.addEventListener('click', async () => {
  if (autoRunActive) {
    return;
  }

  if (!IS_SIDE_PANEL) {
    const state = await getState();
    const opened = await openSidePanel();
    render(state, opened
      ? (getLanguage() === 'zh' ? '侧边栏已打开，请在侧边栏里点击开始自动运行。' : 'Side panel opened. Click Start Auto Run there.')
      : (getLanguage() === 'zh' ? '自动运行需要侧边栏，请开启 Chrome 侧边栏后重试。' : 'Auto run needs the side panel. Please enable the Chrome side panel and try again.'));
    return;
  }

  await runAutoWorkflow();
});

elements.stopAutoBtn.addEventListener('click', async () => {
  autoStopRequested = true;
  const state = await getState();
  state.settings.autoStopRequested = true;
  await setState(state);
  render(state, t('message.stopRequested'));
});

elements.copyNextBtn.addEventListener('click', async () => {
  const state = await getState();
  const next = getNextPendingProfile(state);
  if (!next) {
    render(state, t('message.noCopy'));
    return;
  }

  await navigator.clipboard.writeText(next.profile_url);
  render(state, t('message.copied', { username: next.creator_username }));
});

elements.exportCsvBtn.addEventListener('click', async () => {
  const state = await getState();
  const rows = state.leads.filter((lead) => lead.email);
  await downloadText(buildCsv(rows), `tiktok-leads-${dateStamp()}.csv`, 'text/csv');
  render(state, t('message.exportCsv', { count: rows.length }));
});

elements.exportExcelBtn.addEventListener('click', async () => {
  const state = await getState();
  const rows = state.leads.filter((lead) => lead.email);
  await exportLeadsToExcel(state, { saveAs: true });
  render(state, t('message.exportExcel', { count: rows.length }));
});

elements.exportJsonBtn.addEventListener('click', async () => {
  const state = await getState();
  const rows = state.leads.filter((lead) => lead.email);
  await downloadText(JSON.stringify(rows, null, 2), `tiktok-leads-${dateStamp()}.json`, 'application/json');
  render(state, t('message.exportJson', { count: rows.length }));
});

elements.exportBackupBtn.addEventListener('click', async () => {
  const state = await getState();
  await downloadText(JSON.stringify(state, null, 2), `tiktok-leads-backup-${dateStamp()}.json`, 'application/json');
  render(state, t('message.exportBackup'));
});

elements.clearBtn.addEventListener('click', async () => {
  const confirmed = confirm(t('confirm.clear'));
  if (!confirmed) {
    return;
  }

  const state = createEmptyState();
  state.settings.currentKeyword = elements.keywordInput.value.trim();
  state.settings.language = getLanguage();
  await setState(state);
  render(state, t('message.cleared'));
});

function getLanguage() {
  return normalizeLanguage(elements.languageSelect?.value || DEFAULT_LANGUAGE);
}

function normalizeLanguage(language) {
  return I18N[language] ? language : DEFAULT_LANGUAGE;
}

function t(key, values = {}) {
  const language = getLanguage();
  const template = I18N[language]?.[key] || I18N[DEFAULT_LANGUAGE]?.[key] || key;
  return Object.entries(values).reduce((text, [name, value]) => {
    return text.replaceAll(`{${name}}`, String(value));
  }, template);
}

function applyLanguage(language) {
  const normalized = normalizeLanguage(language);
  if (elements.languageSelect) {
    elements.languageSelect.value = normalized;
  }
  document.documentElement.lang = normalized === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
    element.setAttribute('placeholder', t(element.dataset.i18nPlaceholder));
  });
  elements.openPanelBtn.textContent = t(IS_SIDE_PANEL ? 'actions.panelReady' : 'actions.openPanel');
  elements.startAutoBtn.textContent = t(IS_SIDE_PANEL ? 'actions.start' : 'actions.openSidePanelStart');
}

async function withBusy(fn) {
  setButtonsDisabled(true);
  elements.status.textContent = t('message.busy');
  try {
    await fn();
  } catch (error) {
    elements.status.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  for (const button of document.querySelectorAll('button')) {
    button.disabled = disabled;
  }
  if (IS_SIDE_PANEL) {
    elements.openPanelBtn.disabled = true;
  }
  if (!disabled) {
    setPopupModeControls();
  }
}

function setAutoControlsRunning(running) {
  autoRunActive = running;
  if (!running) {
    stopRunTimerTicker();
  }
  elements.startAutoBtn.disabled = running;
  elements.stopAutoBtn.disabled = !running;
  elements.openSearchBtn.disabled = running;
  elements.scanPageBtn.disabled = running;
  elements.openNextBtn.disabled = running;
  elements.exportExcelBtn.disabled = running;
  elements.clearBtn.disabled = running;
  if (IS_SIDE_PANEL) {
    elements.openPanelBtn.disabled = true;
  }
  setPopupModeControls();
}

async function openSidePanel() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (chrome.sidePanel?.open && tab?.windowId) {
      await chrome.sidePanel.open({ windowId: tab.windowId });
      return true;
    }
  } catch {
    // Chrome may reject this on older versions or if side panel support is disabled.
  }

  return false;
}

function setPopupModeControls() {
  if (IS_SIDE_PANEL) {
    return;
  }

  elements.openSearchBtn.disabled = true;
  elements.scanPageBtn.disabled = true;
  elements.openNextBtn.disabled = true;
  elements.stopAutoBtn.disabled = true;
}

async function ensureSidePanelForPageAction(state) {
  if (IS_SIDE_PANEL) {
    return true;
  }

  const opened = await openSidePanel();
  render(state, opened
    ? (getLanguage() === 'zh' ? '侧边栏已打开，请在右侧侧边栏里执行该操作。' : 'Side panel opened. Please continue there.')
    : (getLanguage() === 'zh' ? '请先打开右侧侧边栏，小弹窗无法稳定执行页面自动操作。' : 'Please open the side panel first. The popup cannot run page automation reliably.'));
  return false;
}

async function runAutoWorkflow() {
  autoStopRequested = false;
  setAutoControlsRunning(true);
  let timerStarted = false;
  let runKeyword = '';

  try {
    let state = await getState();
    const autoSettings = getAutoSettingsFromInputs();
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const activeUrl = activeTab?.url || '';
    let activePageData = null;
    try {
      activePageData = await collectActiveTikTokPage();
    } catch {
      activePageData = null;
    }

    const keyword = resolveWorkflowKeyword(state, activePageData, activeUrl);

    if (!keyword) {
      render(state, t('message.noKeyword'));
      return;
    }

    runKeyword = keyword;
    state.settings.currentKeyword = keyword;
    state.settings.autoSettings = autoSettings;
    state.settings.autoStopRequested = false;
    startRunTimer(state);
    timerStarted = true;
    addTaskLog(state, keyword, 'auto_start', `target_profiles=${autoSettings.maxProfiles} started=${state.runTimer.started_at}`);
    await setState(state);
    startRunTimerTicker();
    renderTimer(state);
    elements.keywordInput.value = keyword;
    render(state, t('message.keywordFromPage', { keyword }));

    if (!activePageData && isSearchOrSearchOriginVideoUrl(activeUrl)) {
      await delay(FAST_PAGE_SETTLE_MS);
      activePageData = await collectActiveTikTokPage().catch(() => null);
    }

    const currentUrl = activePageData?.url || activeUrl;
    if (isTikTokSearchPageUrl(currentUrl) && !isTikTokSearchVideoPageUrl(currentUrl)) {
      render(await getState(), getLanguage() === 'zh' ? '已在搜索结果页，先点击“视频”选项卡。' : 'Search page detected. Opening the Video tab first.');
      await clickVideoTabInCurrentPage();
      await delay(FAST_PAGE_SETTLE_MS);
      activePageData = await collectActiveTikTokPage().catch(() => null);
    }

    if (isSearchResultsWorkflowPage(activePageData)) {
      render(state, getLanguage() === 'zh' ? '已进入搜索结果页：逐个打开视频卡片对应的博主主页。' : 'Search results page detected. Opening each video card creator profile.');
      await runSearchResultsPageWorkflow(keyword, autoSettings, activePageData);
      return;
    }

    if (isSearchOriginVideoPage(activePageData) || isSearchOriginVideoUrl(activeUrl)) {
      const currentVideo = buildCurrentVideoResult(activePageData, keyword) || buildVideoResultFromUrl(activeUrl, keyword);
      if (currentVideo) {
        addTaskLog(state, keyword, 'auto_close_video_then_direct_profile_mode', currentVideo.video_url);
        await setState(state);
        render(state, getLanguage() === 'zh' ? '检测到当前在视频播放页：先点一次关闭按钮显示搜索结果页。' : 'Video page detected. Closing it once to return to search results.');
        await activateTabIfExists(activeTab?.id);
        const closeResult = await clickVideoCloseButtonOnce(activeTab?.id);
        if (!closeResult.searchResultsFound) {
          throw new Error(getLanguage() === 'zh' ? '已点击视频关闭按钮，但还没有检测到搜索结果视频卡片。' : 'Video close was clicked, but search result cards were not detected yet.');
        }
        render(await getState(), getLanguage() === 'zh' ? '已点击一次视频关闭按钮，继续从搜索结果卡片直接打开博主主页。' : 'Video was closed. Continuing with creator profiles from search cards.');
        const searchPageData = await collectActiveTikTokPage().catch(() => null);
        await runSearchResultsPageWorkflow(keyword, autoSettings, searchPageData, getTikTokVideoIdentityKey(currentVideo.video_url));
        return;
      }
    }

    if (isSearchOrSearchOriginVideoUrl(activeUrl)) {
      state = await getState();
      const queuedVideo = getNextQueuedSourceVideo(state, keyword);
      addTaskLog(
        state,
        keyword,
        queuedVideo ? 'auto_resume_waiting_page_with_queue' : 'auto_waiting_search_page_no_queue',
        activeUrl
      );
      await setState(state);

      if (queuedVideo) {
        render(state, getLanguage() === 'zh'
          ? `当前页面还没完全读出来，但检测到已有视频队列，继续执行：@${queuedVideo.creator_username}`
          : `Page is still loading, but an existing queue was found. Continuing: @${queuedVideo.creator_username}`);
        activePageData = activePageData || await waitForWorkflowPageData(8_000);
        const preparedPageData = await ensureSearchResultsPageReady(keyword, '从已有视频队列继续执行', activePageData);
        if (preparedPageData) {
          await runSearchResultsPageWorkflow(keyword, autoSettings, preparedPageData);
          return;
        }
      }

      activePageData = activePageData || await waitForWorkflowPageData(8_000);
      if (activePageData) {
        const preparedPageData = await ensureSearchResultsPageReady(keyword, '等待页面加载后继续执行', activePageData);
        if (preparedPageData) {
          await runSearchResultsPageWorkflow(keyword, autoSettings, preparedPageData);
          return;
        }
      }

      render(await getState(), getLanguage() === 'zh'
        ? '当前搜索页还没加载出视频卡片，且本地没有可继续的视频队列。请等页面出现视频卡片后再开始。'
        : 'This search page has not loaded video cards yet, and there is no local queue. Start again after video cards appear.');
      return;
    }

    const preparedPageData = await ensureSearchResultsPageReady(keyword, '开始自动运行', activePageData);
    if (preparedPageData) {
      await runSearchResultsPageWorkflow(keyword, autoSettings, preparedPageData);
      return;
    }
  } catch (error) {
    const state = await getState();
    render(state, error instanceof Error ? error.message : String(error));
  } finally {
    const state = await getState();
    if (timerStarted || state.runTimer.running) {
      const elapsedMs = finishRunTimer(state);
      addTaskLog(state, runKeyword || state.settings.currentKeyword || '', 'auto_timer_done', `elapsed=${formatDuration(elapsedMs)}`);
    }
    state.settings.autoStopRequested = false;
    await setState(state);
    renderTimer(state);
    setAutoControlsRunning(false);
  }
}

async function scanCurrentPageIntoState(fallbackKeyword) {
  const pageData = await collectActiveTikTokPage();
  const state = await getState();
  const keyword = fallbackKeyword || resolveKeyword(state, pageData);
  const videosAdded = addSourceVideosAndPendingProfiles(state, pageData.videos, keyword);
  let profileMessage = '';

  if (pageData.profile && pageData.isProfilePage) {
    profileMessage = saveProfileFromPage(state, pageData.profile, keyword, pageData.url, pageData.title);
  }

  addTaskLog(state, keyword, 'auto_scan_page', `videos_added=${videosAdded}${profileMessage ? ` ${profileMessage}` : ''}`);
  pruneHandledQueue(state);
  await setState(state);

  return { pageData, state, videosAdded, profileMessage };
}

async function ensureSearchResultsPageReady(keyword, actionName, knownPageData = null) {
  let pageData = knownPageData || await collectActiveTikTokPage().catch(() => null);
  let state = await getState();
  const taskKeyword = keyword || state.settings.currentKeyword || pageData?.inferredSearchKeyword || '';
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!pageData && isSearchOrSearchOriginVideoUrl(activeTab?.url || '')) {
    pageData = await waitForWorkflowPageData(8_000);
  }

  if (pageData && await shouldPauseForGate(pageData, taskKeyword)) {
    return null;
  }

  if (isSearchResultsWorkflowPage(pageData)) {
    return pageData;
  }

  if (pageData && isSearchOriginVideoPage(pageData)) {
    addTaskLog(state, taskKeyword, 'page_guard_close_video_before_action', actionName);
    await setState(state);
    const closeResult = await clickVideoCloseButtonOnce(activeTab?.id);
    if (closeResult.searchResultsFound) {
      return collectActiveTikTokPage().catch(() => null);
    }
  }

  if (pageData && isTikTokSearchPageUrl(pageData.url || activeTab?.url || '')) {
    addTaskLog(state, taskKeyword, 'page_guard_click_video_tab_before_action', actionName);
    await setState(state);
    await clickVideoTabInCurrentPage();
    await delay(FAST_TAB_SETTLE_MS);
    pageData = await collectActiveTikTokPage().catch(() => null);
    if (pageData && await shouldPauseForGate(pageData, taskKeyword)) {
      return null;
    }
    if (isSearchResultsWorkflowPage(pageData)) {
      return pageData;
    }
  }

  const workflowTab = await findBestWorkflowTab(activeTab?.id);
  if (workflowTab?.id && workflowTab.id !== activeTab?.id) {
    addTaskLog(state, taskKeyword, 'page_guard_activate_workflow_tab', `${actionName} | ${workflowTab.url || ''}`);
    await setState(state);
    await activateTabIfExists(workflowTab.id);
    await delay(FAST_PAGE_SETTLE_MS);
    pageData = await collectActiveTikTokPage().catch(() => null);
    return ensureSearchResultsPageReady(taskKeyword, actionName, pageData);
  }

  state = await getState();
  addTaskLog(state, taskKeyword, 'page_guard_mismatch', `${actionName} | ${pageData?.url || activeTab?.url || 'unknown_page'}`);
  await setState(state);
  throw new Error(`当前页面不适合执行“${actionName}”。请打开 TikTok 搜索结果的视频卡片页，或保持从该搜索结果页打开的视频播放页。`);
}

async function waitForWorkflowPageData(timeoutMs = 8_000) {
  const startedAt = Date.now();
  let lastPageData = null;

  while (Date.now() - startedAt < timeoutMs) {
    lastPageData = await collectActiveTikTokPage().catch(() => null);
    if (lastPageData && (
      isSearchResultsWorkflowPage(lastPageData)
      || isSearchOriginVideoPage(lastPageData)
      || isTikTokSearchPageUrl(lastPageData.url || '')
    )) {
      return lastPageData;
    }

    await delay(350);
  }

  return lastPageData;
}

async function findBestWorkflowTab(currentTabId = null) {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const candidates = tabs
    .filter((tab) => tab?.id && tab.url && tab.url.includes('tiktok.com'))
    .map((tab) => ({
      tab,
      rank: getWorkflowTabRank(tab.url, tab.id === currentTabId)
    }))
    .filter((item) => item.rank < 99)
    .sort((first, second) => first.rank - second.rank);

  return candidates[0]?.tab || null;
}

function getWorkflowTabRank(url, isCurrentTab) {
  if (isTikTokSearchVideoPageUrl(url)) {
    return isCurrentTab ? 0 : 1;
  }
  if (isSearchOriginVideoUrl(url)) {
    return isCurrentTab ? 2 : 3;
  }
  if (isTikTokSearchPageUrl(url)) {
    return isCurrentTab ? 4 : 5;
  }
  return 99;
}

async function runSearchResultsPageWorkflow(keyword, autoSettings, initialPageData = null, resumeAfterVideoKey = '') {
  let processedProfiles = 0;
  let emptyRefreshes = 0;
  let pageData = initialPageData;
  let lastSearchResultVideoKey = resumeAfterVideoKey;
  const refreshLimit = getNavigationAttemptLimit(autoSettings);

  while (processedProfiles < autoSettings.maxProfiles) {
    if (await shouldStopAuto()) {
      render(await getState(), getLanguage() === 'zh' ? '自动运行已停止。' : 'Auto run stopped.');
      return;
    }

    pageData = await ensureSearchResultsPageReady(keyword, '处理搜索结果视频', pageData);
    if (!pageData) {
      return;
    }

    let state = await getState();
    const nextVideo = getNextSearchResultVideoCandidate(state, pageData, keyword, lastSearchResultVideoKey);
    await setState(state);

    if (!nextVideo) {
      emptyRefreshes += 1;
      if (pageData?.noMoreResults) {
        await stopWorkflowAndExportExcel(
          keyword,
          processedProfiles,
          'tiktok_no_more_results_text',
          getLanguage() === 'zh'
            ? `搜索结果页出现“暂时没有更多了”，已停止。已处理 ${processedProfiles} 个视频。`
            : `TikTok says there are no more results. Stopped after ${processedProfiles} videos.`
        );
        return;
      }

      if (emptyRefreshes > refreshLimit) {
        await stopWorkflowAndExportExcel(
          keyword,
          processedProfiles,
          'no_more_search_results',
          getLanguage() === 'zh'
            ? `搜索结果页没有更多可处理视频，已处理 ${processedProfiles} 个。`
            : `No more processable search results. Processed ${processedProfiles} videos.`
        );
        return;
      }

      render(state, getLanguage() === 'zh'
        ? `当前可见搜索结果已处理完，正在下滑当前搜索结果页加载新视频（${processedProfiles}/${autoSettings.maxProfiles}）。`
        : `Visible results are done. Scrolling to load more videos (${processedProfiles}/${autoSettings.maxProfiles}).`);
      const loadResult = await scrollSearchResultsPageToLoadMore(autoSettings);
      state = await getState();
      addTaskLog(
        state,
        keyword,
        loadResult?.loaded ? 'search_results_loaded_more' : 'search_results_scroll_no_new_cards',
        `steps=${loadResult?.steps || 0} before=${loadResult?.beforeCount || 0} after=${loadResult?.afterCount || 0} new=${loadResult?.newCount || 0}`
      );
      await setState(state);

      if (loadResult?.noMoreResults && !loadResult.loaded && (loadResult.newCount || 0) === 0) {
        await stopWorkflowAndExportExcel(
          keyword,
          processedProfiles,
          'tiktok_no_more_results_text',
          getLanguage() === 'zh'
            ? `搜索结果页出现“暂时没有更多了”，已停止。已处理 ${processedProfiles} 个视频。`
            : `TikTok says there are no more results. Stopped after ${processedProfiles} videos.`
        );
        return;
      }

      await delay(randomMilliseconds(autoSettings.minDelaySeconds, autoSettings.maxDelaySeconds));
      pageData = null;
      continue;
    }

    emptyRefreshes = 0;
    const message = await processSearchResultCreatorProfile(nextVideo, keyword, autoSettings);
    lastSearchResultVideoKey = getTikTokVideoIdentityKey(nextVideo.video_url);
    processedProfiles += 1;
    render(await getState(), getLanguage() === 'zh'
      ? `自动 ${processedProfiles}/${autoSettings.maxProfiles}：${message}`
      : `Auto ${processedProfiles}/${autoSettings.maxProfiles}: ${message}`);

    if (await maybeTakeRestBreak(processedProfiles, autoSettings, keyword)) {
      render(await getState(), getLanguage() === 'zh'
        ? `休息结束，已处理 ${processedProfiles} 个视频。`
        : `Rest finished. Processed ${processedProfiles} videos.`);
    }

    await delay(randomMilliseconds(autoSettings.minDelaySeconds, autoSettings.maxDelaySeconds));
    pageData = await collectActiveTikTokPage().catch(() => null);
  }

  const state = await getState();
  addTaskLog(state, keyword, 'auto_done', `processed=${processedProfiles} reason=max_profiles_search_results`);
  await setState(state);
  await exportCompletedTaskLeads(keyword, 'max_profiles_search_results');
  render(state, getLanguage() === 'zh'
    ? `自动运行完成，已处理 ${processedProfiles} 个视频。`
    : `Auto run complete. Processed ${processedProfiles} videos.`);
}

async function exportCompletedTaskLeads(keyword, reason) {
  let state = await getState();
  try {
    const exportResult = await exportLeadsToExcel(state, {
      saveAs: false,
      filenameSuffix: reason
    });
    state = await getState();
    addTaskLog(state, keyword, 'export_done', `excel=${exportResult.filename} rows=${exportResult.count} reason=${reason}`);
    await setState(state);
    return exportResult;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    state = await getState();
    addTaskLog(state, keyword, 'error', `auto_excel_export_failed: ${message}`);
    await setState(state);
    return null;
  }
}

async function stopWorkflowAndExportExcel(keyword, processedProfiles, reason, statusMessage) {
  let state = await getState();
  addTaskLog(state, keyword, 'auto_done', `processed=${processedProfiles} reason=${reason}`);
  await setState(state);

  try {
    const exportResult = await exportCompletedTaskLeads(keyword, reason);
    if (!exportResult) {
      throw new Error('Excel export failed.');
    }
    state = await getState();
    render(state, getLanguage() === 'zh'
      ? `${statusMessage} 已自动导出 Excel：${exportResult.filename}（${exportResult.count} 条线索）。`
      : `${statusMessage} Excel exported automatically: ${exportResult.filename} (${exportResult.count} leads).`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    state = await getState();
    addTaskLog(state, keyword, 'error', `auto_excel_export_failed: ${message}`);
    await setState(state);
    render(state, getLanguage() === 'zh'
      ? `${statusMessage} 但自动导出 Excel 失败：${message}`
      : `${statusMessage} Excel auto export failed: ${message}`);
  }
}

async function processSearchResultCreatorProfile(video, keyword, autoSettings) {
  let state = await getState();
  const duplicate = findDuplicateBeforeProfileOpen(state, video);
  if (duplicate) {
    skipSourceVideoBeforeProfile(state, video, keyword, duplicate.reason, 'skipped_duplicate_before_profile');
    await setState(state);
    return `重复已跳过：${duplicate.message}`;
  }

  ensureSourceVideoRecord(state, video, keyword);
  ensurePendingProfileForVideo(state, video, keyword);
  addTaskLog(state, keyword, 'auto_open_profile_from_search_card', `${video.creator_username} | ${video.creator_profile_url}`);
  await setState(state);

  let profileTab = null;
  let searchTab = null;

  try {
    await ensureSearchResultsPageReady(keyword, '从搜索结果卡片打开博主主页');
    searchTab = await getActiveTikTokTab('请先打开 TikTok 搜索结果视频页。');

    profileTab = await openProfileTabForCollection(video.creator_profile_url, searchTab.id);
    await waitForTabComplete(profileTab.id, 90_000);
    await delay(randomMilliseconds(autoSettings.minDelaySeconds, autoSettings.maxDelaySeconds));

    const profilePageData = await collectTikTokPageFromTab(profileTab.id);
    if (await shouldPauseForGate(profilePageData, keyword)) {
      return '检测到登录或验证，已停在主页标签页，请手动处理后重新开始。';
    }

    state = await getState();
    let message = '';
    if (profilePageData.profile && profilePageData.isProfilePage) {
      message = saveProfileFromPage(state, profilePageData.profile, keyword, profilePageData.url, profilePageData.title);
    } else {
      if (!state.skippedProfiles.some((item) => item.profile_url === video.creator_profile_url && item.search_keyword === keyword)) {
        state.skippedProfiles.push({
          id: uniqueId(),
          search_keyword: keyword,
          username: video.creator_username,
          profile_url: video.creator_profile_url,
          source_video_url: video.video_url,
          source_video_title: video.video_title || '',
          reason: 'profile_not_detected',
          checked_at: now()
        });
      }
      markProfileHandled(state, video.creator_profile_url);
      addTaskLog(state, keyword, 'skipped_profile_not_detected', `${video.creator_username} | ${video.creator_profile_url}`);
      message = `主页未识别，已跳过 @${video.creator_username}`;
    }

    markSourceVideoHandled(state, video.video_url, keyword);
    markPendingSourceVideoHandled(state, video.video_url, keyword);
    pruneHandledQueue(state);
    await setState(state);

    await closeProfileTabAfterCollection(profileTab, video.creator_profile_url, searchTab.id);
    profileTab = null;
    await activateTabIfExists(searchTab.id);

    return `${message} 已关闭主页标签。`;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    state = await getState();
    if (!state.skippedProfiles.some((item) => item.profile_url === video.creator_profile_url && item.search_keyword === keyword)) {
      state.skippedProfiles.push({
        id: uniqueId(),
        search_keyword: keyword,
        username: video.creator_username,
        profile_url: video.creator_profile_url,
        source_video_url: video.video_url,
        source_video_title: video.video_title || '',
        reason: `profile_collect_error: ${errorMessage}`,
        checked_at: now()
      });
    }
    markSourceVideoHandled(state, video.video_url, keyword);
    markPendingSourceVideoHandled(state, video.video_url, keyword);
    markProfileHandled(state, video.creator_profile_url);
    pruneHandledQueue(state);
    addTaskLog(state, keyword, 'error', `${video.creator_username} | ${errorMessage}`);
    await setState(state);

    if (profileTab?.id) {
      await closeProfileTabAfterCollection(profileTab, video.creator_profile_url, searchTab?.id).catch(() => undefined);
    }
    if (searchTab?.id) {
      await activateTabIfExists(searchTab.id);
    }

    return `主页采集失败，已跳过 @${video.creator_username}：${errorMessage}`;
  }
}

async function shouldPauseForGate(pageData, keyword) {
  if (!pageData?.gate || pageData.gate.type === 'none') {
    return false;
  }

  const state = await getState();
  addTaskLog(state, keyword, 'pause_required', `${pageData.gate.type}: ${pageData.gate.matchedText}`);
  state.settings.autoStopRequested = true;
  await setState(state);
  render(state, `检测到 ${pageData.gate.type}，请在浏览器里手动处理后再重新开始。`);
  return true;
}

async function shouldStopAuto() {
  if (autoStopRequested) {
    return true;
  }

  const state = await getState();
  return Boolean(state.settings.autoStopRequested);
}

async function scrollActiveTikTokPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先打开 TikTok 页面再滚动。');
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, { type: 'TCLAB_SCROLL_PAGE' });
  if (!response?.ok) {
    throw new Error(response?.error || '无法滚动当前页面。');
  }

  return response.data;
}

async function scrollSearchResultsPageToLoadMore(autoSettings = {}) {
  await ensureSearchResultsPageReady('', '下滑搜索结果页加载新视频');

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先打开 TikTok 搜索结果视频页再加载更多。');
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, {
    type: 'TCLAB_SCROLL_SEARCH_RESULTS',
    options: {
      timeoutMs: Math.max(5_000, Math.min(15_000, (autoSettings.maxDelaySeconds || 4) * 2_000)),
      maxSteps: 5
    }
  });

  if (!response?.ok) {
    throw new Error(response?.error || '无法下滑搜索结果页加载新视频。');
  }

  return response.data;
}

async function waitForActiveTabComplete(timeoutMs) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    return;
  }

  await waitForTabComplete(tab.id, timeoutMs);
}

async function waitForTabComplete(tabId, timeoutMs) {
  const freshTab = await chrome.tabs.get(tabId).catch(() => null);
  if (freshTab?.status === 'complete') {
    await delay(FAST_PAGE_SETTLE_MS);
    return;
  }

  await new Promise((resolve) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }

    chrome.tabs.onUpdated.addListener(listener);
  });

  await delay(FAST_PAGE_SETTLE_MS);
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function randomMilliseconds(minSeconds, maxSeconds) {
  const min = Math.max(0, Number(minSeconds) || 0);
  const max = Math.max(min, Number(maxSeconds) || min);
  return Math.round((min + Math.random() * (max - min)) * 1000);
}

async function maybeTakeRestBreak(processedCount, autoSettings, keyword) {
  if (!autoSettings.restEveryProfiles || autoSettings.restEveryProfiles <= 0) {
    return false;
  }

  if (processedCount <= 0 || processedCount % autoSettings.restEveryProfiles !== 0) {
    return false;
  }

  const restMs = randomMilliseconds(autoSettings.restMinSeconds, autoSettings.restMaxSeconds);
  const restSeconds = Math.round(restMs / 1000);
  const state = await getState();
  addTaskLog(state, keyword, 'auto_rest_break', `processed=${processedCount} seconds=${restSeconds}`);
  await setState(state);
  render(state, `已处理 ${processedCount} 个视频，休息约 ${restSeconds} 秒。`);
  await delay(restMs);
  return true;
}

function getAutoSettingsFromInputs() {
  const maxProfiles = clampInteger(elements.autoProfilesInput.value, 1, 5000, 20);

  return {
    maxScrolls: FAST_AUTO_SETTINGS.maxScrolls,
    maxProfiles,
    minDelaySeconds: FAST_AUTO_SETTINGS.minDelaySeconds,
    maxDelaySeconds: FAST_AUTO_SETTINGS.maxDelaySeconds,
    restEveryProfiles: FAST_AUTO_SETTINGS.restEveryProfiles,
    restMinSeconds: FAST_AUTO_SETTINGS.restMinSeconds,
    restMaxSeconds: FAST_AUTO_SETTINGS.restMaxSeconds
  };
}

function applyAutoSettingsToInputs(settings) {
  const normalized = normalizeAutoSettings(settings);
  elements.autoProfilesInput.value = String(normalized.maxProfiles);
}

function normalizeAutoSettings(settings) {
  return {
    maxScrolls: FAST_AUTO_SETTINGS.maxScrolls,
    maxProfiles: clampInteger(settings?.maxProfiles, 1, 5000, FAST_AUTO_SETTINGS.maxProfiles),
    minDelaySeconds: FAST_AUTO_SETTINGS.minDelaySeconds,
    maxDelaySeconds: FAST_AUTO_SETTINGS.maxDelaySeconds,
    restEveryProfiles: FAST_AUTO_SETTINGS.restEveryProfiles,
    restMinSeconds: FAST_AUTO_SETTINGS.restMinSeconds,
    restMaxSeconds: FAST_AUTO_SETTINGS.restMaxSeconds
  };
}

function getNavigationAttemptLimit(autoSettings) {
  const targetProfiles = clampInteger(autoSettings?.maxProfiles, 1, 5000, FAST_AUTO_SETTINGS.maxProfiles);
  return Math.min(30, Math.max(5, Math.ceil(targetProfiles / 10)));
}

function getLeadFiltersFromInputs() {
  return {
    requireEmail: true,
    minFollowers: clampInteger(elements.minFollowersInput.value, 0, 1000000000, 1000)
  };
}

function applyLeadFiltersToInputs(filters) {
  const normalized = normalizeLeadFilters(filters);
  elements.requireEmailInput.checked = normalized.requireEmail;
  elements.minFollowersInput.value = String(normalized.minFollowers);
}

function normalizeLeadFilters(filters) {
  return {
    requireEmail: true,
    minFollowers: clampInteger(filters?.minFollowers, 0, 1000000000, 1000)
  };
}

// ---- Contact-method detection ------------------------------------------
// Mirrors backend/utils/contact_methods.py. Returns the set of contact
// channels detected on the profile. Used by the scrape filter: if a
// profile exposes ANY of these channels, it qualifies as a lead.

const TCLAB_EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
const TCLAB_PHONE_RE = /(?:\+|00)\d[\d\s().\-]{7,}\d/;

const TCLAB_CONTACT_TERMS = {
  whatsapp: ['whatsapp', 'whats app', 'wa.me', 'api.whatsapp.com', 'chat.whatsapp.com', 'wa:'],
  instagram: ['instagram', 'instagram.com', 'insta', 'ig:', 'ig @'],
  link: ['linktr.ee', 'beacons.ai', 'bio.site', 'taplink', 'stan.store', 'link in bio'],
  telegram: ['telegram', 't.me/', 'telegram.me'],
  line: ['line.me', 'lin.ee', 'line id', 'line:'],
  facebook: ['facebook.com', 'fb.me', 'm.me/'],
  dm: ['dm me', 'dm for', 'direct message', 'message me'],
  phone: ['tel:', 'call me', 'text me']
};

function tclabDetectContactChannels(profile) {
  const channels = new Set();
  const bioRaw = String(profile?.bio || '');
  const bio = bioRaw.toLowerCase();
  const emails = Array.isArray(profile?.emails) ? profile.emails : [];
  const singleEmail = String(profile?.email || '').trim();
  const externalLinks = Array.isArray(profile?.external_links) ? profile.external_links : [];

  // Email — collected by content script + regex on bio
  if (emails.length > 0 || singleEmail || TCLAB_EMAIL_RE.test(bioRaw)) {
    channels.add('email');
  }

  // Phone numbers in bio (international format)
  if (TCLAB_PHONE_RE.test(bioRaw)) {
    channels.add('phone');
  }

  // Channel keywords in bio text
  for (const [kind, terms] of Object.entries(TCLAB_CONTACT_TERMS)) {
    if (channels.has(kind)) continue;
    for (const term of terms) {
      if (bio.includes(term)) {
        channels.add(kind);
        break;
      }
    }
  }

  // External link domains map to channels
  for (const link of externalLinks) {
    const lower = String(link || '').toLowerCase();
    if (lower.startsWith('mailto:')) {
      channels.add('email');
    } else if (lower.includes('wa.me/') || lower.includes('whatsapp.com')) {
      channels.add('whatsapp');
    } else if (lower.includes('instagram.com')) {
      channels.add('instagram');
    } else if (lower.includes('t.me/') || lower.includes('telegram.me')) {
      channels.add('telegram');
    } else if (lower.includes('line.me') || lower.includes('lin.ee')) {
      channels.add('line');
    } else if (lower.includes('facebook.com') || lower.includes('fb.me') || lower.includes('m.me/')) {
      channels.add('facebook');
    } else if (
      lower.includes('linktr.ee') ||
      lower.includes('beacons.ai') ||
      lower.includes('bio.site') ||
      lower.includes('taplink') ||
      lower.includes('stan.store')
    ) {
      channels.add('link');
    }
  }

  return Array.from(channels);
}

function tclabHasAnyContactMethod(profile) {
  return tclabDetectContactChannels(profile).length > 0;
}

function evaluateProfileAgainstFilters(profile, filters) {
  const normalizedFilters = normalizeLeadFilters(filters);
  const channels = tclabDetectContactChannels(profile);
  const hasContact = channels.length > 0;

  if (normalizedFilters.requireEmail && !hasContact) {
    // `requireEmail` field is kept for backward compat with stored state,
    // but its semantics are now "require any contact method".
    return {
      qualified: false,
      reason: 'no_contact',
      message: '没有可见联系方式（邮箱 / WhatsApp / Instagram / 链接 / Telegram / LINE / 电话 / 私信）'
    };
  }

  const followersCount = Number.isFinite(profile.followers_count) ? profile.followers_count : null;
  if (normalizedFilters.minFollowers > 0 && followersCount === null) {
    return {
      qualified: false,
      reason: 'followers_unknown',
      message: `粉丝数未知，最低要求 ${normalizedFilters.minFollowers}`
    };
  }

  if (normalizedFilters.minFollowers > 0 && followersCount < normalizedFilters.minFollowers) {
    return {
      qualified: false,
      reason: 'followers_below_min',
      message: `粉丝数 ${followersCount}，最低要求 ${normalizedFilters.minFollowers}`
    };
  }

  return {
    qualified: true,
    reason: 'qualified',
    message: `检测到联系方式 [${channels.join(', ')}] 且粉丝数 >= ${normalizedFilters.minFollowers}`
  };
}

function clampInteger(value, min, max, fallback) {
  const parsed = Number.parseInt(String(value), 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

async function collectActiveTikTokPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先打开 TikTok 页面再扫描。');
  }

  return collectTikTokPageFromTab(tab.id);
}

async function collectTikTokPageFromTab(tabId) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先打开 TikTok 页面再扫描。');
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, { type: 'TCLAB_COLLECT_PAGE' });
  if (!response?.ok) {
    throw new Error(response?.error || '无法扫描当前页面，请刷新 TikTok 后重试。');
  }

  return response.data;
}

async function searchTikTokKeyword(keyword) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw new Error('没有找到当前标签页。');
  }

  if (!tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先在当前标签页打开已登录的 TikTok 页面。');
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, {
    type: 'TCLAB_SEARCH_TIKTOK',
    keyword
  });

  if (!response?.ok) {
    throw new Error(response?.error || '无法从当前页面搜索 TikTok。');
  }

  await delay(FAST_SEARCH_SETTLE_MS);
  const videoTabResult = await clickVideoTabInCurrentPage();
  await waitForActiveTabComplete(90_000);
  await delay(FAST_TAB_SETTLE_MS);

  return {
    ...response.data,
    videoTabMethod: videoTabResult.method
  };
}

async function clickVideoTabInCurrentPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先在当前标签页打开已登录的 TikTok 页面。');
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, {
    type: 'TCLAB_CLICK_VIDEO_TAB'
  });

  if (!response?.ok) {
    throw new Error(response?.error || '无法从当前页面点击视频选项卡。');
  }

  return response.data;
}

function addSourceVideosAndPendingProfiles(state, videos, keyword) {
  let added = 0;

  for (const video of videos || []) {
    const record = {
      id: uniqueId(),
      creator_username: video.creator_username,
      creator_profile_url: video.creator_profile_url,
      search_keyword: keyword,
      video_url: video.video_url,
      video_title: video.video_title || '',
      video_description: video.video_description || '',
      collected_at: now(),
      handled: false
    };
    sendX9VideoObservation(record, keyword).catch(() => undefined);

    if (!state.sourceVideos.some((item) => item.video_url === record.video_url && item.search_keyword === keyword)) {
      state.sourceVideos.push(record);
    }

    const alreadyQueued = state.pendingProfiles.some((item) => item.profile_url === record.creator_profile_url && item.search_keyword === keyword);
    const alreadyHandled = isProfileAlreadyHandled(state, record.creator_profile_url, record.creator_username);
    if (!alreadyQueued && !alreadyHandled) {
      state.pendingProfiles.push({
        id: uniqueId(),
        search_keyword: keyword,
        creator_username: record.creator_username,
        profile_url: record.creator_profile_url,
        source_video_url: record.video_url,
        source_video_title: record.video_title,
        source_video_description: record.video_description,
        opened: false,
        opened_at: '',
        handled: false
      });
      added += 1;
    }
  }

  return added;
}

function getFirstRelevantVideoResult(pageData, _keyword) {
  const videos = Array.isArray(pageData?.videos) ? pageData.videos : [];
  return videos.find((video) => {
    return video.video_url
      && video.creator_profile_url
      && video.creator_username;
  }) || null;
}

function getFirstVideoCandidate(pageData, _keyword) {
  const videos = Array.isArray(pageData?.videos) ? pageData.videos : [];
  const validVideos = videos.filter((video) => video.video_url && video.creator_profile_url && video.creator_username);
  return validVideos[0] || null;
}

function isSearchResultsWorkflowPage(pageData) {
  if (!pageData) {
    return false;
  }

  const hasSearchCards = Array.isArray(pageData.videos) && pageData.videos.length > 0;
  const urlLooksLikeSearch = /\/search(?:\/video)?\b/i.test(String(pageData.url || ''));
  return Boolean(pageData.isSearchVideoPage || (hasSearchCards && !pageData.currentVideo) || (urlLooksLikeSearch && hasSearchCards));
}

function inferSearchKeywordFromUrl(value) {
  try {
    const url = new URL(value);
    return url.searchParams.get('q') || '';
  } catch {
    return '';
  }
}

function isTikTokSearchPageUrl(value) {
  try {
    const url = new URL(value);
    return /\/search(?:\/video)?\b/i.test(url.pathname);
  } catch {
    return /\/search(?:\/video)?\b/i.test(String(value || ''));
  }
}

function isTikTokSearchVideoPageUrl(value) {
  try {
    const url = new URL(value);
    return /\/search\/video\b/i.test(url.pathname);
  } catch {
    return /\/search\/video\b/i.test(String(value || ''));
  }
}

function isSearchOrSearchOriginVideoUrl(value) {
  try {
    const url = new URL(value);
    return /\/search(?:\/video)?\b/i.test(url.pathname)
      || isSearchOriginVideoUrl(value);
  } catch {
    const text = String(value || '');
    return /\/search(?:\/video)?\b/i.test(text)
      || isSearchOriginVideoUrl(text);
  }
}

function isSearchOriginVideoUrl(value) {
  try {
    const url = new URL(value);
    return /\/@[^/]+\/video\/\d+/i.test(url.pathname) && Boolean(url.searchParams.get('q'));
  } catch {
    const text = String(value || '');
    return /\/@[^/]+\/video\/\d+/i.test(text) && /[?&]q=/i.test(text);
  }
}

function isSearchOriginVideoPage(pageData) {
  if (!pageData?.isVideoPage || !pageData.url) {
    return false;
  }

  try {
    const url = new URL(pageData.url);
    return /\/@[^/]+\/video\/\d+/i.test(url.pathname)
      && Boolean(url.searchParams.get('q') || pageData.inferredSearchKeyword);
  } catch {
    return /\/@[^/]+\/video\/\d+/i.test(String(pageData.url))
      && /[?&]q=/i.test(String(pageData.url));
  }
}

function getNextSearchResultVideoCandidate(state, pageData, keyword, _afterVideoKey = '') {
  const videos = Array.isArray(pageData?.videos) ? pageData.videos : [];
  queueVisibleSearchResultVideos(state, videos, keyword);

  const visibleVideos = buildVisibleSearchVideoMap(videos);

  for (const queuedVideo of state.sourceVideos) {
    if (queuedVideo.search_keyword !== keyword || queuedVideo.handled) {
      continue;
    }

    const visibleVideo = getVisibleVideoFromQueueItem(queuedVideo, visibleVideos, videos);
    const candidate = visibleVideo || queuedVideo;
    if (!candidate?.video_url || !candidate?.creator_profile_url || !candidate?.creator_username) {
      continue;
    }

    if (isSearchResultVideoAlreadyHandled(state, candidate)) {
      skipSourceVideoBeforeProfile(state, candidate, keyword, 'already_handled_or_checked', 'skipped_duplicate_before_profile');
      continue;
    }

    const duplicate = findDuplicateBeforeProfileOpen(state, candidate);
    if (duplicate) {
      skipSourceVideoBeforeProfile(state, candidate, keyword, duplicate.reason, 'skipped_duplicate_before_profile');
      continue;
    }

    return candidate;
  }

  return null;
}

function getNextQueuedSourceVideo(state, keyword) {
  return (state.sourceVideos || []).find((video) => {
    if (video.search_keyword !== keyword || video.handled) {
      return false;
    }

    if (!video.video_url || !video.creator_profile_url || !video.creator_username) {
      return false;
    }

    if (isSearchResultVideoAlreadyHandled(state, video)) {
      return false;
    }

    return true;
  }) || null;
}

function queueVisibleSearchResultVideos(state, videos, keyword) {
  for (const video of videos || []) {
    if (!video?.video_url || !video?.creator_profile_url || !video?.creator_username) {
      continue;
    }

    ensureSourceVideoRecord(state, video, keyword);
  }
}

function buildVisibleSearchVideoMap(videos) {
  const byVideoKey = new Map();
  const byCanonicalUrl = new Map();

  for (const video of videos || []) {
    if (!video?.video_url) {
      continue;
    }

    const videoKey = getTikTokVideoIdentityKey(video.video_url);
    if (videoKey && !byVideoKey.has(videoKey)) {
      byVideoKey.set(videoKey, video);
    }

    const canonicalVideoUrl = canonicalUrl(video.video_url);
    if (canonicalVideoUrl && !byCanonicalUrl.has(canonicalVideoUrl)) {
      byCanonicalUrl.set(canonicalVideoUrl, video);
    }
  }

  return {
    byVideoKey,
    byCanonicalUrl
  };
}

function getVisibleVideoFromQueueItem(queuedVideo, visibleVideos, videos) {
  const queuedKey = getTikTokVideoIdentityKey(queuedVideo.video_url);
  if (queuedKey && visibleVideos.byVideoKey.has(queuedKey)) {
    return visibleVideos.byVideoKey.get(queuedKey);
  }

  const queuedUrl = canonicalUrl(queuedVideo.video_url);
  if (queuedUrl && visibleVideos.byCanonicalUrl.has(queuedUrl)) {
    return visibleVideos.byCanonicalUrl.get(queuedUrl);
  }

  return (videos || []).find((video) => {
    return normalizeUsername(video?.creator_username) === normalizeUsername(queuedVideo.creator_username)
      && canonicalUrl(video?.creator_profile_url || '') === canonicalUrl(queuedVideo.creator_profile_url || '');
  }) || null;
}

function buildCurrentVideoResult(pageData, keyword) {
  if (pageData?.currentVideo?.creator_username) {
    return {
      search_keyword: keyword,
      video_url: canonicalUrl(pageData.currentVideo.video_url || pageData.url),
      video_title: truncateText(pageData.currentVideo.video_title || pageData.title || '', 500),
      video_description: truncateText(pageData.currentVideo.video_description || pageData.visibleText || '', 1000),
      creator_username: pageData.currentVideo.creator_username,
      creator_profile_url: pageData.currentVideo.creator_profile_url || `https://www.tiktok.com/@${encodeURIComponent(pageData.currentVideo.creator_username)}`,
      video_fingerprint: pageData.currentVideo.video_fingerprint || ''
    };
  }

  if (!pageData?.isVideoPage || !pageData.url) {
    return null;
  }

  const username = extractUsernameFromTikTokUrl(pageData.url);
  if (!username) {
    return null;
  }

  const description = truncateText(pageData.visibleText || pageData.title || '', 1000);
  return {
    search_keyword: keyword,
    video_url: canonicalUrl(pageData.url),
    video_title: truncateText(pageData.title || description || pageData.url, 500),
    video_description: description,
    creator_username: username,
    creator_profile_url: `https://www.tiktok.com/@${encodeURIComponent(username)}`,
    video_fingerprint: `${username}|${canonicalUrl(pageData.url)}`
  };
}

function buildVideoResultFromUrl(value, keyword) {
  const username = extractUsernameFromTikTokUrl(value);
  if (!username || !/\/@[^/]+\/video\/\d+/i.test(String(value || ''))) {
    return null;
  }

  const videoUrl = canonicalUrl(value);
  return {
    search_keyword: keyword,
    video_url: videoUrl,
    video_title: videoUrl,
    video_description: '',
    creator_username: username,
    creator_profile_url: `https://www.tiktok.com/@${encodeURIComponent(username)}`,
    video_fingerprint: `${username}|${videoUrl}`
  };
}

function extractUsernameFromTikTokUrl(value) {
  const match = String(value || '').match(/\/@([^/?#]+)(?:\/|$)/i);
  return match?.[1] ? decodeURIComponent(match[1]).trim() : '';
}

function normalizeUsername(value) {
  return String(value || '').replace(/^@/, '').trim().toLowerCase();
}

function getTikTokVideoIdentityKey(value) {
  const raw = String(value || '');
  const match = raw.match(/\/@([^/?#]+)\/video\/(\d+)/i);
  if (!match?.[1] || !match?.[2]) {
    return '';
  }

  return `${normalizeUsername(decodeURIComponent(match[1]))}/video/${match[2]}`;
}

function canonicalUrl(value) {
  try {
    const url = new URL(value);
    url.hash = '';
    return url.toString();
  } catch {
    return String(value || '').trim();
  }
}

function truncateText(value, maxLength) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > maxLength ? `${text.slice(0, Math.max(0, maxLength - 3))}...` : text;
}

function markSourceVideoHandled(state, videoUrl, keyword) {
  const targetKey = getTikTokVideoIdentityKey(videoUrl);
  const targetUrl = canonicalUrl(videoUrl);
  for (const video of state.sourceVideos) {
    const sameVideo = targetKey
      ? getTikTokVideoIdentityKey(video.video_url) === targetKey
      : canonicalUrl(video.video_url) === targetUrl;
    if (sameVideo && video.search_keyword === keyword) {
      video.handled = true;
      video.handled_at = now();
    }
  }
}

function ensureSourceVideoRecord(state, video, keyword) {
  if (!video?.video_url || !video?.creator_username || !video?.creator_profile_url) {
    return false;
  }
  sendX9VideoObservation(video, keyword).catch(() => undefined);

  const targetKey = getTikTokVideoIdentityKey(video.video_url);
  const targetUrl = canonicalUrl(video.video_url);
  const exists = state.sourceVideos.some((item) => {
    const sameVideo = targetKey
      ? getTikTokVideoIdentityKey(item.video_url) === targetKey
      : canonicalUrl(item.video_url) === targetUrl;
    return sameVideo && item.search_keyword === keyword;
  });
  if (exists) {
    return false;
  }

  state.sourceVideos.push({
    id: uniqueId(),
    creator_username: video.creator_username,
    creator_profile_url: video.creator_profile_url,
    search_keyword: keyword,
    video_url: video.video_url,
    video_title: video.video_title || '',
    video_description: video.video_description || '',
    collected_at: now(),
    handled: false
  });

  return true;
}

function skipSourceVideoBeforeProfile(state, video, keyword, reason, eventType) {
  ensureSourceVideoRecord(state, video, keyword);
  markSourceVideoHandled(state, video.video_url, keyword);
  markPendingSourceVideoHandled(state, video.video_url, keyword);
  addTaskLog(state, keyword, eventType, `${video.creator_username || 'unknown'} | ${video.video_url || ''} | ${reason}`);
}

function markPendingSourceVideoHandled(state, videoUrl, keyword) {
  const targetKey = getTikTokVideoIdentityKey(videoUrl);
  const targetUrl = canonicalUrl(videoUrl);
  for (const item of state.pendingProfiles) {
    const sameVideo = targetKey
      ? getTikTokVideoIdentityKey(item.source_video_url) === targetKey
      : canonicalUrl(item.source_video_url) === targetUrl;
    if (sameVideo && item.search_keyword === keyword) {
      item.handled = true;
    }
  }
}

function findDuplicateBeforeProfileOpen(state, video) {
  const username = normalizeUsername(video?.creator_username);
  const profileUrl = canonicalUrl(video?.creator_profile_url || '');
  const videoKey = getTikTokVideoIdentityKey(video?.video_url || '');

  if (state.leads.some((lead) => canonicalUrl(lead.profile_url) === profileUrl || normalizeUsername(lead.username) === username)) {
    return {
      reason: 'duplicate_saved_profile',
      message: `账号已保存：@${video.creator_username}`
    };
  }

  if (state.skippedProfiles.some((item) => canonicalUrl(item.profile_url) === profileUrl || normalizeUsername(item.username) === username)) {
    return {
      reason: 'duplicate_checked_profile',
      message: `账号已检查过：@${video.creator_username}`
    };
  }

  if (videoKey && state.sourceVideos.some((item) => item.handled && getTikTokVideoIdentityKey(item.video_url) === videoKey)) {
    return {
      reason: 'duplicate_handled_video',
      message: `视频已处理过：@${video.creator_username}`
    };
  }

  return null;
}

function isSearchResultVideoAlreadyHandled(state, video) {
  const username = normalizeUsername(video?.creator_username);
  const profileUrl = canonicalUrl(video?.creator_profile_url || '');
  const videoKey = getTikTokVideoIdentityKey(video?.video_url || '');

  return (videoKey && state.sourceVideos.some((item) => item.handled && getTikTokVideoIdentityKey(item.video_url) === videoKey))
    || state.leads.some((lead) => canonicalUrl(lead.profile_url) === profileUrl || normalizeUsername(lead.username) === username)
    || state.skippedProfiles.some((item) => canonicalUrl(item.profile_url) === profileUrl || normalizeUsername(item.username) === username);
}

function ensurePendingProfileForVideo(state, video, keyword) {
  if (!video?.creator_profile_url || !video?.creator_username) {
    return false;
  }

  ensureSourceVideoRecord(state, video, keyword);

  const alreadyQueued = state.pendingProfiles.some((item) => item.profile_url === video.creator_profile_url && item.search_keyword === keyword);
  const alreadyHandled = isProfileAlreadyHandled(state, video.creator_profile_url, video.creator_username);
  if (alreadyQueued || alreadyHandled) {
    return false;
  }

  state.pendingProfiles.unshift({
    id: uniqueId(),
    search_keyword: keyword,
    creator_username: video.creator_username,
    profile_url: video.creator_profile_url,
    source_video_url: video.video_url,
    source_video_title: video.video_title || '',
    source_video_description: video.video_description || '',
    opened: false,
    opened_at: '',
    handled: false
  });

  return true;
}

function saveProfileFromPage(state, profile, keyword, currentUrl, title) {
  const source = findSourceForProfile(state, profile.profile_url, keyword);
  const filters = normalizeLeadFilters(state.settings.leadFilters);
  const evaluation = evaluateProfileAgainstFilters(profile, filters);
  sendX9ProfileObservation(profile, keyword, source, currentUrl, title, evaluation).catch(() => undefined);

  if (!evaluation.qualified) {
    if (!state.skippedProfiles.some((item) => item.profile_url === profile.profile_url && item.search_keyword === keyword)) {
      state.skippedProfiles.push({
        id: uniqueId(),
        search_keyword: keyword,
        username: profile.username,
        profile_url: profile.profile_url,
        source_video_url: source?.source_video_url || currentUrl,
        source_video_title: source?.source_video_title || title || '',
        reason: evaluation.reason,
        checked_at: now()
      });
    }
    markProfileHandled(state, profile.profile_url);
    addTaskLog(state, keyword, evaluation.reason === 'no_email' ? 'skipped_no_email' : 'skipped_filter', `${profile.profile_url} | ${evaluation.message}`);
    return `已跳过 @${profile.username}：${evaluation.message}`;
  }

  const lead = buildLead(profile, keyword, source, currentUrl, title);
  const result = saveLead(state, lead);
  markProfileHandled(state, profile.profile_url);
  addTaskLog(state, keyword, result === 'inserted' ? 'lead_saved' : 'duplicate_updated', `${profile.username} | ${profile.email}`);

  return result === 'inserted'
    ? `已保存 @${profile.username}：${profile.email}`
    : `已更新重复线索 @${profile.username}：${profile.email}`;
}

function buildLead(profile, keyword, source, currentUrl, title) {
  const timestamp = now();
  return {
    id: uniqueId(),
    platform: 'TikTok',
    search_keyword: keyword,
    matched_keywords: [keyword],
    username: profile.username,
    nickname: profile.nickname || '',
    profile_url: profile.profile_url,
    bio: profile.bio || '',
    followers_raw: profile.followers_raw || '',
    followers_count: profile.followers_count,
    following_raw: profile.following_raw || '',
    likes_raw: profile.likes_raw || '',
    email: profile.email,
    emails_json: JSON.stringify(profile.emails || []),
    external_links: JSON.stringify(profile.external_links || []),
    source_video_url: source?.source_video_url || currentUrl,
    source_video_title: source?.source_video_title || title || '',
    source_video_description: source?.source_video_description || '',
    contact_source: 'visible_profile_text',
    lead_status: 'new',
    collected_at: timestamp,
    last_seen_at: timestamp,
    notes: ''
  };
}

function buildX9ProfileObservation(profile, keyword, source, currentUrl, title, evaluation) {
  const handle = normalizeUsername(profile?.username) || normalizeUsername(extractUsernameFromTikTokUrl(profile?.profile_url));
  if (!handle) {
    return null;
  }
  return {
    event_type: 'creator_observation',
    platform: 'tiktok',
    source: 'tiktok_creator_lead_browser_extension_1_0_19',
    worker_id: X9_WORKER_ID,
    account_id: X9_ACCOUNT_ID,
    search_keyword: keyword || null,
    creator: {
      handle,
      display_name: profile?.nickname || handle,
      profile_url: profile?.profile_url || `https://www.tiktok.com/@${encodeURIComponent(handle)}`,
      bio: profile?.bio || null,
      followers_raw: profile?.followers_raw || null,
      followers_count: Number.isFinite(profile?.followers_count) ? profile.followers_count : null,
      email: profile?.email || null,
      external_links: Array.isArray(profile?.external_links) ? profile.external_links : []
    },
    source_video: {
      video_url: source?.source_video_url || currentUrl || null,
      title: source?.source_video_title || title || null,
      description: source?.source_video_description || null,
      hashtags: []
    },
    lead_status: evaluation?.qualified ? 'qualified' : 'skipped',
    filter_reason: evaluation?.reason || '',
    filter_message: evaluation?.message || '',
    collected_at: now()
  };
}

function buildX9VideoObservation(video, keyword) {
  const handle = normalizeUsername(video?.creator_username)
    || normalizeUsername(extractUsernameFromTikTokUrl(video?.creator_profile_url));
  if (!handle) {
    return null;
  }
  return {
    event_type: 'creator_observation',
    platform: 'tiktok',
    source: 'tiktok_creator_lead_browser_extension_1_0_19',
    worker_id: X9_WORKER_ID,
    account_id: X9_ACCOUNT_ID,
    search_keyword: keyword || video?.search_keyword || null,
    creator: {
      handle,
      display_name: handle,
      profile_url: video?.creator_profile_url || `https://www.tiktok.com/@${encodeURIComponent(handle)}`,
      bio: null,
      followers_raw: null,
      followers_count: null,
      email: null,
      external_links: []
    },
    source_video: {
      video_url: video?.video_url || video?.source_video_url || null,
      title: video?.video_title || video?.source_video_title || null,
      description: video?.video_description || video?.source_video_description || null,
      hashtags: []
    },
    lead_status: 'source_video_seen',
    collected_at: video?.collected_at || now()
  };
}

async function sendX9ProfileObservation(profile, keyword, source, currentUrl, title, evaluation) {
  const payload = buildX9ProfileObservation(profile, keyword, source, currentUrl, title, evaluation);
  return postX9Observation(payload);
}

async function sendX9VideoObservation(video, keyword) {
  const payload = buildX9VideoObservation(video, keyword);
  return postX9Observation(payload);
}

async function postX9Observation(payload) {
  if (!payload?.creator?.handle) {
    return { ok: false, reason: 'missing_handle' };
  }
  try {
    const response = await fetch(X9_OBSERVATION_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const body = await response.json().catch(() => ({}));
    await chrome.storage.local.set({
      x9LastObservationUpload: {
        ok: response.ok,
        status: response.status,
        handle: payload.creator.handle,
        search_keyword: payload.search_keyword || '',
        action: body.action || '',
        uploaded_at: now()
      }
    }).catch(() => undefined);
    return { ok: response.ok, status: response.status, body };
  } catch (error) {
    await chrome.storage.local.set({
      x9LastObservationUpload: {
        ok: false,
        status: 0,
        handle: payload.creator.handle,
        search_keyword: payload.search_keyword || '',
        error: error instanceof Error ? error.message : String(error),
        uploaded_at: now()
      }
    }).catch(() => undefined);
    return { ok: false, error };
  }
}

let x9HeartbeatTimerId = null;

function startX9BackendHeartbeat() {
  if (x9HeartbeatTimerId) {
    return;
  }
  x9HeartbeatTimerId = window.setInterval(() => {
    postX9BackendHeartbeat('interval').catch(() => undefined);
  }, X9_HEARTBEAT_INTERVAL_MS);
}

async function postX9BackendHeartbeat(reason) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
  const url = tab?.url || '';
  const payload = {
    event_type: 'extension_heartbeat',
    extension_id: X9_EXTENSION_ID,
    extension_version: chrome.runtime.getManifest().version,
    worker_id: X9_WORKER_ID,
    account_id: X9_ACCOUNT_ID,
    browser_profile: 'chrome_default',
    current_url: url || null,
    page_type: classifyX9TikTokPage(url),
    tiktok_page_status: url.startsWith('https://www.tiktok.com/') ? 'on_tiktok' : 'off_tiktok',
    tiktok_login_status: 'unknown',
    active_tab_title: tab?.title || null,
    timestamp: new Date().toISOString(),
    reason
  };

  try {
    const response = await fetch(X9_HEARTBEAT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    await chrome.storage.local.set({
      x9LastHeartbeat: {
        ok: response.ok,
        status: response.status,
        at: now(),
        url
      }
    }).catch(() => undefined);
    return { ok: response.ok, status: response.status };
  } catch (error) {
    await chrome.storage.local.set({
      x9LastHeartbeat: {
        ok: false,
        status: 0,
        at: now(),
        error: error instanceof Error ? error.message : String(error)
      }
    }).catch(() => undefined);
    return { ok: false, error };
  }
}

function classifyX9TikTokPage(url) {
  if (!url || !url.startsWith('https://www.tiktok.com/')) {
    return 'unknown';
  }
  if (url.includes('/search')) {
    return 'search_results';
  }
  if (/\/@[^/]+\/video\//i.test(url)) {
    return 'video_page';
  }
  if (/\/@[^/?#]+/i.test(url)) {
    return 'creator_profile';
  }
  return 'unknown';
}

function saveLead(state, nextLead) {
  const existing = state.leads.find((lead) => lead.profile_url === nextLead.profile_url)
    || state.leads.find((lead) => lead.username === nextLead.username)
    || state.leads.find((lead) => lead.email === nextLead.email);

  if (!existing) {
    state.leads.push(nextLead);
    return 'inserted';
  }

  const sameEmailDifferentUsername = existing.email === nextLead.email && existing.username !== nextLead.username;
  existing.matched_keywords = mergeKeywords(existing.matched_keywords, nextLead.search_keyword);
  existing.last_seen_at = nextLead.last_seen_at;
  existing.nickname = nextLead.nickname || existing.nickname;
  existing.bio = nextLead.bio || existing.bio;
  existing.followers_raw = nextLead.followers_raw || existing.followers_raw;
  existing.followers_count = nextLead.followers_count ?? existing.followers_count;
  existing.following_raw = nextLead.following_raw || existing.following_raw;
  existing.likes_raw = nextLead.likes_raw || existing.likes_raw;
  existing.emails_json = mergeJsonArrays(existing.emails_json, nextLead.emails_json);
  existing.external_links = mergeJsonArrays(existing.external_links, nextLead.external_links);
  existing.source_video_url = nextLead.source_video_url || existing.source_video_url;
  existing.source_video_title = nextLead.source_video_title || existing.source_video_title;
  existing.source_video_description = nextLead.source_video_description || existing.source_video_description;

  if (sameEmailDifferentUsername) {
    existing.lead_status = 'needs_review';
    existing.notes = appendNote(existing.notes, 'same email found for different username');
  }

  return 'updated';
}

function findSourceForProfile(state, profileUrl, keyword) {
  return state.pendingProfiles.find((item) => item.profile_url === profileUrl && item.search_keyword === keyword)
    || state.pendingProfiles.find((item) => item.profile_url === profileUrl)
    || null;
}

function getNextPendingProfile(state) {
  return state.pendingProfiles.find((item) => !item.handled && !isProfileAlreadyHandled(state, item.profile_url, item.creator_username))
    || null;
}

function isProfileAlreadyHandled(state, profileUrl, username) {
  return state.leads.some((lead) => lead.profile_url === profileUrl || lead.username === username)
    || state.skippedProfiles.some((item) => item.profile_url === profileUrl || item.username === username);
}

function markProfileHandled(state, profileUrl) {
  for (const item of state.pendingProfiles) {
    if (item.profile_url === profileUrl) {
      item.handled = true;
    }
  }
}

function pruneHandledQueue(state) {
  for (const item of state.pendingProfiles) {
    if (isProfileAlreadyHandled(state, item.profile_url, item.creator_username)) {
      item.handled = true;
    }
  }
}

function resolveKeyword(state, pageData) {
  const keyword = resolveWorkflowKeyword(state, pageData, pageData?.url || '') || 'manual-current-page';
  state.settings.currentKeyword = keyword;
  elements.keywordInput.value = keyword;
  return keyword;
}

function resolveWorkflowKeyword(state, pageData, activeUrl = '') {
  const pageUrl = pageData?.url || activeUrl || '';
  const pageKeyword = pageData?.inferredSearchKeyword || inferSearchKeywordFromUrl(pageUrl);
  if (pageKeyword) {
    return pageKeyword.trim();
  }

  const activeKeyword = inferSearchKeywordFromUrl(activeUrl);
  if (activeKeyword) {
    return activeKeyword.trim();
  }

  return elements.keywordInput.value.trim() || state.settings.currentKeyword || '';
}

async function getActiveTikTokTab(errorMessage) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error(errorMessage || '请先打开 TikTok 页面。');
  }

  return tab;
}

async function openProfileTabForCollection(profileUrl, openerTabId) {
  const openerTab = openerTabId ? await chrome.tabs.get(openerTabId).catch(() => null) : null;
  const [activeTab] = openerTab ? [] : await chrome.tabs.query({ active: true, currentWindow: true });
  const baseTab = openerTab || activeTab || null;
  const windowId = baseTab?.windowId;
  const index = typeof baseTab?.index === 'number' ? baseTab.index + 1 : undefined;

  const tab = await chrome.tabs.create({
    url: profileUrl,
    active: true,
    ...(windowId ? { windowId } : {}),
    ...(typeof index === 'number' ? { index } : {})
  });

  if (!tab?.id) {
    throw new Error('无法打开创作者主页新标签。');
  }

  return tab;
}

async function closeProfileTabAfterCollection(profileTab, expectedProfileUrl, openerTabId) {
  const tabId = typeof profileTab === 'number' ? profileTab : profileTab?.id;
  if (!tabId || tabId === openerTabId) {
    return false;
  }

  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id) {
    return false;
  }

  const tabUrl = tab.url || '';
  const expectedUsername = normalizeUsername(extractUsernameFromTikTokUrl(expectedProfileUrl));
  const tabUsername = normalizeUsername(extractUsernameFromTikTokUrl(tabUrl));
  const isExpectedProfile = expectedUsername && tabUsername === expectedUsername;
  const isProfilePage = /https:\/\/www\.tiktok\.com\/@[^/?#]+/i.test(tabUrl)
    && !/\/video\/\d+/i.test(tabUrl)
    && !/\/search(?:\/video)?\b/i.test(tabUrl);

  if (!isExpectedProfile || !isProfilePage) {
    return false;
  }

  await chrome.tabs.remove(tab.id);
  return true;
}

async function activateTabIfExists(tabId) {
  if (!tabId) {
    return;
  }

  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id) {
    return;
  }

  await chrome.tabs.update(tab.id, { active: true }).catch(() => undefined);
  if (tab.windowId && chrome.windows?.update) {
    await chrome.windows.update(tab.windowId, { focused: true }).catch(() => undefined);
  }
}

function render(state, message) {
  const emailLeads = state.leads.filter((lead) => lead.email);
  const pendingProfiles = state.pendingProfiles.filter((item) => !item.handled && !isProfileAlreadyHandled(state, item.profile_url, item.creator_username));
  elements.leadCount.textContent = String(emailLeads.length);
  elements.pendingCount.textContent = String(pendingProfiles.length);
  elements.skippedCount.textContent = String(state.skippedProfiles.length);
  elements.status.textContent = message || t('status.default');
  renderTimer(state);
  renderQueueList(pendingProfiles);
  renderLeadList(emailLeads);
  updateBadge(emailLeads.length);
}

function renderTimer(state) {
  if (!elements.runTimer || !elements.runTimerMeta) {
    return;
  }

  const timer = normalizeRunTimer(state?.runTimer);
  const elapsedMs = timer.running && timer.started_ms
    ? Math.max(0, Date.now() - timer.started_ms)
    : timer.elapsed_ms;
  elements.runTimer.textContent = formatDuration(elapsedMs);

  if (timer.running) {
    elements.runTimerMeta.textContent = timer.started_at ? `${t('timer.running')} · ${timer.started_at}` : t('timer.running');
    return;
  }

  elements.runTimerMeta.textContent = timer.ended_at
    ? `${t('timer.ended')} · ${timer.ended_at}`
    : t('timer.notStarted');
}

function startRunTimer(state) {
  const startedMs = Date.now();
  state.runTimer = {
    running: true,
    started_at: now(),
    started_ms: startedMs,
    ended_at: '',
    elapsed_ms: 0
  };
}

function finishRunTimer(state) {
  const timer = normalizeRunTimer(state.runTimer);
  const elapsedMs = timer.running && timer.started_ms
    ? Math.max(0, Date.now() - timer.started_ms)
    : timer.elapsed_ms;
  state.runTimer = {
    ...timer,
    running: false,
    ended_at: now(),
    elapsed_ms: elapsedMs
  };
  return elapsedMs;
}

function startRunTimerTicker() {
  stopRunTimerTicker();
  runTimerIntervalId = window.setInterval(async () => {
    const state = await getState().catch(() => null);
    if (!state) {
      return;
    }
    renderTimer(state);
    if (!state.runTimer.running) {
      stopRunTimerTicker();
    }
  }, 1000);
}

function stopRunTimerTicker() {
  if (runTimerIntervalId) {
    window.clearInterval(runTimerIntervalId);
    runTimerIntervalId = null;
  }
}

function renderQueueList(pendingProfiles) {
  elements.queueList.replaceChildren();
  if (pendingProfiles.length === 0) {
    elements.queueList.appendChild(createListItem(t('queue.empty'), t('queue.emptyMeta'), true));
    return;
  }

  for (const item of pendingProfiles.slice(0, 4)) {
    elements.queueList.appendChild(createListItem(`@${item.creator_username}`, item.search_keyword));
  }
}

function renderLeadList(emailLeads) {
  elements.leadList.replaceChildren();
  if (emailLeads.length === 0) {
    elements.leadList.appendChild(createListItem(t('leads.empty'), t('leads.emptyMeta'), true));
    return;
  }

  const recent = [...emailLeads].sort((a, b) => String(b.last_seen_at).localeCompare(String(a.last_seen_at))).slice(0, 4);
  for (const lead of recent) {
    elements.leadList.appendChild(createListItem(`@${lead.username}`, lead.email));
  }
}

function createListItem(title, meta, empty = false) {
  const item = document.createElement('li');
  if (empty) {
    item.className = 'empty';
  }

  const titleElement = document.createElement('span');
  titleElement.className = 'item-title';
  titleElement.textContent = title;
  item.appendChild(titleElement);

  const metaElement = document.createElement('span');
  metaElement.className = 'item-meta';
  metaElement.textContent = meta;
  item.appendChild(metaElement);

  return item;
}

async function updateBadge(count) {
  const text = count > 0 ? String(Math.min(count, 999)) : '';
  await chrome.action.setBadgeText({ text }).catch(() => undefined);
  await chrome.action.setBadgeBackgroundColor({ color: '#202a36' }).catch(() => undefined);
}

async function getState() {
  const result = await chrome.storage.local.get([STORAGE_KEY]);
  return normalizeState(result[STORAGE_KEY]);
}

async function setState(state) {
  await chrome.storage.local.set({ [STORAGE_KEY]: normalizeState(state) });
}

function normalizeState(state) {
  const next = state && typeof state === 'object' ? state : createEmptyState();
  next.leads = Array.isArray(next.leads) ? next.leads : [];
  next.sourceVideos = Array.isArray(next.sourceVideos) ? next.sourceVideos : [];
  next.sourceVideos = next.sourceVideos.map((video) => ({
    ...video,
    handled: Boolean(video.handled)
  }));
  next.skippedProfiles = Array.isArray(next.skippedProfiles) ? next.skippedProfiles : [];
  next.taskLogs = Array.isArray(next.taskLogs) ? next.taskLogs : [];
  next.pendingProfiles = Array.isArray(next.pendingProfiles) ? next.pendingProfiles : [];
  next.runTimer = normalizeRunTimer(next.runTimer);
  next.settings = next.settings && typeof next.settings === 'object' ? next.settings : { currentKeyword: '' };
  next.settings.autoSettings = normalizeAutoSettings(next.settings.autoSettings);
  next.settings.leadFilters = normalizeLeadFilters(next.settings.leadFilters);
  next.settings.language = normalizeLanguage(next.settings.language || DEFAULT_LANGUAGE);
  next.settings.autoStopRequested = Boolean(next.settings.autoStopRequested);
  return next;
}

function normalizeRunTimer(timer) {
  const source = timer && typeof timer === 'object' ? timer : {};
  const startedMs = Number(source.started_ms) || 0;
  const elapsedMs = Number(source.elapsed_ms) || 0;
  return {
    running: Boolean(source.running && startedMs),
    started_at: String(source.started_at || ''),
    started_ms: startedMs,
    ended_at: String(source.ended_at || ''),
    elapsed_ms: Math.max(0, elapsedMs)
  };
}

function createEmptyRunTimer() {
  return {
    running: false,
    started_at: '',
    started_ms: 0,
    ended_at: '',
    elapsed_ms: 0
  };
}

function createEmptyState() {
  return {
    leads: [],
    sourceVideos: [],
    skippedProfiles: [],
    taskLogs: [],
    pendingProfiles: [],
    runTimer: createEmptyRunTimer(),
    settings: {
      currentKeyword: '',
      autoSettings: { ...FAST_AUTO_SETTINGS },
      leadFilters: {
        requireEmail: true,
        minFollowers: 1000
      },
      speedProfileVersion: FAST_SPEED_PROFILE_VERSION,
      language: DEFAULT_LANGUAGE,
      autoStopRequested: false
    }
  };
}

function addTaskLog(state, keyword, eventType, message) {
  state.taskLogs.push({
    id: uniqueId(),
    task_keyword: keyword,
    event_type: eventType,
    message,
    created_at: now()
  });
}

function buildCsv(rows) {
  const header = EXPORT_FIELDS.join(',');
  const body = rows.map((row) => EXPORT_FIELDS.map((field) => escapeCsv(formatExportValue(row[field]))).join(','));
  return [header, ...body].join('\r\n');
}

async function exportLeadsToExcel(state, options = {}) {
  const rows = state.leads.filter((lead) => lead.email);
  const suffix = options.filenameSuffix ? `-${safeFilenamePart(options.filenameSuffix)}` : '';
  const filename = `tiktok-leads-${dateStamp()}${suffix}.xls`;
  await downloadText(
    buildExcelHtml(rows),
    filename,
    'application/vnd.ms-excel',
    { saveAs: options.saveAs !== false }
  );
  return {
    filename,
    count: rows.length
  };
}

function buildExcelHtml(rows) {
  const headerCells = EXPORT_FIELDS
    .map((field) => `<th>${escapeHtml(field)}</th>`)
    .join('');
  const bodyRows = rows
    .map((row) => {
      const cells = EXPORT_FIELDS
        .map((field) => `<td>${escapeHtml(formatExportValue(row[field]))}</td>`)
        .join('');
      return `<tr>${cells}</tr>`;
    })
    .join('');

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    table { border-collapse: collapse; }
    th, td { border: 1px solid #999; padding: 4px 6px; mso-number-format:"\\@"; }
    th { background: #eef2f6; font-weight: 700; }
  </style>
</head>
<body>
  <table>
    <thead><tr>${headerCells}</tr></thead>
    <tbody>${bodyRows}</tbody>
  </table>
</body>
</html>`;
}

function formatExportValue(value) {
  if (Array.isArray(value)) {
    return JSON.stringify(value);
  }
  if (value === null || value === undefined) {
    return '';
  }
  return String(value);
}

function escapeCsv(value) {
  const text = String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeFilenamePart(value) {
  return String(value || '')
    .trim()
    .replace(/[^a-z0-9_-]+/gi, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80);
}

async function downloadText(text, filename, mimeType, options = {}) {
  const blob = new Blob([text], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const downloadId = await chrome.downloads.download({
    url,
    filename,
    saveAs: options.saveAs !== false
  });
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
  return downloadId;
}

function mergeKeywords(existing, nextKeyword) {
  const values = Array.isArray(existing) ? existing : [];
  return Array.from(new Set([...values, nextKeyword].map((item) => String(item || '').trim()).filter(Boolean)));
}

function mergeJsonArrays(firstRaw, secondRaw) {
  const first = parseJsonArray(firstRaw);
  const second = parseJsonArray(secondRaw);
  return JSON.stringify(Array.from(new Set([...first, ...second])));
}

function parseJsonArray(raw) {
  try {
    const parsed = JSON.parse(raw || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function appendNote(existing, note) {
  const current = String(existing || '').trim();
  if (!current) {
    return note;
  }
  return current.includes(note) ? current : `${current}; ${note}`;
}

function uniqueId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.max(0, Math.floor((Number(milliseconds) || 0) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (value) => String(value).padStart(2, '0');
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function now() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function dateStamp() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

async function closeVideoViewInCurrentPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先打开 TikTok 视频页再关闭。');
  }

  return closeVideoViewInTab(tab.id);
}

async function closeVideoViewInTab(tabId) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    throw new Error('请先打开 TikTok 视频页再关闭。');
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, { type: 'TCLAB_CLOSE_VIDEO_VIEW' });
  if (!response?.ok) {
    throw new Error(response?.error || '无法关闭当前视频。');
  }

  return response.data;
}

async function waitForSearchResultsInCurrentPage(timeoutMs = 4_000) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    return null;
  }

  return waitForSearchResultsInTab(tab.id, timeoutMs);
}

async function waitForSearchResultsInTab(tabId, timeoutMs = 4_000) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id || !tab.url || !tab.url.includes('tiktok.com')) {
    return null;
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['contentScript.js']
  }).catch(() => undefined);

  const response = await chrome.tabs.sendMessage(tab.id, {
    type: 'TCLAB_WAIT_SEARCH_RESULTS',
    timeoutMs
  });

  if (!response?.ok) {
    return null;
  }

  return response.data;
}

async function clickVideoCloseButtonOnce(preferredTabId = null) {
  const targetTab = preferredTabId ? await chrome.tabs.get(preferredTabId).catch(() => null) : null;
  const tabId = targetTab?.id || null;
  if (tabId) {
    await activateTabIfExists(tabId);
  }

  const pageData = tabId
    ? await collectTikTokPageFromTab(tabId).catch(() => null)
    : await collectActiveTikTokPage().catch(() => null);

  if (isSearchResultsWorkflowPage(pageData)) {
    return {
      ok: true,
      method: 'already_on_search_results',
      attempts: 0,
      searchResultsFound: true,
      searchResultCardCount: Array.isArray(pageData?.videos) ? pageData.videos.length : 0
    };
  }

  if (pageData && isTikTokSearchPageUrl(pageData.url) && !pageData.isVideoPage) {
    await clickVideoTabInCurrentPage();
    const searchResultWait = await waitForSearchResultsInCurrentPage().catch(() => null);
    return {
      ok: true,
      method: 'search_page_click_video_tab_instead_of_close',
      attempts: 0,
      searchResultsFound: Boolean(searchResultWait?.found),
      searchResultCardCount: searchResultWait?.count || 0
    };
  }

  if (pageData && !pageData.isVideoPage && !isSearchOriginVideoPage(pageData)) {
    throw new Error('当前页面不是视频播放页，不能点击视频关闭按钮。');
  }

  const closeResult = tabId
    ? await closeVideoViewInTab(tabId)
    : await closeVideoViewInCurrentPage();
  const searchResultWait = tabId
    ? await waitForSearchResultsInTab(tabId).catch(() => null)
    : await waitForSearchResultsInCurrentPage().catch(() => null);

  return {
    ok: true,
    method: closeResult?.method || 'click_browse_close_once',
    attempts: 1,
    searchResultsFound: Boolean(searchResultWait?.found),
    searchResultCardCount: searchResultWait?.count || 0
  };
}
