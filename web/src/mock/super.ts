// 系统监控
export const systemStatus = [
  { name: 'API 服务', status: 'healthy', value: '正常', detail: '响应 42ms · QPS 128' },
  { name: '数据库', status: 'healthy', value: '正常', detail: 'SQLite · 12.4 MB' },
  { name: 'Worker', status: 'healthy', value: '正常', detail: '3 个进程在线' },
  { name: 'LLM Provider', status: 'warn', value: '部分异常', detail: 'OpenAI 限流' },
];

export const requestVolume = {
  hours: Array.from({ length: 24 }, (_, i) => `${i}:00`),
  values: Array.from({ length: 24 }, (_, i) => 200 + Math.floor(Math.sin(i / 3) * 100) + Math.floor(Math.random() * 80)),
  errors: Array.from({ length: 24 }, () => Math.floor(Math.random() * 8)),
};

export const slowQueries = [
  { endpoint: 'GET /api/v1/queries/sku_heat', avgMs: 1240, p99Ms: 2160, count: 36 },
  { endpoint: 'POST /api/v1/llm/complete', avgMs: 820, p99Ms: 4200, count: 188 },
  { endpoint: 'GET /api/v1/data/outreach', avgMs: 540, p99Ms: 920, count: 624 },
  { endpoint: 'POST /api/v1/ai/generate_outreach', avgMs: 1880, p99Ms: 3600, count: 42 },
  { endpoint: 'GET /api/v1/data/creators', avgMs: 320, p99Ms: 480, count: 1280 },
  { endpoint: 'POST /api/v1/data/creators/bulk', avgMs: 1180, p99Ms: 2240, count: 18 },
  { endpoint: 'GET /api/v1/audit', avgMs: 480, p99Ms: 720, count: 102 },
  { endpoint: 'POST /api/v1/ai/keywords/enrich', avgMs: 2240, p99Ms: 5800, count: 14 },
];

export const resourceGauge = {
  cpu: 38,
  memory: 62,
  disk: 41,
};

// 用户与权限
export const users = [
  { id: 1, username: 'testadmin1', display: '张管理员', role: '部门管理员', dept: '女性护理部', lastLogin: '2026-05-21 09:42', status: 'active' },
  { id: 2, username: 'liao_dev', display: '廖工程师', role: '超级管理员', dept: '技术部', lastLogin: '2026-05-21 02:18', status: 'active' },
  { id: 3, username: 'ceo_boss', display: '老板', role: '公司管理员', dept: '管理层', lastLogin: '2026-05-20 22:30', status: 'active' },
  { id: 4, username: 'testuser', display: '测试 BD', role: '普通用户', dept: '女性护理部', lastLogin: '2026-05-20 18:45', status: 'active' },
  { id: 5, username: 'codex_smoke', display: '运营 PM', role: '普通用户', dept: '母婴护理部', lastLogin: '2026-05-21 10:12', status: 'active' },
  { id: 6, username: 'user_test', display: '剪辑师', role: '只读', dept: '内容部', lastLogin: '2026-05-19 14:20', status: 'active' },
  { id: 7, username: 'intern_zhao', display: '小赵实习生', role: '只读', dept: '运营部', lastLogin: '2026-05-15 11:30', status: 'active' },
  { id: 8, username: 'old_user', display: '旧账号', role: '普通用户', dept: '已离职', lastLogin: '2025-12-10 08:00', status: 'inactive' },
];

export const apiKeys = [
  { id: 1, user: 'liao_dev', prefix: 'sk_x9_live_a1b2', scopes: ['read:*', 'write:*'], created: '2026-01-10', lastUsed: '2 分钟前' },
  { id: 2, user: 'testadmin1', prefix: 'sk_x9_live_c3d4', scopes: ['read:*', 'write:dept'], created: '2026-02-15', lastUsed: '1 小时前' },
  { id: 3, user: 'ceo_boss', prefix: 'sk_x9_live_e5f6', scopes: ['read:*'], created: '2026-03-01', lastUsed: '昨天' },
  { id: 4, user: 'testuser', prefix: 'sk_x9_live_g7h8', scopes: ['read:dept', 'write:creator'], created: '2026-03-20', lastUsed: '3 小时前' },
  { id: 5, user: 'codex_smoke', prefix: 'sk_x9_live_i9j0', scopes: ['read:dept'], created: '2026-04-05', lastUsed: '今天' },
];

