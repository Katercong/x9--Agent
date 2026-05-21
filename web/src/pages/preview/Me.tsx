// /preview/me — Personal workspace.
// What this BD needs to do today, sorted by urgency. Pulls /api/v2/me which
// scopes the existing creator+outreach data to the logged-in user via the
// same alias-matching logic auth_service uses.
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Loader2, AlertCircle, Clock, Package, Send, Mail, Trophy, Target } from 'lucide-react';
import { EChart } from '@/components/charts/EChart';
import { v2Api, type CreatorQueueItem } from '@/api/v2';
import { Pill } from '@/components/Pill';

const fmt = (n: number | null | undefined) => new Intl.NumberFormat('zh-CN').format(Number(n || 0));

export default function Me() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['v2', 'me'],
    queryFn: () => v2Api.me(),
    staleTime: 30_000,
  });

  const sparkOption = useMemo(() => {
    if (!data?.sparkline_7d) return { series: [] };
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['采集', '联系'], top: 0 },
      grid: { left: 30, right: 16, top: 28, bottom: 24 },
      xAxis: { type: 'category', data: data.sparkline_7d.map((p) => p.date.slice(5)), boundaryGap: false },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        { name: '采集', type: 'line', smooth: true, data: data.sparkline_7d.map((p) => p.collected) },
        { name: '联系', type: 'line', smooth: true, data: data.sparkline_7d.map((p) => p.contacted) },
      ],
    };
  }, [data]);

  const funnelOption = useMemo(() => {
    if (!data?.personal_funnel) return { series: [] };
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['我', '部门平均'], top: 0 },
      grid: { left: 30, right: 16, top: 28, bottom: 60 },
      xAxis: { type: 'category', data: data.personal_funnel.map((s) => s.label), axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: 'value' },
      series: [
        { name: '我', type: 'bar', data: data.personal_funnel.map((s) => s.mine) },
        { name: '部门平均', type: 'bar', data: data.personal_funnel.map((s) => Math.round(s.department / Math.max(1, data.personal_funnel.length))) },
      ],
    };
  }, [data]);

  if (isLoading) {
    return <div className="flex items-center gap-2 text-muted text-sm p-4"><Loader2 size={14} className="animate-spin" />加载工作台...</div>;
  }
  if (error || !data?.ok) {
    return <div className="card card-body text-bad text-sm">加载失败:{(error as Error)?.message || '未知'}</div>;
  }

  return (
    <div className="space-y-4">
      <PreviewBanner page={`${data.user.display_name} 的工作台`} />

      {/* Greeting + 4 KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiBlock icon={Send} bg="bg-emerald-50" color="text-emerald-700" label="本周已联系" value={data.weekly.contacted} subLabel={`管辖 ${fmt(data.owned_count)} 位达人`} />
        <KpiBlock icon={Package} bg="bg-amber-50" color="text-amber-700" label="本周寄样" value={data.weekly.sample_shipped} subLabel="样品已寄出" />
        <KpiBlock icon={Trophy} bg="bg-purple-50" color="text-purple-700" label="本周视频" value={data.weekly.video_published} subLabel="已发布" />
        <KpiBlock icon={Target} bg="bg-rose-50" color="text-rose-700" label="本周成交" value={data.weekly.deal_closed} subLabel="(占位)" />
      </div>

      {/* Three priority queues */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <QueueCard
          tone="red"
          icon={AlertCircle}
          title="🔴 今天必须联系"
          subtitle="推荐分高但从未联系"
          items={data.queues.must_today}
        />
        <QueueCard
          tone="yellow"
          icon={Clock}
          title="🟡 待跟进"
          subtitle="已联系 5+ 天无回复"
          items={data.queues.follow_up}
        />
        <QueueCard
          tone="green"
          icon={Package}
          title="🟢 物流登记"
          subtitle="样品已寄,待签收"
          items={data.queues.sample_log}
        />
      </div>

      {/* Trend + Funnel comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">近 7 天活动</h3>
          </div>
          <div className="p-3"><EChart option={sparkOption} height={240} /></div>
        </div>
        <div className="card">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">我 vs 部门平均 (各阶段达人)</h3>
          </div>
          <div className="p-3"><EChart option={funnelOption} height={240} /></div>
        </div>
      </div>
    </div>
  );
}

function KpiBlock({ icon: Icon, bg, color, label, value, subLabel }: any) {
  return (
    <div className="card card-body">
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-full ${bg} ${color} flex items-center justify-center`}>
          <Icon size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xxs text-muted">{label}</div>
          <div className="text-2xl font-bold num text-gray-900 leading-none mt-1">{fmt(value)}</div>
          <div className="text-xxs text-muted mt-1">{subLabel}</div>
        </div>
      </div>
    </div>
  );
}

function QueueCard({ tone, icon: Icon, title, subtitle, items }: { tone: 'red' | 'yellow' | 'green'; icon: any; title: string; subtitle: string; items: CreatorQueueItem[] }) {
  const headerBg = tone === 'red' ? 'bg-rose-50 border-rose-200' : tone === 'yellow' ? 'bg-amber-50 border-amber-200' : 'bg-emerald-50 border-emerald-200';
  return (
    <div className={`card border-2 ${headerBg}`}>
      <div className="px-4 py-3 border-b border-line">
        <div className="flex items-center gap-2">
          <Icon size={14} />
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
          <span className="ml-auto text-xs num font-bold">{items.length}</span>
        </div>
        <div className="text-xxs text-muted">{subtitle}</div>
      </div>
      <div className="divide-y divide-line max-h-96 overflow-y-auto">
        {items.length === 0 && <div className="text-xxs text-muted py-4 text-center">暂无</div>}
        {items.map((item, i) => (
          <Link
            key={i}
            to={`/preview/creators/${encodeURIComponent(item.platform)}/${encodeURIComponent(item.handle_key)}`}
            className="block px-3 py-2 hover:bg-gray-50"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium truncate">@{item.handle}</div>
                <div className="text-xxs text-muted truncate">{item.display_name || '—'} · {fmt(item.followers_count)} 粉</div>
              </div>
              <Pill tone="info">{item.recommendation_score}</Pill>
            </div>
            <div className="text-xxs text-muted mt-1 truncate">{item.reason}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function PreviewBanner({ page }: { page: string }) {
  return (
    <div className="card card-body bg-amber-50 border-amber-200 flex items-center gap-2 text-xs">
      <span className="px-2 py-0.5 rounded bg-amber-200 text-amber-900 font-semibold text-xxs">PREVIEW</span>
      <span className="text-amber-900">v2 看板 · {page}</span>
      <Link to="/preview/pulse" className="ml-auto chip text-xxs">看公司脉搏</Link>
      <Link to="/preview/creators" className="chip text-xxs">达人主表</Link>
    </div>
  );
}
