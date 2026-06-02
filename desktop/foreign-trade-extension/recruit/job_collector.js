'use strict';

const COLLECT_DELAY_MS = 800;

const CROSSBORDER_KEYWORDS = [
  // 核心跨境词
  '跨境', '亚马逊', 'tiktok', 'tiktok shop', '海外', '出口', '外贸',
  '供应链', '海外仓', '品牌出海', 'amazon', 'shopify', '独立站',
  // 美区 / 北美优先词
  '北美', '美区', 'fba', 'fbt', '北美市场',
  // 平台卖家/供应商
  'temu', 'shein', '跨境卖家', '跨境店', '亚马逊卖家',
  // 物流/中间商
  '货代', '一件代发', '柔性供应链', '小单快反',
  // 分销相关
  '分销团长', '分销商',
];

const EXCLUDE_COMPANY_KEYWORDS = [
  '人才网', '招聘网', '招聘平台', '人力资源', '劳务派遣', '猎头',
  '职业培训', '培训学校', '求职', '简历',
];

const _posted = new Set();

function cleanString(text) {
  return (text || '').toString().trim().replace(/\s+/g, ' ');
}

function cleanText(el) {
  if (!el) return '';
  return cleanString(el.innerText);
}

function hasCrossborder(texts) {
  const joined = texts.filter(Boolean).join(' ').toLowerCase();
  return CROSSBORDER_KEYWORDS.some(kw => joined.includes(kw));
}

function isExcludedCompany(company, texts = []) {
  const joined = [company, ...texts].filter(Boolean).join(' ').toLowerCase();
  return EXCLUDE_COMPANY_KEYWORDS.some(kw => joined.includes(kw));
}

function firstText(root, selectors) {
  for (const sel of selectors) {
    const el = root.querySelector(sel);
    const txt = cleanText(el);
    if (txt) return txt;
  }
  return '';
}

function firstAttr(root, selectors, attr) {
  for (const sel of selectors) {
    const el = root.querySelector(sel);
    const val = el?.getAttribute(attr);
    if (val) return val;
  }
  return '';
}

function absUrl(url) {
  if (!url) return '';
  try { return new URL(url, location.href).href; } catch { return url; }
}

function extractZhaopinCompanyId(...values) {
  const joined = values.filter(Boolean).join(' ');
  const patterns = [
    /(?:companyId|company_id|companyNumber|comId)[=/:\s]+([A-Za-z0-9_-]{4,})/i,
    /\/companydetail\/([A-Za-z0-9_-]+)/i,
    /\b(CZ\d{5,}|CC\d{5,}|C\d{6,})\b/i,
  ];
  for (const p of patterns) {
    const m = joined.match(p);
    if (m) return m[1];
  }
  return '';
}

function ingestCompany(payload) {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'backend:ingestCompany', payload }, response => {
      resolve(response || { ok: false, error: chrome.runtime.lastError?.message || 'no response' });
    });
  });
}

function extractContacts(text) {
  const src = cleanString(text);
  const out = {};
  const emails = src.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g);
  if (emails?.length) out.contact_email = emails[0];
  const phones = src.match(/(?:1[3-9]\d{9}|0\d{2,4}[-\s]?\d{6,8})/g);
  if (phones?.length) out.contact_phone = [...new Set(phones.slice(0, 3).map(p => p.replace(/\s+/g, '')))].join(' / ');
  const sameWechat = src.match(/(1[3-9]\d{9})[^。；;，,\n]{0,12}(?:微信同号|微信同手机号|同微信|手机号同微信)/);
  if (sameWechat) out.hr_wechat = sameWechat[1];
  else if (phones?.length && /微信同号|微信同手机号|同微信|手机号同微信/.test(src)) out.hr_wechat = phones[0].replace(/\s+/g, '');
  const wx = src.match(/(?:微信|微信号|VX|WeChat)[：:\s]*([A-Za-z0-9_-]{5,30})/i);
  if (wx && !out.hr_wechat) out.hr_wechat = wx[1];
  if (Object.keys(out).length) {
    out.contact_source = '公开招聘 JD';
    out.contact_verified = false;
  }
  return out;
}

function extractSection(text, labels, stops, minLen = 20, maxLen = 2000) {
  const labelPart = labels.join('|');
  const stopPart = stops.join('|');
  const re = new RegExp(`(?:${labelPart})[\\s:：]+([\\s\\S]{${minLen},${maxLen}}?)(?=${stopPart}|$)`, 'i');
  const m = text.match(re);
  return m ? cleanString(m[1]).slice(0, maxLen) : '';
}

