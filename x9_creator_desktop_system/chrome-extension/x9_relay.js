const X9_STORAGE_KEY = "tclabState";
const X9_RELAYED_KEYS = "x9_relayed_keys";
const X9_API_BASE_KEY = "x9_api_base";          // user override stored here
const X9_API_BASE_ACTIVE_KEY = "x9_api_base_active";  // last-known-good
const X9_HEARTBEAT_ALARM = "x9-relay-heartbeat";
const X9_COMMAND_ALARM = "x9-dashboard-commands";
const X9_DASHBOARD_COMMAND_MESSAGE = "X9_DASHBOARD_COMMAND";
const X9_LEGACY_WORKER_IDS = [
  "tiktok_creator_lead_browser_1_0_19",
  "tiktok_shop_creator_lead_browser_2_2",
];

// Candidates tried in order when no user override is set. Whichever responds
// first to a heartbeat becomes the cached "active" base.
const X9_API_BASE_CANDIDATES = [
  "https://usx9.us",
];

function joinPath(base, path) {
  return `${String(base).replace(/\/+$/, "")}${path}`;
}

function normalizeApiBase(base) {
  return String(base || "").replace(/\/+$/, "");
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
  } catch {
    return "";
  }
}

async function getDashboardBaseCandidates() {
  const [activeTabs, allTabs] = await Promise.all([
    chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []),
    chrome.tabs.query({}).catch(() => []),
  ]);
  const orderedTabs = [...activeTabs, ...allTabs];
  const bases = [];
  for (const tab of orderedTabs) {
    const base = dashboardBaseFromUrl(tab?.url);
    if (base && !bases.includes(base)) {
      bases.push(base);
    }
  }
  return bases;
}

async function getStoredApiBase() {
  const o = await chrome.storage.local.get([X9_API_BASE_KEY, X9_API_BASE_ACTIVE_KEY]);
  return { override: o[X9_API_BASE_KEY] || "", active: o[X9_API_BASE_ACTIVE_KEY] || "" };
}

async function setActiveApiBase(base) {
  await chrome.storage.local.set({ [X9_API_BASE_ACTIVE_KEY]: base });
}

async function getCandidateOrder() {
  const stored = await getStoredApiBase();
  const override = allowedApiBase(stored.override);
  const active = allowedApiBase(stored.active);
  // Explicit user override always wins.
  if (override) return [normalizeApiBase(override)];
  // Prefer the currently open X9 dashboard origin, then the last working one.
  const ordered = [];
  for (const base of await getDashboardBaseCandidates()) {
    if (!ordered.includes(base)) ordered.push(base);
  }
  const normalizedActive = normalizeApiBase(active);
  if (normalizedActive && !ordered.includes(normalizedActive)) ordered.push(normalizedActive);
  for (const c of X9_API_BASE_CANDIDATES) {
    const base = normalizeApiBase(c);
    if (base && !ordered.includes(base)) ordered.push(base);
  }
  return ordered;
}

function allowedApiBase(base) {
  const normalized = normalizeApiBase(base);
  if (!normalized) return "";
  try {
    const parsed = new URL(normalized);
    const host = parsed.hostname.toLowerCase();
    if (parsed.protocol === "https:" && (host === "usx9.us" || host.endsWith(".usx9.us"))) {
      return normalized;
    }
  } catch {
    return "";
  }
  chrome.storage.local.remove([X9_API_BASE_KEY, X9_API_BASE_ACTIVE_KEY]).catch(() => undefined);
  return "";
}

chrome.runtime.onInstalled.addListener(() => {
  ensureX9RelayAlarm();
  relayCurrentState("installed").catch(() => undefined);
  pollDashboardCommands().catch(() => undefined);
});

chrome.runtime.onStartup.addListener(() => {
  ensureX9RelayAlarm();
  relayCurrentState("startup").catch(() => undefined);
  pollDashboardCommands().catch(() => undefined);
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === X9_HEARTBEAT_ALARM) {
    relayCurrentState("alarm").catch(() => undefined);
  }
  if (alarm.name === X9_COMMAND_ALARM) {
    pollDashboardCommands().catch(() => undefined);
  }
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || !changes[X9_STORAGE_KEY]) {
    return;
  }
  relayState(changes[X9_STORAGE_KEY].newValue, "storage_change").catch(() => undefined);
});

function ensureX9RelayAlarm() {
  // Chrome MV3 enforces a 30-second minimum alarm period for performance.
  // 0.5 min = 30 s, the tightest cadence allowed. Server's offline threshold
  // is 90 s, so even a missed alarm won't flap the dashboard.
  chrome.alarms.create(X9_HEARTBEAT_ALARM, { periodInMinutes: 0.5 });
  chrome.alarms.create(X9_COMMAND_ALARM, { periodInMinutes: 0.5 });
}

