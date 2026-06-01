import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle, ArrowLeft, ExternalLink, Link2, Mail, MessageSquare,
  RefreshCw, Send, ShieldCheck, UserCheck, UserMinus,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { OutreachDrawer } from '@/components/outreach/OutreachDrawer';
import { TkScriptModal } from '@/components/outreach/TkScriptModal';
import { useAcquireOutreachLock, useClaimCreator, useCreator, useReleaseCreator } from '@/hooks/useApi';
import { formatCompact, maskEmail, shortRelative } from '@/lib/format';
import type { Language } from '@/lib/i18n';
import type { Creator, CreatorOutreachLock } from '@/api/types';
import { useUiStore } from '@/stores/uiStore';

type TabKey = 'overview' | 'shop' | 'evidence' | 'risk' | 'history';
type Tone = 'good' | 'warn' | 'muted';

const TABS: Array<{ key: TabKey; zh: string; en: string }> = [
  { key: 'overview', zh: '推荐判断', en: 'Recommendation' },
  { key: 'shop', zh: 'Shop 数据', en: 'Shop Data' },
  { key: 'evidence', zh: '证据来源', en: 'Evidence' },
  { key: 'risk', zh: '风险复核', en: 'Risk Review' },
  { key: 'history', zh: '外联历史', en: 'Outreach History' },
];

