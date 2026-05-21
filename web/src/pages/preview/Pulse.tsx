// /preview/pulse — Company pulse page.
// One screen: 3 north-star KPIs + main pipeline funnel + per-department
// sparklines + alert rail. Hits /api/v2/pulse which aggregates across all
// three creator tables (no data is duplicated — see services/v2_service.py).
import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, AlertTriangle, Activity, Users, Mail, Database, ArrowRight } from 'lucide-react';
import { EChart } from '@/components/charts/EChart';
import { v2Api, type RangeKey } from '@/api/v2';

const fmt = (n: number | null | undefined) => new Intl.NumberFormat('zh-CN').format(Number(n || 0));
const RANGE_LABEL: Record<RangeKey, string> = { today: '今日', week: '本周', month: '本月' };
const HEALTH_BG: Record<string, string> = { green: 'bg-emerald-500', yellow: 'bg-amber-500', red: 'bg-rose-500', grey: 'bg-gray-300' };

export default function Pulse() {
  const [range, setRange] = useState<RangeKey>('week');
  const { data, isLoading, error } = useQuery({
    queryKey: ['v2', 'pulse', range],
    queryFn: () => v2Api.pulse(range),
    staleTime: 30_000,
  });

  // Funnel chart option
  const funnelOption = useMemo(() => {
    if (!data?.funnel) return { series: [] };
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c}' },
      series: [{
        type: 'funnel',
        left: '8%', right: '8%', top: 10, bottom: 10,
        minSize: '15%', maxSize: '100%',
        sort: 'descending', gap: 3,
        label: { show: true, position: 'inside', formatter: '{b}\n{c}' },
        labelLine: { show: false },
        data: data.funnel.map((f) => ({ name: f.label, value: f.count })),
      }],
    };
  }, [data]);

  if (isLoading) return <PageSkeleton />;
  if (error) return <div className="card card-body text-bad text-sm">加载失败:{(error as Error).message}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <PreviewBanner page="公司脉搏" />

      {/* Range selector */}
      <div className="flex items-center gap-2">
        {(['today', 'week', 'month'] as RangeKey[]).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={'chip text-xs ' + (range === r ? 'bg-brand-100 text-brand-700' : '')}
          >
            {RANGE_LABEL[r]}
          </button>
        ))}
        <span className="ml-auto text-xxs text-muted">
          数据生成于 {new Date(data.generated_at).toLocaleTimeString('zh-CN')}
        </span>
      </div>

      {/* North-star KPIs (3 big cards) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {data.north_star.map((kpi) => (
          <NorthStarCard key={kpi.key} kpi={kpi} />
        ))}
      </div>

      {/* Funnel + Alerts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="card lg:col-span-2">
          <div className="px-4 py-3 border-b border-line flex items-center gap-2">
            <Activity size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">主链路转化漏斗</h3>
            <span className="text-xxs text-muted">采集 → 联系 → 确认 → 寄样 → 视频 → 广告授权</span>
          </div>
          <div className="p-3">
            <EChart option={funnelOption} height={340} />
          </div>
        </div>
        <AlertsCard alerts={data.alerts} />
      </div>

      {/* Department breakdown */}
      <div className="card">
        <div className="px-4 py-3 border-b border-line flex items-center gap-2">
          <Users size={16} className="text-muted" />
          <h3 className="text-sm font-semibold text-gray-800">分部门概览</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="table-x9">
            <thead>
              <tr>
                <th>部门</th>
                <th className="!text-right">达人数</th>
                <th className="!text-right">今日采集</th>
                <th className="!text-right">已建联</th>
                <th className="!text-right">视频已发</th>
                <th>近 7 天</th>
                <th className="!text-center">健康度</th>
              </tr>
            </thead>
            <tbody>
              {data.departments.map((d) => (
                <tr key={d.department_code}>
                  <td className="text-xs font-medium">{d.department_code || '未分配'}</td>
                  <td className="text-xs num text-right">{fmt(d.creator_count)}</td>
                  <td className="text-xs num text-right">{fmt(d.today_collected)}</td>
                  <td className="text-xs num text-right">{fmt(d.contacted)}</td>
                  <td className="text-xs num text-right">{fmt(d.video_published)}</td>
                  <td><Sparkline values={d.by_day_7} /></td>
                  <td className="text-center">
                    <span className={`inline-block w-2.5 h-2.5 rounded-full ${HEALTH_BG[d.health] || 'bg-gray-300'}`} title={d.health} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function NorthStarCard({ kpi }: { kpi: { label: string; value: number; delta_pct: number | null; compare_label: string } }) {
  const up = (kpi.delta_pct ?? 0) > 0;
  const down = (kpi.delta_pct ?? 0) < 0;
  return (
    <div className="card card-body">
      <div className="text-xs text-muted">{kpi.label}</div>
      <div className="text-4xl font-bold num text-gray-900 mt-2 leading-none">{fmt(kpi.value)}</div>
      <div className="mt-2 flex items-center gap-1.5 text-xxs">
        {kpi.delta_pct === null ? (
          <span className="text-muted">{kpi.compare_label}</span>
        ) : (
          <>
            {up && <TrendingUp size={11} className="text-emerald-600" />}
            {down && <TrendingDown size={11} className="text-rose-600" />}
            <span className={up ? 'text-emerald-600 font-semibold' : down ? 'text-rose-600 font-semibold' : 'text-muted'}>
              {kpi.delta_pct > 0 ? '+' : ''}{kpi.delta_pct}%
            </span>
            <span className="text-muted">{kpi.compare_label}</span>
          </>
        )}
      </div>
    </div>
  );
}

function AlertsCard({ alerts }: { alerts: any[] }) {
  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-line flex items-center gap-2">
        <AlertTriangle size={16} className="text-amber-600" />
        <h3 className="text-sm font-semibold text-gray-800">告警 ({alerts.length})</h3>
      </div>
      <div className="p-2">
        {alerts.length === 0 && <div className="text-xxs text-muted py-3 text-center">一切正常 ✓</div>}
        {alerts.map((a, i) => (
          <Link key={i} to={a.action} className="flex items-center gap-2 px-2 py-2 rounded hover:bg-gray-50">
            <span className={`inline-block w-2 h-2 rounded-full ${a.severity === 'red' ? 'bg-rose-500' : a.severity === 'yellow' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
            <span className="text-xs flex-1">{a.label}</span>
            <span className="text-xs font-semibold num">{a.count}</span>
            <ArrowRight size={12} className="text-muted" />
          </Link>
        ))}
      </div>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex items-end gap-0.5 h-6">
      {values.map((v, i) => (
        <div
          key={i}
          className="bg-brand-300 rounded-sm w-2"
          style={{ height: `${(v / max) * 100}%`, minHeight: 2 }}
          title={`${v}`}
        />
      ))}
    </div>
  );
}

function PreviewBanner({ page }: { page: string }) {
  return (
    <div className="card card-body bg-amber-50 border-amber-200 flex items-center gap-2 text-xs">
      <span className="px-2 py-0.5 rounded bg-amber-200 text-amber-900 font-semibold text-xxs">PREVIEW</span>
      <span className="text-amber-900">这是新看板 v2 的预览版本 — {page}。数据从生产库实时读取,不影响旧页面。</span>
      <Link to="/" className="ml-auto chip text-xxs">返回旧版</Link>
    </div>
  );
}

function PageSkeleton() {
  return <div className="text-muted text-sm p-4">加载中...</div>;
}
