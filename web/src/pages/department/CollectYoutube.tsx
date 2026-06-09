import { type ReactNode, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Clock3,
  Database,
  FileText,
  ListChecks,
  Mail,
  RefreshCw,
  ShieldAlert,
  Users,
  Youtube,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import {
  useYoutubeActors,
  useYoutubeLeads,
  useYoutubeManualReview,
  useYoutubeRuns,
  useYoutubeSources,
  useYoutubeStats,
  type YoutubeActor,
  type YoutubeImportRun,
  type YoutubeLead,
  type YoutubeLeadSource,
} from '@/api/youtube';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

const A = ACCENTS.youtube;
const PAGE_SIZE = 10;

type TabKey = 'runs' | 'leads' | 'manual' | 'sources';
type LeadFilter = 'all' | 'email' | 'review';

function timeValue(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function shortTime(value: string | null | undefined): string {
  const ts = timeValue(value);
  if (!ts) return '暂无';
  const diff = Date.now() - ts;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const date = new Date(ts);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function sourceLabel(value: string) {
  if (value === 'creator_channel') return '视频博主';
  if (value === 'comment_author_channel') return '评论用户';
  return value || '未知来源';
}

function reviewReasonLabel(value: string) {
  if (value === 'captcha_required') return '验证码';
  if (value === 'hidden_email_button_present') return '隐藏邮箱';
  if (value === 'login_required') return '需登录';
  return value;
}

function actorStatus(actor: YoutubeActor) {
  return actor.collection.user_status === 'online'
    ? { label: '有数据', tone: 'good' as const, className: 'border-emerald-200 bg-emerald-50 text-emerald-700' }
    : { label: '等待采集', tone: 'muted' as const, className: 'border-stone-200 bg-stone-50 text-stone-600' };
}

function displayName(actor: YoutubeActor) {
  return actor.display_name || actor.username || actor.id;
}

export default function CollectYoutube() {
  const stats = useYoutubeStats();
  const actors = useYoutubeActors();
  const [activeActorId, setActiveActorId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('leads');
  const [runPage, setRunPage] = useState(0);
  const [leadPage, setLeadPage] = useState(0);
  const [manualPage, setManualPage] = useState(0);
  const [sourcePage, setSourcePage] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [leadFilter, setLeadFilter] = useState<LeadFilter>('all');
  const [selectedLead, setSelectedLead] = useState<YoutubeLead | null>(null);

  const actorItems = actors.data?.items ?? [];
  const activeActor = actorItems.find((actor) => actor.id === activeActorId) || (actorItems.length === 1 ? actorItems[0] : null);

  const runs = useYoutubeRuns({ limit: PAGE_SIZE, offset: runPage * PAGE_SIZE });
  const leads = useYoutubeLeads({
    keyword,
    source_type: sourceType,
    has_email: leadFilter === 'email' ? true : undefined,
    needs_manual_review: leadFilter === 'review' ? true : undefined,
    limit: PAGE_SIZE,
    offset: leadPage * PAGE_SIZE,
  });
  const manual = useYoutubeManualReview({
    keyword,
    source_type: sourceType,
    limit: PAGE_SIZE,
    offset: manualPage * PAGE_SIZE,
  });
  const sources = useYoutubeSources(selectedLead?.id ?? null, { limit: PAGE_SIZE, offset: sourcePage * PAGE_SIZE });

  useEffect(() => {
    setSourcePage(0);
  }, [selectedLead?.id]);

  const runColumns = useMemo<Column<YoutubeImportRun>[]>(
    () => [
      {
        key: 'file',
        header: '批次',
        width: '260px',
        cell: (row) => (
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-gray-900">{row.filename || row.id}</div>
            <div className="truncate text-xxs text-muted">{row.id}</div>
          </div>
        ),
      },
      { key: 'keyword', header: '关键词', cell: (row) => <span className="text-xs">{row.keyword || '—'}</span> },
      { key: 'raw', header: 'Raw', align: 'right', cell: (row) => <span className="num text-xs">{num(row.total_rows)}</span> },
      { key: 'kept', header: '保留', align: 'right', cell: (row) => <span className="num text-xs">{num(row.kept_rows)}</span> },
      { key: 'dropped', header: '空邮箱丢弃', align: 'right', cell: (row) => <span className="num text-xs">{num(row.dropped_no_contact)}</span> },
      { key: 'review', header: '人工审查', align: 'right', cell: (row) => <Pill tone={row.manual_review ? 'warn' : 'muted'}>{num(row.manual_review)}</Pill> },
      { key: 'status', header: '状态', cell: (row) => <Pill tone={row.status === 'imported' ? 'good' : 'info'}>{row.status}</Pill> },
      { key: 'time', header: '导入时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.finished_at || row.created_at)}</span> },
    ],
    [],
  );

  const leadColumns = useMemo<Column<YoutubeLead>[]>(
    () => [
      {
        key: 'channel',
        header: '频道',
        width: '280px',
        cell: (row) => (
          <button
            type="button"
            onClick={() => {
              setSelectedLead(row);
              setActiveTab('sources');
            }}
            className="max-w-[260px] text-left"
          >
            <div className="truncate text-xs font-semibold text-gray-900">{row.display_name || row.channel_handle || row.channel_key}</div>
            <div className="truncate text-xxs text-brand-500">{row.channel_url || row.channel_key}</div>
          </button>
        ),
      },
      {
        key: 'email',
        header: '邮箱',
        cell: (row) => (row.email ? <span className="num text-xs">{row.email}</span> : <span className="text-xxs text-muted">未公开</span>),
      },
      { key: 'source', header: '来源', cell: (row) => <Pill tone="info">{sourceLabel(row.latest_source_type)}</Pill> },
      { key: 'keyword', header: '关键词', cell: (row) => <span className="text-xs">{row.latest_keyword || '—'}</span> },
      {
        key: 'video',
        header: '来源视频',
        cell: (row) =>
          row.latest_video_url ? (
            <a className="text-xs text-brand-500 hover:underline" href={row.latest_video_url} target="_blank" rel="noreferrer">
              打开
            </a>
          ) : (
            <span className="text-xxs text-muted">—</span>
          ),
      },
      {
        key: 'review',
        header: '审查状态',
        cell: (row) =>
          row.needs_manual_review ? (
            <Pill tone="warn">{row.review_reasons.map(reviewReasonLabel).join(', ') || '人工审查'}</Pill>
          ) : (
            <Pill tone={row.has_email ? 'good' : 'muted'}>{row.has_email ? '有邮箱' : '无需审查'}</Pill>
          ),
      },
      { key: 'updated', header: '更新时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.updated_at || row.last_seen_at)}</span> },
    ],
    [],
  );

  const sourceColumns = useMemo<Column<YoutubeLeadSource>[]>(
    () => [
      { key: 'source', header: '来源类型', cell: (row) => <Pill tone="info">{sourceLabel(row.source_type)}</Pill> },
      { key: 'keyword', header: '关键词', cell: (row) => <span className="text-xs">{row.keyword || '—'}</span> },
      {
        key: 'video',
        header: '视频',
        width: '280px',
        cell: (row) => (
          <div className="min-w-0">
            <div className="truncate text-xs text-gray-800">{row.video_title || row.video_id || '—'}</div>
            {row.video_url ? (
              <a className="text-xxs text-brand-500 hover:underline" href={row.video_url} target="_blank" rel="noreferrer">
                打开视频
              </a>
            ) : null}
          </div>
        ),
      },
      { key: 'email', header: '邮箱', cell: (row) => (row.email ? <span className="num text-xs">{row.email}</span> : <span className="text-xxs text-muted">—</span>) },
      {
        key: 'evidence',
        header: '证据',
        cell: (row) =>
          row.evidence_url ? (
            <a className="text-xs text-brand-500 hover:underline" href={row.evidence_url} target="_blank" rel="noreferrer">
              打开
            </a>
          ) : (
            <span className="text-xxs text-muted">—</span>
          ),
      },
      { key: 'time', header: '采集时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.collected_at || row.created_at)}</span> },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <CollectHeader
        accent={A}
        icon={Youtube}
        title="采集 · YouTube"
        subtitle="本地插件采集 · 邮箱清洗 · 人工审查 · 入库明细"
        right={<Pill tone="info">本地测试模式</Pill>}
      />

      <AsyncState
        loading={stats.isLoading || actors.isLoading}
        error={stats.error || actors.error}
        isEmpty={false}
        height={420}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <KpiCard label="今日导入" value={num(stats.data?.today_runs ?? 0)} icon={Clock3} iconBg={A.soft} iconColor={A.key} />
            <KpiCard label="Raw Rows" value={num(stats.data?.raw_rows ?? 0)} icon={Database} iconBg="#e0f2fe" iconColor="#0284c7" />
            <KpiCard label="有效 Leads" value={num(stats.data?.leads ?? 0)} icon={Users} iconBg="#dcfce7" iconColor="#16a34a" />
            <KpiCard label="有邮箱" value={num(stats.data?.has_email ?? 0)} icon={Mail} iconBg="#d1fae5" iconColor="#059669" />
            <KpiCard label="人工审查" value={num(stats.data?.manual_review ?? 0)} icon={ShieldAlert} iconBg="#fef3c7" iconColor="#d97706" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <section className="mt-4 rounded-lg border border-line bg-white shadow-card">
            <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className="flex items-center gap-2">
                <Users size={16} style={{ color: A.key }} />
                <h3 className="text-sm font-semibold text-gray-900">采集用户</h3>
              </div>
              <span className="text-xxs text-muted">默认连接本地 127.0.0.1:8000</span>
            </div>
            {actorItems.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 p-3 md:grid-cols-2 xl:grid-cols-3">
                {actorItems.map((actor) => {
                  const status = actorStatus(actor);
                  const active = activeActor?.id === actor.id;
                  return (
                    <button
                      key={actor.id}
                      type="button"
                      onClick={() => setActiveActorId(actor.id)}
                      className={`rounded-lg border bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-soft ${
                        active ? 'border-gray-900 ring-2 ring-gray-900/10' : 'border-line'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-black text-gray-900">{displayName(actor)}</div>
                          <div className="mt-1 truncate text-xxs text-muted">最近批次：{actor.collection.latest_run?.filename || '暂无'}</div>
                        </div>
                        <span className={`shrink-0 rounded-md border px-2 py-1 text-xxs font-bold ${status.className}`}>{status.label}</span>
                      </div>
                      <div className="mt-4 grid grid-cols-4 gap-3">
                        <MiniStat label="Raw" value={actor.collection.total} />
                        <MiniStat label="Leads" value={actor.collection.lead_total} />
                        <MiniStat label="邮箱" value={actor.collection.with_email} />
                        <MiniStat label="审查" value={actor.collection.manual_review} />
                      </div>
                      <div className="mt-4 flex items-center justify-between gap-2 text-xxs text-muted">
                        <span>最后采集</span>
                        <span>{shortTime(actor.collection.last_collected_at)}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="px-4 py-10 text-center text-sm text-muted">本地库暂无 YouTube 采集数据，插件上传后这里会出现采集卡片</div>
            )}
          </section>
        </Reveal>

        <Reveal i={3}>
          <section className="mt-4 rounded-lg border border-line bg-white shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className="flex flex-wrap gap-2">
                <TabButton active={activeTab === 'runs'} onClick={() => setActiveTab('runs')}>导入批次</TabButton>
                <TabButton active={activeTab === 'leads'} onClick={() => setActiveTab('leads')}>清洗 Leads</TabButton>
                <TabButton active={activeTab === 'manual'} onClick={() => setActiveTab('manual')}>人工审查</TabButton>
                <TabButton active={activeTab === 'sources'} onClick={() => setActiveTab('sources')}>来源证据</TabButton>
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  stats.refetch();
                  actors.refetch();
                  runs.refetch();
                  leads.refetch();
                  manual.refetch();
                  sources.refetch();
                }}
              >
                <RefreshCw size={14} /> 刷新
              </button>
            </div>

            {(activeTab === 'leads' || activeTab === 'manual') && (
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
                <input
                  value={keyword}
                  onChange={(event) => {
                    setKeyword(event.target.value);
                    setLeadPage(0);
                    setManualPage(0);
                  }}
                  placeholder="关键词筛选"
                  className="h-8 w-44 rounded border border-line px-2 text-xs outline-none focus:border-brand-500"
                />
                <select
                  value={sourceType}
                  onChange={(event) => {
                    setSourceType(event.target.value);
                    setLeadPage(0);
                    setManualPage(0);
                  }}
                  className="h-8 rounded border border-line px-2 text-xs outline-none focus:border-brand-500"
                >
                  <option value="">全部来源</option>
                  <option value="creator_channel">视频博主</option>
                  <option value="comment_author_channel">评论用户</option>
                </select>
                {activeTab === 'leads' ? (
                  <select
                    value={leadFilter}
                    onChange={(event) => {
                      setLeadFilter(event.target.value as LeadFilter);
                      setLeadPage(0);
                    }}
                    className="h-8 rounded border border-line px-2 text-xs outline-none focus:border-brand-500"
                  >
                    <option value="all">全部 Lead</option>
                    <option value="email">有邮箱</option>
                    <option value="review">人工审查</option>
                  </select>
                ) : null}
              </div>
            )}

            <div className="min-h-[360px] p-2">
              {activeTab === 'runs' && (
                <AsyncState loading={runs.isLoading} error={runs.error} isEmpty={!runs.isLoading && (runs.data?.items.length ?? 0) === 0} emptyMessage="暂无导入批次" height={320}>
                  <DataTable columns={runColumns} data={runs.data?.items ?? []} rowKey={(row) => row.id} />
                  <PaginationControls page={runPage} pageSize={PAGE_SIZE} total={runs.data?.total ?? 0} currentCount={runs.data?.items.length ?? 0} loading={runs.isFetching} onPageChange={setRunPage} />
                </AsyncState>
              )}

              {activeTab === 'leads' && (
                <AsyncState loading={leads.isLoading} error={leads.error} isEmpty={!leads.isLoading && (leads.data?.items.length ?? 0) === 0} emptyMessage="暂无清洗后的 YouTube Lead" height={320}>
                  <DataTable columns={leadColumns} data={leads.data?.items ?? []} rowKey={(row) => row.id} />
                  <PaginationControls page={leadPage} pageSize={PAGE_SIZE} total={leads.data?.total ?? 0} currentCount={leads.data?.items.length ?? 0} loading={leads.isFetching} onPageChange={setLeadPage} />
                </AsyncState>
              )}

              {activeTab === 'manual' && (
                <AsyncState loading={manual.isLoading} error={manual.error} isEmpty={!manual.isLoading && (manual.data?.items.length ?? 0) === 0} emptyMessage="暂无需要人工审查的频道" height={320}>
                  <DataTable columns={leadColumns} data={manual.data?.items ?? []} rowKey={(row) => row.id} />
                  <PaginationControls page={manualPage} pageSize={PAGE_SIZE} total={manual.data?.total ?? 0} currentCount={manual.data?.items.length ?? 0} loading={manual.isFetching} onPageChange={setManualPage} />
                </AsyncState>
              )}

              {activeTab === 'sources' && (
                <div>
                  <div className="border-b border-line px-2 pb-3">
                    {selectedLead ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <Pill tone="info">{selectedLead.channel_handle || selectedLead.channel_key}</Pill>
                        {selectedLead.email ? <Pill tone="good">{selectedLead.email}</Pill> : <Pill tone="muted">未公开邮箱</Pill>}
                        {selectedLead.channel_url ? (
                          <a className="text-xs text-brand-500 hover:underline" href={selectedLead.channel_url} target="_blank" rel="noreferrer">
                            打开频道
                          </a>
                        ) : null}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-xs text-muted">
                        <FileText size={14} /> 在 Leads 或人工审查表点击频道后查看来源证据
                      </div>
                    )}
                  </div>
                  <AsyncState loading={sources.isLoading} error={sources.error} isEmpty={!selectedLead || (!sources.isLoading && (sources.data?.items.length ?? 0) === 0)} emptyMessage={selectedLead ? '暂无来源证据' : '请先选择一个 Lead'} height={300}>
                    <DataTable columns={sourceColumns} data={sources.data?.items ?? []} rowKey={(row) => row.id} />
                    <PaginationControls page={sourcePage} pageSize={PAGE_SIZE} total={sources.data?.total ?? 0} currentCount={sources.data?.items.length ?? 0} loading={sources.isFetching} onPageChange={setSourcePage} />
                  </AsyncState>
                </div>
              )}
            </div>
          </section>
        </Reveal>
      </AsyncState>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xxs text-muted">{label}</div>
      <div className="num mt-1 text-lg font-black text-gray-900">{num(value)}</div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className={`btn ${active ? 'btn-primary' : ''}`} onClick={onClick}>
      {children}
    </button>
  );
}