const copy = {
  zh: {
    title: '达人详情',
    back: '返回新达人推荐库',
    updated: '最近更新',
    score: '推荐分',
    outreach: '邮件建联',
    profile: '主页',
    shopDetails: 'Shop 详情',
    contactable: '可联系',
    missingContact: '待补联系方式',
    uncategorized: '未分类',
    followers: '粉丝数',
    productFit: '商品匹配',
    priority: '优先级',
    email: '邮箱',
    noEmail: '暂无邮箱',
    owner: '负责人',
    unclaimed: '未认领',
    collabType: '合作类型',
    notSet: '未设定',
    recommendedProduct: '推荐商品',
    status: '状态',
    pending: '待处理',
    source: '采集来源',
    leadStatus: '线索状态',
    unmarked: '未标记',
    captured: '已采集',
    none: '暂无',
    collectedAt: '入库时间',
    lastSeen: '最后发现',
    evidence: '证据',
    emailAvailable: '邮箱可用',
    defaultAction: '建议先用样品包 + 联盟佣金发起低成本合作测试。',
    noReason: '暂无推荐理由。可以在这里展示 AI 生成的合作判断、适配商品、外联策略和人工复核结论。',
    commercialValue: '商业价值',
    contactability: '可联系性',
    dataQuality: '数据完整度',
    reason: '推荐理由',
    nextAction: '下一步动作',
    nextActionDefault: '发送首封合作邮件；72 小时未回复时，切换其他联系方式补触达。',
    positiveTags: '正向标签',
    noTags: '暂无标签',
    basics: '基础资料',
    platform: '平台',
    regionLanguage: '地区/语言',
    rawFollowers: '原始粉丝',
    externalLinks: '外部链接',
    updatedAt: '更新时间',
    keywords: '命中关键词',
    noKeywords: '暂无关键词',
    evidenceSources: '证据来源',
    noEvidence: '暂无证据来源',
    riskSummary: '风险摘要',
    riskDefault: '暂无明显风险。建议首轮仍控制预算，以样品测试和联盟合作验证内容效果。',
    riskTags: '风险标签',
    noRiskTags: '暂无风险标签',
    outreachRecord: '外联记录',
    sentCount: '已发送',
    emailsUnit: '封邮件',
    recentSent: '最近发送',
    emailHistory: '邮件历史',
    historyTip: '详细邮件历史会在点击“邮件建联”后从外联抽屉中查看。',
    outreachActions: '外联动作',
    outreachTip: '邮件入口固定保留，外联抽屉会带入达人、邮箱、模板和历史记录。',
    tkScript: '生成 TK 邀约话术',
    followupInfo: '跟进信息',
    storeOwner: '店铺归属',
    unassigned: '未分配',
    noSent: '暂无发送',
    recommendationStatus: '推荐状态',
    evidenceStrength: '证据强度',
    actions: '操作',
    claim: '认领',
    release: '释放',
    emailPreview: '邮件预览',
    refresh: '刷新',
    notFound: '没有找到该达人',
    lockBusy: '达人已被其他用户占用，请刷新后再试',
    noData: '暂无数据',
    shopData: 'TikTok Shop 数据',
    shopEmpty: '暂无 TikTok Shop 明细。列表数据可能来自普通达人采集或表格导入，后续采集详情后会在这里显示 GMV、GPM、佣金、商品、品牌合作和画像字段。',
    shopProfile: 'Shop 档案',
    detailCaptured: '详情采集',
    links: '链接',
    openShop: '打开 Shop 详情',
    noCoreMetrics: '暂无核心指标。',
    signalLines: '详情信号',
    detailExcerpt: '详情摘录',
    allFields: '全部可用字段',
    avgCommission: '平均佣金',
    shopFollowers: 'Shop 粉丝',
    itemsSold: '销售件数',
    productCount: '商品数',
    brandCollabs: '合作品牌',
    category: '品类',
    avgViews: '平均播放',
    engagement: '互动率',
    pps: 'PPS 分',
    sampleScore: '样品分',
    strong: '强推荐',
    testable: '可测试',
    watch: '观察',
    justNow: '刚刚',
    minutesAgo: '分钟前',
    hoursAgo: '小时前',
    daysAgo: '天前',
  },
  en: {
    title: 'Creator Detail',
    back: 'Back to Recommendations',
    updated: 'Updated',
    score: 'Score',
    outreach: 'Email Outreach',
    profile: 'Profile',
    shopDetails: 'Shop Details',
    contactable: 'Contactable',
    missingContact: 'Needs Contact Info',
    uncategorized: 'Uncategorized',
    followers: 'Followers',
    productFit: 'Product Fit',
    priority: 'Priority',
    email: 'Email',
    noEmail: 'No email',
    owner: 'Owner',
    unclaimed: 'Unclaimed',
    collabType: 'Collab Type',
    notSet: 'Not set',
    recommendedProduct: 'Recommended Product',
    status: 'Status',
    pending: 'Pending',
    source: 'Source',
    leadStatus: 'Lead Status',
    unmarked: 'Unmarked',
    captured: 'Captured',
    none: 'None',
    collectedAt: 'Added',
    lastSeen: 'Last Seen',
    evidence: 'Evidence',
    emailAvailable: 'Email Available',
    defaultAction: 'Start with a sample package plus affiliate commission to test fit at low cost.',
    noReason: 'No recommendation reason yet. AI fit, product match, outreach strategy, and review notes can appear here.',
    commercialValue: 'Commercial Value',
    contactability: 'Contactability',
    dataQuality: 'Data Quality',
    reason: 'Recommendation Reason',
    nextAction: 'Next Action',
    nextActionDefault: 'Send the first collaboration email. If there is no reply after 72 hours, try another contact channel.',
    positiveTags: 'Positive Tags',
    noTags: 'No tags',
    basics: 'Basic Info',
    platform: 'Platform',
    regionLanguage: 'Region / Language',
    rawFollowers: 'Raw Followers',
    externalLinks: 'External Links',
    updatedAt: 'Updated At',
    keywords: 'Matched Keywords',
    noKeywords: 'No keywords',
    evidenceSources: 'Evidence Sources',
    noEvidence: 'No evidence sources',
    riskSummary: 'Risk Summary',
    riskDefault: 'No obvious risk. Keep the first round budget controlled and validate with samples and affiliate collaboration.',
    riskTags: 'Risk Tags',
    noRiskTags: 'No risk tags',
    outreachRecord: 'Outreach Record',
    sentCount: 'Sent',
    emailsUnit: 'emails',
    recentSent: 'recent',
    emailHistory: 'Email History',
    historyTip: 'Detailed email history is available in the outreach drawer after clicking Email Outreach.',
    outreachActions: 'Outreach Actions',
    outreachTip: 'The email entry stays available and carries creator info, mailbox, templates, and history into the drawer.',
    tkScript: 'Generate TK Invite Script',
    followupInfo: 'Follow-up Info',
    storeOwner: 'Store Owner',
    unassigned: 'Unassigned',
    noSent: 'No sends',
    recommendationStatus: 'Recommendation Status',
    evidenceStrength: 'Evidence Strength',
    actions: 'Actions',
    claim: 'Claim',
    release: 'Release',
    emailPreview: 'Email Preview',
    refresh: 'Refresh',
    notFound: 'Creator not found',
    lockBusy: 'This creator is currently locked by another user. Refresh and try again.',
    noData: 'No data',
    shopData: 'TikTok Shop Data',
    shopEmpty: 'No TikTok Shop details yet. This lead may come from general creator collection or table import. GMV, GPM, commission, products, brand collaboration, and profile fields will appear after detail collection.',
    shopProfile: 'Shop Profile',
    detailCaptured: 'Details Captured',
    links: 'Links',
    openShop: 'Open Shop Details',
    noCoreMetrics: 'No core metrics.',
    signalLines: 'Detail Signals',
    detailExcerpt: 'Detail Excerpt',
    allFields: 'All Available Fields',
    avgCommission: 'Avg Commission',
    shopFollowers: 'Shop Followers',
    itemsSold: 'Items Sold',
    productCount: 'Products',
    brandCollabs: 'Brand Collabs',
    category: 'Category',
    avgViews: 'Avg Views',
    engagement: 'Engagement',
    pps: 'PPS Score',
    sampleScore: 'Sample Score',
    strong: 'Strong Fit',
    testable: 'Testable',
    watch: 'Watch',
    justNow: 'Just now',
    minutesAgo: 'min ago',
    hoursAgo: 'h ago',
    daysAgo: 'd ago',
  },
} satisfies Record<Language, Record<string, any>>;