// LLM 配置
export const llmProviders = [
  { code: 'anthropic', name: 'Anthropic Claude', type: 'anthropic', baseUrl: 'https://api.anthropic.com', model: 'claude-opus-4-7', active: true, keyMask: 'sk-ant-***...***qB2c', testStatus: 'ok' },
  { code: 'openai', name: 'OpenAI GPT', type: 'openai', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o', active: false, keyMask: 'sk-***...***x8K1', testStatus: 'warn' },
  { code: 'deepseek', name: 'DeepSeek', type: 'openai-compat', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat', active: false, keyMask: 'sk-***...***pN9z', testStatus: 'ok' },
  { code: 'custom-zhipu', name: '智谱 GLM', type: 'openai-compat', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4', active: false, keyMask: 'sk-***...***mT4w', testStatus: 'unknown' },
];

export const llmFeatures = [
  { feature: 'agent', label: 'AI 助手对话', provider: 'anthropic', model: 'claude-opus-4-7' },
  { feature: 'outreach_script', label: '建联话术生成', provider: 'anthropic', model: 'claude-sonnet-4-6' },
  { feature: 'title_optimizer', label: '标题优化', provider: 'openai', model: 'gpt-4o-mini' },
  { feature: 'keyword_enrich', label: '关键词分类', provider: 'deepseek', model: 'deepseek-chat' },
];

export const tokenUsage = {
  days: Array.from({ length: 14 }, (_, i) => `5/${i + 8}`),
  input: Array.from({ length: 14 }, () => 80_000 + Math.floor(Math.random() * 40_000)),
  output: Array.from({ length: 14 }, () => 20_000 + Math.floor(Math.random() * 10_000)),
};

// Webhook
export const webhooks = [
  { id: 1, name: '钉钉 · 日报', url: 'https://oapi.dingtalk.com/robot/send?***', secret: '已配置', triggers: ['建联完成', '日报'], lastStatus: 'ok', lastSent: '今天 09:00' },
  { id: 2, name: '企微 · 异常告警', url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?***', secret: '已配置', triggers: ['错误率>5%'], lastStatus: 'ok', lastSent: '昨天 17:32' },
  { id: 3, name: 'Slack · 技术频道', url: 'https://hooks.slack.com/services/***', secret: '未配置', triggers: ['API 异常'], lastStatus: 'warn', lastSent: '3 天前' },
  { id: 4, name: '飞书 · 周报', url: 'https://open.feishu.cn/open-apis/bot/v2/hook/***', secret: '已配置', triggers: ['周报'], lastStatus: 'ok', lastSent: '上周一' },
];

// 审计日志
export const auditLogs = Array.from({ length: 18 }, (_, i) => {
  const actions = ['INSERT', 'UPDATE', 'DELETE'];
  const tables = ['creator', 'product', 'outreach', 'audit_log', 'user', 'webhook_subscriber'];
  const users = ['liao_dev', 'testadmin1', 'testuser', 'codex_smoke', 'user_test'];
  return {
    id: i + 1,
    ts: `2026-05-${21 - Math.floor(i / 4)} ${10 + (i % 8)}:${(i * 7) % 60 < 10 ? '0' : ''}${(i * 7) % 60}`,
    user: users[i % users.length],
    dept: ['女性护理部', '技术部', '母婴护理部', '管理层', '内容部'][i % 5],
    table: tables[i % tables.length],
    action: actions[i % actions.length],
    recordId: 100 + i * 3,
    summary: ['修改 tier 字段', '新增达人记录', '删除测试数据', '更新 LLM 配置', '调整 webhook 触发'][i % 5],
  };
});

// 资源浏览器
export const resources = [
  { name: 'product', rows: 44, cols: 37, lastWrite: '今天 08:42', writable: true },
  { name: 'creator', rows: 486, cols: 26, lastWrite: '今天 10:18', writable: true },
  { name: 'outreach', rows: 4860, cols: 15, lastWrite: '今天 11:02', writable: true },
  { name: 'product_image', rows: 3143, cols: 5, lastWrite: '5 月 20 日', writable: true },
  { name: 'creator_product', rows: 826, cols: 3, lastWrite: '今天 09:50', writable: true },
  { name: 'category', rows: 6, cols: 5, lastWrite: '5 月 1 日', writable: true },
  { name: 'staff', rows: 28, cols: 3, lastWrite: '5 月 12 日', writable: true },
  { name: 'audit_log', rows: 18_420, cols: 7, lastWrite: '刚刚', writable: false },
  { name: 'webhook_subscriber', rows: 4, cols: 6, lastWrite: '5 月 10 日', writable: true },
  { name: 'creator_leads', rows: 1280, cols: 12, lastWrite: '今天 06:30', writable: true },
];

// 命名查询
export const namedQueries = [
  { name: 'creators_to_contact', desc: '待联系达人池', sqlPreview: "SELECT * FROM creator WHERE current_status='prospect' AND priority IN ('P2','P3') ORDER BY follower_count DESC", lastRun: '昨天', avgMs: 142 },
  { name: 'sku_heat', desc: 'SKU 被建联次数 + 类目聚合', sqlPreview: 'SELECT product_id, COUNT(*) AS n FROM outreach_sku GROUP BY product_id ORDER BY n DESC', lastRun: '今天', avgMs: 286 },
  { name: 'funnel_summary', desc: '转化漏斗各阶段汇总', sqlPreview: "SELECT status, COUNT(*) FROM creator GROUP BY status", lastRun: '今天', avgMs: 64 },
  { name: 'script_performance', desc: '话术模板效果分析', sqlPreview: 'SELECT template_key, ... FROM outreach_example', lastRun: '今天', avgMs: 380 },
  { name: 'outreach_video_tracking', desc: '在投视频指标更新清单', sqlPreview: "SELECT * FROM outreach WHERE video_url IS NOT NULL AND status='video_published'", lastRun: '2 小时前', avgMs: 168 },
  { name: 'creators_high_engagement', desc: '高互动率达人候选', sqlPreview: 'SELECT * FROM creator WHERE engagement_rate > 0.05', lastRun: '今天', avgMs: 96 },
  { name: 'creators_mid_tier_koc', desc: '腰部 KOC 达人', sqlPreview: "SELECT * FROM creator WHERE tier IN ('B','C') AND follower_count BETWEEN 10000 AND 100000", lastRun: '今天', avgMs: 102 },
  { name: 'outreach_auth_pending', desc: '待授权码处理', sqlPreview: "SELECT * FROM outreach WHERE action='authorize' AND status='video_published'", lastRun: '今天', avgMs: 84 },
];

// API 统计
export const apiStats = [
  { endpoint: 'GET /api/v1/data/creators', count: 12_840, avgMs: 32, errorRate: 0.001 },
  { endpoint: 'POST /api/v1/data/outreach/bulk', count: 4_280, avgMs: 145, errorRate: 0.003 },
  { endpoint: 'GET /api/v1/data/products', count: 3_960, avgMs: 28, errorRate: 0 },
  { endpoint: 'POST /api/v1/llm/complete', count: 1_888, avgMs: 820, errorRate: 0.012 },
  { endpoint: 'POST /api/v1/ai/generate_outreach', count: 420, avgMs: 1880, errorRate: 0.024 },
  { endpoint: 'GET /api/v1/queries/sku_heat', count: 360, avgMs: 1240, errorRate: 0.005 },
  { endpoint: 'GET /api/v1/audit', count: 1_020, avgMs: 480, errorRate: 0 },
  { endpoint: 'POST /api/v1/webhooks/test', count: 86, avgMs: 240, errorRate: 0.062 },
];

export const topUsers = [
  { user: 'liao_dev', calls: 24_860, percent: 48.2 },
  { user: 'codex_smoke', calls: 8_420, percent: 16.3 },
  { user: 'testadmin1', calls: 6_280, percent: 12.2 },
  { user: 'testuser', calls: 4_960, percent: 9.6 },
  { user: 'others', calls: 7_080, percent: 13.7 },
];
