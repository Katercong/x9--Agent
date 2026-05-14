import { ShoppingBag, Star, BarChart3, Plus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill, TierPill } from '@/components/Pill';
import { products } from '@/mock/department';

type Product = typeof products[number];

const categories = ['全部', '女性护理', '母婴', '家居护理', '成人护理', '宠物用品'];

const columns: Column<Product>[] = [
  {
    key: 'image', header: '',
    cell: () => (
      <div className="w-9 h-9 rounded bg-gradient-to-br from-brand-50 to-brand-100 flex items-center justify-center">
        <ShoppingBag size={16} className="text-brand-500" />
      </div>
    ),
    width: '50px',
  },
  { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku}</span> },
  { key: 'name', header: '产品名称', cell: (r) => <span className="text-xs font-medium">{r.name}</span> },
  { key: 'category', header: '类目', cell: (r) => <Pill tone="info">{r.category}</Pill> },
  {
    key: 'price', header: '美区价格', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full bg-brand-500 rounded-full" style={{ width: `${Math.min(r.priceUsd * 5, 100)}%` }} />
        </div>
        <span className="text-xs num">${r.priceUsd}</span>
      </div>
    ),
  },
  {
    key: 'status', header: '主推',
    cell: (r) => (
      r.status === '主推'
        ? <span className="pill bg-red-50 text-red-700 font-medium"><Star size={10} className="inline mr-0.5" />主推</span>
        : <Pill tone="muted">正常</Pill>
    ),
  },
  { key: 'match', header: '匹配等级', cell: (r) => <TierPill tier={r.match} /> },
];

export default function Products() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="部门 SKU" value={products.length} delta={0} icon={ShoppingBag} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="主推数" value={products.filter((p) => p.status === '主推').length} delta={0} icon={Star} iconBg="#fee2e2" iconColor="#dc2626" />
        <KpiCard label="平均价" value="$11" delta={5} icon={BarChart3} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="高匹配 SKU" value={products.filter((p) => p.match === 'A').length} delta={0} icon={Star} iconBg="#fef3c7" iconColor="#ca8a04" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <div className="card lg:col-span-1">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">类目</h3>
          </div>
          <div className="p-2">
            {categories.map((c, i) => (
              <button
                key={c}
                className={`w-full text-left px-3 py-2 rounded text-xs transition-colors mb-0.5 ${
                  i === 0 ? 'bg-brand-50 text-brand-700 font-medium' : 'text-gray-700 hover:bg-soft'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <div className="card lg:col-span-4">
          <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">SKU 列表</h3>
            <div className="ml-auto flex items-center gap-2">
              <button className="btn">批量主推</button>
              <button className="btn btn-primary"><Plus size={12} />新增 SKU</button>
            </div>
          </div>
          <DataTable columns={columns} data={products} rowKey={(r) => r.sku} />
        </div>
      </div>
    </div>
  );
}