function listify(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return [];
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
    } catch {
      // Plain comma-separated text is handled below.
    }
    return trimmed.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function compactText(value: unknown) {
  const text = String(value ?? '').trim();
  return text && text !== 'null' && text !== 'undefined' ? text : '';
}

function hasValue(value: unknown) {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return compactText(value).length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function displayValue(value: unknown): string {
  if (!hasValue(value)) return '—';
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).filter((item) => item !== '—').join(' / ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function shopValue(creator: Creator, ...keys: string[]) {
  const shop = asRecord(creator.tiktok_shop) || {};
  for (const key of keys) {
    const value = shop[key] ?? creator[key];
    if (hasValue(value)) return value;
  }
  return null;
}

function scalarEntries(value: unknown, limit = 24): Array<[string, unknown]> {
  const record = asRecord(value);
  if (!record) return [];
  return Object.entries(record)
    .filter(([, item]) => hasValue(item) && (typeof item !== 'object' || Array.isArray(item)))
    .slice(0, limit);
}

function nestedEntries(value: unknown, limit = 8): Array<[string, Record<string, unknown>]> {
  const record = asRecord(value);
  if (!record) return [];
  return Object.entries(record)
    .filter(([, item]) => asRecord(item))
    .map(([key, item]) => [key, asRecord(item)!] as [string, Record<string, unknown>])
    .slice(0, limit);
}

function metricValue(creator: Creator, ...keys: string[]) {
  const value = shopValue(creator, ...keys);
  return hasValue(value) ? displayValue(value) : null;
}

function creatorName(c: Creator | null | undefined, language: Language) {
  return c?.display_name || c?.handle || (c?.id ? `${language === 'zh' ? '达人' : 'Creator'} ${c.id}` : copy[language].title);
}

function initial(c?: Creator | null) {
  return (c?.handle || c?.display_name || '?').slice(0, 1).toUpperCase();
}

function followers(c?: Creator | null) {
  return c?.followers_count ?? c?.followers ?? null;
}

function scoreTone(score: number | null | undefined, language: Language): { label: string; tone: Tone } {
  if ((score ?? 0) >= 85) return { label: copy[language].strong, tone: 'good' };
  if ((score ?? 0) >= 70) return { label: copy[language].testable, tone: 'warn' };
  return { label: copy[language].watch, tone: 'muted' };
}

function compactByLanguage(value: number | null | undefined, language: Language) {
  if (language === 'zh') return formatCompact(value);
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

function relativeByLanguage(value: string | null | undefined, language: Language) {
  if (language === 'zh') return shortRelative(value);
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value || '—';
  const diff = Date.now() - dt.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return copy.en.justNow;
  if (mins < 60) return `${mins} ${copy.en.minutesAgo}`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ${copy.en.hoursAgo}`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ${copy.en.daysAgo}`;
  return dt.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
}

function Pill({ tone = 'muted', children }: { tone?: Tone | 'info' | 'bad'; children: ReactNode }) {
  const className = tone === 'good'
    ? 'pill-good'
    : tone === 'warn'
      ? 'pill-warn'
      : tone === 'bad'
        ? 'pill-bad'
        : tone === 'info'
          ? 'pill-info'
          : 'pill-muted';
  return <span className={`pill ${className}`}>{children}</span>;
}

function Metric({ label, value, accent }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="text-xxs text-muted">{label}</div>
      <div className="num mt-1 text-lg font-semibold leading-tight" style={{ color: accent ? 'rgb(var(--accent))' : 'rgb(var(--text))' }}>
        {value}
      </div>
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {action}
      </div>
      <div className="p-4 text-sm leading-relaxed text-text">{children}</div>
    </section>
  );
}

function InfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
      <div className="mb-2 text-xs font-semibold text-text">{title}</div>
      <div className="text-xs leading-relaxed text-muted">{children}</div>
    </div>
  );
}

