import { Wallet, TrendingUp, ShoppingBag, Trophy } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useProducts, useCategories } from '@/hooks/useApi';
import { categoryNameMap, productsByCategory } from '@/lib/derive';
import { useMemo } from 'react';
import type { Product } from '@/api/types';

interface SkuRow extends Product {
  rank: number;
  categoryName: string;
}

export default function Revenue() {
  const products = useProducts({ limit: 200 });
  const categories = useCategories({ limit: 50 });

  const items = products.data?.items ?? [];
  const cats = categories.data?.items ?? [];
  const catMap = useMemo(() => categoryNameMap(cats), [cats]);

  const byCategory = productsByCategory(items, catMap);
  const mainPush = items.filter((p) => p.is_main_push === 1);
  const avgPrice = items.length > 0
    ? items.reduce((s, p) => s + (p.price_tiktok || 0), 0) / items.length
    : 0;
  const top1 = items.sort((a, b) => (b.price_tiktok || 0) - (a.price_tiktok || 0))[0];

  // Top 10 by price (proxy for revenue potential)
  const top10: SkuRow[] = items
    .filter((p) => p.price_tiktok !== null)
    .sort((a, b) => (b.price_tiktok || 0) - (a.price_tiktok || 0))
    .slice(0, 10)
    .map((p, i) => ({
      ...p,
      rank: i + 1,
      categoryName: (p.category_id && catMap[p.category_id]) || p.subcategory || '其他',
    }));

  const skuColumns: Column<SkuRow>[] = [
    {
      key: 'rank', header: '#', align: 'center',
      cell: (r) => (
        <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xxs font-bold ${
          r.rank <= 3 ? 'bg-amber-100 text-amber-700' : 'bg-soft text-muted'
        }`}>{r.rank}</span>
      ),
      width: '50px',
    },
    { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku_code}</span> },
    { key: 'name', header: '产品名称', cell: (r) => <span className="text-xs">{r.name_zh || r.name_en}</span> },
    { key: 'category', header: '类目', cell: (r) => <Pill tone="info">{r.categoryName}</Pill> },
    { key: 'price_tiktok', header: 'TikTok', align: 'right', cell: (r) => <span className="text-xs num">${r.price_tiktok?.toFixed(2)}</span> },
    { key: 'price_temu', header: 'Temu', align: 'right', cell: (r) => <span className="text-xs num text-muted">${r.price_temu?.toFixed(2) || '—'}</span> },
    { key: 'price_ebay', header: 'eBay', align: 'right', cell: (r) => <span className="text-xs num text-muted">${r.price_ebay?.toFixed(2) || '—'}</span> },
    { key: 'main', header: '主推', cell: (r) => r.is_main_push === 1 ? <Pill tone="bad">主推</Pill> : <span className="text-xxs text-muted">—</span> },
  ];

  // Category 柱图(按 SKU 数量)
  const catBarOption = {
    grid: { top: 20, right: 30, bottom: 30, left: 80, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f1f5', type: 'dashed' } } },
    yAxis: {
      type: 'category', data: byCategory.map((d) => d.name).reverse(),
      axisLine: { show: false }, axisTick: { show: false },
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    series: [{
      type: 'bar', data: byCategory.map((d) => d.value).reverse(),
      barWidth: 18,
      itemStyle: { color: '#3370ff', borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', fontSize: 11, color: '#4e5969', formatter: '{c} 个' },
    }],
  };

  return (
    <AsyncState loading={products.isLoading} error={products.error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="SKU 总数" value={products.data?.total ?? 0} icon={ShoppingBag} iconBg="#e0e7ff" iconColor="#4f46e5" />
          <KpiCard label="主推 SKU" value={mainPush.length} icon={Trophy} iconBg="#fee2e2" iconColor="#dc2626" />
          <KpiCard label="TikTok 平均价" value={`$${avgPrice.toFixed(2)}`} icon={Wallet} iconBg="#d1fae5" iconColor="#16a34a" />
          <KpiCard label="最高单价 SKU" value={`$${top1?.price_tiktok?.toFixed(2) || '—'}`} icon={TrendingUp} iconBg="#fed7aa" iconColor="#ea580c" />
        </div>

        <ChartCard title="类目 SKU 分布">
          <EChart option={catBarOption} height={280} />
        </ChartCard>

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">Top 10 SKU 按价格</h3>
            <div className="text-xxs text-muted mt-0.5">注:GMV 数据需 Postgres 看板,当前用 TikTok 单价排序</div>
          </div>
          <DataTable columns={skuColumns} data={top10} rowKey={(r) => r.id} />
        </div>
      </div>
    </AsyncState>
  );
}
