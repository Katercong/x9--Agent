/* TikTok Shop service-worker orchestrator (v8).
 * v8: collection only. Finished runs upload raw observations to the backend;
 *     CSV export is a manual backend UI action, never an automatic download. */
(function () {
  const TAG = "[TSCLB-SW]";
  const STORE_KEY = "shopAutoRun";
  const MSG = {
    SHOP_START: "TSCLB_SHOP_START", SHOP_STOP: "TSCLB_SHOP_STOP",
    SHOP_GET_STATE: "TSCLB_SHOP_GET_STATE",
    SHOP_RESET_COUNTS: "TSCLB_SHOP_RESET_COUNTS",
    SHOP_SET_SETTINGS: "TSCLB_SHOP_SET_SETTINGS",
    CS_AUTO_FULL_RUN: "TSCLB_AUTO_FULL_RUN", CS_AUTO_STOP: "TSCLB_AUTO_STOP",
    CS_CLICK_ROW: "TSCLB_CLICK_ROW", CS_SCAN_DETAIL_NOW: "TSCLB_SCAN_DETAIL_NOW",
    CS_LIST_BATCH: "TSCLB_LIST_BATCH", CS_LIST_DONE: "TSCLB_LIST_DONE",
    CS_PROGRESS: "TSCLB_PROGRESS", CS_ERROR: "TSCLB_CS_ERROR",
    AUTO_RUN_FINISHED: "TSCLB_AUTO_RUN_FINISHED",
  };

  const SHOP_EXTENSION_ID = "tiktok_shop_creator_lead_browser_extension_2_2";
  const SHOP_LEGACY_WORKER_ID = "tiktok_shop_creator_lead_browser_2_2";
  const SHOP_STABLE_WORKER_ID_KEY = "x9ShopStableWorkerId";
  const SHOP_QUOTA_KEY = "x9ShopHourlyQuota";
  const SHOP_PENDING_UPLOADS_KEY = "x9ShopPendingUploads";
  const X9_API_BASE_KEY = "x9_api_base";
  const X9_API_BASE_ACTIVE_KEY = "x9_api_base_active";
  const X9_LAST_HEARTBEAT_KEY = "x9LastHeartbeat";
  const X9_LAST_OBSERVATION_UPLOAD_KEY = "x9LastObservationUpload";
  const SHOP_HEARTBEAT_ALARM = "x9-shop-heartbeat";
  const SHOP_HOURLY_LIMIT = null;
  const SHOP_DETAIL_MIN_INTERVAL_MS = 5000;
  const SHOP_UPLOAD_TIMEOUT_MS = 20000;
  const SHOP_UPLOAD_FLUSH_CONCURRENCY = 3;
  const SHOP_PENDING_UPLOAD_LIMIT = 2000;
  const SHOP_PENDING_FLUSH_BATCH_LIMIT = 30;
  const SHOP_POST_DETAIL_DELAY_MS = 300;
  const DETAIL_UPLOAD_VISIBLE_TEXT_LIMIT = 60000;
  const DETAIL_UPLOAD_LINK_LIMIT = 120;

  // New collection traffic goes through usx9.us so the backend can resolve the
  // logged-in portal user and attach actor_user_id consistently.
  const USX9_API_BASE = "https://usx9.us";
  const UPLOAD_PATH = "/api/local/collector/observations";

  const DEFAULT_SETTINGS = {
    endpoint: USX9_API_BASE + UPLOAD_PATH,
    source: SHOP_EXTENSION_ID,
    extensionId: SHOP_EXTENSION_ID,
    workerId: SHOP_LEGACY_WORKER_ID,
    accountId: SHOP_LEGACY_WORKER_ID,
    hourlyLimit: SHOP_HOURLY_LIMIT,
    taskCount: 20,
  };
  const UPLOAD_BASES = [
    USX9_API_BASE,
  ];

  const DEFAULT_STATE = {
    status: "idle", phase: "idle", runId: null,
    listTabId: null, detailTabId: null,
    startedAt: null, finishedAt: null,
    counts: { listItems: 0, listUploads: 0, listUploadFail: 0, detailDone: 0, detailFail: 0, errors: 0 },
    handles: [], doneHandles: [], queueIndex: 0,
    currentHandle: null, nextResumeAt: null, lastError: null, lastStatus: null,
    settings: DEFAULT_SETTINGS,
  };

  let detailLoopActive = false;
  let pendingDetailResolve = null;

  console.log(TAG, "shop_runner v9 loaded");
  ensureShopHeartbeatAlarm();
  scheduleShopResumeIfNeeded().catch(() => undefined);
  postShopHeartbeat("loaded").catch(() => undefined);

  chrome.runtime.onInstalled.addListener(() => {
    ensureShopHeartbeatAlarm();
    scheduleShopResumeIfNeeded().catch(() => undefined);
    postShopHeartbeat("installed").catch(() => undefined);
  });

  chrome.runtime.onStartup.addListener(() => {
    ensureShopHeartbeatAlarm();
    scheduleShopResumeIfNeeded().catch(() => undefined);
    postShopHeartbeat("startup").catch(() => undefined);
  });

  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === SHOP_HEARTBEAT_ALARM) {
      postShopHeartbeat("alarm").catch(() => undefined);
      flushPendingUploads("alarm").catch(() => undefined);
    }
  });

  function getState() {
    return new Promise((resolve) => {
      chrome.storage.local.get([STORE_KEY], (got) => {
        const s = got && got[STORE_KEY];
        resolve(Object.assign({}, DEFAULT_STATE, s || {}, {
          counts: Object.assign({}, DEFAULT_STATE.counts, (s && s.counts) || {}),
          settings: Object.assign({}, DEFAULT_STATE.settings, (s && s.settings) || {}),
          handles: Array.isArray(s && s.handles) ? s.handles : [],
          doneHandles: Array.isArray(s && s.doneHandles) ? s.doneHandles : [],
        }));
      });
    });
  }
  function setState(state) { return new Promise((r) => chrome.storage.local.set({ [STORE_KEY]: state }, r)); }
  async function patchState(patch) {
    const cur = await getState();
    const next = Object.assign({}, cur, patch);
    if (patch.counts) next.counts = Object.assign({}, cur.counts, patch.counts);
    if (patch.settings) next.settings = Object.assign({}, cur.settings, patch.settings);
    await setState(next);
    return next;
  }

  let shopStableWorkerIdentityPromise = null;

  async function ensureShopWorkerIdentity() {
    if (!shopStableWorkerIdentityPromise) {
      shopStableWorkerIdentityPromise = (async () => {
        const extensionId = runtimeExtensionId();
        const prefix = `tiktok_shop_${extensionId}_`;
        const stored = await chrome.storage.local.get([SHOP_STABLE_WORKER_ID_KEY]).catch(() => ({}));
        let workerId = String(stored[SHOP_STABLE_WORKER_ID_KEY] || "").trim();
        if (!workerId.startsWith(prefix)) {
          workerId = `${prefix}${createUuid()}`;
          await chrome.storage.local.set({ [SHOP_STABLE_WORKER_ID_KEY]: workerId }).catch(() => undefined);
        }
        return { extensionId, workerId, accountId: workerId };
      })();
    }
    return shopStableWorkerIdentityPromise;
  }

  async function ensureShopSettings(settings) {
    const identity = await ensureShopWorkerIdentity();
    return Object.assign({}, DEFAULT_SETTINGS, settings || {}, {
      extensionId: identity.extensionId,
      workerId: identity.workerId,
      accountId: identity.accountId,
      hourlyLimit: SHOP_HOURLY_LIMIT,
    });
  }

  function runtimeExtensionId() {
    return String(chrome?.runtime?.id || SHOP_EXTENSION_ID).trim() || SHOP_EXTENSION_ID;
  }

  function createUuid() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
      return globalThis.crypto.randomUUID();
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  }

  function currentHourWindow(nowMs) {
    const d = new Date(nowMs || Date.now());
    d.setMinutes(0, 0, 0);
    const startMs = d.getTime();
    return { startMs, nextMs: startMs + 60 * 60 * 1000 };
  }

  async function getQuotaStatus(nowMs) {
    const now = nowMs || Date.now();
    const windowInfo = currentHourWindow(now);
    const stored = await chrome.storage.local.get([SHOP_QUOTA_KEY]).catch(() => ({}));
    const raw = stored[SHOP_QUOTA_KEY] && typeof stored[SHOP_QUOTA_KEY] === "object" ? stored[SHOP_QUOTA_KEY] : {};
    let used = Number(raw.used) || 0;
    const sameWindow = Number(raw.window_start_ms) === windowInfo.startMs;
    if (!sameWindow) used = 0;
    used = Math.max(0, Math.floor(used));
    const quota = {
      window_start_ms: windowInfo.startMs,
      window_start_at: new Date(windowInfo.startMs).toISOString(),
      hourly_limit: SHOP_HOURLY_LIMIT,
      used,
      hourly_used: used,
      hourly_remaining: null,
      next_resume_at: null,
      last_detail_started_at: sameWindow ? Number(raw.last_detail_started_at) || 0 : 0,
      updated_at: new Date(now).toISOString(),
    };
    if (!sameWindow || raw.used !== quota.used || raw.next_resume_at !== quota.next_resume_at) {
      await chrome.storage.local.set({ [SHOP_QUOTA_KEY]: quota }).catch(() => undefined);
    }
    return quota;
  }

  async function saveQuota(quota) {
    await chrome.storage.local.set({ [SHOP_QUOTA_KEY]: quota }).catch(() => undefined);
    return quota;
  }

  async function waitForDetailPace() {
    let quota = await getQuotaStatus();
    const elapsed = Date.now() - (Number(quota.last_detail_started_at) || 0);
    if (quota.last_detail_started_at && elapsed < SHOP_DETAIL_MIN_INTERVAL_MS) {
      const waitMs = SHOP_DETAIL_MIN_INTERVAL_MS - elapsed;
      await patchState({ lastStatus: `节流等待 ${Math.ceil(waitMs / 1000)} 秒后继续详情采集` });
      await sleep(waitMs);
      quota = await getQuotaStatus();
    }
    quota.last_detail_started_at = Date.now();
    quota.updated_at = new Date().toISOString();
    await saveQuota(quota);
  }

  async function recordDetailUploadForQuota() {
    // Risk-control quota is consumed once a detail payload is ready to upload;
    // backend upload failures must not open extra scrape capacity.
    const quota = await getQuotaStatus();
    quota.used = (Number(quota.used) || 0) + 1;
    quota.hourly_used = quota.used;
    quota.hourly_remaining = null;
    quota.next_resume_at = null;
    quota.updated_at = new Date().toISOString();
    await saveQuota(quota);
    return quota;
  }

  function ensureShopHeartbeatAlarm() {
    chrome.alarms.create(SHOP_HEARTBEAT_ALARM, { periodInMinutes: 0.5 });
  }

  async function scheduleShopResumeIfNeeded() {
    const state = await getState();
    if (state.status !== "paused" || state.phase !== "rate_limited") return;
    await resumeAfterRateLimit();
  }

  async function resumeAfterRateLimit() {
    const state = await getState();
    if (state.status !== "paused" || state.phase !== "rate_limited") return;
    await patchState({
      status: "running",
      phase: "detail_scanning",
      nextResumeAt: null,
      lastStatus: "detail pacing active; collection resumed",
    });
    postShopHeartbeat("rate_limit_resumed").catch(() => undefined);
    if (!detailLoopActive) runDetailLoop().catch(async (e) => {
      await patchState({ status: "error", phase: "idle", lastError: "detail_loop:" + String(e && e.message || e) });
    });
  }

  function apiBaseFromEndpoint(endpoint) {
    try {
      const parsed = new URL(endpoint || "");
      return allowedApiBase(parsed.origin);
    } catch (_) {}
    return "";
  }

  async function buildApiBaseOrder(endpoint) {
    const out = [];
    const add = (base) => {
      const clean = String(base || "").replace(/\/+$/, "");
      if (clean && !out.includes(clean)) out.push(clean);
    };
    add(apiBaseFromEndpoint(endpoint));
    for (const base of await getDashboardBaseCandidates()) add(base);
    for (const base of await getStoredApiBases()) add(base);
    for (const base of UPLOAD_BASES) add(base);
    return out;
  }

  function dashboardBaseFromUrl(url) {
    try {
      const parsed = new URL(url || "");
      const host = parsed.hostname.toLowerCase();
      const path = parsed.pathname || "/";
      const knownHost = host === "usx9.us" || host.endsWith(".usx9.us");
      const dashboardPath = path === "/"
        || path.startsWith("/portal")
        || path.startsWith("/ui")
        || path === "/d"
        || path.startsWith("/d/");
      if (!/^https?:$/.test(parsed.protocol) || !knownHost || !dashboardPath) {
        return "";
      }
      return parsed.origin;
    } catch (_) {
      return "";
    }
  }

  async function getDashboardBaseCandidates() {
    const [activeTabs, allTabs] = await Promise.all([
      chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []),
      chrome.tabs.query({}).catch(() => []),
    ]);
    const bases = [];
    for (const tab of [...activeTabs, ...allTabs]) {
      const base = allowedApiBase(dashboardBaseFromUrl(tab?.url));
      if (base && !bases.includes(base)) bases.push(base);
    }
    return bases;
  }

  async function getStoredApiBases() {
    const got = await chrome.storage.local.get([X9_API_BASE_KEY, X9_API_BASE_ACTIVE_KEY]).catch(() => ({}));
    return [got[X9_API_BASE_KEY], got[X9_API_BASE_ACTIVE_KEY]]
      .map(allowedApiBase)
      .filter(Boolean);
  }

  async function setActiveApiBaseFromEndpoint(endpoint) {
    const base = allowedApiBase(apiBaseFromEndpoint(endpoint));
    if (base) {
      await chrome.storage.local.set({ [X9_API_BASE_ACTIVE_KEY]: base }).catch(() => undefined);
    }
  }

  async function getShopAuthHeaders(headers) {
    if (typeof x9BuildAuthHeaders === "function") {
      return x9BuildAuthHeaders(headers);
    }
    return Object.assign({}, headers || {});
  }

  async function resolveShopActorIdentity() {
    if (typeof x9ResolveActorIdentity === "function") {
      return x9ResolveActorIdentity();
    }
    return shopActorFromUser((bundledShopActorConfig().actor));
  }

  function shopActorFromUser(user) {
    if (!user) return null;
    const id = String(user.id || user.identity || "").trim();
    if (!id) return null;
    return {
      id,
      username: user.username || "",
      display_name: user.display_name || user.name || "",
      email: user.email || "",
      role: user.role || "",
      department_code: user.department_code || "",
    };
  }

  function attachShopActorIdentity(payload, actor) {
    if (typeof x9AttachActorIdentity === "function") {
      return x9AttachActorIdentity(payload, actor);
    }
    if (!payload) return payload;
    const config = bundledShopActorConfig();
    const bundledActor = actor || shopActorFromUser(config.actor);
    if (bundledActor && bundledActor.id) {
      payload.actor_user_id = bundledActor.id;
      payload.actor = bundledActor;
    }
    if (config.actor_token) {
      payload.actor_token = config.actor_token;
      payload.actor_downloaded_at = config.downloaded_at || "";
    }
    return payload;
  }

  function bundledShopActorConfig() {
    const config = globalThis.X9_BUNDLED_ACTOR_CONFIG || {};
    return config && config.ok !== false ? config : {};
  }

  // New upload traffic is pinned to usx9.us so attribution comes from the
  // logged-in portal session.
  function allowedApiBase(base) {
    const normalized = String(base || "").replace(/\/+$/, "");
    if (!normalized) return "";
    try {
      const parsed = new URL(normalized);
      const host = parsed.hostname.toLowerCase();
      if (parsed.protocol === "https:" && (host === "usx9.us" || host.endsWith(".usx9.us"))) {
        return normalized;
      }
    } catch (_) {}
    return "";
  }

  async function postShopHeartbeat(reason) {
    const state = await getState();
    const settings = await ensureShopSettings(state.settings);
    const quota = await getQuotaStatus();
    const actor = await resolveShopActorIdentity();
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
    const currentUrl = activeTab?.url || "";
    const running = state.status === "running";
    const fatalError = state.status === "error" ? (state.lastError || null) : null;
    const payload = {
      app: "tiktok-shop-creator-lead-browser",
      version: chrome.runtime.getManifest().version,
      extension_id: settings.extensionId,
      extensionId: settings.extensionId,
      worker_id: settings.workerId,
      account_id: settings.accountId,
      actor_user_id: actor?.id || null,
      actor: actor || null,
      source: "tiktok_shop",
      status: state.status || "idle",
      running,
      current_action: state.lastStatus || state.phase || reason,
      current_handle: state.currentHandle || null,
      search_keyword: settings.searchKeyword || null,
      hourly_limit: quota.hourly_limit,
      hourly_used: quota.hourly_used,
      hourly_remaining: quota.hourly_remaining,
      next_resume_at: quota.next_resume_at || null,
      last_error: fatalError,
      time: new Date().toISOString(),
      activeTab: {
        id: activeTab?.id || null,
        title: activeTab?.title || "",
        url: currentUrl,
        isTikTok: /tiktok\.com/i.test(currentUrl),
      },
      page: {
        isTikTok: /tiktok\.com/i.test(currentUrl),
        isShopPage: /affiliate-us\.tiktok\.com|seller-us\.tiktok\.com/i.test(currentUrl),
      },
      counts: state.counts || {},
      runTimer: {
        running,
        started_at: state.startedAt || null,
        finished_at: state.finishedAt || null,
      },
      settings: Object.assign({}, settings, {
        hourly_limit: quota.hourly_limit,
        hourly_used: quota.hourly_used,
        hourly_remaining: quota.hourly_remaining,
        next_resume_at: quota.next_resume_at || null,
      }),
      latestLog: { message: state.lastStatus || reason },
      reason,
    };
    attachShopActorIdentity(payload, actor);
    for (const base of await buildApiBaseOrder(settings.endpoint)) {
      try {
        const resp = await fetchWithTimeout(joinPath(base, "/api/local/extension/launcher-heartbeat"), {
          method: "POST",
          credentials: "include",
          headers: await getShopAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload),
        }, 15000);
        const body = await parseJsonResponse(resp);
        if (!resp.ok) {
          const detail = shopResponseDetail(body, `heartbeat_http_${resp.status}`);
          await chrome.storage.local.set({
            [X9_LAST_HEARTBEAT_KEY]: {
              ok: false,
              status: resp.status,
              detail,
              at: new Date().toISOString(),
              actor_user_id: payload.actor_user_id || null,
            },
          }).catch(() => undefined);
          const error = new Error(detail);
          error.status = resp.status;
          throw error;
        }
        await chrome.storage.local.set({
          [X9_LAST_HEARTBEAT_KEY]: {
            ok: true,
            status: resp.status,
            detail: "",
            at: new Date().toISOString(),
            actor_user_id: payload.actor_user_id || null,
          },
        }).catch(() => undefined);
        await chrome.storage.local.set({ [X9_API_BASE_ACTIVE_KEY]: base }).catch(() => undefined);
        break;
      } catch (err) {
        await chrome.storage.local.set({
          [X9_LAST_HEARTBEAT_KEY]: {
            ok: false,
            status: Number(err && err.status) || 0,
            detail: String(err && err.message || err || "heartbeat_failed"),
            at: new Date().toISOString(),
            actor_user_id: payload.actor_user_id || null,
          },
        }).catch(() => undefined);
        await patchState({ lastError: `heartbeat:${String(err && err.message || err)}` }).catch(() => undefined);
      }
    }
  }

  function missingBundledActorError() {
    return new Error("x9_login_required_download_plugin_again");
  }

  async function uploadObservation(observation, endpoint) {
    if (!observation || !observation.creator || !observation.creator.handle) throw new Error("observation missing creator.handle");
    observation = compactObservationForUpload(observation);
    const identity = await ensureShopWorkerIdentity();
    const actor = await resolveShopActorIdentity();
    if (!actor || !actor.id) {
      throw missingBundledActorError();
    }
    observation.extension_id = identity.extensionId;
    observation.worker_id = identity.workerId;
    observation.account_id = identity.accountId;
    attachShopActorIdentity(observation, actor);
    const bodyText = JSON.stringify(observation);
    const failures = [];
    for (const ep of await buildUploadEndpointOrder(endpoint)) {
      try {
        const resp = await fetchWithTimeout(ep, {
          method: "POST",
          credentials: "include",
          headers: await getShopAuthHeaders({ "Content-Type": "application/json", "X-X9-Submit-Only": "1" }),
          body: bodyText,
        }, SHOP_UPLOAD_TIMEOUT_MS);
        let body = await parseJsonResponse(resp);
        if (!resp.ok || (body && body.ok === false)) {
          const detail = (body && (body.detail || body.error)) || `HTTP ${resp.status}`;
          failures.push(`${endpointLabel(ep)} ${detail}`);
          continue;
        }
        await chrome.storage.local.set({
          [X9_LAST_OBSERVATION_UPLOAD_KEY]: {
            ok: true,
            status: resp.status,
            detail: "",
            actor_user_id: observation.actor_user_id || null,
            handle: observation.creator.handle,
            uploaded_at: new Date().toISOString(),
          },
        }).catch(() => undefined);
        await setActiveApiBaseFromEndpoint(ep);
        return { body: body || { ok: true }, endpoint: ep };
      } catch (err) {
        const primaryMessage = String(err && err.message || err);
        if (isFetchTransportError(err)) {
          try {
            const fallbackResp = await fetchWithTimeout(ep, {
              method: "POST",
              credentials: "include",
              headers: await getShopAuthHeaders({ "Content-Type": "text/plain;charset=UTF-8", "X-X9-Submit-Only": "1" }),
              body: bodyText,
            }, SHOP_UPLOAD_TIMEOUT_MS);
            const fallbackBody = await parseJsonResponse(fallbackResp);
            if (!fallbackResp.ok || (fallbackBody && fallbackBody.ok === false)) {
              const detail = (fallbackBody && (fallbackBody.detail || fallbackBody.error)) || `HTTP ${fallbackResp.status}`;
              failures.push(`${endpointLabel(ep)} json:${primaryMessage}; text:${detail}`);
              continue;
            }
            await chrome.storage.local.set({
              [X9_LAST_OBSERVATION_UPLOAD_KEY]: {
                ok: true,
                status: fallbackResp.status,
                detail: "",
                actor_user_id: observation.actor_user_id || null,
                handle: observation.creator.handle,
                uploaded_at: new Date().toISOString(),
              },
            }).catch(() => undefined);
            await setActiveApiBaseFromEndpoint(ep);
            return { body: fallbackBody || { ok: true }, endpoint: ep, transport: "text_plain" };
          } catch (fallbackErr) {
            failures.push(`${endpointLabel(ep)} json:${primaryMessage}; text:${String(fallbackErr && fallbackErr.message || fallbackErr)}`);
            continue;
          }
        }
        failures.push(`${endpointLabel(ep)} ${primaryMessage}`);
      }
    }
    const failureMessage = failures.join(" | ") || "upload_failed";
    await chrome.storage.local.set({
      [X9_LAST_OBSERVATION_UPLOAD_KEY]: {
        ok: false,
        status: 0,
        detail: failureMessage,
        actor_user_id: observation.actor_user_id || null,
        handle: observation.creator.handle,
        uploaded_at: new Date().toISOString(),
      },
    }).catch(() => undefined);
    throw new Error(failureMessage);
  }

  async function buildUploadEndpointOrder(preferred) {
    const out = [];
    const addEndpoint = (ep) => {
      const val = normalizeEndpoint(ep);
      if (val && !out.includes(val)) out.push(val);
    };
    const preferredEndpoint = normalizeEndpoint(preferred || DEFAULT_SETTINGS.endpoint);
    if (isAllowedCollectorEndpoint(preferredEndpoint)) addEndpoint(preferredEndpoint);
    for (const base of await getDashboardBaseCandidates()) addEndpoint(joinPath(base, UPLOAD_PATH));
    for (const base of await getStoredApiBases()) addEndpoint(joinPath(base, UPLOAD_PATH));
    for (const base of UPLOAD_BASES) addEndpoint(joinPath(base, UPLOAD_PATH));
    return out;
  }

  function normalizeEndpoint(endpoint) {
    return String(endpoint || "").trim().replace(/\/+$/, "");
  }

  function joinPath(base, path) {
    return `${String(base || "").replace(/\/+$/, "")}${path}`;
  }

  function endpointLabel(endpoint) {
    try {
      const parsed = new URL(endpoint);
      return `${parsed.origin}${parsed.pathname}`;
    } catch {
      return endpoint || "unknown_endpoint";
    }
  }

  function isAllowedCollectorEndpoint(endpoint) {
    try {
      const parsed = new URL(endpoint);
      return allowedApiBase(parsed.origin) && parsed.pathname.endsWith(UPLOAD_PATH);
    } catch {
      return false;
    }
  }

  function fetchWithTimeout(url, init, timeoutMs) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    return fetch(url, Object.assign({}, init || {}, { signal: controller.signal }))
      .catch((err) => {
        const name = String(err && err.name || "");
        const message = String(err && err.message || err || "");
        if (timedOut || name === "AbortError" || message.includes("aborted")) {
          const e = new Error(`request_response_timeout_${Math.round((timeoutMs || 0) / 1000)}s`);
          e.name = "X9UploadTimeout";
          throw e;
        }
        throw err;
      })
      .finally(() => clearTimeout(timer));
  }

  function isFetchTransportError(err) {
    const name = String(err && err.name || "");
    const message = String(err && err.message || err || "");
    return name === "TypeError"
      || message.includes("Failed to fetch")
      || message.includes("NetworkError")
      || message.includes("Load failed");
  }

  async function parseJsonResponse(resp) {
    try { return await resp.json(); } catch (_) { return null; }
  }

  function shopResponseDetail(body, fallback) {
    const raw = body && (body.detail || body.error || body.message);
    if (typeof raw === "string") return raw;
    if (raw) {
      try { return JSON.stringify(raw); } catch (_) { return String(raw); }
    }
    return fallback || "";
  }

  function buildPendingUploadKey(observation, meta) {
    const handle = (observation && observation.creator && observation.creator.handle) || (meta && meta.handle) || "";
    return [
      observation && observation.run_id || "",
      observation && observation.lead_status || "",
      handle,
      observation && observation.collected_at || "",
    ].join("|").toLowerCase();
  }

  async function enqueuePendingUpload(observation, endpoint, meta, error) {
    const got = await chrome.storage.local.get([SHOP_PENDING_UPLOADS_KEY]).catch(() => ({}));
    const queue = Array.isArray(got[SHOP_PENDING_UPLOADS_KEY]) ? got[SHOP_PENDING_UPLOADS_KEY] : [];
    const key = buildPendingUploadKey(observation, meta);
    if (!key) return;
    observation = compactObservationForUpload(observation);
    const existing = queue.find((item) => item && item.key === key);
    const nextAttemptAt = Date.now() + 60_000;
    if (existing) {
      existing.endpoint = endpoint || existing.endpoint;
      existing.meta = Object.assign({}, existing.meta || {}, meta || {});
      existing.last_error = String(error || existing.last_error || "");
      existing.next_attempt_at = Math.min(Number(existing.next_attempt_at) || nextAttemptAt, nextAttemptAt);
    } else {
      queue.push({
        key,
        observation,
        endpoint,
        meta: meta || {},
        attempts: 0,
        last_error: String(error || ""),
        created_at: new Date().toISOString(),
        next_attempt_at: nextAttemptAt,
      });
    }
    await chrome.storage.local.set({ [SHOP_PENDING_UPLOADS_KEY]: queue.slice(-SHOP_PENDING_UPLOAD_LIMIT) }).catch(() => undefined);
  }

  let pendingFlushActive = false;

  async function flushPendingUploads(reason) {
    if (pendingFlushActive) return;
    pendingFlushActive = true;
    try {
      const got = await chrome.storage.local.get([SHOP_PENDING_UPLOADS_KEY]).catch(() => ({}));
      const queue = Array.isArray(got[SHOP_PENDING_UPLOADS_KEY]) ? got[SHOP_PENDING_UPLOADS_KEY] : [];
      if (queue.length === 0) return;
      const nowMs = Date.now();
      const keep = [];
      const ready = [];
      let sent = 0;
      for (const item of queue) {
        if (!item || !item.observation) continue;
        if (ready.length >= SHOP_PENDING_FLUSH_BATCH_LIMIT || (Number(item.next_attempt_at) || 0) > nowMs) {
          keep.push(item);
          continue;
        }
        ready.push(item);
      }
      let lastEndpoint = "";
      let lastHandle = "";
      const failed = [];
      async function sendPendingItem(item) {
        try {
          const result = await uploadObservation(item.observation, item.endpoint);
          sent += 1;
          lastEndpoint = result.endpoint || item.endpoint || lastEndpoint;
          lastHandle = item.meta?.handle || item.observation?.creator?.handle || lastHandle || "unknown";
        } catch (err) {
          const attempts = (Number(item.attempts) || 0) + 1;
          const backoffMs = Math.min(10 * 60_000, 30_000 * Math.max(1, attempts));
          failed.push(Object.assign({}, item, {
            observation: compactObservationForUpload(item.observation),
            attempts,
            last_error: String(err && err.message || err),
            next_attempt_at: Date.now() + backoffMs,
          }));
        }
      }
      const workers = Array.from({ length: Math.min(SHOP_UPLOAD_FLUSH_CONCURRENCY, ready.length) }, async () => {
        while (ready.length > 0) {
          const item = ready.shift();
          if (item) await sendPendingItem(item);
        }
      });
      await Promise.all(workers);
      keep.push(...failed);
      await chrome.storage.local.set({ [SHOP_PENDING_UPLOADS_KEY]: keep.slice(-SHOP_PENDING_UPLOAD_LIMIT) }).catch(() => undefined);
      if (sent > 0) {
        const cur = await getState();
        await patchState({
          settings: Object.assign({}, cur.settings, lastEndpoint ? { endpoint: lastEndpoint } : {}),
          lastStatus: `pending uploads sent ${sent}${lastHandle ? ` @${lastHandle}` : ""}`,
        });
        postShopHeartbeat(`pending_flush_${reason || "manual"}`).catch(() => undefined);
      }
    } finally {
      pendingFlushActive = false;
    }
  }

  function queueObservationUpload(observation, endpoint, meta) {
    const handle = (observation && observation.creator && observation.creator.handle) || (meta && meta.handle) || "unknown";
    const kind = (meta && meta.kind) || "detail";
    return uploadObservation(observation, endpoint)
      .then(async (result) => {
        const cur = await getState();
        await patchState({
          settings: Object.assign({}, cur.settings, { endpoint: result.endpoint || endpoint }),
          lastStatus: kind === "list" ? `backend accepted list @${handle}` : `backend accepted detail @${handle}`,
          counts: {
            listItems: cur.counts.listItems,
            listUploads: cur.counts.listUploads + (kind === "list" ? 1 : 0),
            listUploadFail: cur.counts.listUploadFail,
            detailDone: cur.counts.detailDone,
            detailFail: cur.counts.detailFail,
            errors: cur.counts.errors,
          },
        });
        postShopHeartbeat(`upload_${kind}_ok`).catch(() => undefined);
        flushPendingUploads(`after_${kind}_ok`).catch(() => undefined);
        return { ok: true, result };
      })
      .catch(async (err) => {
        const cur = await getState();
        const message = String(err && err.message || err);
        const friendly = friendlyUploadError(message);
        await patchState({
          lastError: `upload:${handle}: ${friendly}`,
          lastStatus: kind === "list" ? `列表上传未确认，已加入待重试队列 @${handle}` : `上传响应未确认，已加入待重试队列 @${handle}`,
          counts: {
            listItems: cur.counts.listItems,
            listUploads: cur.counts.listUploads,
            listUploadFail: cur.counts.listUploadFail + (kind === "list" ? 1 : 0),
            detailDone: cur.counts.detailDone,
            detailFail: cur.counts.detailFail,
            errors: cur.counts.errors + 1,
          },
        });
        await enqueuePendingUpload(compactObservationForUpload(observation), endpoint, meta, message);
        postShopHeartbeat(`upload_${kind}_error`).catch(() => undefined);
        return { ok: false, error: message };
      });
  }

  function friendlyUploadError(message) {
    const text = String(message || "");
    if (text.includes("x9_login_required_download_plugin_again") || text.includes("HTTP 401") || text.includes("HTTP 409") || text.includes("login required")) {
      return "Please log in to X9 and download the extension again.";
    }
    if (false) {
      const code = (text.match(/bind_code=([A-Z0-9]+)/i) || [])[1] || "";
      const url = (text.match(/bind_url=(https?:\/\/\S+)/i) || [])[1] || "";
      if (code || url) {
        return `采集窗口已生成跨窗口绑定码 ${code || ""}${url ? `；在已登录窗口打开 ${url}` : ""}`;
      }
      return "采集窗口未绑定系统账号，先在已登录窗口批准绑定码";
    }
    if (text.includes("request_response_timeout") || text.includes("aborted")) {
      return "上传响应超时，数据已加入本地待重试队列；后台可能已经收到";
    }
    if (text.includes("HTTP 500")) {
      return "上传接口 500，数据已加入本地待重试队列";
    }
    if (text.includes("Failed to fetch") || text.includes("NetworkError") || text.includes("Load failed")) {
      return "网络连接失败，数据已加入本地待重试队列";
    }
    return text || "上传未确认，数据已加入本地待重试队列";
  }

  function compactObservationForUpload(observation) {
    if (!observation || observation.lead_status !== "shop_profile_collected") return observation;
    const shop = observation.tiktok_shop;
    if (!shop || typeof shop !== "object") return observation;
    const rawCapture = shop.raw_capture && typeof shop.raw_capture === "object" ? shop.raw_capture : {};
    const compactShop = Object.assign({}, shop, {
      raw_capture: compactRawCapture(rawCapture),
      raw_visible_text: trimUploadText(shop.raw_visible_text, DETAIL_UPLOAD_VISIBLE_TEXT_LIMIT),
      raw_dom_omitted: true,
    });
    delete compactShop.raw_dom_html;
    return Object.assign({}, observation, { tiktok_shop: compactShop });
  }

  function compactRawCapture(rawCapture) {
    const links = Array.isArray(rawCapture.links) ? rawCapture.links : [];
    return {
      page_title: trimUploadText(rawCapture.page_title, 300) || null,
      page_type: rawCapture.page_type || "creator_detail",
      captured_at: rawCapture.captured_at || null,
      links: links.map((link) => trimUploadText(link, 600)).filter(Boolean).slice(0, DETAIL_UPLOAD_LINK_LIMIT),
      raw_dom_omitted: true,
    };
  }

  function trimUploadText(value, limit) {
    const text = String(value || "");
    return text.length > limit ? text.slice(0, limit) : text;
  }

  function buildListObservation(item, state) {
    return {
      event_type: "creator_observation", platform: "tiktok_shop",
      source: state.settings.source, worker_id: state.settings.workerId,
      extension_id: state.settings.extensionId || runtimeExtensionId(),
      account_id: state.settings.accountId || state.settings.workerId,
      run_id: state.runId,
      creator: {
        handle: item.handle, display_name: item.display_name,
        profile_url: item.profile_url, shop_profile_url: item.shop_profile_url,
        avatar_url: item.avatar_url, followers_raw: item.followers_raw,
        followers_count: item.followers_count,
      },
      tiktok_shop: { list_item: item }, lead_status: "shop_list_seen",
      collected_at: item.collected_at || new Date().toISOString(),
    };
  }
  function enrichDetail(observation, state) {
    return Object.assign({}, observation, {
      source: state.settings.source, worker_id: state.settings.workerId,
      extension_id: state.settings.extensionId || runtimeExtensionId(),
      account_id: state.settings.accountId || state.settings.workerId,
      run_id: state.runId, collected_at: observation.collected_at || new Date().toISOString(),
    });
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || typeof message.type !== "string") return false;
    if (message.type === MSG.SHOP_START) { handleStart(message).then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.SHOP_STOP) { handleStop().then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.SHOP_GET_STATE) { getState().then((s) => sendResponse({ ok: true, state: s })).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.SHOP_RESET_COUNTS) { resetCounts().then(sendResponse).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.SHOP_SET_SETTINGS) { patchState({ settings: message.settings || {} }).then((s) => sendResponse({ ok: true, state: s })).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.CS_LIST_BATCH) { handleListBatch(message).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.CS_LIST_DONE) { handleListDone(message, sender).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: String(e && e.message || e) })); return true; }
    if (message.type === MSG.CS_PROGRESS) { handleProgress(message).then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false })); return true; }
    if (message.type === MSG.CS_ERROR) { handleCsError(message).then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false })); return true; }
    return false;
  });

  async function handleStart(message) {
    const cur = await getState();
    let settings = Object.assign({}, DEFAULT_SETTINGS, cur.settings || {}, message.settings || {});
    settings = await ensureShopSettings(settings);
    const taskCount = Math.max(1, parseInt(settings.taskCount, 10) || 20);
    settings.taskCount = taskCount;
    try {
      const actor = await resolveShopActorIdentity();
      if (!actor || !actor.id) throw missingBundledActorError();
    } catch (err) {
      const message = friendlyUploadError(String(err && err.message || err));
      await patchState({
        status: "error",
        phase: "idle",
        lastError: `actor:${message}`,
        lastStatus: message,
      });
      return { ok: false, error: message };
    }
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab || !activeTab.id) return { ok: false, error: "no_active_tab" };
    if (!activeTab.url || !/affiliate-us\.tiktok\.com|seller-us\.tiktok\.com/i.test(activeTab.url)) {
      return { ok: false, error: "active_tab_is_not_tiktok_shop", url: activeTab.url };
    }
    const runId = "run-" + new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
    await setState(Object.assign({}, DEFAULT_STATE, {
      status: "running", phase: "list_scanning", runId,
      listTabId: activeTab.id, startedAt: new Date().toISOString(), settings,
    }));
    await getQuotaStatus();
    detailLoopActive = false;
    postShopHeartbeat("start").catch(() => undefined);
    console.log(TAG, "START runId=" + runId, "tab=" + activeTab.id, "taskCount=" + taskCount);
    try {
      await chrome.tabs.sendMessage(activeTab.id, { type: MSG.CS_AUTO_FULL_RUN, runId, taskCount });
    } catch (err) {
      console.warn(TAG, "sendMessage failed:", err && err.message);
      try {
        await chrome.scripting.executeScript({ target: { tabId: activeTab.id }, files: ["contentScript.js", "shop_collector.js"] });
        await chrome.tabs.sendMessage(activeTab.id, { type: MSG.CS_AUTO_FULL_RUN, runId, taskCount });
      } catch (e2) {
        console.error(TAG, "inject+retry failed", e2);
        await patchState({ status: "error", phase: "idle", lastError: String(e2 && e2.message || e2) });
        return { ok: false, error: String(e2 && e2.message || e2) };
      }
    }
    return { ok: true, runId, taskCount };
  }

  async function handleStop() {
    const state = await getState();
    console.log(TAG, "STOP");
    detailLoopActive = false;
    if (pendingDetailResolve) { try { pendingDetailResolve({ aborted: true }); } catch (_) {} pendingDetailResolve = null; }
    await patchState({ status: "paused", phase: "idle", currentHandle: null });
    postShopHeartbeat("stop").catch(() => undefined);
    if (state.listTabId) { try { await chrome.tabs.sendMessage(state.listTabId, { type: MSG.CS_AUTO_STOP }); } catch (_) {} }
    if (state.detailTabId) {
      try { await chrome.tabs.remove(state.detailTabId); } catch (_) {}
      await patchState({ detailTabId: null });
    }
    return { ok: true };
  }

  async function resetCounts() {
    detailLoopActive = false;
    const cur = await getState();
    await setState(Object.assign({}, DEFAULT_STATE, { settings: cur.settings }));
    return { ok: true };
  }

  async function handleListBatch(message) {
    const state = await getState();
    if (state.status !== "running") return;
    const items = Array.isArray(message.items) ? message.items : [];
    const taskCount = Math.max(1, parseInt(state.settings.taskCount, 10) || 20);
    const handlesAdd = []; let queuedUploads = 0;
    for (const item of items) {
      if (!item || !item.handle) continue;
      if (state.handles.length + handlesAdd.length >= taskCount &&
          !state.handles.includes(item.handle) && !handlesAdd.includes(item.handle)) continue;
      if (!state.handles.includes(item.handle) && !handlesAdd.includes(item.handle)) handlesAdd.push(item.handle);
      queueObservationUpload(buildListObservation(item, state), state.settings.endpoint, { kind: "list", handle: item.handle });
      queuedUploads += 1;
    }
    const merged = state.handles.concat(handlesAdd.filter((h) => !state.handles.includes(h)));
    console.log(TAG, "list_batch items=" + items.length, "queued=" + queuedUploads, "queue=" + merged.length + "/" + taskCount);
    await patchState({
      handles: merged,
      lastStatus: `列表已发现 ${merged.length}/${taskCount}，本批排队上传 ${queuedUploads}`,
      counts: {
        listItems: state.counts.listItems + queuedUploads,
        listUploads: state.counts.listUploads,
        listUploadFail: state.counts.listUploadFail,
        detailDone: state.counts.detailDone, detailFail: state.counts.detailFail,
        errors: state.counts.errors,
      },
    });
  }

  async function handleListDone(message, sender) {
    const state = await getState();
    if (state.status !== "running") return;
    const raw = Array.isArray(message.handles) ? message.handles : state.handles;
    const taskCount = Math.max(1, parseInt(state.settings.taskCount, 10) || 20);
    const handles = raw.slice(0, taskCount);
    console.log(TAG, "list DONE raw=" + raw.length + " cap=" + taskCount + " queue=" + handles.length);
    await patchState({
      phase: "detail_scanning", handles, queueIndex: 0,
      listTabId: state.listTabId || (sender && sender.tab && sender.tab.id) || null,
      lastStatus: `列表完成，详情队列 ${handles.length}/${taskCount}`,
    });
    if (!detailLoopActive) runDetailLoop().catch(async (e) => {
      console.error(TAG, "detail loop crashed", e);
      const cur = await getState();
      patchState({
        status: "error",
        phase: "idle",
        lastError: "detail_loop:" + String(e && e.message || e),
        lastStatus: "详情循环异常，已停止",
        counts: {
          listItems: cur.counts.listItems,
          listUploads: cur.counts.listUploads,
          listUploadFail: cur.counts.listUploadFail,
          detailDone: cur.counts.detailDone,
          detailFail: cur.counts.detailFail,
          errors: cur.counts.errors + 1,
        },
      });
    });
  }

  async function runDetailLoop() {
    if (detailLoopActive) return;
    detailLoopActive = true;
    try {
      let state = await getState();
      console.log(TAG, "runDetailLoop start queue=" + state.handles.length);
      while (detailLoopActive && state.status === "running" && state.queueIndex < state.handles.length) {
        await waitForDetailPace();
        const handle = state.handles[state.queueIndex];
        const pos = `${state.queueIndex + 1}/${state.handles.length}`;
        console.log(TAG, `--- detail ${pos} @${handle} ---`);
        await patchState({ currentHandle: handle, lastStatus: `打开详情 ${pos} @${handle}` });
        let observation = null, phaseError = null, detailTabId = null;
        try {
          detailTabId = await openDetailForHandle(state.listTabId, handle, 15000);
          console.log(TAG, "detail tab", detailTabId, "@" + handle);
          await patchState({ detailTabId, lastStatus: `详情页已打开 ${pos} @${handle}` });
          observation = await scrapeDetailTab(detailTabId, 18000, handle);
          console.log(TAG, "scraped @" + handle);
          await patchState({ lastStatus: `已提取详情 ${pos} @${handle}，准备投递后端` });
        } catch (err) {
          phaseError = String(err && err.message || err);
          console.warn(TAG, "detail failed @" + handle, phaseError);
        } finally {
          if (detailTabId != null) {
            try { await chrome.tabs.remove(detailTabId); console.log(TAG, "closed tab", detailTabId); }
            catch (e) { console.warn(TAG, "close failed", e && e.message); }
            await patchState({ detailTabId: null });
          }
        }
        if (observation) {
          const enriched = enrichDetail(observation, state);
          const hf = (enriched.creator && enriched.creator.handle) || handle;
          const cur = await getState();
          await patchState({
            doneHandles: cur.doneHandles.concat(cur.doneHandles.includes(hf) ? [] : [hf]),
            lastStatus: `已提取详情 ${pos} @${hf}，已交给后端队列`,
            counts: {
              listItems: cur.counts.listItems, listUploads: cur.counts.listUploads,
              listUploadFail: cur.counts.listUploadFail,
              detailDone: cur.counts.detailDone + 1,
              detailFail: cur.counts.detailFail, errors: cur.counts.errors,
            },
          });
          const updatedQuota = await recordDetailUploadForQuota();
          await patchState({ nextResumeAt: updatedQuota.next_resume_at || null });
          await queueObservationUpload(enriched, state.settings.endpoint, { kind: "detail", handle: hf });
        }
        if (phaseError) {
          const cur = await getState();
          await patchState({
            lastError: phaseError,
            lastStatus: `详情失败 ${pos} @${handle}`,
            counts: {
              listItems: cur.counts.listItems, listUploads: cur.counts.listUploads,
              listUploadFail: cur.counts.listUploadFail,
              detailDone: cur.counts.detailDone,
              detailFail: cur.counts.detailFail + 1,
              errors: cur.counts.errors + 1,
            },
          });
        }
        const adv = await getState();
        await patchState({ queueIndex: adv.queueIndex + 1 });
        await sleep(SHOP_POST_DETAIL_DELAY_MS);
        state = await getState();
      }
      if (state.status === "running") {
        await patchState({ status: "done", phase: "finished", finishedAt: new Date().toISOString(), currentHandle: null, lastStatus: "采集完成，数据已交给后端队列" });
        postShopHeartbeat("done").catch(() => undefined);
        console.log(TAG, "ALL DONE list=" + state.handles.length, "ok=" + state.counts.detailDone, "fail=" + state.counts.detailFail);
        const final = await getState();
        try {
          const total = final.counts.detailDone + final.counts.detailFail;
          if (chrome.notifications && chrome.notifications.create) {
            chrome.notifications.create({
              type: "basic",
              iconUrl: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
              title: "TikTok Shop 采集完成",
              message: `列表 ${final.handles.length} · 已提取 ${final.counts.detailDone}/${total}`,
            }, () => void chrome.runtime.lastError);
          }
        } catch (_) {}
      }
    } finally { detailLoopActive = false; }
  }

  function openDetailForHandle(listTabId, handle, maxMs) {
    return new Promise(async (resolve, reject) => {
      if (!listTabId) return reject(new Error("no_list_tab"));
      let settled = false, createdTabId = null, cleanupTimer = null, mainTimer = null;
      function onCreated(tab) {
        const isFromList = tab.openerTabId === listTabId;
        const isDetail = tab.url && /\/connection\/creator\/detail/i.test(tab.url);
        if (settled) {
          if (tab.id !== createdTabId && isFromList) {
            console.log(TAG, "closing dup detail tab", tab.id);
            try { chrome.tabs.remove(tab.id); } catch (_) {}
          }
          return;
        }
        if (isFromList || isDetail) {
          createdTabId = tab.id; settled = true;
          if (mainTimer) { clearTimeout(mainTimer); mainTimer = null; }
          cleanupTimer = setTimeout(finalize, 2500);
          resolve(createdTabId);
        }
      }
      function onUpdated(tabId, info, tab) {
        if (settled || !tab || !tab.url) return;
        if (!/\/connection\/creator\/detail/i.test(tab.url)) return;
        if (tab.openerTabId === listTabId || tabId === createdTabId) {
          createdTabId = tabId; settled = true;
          if (mainTimer) { clearTimeout(mainTimer); mainTimer = null; }
          cleanupTimer = setTimeout(finalize, 2500);
          resolve(createdTabId);
        }
      }
      function finalize() {
        try { chrome.tabs.onCreated.removeListener(onCreated); } catch (_) {}
        try { chrome.tabs.onUpdated.removeListener(onUpdated); } catch (_) {}
        pendingDetailResolve = null;
      }
      chrome.tabs.onCreated.addListener(onCreated);
      chrome.tabs.onUpdated.addListener(onUpdated);
      mainTimer = setTimeout(() => {
        if (settled) return;
        settled = true; finalize();
        reject(new Error("detail_tab_did_not_open_in_" + maxMs + "ms"));
      }, maxMs);
      pendingDetailResolve = (out) => {
        if (out && out.aborted && !settled) { settled = true; finalize(); reject(new Error("aborted")); }
      };
      console.log(TAG, "CLICK_ROW @" + handle, "->", listTabId);
      try {
        await chrome.tabs.sendMessage(listTabId, { type: MSG.CS_CLICK_ROW, handle });
      } catch (e) {
        console.warn(TAG, "CLICK_ROW send failed", e && e.message);
        if (!settled) { settled = true; finalize(); reject(new Error("click_send_failed:" + String(e && e.message || e))); }
      }
    });
  }

  async function scrapeDetailTab(detailTabId, maxMs, expectedHandle) {
    console.log(TAG, "wait tab", detailTabId);
    await waitForTabComplete(detailTabId, maxMs);
    console.log(TAG, "tab loaded, sleeping 600ms");
    await sleep(600);
    let lastErr = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        console.log(TAG, "SCAN_DETAIL_NOW try " + (attempt + 1));
        const resp = await sendToTab(detailTabId, { type: MSG.CS_SCAN_DETAIL_NOW, expectedHandle });
        if (resp && resp.ok && resp.observation) return resp.observation;
        lastErr = resp && resp.error ? resp.error : "no_observation";
        console.warn(TAG, "scan resp not ok:", resp);
      } catch (e) {
        lastErr = String(e && e.message || e);
        console.warn(TAG, "scan ping threw:", lastErr);
        try { await chrome.scripting.executeScript({ target: { tabId: detailTabId }, files: ["shop_collector.js"] }); }
        catch (e2) { console.warn(TAG, "inject also threw:", e2 && e2.message); }
      }
      await sleep(800);
    }
    throw new Error("detail_scrape_failed:" + (lastErr || "unknown"));
  }

  function waitForTabComplete(tabId, maxMs) {
    return new Promise((resolve, reject) => {
      const t0 = Date.now();
      function check() {
        chrome.tabs.get(tabId, (tab) => {
          if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
          if (tab && tab.status === "complete") return resolve(tab);
          if (Date.now() - t0 > maxMs) return reject(new Error("tab_load_timeout_" + maxMs + "ms"));
          setTimeout(check, 350);
        });
      }
      check();
    });
  }
  function sendToTab(tabId, message) {
    return new Promise((resolve, reject) => {
      try {
        chrome.tabs.sendMessage(tabId, message, (resp) => {
          if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
          resolve(resp);
        });
      } catch (e) { reject(e); }
    });
  }
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  async function handleProgress(message) {
    const state = await getState();
    if (state.status !== "running") return;
    const patch = {};
    if (message.phase) patch.phase = message.phase;
    if (message.currentHandle !== undefined) patch.currentHandle = message.currentHandle || null;
    await patchState(patch);
  }
  async function handleCsError(message) {
    const state = await getState();
    console.warn(TAG, "CS error:", message.phase, message.message || message.handle);
    await patchState({
      lastError: `${message.phase || "error"}: ${message.message || message.handle || "(no detail)"}`,
      counts: {
        listItems: state.counts.listItems, listUploads: state.counts.listUploads,
        listUploadFail: state.counts.listUploadFail,
        detailDone: state.counts.detailDone, detailFail: state.counts.detailFail,
        errors: state.counts.errors + 1,
      },
    });
  }

  globalThis.X9_SHOP_COMMANDS = {
    start(settings) {
      return handleStart({ settings: settings || {} });
    },
    stop() {
      return handleStop();
    },
    setSettings(settings) {
      return patchState({ settings: settings || {} }).then((state) => ({ ok: true, state }));
    },
  };

  chrome.tabs.onRemoved.addListener(async (tabId) => {
    const state = await getState();
    if (state.status !== "running") return;
    if (tabId === state.listTabId) {
      console.warn(TAG, "list tab closed — pausing");
      detailLoopActive = false;
      await patchState({ status: "paused", phase: "idle", lastError: "list_tab_closed", currentHandle: null });
    }
  });
})();
