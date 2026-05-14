// 部门管理员 mock — 数字与参考截图严格对齐
export const dashboardKpis = {
  topRow: [
    { label: '总达人', value: 33, subLabel: '达人总数', delta: 0 },
    { label: '今日采集', value: 0, delta: 0 },
    { label: '已推荐', value: 17, delta: 13 },
    { label: '待审核', value: 6, delta: -14 },
    { label: '已建联', value: 3, delta: 50 },
  ],
  // 业务概览 10 项
  overview: [
    { label: '推荐线索', value: 17, delta: 6 },
    { label: '待联系', value: 0, delta: 0 },
    { label: '已推进', value: 1, delta: 100 },
    { label: '待回复', value: 0, delta: 0 },
    { label: '近 7 天新增', value: 29, delta: 21 },
    { label: '未分配推荐', value: 13, delta: -7 },
    { label: '已发邮件', value: 3, delta: 50 },
    { label: '已寄样', value: 0, delta: 0 },
    { label: '视频已发布', value: 0, delta: 0 },
    { label: '可联系达人', value: 29, delta: 16 },
  ],
};

export const trend7d = {
  dates: ['5/15', '5/16', '5/17', '5/18', '5/19', '5/20', '5/21'],
  values: [12, 15, 10, 18, 22, 24, 29],
};

export const statusDistribution = {
  total: 33,
  data: [
    { name: '未填写', value: 32, color: '#94a3b8' },
    { name: '已建联', value: 1, color: '#3370ff' },
  ],
};

export const productDirection = [
  { name: '未填写', value: 28 },
  { name: '经期护理垫', value: 3 },
  { name: '日用护理垫', value: 1 },
  { name: '女性护理', value: 1 },
];

export const priorityDistribution = [
  { label: 'P2', value: 4 },
  { label: 'P3', value: 14 },
  { label: 'P4', value: 15 },
];

export const bdFollowUp = [
  { owner: '未填写', recommend: 13, contact: 0, advance: 0 },
  { owner: 'testuser', recommend: 2, contact: 0, advance: 1 },
  { owner: 'codex_smoke', recommend: 1, contact: 0, advance: 0 },
  { owner: 'user_test', recommend: 1, contact: 0, advance: 0 },
];

// 达人管理 mock(参考截图的 33 达人池)
const handles = [
  'beautyqueen_88', 'glowupwithlin', 'organicmama_co', 'wellness_jess',
  'mommyandme_diary', 'cottoncare_official', 'lavenderly', 'puresoftcare',
  'soft_breeze_pads', 'lillygirly', 'ecoperiod_warrior', 'sheflows',
  'comfymama2025', 'tinyfeet_diary', 'midnightnurse', 'gentlecycle',
  'rosehip_haven', 'pinkflora_routine', 'pristine_pads', 'momlife_oasis',
  'softouch_official', 'mistypetal', 'theflowstudio', 'dailywellbeingco',
  'femcarediaries', 'breezenovice', 'lullaby_mama', 'puriskin_co',
  'cloud9_period', 'feminineflow', 'cottoncradle_co', 'softhugs_baby', 'gentleglow_x',
];
export const creators = handles.map((handle, i) => {
  const tiers = ['S', 'A', 'B', 'C', 'D'];
  const statuses = [
    'prospect', 'prospect', 'prospect', 'contacted',
    'confirmed', 'sample_shipped', 'video_published', 'ad_running',
  ];
  const owners = ['未填写', 'testuser', 'codex_smoke', 'user_test'];
  return {
    id: i + 1,
    handle,
    nickname: handle.replace(/_/g, ' '),
    tier: tiers[i % tiers.length],
    followers: 8000 + Math.floor(Math.random() * 2_000_000),
    gmv30d: Math.floor(Math.random() * 80000),
    status: i < 2 ? statuses[(i + 3) % statuses.length] : i < 4 ? statuses[3] : 'prospect',
    owner: owners[i % owners.length],
    country: ['US', 'UK', 'CA', 'AU', 'PH'][i % 5],
    lastContact: i < 3 ? `2026-05-${10 + i}` : null,
    priority: ['P2', 'P3', 'P4'][i % 3],
  };
});

// 线索池 mock
export const leads = Array.from({ length: 24 }, (_, i) => ({
  id: i + 1,
  platform: ['TikTok', 'Instagram', 'YouTube'][i % 3],
  handle: ['fitwithamy', 'newmom_journey', 'cottoncrush', 'wellbeing_blog',
           'mama_minute', 'organic_routine', 'tabbypads', 'careful_living',
           'glowingmom', 'flowdaily', 'softerlife', 'periodtalk',
           'mama_corner', 'pure_routines', 'cottongram', 'sleepymama',
           'softlove_co', 'breezelife', 'lillypads', 'wellnessmama_x',
           'caringspace', 'mom_simply', 'gentleflo', 'cleanmamadiary'][i],
  name: '潜在达人 ' + (i + 1),
  followers: 5000 + Math.floor(Math.random() * 500_000),
  fitLevel: ['高', '中', '低'][i % 3],
  priority: ['P2', 'P3', 'P4'][i % 3],
  category: ['女性护理', '母婴', '宠物', '家居'][i % 4],
  email: i % 3 === 0 ? `contact${i}@example.com` : null,
  status: ['待审核', '已推荐', '待联系', '已联系'][i % 4],
  collectedAt: `2026-05-${(i % 14) + 8}`,
  score: 50 + Math.floor(Math.random() * 50),
}));