function ScoreBar({ label, value, tone = 'info' }: { label: string; value?: number | null; tone?: 'info' | 'good' | 'warn' }) {
  const pct = Math.max(0, Math.min(100, Number(value ?? 0)));
  const fill = tone === 'good'
    ? 'rgb(var(--good))'
    : tone === 'warn'
      ? 'rgb(var(--warn))'
      : 'rgb(var(--accent))';

  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
      <div className="flex items-center justify-between gap-2 text-xxs text-muted">
        <span>{label}</span>
        <strong className="num text-text">{pct}</strong>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-pill" style={{ background: 'rgb(var(--bg-elev-1))' }}>
        <div className="h-full rounded-pill" style={{ width: `${pct}%`, background: fill }} />
      </div>
    </div>
  );
}

function KeyValueList({ rows, emptyText = copy.zh.noData }: { rows: Array<[string, unknown]>; emptyText?: string }) {
  if (rows.length === 0) return <span>{emptyText}</span>;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-md border border-border p-2.5" style={{ background: 'rgb(var(--bg-elev-1))' }}>
          <div className="text-xxs text-muted">{label}</div>
          <div className="mt-1 break-words text-xs font-medium text-text">{displayValue(value)}</div>
        </div>
      ))}
    </div>
  );
}

function ShopDataPanel({ creator, language }: { creator: Creator; language: Language }) {
  const t = copy[language];
  const shop = asRecord(creator.tiktok_shop);
  const hasShopData = Boolean(shop && Object.keys(shop).length > 0) || Boolean(creator.shop_profile_url);
  const metricRows = [
    ['GMV', metricValue(creator, 'gmv_raw', 'gmv'), true],
    ['GPM', metricValue(creator, 'gpm_raw', 'gpm'), true],
    [t.avgCommission, metricValue(creator, 'avg_commission_rate_raw', 'commission_rate_raw', 'commission_rate'), false],
    [t.shopFollowers, metricValue(creator, 'followers_raw', 'shop_followers_raw'), false],
    [t.itemsSold, metricValue(creator, 'items_sold_raw', 'items_sold'), false],
    [t.productCount, metricValue(creator, 'products_raw', 'product_count'), false],
    [t.brandCollabs, metricValue(creator, 'brand_collaborations_raw', 'brand_collaborations'), false],
    [t.category, metricValue(creator, 'category_text', 'category', 'primary_category'), false],
    [t.avgViews, metricValue(creator, 'avg_video_views_raw', 'avg_video_views'), false],
    [t.engagement, metricValue(creator, 'avg_video_engagement_rate_raw', 'avg_video_engagement_rate'), false],
    [t.pps, metricValue(creator, 'pps_score_raw', 'pps_score'), false],
    [t.sampleScore, metricValue(creator, 'sample_score_raw', 'sample_score'), false],
  ].filter(([, value]) => Boolean(value)) as Array<[string, string, boolean]>;
  const signalLines = listify(shop?.detail_signal_lines);
  const detailSections = asRecord(shop?.detail_sections) || asRecord(shop?.sections);
  const nestedSections = nestedEntries(detailSections);
  const detailExcerpt = compactText(shop?.detail_text_excerpt || shop?.detail_text || shop?.description);
  const scalarRows = scalarEntries(shop).filter(([key]) => !key.includes('raw_html') && !key.includes('json'));

  if (!hasShopData) {
    return (
      <InfoBlock title={t.shopData}>
        {t.shopEmpty}
      </InfoBlock>
    );
  }

  return (
    <div className="grid gap-3">
      <InfoBlock title={t.shopProfile}>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone="info">{creator.source_label || creator.source || 'TikTok Shop'}</Pill>
          {creator.lead_status && <Pill tone="warn">{creator.lead_status}</Pill>}
          {hasValue(shop?.detail_captured_at) && <Pill tone="good">{t.detailCaptured} {displayValue(shop?.detail_captured_at)}</Pill>}
          {hasValue(shop?.detail_links_count) && <Pill>{t.links} {displayValue(shop?.detail_links_count)}</Pill>}
          {creator.shop_profile_url && (
            <a href={creator.shop_profile_url} target="_blank" rel="noreferrer" className="btn btn-ghost !h-7 !px-2 text-xs">
              <ExternalLink size={13} /> {t.openShop}
            </a>
          )}
        </div>
      </InfoBlock>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {metricRows.length > 0 ? metricRows.map(([label, value, accent]) => (
          <Metric key={label} label={label} value={value} accent={accent} />
        )) : (
          <div className="col-span-full text-xs text-muted">{t.noCoreMetrics}</div>
        )}
      </div>

      {signalLines.length > 0 && (
        <InfoBlock title={t.signalLines}>
          <div className="flex flex-wrap gap-1.5">
            {signalLines.map((line) => <Pill key={line} tone="info">{line}</Pill>)}
          </div>
        </InfoBlock>
      )}

      {detailExcerpt && (
        <InfoBlock title={t.detailExcerpt}>
          <div className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md border border-border p-3 text-xs text-text" style={{ background: 'rgb(var(--bg-elev-1))' }}>
            {detailExcerpt}
          </div>
        </InfoBlock>
      )}

      {nestedSections.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          {nestedSections.map(([title, value]) => (
            <InfoBlock key={title} title={title}>
              <KeyValueList rows={scalarEntries(value, 10)} emptyText={t.noData} />
            </InfoBlock>
          ))}
        </div>
      )}

      <InfoBlock title={t.allFields}>
        <KeyValueList rows={scalarRows} emptyText={t.noData} />
      </InfoBlock>
    </div>
  );
}

