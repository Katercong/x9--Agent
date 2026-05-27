import { Trophy } from 'lucide-react';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { useAnalyticsCompany, useStaff } from '@/hooks/useApi';
import { staffStats } from '@/lib/derive';
import { chartPalette } from '@/lib/colors';

interface DeptRow {
  name: string;
  creators: number;
  outreach: number;
  videos: number;
  ad_running: number;
  conv: number;
}

export default function Departments() {
  const analytics = useAnalyticsCompany(30);
  const staffQ = useStaff({ limit: 10 });

  const loading = analytics.isLoading;
  const error = analytics.error;

  const staffList = staffQ.data?.items ?? [];

  const departments = (analytics.data?.departments ?? [])
    .map((row) => {
      const creators = Number(row.creators ?? row.recommended ?? row.assigned ?? 0);
      const outreach = Number(row.sent ?? 0) + Number(row.pending_reply ?? 0) + Number(row.replied ?? 0)
        + Number(row.sample_shipped ?? 0) + Number(row.sample_delivered ?? 0) + Number(row.partnered ?? 0)
        + Number(row.video_published ?? 0);
      const videos = Number(row.video_published ?? 0);
      const adRunning = Number(row.partnered ?? 0);
      return {
        name: row.department_code || row.member || '未分配',
        creators,
        outreach,
        videos,
        ad_running: adRunning,
        conv: creators > 0 ? +((videos / creators) * 100).toFixed(1) : 0,
      };
    })
    .filter((d) => d.creators >= 2 || d.outreach >= 2)
    .sort((a, b) => b.creators - a.creators);

  const maxVals = {
    creators: Math.max(1, ...departments.map((d) => d.creators)),
    outreach: Math.max(1, ...departments.map((d) => d.outreach)),
    videos: Math.max(1, ...departments.map((d) => d.videos)),
    ad_running: Math.max(1, ...departments.map((d) => d.ad_running)),
    conv: Math.max(1, ...departments.map((d) => d.conv)),
  };

  const radarMetrics = ['达人数', '建联事件', '视频数', '投放视频', '转化率'];

  const radarOption = {
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 10 } },
    tooltip: {},
    radar: {
      indicator: radarMetrics.map((name) => ({ name, max: 100 })),
      shape: 'polygon',
      splitArea: { areaStyle: { color: ['rgba(247,247,249,0.4)', 'rgba(247,247,249,0.8)'] } },
      axisName: { color: '#4e5969', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e5e6eb' } },
      axisLine: { lineStyle: { color: '#e5e6eb' } },
    },
    series: [{
      type: 'radar', symbol: 'circle', symbolSize: 4,
      data: departments.slice(0, 6).map((d, i) => ({
        name: d.name,
        value: [
          (d.creators / maxVals.creators) * 100,
          (d.outreach / maxVals.outreach) * 100,
          (d.videos / maxVals.videos) * 100,
          (d.ad_running / maxVals.ad_running) * 100,
          (d.conv / maxVals.conv) * 100,
        ],
        areaStyle: { opacity: 0.18, color: chartPalette.categorical[i] },
        lineStyle: { width: 2, color: chartPalette.categorical[i] },
        itemStyle: { color: chartPalette.categorical[i] },
      })),
    }],
  };

  const deptColumns: Column<DeptRow>[] = [
    {
      key: 'rank', header: '#', align: 'center',
      cell: (_, i) => (
        <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xxs font-bold ${
          i < 3 ? 'bg-amber-100 text-amber-700' : 'bg-soft text-muted'
        }`}>{i + 1}</span>
      ),
      width: '50px',
    },
    { key: 'name', header: '店铺/部门', cell: (r) => <span className="text-xs font-medium">{r.name}</span> },
    { key: 'creators', header: '达人', align: 'right', cell: (r) => <span className="text-xs num">{r.creators}</span> },
    {
      key: 'outreach', header: '建联事件', align: 'right',
      cell: (r) => (
        <div className="flex items-center justify-end gap-2">
          <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
            <div className="h-full bg-brand-500 rounded-full" style={{ width: `${(r.outreach / maxVals.outreach) * 100}%` }} />
          </div>
          <span className="text-xs num">{r.outreach}</span>
        </div>
      ),
    },
    { key: 'videos', header: '视频数', align: 'right', cell: (r) => <span className="text-xs num">{r.videos}</span> },
    { key: 'ad_running', header: '在投', align: 'right', cell: (r) => <span className="text-xs num">{r.ad_running}</span> },
    { key: 'conv', header: '转化率', align: 'right', cell: (r) => <span className={`text-xs num font-medium ${r.conv >= 30 ? 'text-good' : 'text-gray-700'}`}>{r.conv}%</span> },
  ];

  const bdRows = staffStats(staffList).sort((a, b) => b.contacted - a.contacted).slice(0, 5);

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <ChartCard title="部门多维绩效雷达 · Top 6" className="lg:col-span-2">
            <EChart option={radarOption} height={380} />
          </ChartCard>
          <div className="card">
            <div className="px-4 py-3 border-b border-line flex items-center gap-2">
              <Trophy size={16} className="text-amber-500" />
              <h3 className="text-sm font-semibold text-gray-800">Top BD 战绩</h3>
            </div>
            <div className="p-3 space-y-2">
              {bdRows.map((r, i) => (
                <div key={r.name} className="border border-line rounded p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium">{r.name}</span>
                    <span className={`pill ${i === 0 ? 'bg-amber-100 text-amber-700' : 'pill-muted'}`}>#{i + 1}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xxs">
                    <div><div className="text-muted">联系</div><div className="num font-semibold mt-0.5">{r.contacted}</div></div>
                    <div><div className="text-muted">确认</div><div className="num font-semibold mt-0.5">{r.confirmed}</div></div>
                    <div><div className="text-muted">寄样</div><div className="num font-semibold mt-0.5">{r.samples}</div></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">店铺绩效详表</h3>
            <div className="text-xxs text-muted mt-0.5">按 creator.store_assigned 聚合</div>
          </div>
          <DataTable columns={deptColumns} data={departments} rowKey={(r) => r.name} />
        </div>
      </div>
    </AsyncState>
  );
}
