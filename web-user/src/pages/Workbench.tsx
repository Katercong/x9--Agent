import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Chrome,
  Clock,
  Database,
  FileSpreadsheet,
  MessageSquare,
  Play,
  Radio,
  Upload,
  UserCircle,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { AsyncState, Empty } from '@/components/states/States';
import { Pill } from '@/components/Pill';
import {
  useBusinessDashboard,
  useExtensionSessions,
  useMe,
  useRecentObservations,
  useRunProgress,
} from '@/hooks/useApi';
import { formatCompact, shortRelative } from '@/lib/format';
import { pickItems, type CollectorObservation } from '@/api/types';

type CountRow = { key?: string; count?: number; value?: number };

function countValue(row?: CountRow) {
  return Number(row?.count ?? row?.value ?? 0) || 0;
}

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
  return running || rows[0] || {};
}

export default function Workbench() {
  const businessQ = useBusinessDashboard();
  const sessQ = useExtensionSessions();
  const progressQ = useRunProgress();
  const obsQ = useRecentObservations(6);
  const meQ = useMe();

  const data: any = businessQ.data || {};
  const summary = data.summary || {};
  const overviewRows: CountRow[] = data.overview || [];
  const overview = Object.fromEntries(overviewRows.map((row) => [row.key, countValue(row)]));
  const sessions = sessQ.data?.sessions ?? [];
  const onlineCount = sessions.filter((session: any) => session.online).length;
  const activeSession = sessions.find((session: any) => session.online) || sessions[0] || null;
  const progress: any = pickLatestProgress(progressQ.data, activeSession?.worker_id);
  const observations = pickItems<CollectorObservation>(obsQ.data);
  const user = meQ.data?.user;
  const running = Boolean(progress.running);
  const progressDone = Number(progress.done ?? progress.profiles_visited ?? 0) || 0;
  const progressTotal = Number(progress.total ?? progressDone + (progress.profiles_remaining ?? 0)) || 0;
  const progressPct = progressTotal > 0 ? Math.min(100, Math.round((progressDone / progressTotal) * 100)) : 0;

  const taskRows = [
    {
      label: '待回复',
      value: Number(overview.pending_reply || 0),
      detail: '已触达但还未进入下一阶段',
      to: '/recommendations',
      icon: MessageSquare,
      tone: 'info' as const,
    },
    {
      label: '待联系',
      value: Number(overview.prospect || 0),
      detail: '可分配给 BD 的潜在线索',
      to: '/recommendations',
      icon: Users,
      tone: 'muted' as const,
    },
    {
      label: '插件连接状态',
      value: onlineCount,
      detail: onlineCount > 0 ? `${onlineCount} 个插件在线` : '插件离线，请检查浏览器插件',
      to: '/collection',
      icon: onlineCount > 0 ? CheckCircle2 : AlertTriangle,
      tone: onlineCount > 0 ? 'good' as const : 'bad' as const,
    },
  ];

  return (
    <AsyncState loading={businessQ.isLoading && sessQ.isLoading} error={businessQ.error || sessQ.error} height={420}>
      <div className="space-y-4">
        <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.9fr] gap-4">
          <section className="card card-body">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xxs text-muted mb-1">当前部门</div>
                <h2 className="text-xl font-semibold leading-tight">{data.scope?.name || user?.department_code || '当前部门'}</h2>
              </div>
              <Pill tone={onlineCount > 0 ? 'good' : 'warn'}>
                {onlineCount > 0 ? `${onlineCount} 个插件在线` : '插件离线'}
              </Pill>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
              {taskRows.map((task) => (
                <TaskCard key={task.label} {...task} />
              ))}
            </div>
          </section>

          <section className="card card-body">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">当前账号</h3>
              <UserCircle size={18} className="text-muted" />
            </div>
            <div className="mt-4 space-y-3">
              <InfoLine label="用户" value={user?.display_name || user?.username || '匿名'} />
              <InfoLine label="角色" value={user?.role || '未识别'} />
              <InfoLine label="部门" value={user?.department_code || data.scope?.department_code || '当前部门'} />
              <InfoLine label="数据范围" value={data.scope?.type === 'company' ? '公司全量' : '部门数据'} />
            </div>
          </section>
        </div>

        <section>
          <h3 className="sec-title">常用入口</h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <ActionCard icon={Play} title="开始采集" desc="下发插件采集任务" to="/collection" tone="#06b6d4" />
            <ActionCard icon={FileSpreadsheet} title="导入表格" desc="CSV / XLSX 批量入库" to="/collect-import" tone="#f59e0b" />
            <ActionCard icon={Users} title="达人库" desc="推荐池和全部达人统一入口" to="/recommendations" tone="#22c55e" />
            <ActionCard icon={BarChart3} title="业务看板" desc="查看统一业务口径" to="/business" tone="#6366f1" />
          </div>
        </section>

        <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-4">
          <section className="card card-body">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold">采集状态</h3>
              <Link to="/collection" className="chip text-xxs">
                进入采集监控 <ArrowRight size={11} />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <StatusTile
                icon={Chrome}
                label="浏览器插件"
                value={onlineCount > 0 ? '在线' : '离线'}
                detail={activeSession?.last_heartbeat_at ? shortRelative(activeSession.last_heartbeat_at) : '无心跳'}
                good={onlineCount > 0}
              />
              <StatusTile
                icon={Radio}
                label="当前任务"
                value={running ? '运行中' : '空闲'}
                detail={running && progressTotal > 0 ? `${progressDone}/${progressTotal} · ${progressPct}%` : '无进行中任务'}
                good={running}
              />
            </div>
            {progressTotal > 0 && (
              <div className="mt-4">
                <div className="flex items-center justify-between text-xxs text-muted mb-2">
                  <span>{progress.keyword ? `关键词: ${progress.keyword}` : '采集进度'}</span>
                  <span className="num">{progressPct}%</span>
                </div>
                <div className="h-2 rounded-pill overflow-hidden" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                  <div className="h-full rounded-pill transition-all" style={{ width: `${progressPct}%`, background: 'rgb(var(--accent))' }} />
                </div>
              </div>
            )}
          </section>

          <section className="card">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold">最近更新</h3>
              <span className="text-xxs text-muted">来自采集记录</span>
            </div>
            <div className="p-3">
              {observations.length === 0 ? (
                <Empty height={132} message="暂无最近采集记录" />
              ) : (
                <div className="space-y-2">
                  {observations.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center gap-3 rounded border border-border px-3 py-2"
                      style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}
                    >
                      <div className="w-8 h-8 rounded-md flex items-center justify-center shrink-0" style={{ background: 'rgb(var(--accent) / 0.14)' }}>
                        <Upload size={14} style={{ color: 'rgb(var(--accent))' }} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-xs text-text truncate">
                          {item.search_keyword || item.platform || '采集记录'}
                        </div>
                        <div className="text-xxs text-muted truncate">
                          Worker {item.worker_id || '未知'} · {item.content_hash || '无指纹'}
                        </div>
                      </div>
                      <div className="text-xxs text-muted shrink-0">{shortRelative(item.collected_at || item.created_at)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <SmallSummary icon={Database} label="数据口径" value="/dashboard/department-summary" />
          <SmallSummary icon={Clock} label="生成时间" value={data.generated_at ? new Date(data.generated_at).toLocaleString() : '等待生成'} />
          <SmallSummary icon={CheckCircle2} label="整理规则" value="业务看板看结果，采集页面看来源，系统状态看健康" />
        </section>
      </div>
    </AsyncState>
  );
}

function TaskCard({
  label,
  value,
  detail,
  to,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  to: string;
  icon: LucideIcon;
  tone: 'good' | 'warn' | 'bad' | 'info' | 'muted';
}) {
  return (
    <Link
      to={to}
      className="rounded-md border border-border p-3 transition-colors hover:bg-white/5"
      style={{ background: 'rgb(var(--bg-elev-2) / 0.55)' }}
    >
      <div className="flex items-center justify-between">
        <Icon size={16} className="text-muted" />
        <Pill tone={tone}>{value > 0 ? '待处理' : '正常'}</Pill>
      </div>
      <div className="num text-2xl font-bold mt-3">{formatCompact(value)}</div>
      <div className="text-xs font-medium mt-1">{label}</div>
      <div className="text-xxs text-muted mt-1 truncate">{detail}</div>
    </Link>
  );
}

function ActionCard({
  icon: Icon,
  title,
  desc,
  to,
  tone,
}: {
  icon: LucideIcon;
  title: string;
  desc: string;
  to: string;
  tone: string;
}) {
  return (
    <Link to={to} className="card card-body group hover:bg-white/5 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="w-10 h-10 rounded-md flex items-center justify-center shrink-0" style={{ background: `${tone}22`, color: tone }}>
          <Icon size={18} />
        </div>
        <ArrowRight size={14} className="text-muted transition-transform group-hover:translate-x-0.5" />
      </div>
      <div className="text-sm font-semibold mt-3">{title}</div>
      <div className="text-xxs text-muted mt-1">{desc}</div>
    </Link>
  );
}

function StatusTile({
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
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="flex items-center gap-2 text-xs text-muted">
        <Icon size={14} />
        {label}
      </div>
      <div className={good ? 'text-good text-base font-semibold mt-2' : 'text-muted text-base font-semibold mt-2'}>
        {value}
      </div>
      <div className="text-xxs text-muted mt-1 truncate">{detail}</div>
    </div>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-muted">{label}</span>
      <span className="text-text font-medium truncate">{value}</span>
    </div>
  );
}

function SmallSummary({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="card card-body">
      <div className="flex items-center gap-2 text-xs text-muted">
        <Icon size={14} />
        {label}
      </div>
      <div className="text-xs text-text mt-2 truncate">{value}</div>
    </div>
  );
}