async function relayCurrentState(reason) {
  const result = await chrome.storage.local.get([X9_STORAGE_KEY]);
  await relayState(result[X9_STORAGE_KEY], reason);
}

async function relayState(rawState, reason) {
  const state = normalizeX9State(rawState);
  const ingestBatch = await collectNewIngestItems(state);
  if (ingestBatch.items.length > 0) {
    const base = await resolveApiBase();
    if (base) {
      await postJson(joinPath(base, "/api/local/extension/x9-compat/ingest-creators"),
                     { items: ingestBatch.items, time: new Date().toISOString() });
      await markRelayedKeys(ingestBatch.keys);
    }
  }
  await postHeartbeat(state, reason);
}

// Walk the candidate list and return the first base where the heartbeat
// endpoint responds OK. Result is cached as "active" so we hit it directly
// next time. Cleared if it later fails.
async function resolveApiBase() {
  const candidates = await getCandidateOrder();
  for (const base of candidates) {
    try {
      const r = await fetch(joinPath(base, "/health"), { method: "GET" });
      if (r.ok) {
        await setActiveApiBase(base);
        return base;
      }
    } catch (e) {
      // Try the next candidate
    }
  }
  return null;
}

async function collectNewIngestItems(state) {
  const stored = await chrome.storage.local.get([X9_RELAYED_KEYS]);
  const relayed = new Set(Array.isArray(stored[X9_RELAYED_KEYS]) ? stored[X9_RELAYED_KEYS] : []);
  const nextKeys = new Set(relayed);
  const items = [];

  for (const lead of state.leads) {
    const item = buildLeadIngestItem(lead);
    const key = buildRelayKey(item);
    if (item && key && !relayed.has(key)) {
      items.push(item);
      nextKeys.add(key);
    }
  }

  for (const skipped of state.skippedProfiles) {
    const item = buildSkippedIngestItem(skipped);
    const key = buildRelayKey(item);
    if (item && key && !relayed.has(key)) {
      items.push(item);
      nextKeys.add(key);
    }
  }

  return { items, keys: Array.from(nextKeys).slice(-5000) };
}

async function markRelayedKeys(keys) {
  await chrome.storage.local.set({ [X9_RELAYED_KEYS]: keys });
}

function buildLeadIngestItem(lead) {
  const handle = normalizeHandle(lead.username) || handleFromUrl(lead.profile_url);
  if (!handle) {
    return null;
  }
  const item = {
    handle,
    platform: "tiktok",
    profile_url: lead.profile_url || `https://www.tiktok.com/@${encodeURIComponent(handle)}`,
    display_name: lead.nickname || handle,
    bio: lead.bio || "",
    followers: numericFollowerCount(lead.followers_count, lead.followers_raw),
    followers_raw: lead.followers_raw || "",
    following_raw: lead.following_raw || "",
    likes_raw: lead.likes_raw || "",
    email: lead.email || "",
    emails: parseJsonArray(lead.emails_json || lead.emails),
    external_links: parseJsonArray(lead.external_links),
    visible_text: lead.visible_text || "",
    source_url: lead.source_url || lead.current_url || "",
    source: "tiktok_creator_lead_browser",
    current_status: "prospect",
    search_keyword: lead.search_keyword || "",
    source_video_url: lead.source_video_url || "",
    source_video_title: lead.source_video_title || "",
    source_video_description: lead.source_video_description || "",
    notes: `filter=qualified message=${safeNoteValue(lead.lead_status || "lead_saved")}`,
    last_seen_at: lead.last_seen_at || lead.collected_at || new Date().toISOString(),
  };
  return item;
}

function buildSkippedIngestItem(skipped) {
  const handle = normalizeHandle(skipped.username) || handleFromUrl(skipped.profile_url);
  if (!handle) {
    return null;
  }
  const reason = skipped.reason || "skipped";
  const item = {
    handle,
    platform: "tiktok",
    profile_url: skipped.profile_url || `https://www.tiktok.com/@${encodeURIComponent(handle)}`,
    display_name: skipped.nickname || skipped.username || handle,
    bio: skipped.bio || "",
    followers: numericFollowerCount(skipped.followers_count, skipped.followers_raw),
    followers_raw: skipped.followers_raw || "",
    following_raw: skipped.following_raw || "",
    likes_raw: skipped.likes_raw || "",
    email: skipped.email || "",
    emails: parseJsonArray(skipped.emails_json || skipped.emails),
    external_links: parseJsonArray(skipped.external_links),
    visible_text: skipped.visible_text || "",
    source_url: skipped.source_url || skipped.current_url || "",
    source: "tiktok_creator_lead_browser",
    current_status: "dropped",
    search_keyword: skipped.search_keyword || "",
    source_video_url: skipped.source_video_url || "",
    source_video_title: skipped.source_video_title || "",
    source_video_description: skipped.source_video_description || "",
    notes: `filter=${safeNoteValue(reason)} message=skipped`,
    last_seen_at: skipped.checked_at || skipped.last_seen_at || new Date().toISOString(),
  };
  return item;
}

