export const overviewKpis = [
  { label: '30 日 GMV', value: '¥ 2.46M', delta: 12, subLabel: '较上月' },
  { label: '订单数', value: '8,432', delta: 18, subLabel: '近 30 天' },
  { label: '达人池', value: '486', delta: 5, subLabel: '在合作' },
  { label: '总转化率', value: '14.2%', delta: 3, subLabel: '建联到投放' },
  { label: '活跃部门', value: '6 / 6', delta: 0, subLabel: '全员在线' },
  { label: '在投视频', value: '127', delta: 24, subLabel: '7 天新增' },
  { label: '30 日增长', value: '+18%', delta: 18, subLabel: '同比' },
  { label: '异常告警', value: '3', delta: -25, subLabel: '待处理' },
];

export const monthlyRevenue = {
  months: ['11月', '12月', '1月', '2月', '3月', '4月', '5月'],
  departments: ['女性护理部', '母婴护理部', '家居护理部', '宠物用品部', '成人护理部', '海外品牌部'],
  series: [
    [320, 380, 410, 450, 520, 580, 640],
    [280, 290, 310, 340, 380, 410, 450],
    [180, 195, 210, 220, 250, 270, 290],
    [120, 130, 145, 160, 175, 190, 200],
    [150, 160, 170, 185, 200, 220, 240],
    [200, 210, 225, 240, 260, 280, 300],
  ],
};

export const profitMargin = {
  months: ['11月', '12月', '1月', '2月', '3月', '4月', '5月'],
  values: [28.5, 30.1, 31.2, 32.8, 33.5, 34.2, 35.1],
};

export const topSkus = [
  { rank: 1, sku: 'period-undr-A2', name: '云感经期内裤 · L', category: '女性护理', revenue: 487_000, qty: 18_200, margin: 41 },
  { rank: 2, sku: 'cotton-pad-001', name: '纯棉日用卫生巾 · 240mm', category: '女性护理', revenue: 412_000, qty: 32_500, margin: 38 },
  { rank: 3, sku: 'baby-diaper-B1', name: '婴儿超薄纸尿裤 · NB', category: '母婴', revenue: 386_000, qty: 9_100, margin: 35 },
  { rank: 4, sku: 'lavender-pad', name: '薰衣草护理垫 · 60×90', category: '家居护理', revenue: 268_000, qty: 14_800, margin: 42 },
  { rank: 5, sku: 'training-pant', name: 'T 字训练裤 · M', category: '母婴', revenue: 224_000, qty: 6_300, margin: 33 },
  { rank: 6, sku: 'charcoal-mat', name: '活性炭护理垫', category: '家居护理', revenue: 198_000, qty: 11_200, margin: 39 },
  { rank: 7, sku: 'adult-tabs', name: '成人护理垫 · 大码', category: '成人护理', revenue: 176_000, qty: 5_800, margin: 36 },
  { rank: 8, sku: 'cloud-period', name: '云朵经期裤 · 高腰', category: '女性护理', revenue: 152_000, qty: 4_900, margin: 44 },
  { rank: 9, sku: 'pet-mat', name: '宠物隔尿垫', category: '宠物用品', revenue: 134_000, qty: 8_900, margin: 32 },
  { rank: 10, sku: 'men-pads', name: '男士护理垫', category: '成人护理', revenue: 118_000, qty: 4_200, margin: 31 },
];

export const departments = [
  { name: '女性护理部', creators: 142, conv: 18.5, revenue: 640, video: 38, roi: 3.2 },
  { name: '母婴护理部', creators: 98, conv: 15.2, revenue: 450, video: 28, roi: 2.8 },
  { name: '家居护理部', creators: 76, conv: 12.8, revenue: 290, video: 21, roi: 2.4 },
  { name: '宠物用品部', creators: 52, conv: 11.5, revenue: 200, video: 14, roi: 2.1 },
  { name: '成人护理部', creators: 68, conv: 14.6, revenue: 240, video: 16, roi: 2.6 },
  { name: '海外品牌部', creators: 50, conv: 16.2, revenue: 300, video: 19, roi: 3.0 },
];

export const radarMetrics = ['达人数', '转化率', '营收', '视频数', 'ROI', '客单价'];

// 增长趋势 90 天
export const growthSeries = {
  dates: Array.from({ length: 90 }, (_, i) => {
    const d = new Date(2026, 2, 1);
    d.setDate(d.getDate() + i);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  }),
  creators: Array.from({ length: 90 }, (_, i) => 380 + Math.floor(i * 1.2) + Math.floor(Math.random() * 10)),
  skus: Array.from({ length: 90 }, (_, i) => 38 + Math.floor(i / 12) + (Math.random() > 0.85 ? 1 : 0)),
  orders: Array.from({ length: 90 }, (_, i) => 180 + Math.floor(i * 0.8) + Math.floor(Math.random() * 30)),
};

// 全公司转化漏斗
export const funnelData = [
  { name: '潜在线索', value: 4860 },
  { name: '已建联', value: 2420 },
  { name: '已确认', value: 1180 },
  { name: '样品已寄', value: 820 },
  { name: '样品签收', value: 740 },
  { name: '视频已发', value: 542 },
  { name: '已授权', value: 318 },
  { name: '广告投放中', value: 127 },
];