export default function RecommendationDetail() {
  const { creatorId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { language } = useUiStore();
  const t = copy[language];
  const [tab, setTab] = useState<TabKey>('overview');
  const [mailOpen, setMailOpen] = useState(false);
  const [mailLock, setMailLock] = useState<CreatorOutreachLock | null>(null);
  const [mailOpening, setMailOpening] = useState(false);
  const [scriptOpen, setScriptOpen] = useState(false);

  const creatorQ = useCreator(creatorId);
  const claim = useClaimCreator();
  const release = useReleaseCreator();
  const acquireOutreachLock = useAcquireOutreachLock();
  const creator = creatorQ.data;

  const positiveTags = useMemo(() => listify(creator?.positive_tags), [creator]);
  const riskTags = useMemo(() => listify(creator?.risk_tags), [creator]);
  const keywords = useMemo(() => listify(creator?.matched_keywords), [creator]);
  const evidenceSources = useMemo(() => listify(creator?.fit_evidence_sources), [creator]);
  const score = creator?.recommendation_score ?? 0;
  const tone = scoreTone(score, language);
  const priority = creator?.outreach_priority || creator?.priority_level || 'P?';
  const owner = creator?.owner_bd || creator?.bd_owner || t.unclaimed;

  const refreshCreator = () => {
    qc.invalidateQueries({ queryKey: ['creator', creatorId] });
    qc.invalidateQueries({ queryKey: ['creators'] });
  };

  const onClaim = () => {
    if (!creator) return;
    claim.mutate({ id: creator.id, body: {} }, { onSuccess: refreshCreator });
  };

  const onRelease = () => {
    if (!creator) return;
    release.mutate({ id: creator.id }, { onSuccess: refreshCreator });
  };

  const openMail = async () => {
    if (!creator) return;
    setMailOpening(true);
    try {
      const result = await acquireOutreachLock.mutateAsync({ creator_id: creator.id });
      setMailLock(result.lock);
      setMailOpen(true);
    } catch (error: any) {
      alert(String(error?.body?.detail || error?.message || t.lockBusy));
    } finally {
      setMailOpening(false);
    }
  };

  return (
    <AsyncState
      loading={creatorQ.isLoading}
      error={creatorQ.error}
      isEmpty={!creatorQ.isLoading && !creator}
      loadingMessage={language === 'zh' ? '加载中...' : 'Loading...'}
      errorTitle={language === 'zh' ? '加载失败' : 'Failed to load'}
      emptyMessage={t.notFound}
      height={420}
    >
      {creator && (
        <div className="space-y-4">
          <div className="card card-body">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => navigate('/recommendations')}
                  className="btn btn-ghost !h-9 !w-9 !justify-center !px-0"
                  aria-label={t.back}
                  title={t.back}
                >
                  <ArrowLeft size={16} />
                </button>
                <div
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-md text-base font-semibold"
                  style={{ background: 'rgb(var(--accent) / 0.16)', color: 'rgb(var(--accent))' }}
                >
                  {initial(creator)}
                </div>
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <h2 className="truncate text-base font-semibold text-text">@{creator.handle || 'unknown'}</h2>
                    <Pill tone="info">{priority}</Pill>
                    <Pill tone={tone.tone}>{tone.label}</Pill>
                  </div>
                  <div className="mt-1 truncate text-xs text-muted">
                    {creatorName(creator, language)} · {creator.platform || 'tiktok'} · {t.updated} {relativeByLanguage(creator.updated_at || creator.collected_at || creator.created_at, language)}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="rounded-md border border-border px-3 py-1.5 text-xs text-muted" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
                  {t.score} <strong className="num ml-1 text-base text-text">{Math.round(score)}</strong>
                </div>
                <button type="button" onClick={openMail} disabled={mailOpening} className="btn btn-primary">
                  {mailOpening ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />} {t.outreach}
                </button>
                {creator.profile_url && (
                  <a href={creator.profile_url} target="_blank" rel="noreferrer" className="btn">
                    <ExternalLink size={14} /> {t.profile}
                  </a>
                )}
                {creator.shop_profile_url && (
                  <a href={creator.shop_profile_url} target="_blank" rel="noreferrer" className="btn">
                    <ExternalLink size={14} /> {t.shopDetails}
                  </a>
                )}
              </div>
            </div>
          </div>

          <main className="grid gap-3 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
            <aside className="card">
              <div className="border-b border-border p-4">
                <div className="flex items-center gap-3">
                  <div
                    className="grid h-14 w-14 shrink-0 place-items-center rounded-md text-xl font-semibold"
                    style={{ background: 'rgb(var(--accent) / 0.16)', color: 'rgb(var(--accent))' }}
                  >
                    {initial(creator)}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-text">{creatorName(creator, language)}</div>
                    <div className="mt-1 font-mono text-xs text-muted">@{creator.handle || 'unknown'}</div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Pill tone={creator.email || creator.has_contact ? 'good' : 'muted'}>
                        {creator.email || creator.has_contact ? t.contactable : t.missingContact}
                      </Pill>
                      <Pill tone="info">{creator.primary_product_category || creator.recommended_product_type || t.uncategorized}</Pill>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 p-4">
                <Metric label={t.followers} value={compactByLanguage(followers(creator), language)} />
                <Metric label={t.score} value={Math.round(score)} accent />
                <Metric label={t.productFit} value={creator.primary_product_fit_score ?? '—'} />
                <Metric label={t.priority} value={priority} />
                <Metric label="Shop GMV" value={metricValue(creator, 'gmv_raw', 'gmv') ?? '—'} accent />
                <Metric label="Shop GPM" value={metricValue(creator, 'gpm_raw', 'gpm') ?? '—'} />
              </div>

              <dl className="border-t border-border px-4 py-2">
                {[
                  [t.email, creator.email ? maskEmail(creator.email) : t.noEmail],
                  [t.owner, owner],
                  [t.collabType, creator.recommended_collab_type || t.notSet],
                  [t.recommendedProduct, creator.recommended_product_type || creator.primary_product_category || t.notSet],
                  [t.status, creator.recommendation_status || creator.current_status || t.pending],
                  [t.source, creator.source_label || creator.source || '—'],
                  [t.leadStatus, creator.lead_status || t.unmarked],
                  [t.shopDetails, creator.shop_profile_url ? t.captured : t.none],
                  [t.collectedAt, creator.collected_at ? relativeByLanguage(creator.collected_at, language) : '—'],
                  [t.lastSeen, creator.last_seen_at ? relativeByLanguage(creator.last_seen_at, language) : '—'],
                ].map(([label, value]) => (
                  <div key={label} className="grid grid-cols-[72px_minmax(0,1fr)] gap-2 border-b border-border/60 py-2.5 text-xs last:border-b-0">
                    <dt className="text-muted">{label}</dt>
                    <dd className="m-0 min-w-0 break-words text-text">{value}</dd>
                  </div>
                ))}
              </dl>
            </aside>

            <section className="card overflow-hidden">
              <div className="border-b border-border p-4">
                <div className="grid gap-4 lg:grid-cols-[132px_minmax(0,1fr)]">
                  <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
                    <div className="text-xxs uppercase tracking-wide text-muted">Score</div>
                    <div className="num mt-2 text-4xl font-semibold leading-none text-text">{Math.round(score)}</div>
                    <div className="mt-3"><Pill tone={tone.tone}>{tone.label} · {priority}</Pill></div>
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-1.5">
                      <Pill tone={tone.tone}>{tone.label}</Pill>
                      <Pill tone="info">{t.evidence} {creator.evidence_strength || '—'}</Pill>
                      {creator.email && <Pill tone="good">{t.emailAvailable}</Pill>}
                    </div>
                    <h2 className="mt-3 text-lg font-semibold leading-snug text-text">
                      {creator.next_action || t.defaultAction}
                    </h2>
                    <p className="mt-2 text-sm leading-relaxed text-muted">
                      {creator.recommendation_reason || t.noReason}
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
                  <ScoreBar label={t.productFit} value={creator.primary_product_fit_score} />
                  <ScoreBar label={t.commercialValue} value={creator.commercial_value_score} tone="good" />
                  <ScoreBar label={t.contactability} value={creator.contactability_score} />
                  <ScoreBar label={t.dataQuality} value={creator.data_quality_score} tone="warn" />
                </div>
              </div>

              <div className="flex overflow-x-auto border-b border-border" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
                {TABS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setTab(item.key)}
                    className="h-10 min-w-[104px] border-r border-border px-3 text-xs font-medium transition-colors"
                    style={tab === item.key
                      ? { color: 'rgb(var(--text))', background: 'rgb(var(--bg-elev-1))', boxShadow: 'inset 0 -2px 0 rgb(var(--accent))' }
                      : { color: 'rgb(var(--muted))' }}
                  >
                    {item[language]}
                  </button>
                ))}
              </div>

              <div className="p-4">
                {tab === 'overview' && (
                  <div className="grid gap-3">
                    <div className="grid gap-3 lg:grid-cols-2">
                      <InfoBlock title={t.reason}>
                        {creator.recommendation_reason || t.noReason}
                      </InfoBlock>
                      <InfoBlock title={t.nextAction}>
                        {creator.next_action || t.nextActionDefault}
                      </InfoBlock>
                    </div>
                    <InfoBlock title={t.positiveTags}>
                      <div className="flex flex-wrap gap-1.5">
                        {(positiveTags.length > 0 ? positiveTags : [creator.primary_product_category, creator.recommended_product_type, creator.recommended_collab_type].filter(Boolean)).map((tag) => (
                          <Pill key={tag} tone="good">{tag}</Pill>
                        ))}
                        {positiveTags.length === 0 && !creator.primary_product_category && <span>{t.noTags}</span>}
                      </div>
                    </InfoBlock>
                    <InfoBlock title={t.basics}>
                      <KeyValueList rows={([
                        [t.platform, creator.platform || 'tiktok'],
                        [t.source, creator.source_label || creator.source],
                        [t.leadStatus, creator.lead_status],
                        [t.regionLanguage, [creator.country, creator.language].filter(Boolean).join(' / ')],
                        [t.rawFollowers, creator.followers_raw],
                        [t.email, creator.email],
                        [t.externalLinks, listify(creator.external_links).join(' / ')],
                        [t.profile, creator.profile_url],
                        [t.shopDetails, creator.shop_profile_url],
                        [t.collectedAt, creator.collected_at],
                        [t.lastSeen, creator.last_seen_at],
                        [t.updatedAt, creator.updated_at],
                      ] as Array<[string, unknown]>).filter(([, value]) => hasValue(value))} emptyText={t.noData} />
                    </InfoBlock>
                  </div>
                )}

                {tab === 'shop' && (
                  <ShopDataPanel creator={creator} language={language} />
                )}

                {tab === 'evidence' && (
                  <div className="grid gap-3">
                    <div className="grid gap-3 lg:grid-cols-2">
                      <InfoBlock title={t.keywords}>
                        <div className="flex flex-wrap gap-1.5">
                          {keywords.length > 0 ? keywords.map((tag) => (
                            <Pill key={tag} tone="info">{tag}</Pill>
                          )) : <span>{t.noKeywords}</span>}
                        </div>
                      </InfoBlock>
                      <InfoBlock title={t.evidenceSources}>
                        <div className="flex flex-wrap gap-1.5">
                          {evidenceSources.length > 0 ? evidenceSources.map((source) => (
                            <Pill key={source}>{source}</Pill>
                          )) : <span>{t.noEvidence}</span>}
                        </div>
                      </InfoBlock>
                    </div>
                    <InfoBlock title="Profile Snapshot">
                      <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded border border-border p-3 text-xs text-text" style={{ background: 'rgb(var(--bg-elev-1))' }}>
                        {JSON.stringify(creator.profile_snapshot || {}, null, 2)}
                      </pre>
                    </InfoBlock>
                  </div>
                )}

                {tab === 'risk' && (
                  <div className="grid gap-3 lg:grid-cols-2">
                    <InfoBlock title={t.riskSummary}>
                      <div className="flex gap-2">
                        <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warn" />
                        <span>{creator.risk_summary || t.riskDefault}</span>
                      </div>
                    </InfoBlock>
                    <InfoBlock title={t.riskTags}>
                      <div className="flex flex-wrap gap-1.5">
                        {riskTags.length > 0 ? riskTags.map((tag) => (
                          <Pill key={tag} tone="warn">{tag}</Pill>
                        )) : <span>{t.noRiskTags}</span>}
                      </div>
                    </InfoBlock>
                  </div>
                )}

                {tab === 'history' && (
                  <div className="grid gap-3">
                    <InfoBlock title={t.outreachRecord}>
                      <div className="flex items-center gap-2">
                        <Send size={15} />
                        <span>
                          {t.sentCount} {creator.outreach_count ?? 0} {t.emailsUnit}; {t.recentSent}: {creator.last_outreach_at ? relativeByLanguage(creator.last_outreach_at, language) : t.none}
                        </span>
                      </div>
                    </InfoBlock>
                    <InfoBlock title={t.emailHistory}>
                      {t.historyTip}
                    </InfoBlock>
                  </div>
                )}
              </div>
            </section>

            <aside className="space-y-3">
              <Section title={t.outreachActions}>
                <div className="flex flex-wrap gap-1.5">
                  <Pill tone="info">ACTION</Pill>
                  <Pill>{creator.current_status || (language === 'zh' ? '待建联' : 'To Contact')}</Pill>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-muted">
                  {t.outreachTip}
                </p>
                <button type="button" onClick={openMail} disabled={mailOpening} className="btn btn-primary mt-4 w-full justify-center">
                  {mailOpening ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />} {t.outreach}
                </button>
                <button
                  type="button"
                  onClick={() => setScriptOpen(true)}
                  className="btn mt-2 w-full justify-center text-xs"
                >
                  <MessageSquare size={14} /> {t.tkScript}
                </button>
              </Section>

              <Section title={t.followupInfo}>
                <div className="space-y-2">
                  {[
                    [t.owner, owner],
                    [t.storeOwner, creator.store_assigned || t.unassigned],
                    [t.recentSent, creator.last_outreach_at ? relativeByLanguage(creator.last_outreach_at, language) : t.noSent],
                    [t.recommendationStatus, creator.recommendation_status || '—'],
                    [t.evidenceStrength, creator.evidence_strength || '—'],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-start justify-between gap-3 border-b border-border/60 pb-2 text-xs last:border-b-0">
                      <span className="text-muted">{label}</span>
                      <strong className="break-words text-right font-medium text-text">{value}</strong>
                    </div>
                  ))}
                </div>
              </Section>

              <Section title={t.actions}>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={onClaim} disabled={claim.isPending} className="btn justify-center">
                    {claim.isPending ? <RefreshCw size={13} className="animate-spin" /> : <UserCheck size={13} />} {t.claim}
                  </button>
                  <button type="button" onClick={onRelease} disabled={release.isPending} className="btn justify-center">
                    {release.isPending ? <RefreshCw size={13} className="animate-spin" /> : <UserMinus size={13} />} {t.release}
                  </button>
                </div>
                <div className="mt-3 rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
                  <div className="flex items-center gap-2 text-xs font-semibold text-text"><Mail size={14} /> {t.emailPreview}</div>
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    Hi {creator.display_name || creator.handle}, I came across your content and think our product line may fit your audience...
                  </p>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {creator.profile_url && (
                    <a href={creator.profile_url} target="_blank" rel="noreferrer" className="btn justify-center">
                      <Link2 size={13} /> {t.profile}
                    </a>
                  )}
                  <button type="button" onClick={refreshCreator} className="btn justify-center">
                    <ShieldCheck size={13} /> {t.refresh}
                  </button>
                </div>
              </Section>
            </aside>
          </main>

          <OutreachDrawer
            creator={creator}
            open={mailOpen}
            initialLock={mailLock}
            onClose={() => {
              setMailOpen(false);
              setMailLock(null);
              refreshCreator();
            }}
          />
          {scriptOpen && <TkScriptModal creator={creator} onClose={() => setScriptOpen(false)} />}
        </div>
      )}
    </AsyncState>
  );
}
