import { Telescope, Eye, Chrome, AtSign, RefreshCw, AlertOctagon, XCircle } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { Pill } from '@/components/Pill';
import { StartCollectionForm } from '@/components/extension/StartCollectionForm';
import { useExtensionSessions, useRunProgress, useDbStats, useRecentObservations, usePostExtensionCommand } from '@/hooks/useApi';
import { formatCompact, shortRelative } from '@/lib/format';
import { useQueryClient } from '@tanstack/react-query';
import type { CollectorObservation } from '@/api/types';

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
  const dbQ = useDbStats();
  const progressQ = useRunProgress();
  const obsQ = useRecentObservations(30);
  const cancelCmd = usePostExtensionCommand();
  const qc = useQueryClient();

  const sessions = sessQ.data?.sessions ?? [];
  const onlineCount = sessions.filter((s: any) => s.online).length;
  const activeSession = sessions.find((s: any) => s.online) || sessions[0] || null;
  const db: any = dbQ.data || {};
  const p: any = pickLatestProgress(progressQ.data, activeSession?.worker_id);
  const obs = obsQ.data?.items ?? [];

  const obsToday = db.today_raw_observations ?? db.raw_observations_today ?? db.today_observations ?? db.observations ?? 0;
  const newCreators = db.today_creators ?? db.creators_today ?? db.creators ?? 0;
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

  const obsColumns: Column<CollectorObservation>[] = [
    { key: 'time', header: '时间', cell: (r) => <span className="text-xs text-muted">{shortRelative(r.collected_at || r.created_at)}</span>, width: '120px' },
    { key: 'platform', header: '平台', cell: (r) => <Pill tone="info">{r.platform || 'tiktok'}</Pill> },
    { key: 'kw', header: '关键词', cell: (r) => <span className="text-xs">{r.search_keyword || '—'}</span> },
    { key: 'hash', header: '内容指纹', cell: (r) => <span className="text-xs font-mono text-muted truncate max-w-[200px] block">{r.content_hash || '—'}</span> },
    { key: 'worker', header: 'Worker', cell: (r) => <span className="text-xs text-muted truncate max-w-[120px] block">{r.worker_id || '—'}</span> },
  ];

  return (
    <AsyncState loading={sessQ.isLoading || dbQ.isLoading} error={sessQ.error || dbQ.error} height={400}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard
            label="插件在线" value={onlineCount > 0 ? `✓ ${onlineCount}` : '✗ 离线'}
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
          <KpiCard label="今日采集" value={formatCompact(obsToday)} icon={Eye} iconBg="rgb(6 182 212 / 0.18)" iconColor="#22d3ee" subLabel="原始观察记录" />
          <KpiCard label="新增达人" value={formatCompact(newCreators)} icon={Telescope} iconBg="rgb(99 102 241 / 0.18)" iconColor="#a5b4fc" />
        </div>

        {/* 启动采集表单 */}
        <StartCollectionForm onStarted={() => {
          qc.invalidateQueries({ queryKey: ['run-progress'] });
          qc.invalidateQueries({ queryKey: ['collector', 'recent-observations'] });
        }} workerId={activeSession?.worker_id} online={onlineCount > 0} />

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

        {/* 最近观察 */}
        <div className="card">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2">
            <h3 className="text-sm font-semibold">最近观察(实时滚动)</h3>
            <span className="text-xxs text-muted">10 秒自动刷新</span>
          </div>
          <DataTable columns={obsColumns} data={obs} rowKey={(r) => r.id} emptyText="还没有采集到任何观察" compact />
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
