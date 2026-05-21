// Dev-mode mock data. When /api/local/* returns 401 (or any error in dev),
// the client returns these fixtures so the UI shell renders with realistic data.

function recentIso(secondsAgo: number) {
  return new Date(Date.now() - secondsAgo * 1000).toISOString();
}

const creators = [
  { handle: 'jasminechiswell', display_name: 'Jasmine Chiswell', country: 'US', followers: 18800000, tier: 'S', email: 'contact@chiswell.io', score: 92, reason: '内容契合度高 + 互动率优' },
  { handle: 'beautyqueen88', display_name: 'Beauty Queen', country: 'UK', followers: 2300000, tier: 'S', email: null, score: 88, reason: '头部达人 + 受众匹配' },
  { handle: 'cottoncrush', display_name: 'Cotton Crush', country: 'CA', followers: 480000, tier: 'A', email: 'cotton@crush.co', score: 84, reason: '腰部达人,转化稳定' },
  { handle: 'wellbeing_blog', display_name: 'Wellness Blog', country: 'AU', followers: 86000, tier: 'B', email: null, score: 79, reason: '测试期评估' },
  { handle: 'glowupwithlin', display_name: 'Glow Up With Lin', country: 'PH', followers: 1200000, tier: 'S', email: 'lin@glowup.io', score: 86, reason: '可投放主力 · 已合作' },
  { handle: 'organicmama_co', display_name: 'Organic Mama', country: 'US', followers: 320000, tier: 'A', email: null, score: 77, reason: '女性受众占比 78%' },
  { handle: 'softouch_official', display_name: 'SofTouch', country: 'US', followers: 920000, tier: 'S', email: 'soft@touch.co', score: 90, reason: 'S 级头部 + GMV 高' },
  { handle: 'breezenovice', display_name: 'Breeze Novice', country: 'UK', followers: 56000, tier: 'C', email: null, score: 68, reason: '长尾达人 KOC' },
  { handle: 'momlife_oasis', display_name: 'Mom Life Oasis', country: 'US', followers: 240000, tier: 'A', email: 'hello@momoasis.com', score: 82, reason: '已合作过 · 履约良好' },
  { handle: 'flowdaily', display_name: 'Flow Daily', country: 'SG', followers: 134000, tier: 'B', email: null, score: 73, reason: '互动率出色' },
  { handle: 'periodtalk', display_name: 'Period Talk', country: 'VN', followers: 38000, tier: 'C', email: null, score: 65, reason: '潜力测试' },
  { handle: 'pristine_pads', display_name: 'Pristine Pads', country: 'US', followers: 720000, tier: 'A', email: 'biz@pristine.com', score: 80, reason: '邮箱可达 + 内容稳定' },
];

