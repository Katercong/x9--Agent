import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  Building2,
  ClipboardCopy,
  ExternalLink,
  Filter,
  Globe2,
  Handshake,
  Link2,
  Loader2,
  MessageSquareText,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react';
import { SideDrawer } from '@/components/drawer/SideDrawer';
import {
  useForeignTradeCollection,
  useForeignTradeFollowups,
  useStartForeignTradeContact,
  type ForeignTradeContactStatus,
  type ForeignTradeLeadType,
  type LeadItem,
} from '@/api/foreignTrade';

type Board = 'customers' | 'companies';
type ContactStatus = ForeignTradeContactStatus;

type RecommendationCard = {
  id: string;
  board: Board;
  name: string;
  subtitle: string;
  platform: string;
  score: number;
  priority: string;
  status: ContactStatus;
  account?: string | null;
  profileUrl?: string | null;
  commentUrl?: string | null;
  sourceUrl?: string | null;
  contactLabel: string;
  evidence: string;
  reason: string;
  suggestion: string;
  tags: string[];
};

const STATUS_META: Record<ContactStatus, { label: string; tone: string }> = {
  pending_contact: { label: '待建联', tone: 'bg-slate-500/10 text-slate-300 border-slate-500/25' },
  contact_started: { label: '已打开主页', tone: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/25' },
  follow_up: { label: '待跟进', tone: 'bg-amber-500/10 text-amber-300 border-amber-500/25' },
  replied: { label: '已回复', tone: 'bg-sky-500/10 text-sky-300 border-sky-500/25' },
  interested: { label: '有意向', tone: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/25' },
  invalid: { label: '无效', tone: 'bg-rose-500/10 text-rose-300 border-rose-500/25' },
  converted: { label: '已转化', tone: 'bg-lime-500/10 text-lime-300 border-lime-500/25' },
};

function clampScore(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function firstText(...values: Array<unknown>) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

function firstUrl(item: LeadItem) {
  return firstText(
    item.profile_url,
    item.source_url,
    item.recent_comments?.[0]?.note_url,
    item.source_samples?.[0]?.evidence_url,
  );
}

function commentUrl(item: LeadItem) {
  return firstText(item.recent_comments?.[0]?.note_url, item.source_samples?.[0]?.evidence_url, item.source_url);
}

function normalizeStatus(value?: string | null): ContactStatus {
  if (value === 'contacted' || value === '已建联') return 'contact_started';
  if (value && value in STATUS_META) return value as ContactStatus;
  return 'pending_contact';
}

function platformName(value?: string | null) {
  if (value === 'douyin') return '抖音';
  if (value === 'xhs') return '小红书';
  if (value === '51job') return '51job';
  if (value === 'zhaopin') return '智联招聘';
  if (value === 'qzrc') return '大泉州人才网';
  return value || '来源';
}

function mapCustomer(item: LeadItem): RecommendationCard {
  const account = firstText(item.account, item.xhs_user_id, item.external_user_id, item.id);
  const evidence = firstText(
    item.judgment_data?.target_user_utterance,
    item.judgment_evidence,
    item.recent_comments?.[0]?.content,
    item.bio,
    item.summary,
  );
  const score = clampScore(item.fit_score ?? item.score);
  const platform = platformName(item.platform);
  return {
    id: item.id,
    board: 'customers',
    name: item.name || account || '未命名客户',
    subtitle: firstText(item.subtitle, item.bio, item.location, '社媒客户线索'),
    platform,
    score,
    priority: score >= 90 ? '重点' : score >= 70 ? '优先' : '观察',
    status: normalizeStatus(item.status),
    account,
    profileUrl: firstUrl(item),
    commentUrl: commentUrl(item),
    contactLabel: `${item.platform === 'douyin' ? '抖音号' : '小红书号'}: ${account || '待补充'}`,
    evidence: evidence || '暂无评论证据',
    reason: firstText(item.judgment_data?.identity_reasoning, item.score_reason, item.judgment_evidence, '根据清洗后的评论链和账号资料推荐。'),
    suggestion: firstText(item.judgment_suggestion, item.score_suggestion, item.next_action, '打开主页后先确认品类、货源需求和当前发货方式。'),
    tags: [
      item.decision === 'high_priority' ? '高意向' : item.decision === 'nurture' ? '养线索' : '',
      item.intent_type || '',
      item.customer_priority ? `优先级 ${item.customer_priority}` : '',
    ].filter(Boolean),
  };
}

function mapCompany(item: LeadItem): RecommendationCard {
  const score = clampScore(item.score ?? item.fit_score);
  return {
    id: item.id,
    board: 'companies',
    name: item.name || '未命名公司',
    subtitle: firstText(item.subtitle, item.location, item.size_range, item.title, '公司客户线索'),
    platform: platformName(firstText(item.source_type, item.platform, '公司线索')),
    score,
    priority: item.tier || (score >= 80 ? 'A' : score >= 60 ? 'B' : 'C'),
    status: normalizeStatus(item.status),
    sourceUrl: item.source_url,
    contactLabel: firstText(item.contact, item.contact_name, item.contacts?.[0]?.value, '待补充联系方式'),
    evidence: firstText(item.summary, item.score_reason, item.raw_titles?.[0], '暂无公司需求证据'),
    reason: firstText(item.score_reason, item.summary, '根据公司岗位、官网或采集来源识别为潜在客户。'),
    suggestion: firstText(item.score_suggestion, item.next_action, '先确认主营品类、销售渠道和是否需要一件代发供应。'),
    tags: [item.tier ? `${item.tier} 级` : '', item.cooperation_type || '', item.us_market ? '美国市场' : ''].filter(Boolean),
  };
}

function statusClass(status: ContactStatus) {
  return `inline-flex items-center rounded-full border px-2 py-0.5 text-xxs ${STATUS_META[status].tone}`;
}

function scoreTone(score: number) {
  if (score >= 90) return 'text-emerald-300';
  if (score >= 70) return 'text-cyan-300';
  if (score >= 50) return 'text-amber-300';
  return 'text-muted';
}

function leadTypeFor(board: Board): ForeignTradeLeadType {
  return board === 'customers' ? 'customer' : 'company';
}

export default function ForeignTradeRecommendations() {
  const [board, setBoard] = useState<Board>('customers');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | ContactStatus>('all');
  const [selected, setSelected] = useState<RecommendationCard | null>(null);
  const [localStatus, setLocalStatus] = useState<Record<string, ContactStatus>>({});

  const socialQuery = useForeignTradeCollection({ channel: 'social', recommended: true, limit: 120, offset: 0 });
  const jobsQuery = useForeignTradeCollection({ channel: 'jobs', limit: 120, offset: 0 });
  const followupsQuery = useForeignTradeFollowups({ limit: 500, offset: 0 });
  const startContactMutation = useStartForeignTradeContact();

  const followupStatus = useMemo(() => {
    const map: Record<string, ContactStatus> = {};
    for (const item of followupsQuery.data?.items || []) {
      const key = `${item.lead_type === 'customer' ? 'customers' : 'companies'}:${item.lead_id}`;
      map[key] = item.status;
    }
    return map;
  }, [followupsQuery.data]);

  const customers = useMemo(() => {
    return (socialQuery.data?.items || [])
      .map(mapCustomer)
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score);
  }, [socialQuery.data]);

  const companies = useMemo(() => {
    return (jobsQuery.data?.items || [])
      .filter((item) => item.kind === 'company')
      .map(mapCompany)
      .sort((a, b) => b.score - a.score);
  }, [jobsQuery.data]);

  const allItems = board === 'customers' ? customers : companies;
  const decoratedItems = allItems.map((item) => {
    const key = `${item.board}:${item.id}`;
    return { ...item, status: localStatus[key] || followupStatus[key] || item.status };
  });
  const filtered = decoratedItems.filter((item) => {
    const q = query.trim().toLowerCase();
    const matchesQuery = !q || [item.name, item.subtitle, item.account, item.evidence, item.reason, item.contactLabel]
      .some((value) => String(value || '').toLowerCase().includes(q));
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesQuery && matchesStatus;
  });

  const active = selected
    ? { ...selected, status: localStatus[`${selected.board}:${selected.id}`] || followupStatus[`${selected.board}:${selected.id}`] || selected.status }
    : null;
  const pendingCount = decoratedItems.filter((item) => item.status === 'pending_contact').length;
  const highCount = decoratedItems.filter((item) => item.score >= 90).length;
  const loading = socialQuery.isLoading || jobsQuery.isLoading || followupsQuery.isLoading;
  const error = socialQuery.error || jobsQuery.error || followupsQuery.error;

  const startContact = async (item: RecommendationCard) => {
    const popup = window.open('', '_blank');
    if (popup) popup.opener = null;
    const key = `${item.board}:${item.id}`;
    try {
      const result = await startContactMutation.mutateAsync({
        leadType: leadTypeFor(item.board),
        leadId: item.id,
        contact_label: item.contactLabel,
        comment_url: item.commentUrl,
        source_url: item.sourceUrl,
      });
      setLocalStatus((prev) => ({ ...prev, [key]: result.item.status }));
      setSelected({ ...item, status: result.item.status });
      const url = result.open_url || item.profileUrl || item.sourceUrl || item.commentUrl;
      if (url && popup) popup.location.href = url;
      else if (url) window.open(url, '_blank', 'noopener,noreferrer');
      else popup?.close();
    } catch (err) {
      popup?.close();
      const message = err instanceof Error ? err.message : '建联状态写入失败';
      window.alert(message);
    }
  };

  const copyCard = async (item: RecommendationCard) => {
    const text = [
      `名称: ${item.name}`,
      `平台: ${item.platform}`,
      item.account ? `账号: ${item.account}` : '',
      item.profileUrl ? `主页: ${item.profileUrl}` : '',
      item.commentUrl ? `评论/来源: ${item.commentUrl}` : '',
      `联系方式: ${item.contactLabel}`,
      `证据: ${item.evidence}`,
    ].filter(Boolean).join('\n');
    await navigator.clipboard?.writeText(text);
  };

  return (
    <div className="space-y-4">
      <section className="relative overflow-hidden rounded-md border border-border bg-elev1">
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-400 via-emerald-300 to-amber-300" />
        <div className="flex flex-col gap-4 p-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xxs uppercase tracking-[0.18em] text-muted">
              <Sparkles size={14} className="text-accent" />
              Foreign Trade Recommendation Desk
            </div>
            <h1 className="mt-2 text-xl font-semibold text-text">外贸客户推荐</h1>
            <p className="mt-1 max-w-3xl text-xs text-muted">
              客户推荐池来自小红书/抖音采集清洗后的 GPT 评分结果；公司推荐池来自招聘网站和公司线索评分结果。
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-right">
            <Kpi label="推荐总数" value={decoratedItems.length} />
            <Kpi label="高意向" value={highCount} tone="text-emerald-300" />
            <Kpi label="待建联" value={pendingCount} tone="text-amber-300" />
          </div>
        </div>
      </section>

      <section className="grid gap-3 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-3">
          <div className="rounded-md border border-border bg-elev1 p-2">
            <BoardButton active={board === 'customers'} icon={<UserRound size={15} />} label="客户推荐" count={customers.length} onClick={() => setBoard('customers')} />
            <BoardButton active={board === 'companies'} icon={<Building2 size={15} />} label="公司推荐" count={companies.length} onClick={() => setBoard('companies')} />
          </div>

          <div className="rounded-md border border-border bg-elev1 p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold">
              <Filter size={14} className="text-accent" />筛选
            </div>
            <label className="flex h-9 items-center gap-2 rounded-md border border-border bg-bg px-3">
              <Search size={14} className="text-muted" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索名称 / 账号 / 证据"
                className="input-bare w-full"
              />
            </label>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {(['all', 'pending_contact', 'contact_started', 'follow_up'] as const).map((status) => (
                <button
                  key={status}
                  type="button"
                  onClick={() => setStatusFilter(status)}
                  className={`rounded border px-2 py-1.5 text-xxs transition ${statusFilter === status ? 'border-accent bg-accent/15 text-accent' : 'border-border hover:bg-elev2'}`}
                >
                  {status === 'all' ? '全部' : STATUS_META[status].label}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-border bg-elev1 p-3">
            <div className="mb-2 text-xs font-semibold">建联流程</div>
            <FlowRow index="1" title="查看评分结果" text="小红书/抖音清洗数据、证据链、GPT 推荐分" />
            <FlowRow index="2" title="点击建联" text="写入状态并打开客户主页或公司来源" />
            <FlowRow index="3" title="提交跟进" text="在邮件跟进系统记录结果" />
          </div>
        </aside>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">{board === 'customers' ? '小红书/抖音评分客户池' : '公司推荐池'}</div>
              <div className="text-xxs text-muted">
                {filtered.length} 条结果 · {board === 'customers' ? '只展示采集清洗后已评分的客户线索' : '按公司评分和待建联优先展示'}
              </div>
            </div>
            <button type="button" className="btn btn-ghost" onClick={() => { setQuery(''); setStatusFilter('all'); }}>
              重置筛选
            </button>
          </div>

          {loading && (
            <div className="flex h-48 items-center justify-center gap-2 rounded-md border border-border bg-elev1 text-xs text-muted">
              <Loader2 size={14} className="animate-spin" />正在加载推荐数据
            </div>
          )}
          {!loading && error && (
            <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-200">
              推荐数据加载失败：{error instanceof Error ? error.message : String(error)}
            </div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div className="rounded-md border border-dashed border-border bg-elev1 p-8 text-center text-xs text-muted">
              暂无符合条件的推荐线索
            </div>
          )}

          <div className="grid gap-3 2xl:grid-cols-2">
            {filtered.map((item) => (
            <RecommendationRow
                key={item.id}
                item={item}
                busy={startContactMutation.isPending}
                onOpen={() => setSelected(item)}
                onStart={() => startContact(item)}
              />
            ))}
          </div>
        </div>
      </section>

      <SideDrawer
        open={Boolean(active)}
        onClose={() => setSelected(null)}
        title={active?.board === 'companies' ? '公司名片' : '客户名片'}
        subtitle={active ? `${active.platform} · ${STATUS_META[active.status].label}` : undefined}
        width={620}
        footer={active && (
          <>
            <button type="button" className="btn btn-ghost" onClick={() => copyCard(active)}>
              <ClipboardCopy size={14} />复制名片
            </button>
            {active.commentUrl && (
              <a className="btn" href={active.commentUrl} target="_blank" rel="noreferrer">
                <MessageSquareText size={14} />评论来源
              </a>
            )}
            <button type="button" className="btn btn-primary" onClick={() => startContact(active)} disabled={startContactMutation.isPending}>
              {startContactMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Handshake size={14} />}
              建联并打开
            </button>
          </>
        )}
      >
        {active && (
          <div className="space-y-4">
            <div className="rounded-md border border-border bg-bg p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-lg font-semibold">{active.name}</h2>
                    <span className={statusClass(active.status)}>{STATUS_META[active.status].label}</span>
                  </div>
                  <div className="mt-1 text-xs text-muted">{active.subtitle}</div>
                </div>
                <div className="text-right">
                  <div className={`num text-3xl font-semibold ${scoreTone(active.score)}`}>{active.score}</div>
                  <div className="text-xxs text-muted">推荐分</div>
                </div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <InfoLine icon={<UserRound size={14} />} label="账号" value={active.account || active.contactLabel} />
                <InfoLine icon={<Globe2 size={14} />} label="平台" value={active.platform} />
                <InfoLine icon={<Link2 size={14} />} label="联系方式" value={active.contactLabel} />
                <InfoLine icon={<ShieldCheck size={14} />} label="优先级" value={active.priority} />
              </div>
            </div>

            <Section title="判断证据" icon={<MessageSquareText size={15} />}>
              <p className="text-sm leading-6">{active.evidence}</p>
            </Section>

            <Section title="推荐理由" icon={<Sparkles size={15} />}>
              <p className="text-sm leading-6">{active.reason}</p>
            </Section>

            <Section title="建联建议" icon={<Handshake size={15} />}>
              <p className="text-sm leading-6">{active.suggestion}</p>
            </Section>

            <div className="grid gap-2 sm:grid-cols-2">
              {active.board === 'customers' && <ActionRoute to={`/social-users/${active.id}`} label="查看用户详情" />}
              {active.profileUrl && <ActionLink href={active.profileUrl} label="打开用户主页" />}
              {active.sourceUrl && <ActionLink href={active.sourceUrl} label="打开公司来源" />}
              {active.commentUrl && <ActionLink href={active.commentUrl} label="打开评论链接" />}
            </div>
          </div>
        )}
      </SideDrawer>
    </div>
  );
}

function BoardButton({ active, icon, label, count, onClick }: { active: boolean; icon: React.ReactNode; label: string; count: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`mt-1 flex w-full items-center justify-between rounded px-3 py-2 text-left text-xs transition first:mt-0 ${active ? 'bg-accent text-slate-950' : 'hover:bg-elev2'}`}
    >
      <span className="inline-flex items-center gap-2 font-medium">{icon}{label}</span>
      <span className="num">{count}</span>
    </button>
  );
}

function Kpi({ label, value, tone = 'text-text' }: { label: string; value: number; tone?: string }) {
  return (
    <div className="min-w-[92px] rounded-md border border-border bg-bg px-3 py-2">
      <div className={`num text-lg font-semibold ${tone}`}>{value}</div>
      <div className="text-xxs text-muted">{label}</div>
    </div>
  );
}

function FlowRow({ index, title, text }: { index: string; title: string; text: string }) {
  return (
    <div className="flex gap-2 border-t border-border py-2 first:border-t-0 first:pt-0 last:pb-0">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xxs text-accent">{index}</span>
      <div>
        <div className="text-xs font-medium">{title}</div>
        <div className="text-xxs text-muted">{text}</div>
      </div>
    </div>
  );
}

function RecommendationRow({
  item,
  busy,
  onOpen,
  onStart,
}: {
  item: RecommendationCard;
  busy: boolean;
  onOpen: () => void;
  onStart: () => void;
}) {
  return (
    <article className="rounded-md border border-border bg-elev1 p-3 transition hover:border-accent/60 hover:bg-elev2/60">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent/15 text-accent">
          {item.board === 'customers' ? <UserRound size={18} /> : <Building2 size={18} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {item.board === 'customers' ? (
              <Link to={`/social-users/${item.id}`} className="truncate text-left text-sm font-semibold hover:text-accent">
                {item.name}
              </Link>
            ) : (
              <button type="button" onClick={onOpen} className="truncate text-left text-sm font-semibold hover:text-accent">
                {item.name}
              </button>
            )}
            <span className={statusClass(item.status)}>{STATUS_META[item.status].label}</span>
          </div>
          <div className="mt-0.5 truncate text-xxs text-muted">{item.subtitle}</div>
          <div className="mt-2 line-clamp-2 min-h-[34px] text-xs leading-5 text-text/90">{item.evidence}</div>
          <div className="mt-2 flex flex-wrap gap-1">
            {item.tags.slice(0, 4).map((tag) => (
              <span key={tag} className="rounded-full bg-bg px-2 py-0.5 text-xxs text-muted">{tag}</span>
            ))}
          </div>
        </div>
        <div className="w-20 shrink-0 text-right">
          <div className={`num text-2xl font-semibold ${scoreTone(item.score)}`}>{item.score}</div>
          <div className="text-xxs text-muted">{item.priority}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
        {item.board === 'customers' ? (
          <Link
            to={`/social-users/${item.id}`}
            className="max-w-full truncate rounded-full bg-bg px-2 py-1 text-xxs text-accent hover:underline"
            title="查看用户详细信息"
          >
            {item.contactLabel}
          </Link>
        ) : (
          <div className="truncate text-xxs text-muted">{item.contactLabel}</div>
        )}
        <div className="flex gap-2">
          <button type="button" onClick={onOpen} className="btn btn-ghost !h-8">
            名片 <ArrowUpRight size={13} />
          </button>
          <button type="button" onClick={onStart} className="btn btn-primary !h-8" disabled={busy}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Handshake size={13} />}建联
          </button>
        </div>
      </div>
    </article>
  );
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-bg p-4">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-accent">
        {icon}
        {title}
      </div>
      {children}
    </section>
  );
}

function InfoLine({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-elev1 px-3 py-2">
      <div className="flex items-center gap-1.5 text-xxs text-muted">{icon}{label}</div>
      <div className="mt-1 truncate text-xs">{value}</div>
    </div>
  );
}

function ActionLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded-md border border-border bg-bg px-3 py-2 text-xs transition hover:border-accent hover:text-accent">
      {label}
      <ExternalLink size={14} />
    </a>
  );
}

function ActionRoute({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="flex items-center justify-between rounded-md border border-border bg-bg px-3 py-2 text-xs transition hover:border-accent hover:text-accent">
      {label}
      <ArrowUpRight size={14} />
    </Link>
  );
}