async function postCompany(data) {
  const key = `${data.platform}:${data.platform_company_id || data.company_name}:${data.jd_title}:${data.source_url || ''}`;
  if (_posted.has(key)) return;
  _posted.add(key);
  try {
    const res = await ingestCompany(data);
    if (res.ok) {
      const j = res.body || {};
      console.log(`[公司线索] ✓ ${data.company_name} → tier=${j.tier} score=${j.score}`);
    } else {
      console.warn(`[公司线索] ✗ ${data.company_name} HTTP ${res.status || ''} ${res.error || ''}`);
    }
  } catch (err) {
    console.warn('[公司线索] 推送失败:', err.message);
  }
}

// ---------------------------------------------------------------------------
// 51job
// ---------------------------------------------------------------------------
function collect51job() {
  const cards = document.querySelectorAll('div.e a.el, div.joblist-box__item a');
  const results = [];
  cards.forEach(card => {
    const row = card.closest('tr') || card.closest('li') || card.parentElement;
    if (!row) return;
    const jdTitle = cleanText(card);
    const jdUrl = card.href || '';
    const cells = row.querySelectorAll('td');
    let company = '', city = '';
    if (cells.length > 1) {
      company = cleanText(cells[1]);
      city = cells.length > 2 ? cleanText(cells[2]) : '';
    } else {
      const cn = row.querySelector('.cname, .company-name, [class*="company"]');
      company = cn ? cleanText(cn) : '';
      const cityEl = row.querySelector('[class*="city"], [class*="location"], [class*="area"]');
      city = cityEl ? cleanText(cityEl) : '';
    }
    if (!company || isExcludedCompany(company, [jdTitle])) return;
    if (!hasCrossborder([jdTitle, company])) return;
    results.push({
      platform: '51job',
      company_name: company,
      jd_title: jdTitle,
      city,
      source_url: jdUrl,
      source_mode: 'job_seeker',
      source_type: 'public_job',
      permission_note: '来源为公开招聘职位页，用于判断公司跨境业务需求',
    });
  });
  return results;
}

// ---------------------------------------------------------------------------
// Zhaopin
// ---------------------------------------------------------------------------
function collectZhaopin() {
  if (/\/jobs?\//i.test(location.pathname) || /jobs\.zhaopin\.com/i.test(location.hostname)) {
    return collectZhaopinDetail();
  }

  const cards = document.querySelectorAll(
    'li.positionlist_item, div.contentpanel-map-job, div.job-card, ' +
    'div[class*="joblist-box__item"], div[class*="positionlist_item"], ' +
    'div[class*="job-card"], div[class*="contentpile"] div[class*="item"]'
  );
  const results = [];
  cards.forEach(card => {
    const titleEl = card.querySelector(
      'a.position-title, a.jobname, a[class*="job-name"], ' +
      'a[class*="position-title"], a[href*="jobs.zhaopin.com"]'
    );
    const companyEl = card.querySelector(
      'a.company-name, a.companyname, a[class*="company"], ' +
      '[class*="companyName"] a, [class*="company-name"] a'
    );
    const jdTitle = titleEl ? cleanText(titleEl) : '';
    const cardText = cleanText(card);
    let company = companyEl ? cleanText(companyEl) : '';
    if (company.length > 80) {
      company = cleanString(cardText.match(/(?:公司名称|招聘单位|企业名称)[\s:：]+([^\n|]{2,80})/)?.[1] || '');
    }
    const city = firstText(card, ['span.work-area', 'span.area', '[class*="city"]', '[class*="area"]', '[class*="job-area"]']);
    const salary = firstText(card, ['[class*="salary"]', '.salary', '.job-salary', '.position-salary']);
    const tags = firstText(card, ['[class*="tag"]', '[class*="welfare"]', '[class*="requirement"]']);
    const jdUrl = titleEl?.href || '';
    const companyUrl = companyEl?.href || '';
    const companyId = card.getAttribute('data-company-id') || extractZhaopinCompanyId(companyUrl, jdUrl, cardText);
    if (!company || isExcludedCompany(company, [jdTitle, tags])) return;
    if (!hasCrossborder([jdTitle, company, tags])) return;
    results.push({
      platform: 'zhaopin',
      platform_company_id: companyId,
      company_name: company.slice(0, 300),
      jd_title: jdTitle.slice(0, 300),
      city,
      salary_range: salary,
      source_url: absUrl(jdUrl),
      source_mode: 'job_seeker',
      source_type: 'public_job',
      permission_note: '来源为智联招聘公开职位页，用于判断公司跨境业务需求',
      raw_data: { company_url: companyUrl, card_text: cardText.slice(0, 1200) },
    });
  });
  return results;
}

