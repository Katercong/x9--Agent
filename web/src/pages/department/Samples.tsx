import { Package, Truck, AlertTriangle, CheckCircle2, Upload, Plus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useOutreach } from '@/hooks/useApi';
import { formatDate } from '@/lib/format';
import type { Outreach } from '@/api/types';

const columns: Column<Outreach>[] = [
  { key: 'creator', header: '达人 ID', cell: (r) => <span className="text-xs font-mono">#{r.creator_id}</span> },
  { key: 'store', header: '店铺', cell: (r) => <span className="text-xs">{r.store_name || '—'}</span> },
  { key: 'bd', header: 'BD', cell: (r) => <span className="text-xs">{r.bd_owner || '—'}</span> },
  { key: 'qty', header: '数量', align: 'right', cell: (r) => <span className="text-xs num">{r.sample_qty ?? '—'}</span> },
  { key: 'channel', header: '渠道', cell: (r) => <span className="text-xs">{r.channel || '—'}</span> },
  { key: 'date', header: '日期', cell: (r) => <span className="text-xs">{formatDate(r.event_date || r.created_at)}</span> },
  {
    key: 'status', header: '状态',
    cell: (r) => {
      const toneMap: Record<string, 'good' | 'warn' | 'bad' | 'info' | 'muted'> = {
        sample_shipped: 'info',
        sample_delivered: 'good',
        dropped: 'bad',
      };
      return <Pill tone={toneMap[r.status || ''] || 'muted'}>{r.status || '—'}</Pill>;
    },
  },
  { key: 'remark', header: '备注', cell: (r) => <span className="text-xs text-muted truncate max-w-[200px] block">{r.remark || '—'}</span> },
];

export default function Samples() {
  // 拉全量再前端聚合(SQLite 数据量小,够用)
  const { data, isLoading, error } = useOutreach({ limit: 500, order_by: 'event_date:desc' });
  const all = data?.items ?? [];

  // 与样品相关的事件
  const sampleEvents = all.filter((o) =>
    o.action === 'sample_shipped' ||
    o.status === 'sample_shipped' ||
    o.status === 'sample_delivered',
  );

  const shipped = sampleEvents.filter((o) => o.status === 'sample_shipped').length;
  const delivered = sampleEvents.filter((o) => o.status === 'sample_delivered').length;
  const pending = sampleEvents.length - shipped - delivered;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="样品事件" value={sampleEvents.length} icon={Package} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="在途" value={shipped} icon={Truck} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="已签收" value={delivered} icon={CheckCircle2} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="其他状态" value={pending} icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">样品事件流水</h3>
          <span className="text-xxs text-muted">数据源:outreach (action / status 含 sample)</span>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn"><Upload size={12} />导入物流</button>
            <button className="btn btn-primary"><Plus size={12} />登记寄样</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={sampleEvents.length === 0} height={300}>
          <DataTable columns={columns} data={sampleEvents} rowKey={(r) => r.id} />
        </AsyncState>
      </div>
    </div>
  );
}
