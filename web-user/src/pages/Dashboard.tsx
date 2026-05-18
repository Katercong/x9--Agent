import { Eye, Users, Sparkles, ClipboardCheck, Server, Database, Chrome, AtSign } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { AsyncState } from '@/components/states/States';
import { useAppStatus, useDbStats, useExtensionStatus } from '@/hooks/useApi';
import { formatCompact, shortRelative } from '@/lib/format';

export default function Dashboard() {
  const appQ = useAppStatus();
  const dbQ = useDbStats();
  const extQ = useExtensionStatus();

  const loading = appQ.isLoading || dbQ.isLoading || extQ.isLoading;
  const error = appQ.error || dbQ.error || extQ.error;

  const db: any = dbQ.data || {};
  const ext: any = extQ.data || {};
  const app: any = appQ.data || {};

  const obs = (db as any).observations ?? (db as any).today_observations ?? 0;
  const creators = (db as any).creators ?? 0;
  const recs = (db as any).recommendations ?? (db as any).recommended ?? 0;
  const review = (db as any).review_pending ?? (db as any).review ?? 0;

  return (
    <AsyncState loading={loading} error={error} height={400}>
      <div className="space-y-4">
        {/* Hero */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="card card-body col-span-2 lg:col-span-1 flex flex-col justify-center">
            <span className="text-xxs text-muted">今日采集</span>
            <span className="text-3xl num font-bold mt-1" style={{ color: 'rgb(var(--accent))' }}>
              {formatCompact(obs as number)}
            </span>
            <span className="text-xxs text-muted mt-2">浏览器扩展实时上传的创作者观察记录</span>
          </div>
          <KpiCard label="今日达人" value={formatCompact(creators as number)} icon={Users} iconBg="rgb(99 102 241 / 0.18)" iconColor="#a5b4fc" />
          <KpiCard label="已推荐" value={formatCompact(recs as number)} icon={Sparkles} iconBg="rgb(245 158 11 / 0.18)" iconColor="#fbbf24" />
          <KpiCard label="待审核" value={formatCompact(review as number)} icon={ClipboardCheck} iconBg="rgb(239 68 68 / 0.18)" iconColor="#fca5a5" />
        </div>

        {/* System status */}
        <h3 className="sec-title pt-2">系统状态</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatusCard
            icon={Server}
            label="后端服务"
            value={app.ok === false ? '异常' : (app.service || '在线')}
            tone={app.ok === false ? 'bad' : 'good'}
            detail={app.version ? `v${app.version}` : undefined}
          />
          <StatusCard
            icon={Database}
            label="数据库"
            value={creators ? '正常' : '空'}
            tone="good"
            detail={`${formatCompact(creators as number)} 达人 · ${formatCompact(recs as number)} 推荐`}
          />
          <StatusCard
            icon={Chrome}
            label="浏览器插件"
            value={ext.online ? '在线' : '离线'}
            tone={ext.online ? 'good' : 'muted'}
            detail={ext.last_heartbeat_at ? `心跳:${shortRelative(ext.last_heartbeat_at)}` : '未连接'}
          />
          <StatusCard
            icon={AtSign}
            label="TikTok 登录"
            value={ext.tiktok_logged_in ? '已登录' : '未登录'}
            tone={ext.tiktok_logged_in ? 'good' : 'warn'}
            detail={ext.worker_id ? `Worker: ${String(ext.worker_id).slice(0, 8)}` : undefined}
          />
        </div>
      </div>
    </AsyncState>
  );
}

function StatusCard({
  icon: Icon, label, value, tone, detail,
}: {
  icon: any; label: string; value: string; tone: 'good' | 'warn' | 'bad' | 'muted'; detail?: string;
}) {
  const toneClass = {
    good: 'text-good', warn: 'text-warn', bad: 'text-bad', muted: 'text-muted',
  }[tone];
  return (
    <div className="card card-body">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Icon size={14} className="text-muted" />
          <span className="text-xs text-muted">{label}</span>
        </div>
        <Eye size={12} className={toneClass} />
      </div>
      <div className={`text-base font-semibold ${toneClass}`}>{value}</div>
      {detail && <div className="text-xxs text-muted mt-1">{detail}</div>}
    </div>
  );
}
