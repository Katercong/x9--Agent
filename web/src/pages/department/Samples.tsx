import { Package, Truck, AlertTriangle, CheckCircle2, Upload, Plus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { samples } from '@/mock/department';
import { formatDate } from '@/lib/format';

type Sample = typeof samples[number];

const columns: Column<Sample>[] = [
  { key: 'creator', header: '达人', cell: (r) => <span className="text-xs">@{r.creator}</span> },
  { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku}</span> },
  { key: 'qty', header: '数量', align: 'right', cell: (r) => <span className="text-xs num">{r.qty}</span> },
  { key: 'carrier', header: '承运商', cell: (r) => <span className="text-xs">{r.carrier}</span> },
  { key: 'trackNo', header: '运单号', cell: (r) => <span className="text-xs font-mono text-muted">{r.trackNo}</span> },
  { key: 'shippedAt', header: '寄出', cell: (r) => <span className="text-xs">{formatDate(r.shippedAt)}</span> },
  { key: 'estimatedAt', header: '预计签收', cell: (r) => <span className="text-xs text-muted">{formatDate(r.estimatedAt)}</span> },
  { key: 'deliveredAt', header: '实际签收', cell: (r) => <span className="text-xs">{r.deliveredAt ? formatDate(r.deliveredAt) : '—'}</span> },
  {
    key: 'delayDays', header: '延迟', align: 'right',
    cell: (r) => r.delayDays > 0 ? <span className="text-xs text-bad font-medium">{r.delayDays}d</span> : <span className="text-xs text-muted">—</span>,
  },
  {
    key: 'status', header: '状态',
    cell: (r) => {
      const toneMap: Record<string, 'good' | 'warn' | 'bad' | 'info'> = {
        '已签收': 'good', '在途': 'info', '延迟': 'bad',
      };
      return <Pill tone={toneMap[r.status] || 'muted'}>{r.status}</Pill>;
    },
  },
];

export default function Samples() {
  const pending = samples.filter((s) => s.status === '在途').length;
  const delivered = samples.filter((s) => s.status === '已签收').length;
  const delayed = samples.filter((s) => s.status === '延迟').length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="待寄送" value={2} delta={0} icon={Package} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="在途中" value={pending} delta={20} icon={Truck} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="延迟签收" value={delayed} delta={50} icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
        <KpiCard label="已签收" value={delivered} delta={33} icon={CheckCircle2} iconBg="#d1fae5" iconColor="#16a34a" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">物流明细</h3>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn"><Upload size={12} />导入物流</button>
            <button className="btn btn-primary"><Plus size={12} />登记寄样</button>
          </div>
        </div>
        <DataTable columns={columns} data={samples} rowKey={(r) => r.id} />
      </div>
    </div>
  );
}