// 各阶段流失 / 时长
export const funnelStageDetail = [
  { stage: '线索→建联', drop: 2440, retained: 2420, days: 2.4 },
  { stage: '建联→确认', drop: 1240, retained: 1180, days: 3.8 },
  { stage: '确认→寄样', drop: 360, retained: 820, days: 1.2 },
  { stage: '寄样→签收', drop: 80, retained: 740, days: 7.5 },
  { stage: '签收→视频', drop: 198, retained: 542, days: 12.0 },
  { stage: '视频→授权', drop: 224, retained: 318, days: 4.6 },
  { stage: '授权→投放', drop: 191, retained: 127, days: 6.2 },
];

// SKU 价值地图(Treemap)
export const skuTreemap = [
  {
    name: '女性护理', children: [
      { name: '云感经期内裤·L', value: 487 },
      { name: '纯棉日用卫生巾·240mm', value: 412 },
      { name: '云朵经期裤·高腰', value: 152 },
      { name: '迷你护理垫', value: 96 },
    ]
  },
  {
    name: '母婴', children: [
      { name: '婴儿超薄纸尿裤·NB', value: 386 },
      { name: 'T 字训练裤·M', value: 224 },
      { name: 'Q 弹纸尿裤·L', value: 108 },
    ]
  },
  {
    name: '家居护理', children: [
      { name: '薰衣草护理垫·60×90', value: 268 },
      { name: '活性炭护理垫', value: 198 },
      { name: '日常护理垫', value: 72 },
    ]
  },
  {
    name: '成人护理', children: [
      { name: '成人护理垫·大码', value: 176 },
      { name: '男士护理垫', value: 118 },
      { name: '一次性裤', value: 64 },
    ]
  },
  {
    name: '宠物用品', children: [
      { name: '宠物隔尿垫', value: 134 },
      { name: '宠物训练垫', value: 58 },
    ]
  },
];

// 达人 Tier 分布
export const tierDistribution = [
  { name: 'S 级', value: 24, color: '#dc2626' },
  { name: 'A 级', value: 86, color: '#ea580c' },
  { name: 'B 级', value: 168, color: '#3370ff' },
  { name: 'C 级', value: 138, color: '#16a34a' },
  { name: 'D 级', value: 70, color: '#86909c' },
];

// 国家分布
export const countryDistribution = [
  { name: 'United States', value: 186 },
  { name: 'United Kingdom', value: 78 },
  { name: 'Canada', value: 48 },
  { name: 'Australia', value: 42 },
  { name: 'Germany', value: 38 },
  { name: 'France', value: 32 },
  { name: 'Philippines', value: 28 },
  { name: 'Indonesia', value: 22 },
  { name: 'Vietnam', value: 12 },
];

// 头部达人 Top 20
export const topCreators = Array.from({ length: 20 }, (_, i) => ({
  rank: i + 1,
  handle: ['beautyqueen_88', 'glowupwithlin', 'organicmama_co', 'wellness_jess',
           'mommyandme_diary', 'cottoncare_official', 'lavenderly', 'puresoftcare',
           'soft_breeze_pads', 'lillygirly', 'ecoperiod_warrior', 'sheflows',
           'comfymama2025', 'tinyfeet_diary', 'midnightnurse', 'gentlecycle',
           'rosehip_haven', 'pinkflora_routine', 'pristine_pads', 'momlife_oasis'][i],
  tier: ['S', 'S', 'S', 'A', 'A', 'A', 'A', 'A', 'A', 'B'][i % 10],
  followers: 2_000_000 - i * 80_000,
  videos: 32 - i,
  gmv30d: 86_000 - i * 3_200,
  conv: 24 - i * 0.6,
}));

// 重要事件 timeline
export const importantEvents = [
  { date: '2026-05-21', type: '签约', level: 'good', title: 'beautyqueen_88 完成年度合作签约', dept: '女性护理部' },
  { date: '2026-05-20', type: '里程碑', level: 'info', title: '30 日 GMV 突破 ¥240 万,创历史新高', dept: '全公司' },
  { date: '2026-05-18', type: '异常', level: 'warn', title: '宠物用品部转化率下滑 8%,需复盘', dept: '宠物用品部' },
  { date: '2026-05-15', type: '签约', level: 'good', title: 'glowupwithlin 视频带货 ROI 4.2x', dept: '女性护理部' },
  { date: '2026-05-12', type: '运营', level: 'info', title: '新增 28 个 KOC 达人入库', dept: '母婴护理部' },
  { date: '2026-05-10', type: '异常', level: 'bad', title: '海外品牌部 3 个 SKU 库存预警', dept: '海外品牌部' },
  { date: '2026-05-08', type: '里程碑', level: 'good', title: '家居护理部完成季度营收目标', dept: '家居护理部' },
  { date: '2026-05-05', type: '运营', level: 'info', title: 'AI 邮件生成功能上线,日均节省 4 小时', dept: '全公司' },
];
