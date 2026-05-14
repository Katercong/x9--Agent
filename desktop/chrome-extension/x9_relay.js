const X9_STORAGE_KEY = "tclabState";
const X9_RELAYED_KEYS = "x9_relayed_keys";
const X9_API_BASE_KEY = "x9_api_base";          // user override stored here
const X9_API_BASE_ACTIVE_KEY = "x9_api_base_active";  // last-known-good
const X9_HEARTBEAT_ALARM = "x9-relay-heartbeat";

// Candidates tried in order when no user override is set. Whichever responds
// first to a heartbeat becomes the cached "active" base.
const X9_API_BASE_CANDIDATES = [
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://usx9.us",
  "http://192.168.1.171:8000",
  "http://192.168.1.171",
];

function joinPath(base, path) {
  return `${String(base).replace(/\/+$/, "")}${path}`;
}

async function getStoredApiBase() {
  const o = await chrome.storage.local.get([X9_API_BASE_KEY, X9_API_BASE_ACTIVE_KEY]);
  return { override: o[X9_API_BASE_KEY] || "", active: o[X9_API_BASE_ACTIVE_KEY] || "" };
}

async function setActiveApiBase(base) {
  await chrome.storage.local.set({ [X9_API_BASE_ACTIVE_KEY]: base });
}

async function getCandidateOrder() {
  const { override, active } = await getStoredApiBase();
  // Explicit user override always wins.
  if (override) return [override];
  // Otherwise try the last working one first, then walk the candidate list.
  const ordered = [];
  if (active) ordered.push(active);
  for (const c of X9_API_BASE_CANDIDATES) {
    if (!ordered.includes(c)) ordered.push(c);
  }
  return ordered;
}

chrome.runtime.onInstalled.addListener(() => {
  ensureX9RelayAlarm();
  relayCurrentState("installed").catch(() => undefined);
});

chrome.runtime.onStartup.addListener(() => {
  ensureX9RelayAlarm();
  relayCurrentState("startup").catch(() => undefined);
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === X9_HEARTBEAT_ALARM) {
    relayCurrentState("alarm").catch(() => undefined);
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
    email: lead.email || "",
    external_links: parseJsonArray(lead.external_links),
    source: "tiktok_creator_lead_browser",
    current_status: "prospect",
    search_keyword: lead.search_keyword || "",
    source_video_url: lead.source_video_url || "",
    source_video_title: lead.source_video_title || "",
    source_video_description: lead.source_video_description || "",
    notes: `filter=qualified message=${safeNoteValue(lead.lead_status || "lead_saved")}`,
    last_seen_at: lead.last_seen_at || lead.collected_at || new Date().toISOString(),
  };
  return hasDirectContact(item) ? item : null;
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
    email: skipped.email || "",
    external_links: parseJsonArray(skipped.external_links),
    source: "tiktok_creator_lead_browser",
    current_status: "dropped",
    search_keyword: skipped.search_keyword || "",
    source_video_url: skipped.source_video_url || "",
    source_video_title: skipped.source_video_title || "",
    source_video_description: skipped.source_video_description || "",
    notes: `filter=${safeNoteValue(reason)} message=skipped`,
    last_seen_at: skipped.checked_at || skipped.last_seen_at || new Date().toISOString(),
  };
  return hasDirectContact(item) ? item : null;
}

function hasDirectContact(item) {
  const email = String(item.email || "");
  if (/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.test(email)) {
    return true;
  }
  const linkText = JSON.stringify(item.external_links || []);
  const text = `${item.bio || ""} ${linkText}`.toLowerCase();
  return /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.test(text)
    || /(whats\s*app|whatsapp|wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com|telegram|t\.me\/|telegram\.me|line\.me|lin\.ee|facebook\.com|fb\.me|m\.me\/|dm me|dm for|direct message|message me|instagram\.com|insta|ig[:\s@]|tel:)/i.test(text)
    || /(?:\+|00)?\d[\d\s().-]{7,}\d/.test(text);
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