function collectZhaopinDetail() {
  const bodyText = cleanString(document.body?.innerText || '');
  const jdTitle = firstText(document, [
    'h1', '.job-title', '[class*="job-title"]', '[class*="position-title"]',
  ]) || cleanString(document.title).replace(/[-_|].*$/, '');
  let company = firstText(document, [
    'a.company-name', '.company-name', '[class*="company-name"]',
    '[class*="companyName"]', '[class*="company"] a',
  ]);
  if (company.length > 80) {
    const m = bodyText.match(/(?:公司名称|招聘单位|企业名称)[\s:：]+([^\n|]{2,80})/);
    company = m ? cleanString(m[1]) : '';
  }
  const salary = firstText(document, ['.salary', '[class*="salary"]', '[class*="job-salary"]']);
  const city = firstText(document, ['[class*="city"]', '[class*="area"]', '[class*="work"]']) ||
    (bodyText.match(/(?:工作地点|工作城市)[\s:：]+([^\n|]{2,60})/)?.[1] || '');

  let jdDescription = firstText(document, [
    '.job-detail', '.describtion', '.description', '.job-desc',
    '[class*="job-detail"]', '[class*="jobDescription"]',
  ]);
  if (!jdDescription || !/(职位|岗位|职责|要求|任职)/.test(jdDescription)) {
    jdDescription = extractSection(
      bodyText,
      ['职位描述', '岗位职责', '任职要求', '工作职责'],
      ['公司介绍', '公司简介', '工作地址', '职位福利', '工商信息']
    );
  }

  let companyDescription = firstText(document, [
    '.company-intro', '.company-about', '.company-info', '.company-profile',
    '[class*="company-intro"]', '[class*="companyInfo"]',
    '[class*="company-profile"]', '[class*="company"] [class*="intro"]',
  ]);
  if (!companyDescription || companyDescription.length < 20) {
    companyDescription = extractSection(
      bodyText,
      ['公司介绍', '公司简介', '企业介绍', '企业简介'],
      ['工商信息', '工作地址', '公司地址', '在招职位']
    );
  }

  let address = firstText(document, ['.job-address', '.company-address', '[class*="address"]', '[class*="work-address"]']);
  if (!address) address = bodyText.match(/(?:工作地址|公司地址|上班地址)[\s:：]+([^|\n]{4,180})/)?.[1] || '';

  const industry = bodyText.match(/(?:行业|所属行业)[\s:：]+([^|\n]{2,80})/)?.[1] || '';
  const sizeRange = bodyText.match(/(?:公司规模|规模)[\s:：]+([^|\n]{2,80})/)?.[1] || '';
  const companyId = extractZhaopinCompanyId(location.href, bodyText);

  if (!company || isExcludedCompany(company, [jdTitle, jdDescription, companyDescription])) return [];
  if (!hasCrossborder([jdTitle, jdDescription, companyDescription, company])) return [];

  return [{
    platform: 'zhaopin',
    platform_company_id: companyId,
    company_name: company.slice(0, 300),
    jd_title: jdTitle.slice(0, 300),
    city: cleanString(city).slice(0, 100),
    salary_range: cleanString(salary).slice(0, 120),
    industry: cleanString(industry).slice(0, 200),
    size_range: cleanString(sizeRange).slice(0, 60),
    company_address: cleanString(address).slice(0, 300),
    company_description: companyDescription.slice(0, 2000),
    source_url: location.href,
    source_mode: 'job_seeker',
    source_type: 'public_job',
    permission_note: '来源为智联招聘公开职位页，用于判断公司跨境业务需求',
    jd_description: jdDescription.slice(0, 2000),
    raw_data: { detail_text: bodyText.slice(0, 2500) },
    ...extractContacts(jdDescription),
  }];
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
function detectPlatform() {
  const h = location.hostname;
  if (h.includes('51job')) return '51job';
  if (h.includes('zhaopin')) return 'zhaopin';
  return null;
}

async function collectAndPost() {
  const plat = detectPlatform();
  if (!plat) return;
  const entries = plat === '51job' ? collect51job() : collectZhaopin();
  if (!entries.length) return;
  console.log(`[公司线索] 本页发现 ${entries.length} 条跨境公司`);
  for (const e of entries) {
    await postCompany(e);
    await new Promise(r => setTimeout(r, 120));
  }
}

let _timer = null;
function schedule() {
  clearTimeout(_timer);
  _timer = setTimeout(collectAndPost, COLLECT_DELAY_MS);
}

schedule();

const _push = history.pushState.bind(history);
const _replace = history.replaceState.bind(history);
history.pushState = (...args) => { _push(...args); schedule(); };
history.replaceState = (...args) => { _replace(...args); schedule(); };
window.addEventListener('popstate', schedule);

console.log('[公司线索] job_collector.js 已加载 —', location.hostname);
