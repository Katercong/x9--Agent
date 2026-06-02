'use strict';

chrome.runtime.onInstalled.addListener(() => {
  if (chrome.sidePanel?.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

// ===========================================================================
// 批量回填编排
// ===========================================================================
// 流程：
//   1. sidepanel 发 {type:'backfill:start', limit, only_missing} 给 background
//   2. background 拉后端 list → 过滤缺字段的 → 队列
//   3. 顺序 chrome.tabs.create 打开每个详情页（active:false → 后台标签）
//   4. content script 在页面里抓数据 → POST 后端 → 发 'backfill:done'
//   5. background 收到 done → 关闭那个 tab → 处理下一个 → 进度回传 sidepanel
//   6. 中途超时（默认 18s）自动跳过

const NATIVE_HOST = 'com.companyleads.helper';
let backendConfigCache = null;
const TAB_TIMEOUT_MS = 18000;

function nativeMessage(type, payload = {}) {
  return new Promise((resolve, reject) => {
    if (!chrome.runtime?.sendNativeMessage) {
      reject(new Error('nativeMessaging unavailable'));
      return;
    }
    chrome.runtime.sendNativeMessage(NATIVE_HOST, { type, payload }, response => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message || 'native host unavailable'));
        return;
      }
      if (!response || response.ok === false) {
        reject(new Error(response?.error || 'native host returned an error'));
        return;
      }
      resolve(response);
    });
  });
}

async function backendConfig() {
  if (backendConfigCache) return backendConfigCache;
  try {
    const res = await nativeMessage('helper.getClientConfig');
    backendConfigCache = {
      backendUrl: (res.config?.backendUrl || 'https://usx9.us').replace(/\/$/, ''),
      apiToken: res.config?.apiToken || '',
    };
  } catch {
    backendConfigCache = { backendUrl: 'https://usx9.us', apiToken: '' };
  }
  return backendConfigCache;
}

async function backendFetch(path, options = {}) {
  const cfg = await backendConfig();
  const headers = { ...(options.headers || {}) };
  if (cfg.apiToken) headers['X-CompanyLeads-Token'] = cfg.apiToken;
  return fetch(cfg.backendUrl + path, { ...options, headers });
}

async function dispatchDebuggerMouseClick(tabId, x, y) {
  if (tabId == null) throw new Error('missing_tab_id');
  if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error('invalid_coordinates');
  const debuggee = { tabId };
  let attached = false;
  try {
    await chrome.debugger.attach(debuggee, '1.3');
    attached = true;
    await chrome.debugger.sendCommand(debuggee, 'Input.dispatchMouseEvent', {
      type: 'mouseMoved',
      x,
      y,
      button: 'none',
      buttons: 0,
    });
    await new Promise(resolve => setTimeout(resolve, 120 + Math.floor(Math.random() * 180)));
    await chrome.debugger.sendCommand(debuggee, 'Input.dispatchMouseEvent', {
      type: 'mousePressed',
      x,
      y,
      button: 'left',
      buttons: 1,
      clickCount: 1,
    });
    await new Promise(resolve => setTimeout(resolve, 80 + Math.floor(Math.random() * 140)));
    await chrome.debugger.sendCommand(debuggee, 'Input.dispatchMouseEvent', {
      type: 'mouseReleased',
      x,
      y,
      button: 'left',
      buttons: 0,
      clickCount: 1,
    });
    return { ok: true };
  } finally {
    if (attached) {
      try { await chrome.debugger.detach(debuggee); } catch {}
    }
  }
}

// qzrc 回填新默认（与 qzrc_backfill.py 对齐：低频小批）
const QZRC_DEFAULTS = {
  batches: 3,
  batch_size: 10,
  item_delay_min_s: 8,
  item_delay_max_s: 20,
  batch_delay_min_s: 180,    // 3 min
  batch_delay_max_s: 480,    // 8 min
  post_captcha_multiplier: 3,
  stop_on_captcha: false,
};

const state = {
  running: false,
  cancelled: false,
  total: 0,
  done: 0,
  ok: 0,
  fail: 0,
  captcha_hits: 0,
  // 批次信息
  batches_done: 0,
  batches_total: 0,
  current_batch_idx: 0,
  current_item_idx: 0,
  current_batch_size: 0,
  next_batch_at: null,       // ISO 时间，倒计时
  current: null,             // {tabId, cid, resolve}
  reportPort: null,
  cfg: { ...QZRC_DEFAULTS },
};

