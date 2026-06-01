'use strict';

const HELPER = 'http://127.0.0.1:8765';
const NATIVE_HOST = 'com.companyleads.helper';
const MAX_AUTO_PAGES = 100;
const TALENT_51JOB_KEYWORDS = '跨境销售,跨境电商运营,Amazon运营,美区运营,海外仓招商,跨境供应链,品牌出海销售';

// 平台登录策略：qzrc/51job 公司客户=登录可选（采集公开信息）；
// 智联公司客户=登录必需（未登录被登录墙拦截、拿不到数据）；跨境人才=登录必需（依赖企业端权限）
const LOGIN_POLICY = {
  qzrc_job: 'optional',
  '51job': 'optional',
  zhaopin: 'required',
  qzrc_resume: 'required',
  '51job_talent': 'required',
  zhaopin_resume: 'required',
};

function loginPolicyFor(platform) {
  return LOGIN_POLICY[platform] === 'required' ? 'required' : 'optional';
}

function updateLoginHint() {
  const el = $('login-hint');
  if (!el) return;
  const platform = $('platform')?.value;
  const required = loginPolicyFor(platform) === 'required';
  let text;
  if (platform === 'zhaopin') {
    // 智联公司客户硬性要求登录：醒目提醒用户必须先登录
    text = '智联公司客户：必须先在工作窗口登录智联后才能采集（未登录无法获取数据）';
  } else if (required) {
    text = '跨境人才：需要先在工作窗口登录后才能采集';
  } else {
    text = '公司客户：未登录也可采集公开信息';
  }
  el.textContent = text;
  // 需登录平台用警示色提醒；免登录平台保持默认 muted 颜色
  el.style.color = required ? '#c0392b' : '';
}

let currentTask = null;
let pollTimer = null;
const notifiedTasks = new Set();      // 已弹过完成通知的任务 id
const taskMaxItems = {};              // 本会话内下发任务的目标条数（用于显示 N / max）

const PLATFORM_LABELS = {
  qzrc_job: '大泉州·公司客户',
  qzrc_resume: '大泉州·跨境人才',
  '51job': '前程无忧·公司客户',
  '51job_talent': '前程无忧·跨境人才',
  zhaopin: '智联·公司客户',
  zhaopin_resume: '智联·跨境人才',
};
const ACTIVE_STATES = ['queued', 'running', 'stopping'];

const $ = id => document.getElementById(id);

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
const EXPECTED_ROOT_SUFFIX = '\\CompanyLeads_local';

function parseProgressFromLogs(lines = []) {
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = String(lines[i] || '');
    const marker = '[PROGRESS] ';
    const idx = line.indexOf(marker);
    if (idx < 0) continue;
    try {
      const parsed = JSON.parse(line.slice(idx + marker.length).trim());
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {}
  }
  return {};
}

function progressFromTask(task = {}) {
  const logs = task.logs || task.log_tail || [];
  const fromLogs = parseProgressFromLogs(logs);
  const fromApi = task.progress || {};
  const apiHasCounts = Number(fromApi.total || 0) > 0 || Number(fromApi.items_total || 0) > 0;
  const logHasProgress = Object.keys(fromLogs).length > 0;
  const merged = logHasProgress && !apiHasCounts ? fromLogs : { ...fromLogs, ...fromApi };
  const status = task.status || '';

  if (status === 'done') {
    merged.phase = merged.phase || 'done';
    merged.label = merged.label && merged.label !== 'done' ? merged.label : '采集完成';
  } else if (status === 'failed') {
    merged.phase = 'failed';
    merged.label = merged.label && merged.label !== 'failed' ? merged.label : '采集失败';
  } else if (status === 'stopped') {
    merged.phase = 'stopped';
    merged.label = merged.label && merged.label !== 'stopped' ? merged.label : '已停止';
  }

  return merged;
}

const STAGE_LABELS = {
  idle: '未开始',
  queued: '正在下发任务',
  start: '准备采集',
  page: '采集中',
  page_done: '采集中',
  enrich: '详情补全中',
  done: '采集完成',
  failed: '采集失败',
  stopped: '已停止',
};