export const MOCKS: Record<string, any | ((qs: string) => any)> = {
  '/auth/me': {
    logged_in: true,
    user: { id: 1, username: 'liao', display_name: '廖工程师', email: 'liao@x9.com', role: 'admin', department_code: 'cross_border', active: 1 },
  },
  '/app/status': { ok: true, service: 'X9 后端', version: '2.4.1' },
  '/db/stats': {
    creators: 132,
    recommendations: 48,
    observations: 1284,
    review_pending: 6,
    outreach: 101,
    today_observations: 86,
    today_trend: [4, 6, 8, 12, 18, 25, 32, 28, 22, 18, 14, 10, 8, 6, 4, 3, 2, 1, 2, 3, 5, 8, 10, 12],
  },
  '/db/status': { ok: true },
  // NOTE: '/extension/status' is defined once below in the Collection section
  // (the sessions[] shape the UI consumes); the old flat shape was a dead
  // duplicate key (TS1117) and has been removed.
  '/extension/run-progress': {
    ok: true, status: '正在采集中', done: 184, total: 250, message: '当前批次 · 处理至 jasminechiswell',
  },
  '/admin/business-dashboard': {
    scope: '跨境部门 · 实时数据',
    cards: [
      { label: '本月达人入库', value: 132, sub: '+18 较上月' },
      { label: '推荐转化率', value: '36.4%', sub: '高于均值' },
      { label: 'AI 评分均值', value: 72.5, sub: '近 7 天' },
      { label: '邮件回复率', value: '24.8%', sub: '较上周 +3.2%' },
    ],
    status_rows: [
      { label: 'TikTok 登录有效', value: '✓ 已登录' },
      { label: 'Gmail 绑定', value: '已绑定 2 个账户' },
      { label: '插件最近心跳', value: '18 秒前' },
      { label: '当前任务进度', value: '184 / 250 (74%)' },
      { label: '当前部门', value: 'cross_border' },
      { label: '系统版本', value: '2.4.1' },
    ],
    breakdown: [
      { name: '推荐通过', value: 48 },
      { name: '审核中', value: 12 },
      { name: '已联系', value: 36 },
      { name: '已寄样', value: 18 },
      { name: '已发视频', value: 9 },
      { name: '已授权投放', value: 4 },
    ],
  },
  '/creators/recommended': {
    ok: true, total: 48,
    items: creators.map((c, i) => ({
      id: i + 1,
      handle: c.handle, display_name: c.display_name, platform: 'tiktok', profile_url: 'https://www.tiktok.com/@' + c.handle,
      country: c.country, followers: c.followers, tier: c.tier, email: c.email,
      category_tags: i % 2 === 0 ? ['女性护理', '母婴'] : ['女性护理'],
      recommendation_score: c.score, recommendation_reason: c.reason,
      updated_at: recentIso(i * 3600),
    })),
  },
  '/creators': {
    ok: true, total: 132,
    items: creators.map((c, i) => ({
      id: i + 1, handle: c.handle, display_name: c.display_name, platform: 'tiktok', country: c.country,
      followers: c.followers, tier: c.tier, email: c.email,
    })),
  },
  '/review-tasks': (qs: string) => {
    const status = qs.includes('approved') ? 'approved' : qs.includes('rejected') ? 'rejected' : 'pending';
    if (status !== 'pending') return { ok: true, total: status === 'approved' ? 28 : 9, items: [] };
    return {
      ok: true, total: 6,
      items: Array.from({ length: 6 }, (_, i) => ({
        id: i + 100, creator_id: 300 + i, status: 'pending',
        priority: ['P1', 'P1', 'P2', 'P2', 'P3', 'P3'][i],
        ai_score: [62, 58, 72, 68, 76, 80][i],
        reason: [
          '评分边界值,需人工确认 fit',
          '邮箱字段为空,需复审是否纳入',
          '类目标签与主推 SKU 不完全匹配',
          '粉丝增长异常,疑似买量',
          '内容轻度敏感词,需人工放行',
          '低互动率但 GMV 表现好',
        ][i],
        created_at: recentIso((i + 1) * 7200),
        updated_at: recentIso(i * 1800),
      })),
    };
  },
  '/shared/keywords/dashboard': {
    total: 248, new_24h: 18, pending_classify: 24, last_captured_at: recentIso(1800),
    top_growth: [
      { keyword: 'period underwear', search_volume: 420000, growth_rate: 1.84, rank_position: 3, category: '女性护理' },
      { keyword: 'organic cotton pads', search_volume: 280000, growth_rate: 1.42, rank_position: 7, category: '女性护理' },
      { keyword: 'baby diaper rash', search_volume: 360000, growth_rate: 1.18, rank_position: 5, category: '母婴' },
      { keyword: 'leakproof underwear', search_volume: 190000, growth_rate: 0.96, rank_position: 12, category: '女性护理' },
      { keyword: 'lavender mat', search_volume: 88000, growth_rate: 0.74, rank_position: 24, category: '家居护理' },
      { keyword: 'training pants', search_volume: 145000, growth_rate: 0.62, rank_position: 18, category: '母婴' },
      { keyword: 'adult care pad', search_volume: 92000, growth_rate: 0.52, rank_position: 36, category: '成人护理' },
      { keyword: 'pet pee pad', search_volume: 130000, growth_rate: 0.38, rank_position: 28, category: '宠物' },
    ],
    top_volume: [
      { keyword: 'period underwear', search_volume: 420000, growth_rate: 1.84, rank_position: 3, category: '女性护理' },
      { keyword: 'baby diaper rash', search_volume: 360000, growth_rate: 1.18, rank_position: 5, category: '母婴' },
      { keyword: 'organic cotton pads', search_volume: 280000, growth_rate: 1.42, rank_position: 7, category: '女性护理' },
      { keyword: 'leakproof underwear', search_volume: 190000, growth_rate: 0.96, rank_position: 12, category: '女性护理' },
      { keyword: 'training pants', search_volume: 145000, growth_rate: 0.62, rank_position: 18, category: '母婴' },
      { keyword: 'pet pee pad', search_volume: 130000, growth_rate: 0.38, rank_position: 28, category: '宠物' },
      { keyword: 'adult care pad', search_volume: 92000, growth_rate: 0.52, rank_position: 36, category: '成人护理' },
      { keyword: 'lavender mat', search_volume: 88000, growth_rate: 0.74, rank_position: 24, category: '家居护理' },
    ],
    items: Array.from({ length: 15 }, (_, i) => ({
      id: i + 1,
      keyword: ['sustainable pads', 'menstrual cup', 'eco diaper', 'cotton liner', 'nighttime pad',
                'reusable pad', 'pet litter mat', 'puppy training pad', 'overnight diaper', 'sensitive skin liner',
                'postpartum pads', 'maternity briefs', 'incontinence pad', 'absorbent mat', 'mini liner'][i],
      search_volume: 65000 + i * 8000,
      growth_rate: (Math.random() - 0.25) * 1.3,
      rank_position: 42 + i,
      category: ['女性护理', '母婴', '家居护理', '成人护理', '宠物'][i % 5],
    })),
  },
  '/shared/assistant/info': {
    provider: 'Anthropic',
    model: 'claude-opus-4-7',
    ready: true,
    greeting: '你好!我是 X9 AI 助手,有什么可以帮你的?\n\n常见用法:\n• 查询达人:"帮我找美国地区粉丝 50w+ 的女性护理类达人"\n• 生成话术:"给 @jasminechiswell 写一封英文初次建联邮件"\n• 运维操作:"插件离线了怎么排查?"',
  },
  '/shared/assistant/chat': {
    reply: '收到你的问题!这是 Mock 演示回复 — 接到真实 LLM 后会展示完整的回答内容,支持代码块、列表、Markdown 渲染等。',
  },

  // ---------- Outreach ----------
  '/outreach/templates': {
    ok: true, total: 4,
    items: [
      { id: 'tpl_1', name: '初次建联 · 中文', description: '通用第一次接触模板', language: 'zh', collab_type: 'sample', product_type: 'feminine_care_daily_liner', subject_template: 'X9 × {handle} · 合作邀请', body_template: 'Hi {display_name},\n你好!我是 X9 跨境品牌的 {sender_name}...\n\n{signature}', is_default: 1, is_active: 1, tone: 'friendly', max_length: 1200 },
      { id: 'tpl_2', name: 'First Outreach · EN', description: 'English first contact', language: 'en', collab_type: 'sample', product_type: null, subject_template: 'Quick intro: X9 × @{handle}', body_template: 'Hi {display_name},\n\nI hope this finds you well...\n\nBest,\n{sender_name}', is_default: 0, is_active: 1, tone: 'casual', max_length: 1000 },
      { id: 'tpl_3', name: '寄样确认', description: '寄样前的最后确认', language: 'zh', collab_type: 'sample', product_type: null, subject_template: 'X9 寄样确认 · {product_name}', body_template: 'Hi {display_name},\n样品已为你备好...\n', is_default: 0, is_active: 1, tone: 'formal', max_length: 800 },
      { id: 'tpl_4', name: '视频追问', description: '寄样后催促发视频', language: 'zh', collab_type: 'sample', product_type: null, subject_template: '关于 X9 视频拍摄进度', body_template: 'Hi {display_name},\n上次寄给你的 X9 样品收到了吗?...', is_default: 0, is_active: 1, tone: 'friendly', max_length: 600 },
    ],
  },
  '/outreach/gmail/accounts': {
    ok: true, total: 1,
    items: [
      { id: 'gmail_1', email: 'mercy@x9-test.com', display_name: 'Mercy', label: 'workspace', is_default: 1, is_active: 1, expires_at: null, created_at: recentIso(86400 * 7) },
    ],
  },
  '/outreach/history/1': {
    ok: true, total: 2,
    items: [
      { id: 'eml_a', subject: 'X9 × @jasminechiswell · 合作邀请', to_email: 'contact@chiswell.io', status: 'sent', sent_at: recentIso(86400), from_email: 'mercy@x9-test.com' },
      { id: 'eml_b', subject: 'Re: 寄样确认', to_email: 'contact@chiswell.io', status: 'queued', sent_at: null, from_email: 'mercy@x9-test.com' },
    ],
  },

  // ---------- Collection / Extension ----------
  '/extension/status': {
    sessions: [
      { session_id: 'sess_1', worker_id: 'wk_a8b7c6d5e4f3', account_id: 'mercy_main', online: true, last_heartbeat_at: recentIso(18), current_url: 'https://www.tiktok.com/search?q=organic%20pads', page_type: 'search', tiktok_login_status: 'logged_in' },
    ],
  },
  '/collector/recent-observations': {
    ok: true, total: 50,
    items: Array.from({ length: 20 }, (_, i) => ({
      id: i + 1,
      platform: 'tiktok',
      worker_id: 'wk_a8b7c6d5e4f3',
      search_keyword: ['organic cotton pads', 'period underwear', 'baby diaper', 'training pants', 'lavender mat'][i % 5],
      content_hash: 'sha_' + Math.random().toString(36).slice(2, 10),
      collected_at: recentIso(i * 60),
      created_at: recentIso(i * 60 + 5),
    })),
  },
};

export function matchMock(path: string): any | null {
  if (!path.startsWith('/api/local')) return null;
  const stripped = path.replace('/api/local', '');
  const [route, qs = ''] = stripped.split('?');
  for (const key of Object.keys(MOCKS)) {
    if (route === key || route === key + '/' || route.startsWith(key + '/') || route.startsWith(key + '?')) {
      const v = MOCKS[key];
      return typeof v === 'function' ? v(qs) : v;
    }
  }
  return null;
}
