import { useState } from 'react';
import { Briefcase, Building2, Clock3, Star, Mail, Users } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useForeignTradeCollection, type LeadItem } from '@/api/foreignTrade';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';
import LeadDetailDrawer, { type LeadKind } from './LeadDetailDrawer';

const PAGE_SIZE = 10;

const PLATFORM_LABELS: Record<string, string> = {
  '51job': '前程无忧',
  zhaopin: '智联招聘',
  qzrc: '大泉州人才网',
};

const TIER_TONE: Record<string, 'good' | 'warn' | 'muted'> = {
  A: 'good',
  B: 'warn',
  C: 'muted',
};

function shortTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return '暂无';
  const diff = Date.now() - ts;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

const KIND_LABELS: Record<string, string> = { company: '公司客户', talent: '跨境人才' };

export default function CollectJobs() {
  const A = ACCENTS.jobs;
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<{ id: string; kind: LeadKind } | null>(null);
  const feed = useForeignTradeCollection({ channel: 'jobs', limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const stats = feed.data?.stats ?? {};
  const items = feed.data?.items ?? [];
  const total = feed.data?.total ?? 0;

  // jobs channel rows are either company leads or talent leads; route each to
  // the matching detail endpoint (/company-leads/{id} or /talents/{id}).
  const openDetail = (row: LeadItem) => {
    if (row.kind === 'company' || row.kind === 'talent') {
      setDetail({ id: row.id, kind: row.kind });
    }
  };

  const columns: Column<LeadItem>[] = [
    {
      key: 'name',
      header: '公司 / 线索',
      width: '260px',
      cell: (row) => (
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold text-gray-900">{row.name || '—'}</div>
          <div className="truncate text-xxs text-muted">{row.subtitle || '—'}</div>
        </div>
      ),
    },
    {
      key: 'kind',
      header: '类型',
      cell: (row) => <span className="text-xs text-gray-700">{KIND_LABELS[row.kind] || row.kind_label || '—'}</span>,
    },
    {
      key: 'platform',
      header: '来源',
      cell: (row) => <span className="text-xs text-gray-700">{PLATFORM_LABELS[row.platform || ''] || row.platform || '—'}</span>,
    },
    {
      key: 'tier',
      header: '分级',
      cell: (row) => (row.tier ? <Pill tone={TIER_TONE[row.tier] || 'muted'}>{row.tier} 级</Pill> : <span className="text-xs text-muted">未评级</span>),
    },
    {
      key: 'status',
      header: '状态',
      cell: (row) => <span className="text-xs text-gray-700">{row.status || '—'}</span>,
    },
    {
      key: 'contact',
      header: '联系方式',
      cell: (row) => <span className="truncate text-xs text-gray-700">{row.contact || '—'}</span>,
    },
    {
      key: 'us',
      header: '美区',
      cell: (row) => (row.us_market ? <Pill tone="good">美区</Pill> : <span className="text-xs text-muted">—</span>),
    },
    { key: 'created', header: '采集时间', align: 'right', cell: (row) => <span className="text-xs text-muted">{shortTime(row.created_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={Briefcase} title="招聘网站采集" subtitle="51job / 智联 / 大泉州 · 公司客户与跨境人才" />

      <AsyncState loading={feed.isLoading} error={feed.error} height={420}>
        <Reveal i={1}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <KpiCard label="总线索" value={num(stats.total)} icon={Building2} iconBg={A.soft} iconColor={A.key} />
            <KpiCard label="今日采集" value={num(stats.today)} icon={Clock3} iconBg="#e0e7ff" iconColor="#4f46e5" />
            <KpiCard label="公司客户" value={num(stats.company_total)} icon={Building2} iconBg="#dbeafe" iconColor="#2563eb" />
            <KpiCard label="跨境人才" value={num(stats.talent_total)} icon={Users} iconBg="#dcfce7" iconColor="#16a34a" />
            <KpiCard label="A 级线索" value={num(stats.tier_a)} icon={Star} iconBg="#fef3c7" iconColor="#ca8a04" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <section className="mt-4 rounded-lg border border-line bg-white shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className="flex items-center gap-2">
                <Mail size={16} style={{ color: A.key }} />
                <h3 className="text-sm font-semibold text-gray-900">最近采集的招聘线索</h3>
              </div>
              <span className="text-xxs text-muted">{num(total)} 条招聘线索 · 点击查看详情与原页链接</span>
            </div>
            <div className="p-2">
              <AsyncState
                loading={feed.isLoading}
                error={feed.error}
                isEmpty={!feed.isLoading && items.length === 0}
                emptyMessage="还没有招聘网站采集数据"
                height={240}
              >
                <DataTable columns={columns} data={items} rowKey={(row) => row.id} emptyText="还没有采集记录" onRowClick={openDetail} />
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
          </section>
        </Reveal>
      </AsyncState>

      <LeadDetailDrawer kind={detail?.kind ?? 'company'} id={detail?.id ?? null} onClose={() => setDetail(null)} />
    </div>
  );
}