function taskCountText(task, progress, phase) {
  const isIdle = phase === 'idle' && !task.status;
  const isTerminal = phase === 'done' || phase === 'failed' || phase === 'stopped';
  const items = Number(progress.items_total || 0);
  const maxItems = Number(progress.max_items || taskMaxItems[task.id] || 0);
  if (isIdle) return '未开始';
  if (isTerminal || maxItems <= 0) return `已采集 ${items} 条`;
  return `已采集 ${Math.min(items, maxItems)} / ${maxItems} 条`;
}

function renderTaskCard(task) {
  const progress = progressFromTask(task);
  const phase = progress.phase || task.status || 'idle';
  const isActive = phase === 'page' || phase === 'page_done' || phase === 'enrich';
  const platformLabel = PLATFORM_LABELS[task.platform] || task.platform || '采集任务';
  const stage = STAGE_LABELS[phase] || progress.label || phase || '采集中';
  const keyword = progress.current_keyword || '';
  const page = progress.current_page;

  let statusText = stage;
  if (isActive && keyword) statusText += ` · 当前关键词：${keyword}`;
  const pageText = (isActive && page) ? `当前页：第 ${page} 页` : '';

  return `<div class="task-card" data-status="${esc(task.status || phase)}">
    <div class="progress-head">
      <div class="progress-title">${esc(platformLabel)}</div>
      <div class="progress-count">${esc(taskCountText(task, progress, phase))}</div>
    </div>
    <div class="progress-meta">
      <span>${esc(statusText)}</span>
      <span>${esc(pageText)}</span>
    </div>
  </div>`;
}

// 多任务进度：进行中的任务全部展示；没有进行中的就展示最近一条（看到最终结果）。
function renderTasks(tasks) {
  const container = $('crawl-progress');
  if (!container) return;
  const list = Array.isArray(tasks) ? tasks : [];
  const active = list.filter(t => ACTIVE_STATES.includes(t.status));
  let toShow = (active.length ? active : list.slice(0, 1)).slice(0, 8);
  if (!toShow.length) {
    container.innerHTML = `<div class="task-card task-empty">
      <div class="progress-head"><div class="progress-title">主采集进度</div><div class="progress-count">未开始</div></div>
      <div class="progress-meta"><span>未开始</span></div>
    </div>`;
    return;
  }
  container.innerHTML = toShow.map(renderTaskCard).join('');
}

function isExpectedHelperRoot(root) {
  return String(root || '').replace(/\//g, '\\').endsWith(EXPECTED_ROOT_SUFFIX);
}

async function helperFetch(path, options = {}) {
  const res = await fetch(HELPER + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(body ? `HTTP ${res.status}: ${body.slice(0, 500)}` : `HTTP ${res.status}`);
  }
  return res.json();
}

function setHealth(text) {
  const el = $('health');
  if (el && el.textContent !== text) el.textContent = text;
}

function setRuntimeStatus(text) {
  if (String(text || '').startsWith('CDP:')) return;
  const el = $('runtime-status');
  if (el && el.textContent !== text) el.textContent = text;
}

function nativeMessage(type, payload = {}) {
  return new Promise((resolve, reject) => {
    if (!chrome.runtime?.sendNativeMessage) {
      reject(new Error('当前扩展缺少 nativeMessaging 权限'));
      return;
    }
    chrome.runtime.sendNativeMessage(NATIVE_HOST, { type, payload }, response => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message || 'Native host 未安装或无法启动'));
        return;
      }
      if (!response || response.ok === false) {
        reject(new Error(response?.error || 'Native host 返回异常'));
        return;
      }
      resolve(response);
    });
  });
}

function renderNativeStatus(status) {
  const helper = status.helperReady ? 'helper: 已连接' : 'helper: 未连接';
  const backend = status.backendReady ? `后台: 已连接${status.backendUrl ? ` (${status.backendUrl})` : ''}` : `后台: 未连接${status.backendUrl ? ` (${status.backendUrl})` : ''}`;
  const cdp = status.cdpReady ? `CDP: ${status.cdpUrl || 'ready'}` : 'CDP: 未就绪';
  const profile = status.runtime?.userDataDir ? `profile: ${status.runtime.userDataDir}` : 'profile: 受控独立窗口';
  const mode = status.mode ? `mode: ${status.mode}` : '';
  const auth = status.apiTokenConfigured ? 'token: configured' : 'token: none';
  const llm = status.systemStatus?.llm_configured ? `LLM: ${status.systemStatus.llm_model || 'ready'}` : 'LLM: not configured/unknown';
  setRuntimeStatus([helper, backend, cdp, profile, mode, auth, llm].filter(Boolean).join(' · '));
}

