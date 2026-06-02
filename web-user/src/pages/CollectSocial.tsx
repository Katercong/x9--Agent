import { useState } from 'react';
import { Heart, Users, Clock3, Flame, Mail, Telescope } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useForeignTradeCollection, type LeadItem } from '@/api/foreignTrade';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

const PAGE_SIZE = 10;

const PLATFORM_LABELS: Record<string, string> = { xhs: '小红书', douyin: '抖音' };

function parseTimeMs(value: string): number {
  const text = String(value || '').trim();
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(text);
  const normalized = !hasZone && /^\d{4}-\d{2}-\d{2}[T ]/.test(text) ? `${text.replace(' ', 'T')}Z` : text;
  return new Date(normalized).getTime();
}

function shortTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const ts = parseTimeMs(value);
  if (!Number.isFinite(ts)) return '暂无';
  const minutes = Math.floor((Date.now() - ts) / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function followers(value: number | null | undefined): string {
  if (!value) return '—';
  if (value >= 10000) return `${(value / 10000).toFixed(1)}w`;
  return num(value);
}

export default function CollectSocial() {
  const A = ACCENTS.social;
  const [page, setPage] = useState(0);
  const feed = useForeignTradeCollection({ channel: 'social', limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const stats = feed.data?.stats ?? {};
  const items = feed.data?.items ?? [];
  const total = feed.data?.total ?? 0;

  const columns: Column<LeadItem>[] = [
    {
      key: 'name',
      header: '博主',
      width: '240px',
      cell: (row) => (
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-text">{row.name || '—'}</div>
          <div className="truncate text-xxs text-muted">{row.subtitle || '—'}</div>
        </div>
      ),
    },
    { key: 'platform', header: '平台', cell: (row) => <span className="text-xs text-text">{PLATFORM_LABELS[row.platform || ''] || row.platform || '—'}</span> },
    { key: 'followers', header: '粉丝', align: 'right', cell: (row) => <span className="num text-xs font-semibold">{followers(row.followers)}</span> },
    { key: 'contact', header: '联系方式', cell: (row) => (row.has_contact ? <Pill tone="good">已提取</Pill> : <span className="text-xs text-muted">无</span>) },
    { key: 'created', header: '采集时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.created_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={Heart} title="小红书 / 抖音采集" subtitle="博主 / 笔记 / 评论 · 联系方式与采购意向" />

      <AsyncState loading={feed.isLoading} error={feed.error} height={420}>
        <Reveal i={1}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <KpiCard label="总博主线索" value={num(stats.total)} icon={Users} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="今日采集" value={num(stats.today)} icon={Clock3} iconBg="rgb(99 102 241 / 0.16)" iconColor="#818cf8" />
            <KpiCard label="采集批次" value={num(stats.runs)} icon={Telescope} iconBg="rgb(6 182 212 / 0.16)" iconColor="#22d3ee" />
            <KpiCard label="含联系方式" value={num(stats.with_contact)} icon={Mail} iconBg="rgb(37 99 235 / 0.16)" iconColor="#60a5fa" />
            <KpiCard label="高意向" value={num(stats.high_intent)} icon={Flame} iconBg="rgb(239 68 68 / 0.16)" iconColor="#f87171" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <Heart size={16} style={{ color: A.key }} />
                <h3 className="text-sm font-semibold text-text">最近采集的社媒博主</h3>
              </div>
              <span className="text-xxs text-muted">{num(total)} 个博主线索</span>
            </div>
            <div className="p-2">
              <AsyncState
                loading={feed.isLoading}
                error={feed.error}
                isEmpty={!feed.isLoading && items.length === 0}
                emptyMessage="还没有小红书 / 抖音采集数据"
                height={240}
              >
                <DataTable columns={columns} data={items} rowKey={(row) => row.id} emptyText="还没有采集记录" />
                <PaginationControls
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={total}
                  currentCount={items.length}
                  loading={feed.isFetching}
                  onPageChange={setPage}
                />
              </AsyncState>
            </div>
            <div className="h-1" style={{ background: A.key }} />
          </section>
        </Reveal>
      </AsyncState>
    </div>
  );
}
