import { useMemo, useState } from 'react';
import { AlertTriangle, Clock3, Database, ListChecks, Radio, Search, Store, Users, Radar } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import {
  useCollectionActors,
  useObservationsFeed,
  type CollectionActor,
  type ObservationItem,
  type SourceKey,
} from '@/api/collector';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

type MonitorSource = Extract<SourceKey, 'tiktok_shop' | 'x9_leads'>;

interface CollectShopProps {
  previewDemo?: boolean;
}

interface CollectionMonitorBoardProps {
  previewDemo?: boolean;
  sourceKey: MonitorSource;
}

interface UserCard {
  id: string;
  displayName: string;
  today: number;
  total: number;
  detail: number;
  gmv: number;
  lastCollectedAt: string | null;
  status: 'collecting' | 'idle' | 'offline' | 'error';
}

const SOURCE_META = {
  tiktok_shop: {
    accent: ACCENTS.shop,
    icon: Store,
    title: 'TikTok Shop 采集用户',
    subtitle: '数据库统计 · 队列与入库明细',
    empty: '还没有 TikTok Shop 采集数据',
  },
  x9_leads: {
    accent: ACCENTS.leads,
    icon: Radar,
    title: 'X9 线索采集用户',
    subtitle: '数据库统计 · 队列与入库明细',
    empty: '还没有 X9 线索采集数据',
  },
} as const;

function displayName(actor: CollectionActor): string {
  return actor.display_name || actor.username || actor.email || actor.id;
}

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

function shortWorkerId(value: string | null | undefined): string {
  if (!value) return '暂无 worker';
  const text = String(value);
  return text.length > 28 ? `${text.slice(0, 18)}...${text.slice(-6)}` : text;
}

function statusMeta(status: UserCard['status']) {
  if (status === 'error') return { label: '异常', tone: 'bad' as const, className: 'border-red-200 bg-red-50 text-red-700' };
  if (status === 'collecting') return { label: '采集中', tone: 'good' as const, className: 'border-emerald-200 bg-emerald-50 text-emerald-700' };
  if (status === 'idle') return { label: '闲置', tone: 'info' as const, className: 'border-sky-200 bg-sky-50 text-sky-700' };
  return { label: '不在线', tone: 'muted' as const, className: 'border-stone-200 bg-stone-50 text-stone-600' };
}

function normalizeStatus(actorStatus: unknown, total: number): UserCard['status'] {
  if (actorStatus === 'error') return 'error';
  if (actorStatus === 'collecting') return 'collecting';
  if (actorStatus === 'idle') return 'idle';
  return total > 0 ? 'offline' : 'offline';
}

function sourceStats(actor: CollectionActor, sourceKey: MonitorSource) {
  const collection = actor.collection || { total: 0, today: 0 };
  const bucket = collection.sources?.[sourceKey];
  if (sourceKey === 'tiktok_shop') {
    return {
      today: collection.shop_today ?? bucket?.today ?? 0,
      total: collection.shop_total ?? bucket?.total ?? 0,
      detail: collection.shop_detail_total ?? bucket?.funnel?.shop_profile_collected ?? 0,
      gmv: collection.with_gmv ?? bucket?.contacts?.with_gmv ?? 0,
      lastCollectedAt: bucket?.last_collected_at ?? collection.last_collected_at ?? null,
      status: normalizeStatus(collection.user_status, collection.shop_total ?? bucket?.total ?? 0),
    };
  }
  return {
    today: bucket?.today ?? collection.today ?? 0,
    total: bucket?.total ?? collection.total ?? 0,
    detail: bucket?.contacts?.with_email ?? 0,
    gmv: bucket?.contacts?.with_links ?? 0,
    lastCollectedAt: bucket?.last_collected_at ?? collection.last_collected_at ?? null,
    status: normalizeStatus(collection.user_status, bucket?.total ?? collection.total ?? 0),
  };
}

