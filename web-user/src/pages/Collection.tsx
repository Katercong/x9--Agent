import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  AtSign,
  CalendarDays,
  CheckCircle2,
  Chrome,
  Clock,
  FileSpreadsheet,
  Link2,
  Mail,
  Radar,
  RefreshCw,
  Radio,
  ScanLine,
  Store,
  Users,
  XCircle,
  AlertOctagon,
  type LucideIcon,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { AsyncState } from '@/components/states/States';
import { Pill } from '@/components/Pill';
import { useExtensionSessions, useRunProgress, useRecentObservations, usePostExtensionCommand } from '@/hooks/useApi';
import { shortRelative } from '@/lib/format';
import { useQueryClient } from '@tanstack/react-query';
import {
  useObservationsFeed,
  useSourceStats,
  type ObservationItem,
  type SourceBucket,
} from '@/api/collector';
import { ACCENTS, dailyAreaOption, num, type Accent } from './collectShared';

function pickLatestProgress(data: any, preferredWorkerId?: string | null) {
  if (!data) return {};
  const rows = data.progress
    ? [data.progress]
    : Array.isArray(data.items)
      ? data.items
      : [];
  if (rows.length === 0) return data;
  const preferred = preferredWorkerId
    ? rows.find((item: any) => item?.worker_id === preferredWorkerId)
    : null;
  const running = rows.find((item: any) => item?.running);
  if (preferred && (preferred.running || !running)) return preferred;
  if (running) return running;
  return [...rows].sort((a: any, b: any) => {
    const runningDelta = Number(Boolean(b?.running)) - Number(Boolean(a?.running));
    if (runningDelta) return runningDelta;
    return String(b?.updated_at || b?.started_at || '').localeCompare(String(a?.updated_at || a?.started_at || ''));
  })[0] || {};
}

