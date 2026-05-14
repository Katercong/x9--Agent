import { Trophy, AlertTriangle, ShoppingBag } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { skuTreemap, topSkus } from '@/mock/company';
import { chartPalette } from '@/lib/colors';

const stockWarning = topSkus.slice(0, 6).map((s, i) => ({
  ...s,
  stock: 200 + i * 30 - (i === 2 || i === 4 ? 180 : 0),
  threshold: 100,
}));

type Warn = typeof stockWarning[number];

const stockColumns: Column<Warn>[] = [
  { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku}</span> },
  { key: 'name', header: '产品名称', cell: (r) => <span className="text-xs">{r.name}</span> },
  { key: 'stock', header: '当前库存', align: 'right', cell: (r) => <span className={`text-xs num font-medium ${r.stock < r.threshold ? 'text-bad' : 'text-gray-700'}`}>{r.stock}</span> },
  { key: 'threshold', header: '阈值', align: 'right', cell: (r) => <span className="text-xs num text-muted">{r.threshold}</span> },
  {
    key: 'status', header: '状态',
    cell: (r) => <Pill tone={r.stock < r.threshold ? 'bad' : 'good'}>{r.stock < r.threshold ? '预警' : '正常'}</Pill>,
  },
];

export default function Products() {
  const treemapOption = {
    tooltip: { formatter: (info: any) => `${info.name}<br/>营收: ¥${info.value}K` },
    series: [
      {
        type: 'treemap',
        roam: false,
        breadcrumb: { show: false },
        nodeClick: false,
        label: {
          show: true,
          formatter: '{b}',
          fontSize: 12,
        },
        upperLabel: {
          show: true,
          height: 24,
          color: '#1f2329',
          fontWeight: 600,
        },
        itemStyle: { gapWidth: 2, borderColor: '#fff', borderWidth: 1 },
        levels: [
          { itemStyle: { borderColor: '#fff', borderWidth: 4, gapWidth: 4 } },
          {
            colorSaturation: [0.35, 0.6],
            itemStyle: { borderColorSaturation: 0.6, gapWidth: 2 },
          },
        ],
        data: skuTreemap.map((cat, i) => ({
          name: cat.name,
          children: cat.children,
          itemStyle: { color: chartPalette.categorical[i] },
        })),
      },
    ],
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="总 SKU" value={44} delta={2} icon={ShoppingBag} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="主推 SKU" value={12} delta={20} icon={Trophy} iconBg="#fed7aa" iconColor="#ea580c" />
        <KpiCard label="头部贡献" value="68%" delta={4} icon={Trophy} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="库存预警" value={2} delta={100} icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
      </div>

      <ChartCard title="SKU 价值地图 · 按类目分组,大小=营收(千元)">
        <EChart option={treemapOption} height={400} />
      </ChartCard>

      <div className="card">
        <div className="px-4 py-3 border-b border-line flex items-center gap-2">
          <AlertTriangle size={16} className="text-bad" />
          <h3 className="text-sm font-semibold text-gray-800">库存预警明细</h3>
        </div>
        <DataTable columns={stockColumns} data={stockWarning} rowKey={(r) => r.sku} />
      </div>
    </div>
  );
}