function rowStatus(row: ObservationItem): { label: string; tone: 'good' | 'warn' } {
  return row.ingest_status === 'ingested'
    ? { label: '已入库', tone: 'good' }
    : { label: '队列中', tone: 'warn' };
}

function rowGmv(row: ObservationItem): string {
  return row.shop?.gmv_raw || '—';
}

function rowCategory(row: ObservationItem): string {
  return row.shop?.category_text || row.lead?.current_status || '—';
}

export function CollectionMonitorBoard({ sourceKey }: CollectionMonitorBoardProps) {
  const meta = SOURCE_META[sourceKey];
  const A = meta.accent;
  const actors = useCollectionActors(true);
  const rawActors = actors.data?.items ?? [];
  const [selectedActorId, setSelectedActorId] = useState<string | null>(null);

  const cards = useMemo<UserCard[]>(() => {
    return rawActors
      .map((actor) => {
        const stats = sourceStats(actor, sourceKey);
        return {
          id: actor.id,
          displayName: displayName(actor),
          today: stats.today,
          total: stats.total,
          detail: stats.detail,
          gmv: stats.gmv,
          lastCollectedAt: stats.lastCollectedAt,
          status: stats.status,
        };
      })
      .sort((a, b) => {
        const rank = { error: 4, collecting: 3, idle: 2, offline: 1 };
        return rank[b.status] - rank[a.status] || b.today - a.today || b.total - a.total;
      });
  }, [rawActors, sourceKey]);

  const activeCard = cards.find((card) => card.id === selectedActorId) || (cards.length === 1 ? cards[0] : null);
  const detailActorId = activeCard?.id || '__none__';
  const detailFeed = useObservationsFeed({ source: sourceKey, limit: 300, actor_user_id: detailActorId });
  const detailItems = activeCard ? (detailFeed.data?.items ?? []) : [];

  const totals = useMemo(() => {
    return {
      today: cards.reduce((sum, card) => sum + card.today, 0),
      total: cards.reduce((sum, card) => sum + card.total, 0),
      collecting: cards.filter((card) => card.status === 'collecting').length,
      errors: cards.filter((card) => card.status === 'error').length,
    };
  }, [cards]);
  const unassignedStats = actors.data?.unassigned;
  const unassignedSource = unassignedStats?.sources?.[sourceKey];
  const unassignedTotal = unassignedSource?.total ?? (sourceKey === 'tiktok_shop' ? unassignedStats?.total ?? 0 : 0);
  const unassignedToday = unassignedSource?.today ?? (sourceKey === 'tiktok_shop' ? unassignedStats?.today ?? 0 : 0);
  const latestUnassignedWorker =
    unassignedStats?.recent_workers?.find((worker) => {
      if (!worker) return false;
      if (sourceKey === 'tiktok_shop') return worker.source === 'tiktok_shop' || worker.platform === 'tiktok_shop';
      return worker.source === sourceKey;
    }) || unassignedStats?.recent_workers?.[0] || null;

  const columns: Column<ObservationItem>[] = [
    {
      key: 'creator',
      header: '达人',
      width: '210px',
      cell: (row) => (
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-gray-900">@{row.handle || 'unknown'}</div>
          <div className="truncate text-xxs text-muted">{row.display_name || '—'}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '状态',
      cell: (row) => {
        const status = rowStatus(row);
        return <Pill tone={status.tone}>{status.label}</Pill>;
      },
    },
    { key: 'gmv', header: 'GMV', align: 'right', cell: (row) => <span className="num text-xs font-semibold">{rowGmv(row)}</span> },
    { key: 'category', header: '类目', cell: (row) => <span className="text-xs text-gray-700">{rowCategory(row)}</span> },
    { key: 'keyword', header: '关键词', cell: (row) => <span className="text-xs text-gray-700">{row.search_keyword || '—'}</span> },
    { key: 'collected', header: '采集时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.collected_at || row.created_at)}</span> },
    { key: 'ingested', header: '入库/更新', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.ingested_at || row.collected_at || row.created_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={meta.icon} title={meta.title} subtitle={meta.subtitle} />

      <AsyncState
        loading={actors.isLoading}
        error={actors.error}
        isEmpty={!actors.isLoading && cards.length === 0}
        emptyMessage={meta.empty}
        height={420}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <KpiCard label="今日采集" value={num(totals.today)} icon={Clock3} iconBg={A.soft} iconColor={A.key} />
            <KpiCard label="总采集" value={num(totals.total)} icon={Database} iconBg="#e0e7ff" iconColor="#4f46e5" />
            <KpiCard label="采集中用户" value={num(totals.collecting)} icon={Radio} iconBg="#dcfce7" iconColor="#16a34a" />
            <KpiCard label="异常用户" value={num(totals.errors)} icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
            <KpiCard
              label="未归属采集"
              value={num(unassignedTotal)}
              subLabel={`今日 ${num(unassignedToday)} · ${shortWorkerId(latestUnassignedWorker?.worker_id)}`}
              icon={AlertTriangle}
              iconBg="#fff7ed"
              iconColor="#ea580c"
            />
          </div>
        </Reveal>

        <Reveal i={2}>
          <section className="mt-4 rounded-lg border border-line bg-white shadow-card">
            <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className="flex items-center gap-2">
                <Users size={16} style={{ color: A.key }} />
                <h3 className="text-sm font-semibold text-gray-900">采集用户</h3>
              </div>
              <span className="text-xxs text-muted">{num(cards.length)} 个用户</span>
            </div>
            <div className="grid grid-cols-1 gap-3 p-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {cards.map((card) => {
                const status = statusMeta(card.status);
                const active = activeCard?.id === card.id;
                return (
                  <button
                    key={card.id}
                    type="button"
                    onClick={() => setSelectedActorId(card.id)}
                    className={`rounded-lg border bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-soft ${
                      active ? 'border-gray-900 ring-2 ring-gray-900/10' : 'border-line'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-black text-gray-900">{card.displayName}</div>
                      </div>
                      <span className={`shrink-0 rounded-md border px-2 py-1 text-xxs font-bold ${status.className}`}>{status.label}</span>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xxs text-muted">今日采集</div>
                        <div className="num mt-1 text-lg font-black text-gray-900">{num(card.today)}</div>
                      </div>
                      <div>
                        <div className="text-xxs text-muted">总采集</div>
                        <div className="num mt-1 text-lg font-black text-gray-900">{num(card.total)}</div>
                      </div>
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-2 text-xxs text-muted">
                      <span>最后采集</span>
                      <span>{shortTime(card.lastCollectedAt)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </Reveal>

        <Reveal i={3}>
          <section className="mt-4 rounded-lg border border-line bg-white shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className="flex items-center gap-2">
                <ListChecks size={16} style={{ color: A.key }} />
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    {activeCard ? `${activeCard.displayName} 的采集详情` : '选择一个用户查看详情'}
                  </h3>
                  <div className="text-xxs text-muted">只展示该用户上传的数据库记录</div>
                </div>
              </div>
              {activeCard ? <Pill tone={statusMeta(activeCard.status).tone}>{statusMeta(activeCard.status).label}</Pill> : null}
            </div>
            {activeCard ? (
              <div className="p-2">
                <AsyncState
                  loading={detailFeed.isLoading}
                  error={detailFeed.error}
                  isEmpty={!detailFeed.isLoading && detailItems.length === 0}
                  emptyMessage="该用户还没有 TikTok Shop 采集记录"
                  height={240}
                >
                  <DataTable columns={columns} data={detailItems} rowKey={(row) => row.id} emptyText="该用户还没有采集记录" />
                </AsyncState>
              </div>
            ) : (
              <div className="px-4 py-10 text-center text-sm text-muted">点击上方用户卡片查看上传明细</div>
            )}
          </section>
        </Reveal>
      </AsyncState>
    </div>
  );
}

export default function CollectShop({ previewDemo = false }: CollectShopProps) {
  return <CollectionMonitorBoard sourceKey="tiktok_shop" previewDemo={previewDemo} />;
}
