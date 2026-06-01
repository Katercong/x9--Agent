(() => {
  const TAG = "[DOUYIN-RUNNER]";
  const MSG = {
    START: "DOUYIN_START",
    STOP: "DOUYIN_STOP",
    GET_STATE: "DOUYIN_GET_STATE",
    RESET: "DOUYIN_RESET",
    CS_START: "DOUYIN_CS_START",
    CS_STOP: "DOUYIN_CS_STOP",
    PROGRESS: "DOUYIN_PROGRESS",
    POST_DONE: "DOUYIN_POST_DONE",
    DONE: "DOUYIN_DONE",
    ERROR: "DOUYIN_ERROR",
    EXPECT_PROFILE: "DOUYIN_EXPECT_PROFILE",
    VERIFY_PROFILE_TAB: "DOUYIN_VERIFY_PROFILE_TAB",
    WAIT_PROFILE: "DOUYIN_WAIT_PROFILE",
    PROFILE_RESULT: "DOUYIN_PROFILE_RESULT",
    OPEN_PROFILE_TAB: "DOUYIN_OPEN_PROFILE_TAB",
    CLOSE_PROFILE_TABS: "DOUYIN_CLOSE_PROFILE_TABS"
  };
  const RESULT_STORAGE_KEY = "x9_douyin_last_result";
  const INGEST_ENDPOINT_KEY = "x9_douyin_ingest_endpoint";
  const INGEST_UPLOAD_STORAGE_KEY = "x9_douyin_last_ingest_upload";
  const DEFAULT_INGEST_ENDPOINT = "https://usx9.us/api/douyin/ingest";

  const DEFAULT_STATE = {
    status: "idle",
    phase: "idle",
    message: "等待开始",
    runId: null,
    listTabId: null,
    startedAt: null,
    finishedAt: null,
    settings: {},
    posts: [],
    comments: [],
    users: {},
    logs: [],
    sample: {},
    ingestUpload: null
  };

  let state = Object.assign({}, DEFAULT_STATE);
  let finishing = false;
  let profileOpenQueue = Promise.resolve();
  const profileWaiters = new Map();
  const profileRequests = new Map();
  const managedProfileTabs = new Set();
  const managedProfileUrls = new Set();

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
    if (message.type === MSG.POST_DONE) {
      mergePostPayload(message);
      persistSnapshot(false, false).catch((e) => console.warn(TAG, "persist failed", e));
      const completionReason = targetCompletionReason();
      if (completionReason) {
        autoFinishRun(completionReason).catch((e) => console.warn(TAG, "auto finish failed", e));
      }
      sendResponse({ ok: true, autoFinish: Boolean(completionReason) });
      return true;
    }
    if (message.type === MSG.DONE) {
      if (finishing || state.status === "done") {
        sendResponse({ ok: true, upload: state.ingestUpload || null });
        return true;
      }
      patch({ status: "running", phase: "upload", finishedAt: new Date().toISOString(), message: "上传中" });
      log("done");
      cleanupAllProfileTabs().then(() => persistSnapshot(false, true, finalSnapshotOverrides("done", "上传中"))).then((uploadInfo) => {
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
      expectProfile(message, sender).then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.VERIFY_PROFILE_TAB) {
      verifyProfileTab(message, sender).then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.WAIT_PROFILE) {
      waitProfile(message).then(sendResponse);
      return true;
    }
    if (message.type === MSG.CLOSE_PROFILE_TABS) {
      handleCloseProfileTabs(sender).then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
      return true;
    }
    if (message.type === MSG.OPEN_PROFILE_TAB) {
      enqueueOpenProfileTab(message, sender).then(sendResponse).catch((e) => sendResponse({ ok: false, error: errText(e) }));
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
    state = Object.assign({}, DEFAULT_STATE, { users: {}, posts: [], comments: [], logs: [], sample: {}, ingestUpload: null });
    await chrome.storage.local.remove([RESULT_STORAGE_KEY, INGEST_UPLOAD_STORAGE_KEY]).catch(() => undefined);
    return { ok: true, state: publicState() };
  }

  async function autoFinishRun(reason) {
    if (finishing) return state.ingestUpload || null;
    if (state.status !== "running") return state.ingestUpload || null;
    finishing = true;
    try {
      const message = `${reason}; uploading and running GPT judgment`;
      patch({ status: "running", phase: "upload", finishedAt: new Date().toISOString(), message });
      log("auto finish: " + reason);
      if (state.listTabId) {
        try { await chrome.tabs.sendMessage(state.listTabId, { type: MSG.CS_STOP }); } catch (_) {}
      }
      stopProfileWaiters("auto_finished");
      await cleanupAllProfileTabs();
      const uploadInfo = await persistSnapshot(false, true, finalSnapshotOverrides("done", message));
      if (uploadInfo && uploadInfo.ok === false) {
        patch({ status: "error", phase: "upload", message: `upload failed: ${uploadInfo.error || "unknown_error"}` });
      } else {
        const ai = uploadInfo && uploadInfo.ai_judgment;
        const aiText = ai && ai.ok === false ? `; GPT skipped: ${ai.error || "unknown_error"}` : "; GPT judgment done";
        patch({ status: "done", phase: "upload", message: `upload success${aiText}` });
      }
      await chrome.storage.local.set({ [RESULT_STORAGE_KEY]: exportSnapshot() }).catch(() => undefined);
      return uploadInfo;
    } finally {
      finishing = false;
    }
  }

  function stopProfileWaiters(reason) {
    for (const waiter of profileWaiters.values()) {
      try { waiter.resolve({ ok: false, error: reason }); } catch (_) {}
      clearTimeout(waiter.timer);
      if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
    }
    profileWaiters.clear();
    profileRequests.clear();
  }

  async function handleStart(settings) {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab || !activeTab.id) return { ok: false, error: "no_active_tab" };
    if (!/douyin\.com/i.test(activeTab.url || "")) {
      return { ok: false, error: "active_tab_is_not_douyin", url: activeTab.url || "" };
    }
    finishing = false;
    profileOpenQueue = Promise.resolve();
    stopProfileWaiters("new_run");
    if (state.listTabId && state.listTabId !== activeTab.id) {
      await cleanupProfileTabsForList(state.listTabId).catch(() => undefined);
    }
    const runId = "douyin-" + new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
    state = Object.assign({}, DEFAULT_STATE, {
      status: "running",
      phase: "posts",
      message: "启动抖音严格步骤采集",
      runId,
      listTabId: activeTab.id,
      startedAt: new Date().toISOString(),
      settings: normalizeSettings(settings),
      posts: [],
      comments: [],
      users: {},
      logs: [],
      sample: {},
      ingestUpload: null
    });
    await chrome.storage.local.remove([INGEST_UPLOAD_STORAGE_KEY]).catch(() => undefined);
    log("start " + runId);
    await cleanupProfileTabsForList(activeTab.id);
    await ensureInjected(activeTab.id, { force: true });
    try {
      await chrome.tabs.sendMessage(activeTab.id, { type: MSG.CS_START, runId, settings: state.settings });
    } catch (_) {
      await ensureInjected(activeTab.id, { force: true });
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

  async function ensureInjected(tabId, options = {}) {
    if (options.force) {
      try {
        await chrome.tabs.sendMessage(tabId, { type: MSG.CS_STOP });
      } catch (_) {}
      await chrome.scripting.executeScript({
        target: { tabId },
        func: () => {
          try {
            window.__DOUYIN_CREATOR_COLLECTOR__ = false;
            window.__DOUYIN_CREATOR_COLLECTOR_VERSION__ = "";
          } catch (_) {}
        },
      });
      await chrome.scripting.executeScript({ target: { tabId }, files: ["social/douyin_content.js"] });
      return;
    }
    try {
      await chrome.tabs.sendMessage(tabId, { type: "DOUYIN_PING" });
      return;
    } catch (_) {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["social/douyin_content.js"] });
    }
  }

  function normalizeSettings(input) {
    return {
      limitMode: input.limitMode === "videos" ? "videos" : "profiles",
      keyword: String(input.keyword || "").trim(),
      maxPosts: clamp(input.maxPosts, 1, 200, 10),
      profileLimit: clamp(input.profileLimit, 1, 300, 20)
    };
  }

  function mergePostPayload(message) {
    if (!state.settings.keyword && message.post && message.post.keyword) {
      state.settings = Object.assign({}, state.settings, { keyword: String(message.post.keyword || "").trim() });
    }
    if (message.post) mergePost(message.post);
    for (const c of message.comments || []) mergeComment(c);
    for (const u of message.users || []) mergeUser(u);
    state.sample = {
      post: state.posts[0] || null,
      comment: state.comments[0] || null,
      user: Object.values(state.users)[0] || null
    };
    patch({ phase: "comments", message: `已采集视频 ${state.posts.length}，评论 ${state.comments.length}，发现用户 ${Object.keys(state.users).length}，已采主页 ${collectedProfileCount()}` });
  }

  function mergePost(post) {
    const key = post.post_id || post.video_id || post.url || post.search_result_url;
    const index = state.posts.findIndex((item) => (item.post_id || item.video_id || item.url || item.search_result_url) === key);
    if (index >= 0) state.posts[index] = Object.assign({}, state.posts[index], post);
    else state.posts.push(post);
  }

  function mergeComment(comment) {
    const key = comment.comment_id || `${comment.post_id || ""}:${comment.content || ""}:${comment.published_at_text || ""}`;
    const index = state.comments.findIndex((item) => (item.comment_id || `${item.post_id || ""}:${item.content || ""}:${item.published_at_text || ""}`) === key);
    if (index >= 0) state.comments[index] = Object.assign({}, state.comments[index], comment);
    else state.comments.push(comment);
  }

  async function expectProfile(message, sender) {
    const key = profileKey(message.user || {}, message.profileUrl);
    if (!key) return { ok: false, error: "missing_profile_key" };
    const existing = state.users[key] || {};
    state.users[key] = Object.assign({}, existing, message.user || {}, {
      profile_url: message.profileUrl || existing.profile_url || "",
      profile_pending: true
    });
    const requestId = message.requestId || key;
    const profileUrl = message.profileUrl || state.users[key].profile_url || "";
    const knownTabIds = await matchingProfileTabIds({ profileUrl, user: state.users[key] }).catch(() => []);
    profileRequests.set(requestId, {
      requestId,
      key,
      profileUrl,
      user: state.users[key],
      sourceType: message.sourceType || "",
      requestedAt: Date.now(),
      openerTabId: state.listTabId || (sender && sender.tab && sender.tab.id) || null,
      knownTabIds,
      tabId: null
    });
    patch({ phase: "profiles", message: "打开用户主页新标签：" + (state.users[key].username || key) });
    return { ok: true, requestId, knownTabIds };
  }

  async function verifyProfileTab(message, sender) {
    const requestId = message.requestId || "";
    const request = profileRequests.get(requestId);
    if (!request) return { ok: false, error: "missing_profile_request" };
    const timeoutMs = clamp(message.timeoutMs, 500, 8000, 3000);
    const started = Date.now();
    while (Date.now() - started <= timeoutMs) {
      const tab = await findFreshMatchingProfileTab(request, sender);
      if (tab && tab.id) {
        request.tabId = tab.id;
        rememberManagedProfileTab(tab, request.profileUrl);
        await closeExtraProfileTabs(tab.id, state.listTabId || request.openerTabId);
        if (tab.status === "complete") await ensureInjected(tab.id).catch(() => undefined);
        patch({ phase: "profiles", message: `profile tab verified: ${tab.id}` });
        return { ok: true, tabId: tab.id, url: tab.pendingUrl || tab.url || "" };
      }
      const candidate = await findFreshProfileOpenCandidate(request, sender);
      if (candidate && candidate.id) {
        request.tabId = candidate.id;
        rememberManagedProfileTab(candidate, request.profileUrl);
      }
      await sleep(200);
    }
    if (request.tabId && request.tabId !== state.listTabId) {
      await chrome.tabs.remove(request.tabId).catch(() => undefined);
      forgetManagedProfileTabs(new Set([request.tabId]));
      request.tabId = null;
    }
    return { ok: false, error: "profile_tab_not_opened" };
  }

  function waitProfile(message) {
    const key = profileKey(message.user || {}, message.profileUrl);
    if (!key) return Promise.resolve({ ok: false, error: "missing_profile_key" });
    const existing = state.users[key];
    if (existing && existing.profile_collected_at) return Promise.resolve({ ok: true, user: existing });
    return new Promise((resolve) => {
      const timeoutMs = clamp(message.timeoutMs, 3000, 60000, 22000);
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
        tabId: message.tabId || request.tabId || null,
        startedAt: Date.now(),
        resolve,
        timer: null,
        pollTimer: null
      };
      if (request && waiter.tabId) request.tabId = waiter.tabId;
      const timer = setTimeout(() => {
        profileWaiters.delete(waiter.requestId);
        profileRequests.delete(waiter.requestId);
        if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
        if (state.users[key]) state.users[key].profile_pending = false;
        cleanupProfileTabs(waiter).finally(() => {
          resolve({ ok: false, error: "profile_timeout", user: state.users[key] || null });
        });
      }, timeoutMs);
      waiter.timer = timer;
      profileWaiters.set(requestId, waiter);
      trackProfileTab(waiter);
    });
  }

  function enqueueOpenProfileTab(message, sender) {
    const task = profileOpenQueue
      .catch(() => undefined)
      .then(() => handleOpenProfileTab(message, sender));
    profileOpenQueue = task.then(() => undefined, () => undefined);
    return task;
  }

  async function handleOpenProfileTab(message, sender) {
    const profileUrl = String(message.profileUrl || "").trim();
    if (!/douyin\.com\/user\//i.test(profileUrl)) return { ok: false, error: "invalid_profile_url" };
    const openerTabId = sender && sender.tab && sender.tab.id ? sender.tab.id : undefined;
    const listTabId = state.listTabId || openerTabId;
    const requestId = message.requestId || profileKey(message.user || {}, profileUrl);
    clearStaleProfileWaiters(requestId, "profile_wait_stale", 45000);
    clearStaleProfileRequests(requestId, "profile_request_stale", 45000);
    const activeWaiter = findActiveProfileWaiter(requestId, 45000);
    const activeRequest = findActiveProfileRequest(requestId, 45000);
    if (activeWaiter || activeRequest) {
      const pending = profileRequests.get(requestId);
      if (pending && state.users[pending.key]) state.users[pending.key].profile_pending = false;
      profileRequests.delete(requestId);
      return { ok: false, error: "profile_wait_in_progress", activeRequestId: (activeWaiter || activeRequest).requestId };
    }
    await cleanupProfileTabsForList(listTabId);
    const tab = await chrome.tabs.create({
      url: profileUrl,
      active: false,
      openerTabId
    });
    rememberManagedProfileTab(tab, profileUrl);
    await closeExtraProfileTabs(tab && tab.id, listTabId);
    const request = profileRequests.get(requestId);
    if (request && tab && tab.id) request.tabId = tab.id;
    return { ok: true, tabId: tab && tab.id };
  }

  function clearOtherProfileWaiters(keepRequestId, reason) {
    for (const waiter of Array.from(profileWaiters.values())) {
      if (!waiter || waiter.requestId === keepRequestId) continue;
      try { waiter.resolve({ ok: false, error: reason || "profile_open_replaced" }); } catch (_) {}
      clearTimeout(waiter.timer);
      if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
      profileWaiters.delete(waiter.requestId);
      profileRequests.delete(waiter.requestId);
      if (state.users[waiter.key]) state.users[waiter.key].profile_pending = false;
    }
  }

  function findActiveProfileWaiter(keepRequestId, maxAgeMs) {
    const now = Date.now();
    for (const waiter of profileWaiters.values()) {
      if (!waiter || waiter.requestId === keepRequestId) continue;
      if (now - Number(waiter.startedAt || now) <= maxAgeMs) return waiter;
    }
    return null;
  }

  function findActiveProfileRequest(keepRequestId, maxAgeMs) {
    const now = Date.now();
    for (const request of profileRequests.values()) {
      if (!request || request.requestId === keepRequestId) continue;
      if (now - Number(request.requestedAt || now) <= maxAgeMs) return request;
    }
    return null;
  }

  function clearStaleProfileWaiters(keepRequestId, reason, maxAgeMs) {
    const now = Date.now();
    for (const waiter of Array.from(profileWaiters.values())) {
      if (!waiter || waiter.requestId === keepRequestId) continue;
      if (now - Number(waiter.startedAt || now) <= maxAgeMs) continue;
      try { waiter.resolve({ ok: false, error: reason || "profile_wait_stale" }); } catch (_) {}
      clearTimeout(waiter.timer);
      if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
      profileWaiters.delete(waiter.requestId);
      profileRequests.delete(waiter.requestId);
      if (state.users[waiter.key]) state.users[waiter.key].profile_pending = false;
    }
  }

  function clearStaleProfileRequests(keepRequestId, reason, maxAgeMs) {
    const now = Date.now();
    for (const request of Array.from(profileRequests.values())) {
      if (!request || request.requestId === keepRequestId) continue;
      if (now - Number(request.requestedAt || now) <= maxAgeMs) continue;
      profileRequests.delete(request.requestId);
      if (state.users[request.key]) {
        state.users[request.key].profile_pending = false;
        state.users[request.key].profile_collection_error = reason || "profile_request_stale";
      }
    }
  }

  async function handleCloseProfileTabs(sender) {
    const listTabId = state.listTabId || (sender && sender.tab && sender.tab.id) || null;
    if (!listTabId) return { ok: true, closed: 0 };
    const closed = await cleanupProfileTabsForList(listTabId);
    await activateCollectionTab(listTabId);
    return { ok: true, closed };
  }

  async function handleProfileResult(message, sender) {
    const user = message.user || {};
    const key = profileKey(user, user.profile_url || message.profileUrl);
    const senderTabId = sender && sender.tab && sender.tab.id ? sender.tab.id : null;
    const waiter = key ? findProfileWaiterForResult(key, senderTabId) : null;
    const request = key ? findProfileRequestForResult(key, senderTabId) : null;
    if (!key || (!waiter && !request)) {
      return { ok: true, ignored: true };
    }
    if (waiter && waiter.tabId && senderTabId && waiter.tabId !== senderTabId) {
      return { ok: true, ignored: true, reason: "tab_mismatch" };
    }
    if (!waiter && request && !request.tabId) {
      return { ok: true, ignored: true, reason: "request_not_bound" };
    }
    if (request && senderTabId && Array.isArray(request.knownTabIds) && request.knownTabIds.includes(senderTabId)) {
      return { ok: true, ignored: true, reason: "known_old_profile_tab" };
    }
    if (!waiter && request && request.tabId && senderTabId && request.tabId !== senderTabId) {
      return { ok: true, ignored: true, reason: "request_tab_mismatch" };
    }
    if (state.status !== "running" && !waiter && !request) {
      return { ok: true, ignored: true };
    }
    const complete = Boolean(user.profile_collected_at);
    const alreadyCollected = Boolean(key && state.users[key] && state.users[key].profile_collected_at);
    if (complete && !alreadyCollected && isProfileLimitMode() && collectedProfileCount() >= clamp(state.settings && state.settings.profileLimit, 1, 300, 20)) {
      if (waiter) {
        clearTimeout(waiter.timer);
        if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
        profileWaiters.delete(waiter.requestId);
        profileRequests.delete(waiter.requestId);
        waiter.resolve({ ok: false, error: "profile_limit_reached", user: state.users[key] || user });
      } else if (request) {
        profileRequests.delete(request.requestId);
      }
      if (state.users[key]) state.users[key].profile_pending = false;
      if (sender && sender.tab && sender.tab.id && sender.tab.id !== state.listTabId) {
        const cleanupWaiter = { tabId: sender.tab.id, key, profileUrl: user.profile_url || message.profileUrl || "", user };
        await cleanupProfileTabs(cleanupWaiter).catch(() => undefined);
      }
      return { ok: true, ignored: true, reason: "profile_limit_reached" };
    }
    let shouldClose = false;
    let waiterToResolve = null;
    let resolvedUser = null;
    if (key) {
      mergeUser(user);
      if (waiter) {
        if (senderTabId) waiter.tabId = senderTabId;
        clearTimeout(waiter.timer);
        if (waiter.pollTimer) clearTimeout(waiter.pollTimer);
        profileWaiters.delete(waiter.requestId);
        profileRequests.delete(waiter.requestId);
        waiterToResolve = waiter;
        resolvedUser = state.users[key];
        shouldClose = true;
      } else if (request) {
        profileRequests.delete(request.requestId);
        shouldClose = true;
      }
      if (state.users[key] && state.users[key].profile_pending) shouldClose = true;
      if (state.users[key]) state.users[key].profile_pending = false;
    }
    if (shouldClose && sender && sender.tab && sender.tab.id && sender.tab.id !== state.listTabId) {
      const waiter = { tabId: sender.tab.id, key, profileUrl: user.profile_url || message.profileUrl || "", user };
      await cleanupProfileTabs(waiter).catch(() => undefined);
      await activateCollectionTab();
    }
    if (waiterToResolve) {
      const resolved = resolvedUser || (key && state.users[key]) || user;
      waiterToResolve.resolve({
        ok: Boolean(resolved && resolved.profile_collected_at),
        error: resolved && resolved.profile_collected_at ? undefined : "profile_incomplete",
        user: resolved
      });
    }
    persistSnapshot(false, false).catch((e) => console.warn(TAG, "persist failed", e));
    const completionReason = targetCompletionReason();
    if (completionReason) {
      autoFinishRun(completionReason).catch((e) => console.warn(TAG, "auto finish failed", e));
    }
    return { ok: true };
  }

  function mergeUser(user) {
    const key = profileKey(user, user.profile_url);
    if (!key) return;
    const prev = state.users[key] || {};
    const incoming = Object.assign({}, user);
    if (!incoming.profile_collected_at && prev.profile_collected_at) delete incoming.profile_collected_at;
    state.users[key] = Object.assign({}, prev, incoming, {
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

  function findProfileWaiterForResult(key, tabId) {
    const waiters = Array.from(profileWaiters.values()).filter((waiter) => waiter && waiter.key === key);
    if (tabId) {
      const byTab = waiters.find((waiter) => waiter.tabId === tabId);
      if (byTab) return byTab;
    }
    return waiters.find((waiter) => !waiter.tabId) || waiters[0] || null;
  }

  function findProfileRequestForResult(key, tabId) {
    const requests = Array.from(profileRequests.values()).filter((request) => request && request.key === key);
    if (tabId) {
      const byTab = requests.find((request) => request.tabId === tabId);
      if (byTab) return byTab;
    }
    return requests.find((request) => !request.tabId) || requests[0] || null;
  }

  async function matchingProfileTabIds(waiter) {
    const tabs = await chrome.tabs.query({});
    return tabs
      .filter((tab) => tabMatchesProfileWaiter(tab, waiter || {}))
      .map((tab) => tab.id)
      .filter((id) => id != null);
  }

  async function findFreshMatchingProfileTab(request, sender) {
    const listTabId = state.listTabId || (sender && sender.tab && sender.tab.id) || null;
    const known = new Set(request.knownTabIds || []);
    const tabs = await chrome.tabs.query({});
    const candidates = tabs
      .filter((tab) => tab && tab.id && tab.id !== listTabId)
      .filter((tab) => !known.has(tab.id))
      .filter((tab) => tabMatchesProfileWaiter(tab, request));
    return candidates.find((tab) => request.openerTabId && tab.openerTabId === request.openerTabId) ||
      candidates.find((tab) => tab.openerTabId === listTabId) ||
      candidates[0] ||
      null;
  }

  async function findFreshProfileOpenCandidate(request, sender) {
    const listTabId = state.listTabId || (sender && sender.tab && sender.tab.id) || null;
    const known = new Set(request.knownTabIds || []);
    const tabs = await chrome.tabs.query({});
    const candidates = tabs
      .filter((tab) => tab && tab.id && tab.id !== listTabId)
      .filter((tab) => !known.has(tab.id))
      .filter((tab) => !request.tabId || tab.id === request.tabId || tab.openerTabId === request.openerTabId || tab.openerTabId === listTabId)
      .filter((tab) => {
        const url = String(tab.pendingUrl || tab.url || "");
        return !url || /^about:blank/i.test(url) || /douyin\.com/i.test(url);
      });
    return candidates.find((tab) => request.tabId && tab.id === request.tabId) ||
      candidates.find((tab) => request.openerTabId && tab.openerTabId === request.openerTabId) ||
      candidates.find((tab) => tab.openerTabId === listTabId) ||
      null;
  }

  function trackProfileTab(waiter) {
    let attempts = 0;
    const tick = async () => {
      if (!profileWaiters.has(waiter.requestId)) return;
      attempts += 1;
      try {
        const tab = await findMatchingProfileTab(waiter);
        if (tab && tab.id) {
          waiter.tabId = tab.id;
          rememberManagedProfileTab(tab, waiter.profileUrl);
          await closeExtraProfileTabs(tab.id, state.listTabId);
          const request = profileRequests.get(waiter.requestId);
          if (request) request.tabId = tab.id;
          if (tab.status === "complete") await ensureInjected(tab.id).catch(() => undefined);
        } else if (attempts >= 24 && !waiter.tabId) {
          profileWaiters.delete(waiter.requestId);
          profileRequests.delete(waiter.requestId);
          clearTimeout(waiter.timer);
          if (state.users[waiter.key]) state.users[waiter.key].profile_pending = false;
          waiter.resolve({ ok: false, error: "profile_tab_not_found", user: state.users[waiter.key] || null });
          return;
        }
      } catch (_) {}
      if (attempts < 90 && profileWaiters.has(waiter.requestId)) {
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
    if (!/douyin\.com\/user\//i.test(url)) return false;
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
    forgetManagedProfileTabs(ids, tabs);
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
    managedProfileTabs.clear();
    managedProfileUrls.clear();
  }

  async function cleanupProfileTabsForList(listTabId) {
    if (!listTabId) return 0;
    const tabs = await chrome.tabs.query({}).catch(() => []);
    const ids = tabs
      .filter((tab) => tab && tab.id && tab.id !== listTabId && tab.openerTabId === listTabId)
      .concat(tabs.filter((tab) => tab && tab.id && tab.id !== listTabId && managedProfileTabs.has(tab.id)))
      .concat(tabs.filter((tab) => {
        if (!tab || !tab.id || tab.id === listTabId) return false;
        const url = canonicalProfileUrl(String(tab.pendingUrl || tab.url || ""));
        return url && managedProfileUrls.has(url);
      }))
      .filter((tab, index, arr) => arr.findIndex((item) => item && item.id === tab.id) === index)
      .filter((tab) => /douyin\.com\/user\//i.test(String(tab.pendingUrl || tab.url || "")))
      .map((tab) => tab.id);
    forgetManagedProfileTabs(new Set(ids), tabs);
    await Promise.all(ids.map((id) => chrome.tabs.remove(id).catch(() => undefined)));
    return ids.length;
  }

  async function closeExtraProfileTabs(keepTabId, listTabId) {
    const tabs = await chrome.tabs.query({}).catch(() => []);
    const ids = tabs
      .filter((tab) => tab && tab.id && tab.id !== keepTabId && tab.id !== listTabId)
      .filter((tab) => {
        const url = String(tab.pendingUrl || tab.url || "");
        if (!/douyin\.com\/user\//i.test(url)) return false;
        if (managedProfileTabs.has(tab.id)) return true;
        if (listTabId && tab.openerTabId === listTabId) return true;
        const canonical = canonicalProfileUrl(url);
        return Boolean(canonical && managedProfileUrls.has(canonical));
      })
      .map((tab) => tab.id);
    if (!ids.length) return 0;
    forgetManagedProfileTabs(new Set(ids), tabs);
    await Promise.all(ids.map((id) => chrome.tabs.remove(id).catch(() => undefined)));
    return ids.length;
  }

  async function activateCollectionTab(fallbackTabId) {
    const tabId = state.listTabId || fallbackTabId || null;
    if (!tabId) return false;
    try {
      const tab = await chrome.tabs.get(tabId);
      if (!tab || !tab.id) return false;
      if (tab.windowId != null) {
        await chrome.windows.update(tab.windowId, { focused: true }).catch(() => undefined);
      }
      await chrome.tabs.update(tab.id, { active: true });
      return true;
    } catch (_) {
      return false;
    }
  }

  function rememberManagedProfileTab(tab, fallbackUrl) {
    if (tab && tab.id) managedProfileTabs.add(tab.id);
    const url = canonicalProfileUrl(String((tab && (tab.pendingUrl || tab.url)) || fallbackUrl || ""));
    if (url) managedProfileUrls.add(url);
  }

  function forgetManagedProfileTabs(ids, tabs) {
    const idSet = ids instanceof Set ? ids : new Set(ids || []);
    for (const id of idSet) managedProfileTabs.delete(id);
    for (const tab of tabs || []) {
      if (!tab || !idSet.has(tab.id)) continue;
      const url = canonicalProfileUrl(String(tab.pendingUrl || tab.url || ""));
      if (url) managedProfileUrls.delete(url);
    }
  }

  function exportSnapshot(overrides) {
    const users = Object.values(state.users || {});
    const replies = state.comments.filter((c) => Number(c.depth || 0) > 0).length;
    const snapshot = {
      platform: "douyin",
      status: state.status,
      phase: state.phase,
      message: state.message,
      run_id: state.runId,
      started_at: state.startedAt,
      finished_at: state.finishedAt,
      settings: state.settings || {},
      counts: {
        posts: state.posts.length,
        comments: state.comments.length,
        replies,
        users: users.length,
        profiles: users.filter((u) => u.profile_collected_at).length
      },
      posts: state.posts || [],
      comments: state.comments || [],
      users,
      logs: state.logs || [],
      exported_at: new Date().toISOString()
    };
    return Object.assign(snapshot, overrides || {});
  }

  async function persistSnapshot(download, upload, overrides) {
    const snapshot = exportSnapshot(overrides);
    await chrome.storage.local.set({ [RESULT_STORAGE_KEY]: snapshot });
    let uploadInfo = null;
    if (upload) uploadInfo = await uploadSnapshot(snapshot);
    if (!download) return uploadInfo;
    const json = JSON.stringify(snapshot, null, 2);
    const filename = `douyin_collect_${snapshot.run_id || Date.now()}.json`;
    const url = "data:application/json;charset=utf-8," + encodeURIComponent(json);
    await chrome.downloads.download({ url, filename, saveAs: false, conflictAction: "overwrite" });
    return uploadInfo;
  }

  function finalSnapshotOverrides(status, message) {
    return {
      status: status || "done",
      phase: "upload",
      message: message || state.message || "uploading",
      finished_at: state.finishedAt || new Date().toISOString()
    };
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
      const uploadInfo = {
        ok: true,
        endpoint,
        run_id: snapshot.run_id || state.runId || null,
        at: new Date().toISOString(),
        stats: result.stats || null,
        ai_judgment: result.ai_judgment || null
      };
      patch({ ingestUpload: uploadInfo });
      await chrome.storage.local.set({ [INGEST_UPLOAD_STORAGE_KEY]: uploadInfo });
      log("已上传抖音接口");
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
    const profiles = collectedProfileCount();
    const replies = state.comments.filter((c) => Number(c.depth || 0) > 0).length;
    return Object.assign({}, state, {
      counts: {
        posts: state.posts.length,
        comments: state.comments.length,
        replies,
        users: users.length,
        profiles
      },
      sample: {
        post: state.posts[0] || null,
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

  function collectedProfileCount() {
    return Object.values(state.users || {}).filter((u) => u && u.profile_collected_at).length;
  }

  function isProfileLimitMode() {
    return !state.settings || state.settings.limitMode !== "videos";
  }

  function targetCompletionReason() {
    if (state.status !== "running") return "";
    const settings = state.settings || {};
    if (settings.limitMode === "videos") {
      const target = clamp(settings.maxPosts, 1, 200, 10);
      return state.posts.length >= target ? `video target reached ${state.posts.length}/${target}` : "";
    }
    const target = clamp(settings.profileLimit, 1, 300, 20);
    const profiles = collectedProfileCount();
    return profiles >= target ? `profile target reached ${profiles}/${target}` : "";
  }

  function patch(values) {
    state = Object.assign({}, state, values || {});
  }

  function log(text) {
    const value = String(text || "").trim();
    if (!value) return;
    state.logs = (state.logs || []).concat(`[${new Date().toLocaleTimeString()}] ${value}`).slice(-120);
    console.log(TAG, value);
  }

  function profileKey(user, profileUrl) {
    const url = String(profileUrl || user.profile_url || "");
    const m = url.match(/\/user\/([^/?#]+)/);
    return user.user_id || user.sec_uid || user.unique_id || (m && m[1]) || user.username || url;
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

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
})();
