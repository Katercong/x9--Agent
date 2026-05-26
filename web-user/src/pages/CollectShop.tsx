import { useMemo } from 'react';
import { AlertTriangle, Clock3, Database, ListChecks, Radio, Store, UserRound } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useMe } from '@/hooks/useApi';
import { useShopCollectionSummary, type ObservationItem } from '@/api/collector';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

const A = ACCENTS.shop;

type UserStatus = 'collecting' | 'idle' | 'offline' | 'error';

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

function normalizeStatus(value: unknown, total: number): UserStatus {
  if (value === 'error') return 'error';
  if (value === 'collecting') return 'collecting';
  if (value === 'idle') return 'idle';
  return total > 0 ? 'offline' : 'offline';
}

function statusMeta(status: UserStatus) {
  if (status === 'error') return { label: '异常', tone: 'bad' as const, icon: AlertTriangle };
  if (status === 'collecting') return { label: '采集中', tone: 'good' as const, icon: Radio };
  if (status === 'idle') return { label: '闲置', tone: 'info' as const, icon: Clock3 };
  return { label: '不在线', tone: 'muted' as const, icon: Clock3 };
}

function rowStatus(row: ObservationItem): { label: string; tone: 'good' | 'warn' } {
  return row.ingest_status === 'ingested'
    ? { label: '已入库', tone: 'good' }
    : { label: '队列中', tone: 'warn' };
}

export default function CollectShop() {
  const me = useMe();
  const summary = useShopCollectionSummary(300);

  const user = me.data?.user;
  const stats = summary.data?.stats;
  const items = summary.data?.recent?.items ?? [];
  const total = Number(stats?.total ?? 0);
  const today = Number(stats?.today ?? 0);
  const ingested = Number(stats?.ingested_total ?? 0);
  const queued = Number(stats?.queued_total ?? today);
  const lastCollectedAt = stats?.last_collected_at ?? items[0]?.collected_at ?? items[0]?.created_at ?? null;
  const status = normalizeStatus(stats?.user_status, total);
  const statusInfo = statusMeta(status);
  const StatusIcon = statusInfo.icon;
  const displayName = user?.display_name || user?.username || '当前用户';

  const rows = useMemo(() => items.slice(0, 300), [items]);

  const columns: Column<ObservationItem>[] = [
    {
      key: 'creator',
      header: '达人',
      width: '220px',
      cell: (row) => (
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-text">@{row.handle || 'unknown'}</div>
          <div className="truncate text-xxs text-muted">{row.display_name || '—'}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '状态',
      cell: (row) => {
        const state = rowStatus(row);
        return <Pill tone={state.tone}>{state.label}</Pill>;
      },
    },
    { key: 'gmv', header: 'GMV', align: 'right', cell: (row) => <span className="num text-xs font-semibold text-text">{row.shop?.gmv_raw || '—'}</span> },
    { key: 'category', header: '类目', cell: (row) => <span className="text-xs text-text">{row.shop?.category_text || '—'}</span> },
    { key: 'keyword', header: '关键词', cell: (row) => <span className="text-xs text-text">{row.search_keyword || '—'}</span> },
    { key: 'time', header: '采集时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.collected_at || row.created_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader
        accent={A}
        icon={Store}
        title="我的 TikTok Shop 采集"
        subtitle="数据库统计 · 队列与入库记录"
        right={<Pill tone={statusInfo.tone}>{statusInfo.label}</Pill>}
      />

      <AsyncState
        loading={summary.isLoading || me.isLoading}
        error={summary.error || me.error}
        isEmpty={false}
        emptyMessage="还没有 TikTok Shop 采集数据"
        height={420}
      >
        <Reveal i={1}>
          <section className="card card-body">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: A.key }}>
                  <UserRound size={22} />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-base font-bold text-text">{displayName}</div>
                  <div className="mt-1 text-xs text-muted">最后采集：{shortTime(lastCollectedAt)}</div>
                </div>
              </div>
              <div className="inline-flex items-center gap-2 rounded-md border border-border bg-elev2 px-3 py-2 text-xs font-semibold text-text">
                <StatusIcon size={14} />
                {statusInfo.label}
              </div>
            </div>
          </section>
        </Reveal>

        <Reveal i={2}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <KpiCard label="今日采集" value={num(today)} icon={Clock3} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="总采集" value={num(total)} icon={Database} iconBg="rgba(99,102,241,0.16)" iconColor="#818cf8" />
            <KpiCard label="今日队列中" value={num(queued)} icon={ListChecks} iconBg="rgba(245,158,11,0.16)" iconColor="#f59e0b" />
            <KpiCard label="已入库" value={num(ingested)} icon={Database} iconBg="rgba(16,185,129,0.16)" iconColor="#10b981" />
            <KpiCard label="最后采集" value={shortTime(lastCollectedAt)} icon={Clock3} iconBg="rgba(6,182,212,0.14)" iconColor="#06b6d4" compact />
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <section className="card card-body">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-text">今日队列中</div>
                  <div className="mt-1 text-xxs text-muted">当天未形成入库结果，次日自动归零</div>
                </div>
                <div className="num text-2xl font-black text-text">{num(queued)}</div>
              </div>
            </section>
            <section className="card card-body">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-text">已入库</div>
                  <div className="mt-1 text-xxs text-muted">已经进入达人数据或来源归档</div>
                </div>
                <div className="num text-2xl font-black text-text">{num(ingested)}</div>
              </div>
            </section>
          </div>
        </Reveal>

        <Reveal i={4}>
          <section className="card mt-4">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-text">我的最近采集记录</h3>
              <div className="text-xxs text-muted">来自数据库，仅包含当前登录用户的数据</div>
            </div>
            <div className="p-2">
              <DataTable columns={columns} data={rows} rowKey={(row) => row.id} emptyText="还没有 TikTok Shop 采集数据" />
            </div>
          </section>
        </Reveal>
      </AsyncState>
    </div>
  );
}
