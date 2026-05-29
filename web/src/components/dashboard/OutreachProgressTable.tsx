import { DataTable, type Column } from '@/components/table/DataTable';
import type { AnalyticsMemberRow } from '@/api/types';

function countOf(value: unknown) {
  return Number(value ?? 0) || 0;
}

function memberLabel(value: string) {
  if (!value || value === 'unassigned') return '未分配';
  return value;
}

function ContactProgress({ value, max }: { value: number; max: number }) {
  const ratio = max > 0 ? value / max : 0;
  const pct = max > 0 ? Math.max(3, Math.min(100, Math.round(ratio * 100))) : 0;

  return (
    <div className="min-w-[150px]">
      <div className="mb-1 flex items-center justify-end gap-2">
        <span className="text-xs font-semibold num text-gray-900">{value}</span>
        <span className="text-[10px] text-muted">{max > 0 ? `${Math.round(ratio * 100)}%` : '0%'}</span>
      </div>
      <div className="h-1.5 rounded-full bg-blue-50">
        <div className="h-1.5 rounded-full bg-[#3370ff]" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

interface OutreachProgressTableProps {
  rows: AnalyticsMemberRow[];
  title?: string;
  subtitle?: string;
  emptyText?: string;
}

export function OutreachProgressTable({
  rows,
  title = '达人建联进度数据',
  subtitle = '合并成员入库、推荐、建联事件和 BD 历史跟进；总建联进度条按当前 Top 对接人相对占比展示。',
  emptyText = '暂无达人建联进度数据',
}: OutreachProgressTableProps) {
  const maxContacted = Math.max(0, ...rows.map((row) => countOf(row.total_contacted ?? row.sent)));
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
      header: '总建联进度',
      align: 'right',
      width: '190px',
      cell: (r) => <ContactProgress value={countOf(r.total_contacted ?? r.sent)} max={maxContacted} />,
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
