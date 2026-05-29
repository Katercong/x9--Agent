import { DataTable, type Column } from '@/components/table/DataTable';
import type { AnalyticsMemberRow } from '@/api/types';

function countOf(value: unknown) {
  return Number(value ?? 0) || 0;
}

function memberLabel(value: string) {
  if (!value || value === 'unassigned') return '未分配';
  return value;
}

interface OutreachStatsTableProps {
  rows: AnalyticsMemberRow[];
  title?: string;
  subtitle?: string;
  emptyText?: string;
}

export function OutreachStatsTable({
  rows,
  title = '达人建联统计数据',
  subtitle = '只统计成员入库、推荐、建联事件和 BD 历史跟进数量；不按个人职责展示进度或完成率。',
  emptyText = '暂无达人建联统计数据',
}: OutreachStatsTableProps) {
  const columns: Column<AnalyticsMemberRow>[] = [
    {
      key: 'member',
      header: '对接人',
      width: '150px',
      cell: (r) => <span className="text-xs font-medium text-gray-900">{memberLabel(r.member)}</span>,
    },
    { key: 'shop', header: 'Shop入库', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.tiktok_shop_processed)}</span> },
    { key: 'video', header: '视频入库', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.tiktok_video_processed)}</span> },
    { key: 'bd', header: 'BD入库', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.bd_processed)}</span> },
    { key: 'recommended', header: '推荐', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.recommended)}</span> },
    {
      key: 'total_contacted',
      header: '总建联',
      align: 'right',
      cell: (r) => <span className="text-xs font-semibold num text-gray-900">{countOf(r.total_contacted ?? r.sent)}</span>,
    },
    { key: 'confirmed', header: '已确认', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.confirmed)}</span> },
    { key: 'replied', header: '已回复', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.replied)}</span> },
    { key: 'sample_shipped', header: '已寄样', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.sample_shipped)}</span> },
    { key: 'video_published', header: '已发视频', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.video_published)}</span> },
    { key: 'partnered', header: '已合作', align: 'right', cell: (r) => <span className="text-xs num">{countOf(r.partnered)}</span> },
  ];

  return (
    <div className="card">
      <div className="px-4 pt-3 pb-2">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        <div className="text-xxs text-muted mt-0.5">{subtitle}</div>
      </div>
      <div className="px-2 pb-3">
        <DataTable
          columns={columns}
          data={rows}
          rowKey={(r) => r.member}
          emptyText={emptyText}
          compact
        />
      </div>
    </div>
  );
}