chrome.runtime.onConnect.addListener(port => {
  if (port.name !== 'backfill-progress') return;
  state.reportPort = port;
  pushProgress();
  port.onDisconnect.addListener(() => {
    if (state.reportPort === port) state.reportPort = null;
  });
  // 命令也走同一个 port，避免 sendMessage 在 service worker 休眠时报
  // "Could not establish connection. Receiving end does not exist."
  port.onMessage.addListener(async (msg) => {
    if (msg?.type === 'backfill:start') {
      if (state.running) {
        pushProgress({ note: '已有任务在跑，忽略' });
        return;
      }
      // 应用本次配置
      state.cfg = { ...QZRC_DEFAULTS, ...(msg.cfg || {}) };
      // 兼容旧 limit：转换成 (batches=1, batch_size=limit)
      if (msg.limit && !msg.cfg) {
        state.cfg.batches = 1;
        state.cfg.batch_size = Math.max(1, Math.min(500, msg.limit));
      }
      state.running = true;
      state.cancelled = false;
      state.done = 0; state.ok = 0; state.fail = 0; state.captcha_hits = 0;
      state.batches_done = 0;
      state.batches_total = state.cfg.batches;
      state.next_batch_at = null;
      try {
        await runAllBatches();
      } catch (err) {
        pushProgress({ note: '任务异常: ' + (err?.message || err) });
      } finally {
        state.running = false;
        clearCurrent();
        pushProgress({ note: `结束：访问 ${state.done} / 成功 ${state.ok} / 失败 ${state.fail} / 验证码 ${state.captcha_hits}` });
      }
    } else if (msg?.type === 'backfill:stop') {
      state.cancelled = true;
      state.running = false;
      clearCurrent();
      pushProgress({ note: '已请求停止' });
    }
  });
});

function rnd(lo, hi) { return Math.floor(lo + Math.random() * (hi - lo)); }

async function sleepCancellable(ms) {
  const step = 500;
  let remaining = ms;
  while (remaining > 0 && !state.cancelled) {
    await new Promise(r => setTimeout(r, Math.min(step, remaining)));
    remaining -= step;
  }
}

async function runAllBatches() {
  const cfg = state.cfg;
  let lastBatchHitCaptcha = false;
  for (let b = 1; b <= cfg.batches; b++) {
    if (state.cancelled) break;
    state.current_batch_idx = b;
    state.next_batch_at = null;
    pushProgress({ note: `[BATCH ${b}/${cfg.batches}] 拉取目标…` });

    const targets = await fetchBackfillTargets(cfg.batch_size);
    state.current_batch_size = targets.length;
    state.current_item_idx = 0;
    pushProgress({ note: `[BATCH ${b}/${cfg.batches}] 拉到 ${targets.length} 条` });
    if (!targets.length) {
      pushProgress({ note: '队列空了' });
      break;
    }

    let captchaHitInBatch = false;
    for (let i = 0; i < targets.length; i++) {
      if (state.cancelled) break;
      state.current_item_idx = i + 1;
      const target = targets[i];
      const result = await processOne(target);
      state.done++;
      state.total = state.done;
      if (result === 'captcha') {
        state.captcha_hits++;
        captchaHitInBatch = true;
        pushProgress({ note: `[BATCH ${b}] 第 ${i+1} 条命中验证码 → 立即停批` });
        break;   // 立即停批
      } else if (result === 'ok') {
        state.ok++;
      } else {
        state.fail++;
      }
      // 单条间隔
      if (i < targets.length - 1 && !state.cancelled) {
        const d = rnd(cfg.item_delay_min_s, cfg.item_delay_max_s);
        pushProgress({ note: `等 ${d}s 后下一条 (item ${i+1}/${targets.length})` });
        await sleepCancellable(d * 1000);
      }
    }
    state.batches_done = b;

    if (state.cancelled) break;
    if (captchaHitInBatch && cfg.stop_on_captcha) {
      pushProgress({ note: 'stop-on-captcha=true → 终止整个 run' });
      break;
    }
    if (b < cfg.batches) {
      let cool = rnd(cfg.batch_delay_min_s, cfg.batch_delay_max_s);
      if (captchaHitInBatch) cool = Math.floor(cool * (cfg.post_captcha_multiplier || 3));
      state.next_batch_at = new Date(Date.now() + cool * 1000).toISOString();
      pushProgress({ note: `[REST] 批后冷却 ${cool}s (≈${(cool/60).toFixed(1)} min)${captchaHitInBatch ? ' (验证码后加倍)' : ''}` });
      await sleepCancellable(cool * 1000);
      state.next_batch_at = null;
    }
    lastBatchHitCaptcha = captchaHitInBatch;
  }
}