async function ensureLocalStack() {
  setHealth('helper: 启动中...');
  const status = await nativeMessage('helper.ensureStarted');
  renderNativeStatus(status);
  return status;
}

function setCompletion(text, tone = 'info') {
  const el = $('task-completion');
  if (!el) return;
  el.style.display = text ? 'block' : 'none';
  el.textContent = text || '';
  el.style.border = tone === 'success' ? '1px solid #166534'
    : tone === 'error' ? '1px solid #7f1d1d'
    : tone === 'stopped' ? '1px solid #92400e'
    : '1px solid #1f2937';
  el.style.background = tone === 'success' ? '#052e16'
    : tone === 'error' ? '#450a0a'
    : tone === 'stopped' ? '#431407'
    : '#0b1220';
}

function notificationIconUrl() {
  try {
    return chrome.runtime.getURL('icon.png');
  } catch {
    return '';
  }
}

function notifyTaskCompleted(task) {
  if (!task || notifiedTasks.has(task.id)) return;
  notifiedTasks.add(task.id);
  const statusText = task.status === 'done' ? '采集完成'
    : task.status === 'failed' ? '采集失败'
    : task.status === 'stopped' ? '采集已停止'
    : `任务结束：${task.status}`;
  const tone = task.status === 'done' ? 'success'
    : task.status === 'failed' ? 'error'
    : task.status === 'stopped' ? 'stopped'
    : 'info';
  setCompletion(`${statusText}。任务 ${task.id}${task.returncode === null ? '' : `，退出码 ${task.returncode}`}`, tone);
  try {
    chrome.notifications?.create(`companyleads-${task.id}`, {
      type: 'basic',
      iconUrl: notificationIconUrl(),
      title: 'Company Leads Collector',
      message: `${statusText}：${task.platform || '采集任务'}`,
      priority: 1,
    });
  } catch {}
}

async function checkHealth() {
  try {
    const d = await helperFetch('/health');
    setHealth(`helper: 已连接，历史任务 ${d.tasks}，运行中 ${d.running_tasks || 0}`);
    if (d.root && !isExpectedHelperRoot(d.root)) {
      setRuntimeStatus(`helper root 指向 ${d.root}，建议在 CompanyLeads_local 运行 install_companyleads.ps1 -SkipPythonInstall 后重启 helper`);
      return;
    }
    if (d.runtime) {
      setRuntimeStatus(`CDP: ${d.runtime.url || '未就绪'} · profile: ${d.runtime.userDataDir || '受控独立窗口'}`);
    }
    try {
      const status = await nativeMessage('helper.getStatus');
      renderNativeStatus(status);
    } catch {}
  } catch (err) {
    try {
      const status = await ensureLocalStack();
      if (status.helperReady) {
        const d = await helperFetch('/health');
        setHealth(`helper: 已连接，历史任务 ${d.tasks}，运行中 ${d.running_tasks || 0}`);
      } else {
        setHealth('helper: 启动失败');
      }
    } catch (nativeErr) {
      // 逐页采集不经过 helper；连不上只代表「批量采集」不可用，不是错误。
      setHealth('ℹ️ 逐页采集可直接使用（打开招聘页即自动采集）。批量采集需安装本机 helper（见 docs 批量采集安装说明），当前未安装。');
      setRuntimeStatus('');
    }
  }
}

function ensurePolling() {
  if (!pollTimer) pollTimer = setInterval(pollTasks, 1500);
}

async function pollTasks() {
  try {
    const d = await helperFetch('/tasks');
    const items = d.items || [];
    renderTasks(items);
    // 只对本会话内下发、且刚结束的任务弹完成通知（避免面板重开时对历史任务刷屏）
    for (const t of items) {
      if (!ACTIVE_STATES.includes(t.status) && (t.id in taskMaxItems) && !notifiedTasks.has(t.id)) {
        notifyTaskCompleted(t);
      }
    }
    const active = items.filter(t => ACTIVE_STATES.includes(t.status));
    if (active.length) {
      ensurePolling();
    } else if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
      await checkHealth();
    }
  } catch (err) {
    setHealth(`任务查询失败：${err.message}`);
  }
}