function buildRelayKey(item) {
  if (!item) {
    return "";
  }
  return [
    item.current_status || "",
    item.profile_url || "",
    item.handle || "",
    item.email || "",
    item.search_keyword || "",
  ].join("|").toLowerCase();
}

async function postHeartbeat(state, reason) {
  const activeTab = await getActiveTab();
  const page = classifyPage(activeTab?.url || "");
  const autoSettings = state.settings.autoSettings || {};
  const leadFilters = state.settings.leadFilters || {};
  const settings = {
    ...state.settings,
    ...autoSettings,
    ...leadFilters,
  };
  const pending = state.pendingProfiles.filter((item) => !item.handled).length;
  const payload = {
    app: "tiktok-creator-lead-browser",
    version: chrome.runtime.getManifest().version,
    source: "x9_relay",
    reason,
    extensionId: chrome.runtime.id,
    time: new Date().toISOString(),
    activeTab: {
      id: activeTab?.id || null,
      title: activeTab?.title || "",
      url: activeTab?.url || "",
      isTikTok: Boolean(activeTab?.url && activeTab.url.includes("tiktok.com")),
    },
    page,
    counts: {
      leads: state.leads.length,
      pending,
      skipped: state.skippedProfiles.length,
      sourceVideos: state.sourceVideos.length,
      taskLogs: state.taskLogs.length,
    },
    runTimer: state.runTimer,
    settings,
    latestLog: state.taskLogs[state.taskLogs.length - 1] || {},
  };
  const base = await resolveApiBase();
  if (!base) return;  // No backend reachable — bail until next alarm.
  try {
    await postJson(joinPath(base, "/api/local/extension/launcher-heartbeat"), payload);
  } catch (e) {
    // If the previously-active base fails, clear it so the next call retries
    // the full candidate list.
    await chrome.storage.local.remove(X9_API_BASE_ACTIVE_KEY);
  }
}

async function pollDashboardCommands() {
  const base = await resolveApiBase();
  if (!base) return;

  for (const workerId of getCommandWorkerIds()) {
    let data = null;
    try {
      const url = joinPath(
        base,
        `/api/local/extension/commands/pending?worker_id=${encodeURIComponent(workerId)}&claim=true&limit=10`
      );
      data = await getJson(url);
    } catch (e) {
      await chrome.storage.local.remove(X9_API_BASE_ACTIVE_KEY);
      return;
    }

    const items = Array.isArray(data?.items) ? data.items : [];
    for (const command of items) {
      await executeDashboardCommand(base, command).catch(() => undefined);
    }
  }
}

function getCommandWorkerIds() {
  const ids = [chrome.runtime.id, ...X9_LEGACY_WORKER_IDS]
    .map((id) => String(id || "").trim())
    .filter(Boolean);
  return Array.from(new Set(ids));
}

async function executeDashboardCommand(base, command) {
  try {
    const payload = parseCommandPayload(command);
    const result = await dispatchDashboardCommand({
      id: command.id,
      command_type: command.command_type,
      worker_id: command.worker_id,
      payload,
    });
    await postJson(joinPath(base, `/api/local/extension/commands/${encodeURIComponent(command.id)}/ack`), {
      status: "done",
      result: result || { ok: true },
    });
  } catch (e) {
    await postJson(joinPath(base, `/api/local/extension/commands/${encodeURIComponent(command.id)}/ack`), {
      status: "error",
      error_message: String(e && e.message || e),
    }).catch(() => undefined);
  }
}

function parseCommandPayload(command) {
  if (command?.payload && typeof command.payload === "object") {
    return command.payload;
  }
  const raw = command?.payload_json;
  if (!raw) return {};
  try {
    return JSON.parse(raw) || {};
  } catch {
    return {};
  }
}

async function dispatchDashboardCommand(command) {
  const type = String(command.command_type || "");
  const payload = command.payload || {};

  if (type === "start_shop_collection" || payload.source === "tiktok_shop") {
    return dispatchShopDashboardCommand(command);
  }

  await openSidePanelIfPossible();
  const response = await sendExtensionMessage({
    type: X9_DASHBOARD_COMMAND_MESSAGE,
    command,
  });
  if (response && response.ok === false) {
    throw new Error(response.error || "dashboard command failed");
  }
  return response || { ok: true };
}