// 邮件队列 mock
export const emailTemplates = [
  { name: '初次建联 · 女性护理', useCount: 18, openRate: 0.42, replyRate: 0.12 },
  { name: '寄样确认 · 通用', useCount: 9, openRate: 0.78, replyRate: 0.55 },
  { name: '视频发布提醒 · 中文', useCount: 6, openRate: 0.65, replyRate: 0.31 },
  { name: '广告授权续约 · 英文', useCount: 4, openRate: 0.5, replyRate: 0.25 },
];

export const emailQueue = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1,
  to: creators[i % creators.length].handle + '@gmail.com',
  template: emailTemplates[i % emailTemplates.length].name,
  status: ['草稿', '已发送', '已读', '已回复', '待回复'][i % 5],
  sku: ['cotton-pad-001', 'period-undr-A2', 'baby-diaper-B1'][i % 3],
  sentAt: i % 5 !== 0 ? `2026-05-${10 + (i % 8)}` : null,
  opened: i % 3 === 0,
  replied: i % 5 === 3,
}));

// 样品物流 mock
export const samples = Array.from({ length: 8 }, (_, i) => ({
  id: i + 1,
  creator: creators[i].handle,
  sku: ['cotton-pad-001', 'period-undr-A2', 'baby-diaper-B1', 'lavender-pad'][i % 4],
  qty: 1 + (i % 3),
  carrier: ['顺丰', '中通', 'DHL', 'UPS'][i % 4],
  trackNo: 'SF' + (1000_0000_0000 + i).toString(),
  shippedAt: `2026-05-${5 + i}`,
  estimatedAt: `2026-05-${15 + i}`,
  deliveredAt: i < 3 ? `2026-05-${14 + i}` : null,
  delayDays: i > 5 ? 3 + i : 0,
  status: i < 3 ? '已签收' : i < 6 ? '在途' : '延迟',
}));

// 在投视频 mock
export const videos = Array.from({ length: 10 }, (_, i) => ({
  id: i + 1,
  thumbnail: `https://picsum.photos/seed/video${i}/200/300`,
  creator: creators[i].handle,
  sku: ['cotton-pad-001', 'period-undr-A2', 'baby-diaper-B1'][i % 3],
  url: `https://www.tiktok.com/@${creators[i].handle}/video/${7000000000000000000 + i}`,
  publishedAt: `2026-05-${i + 8}`,
  views: 12000 + Math.floor(Math.random() * 980000),
  likes: 800 + Math.floor(Math.random() * 50000),
  comments: 20 + Math.floor(Math.random() * 2000),
  shares: 10 + Math.floor(Math.random() * 500),
  lastUpdate: `2026-05-${20 - (i % 5)}`,
  hoursAgo: i * 6,
}));

// 产品(部门内主推 SKU)
export const products = [
  { sku: 'cotton-pad-001', name: '纯棉日用卫生巾 · 240mm', category: '女性护理', priceUsd: 4.99, status: '主推', match: 'A' },
  { sku: 'period-undr-A2', name: '云感经期内裤 · L', category: '女性护理', priceUsd: 12.99, status: '主推', match: 'A' },
  { sku: 'baby-diaper-B1', name: '婴儿超薄纸尿裤 · NB', category: '母婴', priceUsd: 19.99, status: '正常', match: 'B' },
  { sku: 'lavender-pad', name: '薰衣草护理垫 · 60×90', category: '家居护理', priceUsd: 7.49, status: '正常', match: 'B' },
  { sku: 'training-pant', name: 'T 字训练裤 · M', category: '母婴', priceUsd: 14.99, status: '正常', match: 'C' },
  { sku: 'charcoal-mat', name: '活性炭护理垫', category: '家居护理', priceUsd: 8.99, status: '正常', match: 'C' },
];

// 设置 - 部门成员
export const deptMembers = [
  { name: 'testuser', role: 'BD', email: 'test@x9.com', joined: '2025-12-01', status: 'active' },
  { name: 'codex_smoke', role: 'PM', email: 'codex@x9.com', joined: '2026-01-15', status: 'active' },
  { name: 'user_test', role: '剪辑', email: 'edit@x9.com', joined: '2026-02-20', status: 'active' },
  { name: 'testadmin1', role: '部门管理员', email: 'admin@x9.com', joined: '2025-11-10', status: 'active' },
];