function normalizedLimit() {
  const value = Number($('max-items').value || 10);
  if (!Number.isFinite(value)) return 10;
  return Math.max(1, Math.min(5000, Math.floor(value)));
}

function syncPlatformDefaults() {
  const platform = $('platform')?.value;
  if (platform !== '51job_talent') return;
  if (!$('keywords').value.trim() || $('keywords').dataset.auto51jobTalent === '1') {
    $('keywords').value = TALENT_51JOB_KEYWORDS;
    $('keywords').dataset.auto51jobTalent = '1';
  }
}

async function startTask() {
  try {
    await ensureLocalStack();
  } catch (err) {
    setHealth(`本机服务启动失败：${err.message}`);
    return;
  }

  const limit = normalizedLimit();
  const payload = {
    platform: $('platform').value,
    keywords: $('keywords').value.trim(),
    max_pages: MAX_AUTO_PAGES,
    max_items: limit,
    per_keyword_limit: 0,
    delay_min: 1,
    delay_max: 2,
    detail_delay_min: 1.5,
    detail_delay_max: 3,
    dry_run: false,
    inspect: false,
    needs_login: loginPolicyFor($('platform').value) === 'required',
    enrich: false,  // 大泉州公司客户改回纯列表采集：不进入详情页、不回填，避免触发验证码风控（其他平台后端本就忽略此字段）
    batch_size: 0,
    item_delay_min: 1,
    item_delay_max: 2,
    batch_delay_min: 0,
    batch_delay_max: 0,
    enrich_batch_size: 0,
    enrich_item_delay_min: 1.5,
    enrich_item_delay_max: 3,
    enrich_batch_delay_min: 0,
    enrich_batch_delay_max: 0,
    post_captcha_multiplier: 3,
    stop_on_captcha: false,
  };

  try {
    setCompletion('');
    const d = await helperFetch('/tasks', { method: 'POST', body: JSON.stringify(payload) });
    currentTask = d.task.id;
    taskMaxItems[d.task.id] = limit;
    notifiedTasks.delete(d.task.id);
    await pollTasks();   // 立即刷新卡片，并在有进行中任务时自动开启轮询
  } catch (err) {
    setHealth(`下发失败：${err.message}`);
  }
}

async function openDashboard() {
  try {
    const status = await nativeMessage('helper.openDashboard');
    renderNativeStatus(status);
    setHealth('已打开管理后台');
  } catch (err) {
    try {
      const cfg = await nativeMessage('helper.getClientConfig');
      window.open(cfg.config?.backendUrl || 'http://127.0.0.1:8000', '_blank');
    } catch {
      window.open('http://127.0.0.1:8000', '_blank');
    }
  }
}

async function stopTask() {
  let active;
  try {
    const d = await helperFetch('/tasks');
    active = (d.items || []).filter(t => ACTIVE_STATES.includes(t.status));
  } catch (err) {
    setHealth(`停止失败：${err.message}`);
    return;
  }
  if (!active.length) {
    setHealth('当前没有可停止的采集任务');
    return;
  }
  setHealth(`正在停止 ${active.length} 个采集任务…`);
  for (const t of active) {
    try {
      await helperFetch(`/tasks/${t.id}/stop`, { method: 'POST' });
    } catch (err) {
      setHealth(`停止任务 ${t.id} 失败：${err.message}`);
    }
  }
  await pollTasks();
  await checkHealth();
}

$('start').addEventListener('click', startTask);
$('stop').addEventListener('click', stopTask);
$('open-dashboard')?.addEventListener('click', openDashboard);
$('platform')?.addEventListener('change', () => { syncPlatformDefaults(); updateLoginHint(); });
$('keywords')?.addEventListener('input', () => { $('keywords').dataset.auto51jobTalent = '0'; });
$('max-items')?.addEventListener('input', () => {
  $('max-items').value = String(normalizedLimit());
});

syncPlatformDefaults();
updateLoginHint();
pollTasks();   // 面板打开时立即展示正在运行的任务（含多任务），并在有进行中任务时自动轮询
checkHealth();
setInterval(checkHealth, 8000);