async function dispatchShopDashboardCommand(command) {
  const payload = command.payload || {};
  const maxProfiles = Number(payload.max_profiles ?? payload.maxProfiles ?? payload.task_count ?? payload.taskCount ?? 20);
  const settings = {
    endpoint: payload.endpoint || await resolveCollectorEndpoint(),
    taskCount: Number.isFinite(maxProfiles) && maxProfiles > 0 ? Math.round(maxProfiles) : 20,
  };

  if (command.command_type === "cancel_collection" || command.command_type === "cancel_shop_collection") {
    if (globalThis.X9_SHOP_COMMANDS?.stop) {
      return globalThis.X9_SHOP_COMMANDS.stop();
    }
    return sendExtensionMessage({ type: "TSCLB_SHOP_STOP" });
  }

  if (globalThis.X9_SHOP_COMMANDS?.start) {
    return globalThis.X9_SHOP_COMMANDS.start(settings);
  }
  return sendExtensionMessage({ type: "TSCLB_SHOP_START", settings });
}

async function resolveCollectorEndpoint() {
  const base = await resolveApiBase();
  return joinPath(base || "https://usx9.us", "/api/local/collector/observations");
}

async function openSidePanelIfPossible() {
  if (!chrome.sidePanel?.open) return;
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
  const windowId = tabs[0]?.windowId;
  if (!windowId) return;
  await chrome.sidePanel.open({ windowId }).catch(() => undefined);
  await sleep(500);
}

function sendExtensionMessage(message) {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error("请先打开浏览器插件侧边栏，再从采集页下发任务。"));
          return;
        }
        resolve(response || { ok: true });
      });
    } catch (e) {
      reject(e);
    }
  });
}

async function getJson(url) {
  const response = await fetch(url, { method: "GET" });
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`);
  }
  return response.json().catch(() => ({}));
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
  return tabs[0] || null;
}

function classifyPage(url) {
  const isTikTok = Boolean(url && url.includes("tiktok.com"));
  const isSearch = isTikTok && url.includes("/search");
  const isVideo = isTikTok && /\/@[^/]+\/video\//i.test(url);
  const isProfile = isTikTok && /\/@[^/?#]+/i.test(url) && !isVideo;
  return {
    detected: isTikTok,
    url,
    title: "",
    isTikTok,
    isProfilePage: isProfile,
    isVideoPage: isVideo,
    isSearchVideoPage: isSearch,
    inferredSearchKeyword: inferKeywordFromUrl(url),
    gate: { type: "none", matchedText: "" },
  };
}

function inferKeywordFromUrl(url) {
  if (!url) {
    return "";
  }
  try {
    const parsed = new URL(url);
    const q = parsed.searchParams.get("q") || parsed.searchParams.get("keyword") || "";
    return decodeURIComponent(q).trim();
  } catch {
    return "";
  }
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`POST ${url} failed with ${response.status}`);
  }
  return response.json().catch(() => ({}));
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function normalizeX9State(state) {
  const source = state && typeof state === "object" ? state : {};
  const runTimer = source.runTimer && typeof source.runTimer === "object" ? source.runTimer : {};
  const settings = source.settings && typeof source.settings === "object" ? source.settings : {};
  return {
    leads: Array.isArray(source.leads) ? source.leads : [],
    sourceVideos: Array.isArray(source.sourceVideos) ? source.sourceVideos : [],
    skippedProfiles: Array.isArray(source.skippedProfiles) ? source.skippedProfiles : [],
    taskLogs: Array.isArray(source.taskLogs) ? source.taskLogs : [],
    pendingProfiles: Array.isArray(source.pendingProfiles) ? source.pendingProfiles : [],
    runTimer: {
      running: Boolean(runTimer.running),
      started_at: runTimer.started_at || "",
      started_ms: Number(runTimer.started_ms) || 0,
      ended_at: runTimer.ended_at || "",
      elapsed_ms: Number(runTimer.elapsed_ms) || 0,
    },
    settings,
  };
}

function normalizeHandle(value) {
  return String(value || "")
    .trim()
    .replace(/^@+/, "")
    .split(/[/?#]/)[0]
    .toLowerCase();
}

function handleFromUrl(url) {
  const match = String(url || "").match(/tiktok\.com\/@([^/?#]+)/i);
  return normalizeHandle(match?.[1] || "");
}

function parseJsonArray(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function numericFollowerCount(value, raw) {
  const direct = Number(value);
  if (Number.isFinite(direct) && direct >= 0) {
    return Math.round(direct);
  }
  const text = String(raw || "").trim().toUpperCase().replace(/,/g, "");
  const match = text.match(/^([0-9]+(?:\.[0-9]+)?)([KMB])?$/);
  if (!match) {
    return null;
  }
  const base = Number(match[1]);
  const unit = match[2] || "";
  const multiplier = unit === "K" ? 1_000 : unit === "M" ? 1_000_000 : unit === "B" ? 1_000_000_000 : 1;
  return Math.round(base * multiplier);
}

function safeNoteValue(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^\w.-]/g, "_")
    .slice(0, 120);
}
