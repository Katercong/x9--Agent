'use strict';

// qzrc 公司详情页/人才详情页 内容脚本
//   - 详情页路径形如 https://www.qzrc.com/company/show/<ID>
//   - 自动提取公司简介 / 地址 / 联系人，POST 到后端 ingest
//   - 在批量回填任务里：完成后向 background 发 "backfill:done"，由 background 关闭 tab

// 终止锚词（强化版，紧贴 Python 端）
const STOP_DESC = [
  '公司地址','工作地址','联系地址','联系方式','联系人','招聘职位',
  '联系电话','电话','传真','公司性质','公司规模','公司福利','公司行业',
  '工作内容','职位信息','申请该职位','申请此职位','申请职位','立即申请',
  '放入收藏','收藏职位','返回顶部','Top',
  '公司地图','地图数据','地图 卫星','查看地图','地图导航','地图',
];
const STOP_ADDR = [
  '联系方式','联系人','联系电话','电话','邮箱','传真',
  '路线','公交','招聘职位','公司简介',
  '工作内容','职位信息','申请该职位','申请此职位','申请职位','立即申请',
  '放入收藏','收藏职位','返回顶部','Top','返回',
  '地图数据','地图 卫星','查看地图','地图导航','地图',
];
const DESC_RE = new RegExp(`(?:公司简介|公司介绍|企业简介|单位简介)[\\s:：]+(.{20,2000}?)(?=${STOP_DESC.join('|')}|$)`);
const ADDR_RE = new RegExp(`(?:公司地址|工作地址|联系地址)[\\s:：]+([^|\\n]{4,200}?)(?=${STOP_ADDR.join('|')}|$)`);
const PHONE_RE = /(?:1[3-9]\d{9}|0\d{2,4}[-\s]?\d{6,8})/;
const EMAIL_RE = /[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/;

// 业务白名单：含其一才像是真的"简介"
const BUSINESS_HINTS = ['我们','主营','经营','成立','专注','致力','从事','旗下','始建',
  '创建','是一家','主要业务','公司业务','提供','服务于','始终','秉承','理念','团队','产品','客户','行业','技术'];
const ADDRESS_HINT_RE = /[路街号楼区省市镇村栋座层室厂园)）]/g;

function looksLikeAddress(text) {
  const t = (text || '').trim();
  if (t.length < 6 || t.length > 80) return false;
  if (BUSINESS_HINTS.some(h => t.includes(h))) return false;
  const hits = (t.match(ADDRESS_HINT_RE) || []).length;
  return hits >= 2;
}

function cleanAddrTail(addr) {
  let a = addr;
  const stops = ['工作内容','职位信息','申请该职位','申请此职位','申请职位','立即申请',
                 '放入收藏','收藏职位','返回顶部','Top','◆','地图数据','地图 卫星','查看地图','地图导航'];
  for (const s of stops) {
    const i = a.indexOf(s);
    if (i > 0) a = a.slice(0, i);
  }
  return a.replace(/[\s·\-◆、，,；;。.]+$/, '').trim();
}

function clean(s) { return (s || '').replace(/\s+/g, ' ').trim(); }

function ingestCompany(payload) {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'backend:ingestCompany', payload }, response => {
      resolve(response || { ok: false, error: chrome.runtime.lastError?.message || 'no response' });
    });
  });
}

function detectCompanyDetail() {
  const m = location.pathname.match(/\/company\/show\/([A-Za-z0-9]+)/);
  return m ? m[1] : null;
}

// 不应该被当成公司名的页面级文案
const BAD_NAME_TOKENS = ['登录', '注册', '首页', '会员中心', '招聘', '简历', '搜索', '大泉州人才网', '错误', '未找到', '404'];

function looksLikeCompanyName(name) {
  if (!name) return false;
  const n = name.trim();
  if (n.length < 3 || n.length > 60) return false;
  if (BAD_NAME_TOKENS.some(t => n === t || n.startsWith(t + ' ') || n === t + '页')) return false;
  // 公司名常见后缀
  if (/(公司|有限|股份|工厂|集团|中心|工作室|事务所|机构|学校|商行|商店|个体|店|厂|社|社会|协会)$/.test(n)) return true;
  if (n.length >= 4) return true;   // 长度够也接受
  return false;
}