function pushProgress(extra) {
  if (!state.reportPort) return;
  try {
    state.reportPort.postMessage({
      type: 'progress',
      running: state.running,
      total: state.total,
      done: state.done,
      ok: state.ok,
      fail: state.fail,
      captcha_hits: state.captcha_hits,
      current_cid: state.current?.cid || null,
      // 批次进度
      batches_total: state.batches_total,
      batches_done: state.batches_done,
      current_batch_idx: state.current_batch_idx,
      current_item_idx: state.current_item_idx,
      current_batch_size: state.current_batch_size,
      next_batch_at: state.next_batch_at,
      ...(extra || {}),
    });
  } catch {}
}

async function fetchBackfillTargets(limit) {
  const out = [];
  let page = 1;
  while (out.length < limit) {
    const res = await backendFetch(`/api/companies?platform=qzrc&page=${page}&page_size=100&include_excluded=true`);
    const d = await res.json();
    const items = d.items || [];
    if (!items.length) break;
    for (const it of items) {
      const needs = !it.company_description || !it.company_address;
      const hasCid = !!it.platform_company_id;
      if (needs && hasCid) {
        out.push({
          cid: it.platform_company_id,
          name: it.company_name,
          url: `https://www.qzrc.com/company/show/${it.platform_company_id}`,
        });
        if (out.length >= limit) break;
      }
    }
    if (page * 100 >= (d.total || 0)) break;
    page += 1;
  }
  return out;
}

function clearCurrent() {
  if (!state.current) return;
  const cur = state.current;
  state.current = null;
  if (cur.timeoutHandle) clearTimeout(cur.timeoutHandle);
  if (cur.tabId != null) {
    chrome.tabs.remove(cur.tabId).catch(() => {});
  }
  if (cur.resolve) cur.resolve();
}

// processOne: resolve('ok' | 'captcha' | 'fail' | 'timeout')
async function processOne(target) {
  return new Promise(async (resolve) => {
    let tab;
    try {
      tab = await chrome.tabs.create({ url: target.url, active: false });
    } catch (err) {
      pushProgress({ note: `打开 tab 失败: ${err.message}` });
      return resolve('fail');
    }
    state.current = { tabId: tab.id, cid: target.cid, resolve };
    state.current.timeoutHandle = setTimeout(() => {
      pushProgress({ note: `[超时] ${target.name}` });
      const cur = state.current; state.current = null;
      if (cur?.tabId != null) chrome.tabs.remove(cur.tabId).catch(() => {});
      resolve('timeout');
    }, TAB_TIMEOUT_MS);
    pushProgress({ note: `处理中: ${target.name}` });
  });
}

// content script 用 sendMessage 推 'backfill:done'（不走 port），单独保留
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === 'backend:ingestCompany') {
    backendFetch('/api/companies/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.payload || {}),
    })
      .then(async res => {
        const text = await res.text();
        let body = {};
        try { body = text ? JSON.parse(text) : {}; } catch { body = { raw: text }; }
        sendResponse({ ok: res.ok, status: res.status, body });
      })
      .catch(err => sendResponse({ ok: false, error: err?.message || String(err) }));
    return true;
  }

  if (msg?.type === 'zhaopin:debugger_click') {
    dispatchDebuggerMouseClick(sender?.tab?.id, Number(msg.x), Number(msg.y))
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ ok: false, reason: err?.message || String(err) }));
    return true;
  }

  if (msg?.type === 'backfill:done') {
    if (state.current && state.current.cid === msg.platform_company_id) {
      const cur = state.current;
      // 关掉 tab + 清理 timeout
      if (cur.timeoutHandle) clearTimeout(cur.timeoutHandle);
      if (cur.tabId != null) chrome.tabs.remove(cur.tabId).catch(() => {});
      state.current = null;
      // 决定结果类型
      let result;
      if (msg.reason === 'captcha') {
        result = 'captcha';
        pushProgress({ note: `⚠ 命中验证码: ${msg.platform_company_id}（停批）` });
      } else if (msg.ok && (msg.got_desc || msg.got_addr)) {
        result = 'ok';
        pushProgress({ note: `✓ ${msg.platform_company_id} ${msg.got_desc ? '简介' : ''}${msg.got_addr ? ' 地址' : ''}` });
      } else {
        result = 'fail';
        pushProgress({ note: `✗ ${msg.platform_company_id} ${msg.error || msg.reason || ''}` });
      }
      if (cur.resolve) cur.resolve(result);
    }
    sendResponse?.({ ok: true });
    return false;
  }
});
