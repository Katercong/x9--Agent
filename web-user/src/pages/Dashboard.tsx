import {
  Activity,
  AlertCircle,
  AtSign,
  BarChart3,
  CheckCircle2,
  Chrome,
  Clock,
  Database,
  RefreshCw,
  Server,
  ShieldCheck,
  UploadCloud,
  UserPlus,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import {
  useAppStatus,
  useBusinessDashboard,
  useDbStats,
  useDbStatus,
  useExtensionSessions,
  useExtensionStatus,
} from '@/hooks/useApi';
import { useSourceStats } from '@/api/collector';
import { formatCompact, shortRelative } from '@/lib/format';

export default function Dashboard() {
  const appQ = useAppStatus();
  const dbStatusQ = useDbStatus();
  const dbStatsQ = useDbStats();
  const businessQ = useBusinessDashboard();
  const sourceStatsQ = useSourceStats();
  const extQ = useExtensionStatus();
  const sessQ = useExtensionSessions();

  const loading = appQ.isLoading || dbStatusQ.isLoading || extQ.isLoading || businessQ.isLoading || sourceStatsQ.isLoading;
  const error = appQ.error || dbStatusQ.error || extQ.error || businessQ.error || sourceStatsQ.error;

  const app: any = appQ.data || {};
  const dbStatus: any = dbStatusQ.data || {};
  const dbStats: any = dbStatsQ.data || {};
  const business: any = businessQ.data || {};
  const summary = business.summary || {};
  const sourceBuckets = sourceStatsQ.data?.sources;
  const ext: any = extQ.data || {};
  const sessions = sessQ.data?.sessions ?? [];
  const onlineCount = sessions.filter((session: any) => session.online).length;
  const latestSession = sessions.find((session: any) => session.online) || sessions[0] || null;
  const appOk = app.ok !== false;
  const dbOk = dbStatus.ok !== false;
  const extOnline = Boolean(ext.online || onlineCount > 0);
  const tiktokLoggedIn = Boolean(ext.tiktok_logged_in || sessions.some((session: any) => session.tiktok_login_status === 'logged_in'));
  const rawTotal = Number(summary.raw_observations_total ?? sumBuckets(sourceBuckets, 'total') ?? dbStats.raw_observations ?? dbStats.observations ?? 0) || 0;
  const rawToday = Number(summary.raw_observations_today ?? sumBuckets(sourceBuckets, 'today') ?? dbStats.today_raw_observations ?? dbStats.raw_observations_today ?? 0) || 0;
  const businessTotal = Number(summary.total_creators ?? 0) || 0;
  const businessToday = Number(summary.today_new_creators ?? summary.today_collected ?? 0) || 0;
  const bdHistoryCreators = Number(summary.bd_history_creators ?? summary.legacy_staff_contacted ?? 0) || 0;

  return (
    <AsyncState loading={loading} error={error} height={420}>
      <div className="space-y-4">
        <section>
          <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="sec-title !mb-0">全平台统计口径</h3>
            <span className="text-xxs text-muted">{business.scope?.name || '当前范围'} · 所有来源累计</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            <HealthCard
              icon={Users}
              label="总达人"
              value={formatCompact(businessTotal)}
              detail="所有渠道累计"
              tone="good"
            />
            <HealthCard
              icon={UserPlus}
              label="今日新增"
              value={formatCompact(businessToday)}
              detail="所有渠道今日累计"
              tone="good"
            />
            <HealthCard
              icon={UploadCloud}
              label="今日采集回传"
              value={formatCompact(rawToday)}
              detail={`raw 总回传 ${formatCompact(rawTotal)}`}
              tone={rawToday > 0 ? 'warn' : 'muted'}
            />
            <HealthCard
              icon={BarChart3}
              label="BD历史达人"
              value={formatCompact(bdHistoryCreators)}
              detail="已纳入业务达人总数和业务触达"
              tone="muted"
            />
          </div>
        </section>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <HealthCard
            icon={Server}
            label="后端服务"
            value={appOk ? '在线' : '异常'}
            detail={app.service || 'X9 service'}
            tone={appOk ? 'good' : 'bad'}
          />
          <HealthCard
            icon={Database}
            label="数据库连接"
            value={dbOk ? '正常' : '异常'}
            detail={dbStatus.url ? maskDbUrl(String(dbStatus.url)) : '当前数据库'}
            tone={dbOk ? 'good' : 'bad'}
          />
          <HealthCard
            icon={Chrome}
            label="浏览器插件"
            value={extOnline ? '在线' : '离线'}
            detail={latestSession?.last_heartbeat_at ? `心跳 ${shortRelative(latestSession.last_heartbeat_at)}` : '未收到心跳'}
            tone={extOnline ? 'good' : 'muted'}
          />
          <HealthCard
            icon={AtSign}
            label="TikTok 登录"
            value={tiktokLoggedIn ? '已登录' : '未登录'}
            detail={latestSession?.worker_id ? `Worker ${String(latestSession.worker_id).slice(0, 8)}` : '等待插件上报'}
            tone={tiktokLoggedIn ? 'good' : 'warn'}
          />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-4">
          <section className="card">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold">服务信息</h3>
              <ShieldCheck size={16} className="text-muted" />
            </div>
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              <InfoTile label="运行环境" value={app.env || 'production'} />
              <InfoTile label="系统版本" value={app.system_version || app.version || '—'} />
              <InfoTile label="评分版本" value={app.score_version || '—'} />
              <InfoTile label="推荐版本" value={app.rec_version || '—'} />
              <InfoTile label="标签版本" value={app.tag_version || '—'} />
              <InfoTile label="服务时间" value={app.now ? new Date(app.now).toLocaleString() : '—'} />
            </div>
          </section>

          <section className="card">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold">同步与采集健康</h3>
              <Activity size={16} className="text-muted" />
            </div>
            <div className="p-4 space-y-3">
              <SignalRow
                icon={RefreshCw}
                label="插件会话"
                value={`${formatCompact(sessions.length)} 个`}
                detail={`${formatCompact(onlineCount)} 个在线`}
                good={onlineCount > 0}
              />
              <SignalRow
                icon={Clock}
                label="最近心跳"
                value={latestSession?.last_heartbeat_at ? shortRelative(latestSession.last_heartbeat_at) : '无心跳'}
                detail={latestSession?.page_type || latestSession?.current_url || '等待插件连接'}
                good={onlineCount > 0}
              />
              <SignalRow
                icon={Database}
                label="原始观察记录"
                value={formatCompact(rawTotal)}
              detail={`今日 raw 回传 ${formatCompact(rawToday)}，已纳入总达人口径`}
                good
              />
              <SignalRow
                icon={AlertCircle}
                label="系统日志"
                value={formatCompact(dbStats.system_logs)}
                detail="只用于排查，不作为业务看板指标"
                good
              />
            </div>
          </section>
        </div>

        <section className="card">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold">采集来源拆分</h3>
            <UploadCloud size={16} className="text-muted" />
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <SourceTile label="TikTok Shop raw" total={sourceBuckets?.tiktok_shop?.total} today={sourceBuckets?.tiktok_shop?.today} />
            <SourceTile label="X9 线索 raw" total={sourceBuckets?.x9_leads?.total} today={sourceBuckets?.x9_leads?.today} />
            <SourceTile label="表格导入 raw" total={sourceBuckets?.table_import?.total} today={sourceBuckets?.table_import?.today} />
          </div>
        </section>

        <section className="card card-body">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-md flex items-center justify-center shrink-0" style={{ background: 'rgb(var(--accent) / 0.14)', color: 'rgb(var(--accent))' }}>
              <CheckCircle2 size={18} />
            </div>
            <div>
              <h3 className="text-sm font-semibold">页面职责</h3>
              <p className="text-xs text-muted mt-1">
                总达人统一按所有渠道累计口径展示；系统状态只看服务、数据库、插件健康。
              </p>
            </div>
          </div>
        </section>
      </div>
    </AsyncState>
  );
}

function HealthCard({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone: 'good' | 'warn' | 'bad' | 'muted';
}) {
  const toneClass = {
    good: 'text-good',
    warn: 'text-warn',
    bad: 'text-bad',
    muted: 'text-muted',
  }[tone];

  return (
    <div className="card card-body">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted">
          <Icon size={15} />
          {label}
        </div>
        <span className={`w-2 h-2 rounded-full ${tone === 'good' ? 'bg-good' : tone === 'bad' ? 'bg-bad' : tone === 'warn' ? 'bg-warn' : 'bg-muted'}`} />
      </div>
      <div className={`text-lg font-semibold mt-3 ${toneClass}`}>{value}</div>
      <div className="text-xxs text-muted mt-1 truncate">{detail}</div>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="text-xxs text-muted">{label}</div>
      <div className="text-xs text-text font-medium mt-1 truncate">{value}</div>
    </div>
  );
}

function SignalRow({
  icon: Icon,
  label,
  value,
  detail,
  good,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  good: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border px-3 py-2" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <Icon size={15} className={good ? 'text-good' : 'text-muted'} />
      <div className="min-w-0 flex-1">
        <div className="text-xs text-text">{label}</div>
        <div className="text-xxs text-muted truncate">{detail}</div>
      </div>
      <div className="text-xs font-semibold num">{value}</div>
    </div>
  );
}

function SourceTile({ label, total, today }: { label: string; total?: number; today?: number }) {
  const totalValue = Number(total ?? 0) || 0;
  const todayValue = Number(today ?? 0) || 0;
  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="text-xs text-text font-medium">{label}</div>
      <div className="grid grid-cols-2 gap-2 mt-3">
        <div>
          <div className="text-xxs text-muted">总回传</div>
          <div className="text-base font-semibold num">{formatCompact(totalValue)}</div>
        </div>
        <div>
          <div className="text-xxs text-muted">今日回传</div>
          <div className="text-base font-semibold num">{formatCompact(todayValue)}</div>
        </div>
      </div>
    </div>
  );
}

function maskDbUrl(value: string) {
  return value
    .replace(/\/\/([^:/@]+):([^@]+)@/, '//***:***@')
    .replace(/([?&]password=)[^&]+/i, '$1***');
}

function sumBuckets(sources: any, key: 'total' | 'today') {
  if (!sources) return 0;
  return Object.values(sources).reduce((sum: number, bucket: any) => sum + (Number(bucket?.[key]) || 0), 0);
}
