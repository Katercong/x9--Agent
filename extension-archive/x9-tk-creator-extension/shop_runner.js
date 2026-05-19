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

  const DEFAULT_SETTINGS = {
    endpoint: "http://127.0.0.1:8000/api/local/collector/observations",
    source: "tiktok_shop_creator_lead_browser_extension_2_2",
    workerId: "tiktok_shop_creator_lead_browser_2_2",
    taskCount: 20,
  };

  const DEFAULT_STATE = {
    status: "idle", phase: "idle", runId: null,
    listTabId: null, detailTabId: null,
    startedAt: null, finishedAt: null,
    counts: { listItems: 0, listUploads: 0, listUploadFail: 0, detailDone: 0, detailFail: 0, errors: 0 },
    handles: [], doneHandles: [], queueIndex: 0,
    currentHandle: null, lastError: null, lastStatus: null,
    settings: DEFAULT_SETTINGS,
  };

  let detailLoopActive = false;
  let pendingDetailResolve = null;

  console.log(TAG, "shop_runner v8 loaded");

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

  async function uploadObservation(observation, endpoint) {
    if (!observation || !observation.creator || !observation.creator.handle) throw new Error("observation missing creator.handle");
    const resp = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(observation) });
    let body = null; try { body = await resp.json(); } catch (_) {}
    if (!resp.ok || (body && body.ok === false)) {
      const detail = (body && (body.detail || body.error)) || `HTTP ${resp.status}`;
      throw new Error(detail);
    }
    return body || { ok: true };
  }

  function queueObservationUpload(observation, endpoint, meta) {
    const handle = (observation && observation.creator && observation.creator.handle) || (meta && meta.handle) || "unknown";
    const kind = (meta && meta.kind) || "detail";
    uploadObservation(observation, endpoint)
      .then(async () => {
        const cur = await getState();
        await patchState({
          lastStatus: kind === "list" ? `列表已入库 @${handle}` : `后端已接收 @${handle}`,
          counts: {
            listItems: cur.counts.listItems,
            listUploads: cur.counts.listUploads + (kind === "list" ? 1 : 0),
            listUploadFail: cur.counts.listUploadFail,
            detailDone: cur.counts.detailDone,
            detailFail: cur.counts.detailFail,
            errors: cur.counts.errors,
          },
        });
      })
      .catch(async (err) => {
        const cur = await getState();
        const message = String(err && err.message || err);
        await patchState({
          lastError: `upload:${handle}: ${message}`,
          lastStatus: kind === "list" ? `列表上传失败 @${handle}` : `后端上传失败 @${handle}`,
          counts: {
            listItems: cur.counts.listItems,
            listUploads: cur.counts.listUploads,
            listUploadFail: cur.counts.listUploadFail + (kind === "list" ? 1 : 0),
            detailDone: cur.counts.detailDone,
            detailFail: cur.counts.detailFail,
            errors: cur.counts.errors + 1,
          },
        });
      });
  }

  function buildListObservation(item, state) {
    return {
      event_type: "creator_observation", platform: "tiktok_shop",
      source: state.settings.source, worker_id: state.settings.workerId,
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
    const settings = Object.assign({}, DEFAULT_SETTINGS, cur.settings || {}, message.settings || {});
    const taskCount = Math.max(1, parseInt(settings.taskCount, 10) || 20);
    settings.taskCount = taskCount;
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
    detailLoopActive = false;
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
        const handle = state.handles[state.queueIndex];
        const pos = `${state.queueIndex + 1}/${state.handles.length}`;
        console.log(TAG, `--- detail ${pos} @${handle} ---`);
        await patchState({ currentHandle: handle, lastStatus: `打开详情 ${pos} @${handle}` });
        let observation = null, phaseError = null, detailTabId = null;
        try {
          detailTabId = await openDetailForHandle(state.listTabId, handle, 15000);
          console.log(TAG, "detail tab", detailTabId, "@" + handle);
          await patchState({ detailTabId, lastStatus: `详情页已打开 ${pos} @${handle}` });
          observation = await scrapeDetailTab(detailTabId, 18000);
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
          queueObservationUpload(enriched, state.settings.endpoint, { kind: "detail", handle: hf });
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
        await sleep(800 + Math.floor(Math.random() * 500));
        state = await getState();
      }
      if (state.status === "running") {
        await patchState({ status: "done", phase: "finished", finishedAt: new Date().toISOString(), currentHandle: null, lastStatus: "采集完成，数据已交给后端队列" });
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

  async function scrapeDetailTab(detailTabId, maxMs) {
    console.log(TAG, "wait tab", detailTabId);
    await waitForTabComplete(detailTabId, maxMs);
    console.log(TAG, "tab loaded, sleeping 600ms");
    await sleep(600);
    let lastErr = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        console.log(TAG, "SCAN_DETAIL_NOW try " + (attempt + 1));
        const resp = await sendToTab(detailTabId, { type: MSG.CS_SCAN_DETAIL_NOW });
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