// qzrc 验证码页关键字
const QZRC_CAPTCHA_TOKENS = [
  '本次访问需要做以下验证码校验', '拖动图片验证', '图形验证',
  '滑动验证', '请完成验证', '验证码校验',
];

function isQzrcCaptchaPage() {
  const head = ((document.body && document.body.innerText) || '').slice(0, 800);
  return QZRC_CAPTCHA_TOKENS.some(t => head.includes(t));
}

function splitPrewrap(prewrap) {
  // 实测：[地址] + "地图数据"/"地图 卫星" + [公司简介]
  const m = prewrap.match(/(地图数据|地图\s*卫星)/);
  if (!m) {
    // 整段：用业务白名单判定归属
    const t = prewrap.trim();
    if (BUSINESS_HINTS.some(h => t.includes(h)) && t.length >= 30) {
      return { desc: t.replace(/^(公司简介|公司介绍|企业简介|单位简介)[\s:：]*/, '').slice(0, 2000) };
    }
    if (t.length <= 200) {
      const addrChars = (t.match(ADDRESS_HINT_RE) || []).length;
      if (addrChars >= 2) {
        return { addr: t.replace(/^(公司地址|工作地址|联系地址)[\s:：]*/, '').slice(0, 300) };
      }
    }
    return {};
  }
  const head = prewrap.slice(0, m.index).trim();
  const tail = prewrap.slice(m.index + m[0].length).trim();
  // tail 剥离已知地图噪声（与 Python 端 _MAP_NOISE_PATTERNS 对齐）
  const MAP_NOISE = [
    /©\s*\d{2,4}(?:\s*[-/]\s*\d+)?/g,
    /GS\s*\(\d{2,4}\)\s*\d+\s*号?/g,
    /GS\s*-\s*\d+/g,
    /\d{1,3}\s*°[\d'′″\s.]*/g,
    /地图|卫星|路线|导航|缩放|放大|缩小|交通/g,
    /Tencent|腾讯|百度|高德|Google|Maps/gi,
  ];
  let tailClean = tail;
  for (const pat of MAP_NOISE) tailClean = tailClean.replace(pat, ' ');
  tailClean = tailClean.replace(/\s+/g, ' ').trim()
    .replace(/^[\s©®&、，,；;。.·\-◆号]+/, '').trim()
    .replace(/^(公司简介|公司介绍|企业简介|单位简介)[\s:：]*/, '').trim();

  const headClean = head
    .replace(/^(公司地址|工作地址|联系地址)[\s:：]*/, '')
    .replace(/[\s·\-◆、，,；;。.]+$/, '')
    .trim();
  const out = {};
  if (headClean.length >= 4 && headClean.length <= 200) out.addr = headClean.slice(0, 300);
  if (tailClean.length >= 20) out.desc = tailClean.slice(0, 2000);
  return out;
}

function extractFromDOM() {
  const out = {};

  // 候选名字 → 取第一个合法的
  const candidates = [];
  for (const sel of ['h1.company-name', 'h2.company-name', '.company-title',
                     'h1', 'h2.title', '.page-title']) {
    document.querySelectorAll(sel).forEach(el => {
      const t = clean(el.innerText);
      if (t) candidates.push(t);
    });
  }
  const title = clean(document.title || '').replace(/\s*[-|·_]\s*(大泉州人才网|qzrc.*|招聘.*).*$/i, '').trim();
  if (title) candidates.push(title);
  for (const c of candidates) {
    if (looksLikeCompanyName(c)) { out.company_name = c; break; }
  }

  // ① 优先 DOM 区块：.company-box .bk.prewrap → 切分为 addr + desc
  const prewrapEl = document.querySelector('.company-box .bk.prewrap')
                 || document.querySelector('.company-box .prewrap')
                 || document.querySelector('.bk.prewrap');
  if (prewrapEl) {
    const prewrapText = clean(prewrapEl.innerText);
    const split = splitPrewrap(prewrapText);
    if (split.addr) out.company_address = split.addr;
    if (split.desc) out.company_description = split.desc;
    console.log(`[qzrc] prewrap 切分: addr=${(split.addr || '').length} 字 / desc=${(split.desc || '').length} 字`);
  }

  // ② 整页正则兜底（仅 prewrap 没拿到时）
  const text = clean(document.body ? document.body.innerText : '');
  if (!out.company_description) {
    const d = text.match(DESC_RE);
    if (d) {
      const cand = d[1].trim();
      if (!looksLikeAddress(cand)) out.company_description = cand.slice(0, 2000);
    }
  }
  if (!out.company_address) {
    const a = text.match(ADDR_RE);
    if (a) {
      const cleaned = cleanAddrTail(a[1].trim());
      if (cleaned.length >= 4 && cleaned.length <= 150) out.company_address = cleaned.slice(0, 300);
    }
  }

  // ③ DOM selector 严格兜底
  if (!out.company_description) {
    for (const sel of ['div.intro-box', '.company-info-content', '.company-description',
                       "[class*='company-intro']", "[class*='companyIntro']"]) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const txt = clean(el.innerText);
      if (txt.length > 30 && !looksLikeAddress(txt) && BUSINESS_HINTS.some(h => txt.includes(h))) {
        out.company_description = txt.slice(0, 2000);
        break;
      }
    }
  }

  // ④ 联系电话/邮箱（如果详情页直接列出）
  const p = text.match(PHONE_RE);
  if (p) out.contact_phone = p[0];
  const e = text.match(EMAIL_RE);
  if (e) out.contact_email = e[0];

  // ⑤ 行业/规模（如果显式标注）
  const indM = text.match(/(?:公司行业|所属行业|行业类型)[\s:：]+([^|\n]{2,40}?)(?=公司规模|公司性质|招聘职位|联系方式|$)/);
  if (indM) out.industry = indM[1].trim();
  const sizeM = text.match(/(?:公司规模|员工规模)[\s:：]+([^|\n]{2,30}?)(?=公司性质|招聘|联系|$)/);
  if (sizeM) out.size_range = sizeM[1].trim();

  return out;
}

