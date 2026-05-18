import { useMemo } from 'react';
import { Trophy, ShoppingBag, Star } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { useProducts, useCategories } from '@/hooks/useApi';
import { categoryNameMap } from '@/lib/derive';
import { chartPalette } from '@/lib/colors';

export default function Products() {
  const products = useProducts({ limit: 200 });
  const categories = useCategories({ limit: 50 });

  const items = products.data?.items ?? [];
  const cats = categories.data?.items ?? [];
  const catMap = useMemo(() => categoryNameMap(cats), [cats]);

  // 类目 -> 产品分组 → Treemap
  const treemap = cats.map((c, i) => {
    const children = items
      .filter((p) => p.category_id === c.id)
      .map((p) => ({ name: p.name_zh || p.name_en || p.sku_code, value: p.price_tiktok || 0 }));
    return {
      name: c.name_zh,
      itemStyle: { color: chartPalette.categorical[i] },
      children,
    };
  }).filter((c) => c.children.length > 0);

  const mainPush = items.filter((p) => p.is_main_push === 1);
  const totalValue = items.reduce((s, p) => s + (p.price_tiktok || 0), 0);
  const mainPushValue = mainPush.reduce((s, p) => s + (p.price_tiktok || 0), 0);
  const mainPushPct = totalValue > 0 ? ((mainPushValue / totalValue) * 100).toFixed(0) : '0';

  const treemapOption = {
    tooltip: { formatter: (info: any) => `${info.name}<br/>单价: $${info.value}` },
    series: [{
      type: 'treemap', roam: false, breadcrumb: { show: false }, nodeClick: false,
      label: { show: true, formatter: '{b}', fontSize: 12 },
      upperLabel: { show: true, height: 24, color: '#1f2329', fontWeight: 600 },
      itemStyle: { gapWidth: 2, borderColor: '#fff', borderWidth: 1 },
      levels: [
        { itemStyle: { borderColor: '#fff', borderWidth: 4, gapWidth: 4 } },
        { colorSaturation: [0.35, 0.6], itemStyle: { borderColorSaturation: 0.6, gapWidth: 2 } },
      ],
      data: treemap,
    }],
  };

  return (
    <AsyncState loading={products.isLoading} error={products.error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="总 SKU" value={products.data?.total ?? 0} icon={ShoppingBag} iconBg="#dbeafe" iconColor="#2563eb" />
          <KpiCard label="主推 SKU" value={mainPush.length} icon={Trophy} iconBg="#fed7aa" iconColor="#ea580c" />
          <KpiCard label="主推单价占比" value={`${mainPushPct}%`} icon={Star} iconBg="#fef3c7" iconColor="#ca8a04" />
          <KpiCard label="类目数" value={cats.length} icon={Star} iconBg="#d1fae5" iconColor="#16a34a" />
        </div>

        <ChartCard title="SKU 价值地图 · 按类目分组,大小=单价(USD)">
          <EChart option={treemapOption} height={420} />
        </ChartCard>
      </div>
    </AsyncState>
  );
}
