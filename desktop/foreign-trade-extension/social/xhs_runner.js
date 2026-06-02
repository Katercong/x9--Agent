(() => {
  const TAG = "[XHS-RUNNER]";
  const MSG = {
    START: "XHS_START",
    STOP: "XHS_STOP",
    GET_STATE: "XHS_GET_STATE",
    RESET: "XHS_RESET",
    CS_START: "XHS_CS_START",
    CS_STOP: "XHS_CS_STOP",
    PROGRESS: "XHS_PROGRESS",
    NOTE_DONE: "XHS_NOTE_DONE",
    DONE: "XHS_DONE",
    ERROR: "XHS_ERROR",
    EXPECT_PROFILE: "XHS_EXPECT_PROFILE",
    WAIT_PROFILE: "XHS_WAIT_PROFILE",
    PROFILE_RESULT: "XHS_PROFILE_RESULT"
  };
  const RESULT_STORAGE_KEY = "x9_xhs_last_result";
  const INGEST_ENDPOINT_KEY = "x9_xhs_ingest_endpoint";
  const INGEST_UPLOAD_STORAGE_KEY = "x9_xhs_last_ingest_upload";
  const DEFAULT_INGEST_ENDPOINT = "https://usx9.us/api/xhs/ingest";

  const DEFAULT_STATE = {
    status: "idle",
    phase: "idle",
    message: "等待开始",
    runId: null,
    listTabId: null,
    startedAt: null,
    finishedAt: null,
    settings: {},
    notes: [],
    comments: [],
    users: {},
    logs: [],
    sample: {},
    ingestUpload: null
  };

  let state = Object.assign({}, DEFAULT_STATE);
  const profileWaiters = new Map();
  const profileRequests = new Map();

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || typeof message.type !== "string") return false;
    if (message.type === MSG.START) {
      handleStart(message.settings || {}).then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.STOP) {
      handleStop().then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.GET_STATE) {
      sendResponse({ ok: true, state: publicState() });
      return true;
    }
    if (message.type === MSG.RESET) {
      handleReset().then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.PROGRESS) {
      patch({ phase: message.phase || state.phase, message: message.message || state.message });
      log(message.message || message.phase || "progress");
      sendResponse({ ok: true });
      return true;
    }
    if (message.type === MSG.NOTE_DONE) {
      mergeNotePayload(message);
      persistSnapshot(false, false).catch((e) => console.warn(TAG, "persist failed", e));
      sendResponse({ ok: true });
      return true;
    }
    if (message.type === MSG.DONE) {
      patch({ status: "running", phase: "upload", finishedAt: new Date().toISOString(), message: "上传中" });
      log("done");
      cleanupAllProfileTabs().then(() => persistSnapshot(false, true)).then((uploadInfo) => {
        if (uploadInfo && uploadInfo.ok === false) {
          patch({ status: "error", phase: "upload", message: `上传失败：${uploadInfo.error || "unknown_error"}` });
        } else {
          patch({ status: "done", phase: "upload", message: "上传成功" });
        }
        chrome.storage.local.set({ [RESULT_STORAGE_KEY]: exportSnapshot() }).catch(() => undefined);
        sendResponse({ ok: true, upload: uploadInfo || null });
      }).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.ERROR) {
      patch({ status: "error", phase: "idle", finishedAt: new Date().toISOString(), message: message.error || "采集失败" });
      log("error: " + (message.error || "unknown"));
      cleanupAllProfileTabs().then(() => persistSnapshot(false, false)).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.EXPECT_PROFILE) {
      expectProfile(message);
      sendResponse({ ok: true });
      return true;
    }
    if (message.type === MSG.WAIT_PROFILE) {
      waitProfile(message).then(sendResponse);
      return true;
    }
    if (message.type === MSG.PROFILE_RESULT) {
      handleProfileResult(message, sender).then(sendResponse);
      return true;
    }
    return false;
  });

  async function handleReset() {
    if (state.listTabId) {
      try { await chrome.tabs.sendMessage(state.listTabId, { type: MSG.CS_STOP }); } catch (_) {}
    }
    for (const waiter of profileWaiters.values()) {
      try { waiter.resolve({ ok: false, error: "reset" }); } catch (_) {}
      clearTimeout(waiter.timer);
      if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
    }
    await cleanupAllProfileTabs();
    state = Object.assign({}, DEFAULT_STATE, { users: {}, notes: [], comments: [], logs: [], sample: {}, ingestUpload: null });
    await chrome.storage.local.remove([RESULT_STORAGE_KEY, INGEST_UPLOAD_STORAGE_KEY]).catch(() => undefined);
    return { ok: true, state: publicState() };
  }

  async function handleStart(settings) {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab || !activeTab.id) return { ok: false, error: "no_active_tab" };
    if (!/xiaohongshu\.com/i.test(activeTab.url || "")) {
      return { ok: false, error: "active_tab_is_not_xiaohongshu", url: activeTab.url || "" };
    }
    const runId = "xhs-" + new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
    state = Object.assign({}, DEFAULT_STATE, {
      status: "running",
      phase: "notes",
      message: "启动小红书严格步骤采集",
      runId,
      listTabId: activeTab.id,
      startedAt: new Date().toISOString(),
      settings: normalizeSettings(settings),
      notes: [],
      comments: [],
      users: {},
      logs: [],
      sample: {},
      ingestUpload: null
    });
    await chrome.storage.local.remove([INGEST_UPLOAD_STORAGE_KEY]).catch(() => undefined);
    log("start " + runId);
    await cleanupProfileTabsForList(activeTab.id);
    await ensureInjected(activeTab.id);
    try {
      await chrome.tabs.sendMessage(activeTab.id, { type: MSG.CS_START, runId, settings: state.settings });
    } catch (err) {
      await ensureInjected(activeTab.id);
      await chrome.tabs.sendMessage(activeTab.id, { type: MSG.CS_START, runId, settings: state.settings });
    }
    return { ok: true, runId };
  }

  async function handleStop() {
    patch({ status: "paused", phase: "idle", finishedAt: new Date().toISOString(), message: "已停止" });
    if (state.listTabId) {
      try { await chrome.tabs.sendMessage(state.listTabId, { type: MSG.CS_STOP }); } catch (_) {}
    }
    for (const waiter of profileWaiters.values()) {
      try { waiter.resolve({ ok: false, error: "stopped" }); } catch (_) {}
      clearTimeout(waiter.timer);
      if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
    }
    await cleanupAllProfileTabs();
    return { ok: true };
  }

  async function ensureInjected(tabId) {
    try {
      await chrome.tabs.sendMessage(tabId, { type: "XHS_PING" });
      return;
    } catch (_) {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["social/xhs_content.js"] });
    }
  }

  function normalizeSettings(input) {
    return {
      keyword: String(input.keyword || "").trim(),
      maxNotes: clamp(input.maxNotes, 1, 200, 10),
      historyLimit: 10,
      profileLimit: clamp(input.profileLimit, 1, 300, 20)
    };
  }

  function mergeNotePayload(message) {
    if (!state.settings.keyword && message.note && message.note.keyword) {
      state.settings = Object.assign({}, state.settings, { keyword: String(message.note.keyword || "").trim() });
    }
    if (message.note) mergeNote(message.note);
    for (const c of message.comments || []) mergeComment(c);
    for (const u of message.users || []) mergeUser(u);
    state.sample = {
      note: state.notes[0] || null,
      comment: state.comments[0] || null,
      user: Object.values(state.users)[0] || null
    };
    patch({ phase: "comments", message: `已采集笔记 ${state.notes.length}，评论 ${state.comments.length}，用户 ${Object.keys(state.users).length}` });
  }

  function mergeNote(note) {
    const key = note.note_id || note.url || note.search_result_url;
    const index = state.notes.findIndex((item) => (item.note_id || item.url || item.search_result_url) === key);
    if (index >= 0) state.notes[index] = Object.assign({}, state.notes[index], note);
    else state.notes.push(note);
  }

  function mergeComment(comment) {
    const key = comment.comment_id || `${comment.note_id || ""}:${comment.content || ""}:${comment.published_at_text || ""}`;
    const index = state.comments.findIndex((item) => (item.comment_id || `${item.note_id || ""}:${item.content || ""}:${item.published_at_text || ""}`) === key);
    if (index >= 0) state.comments[index] = Object.assign({}, state.comments[index], comment);
    else state.comments.push(comment);
  }

  function expectProfile(message) {
    const key = profileKey(message.user || {}, message.profileUrl);
    if (!key) return;
    const existing = state.users[key] || {};
    state.users[key] = Object.assign({}, existing, message.user || {}, {
      profile_url: message.profileUrl || existing.profile_url || "",
      profile_pending: true
    });
    const requestId = message.requestId || key;
    profileRequests.set(requestId, {
      requestId,
      key,
      profileUrl: message.profileUrl || state.users[key].profile_url || "",
      user: state.users[key],
      sourceType: message.sourceType || "",
      requestedAt: Date.now(),
      tabId: null
    });
    patch({ phase: "profiles", message: "打开用户主页新标签：" + (state.users[key].username || key) });
  }

  function waitProfile(message) {
    const key = profileKey(message.user || {}, message.profileUrl);
    if (!key) return Promise.resolve({ ok: false, error: "missing_profile_key" });
    const existing = state.users[key];
    if (existing && existing.profile_collected_at) return Promise.resolve({ ok: true, user: existing });
    return new Promise((resolve) => {
      const timeoutMs = clamp(message.timeoutMs, 3000, 60000, 20000);
      const requestId = message.requestId || key;
      const request = profileRequests.get(requestId) || {
        requestId,
        key,
        profileUrl: message.profileUrl || "",
        user: message.user || {},
        tabId: null
      };
      const waiter = {
        requestId,
        key,
        profileUrl: request.profileUrl || message.profileUrl || "",
        user: request.user || message.user || {},
        tabId: request.tabId || null,
        resolve,
        timer: null,
        pollTimer: null
      };
      const timer = setTimeout(() => {
        profileWaiters.delete(key);
        if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
        if (state.users[key]) state.users[key].profile_pending = false;
        cleanupProfileTabs(waiter).finally(() => {
          resolve({ ok: false, error: "profile_timeout", user: state.users[key] || null });
        });
      }, timeoutMs);
      waiter.timer = timer;
      profileWaiters.set(key, waiter);
      trackProfileTab(waiter);
    });
  }

  async function handleProfileResult(message, sender) {
    const user = message.user || {};
    const key = profileKey(user, user.profile_url || message.profileUrl);
    if (state.status !== "running" && (!key || !profileWaiters.has(key))) {
      return { ok: true, ignored: true };
    }
    let shouldClose = false;
    if (key) {
      mergeUser(Object.assign({}, user, { profile_collected_at: user.profile_collected_at || new Date().toISOString() }));
      const waiter = profileWaiters.get(key);
      if (waiter) {
        if (sender && sender.tab && sender.tab.id) waiter.tabId = sender.tab.id;
        clearTimeout(waiter.timer);
        if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
        profileWaiters.delete(key);
        profileRequests.delete(waiter.requestId);
        waiter.resolve({ ok: true, user: state.users[key] });
        shouldClose = true;
      }
      if (state.users[key] && state.users[key].profile_pending) shouldClose = true;
      if (state.users[key]) state.users[key].profile_pending = false;
    }
    if (shouldClose && sender && sender.tab && sender.tab.id && sender.tab.id !== state.listTabId) {
      const waiter = { tabId: sender.tab.id, key, profileUrl: user.profile_url || message.profileUrl || "", user };
      setTimeout(() => cleanupProfileTabs(waiter).catch(() => undefined), 500);
    }
    persistSnapshot(false).catch((e) => console.warn(TAG, "persist failed", e));
    return { ok: true };
  }

  function mergeUser(user) {
    const key = profileKey(user, user.profile_url);
    if (!key) return;
    const prev = state.users[key] || {};
    state.users[key] = Object.assign({}, prev, user, {
      sources: mergeSources(prev.sources, user.sources)
    });
    state.sample.user = state.sample.user || state.users[key];
  }

  function mergeSources(a, b) {
    const out = [];
    const seen = new Set();
    for (const item of [].concat(a || [], b || [])) {
      const sig = JSON.stringify(item || {});
      if (seen.has(sig)) continue;
      seen.add(sig);
      out.push(item);
    }
    return out;
  }

  function trackProfileTab(waiter) {
    let attempts = 0;
    const tick = async () => {
      if (!profileWaiters.has(waiter.key)) return;
      attempts += 1;
      try {
        const tab = await findMatchingProfileTab(waiter);
        if (tab && tab.id) {
          waiter.tabId = tab.id;
          const request = profileRequests.get(waiter.requestId);
          if (request) request.tabId = tab.id;
          if (tab.status === "complete") await ensureInjected(tab.id).catch(() => undefined);
        }
      } catch (_) {}
      if (attempts < 90 && profileWaiters.has(waiter.key)) {
        waiter.pollTimer = setTimeout(tick, 250);
      }
    };
    tick();
  }

  async function findMatchingProfileTab(waiter) {
    const tabs = await chrome.tabs.query({});
    return tabs.find((tab) => tabMatchesProfileWaiter(tab, waiter) && tab.id !== state.listTabId && (tab.openerTabId === state.listTabId || tab.id === waiter.tabId)) ||
      tabs.find((tab) => tabMatchesProfileWaiter(tab, waiter) && tab.id !== state.listTabId) ||
      null;
  }

  function tabMatchesProfileWaiter(tab, waiter) {
    const url = String(tab && (tab.pendingUrl || tab.url) || "");
    if (!/xiaohongshu\.com\/user\/profile\//i.test(url)) return false;
    const expectedId = profileKey(waiter.user || {}, waiter.profileUrl);
    const actualId = profileKey({}, url);
    if (expectedId && actualId && expectedId === actualId) return true;
    return canonicalProfileUrl(url) === canonicalProfileUrl(waiter.profileUrl);
  }

  async function cleanupProfileTabs(waiter) {
    const ids = new Set();
    if (waiter && waiter.tabId && waiter.tabId !== state.listTabId) ids.add(waiter.tabId);
    const tabs = await chrome.tabs.query({}).catch(() => []);
    for (const tab of tabs) {
      if (!tab || !tab.id || tab.id === state.listTabId) continue;
      if (!tabMatchesProfileWaiter(tab, waiter || {})) continue;
      if (tab.id === waiter.tabId || tab.openerTabId === state.listTabId) ids.add(tab.id);
    }
    await Promise.all(Array.from(ids).map((id) => chrome.tabs.remove(id).catch(() => undefined)));
  }

  async function cleanupAllProfileTabs() {
    const waiters = Array.from(new Set(profileWaiters.values()));
    for (const waiter of waiters) {
      clearTimeout(waiter.timer);
      if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
      await cleanupProfileTabs(waiter);
    }
    profileWaiters.clear();
    profileRequests.clear();
    if (state.listTabId) await cleanupProfileTabsForList(state.listTabId);
  }

  async function cleanupProfileTabsForList(listTabId) {
    const tabs = await chrome.tabs.query({}).catch(() => []);
    const ids = tabs
      .filter((tab) => tab && tab.id && tab.id !== listTabId && tab.openerTabId === listTabId)
      .filter((tab) => /xiaohongshu\.com\/user\/profile\//i.test(String(tab.pendingUrl || tab.url || "")))
      .map((tab) => tab.id);
    await Promise.all(ids.map((id) => chrome.tabs.remove(id).catch(() => undefined)));
  }

  function exportSnapshot() {
    const users = Object.values(state.users || {});
    const replies = state.comments.filter((c) => Number(c.depth || 0) > 0).length;
    return {
      status: state.status,
      phase: state.phase,
      message: state.message,
      run_id: state.runId,
      started_at: state.startedAt,
      finished_at: state.finishedAt,
      settings: state.settings || {},
      counts: {
        notes: state.notes.length,
        comments: state.comments.length,
        replies,
        users: users.length,
        profiles: users.filter((u) => u.profile_collected_at).length
      },
      notes: state.notes || [],
      comments: state.comments || [],
      users,
      logs: state.logs || [],
      exported_at: new Date().toISOString()
    };
  }

  async function persistSnapshot(download, upload) {
    const snapshot = exportSnapshot();
    await chrome.storage.local.set({ [RESULT_STORAGE_KEY]: snapshot });
    let uploadInfo = null;
    if (upload) uploadInfo = await uploadSnapshot(snapshot);
    if (!download) return uploadInfo;
    const json = JSON.stringify(snapshot, null, 2);
    const filename = `xhs_collect_${snapshot.run_id || Date.now()}.json`;
    const url = "data:application/json;charset=utf-8," + encodeURIComponent(json);
    await chrome.downloads.download({ url, filename, saveAs: false, conflictAction: "overwrite" });
    return uploadInfo;
  }

  async function uploadSnapshot(snapshot) {
    const stored = await chrome.storage.local.get([INGEST_ENDPOINT_KEY]).catch(() => ({}));
    const endpoint = normalizeIngestEndpoint(stored[INGEST_ENDPOINT_KEY]);
    if (!endpoint) return null;
    const uploading = {
      ok: null,
      endpoint,
      run_id: snapshot.run_id || state.runId || null,
      at: new Date().toISOString()
    };
    patch({ ingestUpload: uploading });
    await chrome.storage.local.set({ [INGEST_UPLOAD_STORAGE_KEY]: uploading }).catch(() => undefined);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(snapshot)
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        throw new Error(`upload_failed_${response.status}: ${detail.slice(0, 200)}`);
      }
      const result = await response.json().catch(() => ({}));
      clearFinishedQueueAfterUpload();
      const uploadInfo = {
        ok: true,
        endpoint,
        run_id: snapshot.run_id || state.runId || null,
        at: new Date().toISOString(),
        stats: result.stats || result.counts || null,
        queue_cleanup: result.queue_cleanup || null
      };
      patch({ ingestUpload: uploadInfo });
      await chrome.storage.local.set({ [INGEST_UPLOAD_STORAGE_KEY]: uploadInfo });
      log("已上传清洗接口");
      return uploadInfo;
    } catch (error) {
      const uploadInfo = {
        ok: false,
        endpoint,
        run_id: snapshot.run_id || state.runId || null,
        at: new Date().toISOString(),
        error: errText(error)
      };
      patch({ ingestUpload: uploadInfo });
      await chrome.storage.local.set({ [INGEST_UPLOAD_STORAGE_KEY]: uploadInfo }).catch(() => undefined);
      console.warn(TAG, "ingest upload failed", error);
      return uploadInfo;
    }
  }

  function publicState() {
    const users = Object.values(state.users || {});
    const profiles = users.filter((u) => u.profile_collected_at).length;
    const replies = state.comments.filter((c) => Number(c.depth || 0) > 0).length;
    return Object.assign({}, state, {
      counts: {
        notes: state.notes.length,
        comments: state.comments.length,
        replies,
        users: users.length,
        profiles
      },
      sample: {
        note: state.notes[0] || null,
        comment: state.comments[0] || null,
        user: users[0] || null
      }
    });
  }

  function normalizeIngestEndpoint(value) {
    const raw = String(value || "").trim();
    if (!raw || /127\.0\.0\.1:18766|localhost:18766/i.test(raw)) return DEFAULT_INGEST_ENDPOINT;
    try {
      const url = new URL(raw);
      if (url.protocol === "https:" && (url.hostname === "usx9.us" || url.hostname.endsWith(".usx9.us"))) {
        return raw;
      }
      if (/^(127\.0\.0\.1|localhost)$/.test(url.hostname) && url.port === "8000") {
        return raw;
      }
    } catch (_) {}
    return DEFAULT_INGEST_ENDPOINT;
  }

  function patch(values) {
    state = Object.assign({}, state, values || {});
  }

  function clearFinishedQueueAfterUpload() {
    for (const user of Object.values(state.users || {})) {
      if (user) user.profile_pending = false;
    }
    profileWaiters.clear();
    profileRequests.clear();
  }

  function log(text) {
    const value = String(text || "").trim();
    if (!value) return;
    state.logs = (state.logs || []).concat(`[${new Date().toLocaleTimeString()}] ${value}`).slice(-120);
    console.log(TAG, value);
  }

  function profileKey(user, profileUrl) {
    const url = String(profileUrl || user.profile_url || "");
    const m = url.match(/\/user\/profile\/([^/?#]+)/);
    return user.user_id || (m && m[1]) || user.username || url;
  }

  function canonicalProfileUrl(url) {
    return String(url || "").split("#")[0].split("?")[0].replace(/\/$/, "");
  }

  function clamp(value, min, max, fallback) {
    const n = parseInt(value, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function errText(error) {
    return String(error && error.message || error || "unknown_error");
  }
})();