async function postIngest(payload) {
  try {
    const res = await ingestCompany(payload);
    if (!res.ok) {
      console.warn('[qzrc回填] 推送失败', res.status, res.error || '');
      return { ok: false, status: res.status, error: res.error || JSON.stringify(res.body || {}) };
    }
    const j = res.body || {};
    console.log('[qzrc回填] ✓', payload.company_name, '→ tier=' + j.tier);
    return { ok: true, ...j };
  } catch (err) {
    console.warn('[qzrc回填] 请求异常', err.message);
    return { ok: false, error: err.message };
  }
}

async function runCompanyDetailFlow() {
  const cid = detectCompanyDetail();
  if (!cid) return;

  // 给页面一点时间渲染 SPA 内容
  await new Promise(r => setTimeout(r, 1500));

  // ─── 验证码页检测：命中时不抓不写，让 background 暂停 ───
  if (isQzrcCaptchaPage()) {
    console.warn('[qzrc回填] 命中验证码页，暂停。请人工通过验证后重试');
    chrome.runtime?.sendMessage?.({
      type: 'backfill:done',
      platform_company_id: cid,
      ok: false,
      reason: 'captcha',
    });
    return;
  }

  const extracted = extractFromDOM();
  if (!extracted.company_name) {
    console.warn('[qzrc回填] 没拿到公司名，跳过');
    chrome.runtime?.sendMessage?.({
      type: 'backfill:done', platform_company_id: cid, ok: false, reason: 'no_company_name',
    });
    return;
  }

  const payload = {
    platform: 'qzrc',
    platform_company_id: cid,
    source_url: location.href,
    source_mode: 'job_seeker',
    ...extracted,
  };
  const result = await postIngest(payload);

  // 告诉 background 这条做完了（不论成功/失败，让批量回填能继续）
  chrome.runtime?.sendMessage?.({
    type: 'backfill:done',
    platform_company_id: cid,
    ok: result.ok,
    got_desc: !!extracted.company_description,
    got_addr: !!extracted.company_address,
    error: result.error,
  });
}

if (detectCompanyDetail()) {
  runCompanyDetailFlow();
  console.log('[qzrc回填] qzrc_collector.js 已加载 —', location.pathname);
}
