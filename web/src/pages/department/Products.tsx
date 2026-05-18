import { useState, useMemo } from 'react';
import { ShoppingBag, Star, BarChart3, Plus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useProducts, useCategories } from '@/hooks/useApi';
import { categoryNameMap } from '@/lib/derive';
import { cn } from '@/lib/cn';
import type { Product } from '@/api/types';

export default function Products() {
  const [categoryFilter, setCategoryFilter] = useState<number | null>(null);

  const products = useProducts({ limit: 200 });
  const categories = useCategories({ limit: 50 });

  const items = products.data?.items ?? [];
  const cats = categories.data?.items ?? [];
  const catMap = useMemo(() => categoryNameMap(cats), [cats]);

  const filtered = categoryFilter === null ? items : items.filter((p) => p.category_id === categoryFilter);
  const mainPush = items.filter((p) => p.is_main_push === 1).length;
  const avgPrice = items.length > 0
    ? items.reduce((s, p) => s + (p.price_tiktok || 0), 0) / items.length
    : 0;

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
    { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku_code}</span> },
    {
      key: 'name', header: '产品名称',
      cell: (r) => (
        <div className="min-w-0">
          <div className="text-xs font-medium truncate">{r.name_zh || r.name_en || r.sku_code}</div>
          {r.name_en && r.name_zh && <div className="text-xxs text-muted truncate">{r.name_en}</div>}
        </div>
      ),
    },
    {
      key: 'category', header: '类目',
      cell: (r) => <Pill tone="info">{(r.category_id && catMap[r.category_id]) || r.subcategory || '—'}</Pill>,
    },
    {
      key: 'price', header: 'TikTok 价', align: 'right',
      cell: (r) => (
        <div className="flex items-center justify-end gap-2">
          <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
            <div className="h-full bg-brand-500 rounded-full" style={{ width: `${Math.min((r.price_tiktok || 0) * 3, 100)}%` }} />
          </div>
          <span className="text-xs num">${r.price_tiktok?.toFixed(2) || '—'}</span>
        </div>
      ),
    },
    {
      key: 'main', header: '主推',
      cell: (r) => r.is_main_push === 1
        ? <span className="pill bg-red-50 text-red-700 font-medium"><Star size={10} className="inline mr-0.5" />主推</span>
        : <Pill tone="muted">正常</Pill>,
    },
    { key: 'tier', header: '分级', cell: (r) => <span className="text-xs">{r.tier || '—'}</span> },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="部门 SKU" value={items.length} icon={ShoppingBag} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="主推数" value={mainPush} icon={Star} iconBg="#fee2e2" iconColor="#dc2626" />
        <KpiCard label="平均 TikTok 价" value={`$${avgPrice.toFixed(2)}`} icon={BarChart3} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="类目数" value={cats.length} icon={Star} iconBg="#fef3c7" iconColor="#ca8a04" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <div className="card lg:col-span-1">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">类目</h3>
          </div>
          <div className="p-2">
            <button
              onClick={() => setCategoryFilter(null)}
              className={cn(
                'w-full text-left px-3 py-2 rounded text-xs transition-colors mb-0.5',
                categoryFilter === null ? 'bg-brand-50 text-brand-700 font-medium' : 'text-gray-700 hover:bg-soft',
              )}
            >
              全部 ({items.length})
            </button>
            {cats.map((c) => {
              const count = items.filter((p) => p.category_id === c.id).length;
              return (
                <button
                  key={c.id}
                  onClick={() => setCategoryFilter(c.id)}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded text-xs transition-colors mb-0.5',
                    categoryFilter === c.id ? 'bg-brand-50 text-brand-700 font-medium' : 'text-gray-700 hover:bg-soft',
                  )}
                >
                  {c.name_zh} ({count})
                </button>
              );
            })}
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
          <AsyncState loading={products.isLoading} error={products.error} isEmpty={filtered.length === 0} height={300}>
            <DataTable columns={columns} data={filtered} rowKey={(r) => r.id} />
          </AsyncState>
        </div>
      </div>
    </div>
  );
}
