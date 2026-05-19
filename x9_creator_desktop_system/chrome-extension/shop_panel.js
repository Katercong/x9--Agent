/* TikTok Shop popup panel (v6).
 * Drives the simplified card UI: status pill (data-state), task count input,
 * Start / Stop / Reset buttons, counts grid, progress footnotes. */
(function () {
  const MSG = {
    SHOP_START: "TSCLB_SHOP_START",
    SHOP_STOP: "TSCLB_SHOP_STOP",
    SHOP_GET_STATE: "TSCLB_SHOP_GET_STATE",
    SHOP_RESET_COUNTS: "TSCLB_SHOP_RESET_COUNTS",
    SHOP_SET_SETTINGS: "TSCLB_SHOP_SET_SETTINGS",
  };

  const DEFAULT_ENDPOINT = "http://127.0.0.1:8000/api/local/collector/observations";
  const SHOP_API_BASE_KEY = "x9_api_base";
  const SHOP_API_BASE_ACTIVE_KEY = "x9_api_base_active";
  const SHOP_BACKEND_CANDIDATES = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://usx9.us",
    "http://usx9.us",
    "http://192.168.1.171:8000",
    "http://192.168.1.171",
  ];
  let pollTimer = null;

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    const root = document.getElementById("shopPanel");
    if (!root) return;
    bind();
    paintFromStorage();
    startPolling();
  }

  function bind() {
    document.getElementById("shopStartBtn")?.addEventListener("click", onStart);
    document.getElementById("shopStopBtn")?.addEventListener("click", onStop);
    document.getElementById("shopResetBtn")?.addEventListener("click", onReset);
    const t = document.getElementById("shopTaskCount");
    if (t) t.addEventListener("input", () => { t.dataset.touched = "1"; });
  }

  async function onStart() {
    const endpoint = await resolveShopEndpoint();
    const taskCount = Math.max(1, parseInt(document.getElementById("shopTaskCount")?.value || "20", 10) || 20);
    await send(MSG.SHOP_SET_SETTINGS, { settings: { endpoint, taskCount } });
    setStatusPillState("running", "启动中…");
    setError("");
    const resp = await send(MSG.SHOP_START, { settings: { endpoint, taskCount } });
    if (!resp || !resp.ok) {
      setStatusPillState("error", "启动失败");
      const e = (resp && resp.error) || "unknown";
      if (e === "active_tab_is_not_tiktok_shop") setError("请先打开 affiliate-us.tiktok.com 列表页再点开始");
      else if (e === "no_active_tab") setError("找不到活动标签页");
      else setError("启动失败：" + e);
    } else {
      setStatusPillState("running", "运行中");
    }
    refresh();
  }

  async function onStop() {
    setStatusPillState("paused", "停止中…");
    await send(MSG.SHOP_STOP);
    refresh();
  }

  async function onReset() {
    if (!confirm("重置 TikTok Shop 计数器和状态？(不会删后端数据)")) return;
    await send(MSG.SHOP_RESET_COUNTS);
    refresh();
  }

  function send(type, payload) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(Object.assign({ type }, payload || {}), (resp) => {
          if (chrome.runtime.lastError) return resolve({ ok: false, error: chrome.runtime.lastError.message });
          resolve(resp);
        });
      } catch (e) {
        resolve({ ok: false, error: String(e && e.message || e) });
      }
    });
  }

  async function resolveShopEndpoint() {
    const input = document.getElementById("shopEndpointInput");
    const current = (input?.value || "").trim();
    if (current && current !== DEFAULT_ENDPOINT) {
      return current;
    }

    const stored = await chrome.storage.local.get([SHOP_API_BASE_KEY, SHOP_API_BASE_ACTIVE_KEY]).catch(() => ({}));
    const bases = [
      stored[SHOP_API_BASE_KEY],
      stored[SHOP_API_BASE_ACTIVE_KEY],
      ...SHOP_BACKEND_CANDIDATES,
    ].filter(Boolean);

    const seen = new Set();
    for (const rawBase of bases) {
      const base = String(rawBase).replace(/\/+$/, "");
      if (!base || seen.has(base)) continue;
      seen.add(base);
      if (await canReachShopBackend(base)) {
        await chrome.storage.local.set({ [SHOP_API_BASE_ACTIVE_KEY]: base }).catch(() => undefined);
        const endpoint = joinShopPath(base, "/api/local/collector/observations");
        if (input) input.value = endpoint;
        return endpoint;
      }
    }

    return current || DEFAULT_ENDPOINT;
  }

  async function canReachShopBackend(base) {
    try {
      const response = await fetch(joinShopPath(base, "/health"), { method: "GET" });
      return response.ok;
    } catch {
      return false;
    }
  }

  function joinShopPath(base, path) {
    return `${String(base).replace(/\/+$/, "")}${path}`;
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(refresh, 500);
    refresh();
  }

  async function refresh() {
    const resp = await send(MSG.SHOP_GET_STATE);
    if (resp && resp.ok && resp.state) paint(resp.state);
  }

  function paintFromStorage() {
    try {
      chrome.storage?.local?.get?.(["shopAutoRun"], (got) => {
        const s = got?.shopAutoRun;
        const ep = (s && s.settings && s.settings.endpoint) || DEFAULT_ENDPOINT;
        const inp = document.getElementById("shopEndpointInput");
        if (inp && !inp.value) inp.value = ep;
        // Task count: only seed from storage if user hasn't touched the field.
        const taskInp = document.getElementById("shopTaskCount");
        const stored = s && s.settings && s.settings.taskCount;
        if (taskInp && stored && !taskInp.dataset.touched) {
          taskInp.value = String(stored);
        }
      });
    } catch (_) { /* ignore */ }
  }

  function paint(state) {
    const inp = document.getElementById("shopEndpointInput");
    if (inp && !inp.value) inp.value = (state.settings && state.settings.endpoint) || DEFAULT_ENDPOINT;

    const pillMap = {
      idle: "闲置", running: "运行中", paused: "已停止", done: "已完成", error: "错误",
    };
    setStatusPillState(state.status || "idle", pillMap[state.status] || "闲置");

    const phaseMap = {
      idle: "闲置", list_scanning: "列表滚动采集中", detail_scanning: "详情逐个采集中", finished: "已完成",
    };
    const c = state.counts || {};
    const queueTotal = state.handles?.length || 0;
    const extracted = c.detailDone || 0;
    const failed = c.detailFail || 0;
    const processed = Math.min(queueTotal, extracted + failed);
    const pending = Math.max(0, queueTotal - processed);
    const currentIndex = state.status === "running" && queueTotal
      ? Math.min(queueTotal, Math.max(processed + 1, (state.queueIndex || 0) + 1))
      : processed;

    setText("shopCountList", String(queueTotal));
    setText("shopCountDetailOk", String(c.detailDone || 0));
    setText("shopCountDetailFail", String(c.detailFail || 0));
    setText("shopCountErrors", String(c.errors || 0));

    const phaseEl = document.getElementById("shopPhase");
    if (phaseEl) {
      const phase = phaseMap[state.phase] || state.phase || "闲置";
      if (state.phase === "detail_scanning" || queueTotal) {
        phaseEl.textContent = `阶段：${phase} · 详情 ${processed}/${queueTotal} · 剩余 ${pending}`;
      } else {
        phaseEl.textContent = `阶段：${phase}`;
      }
    }
    const curEl = document.getElementById("shopCurrent");
    if (curEl) {
      const status = state.lastStatus || "";
      const current = state.currentHandle ? `当前：@${state.currentHandle} (${currentIndex}/${queueTotal || "?"})` : "";
      curEl.textContent = [current, status].filter(Boolean).join(" · ");
    }

    setError(state.lastError || "");
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function setStatusPillState(state, text) {
    const el = document.getElementById("shopStatusPill");
    if (!el) return;
    el.textContent = text;
    el.setAttribute("data-state", state || "idle");
  }
  function setError(msg) {
    const el = document.getElementById("shopError");
    if (!el) return;
    if (msg) { el.textContent = `⚠ ${msg}`; el.classList.add("error"); }
    else { el.textContent = ""; el.classList.remove("error"); }
  }
})();