export default function Collection() {
  const sessQ = useExtensionSessions();
  const progressQ = useRunProgress();
  const statsQ = useSourceStats();
  const shopFeedQ = useObservationsFeed({ source: 'tiktok_shop', limit: 8 });
  const leadsFeedQ = useObservationsFeed({ source: 'x9_leads', limit: 8 });
  const importFeedQ = useObservationsFeed({ source: 'table_import', limit: 8 });
  const obsQ = useRecentObservations(30);
  const cancelCmd = usePostExtensionCommand();
  const qc = useQueryClient();

  const sessions = sessQ.data?.sessions ?? [];
  const onlineCount = sessions.filter((s: any) => s.online).length;
  const activeSession = sessions.find((s: any) => s.online) || sessions[0] || null;
  const p: any = pickLatestProgress(progressQ.data, activeSession?.worker_id);
  const recentCount = obsQ.data?.items?.length ?? 0;

  const done = p.done ?? p.profiles_visited ?? 0;
  const total = p.total ?? (done + (p.profiles_remaining ?? 0));
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const running = p.running ?? false;

  const onCancel = () => {
    cancelCmd.mutate(
      { command_type: 'cancel_collection', worker_id: activeSession?.worker_id || undefined },
      { onSuccess: () => qc.invalidateQueries({ queryKey: ['run-progress'] }) },
    );
  };

  return (
    <AsyncState loading={sessQ.isLoading} error={sessQ.error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard
            label="插件在线"
            value={onlineCount > 0 ? `${onlineCount}` : '离线'}
            icon={Chrome}
            iconBg={onlineCount > 0 ? 'rgb(34 197 94 / 0.18)' : 'rgb(134 145 162 / 0.18)'}
            iconColor={onlineCount > 0 ? '#22c55e' : '#8691a2'}
            subLabel={activeSession?.last_heartbeat_at ? `心跳:${shortRelative(activeSession.last_heartbeat_at)}` : '无心跳'}
          />
          <KpiCard
            label="TikTok 登录"
            value={sessions.some((s: any) => s.tiktok_login_status === 'logged_in') ? '已登录' : '未登录'}
            icon={AtSign}
            iconBg={sessions.some((s: any) => s.tiktok_login_status === 'logged_in') ? 'rgb(34 197 94 / 0.18)' : 'rgb(245 158 11 / 0.18)'}
            iconColor={sessions.some((s: any) => s.tiktok_login_status === 'logged_in') ? '#22c55e' : '#fbbf24'}
          />
          <KpiCard
            label="当前任务"
            value={running ? '运行中' : '空闲'}
            icon={Radio}
            iconBg={running ? 'rgb(6 182 212 / 0.18)' : 'rgb(134 145 162 / 0.18)'}
            iconColor={running ? '#22d3ee' : '#8691a2'}
            subLabel={p.keyword ? `关键词:${p.keyword}` : p.current_action || '等待下发任务'}
          />
          <KpiCard
            label="最近心跳"
            value={activeSession?.last_heartbeat_at ? shortRelative(activeSession.last_heartbeat_at) : '无心跳'}
            icon={Clock}
            iconBg="rgb(99 102 241 / 0.16)"
            iconColor="#818cf8"
            subLabel={activeSession?.page_type || '插件会话状态'}
          />
        </div>

        <section>
          <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="sec-title !mb-0">达人数据采集总览</h3>
            <span className="text-xxs text-muted">插件状态、任务进度与三类采集渠道统一管理，10 秒自动刷新</span>
          </div>
          <AsyncState
            loading={statsQ.isLoading || shopFeedQ.isLoading || leadsFeedQ.isLoading || importFeedQ.isLoading}
            error={statsQ.error || shopFeedQ.error || leadsFeedQ.error || importFeedQ.error}
            height={360}
          >
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
              <ChannelMonitor
                icon={Store}
                accent={ACCENTS.shop}
                title="TikTok Shop 采集"
                subtitle="affiliate-us 达人列表与详情采集"
                to="/collect-shop"
                bucket={statsQ.data?.sources?.tiktok_shop}
                items={shopFeedQ.data?.items ?? []}
                metrics={shopMetrics(statsQ.data?.sources?.tiktok_shop, shopFeedQ.data?.items ?? [])}
              />
              <ChannelMonitor
                icon={Radar}
                accent={ACCENTS.leads}
                title="X9 线索采集"
                subtitle="www.tiktok.com 卡片流与可联系线索"
                to="/collect-leads"
                bucket={statsQ.data?.sources?.x9_leads}
                items={leadsFeedQ.data?.items ?? []}
                metrics={leadsMetrics(leadsFeedQ.data?.items ?? [])}
              />
              <ChannelMonitor
                icon={FileSpreadsheet}
                accent={ACCENTS.import}
                title="表格导入"
                subtitle="CSV / XLSX 批量导入与结构化入库"
                to="/collect-import"
                bucket={statsQ.data?.sources?.table_import}
                items={importFeedQ.data?.items ?? []}
                metrics={importMetrics(importFeedQ.data?.items ?? [])}
              />
            </div>
          </AsyncState>
        </section>

        {/* 流程进度 + 控制 */}
        <div className="card card-body">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">实时进度</h3>
            <div className="flex items-center gap-2">
              {running && (
                <button onClick={onCancel} disabled={cancelCmd.isPending} className="btn">
                  <XCircle size={12} className="text-bad" />取消
                </button>
              )}
            </div>
          </div>
          {total > 0 ? (
            <div>
              <div className="flex items-center justify-between text-xs text-muted mb-2">
                <span>
                  {p.keyword ? `当前关键词: ${p.keyword}` : '进行中'}
                  {p.step && <span className="ml-2 text-xxs">· step={p.step}</span>}
                </span>
                <span className="num">{done} / {total} ({pct}%)</span>
              </div>
              <div className="h-2 rounded-pill overflow-hidden" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                <div className="h-full rounded-pill transition-all" style={{ width: `${pct}%`, background: 'rgb(var(--accent))' }} />
              </div>
              <div className="grid grid-cols-3 gap-3 mt-3 text-xxs text-muted">
                <div>
                  <div>已采集</div><div className="text-text text-sm num font-semibold">{p.profiles_visited ?? done}</div>
                </div>
                <div>
                  <div>待处理</div><div className="text-text text-sm num font-semibold">{p.profiles_remaining ?? Math.max(0, total - done)}</div>
                </div>
                <div>
                  <div>入库 leads</div><div className="text-text text-sm num font-semibold">{p.leads_saved ?? 0}</div>
                </div>
              </div>
              {p.current_action && (
                <div className="text-xxs text-muted mt-2">当前动作:{p.current_action} {p.current_handle && `→ @${p.current_handle}`}</div>
              )}
              {p.last_error && (
                <div className="text-xxs text-bad mt-2 flex items-center gap-1"><AlertOctagon size={11} />{p.last_error}</div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-3 text-xs text-muted">
              <RefreshCw size={14} className="animate-spin opacity-50" />
              当前无进行中的采集任务,使用上方"下发采集任务"启动。
            </div>
          )}
        </div>

        <div className="card card-body">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <CheckCircle2 size={16} className={recentCount > 0 ? 'text-good' : 'text-muted'} />
              <div>
                <h3 className="text-sm font-semibold">全渠道观察流</h3>
                <div className="text-xxs text-muted">最近缓存 {recentCount} 条，用于判断插件是否持续回传。</div>
              </div>
            </div>
            <Pill tone={recentCount > 0 ? 'good' : 'muted'}>{recentCount > 0 ? '有回传' : '暂无回传'}</Pill>
          </div>
        </div>

        {/* 会话详情 */}
        {sessions.length > 0 && (
          <ChartCard title="插件会话">
            <div className="space-y-2 px-2 pb-2">
              {sessions.map((s: any) => (
                <div key={s.session_id} className="border border-border rounded p-3" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono">{s.worker_id || s.session_id}</span>
                    <Pill tone={s.online ? 'good' : 'muted'}>{s.online ? '在线' : '离线'}</Pill>
                  </div>
                  <div className="text-xxs text-muted">心跳:{shortRelative(s.last_heartbeat_at)} · {s.page_type || '未知页面'} · TT={s.tiktok_login_status || '?'}</div>
                  {s.current_url && (
                    <div className="text-xxs text-muted truncate mt-0.5">{s.current_url}</div>
                  )}
                </div>
              ))}
            </div>
          </ChartCard>
        )}
      </div>
    </AsyncState>
  );
}

type ChannelMetric = {
  label: string;
  value: string;
  icon: LucideIcon;
  detail?: string;
};

function ChannelMonitor({
  icon: Icon,
  accent,
  title,
  subtitle,
  to,
  bucket,
  items,
  metrics,
}: {
  icon: LucideIcon;
  accent: Accent;
  title: string;
  subtitle: string;
  to: string;
  bucket?: SourceBucket;
  items: ObservationItem[];
  metrics: ChannelMetric[];
}) {
  const total = bucket?.total ?? items.length;
  const today = bucket?.today ?? 0;
  const dailyTotal = sumDaily(bucket);
  const active = today > 0 || items.length > 0;

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="w-10 h-10 rounded-md flex items-center justify-center shrink-0"
              style={{ background: accent.dim, color: accent.key }}
            >
              <Icon size={19} />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-text truncate">{title}</h4>
              <div className="text-xxs text-muted truncate">{subtitle}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Pill tone={active ? 'good' : 'muted'}>{active ? '有数据' : '等待数据'}</Pill>
            <Link to={to} className="chip text-xxs">
              详情 <ArrowUpRight size={11} />
            </Link>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <ChannelMetricTile label="总回传" value={num(total)} icon={Users} accent={accent} />
          <ChannelMetricTile label="今日回传" value={num(today)} icon={CalendarDays} accent={accent} />
          <ChannelMetricTile label="近 7 天" value={num(dailyTotal)} icon={Radio} accent={accent} />
          {metrics.slice(0, 1).map((metric) => (
            <ChannelMetricTile key={metric.label} {...metric} accent={accent} />
          ))}
        </div>

        {metrics.length > 1 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {metrics.slice(1).map((metric) => (
              <div
                key={metric.label}
                className="rounded-md border border-border px-3 py-2"
                style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}
              >
                <div className="flex items-center gap-2 text-xxs text-muted">
                  <metric.icon size={13} />
                  {metric.label}
                </div>
                <div className="text-sm font-semibold num mt-1">{metric.value}</div>
                {metric.detail && <div className="text-xxs text-muted mt-0.5 truncate">{metric.detail}</div>}
              </div>
            ))}
          </div>
        )}

        <div className="rounded-md border border-border" style={{ background: 'rgb(var(--bg-elev-2) / 0.3)' }}>
          <EChart option={dailyAreaOption(bucket?.daily ?? [], accent.key)} height={154} />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <h5 className="text-xs font-semibold">最近入库</h5>
            <span className="text-xxs text-muted">{items.length} 条缓存</span>
          </div>
          {items.length === 0 ? (
            <div className="text-xs text-muted text-center py-6 border border-dashed border-border rounded">
              暂无该渠道采集记录
            </div>
          ) : (
            <div className="space-y-2">
              {items.slice(0, 4).map((item) => (
                <ChannelObservationRow key={item.id} item={item} accent={accent} />
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="h-1" style={{ background: accent.key }} />
    </div>
  );
}

function ChannelMetricTile({
  label,
  value,
  icon: Icon,
  accent,
  detail,
}: ChannelMetric & { accent: Accent }) {
  return (
    <div className="rounded-md border border-border px-3 py-2" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="flex items-center gap-2 text-xxs text-muted">
        <Icon size={13} style={{ color: accent.key }} />
        {label}
      </div>
      <div className="text-base font-semibold num mt-1">{value}</div>
      {detail && <div className="text-xxs text-muted mt-0.5 truncate">{detail}</div>}
    </div>
  );
}

function ChannelObservationRow({ item, accent }: { item: ObservationItem; accent: Accent }) {
  const isShop = item.source === 'tiktok_shop';
  const isImport = item.source === 'table_import';
  const status = isImport
    ? '表格导入'
    : isShop
    ? item.shop?.lead_status === 'shop_profile_collected'
      ? '详情已采'
      : '列表发现'
    : item.lead?.email
      ? '有邮箱'
      : (item.lead?.external_links?.length ?? 0) > 0
        ? '有外链'
        : '待补充';
  const detail = isImport
    ? [item.import_meta?.country, item.import_meta?.tier, item.import_meta?.email].filter(Boolean).join(' · ') || item.search_keyword || '表格导入'
    : isShop
    ? item.shop?.gmv_raw || item.shop?.category_text || item.search_keyword || 'TikTok Shop'
    : item.lead?.email || item.search_keyword || item.lead?.source_video_url || 'X9 线索';

  return (
    <div
      className="flex items-center gap-3 rounded-md border border-border px-3 py-2"
      style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}
    >
      <div
        className="w-8 h-8 rounded-md flex items-center justify-center text-white text-xs font-semibold shrink-0"
        style={{ background: accent.key }}
      >
        {(item.handle || '?').slice(0, 1).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs text-text truncate">@{item.handle || 'unknown'}</div>
        <div className="text-xxs text-muted truncate">{detail}</div>
      </div>
      <div className="text-right shrink-0">
        <Pill tone={status === '待补充' ? 'muted' : 'info'}>{status}</Pill>
        <div className="text-xxs text-muted mt-1">{shortRelative(item.collected_at || item.created_at)}</div>
      </div>
    </div>
  );
}

function sumDaily(bucket?: SourceBucket) {
  return (bucket?.daily ?? []).reduce((sum, row) => sum + (Number(row.count) || 0), 0);
}

function shopMetrics(bucket: SourceBucket | undefined, items: ObservationItem[]): ChannelMetric[] {
  const detailCount = bucket?.funnel?.shop_profile_collected
    ?? items.filter((item) => item.shop?.lead_status === 'shop_profile_collected').length;
  const listCount = bucket?.funnel?.shop_list_seen
    ?? items.filter((item) => item.shop?.lead_status === 'shop_list_seen').length;
  return [
    { label: '详情已采', value: num(detailCount), icon: ScanLine, detail: '从列表进入详情页' },
    { label: '列表发现', value: num(listCount), icon: Store, detail: 'TikTok Shop 列表记录' },
    { label: '含 GMV', value: num(items.filter((item) => item.shop?.gmv_raw).length), icon: CheckCircle2, detail: '最近缓存样本' },
  ];
}

function leadsMetrics(items: ObservationItem[]): ChannelMetric[] {
  const withEmail = items.filter((item) => item.lead?.email).length;
  const withLinks = items.filter((item) => (item.lead?.external_links?.length ?? 0) > 0).length;
  return [
    { label: '有邮箱', value: num(withEmail), icon: Mail, detail: '最近缓存样本' },
    { label: '有外链', value: num(withLinks), icon: Link2, detail: 'Instagram / Linktree 等' },
  ];
}

function importMetrics(items: ObservationItem[]): ChannelMetric[] {
  const withEmail = items.filter((item) => item.import_meta?.email).length;
  const countries = new Set(items.map((item) => item.import_meta?.country).filter(Boolean));
  return [
    { label: '有邮箱', value: num(withEmail), icon: Mail, detail: '最近缓存样本' },
    { label: '国家数', value: num(countries.size), icon: FileSpreadsheet, detail: '最近导入样本' },
  ];
}
