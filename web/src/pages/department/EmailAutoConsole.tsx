import { useMemo, useState } from 'react';
import {
  CalendarClock,
  CheckCircle2,
  Edit3,
  Eye,
  Pause,
  Play,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { cn } from '@/lib/cn';
import {
  useEmailAutoActions,
  useEmailAutoCampaignStatus,
  useEmailAutoCreateCampaign,
  useEmailAutoDashboard,
  useEmailAutoMailboxRemove,
  useEmailAutoMailboxUpdate,
  useEmailAutoSyncMailboxes,
} from '@/hooks/useApi';
import type { EmailAutoCampaignCreate, EmailAutoJob } from '@/api/types';

type CampaignStatus = 'running' | 'paused' | 'draft';
type MailboxStatus = 'normal' | 'cooldown' | 'limit' | 'auth_expired' | 'bounce_risk';
type JobStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'skipped' | 'draft_created';
type ScheduleType = 'daily' | 'weekly' | 'monthly';

interface AutoCampaign {
  id: string;
  name: string;
  status: CampaignStatus;
  scheduleType: ScheduleType;
  scheduleLabel: string;
  timeWindow: string;
  sent: number;
  dailyLimit: number;
  hourlyLimit: number;
  interval: string;
  mailboxPool: string;
  filters: string[];
  action: string;
}

interface MailboxQuota {
  id: string;
  email: string;
  owner: string;
  status: MailboxStatus;
  enabled: boolean;
  autoSent: number;
  quota: number;
  remaining: number;
  replies: number;
  bounces: number;
  failures: number;
  nextSendAt: string;
  lastSyncAt: string;
}

interface AutoJob {
  id: string;
  time: string;
  creator: string;
  recipient: string;
  sender: string;
  product: string;
  plan: string;
  status: JobStatus;
  reason: string;
  filters: string[];
  subject?: string;
  body?: string;
  body_format?: string;
}

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const recommendationSelectFields = [
  {
    label: '来源',
    defaultOption: '全部来源',
    options: ['全部来源', 'TikTok Shop', 'X9 线索', '表格导入', '其他'],
  },
  {
    label: '优先级',
    defaultOption: '全部优先级',
    options: ['全部优先级', 'P1', 'P2', 'P3', 'P4'],
  },
  {
    label: '联系方式',
    defaultOption: '有邮箱',
    options: ['全部联系', '可联系', '有邮箱', '无联系方式'],
  },
  {
    label: '评分',
    defaultOption: '85+ 强推荐',
    options: ['全部评分', '85+ 强推荐', '70-84 可测试', '50-69 观察', '<50 低分'],
  },
  {
    label: '产品',
    defaultOption: '动态读取：主品类 / 推荐产品 / 标签',
    options: ['全部产品', '动态读取：主品类 / 推荐产品 / 标签'],
  },
  {
    label: '合作',
    defaultOption: '动态读取：推荐合作方式',
    options: ['全部合作', '动态读取：推荐合作方式'],
  },
  {
    label: '建联状态',
    defaultOption: '动态读取：待建联 / 已建联 / 已回复等',
    options: ['全部状态', '动态读取：待建联 / 已建联 / 已回复等'],
  },
  {
    label: '复核状态',
    defaultOption: '无复核/风险',
    options: ['全部复核状态', '需要复核', '有风险提示', '无复核/风险'],
  },
  {
    label: '归属',
    defaultOption: '全部归属',
    options: ['全部归属', '已分配 BD', '未分配 BD'],
  },
  {
    label: '入库时间',
    defaultOption: '近 30 天',
    options: ['全部入库时间', '近 24 小时', '近 7 天', '近 30 天'],
  },
  {
    label: '排序',
    defaultOption: '综合推荐排序',
    options: ['综合推荐排序', '评分从高到低', '粉丝从高到低', '产品匹配优先', '优先级 P1 优先', '最近入库优先', '可联系优先', '小达人优先'],
  },
];

const recommendationProtectionRules = [
  '客户推荐库 uncontacted=true',
  'outreach_sent=false',
  '必须有邮箱',
  '30 天内未重复首封',
  '排除已回复',
  '排除退订',
  '排除退信',
  '发送成功后进入邮件跟踪',
];

export default function EmailAutoConsole() {
  const [selectedStatus, setSelectedStatus] = useState<'all' | JobStatus>('pending');
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [previewJob, setPreviewJob] = useState<AutoJob | null>(null);
  const [editingMailbox, setEditingMailbox] = useState<MailboxQuota | null>(null);
  const [scheduleType, setScheduleType] = useState<ScheduleType>('daily');
  const [selectedWeekdays, setSelectedWeekdays] = useState(['周一', '周二', '周三', '周四', '周五']);
  const [notice, setNotice] = useState('');
  const dashboardQ = useEmailAutoDashboard();
  const syncMailboxes = useEmailAutoSyncMailboxes();
  const createCampaign = useEmailAutoCreateCampaign();
  const campaignStatus = useEmailAutoCampaignStatus();
  const updateMailbox = useEmailAutoMailboxUpdate();
  const removeMailbox = useEmailAutoMailboxRemove();
  const emailAutoActions = useEmailAutoActions();
  const showNotice = (message: string) => setNotice(message);

  const campaigns: AutoCampaign[] = useMemo(() => (dashboardQ.data?.campaigns ?? []).map((item) => ({
    id: item.id,
    name: item.name,
    status: item.status as CampaignStatus,
    scheduleType: item.schedule_type as ScheduleType,
    scheduleLabel: item.schedule_label,
    timeWindow: item.time_window,
    sent: item.sent,
    dailyLimit: item.daily_limit,
    hourlyLimit: item.hourly_limit,
    interval: item.interval,
    mailboxPool: item.mailbox_pool === 'all' ? '全部已启用绑定邮箱' : item.mailbox_pool,
    filters: filterSummary(item.filters),
    action: item.send_mode === 'send' ? '自动发送并进入邮件跟踪' : '只生成草稿，人工确认后发送',
  })), [dashboardQ.data?.campaigns]);

  const mailboxes: MailboxQuota[] = useMemo(() => (dashboardQ.data?.mailboxes ?? []).map((item) => ({
    id: item.id,
    email: item.email,
    owner: item.owner,
    status: item.status as MailboxStatus,
    enabled: item.enabled,
    autoSent: item.auto_sent,
    quota: item.quota,
    remaining: item.remaining,
    replies: item.replies,
    bounces: item.bounces,
    failures: item.failures,
    nextSendAt: item.next_send_at,
    lastSyncAt: item.last_sync_at ? formatShortTime(item.last_sync_at) : '未同步',
  })), [dashboardQ.data?.mailboxes]);

  const jobs: AutoJob[] = useMemo(() => (dashboardQ.data?.jobs ?? []).map(mapApiJob), [dashboardQ.data?.jobs]);

  const totalSent = dashboardQ.data?.dashboard.today_sent ?? 0;
  const totalTarget = dashboardQ.data?.dashboard.today_target ?? 0;
  const availableMailboxes = dashboardQ.data?.dashboard.available_mailboxes ?? 0;
  const riskMailboxes = dashboardQ.data?.dashboard.risk_mailboxes ?? 0;
  const queueCount = dashboardQ.data?.dashboard.queue_count ?? 0;
  const replyCount = dashboardQ.data?.dashboard.reply_count ?? 0;
  const bounceCount = dashboardQ.data?.dashboard.bounce_count ?? 0;
  const jobStatusCounts = useMemo(() => jobs.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {}), [jobs]);

  const filteredJobs = useMemo(
    () => jobs.filter((item) => selectedStatus === 'all' || item.status === selectedStatus),
    [selectedStatus],
  );

  const campaignColumns: Column<AutoCampaign>[] = [
    {
      key: 'name',
      header: '计划',
      cell: (row) => (
        <div className="min-w-[240px]">
          <div className="font-semibold text-gray-900">{row.name}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {row.filters.slice(0, 5).map((tag) => <Pill key={tag} tone="muted">{tag}</Pill>)}
          </div>
        </div>
      ),
    },
    {
      key: 'schedule',
      header: '周期 / 时间',
      cell: (row) => (
        <div className="text-xs">
          <div className="font-semibold text-gray-800">{row.scheduleLabel}</div>
          <div className="mt-1 text-muted">{row.timeWindow} · {row.interval}</div>
        </div>
      ),
    },
    {
      key: 'quota',
      header: '发送量',
      cell: (row) => (
        <div className="min-w-[140px]">
          <div className="num font-semibold text-gray-900">{row.sent}/{row.dailyLimit}</div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, (row.sent / row.dailyLimit) * 100)}%` }} />
          </div>
          <div className="mt-1 text-xxs text-muted">{row.hourlyLimit}/小时</div>
        </div>
      ),
    },
    {
      key: 'pool',
      header: '邮箱池',
      cell: (row) => <span className="text-xs text-muted">{row.mailboxPool}</span>,
    },
    {
      key: 'status',
      header: '状态',
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'action',
      header: '操作',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <button
            className="btn btn-ghost"
            disabled={campaignStatus.isPending}
            onClick={() => {
              const next = row.status === 'running' ? 'paused' : 'running';
              campaignStatus.mutate({ id: row.id, status: next }, { onSuccess: () => showNotice(next === 'running' ? '计划已恢复运行' : '计划已暂停') });
            }}
          >{row.status === 'running' ? <Pause size={13} /> : <Play size={13} />}{row.status === 'running' ? '暂停' : '恢复'}</button>
          <button
            className="btn btn-ghost"
            disabled={emailAutoActions.generateJobs.isPending}
            onClick={() => emailAutoActions.generateJobs.mutate({ id: row.id, limit: 200 }, { onSuccess: (res) => showNotice(`已生成 ${res.created_jobs} 个队列任务`) })}
          ><Edit3 size={13} />补充队列</button>
        </div>
      ),
    },
  ];

  const mailboxColumns: Column<MailboxQuota>[] = [
    {
      key: 'email',
      header: 'Gmail',
      cell: (row) => (
        <div className="min-w-[210px]">
          <div className="num font-semibold text-gray-900">{row.email}</div>
          <div className="mt-1 text-xxs text-muted">{row.owner} · 最后同步 {row.lastSyncAt}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '状态',
      cell: (row) => <MailboxStatusBadge status={row.status} enabled={row.enabled} />,
    },
    {
      key: 'quota',
      header: '今日额度',
      cell: (row) => (
        <div className="min-w-[130px]">
          <div className="num font-semibold text-gray-900">{row.autoSent}/{row.quota}</div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
            <div className={cn('h-full rounded-full', row.status === 'cooldown' ? 'bg-amber-500' : 'bg-green-500')} style={{ width: `${Math.min(100, (row.autoSent / row.quota) * 100)}%` }} />
          </div>
          <div className="mt-1 text-xxs text-muted">剩余 {Math.max(0, row.quota - row.autoSent)} 封</div>
        </div>
      ),
    },
    { key: 'reply', header: '回复', align: 'right', cell: (row) => <span className="num text-xs font-semibold">{row.replies}</span> },
    { key: 'bounce', header: '退信/失败', align: 'right', cell: (row) => <span className="num text-xs text-muted">{row.bounces}/{row.failures}</span> },
    { key: 'next', header: '下次可发', cell: (row) => <span className="text-xs text-muted">{row.nextSendAt}</span> },
    {
      key: 'op',
      header: '授权 / 额度',
      align: 'right',
      cell: (row) => (
        <button className="btn btn-ghost" onClick={() => setEditingMailbox(row)}><Settings2 size={13} />编辑授权</button>
      ),
    },
  ];

  const jobColumns: Column<AutoJob>[] = [
    { key: 'time', header: '时间', width: '70px', cell: (row) => <span className="num text-xs">{row.time}</span> },
    {
      key: 'creator',
      header: '达人',
      cell: (row) => (
        <div className="min-w-[170px]">
          <div className="font-semibold text-gray-900">{row.creator}</div>
          <div className="mt-1 text-xxs text-muted">{row.recipient}</div>
        </div>
      ),
    },
    { key: 'sender', header: '发件邮箱', cell: (row) => <span className="num text-xs text-muted">{row.sender}</span> },
    {
      key: 'asset',
      header: '素材/话术',
      cell: (row) => (
        <div className="min-w-[180px]">
          <div className="text-xs font-medium text-gray-800">{row.product}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {row.filters.map((tag) => <Pill key={tag} tone="info">{tag}</Pill>)}
          </div>
        </div>
      ),
    },
    { key: 'plan', header: '计划', cell: (row) => <span className="text-xs text-muted">{row.plan}</span> },
    { key: 'status', header: '状态', cell: (row) => <JobStatusBadge status={row.status} /> },
    { key: 'reason', header: '原因', cell: (row) => <span className="text-xs text-muted">{row.reason}</span> },
    {
      key: 'preview',
      header: '操作',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={() => setPreviewJob(row)}><Eye size={13} />邮件预览</button>
          {row.status === 'failed' || row.status === 'skipped' ? (
            <button className="btn btn-ghost" onClick={() => emailAutoActions.retryJob.mutate(row.id, { onSuccess: () => showNotice('任务已重新进入待发送队列') })}>重试</button>
          ) : null}
          {row.status === 'pending' || row.status === 'failed' ? (
            <button className="btn btn-ghost" onClick={() => emailAutoActions.skipJob.mutate(row.id, { onSuccess: () => showNotice('任务已跳过') })}>跳过</button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {notice && (
        <div className="fixed right-4 top-16 z-[100] flex max-w-sm items-center gap-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-700 shadow-lg">
          <span className="min-w-0 flex-1">{notice}</span>
          <button type="button" className="text-blue-500 hover:text-blue-800" onClick={() => setNotice('')}>关闭</button>
        </div>
      )}
      <section className="card">
        <div className="card-body">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold text-gray-900">自动邮件控制台</h2>
                <Pill tone="good">运行中</Pill>
                <Pill tone="info">客户推荐库</Pill>
                <Pill tone="info">AI 图片话术</Pill>
              </div>
              <p className="mt-1 max-w-3xl text-xs text-muted">
                从客户推荐库自动取达人，按时间窗口、邮箱额度和保护规则生成 20% commission 邮件，发送后自动更新达人状态并进入邮件跟踪系统。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="btn"
                disabled={emailAutoActions.pauseAll.isPending}
                onClick={() => emailAutoActions.pauseAll.mutate(undefined, { onSuccess: (res) => showNotice(`已暂停 ${res.updated} 个计划`) })}
              ><Pause size={14} />暂停全部</button>
              <button
                className="btn"
                disabled={syncMailboxes.isPending}
                onClick={() => syncMailboxes.mutate(undefined, { onSuccess: (res) => showNotice(`已同步 ${res.total} 个绑定邮箱`) })}
              ><RefreshCw size={14} />同步邮箱</button>
              <button className="btn btn-primary" onClick={() => setShowPlanModal(true)}><CalendarClock size={14} />新建计划</button>
            </div>
          </div>
        </div>
        <div className="grid border-t border-line sm:grid-cols-2 xl:grid-cols-6">
          <Metric label="今日已发" value={`${totalSent}/${totalTarget}`} sub="按配置额度，不打满 Gmail 官方上限" tone="blue" />
          <Metric label="可用邮箱" value={`${availableMailboxes}/${mailboxes.length}`} sub="自动读取已绑定邮箱" tone="green" />
          <Metric label="队列" value={queueCount.toLocaleString('zh-CN')} sub="待发送任务" tone="cyan" />
          <Metric label="回复" value={replyCount} sub="今日同步回复" tone="green" />
          <Metric label="退信" value={bounceCount} sub="超过阈值自动冷却" tone="amber" />
          <Metric label="风险邮箱" value={riskMailboxes} sub="冷却/授权/退信风险" tone="red" />
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,.75fr)]">
        <section className="card">
          <div className="card-body border-b border-line">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">运行计划</h3>
                <p className="mt-0.5 text-xxs text-muted">支持每天 / 每周指定周几 / 每月指定日期，发送窗口精确到小时分钟。</p>
              </div>
              <button className="btn btn-primary" onClick={() => setShowPlanModal(true)}><Sparkles size={13} />创建自动发送计划</button>
            </div>
          </div>
          <DataTable columns={campaignColumns} data={campaigns} rowKey={(row) => row.id} emptyText={dashboardQ.isLoading ? '正在读取自动邮件计划…' : '暂无自动发送计划'} />
        </section>

        <section className="card">
          <div className="card-body border-b border-line">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">达人来源：客户推荐库</h3>
                <p className="mt-0.5 text-xxs text-muted">发送对象只从客户推荐库筛选，发送后状态更新到邮件跟踪。</p>
              </div>
              <Pill tone="good">保护规则开启</Pill>
            </div>
          </div>
          <div className="p-4">
            <RecommendationRulesPanel compact />
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-body border-b border-line">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">邮箱额度中心</h3>
              <p className="mt-0.5 text-xxs text-muted">自动获取当前已绑定 Gmail，可编辑授权信息、启用状态和每日发送数量额度。</p>
            </div>
            <div className="flex gap-2">
              <button
                className="btn"
                disabled={syncMailboxes.isPending}
                onClick={() => syncMailboxes.mutate(undefined, { onSuccess: (res) => showNotice(`已同步 ${res.total} 个绑定邮箱`) })}
              ><RefreshCw size={13} />同步绑定邮箱</button>
              <button
                className="btn"
                disabled={emailAutoActions.healthCheck.isPending}
                onClick={() => emailAutoActions.healthCheck.mutate(
                  { max_accounts: 20, poll_seconds: 30 },
                  { onSuccess: (res) => showNotice(`健康检查完成：${res.passed}/${res.total} 个邮箱通过互发互读`) },
                )}
              ><ShieldCheck size={13} />批量健康检查</button>
            </div>
          </div>
        </div>
        <DataTable columns={mailboxColumns} data={mailboxes} rowKey={(row) => row.id} emptyText={dashboardQ.isLoading ? '正在读取已绑定邮箱…' : '暂无已绑定 Gmail'} />
      </section>

      <section className="card">
        <div className="card-body border-b border-line">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">队列 / 日志</h3>
              <p className="mt-0.5 text-xxs text-muted">发送成功后自动更新达人状态：待建联 → 已发送首封，并进入邮件跟踪系统同步线程。</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {[
                ['all', '全部'],
                ['pending', `待发送 ${jobStatusCounts.pending || 0}`],
                ['sending', `发送中 ${jobStatusCounts.sending || 0}`],
                ['sent', `已发送 ${jobStatusCounts.sent || 0}`],
                ['draft_created', `已生成草稿 ${jobStatusCounts.draft_created || 0}`],
                ['failed', `失败 ${jobStatusCounts.failed || 0}`],
                ['skipped', `已跳过 ${jobStatusCounts.skipped || 0}`],
              ].map(([key, label]) => (
                <button
                  key={key}
                  className={cn('btn', selectedStatus === key && 'border-brand-500 bg-blue-50 text-brand-600')}
                  onClick={() => setSelectedStatus(key as 'all' | JobStatus)}
                >
                  {label}
                </button>
              ))}
              <button
                className="btn"
                disabled={emailAutoActions.retryFailed.isPending}
                onClick={() => emailAutoActions.retryFailed.mutate(undefined, { onSuccess: (res) => showNotice(`已重试 ${res.updated} 个失败任务`) })}
              ><RefreshCw size={13} />重试失败</button>
              <button
                className="btn btn-primary"
                disabled={emailAutoActions.processJobs.isPending}
                onClick={() => {
                  if (!window.confirm('确认执行到点任务？如果计划为自动发送，将真实调用 Gmail 发出邮件。')) return;
                  emailAutoActions.processJobs.mutate({ limit: 10, confirm_send: true }, { onSuccess: (res) => showNotice(`已处理 ${res.processed} 个任务`) });
                }}
              ><Play size={13} />执行到点任务</button>
            </div>
          </div>
        </div>
        <DataTable columns={jobColumns} data={filteredJobs} rowKey={(row) => row.id} emptyText={dashboardQ.isLoading ? '正在读取队列任务…' : '当前筛选下暂无任务'} />
      </section>

      {showPlanModal && (
        <PlanModal
          scheduleType={scheduleType}
          selectedWeekdays={selectedWeekdays}
          mailboxes={mailboxes}
          onScheduleTypeChange={setScheduleType}
          onWeekdaysChange={setSelectedWeekdays}
          onClose={() => setShowPlanModal(false)}
          onPreview={(payload) => {
            emailAutoActions.previewCampaign.mutate(payload, {
              onSuccess: (res) => setPreviewJob(mapApiJob(res.item)),
              onError: (error) => showNotice(error instanceof Error ? error.message : '没有找到符合筛选条件的达人'),
            });
          }}
          onCreate={(payload) => {
            createCampaign.mutate(payload, {
              onSuccess: (res) => {
                setShowPlanModal(false);
                showNotice(`计划已创建，生成 ${res.created_jobs} 个真实队列任务`);
              },
            });
          }}
          submitting={createCampaign.isPending}
          previewing={emailAutoActions.previewCampaign.isPending}
        />
      )}

      {previewJob && (
        <MailPreviewModal
          job={previewJob}
          onClose={() => setPreviewJob(null)}
        />
      )}

      {editingMailbox && (
        <MailboxModal
          mailbox={editingMailbox}
          onClose={() => setEditingMailbox(null)}
          onSave={(body) => updateMailbox.mutate({ id: editingMailbox.id, body }, {
            onSuccess: () => {
              setEditingMailbox(null);
              showNotice('邮箱额度配置已保存');
            },
          })}
          onRemove={() => {
            if (!window.confirm(`确定取消 ${editingMailbox.email} 的 Gmail 授权吗？取消后该邮箱将从自动发送邮箱池移除。`)) return;
            removeMailbox.mutate(editingMailbox.id, {
              onSuccess: () => {
                setEditingMailbox(null);
                showNotice(`已取消 ${editingMailbox.email} 的 Gmail 授权`);
              },
            });
          }}
          saving={updateMailbox.isPending}
          removing={removeMailbox.isPending}
        />
      )}
    </div>
  );
}

function mapApiJob(item: EmailAutoJob): AutoJob {
  return {
    id: item.id,
    time: item.time || (item.scheduled_at ? formatShortTime(item.scheduled_at) : ''),
    creator: item.creator,
    recipient: item.recipient,
    sender: item.sender,
    product: item.product,
    plan: item.plan,
    status: item.status as JobStatus,
    reason: item.reason,
    filters: item.filters ?? [],
    subject: item.subject,
    body: item.body,
    body_format: item.body_format,
  };
}

function formatShortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function filterSummary(filters: Record<string, unknown>) {
  const labels: string[] = ['客户推荐库'];
  const map: Record<string, Record<string, string>> = {
    source: { all: '全部来源' },
    priority: { all: '全部优先级', P1: 'P1', P2: 'P2', P3: 'P3', P4: 'P4' },
    contact: { email: '有邮箱', all: '全部联系' },
    score: { gte85: '85+ 强推荐', '70_84': '70-84 可测试', '50_69': '50-69 观察', lt50: '<50 低分' },
    review: { clean: '无复核/风险', need_review: '需要复核', has_risk: '有风险提示' },
    owner: { assigned: '已分配 BD', unassigned: '未分配 BD' },
    date: { '1d': '近 24 小时', '7d': '近 7 天', '30d': '近 30 天' },
    sort: { recommended: '综合推荐排序', score: '评分优先', followers: '粉丝优先', priority: '优先级优先', recent: '最近入库', micro: '小达人优先' },
  };
  for (const key of ['source', 'priority', 'contact', 'score', 'review', 'owner', 'date', 'sort']) {
    const value = String(filters[key] ?? 'all');
    const label = map[key]?.[value];
    if (label && !label.startsWith('全部')) labels.push(label);
  }
  const minFollowers = filters.min_followers;
  const maxFollowers = filters.max_followers;
  if (minFollowers || maxFollowers) labels.push(`粉丝 ${minFollowers || 0}-${maxFollowers || '不限'}`);
  return labels.slice(0, 8);
}

function Metric({ label, value, sub, tone }: { label: string; value: string | number; sub: string; tone: 'blue' | 'green' | 'cyan' | 'amber' | 'red' }) {
  const toneClass = {
    blue: 'text-brand-600 bg-blue-50',
    green: 'text-green-700 bg-green-50',
    cyan: 'text-cyan-700 bg-cyan-50',
    amber: 'text-amber-700 bg-amber-50',
    red: 'text-red-700 bg-red-50',
  }[tone];
  return (
    <div className="border-b border-r border-line bg-white p-4 last:border-r-0 sm:[&:nth-child(even)]:border-r-0 xl:border-b-0 xl:[&:nth-child(even)]:border-r">
      <div className="text-xxs font-medium text-muted">{label}</div>
      <div className={cn('num mt-1 inline-flex rounded px-2 py-1 text-xl font-black leading-none', toneClass)}>{value}</div>
      <div className="mt-2 truncate text-xxs text-muted">{sub}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: CampaignStatus }) {
  if (status === 'running') return <Pill tone="good">运行中</Pill>;
  if (status === 'paused') return <Pill tone="warn">已暂停</Pill>;
  return <Pill tone="muted">草稿</Pill>;
}

function MailboxStatusBadge({ status, enabled }: { status: MailboxStatus; enabled: boolean }) {
  if (!enabled) return <Pill tone="muted">未启用</Pill>;
  const map: Record<MailboxStatus, { tone: 'good' | 'warn' | 'bad' | 'info' | 'muted'; label: string }> = {
    normal: { tone: 'good', label: '正常' },
    cooldown: { tone: 'warn', label: '冷却' },
    limit: { tone: 'warn', label: '达限' },
    auth_expired: { tone: 'bad', label: '授权失效' },
    bounce_risk: { tone: 'bad', label: '退信过高' },
  };
  const meta = map[status];
  return <Pill tone={meta.tone}>{meta.label}</Pill>;
}

function JobStatusBadge({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, { tone: 'good' | 'warn' | 'bad' | 'info' | 'muted'; label: string }> = {
    pending: { tone: 'warn', label: '待发送' },
    sending: { tone: 'info', label: '发送中' },
    sent: { tone: 'good', label: '已发送' },
    draft_created: { tone: 'info', label: '已生成草稿' },
    failed: { tone: 'bad', label: '失败' },
    skipped: { tone: 'muted', label: '已跳过' },
  };
  const meta = map[status];
  return <Pill tone={meta.tone}>{meta.label}</Pill>;
}

function buildUsTimeReference(startTime: string, endTime: string) {
  return [
    { zone: '美国东部 ET', offsetHours: -12 },
    { zone: '美国中部 CT', offsetHours: -13 },
    { zone: '美国西部 PT', offsetHours: -15 },
  ].map((item) => ({
    zone: item.zone,
    window: `${shiftChinaTime(startTime, item.offsetHours)} - ${shiftChinaTime(endTime, item.offsetHours)}`,
  }));
}

function shiftChinaTime(value: string, offsetHours: number) {
  const match = value.trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return '时间格式错误';
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return '时间格式错误';
  let total = hours * 60 + minutes + offsetHours * 60;
  let day = '当天';
  if (total < 0) {
    total += 24 * 60;
    day = '前一天';
  } else if (total >= 24 * 60) {
    total -= 24 * 60;
    day = '后一天';
  }
  const hh = String(Math.floor(total / 60)).padStart(2, '0');
  const mm = String(total % 60).padStart(2, '0');
  return `${day} ${hh}:${mm}`;
}

function PlanModal({
  scheduleType,
  selectedWeekdays,
  mailboxes,
  onScheduleTypeChange,
  onWeekdaysChange,
  onClose,
  onPreview,
  onCreate,
  submitting,
  previewing,
}: {
  scheduleType: ScheduleType;
  selectedWeekdays: string[];
  mailboxes: MailboxQuota[];
  onScheduleTypeChange: (value: ScheduleType) => void;
  onWeekdaysChange: (value: string[]) => void;
  onClose: () => void;
  onPreview: (payload: EmailAutoCampaignCreate) => void;
  onCreate: (payload: EmailAutoCampaignCreate) => void;
  submitting?: boolean;
  previewing?: boolean;
}) {
  const [planName, setPlanName] = useState('客户推荐库每日首封');
  const [startTime, setStartTime] = useState('09:30');
  const [endTime, setEndTime] = useState('18:00');
  const [dailyLimit, setDailyLimit] = useState(300);
  const [hourlyLimit, setHourlyLimit] = useState(40);
  const [intervalMin, setIntervalMin] = useState(90);
  const [intervalMax, setIntervalMax] = useState(240);
  const [sendMode, setSendMode] = useState<'draft' | 'send'>('send');
  const [candidateLimit, setCandidateLimit] = useState(200);
  const usTimeReference = buildUsTimeReference(startTime, endTime);
  const capacityMailboxes = useMemo(
    () => mailboxes.filter((item) => item.enabled && item.quota > 0 && !['auth_expired', 'bounce_risk', 'cooldown'].includes(item.status)),
    [mailboxes],
  );
  const usableMailboxes = useMemo(
    () => capacityMailboxes.filter((item) => item.status === 'normal'),
    [capacityMailboxes],
  );
  const mailboxDailyCapacity = capacityMailboxes.reduce((sum, item) => sum + Math.max(0, item.quota || 0), 0);
  const mailboxRemainingToday = capacityMailboxes.reduce((sum, item) => sum + Math.max(0, item.remaining || 0), 0);
  const minMailboxQuota = capacityMailboxes.length ? Math.min(...capacityMailboxes.map((item) => Math.max(0, item.quota || 0))) : 0;
  const maxMailboxQuota = capacityMailboxes.length ? Math.max(...capacityMailboxes.map((item) => Math.max(0, item.quota || 0))) : 0;
  const protectedDailyLimit = mailboxDailyCapacity > 0
    ? Math.max(1, Math.min(dailyLimit, mailboxDailyCapacity))
    : Math.max(1, dailyLimit);
  const protectedHourlyLimit = Math.max(1, Math.min(hourlyLimit, protectedDailyLimit));
  const protectedCandidateLimit = Math.max(1, Math.min(candidateLimit, protectedDailyLimit, 1000));
  const todayExecutableLimit = Math.min(protectedDailyLimit, mailboxRemainingToday);
  const dailyLimitAdjusted = mailboxDailyCapacity > 0 && dailyLimit > mailboxDailyCapacity;
  const candidateLimitAdjusted = candidateLimit > protectedCandidateLimit;

  const toggleWeekday = (day: string) => {
    if (selectedWeekdays.includes(day)) {
      onWeekdaysChange(selectedWeekdays.filter((item) => item !== day));
    } else {
      onWeekdaysChange([...selectedWeekdays, day]);
    }
  };

  const createPayload = (): EmailAutoCampaignCreate => ({
    name: planName,
    status: 'running',
    schedule_type: scheduleType,
    weekdays: selectedWeekdays,
    month_days: [1],
    start_time: startTime,
    end_time: endTime,
    daily_limit: protectedDailyLimit,
    hourly_limit: protectedHourlyLimit,
    interval_min_seconds: Math.min(intervalMin, intervalMax),
    interval_max_seconds: Math.max(intervalMin, intervalMax),
    mailbox_pool: 'all',
    send_mode: sendMode,
    filters: {
      source: 'all',
      priority: 'all',
      contact: 'email',
      score: 'gte85',
      review: 'clean',
      date: '30d',
      sort: 'recommended',
    },
    generate_jobs: true,
    candidate_limit: protectedCandidateLimit,
  });

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-4">
      <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line p-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">新建自动发送计划</h3>
            <p className="mt-1 text-xs text-muted">计划会写入数据库，并按客户推荐库筛选生成真实队列任务。</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}><X size={14} />关闭</button>
        </div>

        <div className="overflow-y-auto p-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <FormField label="计划名称">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={planName} onChange={(event) => setPlanName(event.target.value)} />
            </FormField>
            <FormField label="邮箱池">
              <select className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="enabled">
                <option value="enabled">全部已启用绑定邮箱</option>
                <option value="creator">Creator Team 邮箱池</option>
                <option value="x9">X9 Outreach 邮箱池</option>
              </select>
            </FormField>
          </div>

          <div className="mt-4 rounded-md border border-line bg-soft p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900"><CalendarClock size={15} />发送周期和时间窗口</div>
            <div className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)_140px_140px]">
              <FormField label="周期">
                <select
                  className="w-full rounded-md border border-line px-3 py-2 text-xs"
                  value={scheduleType}
                  onChange={(event) => onScheduleTypeChange(event.target.value as ScheduleType)}
                >
                  <option value="daily">每天</option>
                  <option value="weekly">每周</option>
                  <option value="monthly">每月</option>
                </select>
              </FormField>
              {scheduleType === 'weekly' ? (
                <FormField label="具体周几">
                  <div className="flex flex-wrap gap-1.5">
                    {WEEKDAYS.map((day) => (
                      <button
                        type="button"
                        key={day}
                        onClick={() => toggleWeekday(day)}
                        className={cn('rounded border px-2 py-1 text-xs', selectedWeekdays.includes(day) ? 'border-brand-500 bg-blue-50 text-brand-600' : 'border-line bg-white text-gray-600')}
                      >
                        {day}
                      </button>
                    ))}
                  </div>
                </FormField>
              ) : scheduleType === 'monthly' ? (
                <FormField label="每月日期">
                  <select className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="1-28">
                    <option value="1-28">每月 1-28 号</option>
                    <option value="1-15">每月 1-15 号</option>
                    <option value="custom">自定义日期</option>
                  </select>
                </FormField>
              ) : (
                <FormField label="每天规则">
                  <div className="rounded-md border border-line bg-white px-3 py-2 text-xs text-muted">每天按时间窗口自动发送</div>
                </FormField>
              )}
              <FormField label="开始时间">
                <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
              </FormField>
              <FormField label="结束时间">
                <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
              </FormField>
            </div>
            <div className="mt-3 rounded-md border border-blue-100 bg-blue-50 p-3 text-xs text-blue-700">
              <div className="font-semibold text-blue-800">美国时间参考（按当前夏令时）</div>
              <div className="mt-2 grid gap-2 md:grid-cols-3">
                {usTimeReference.map((item) => (
                  <div key={item.zone} className="rounded border border-blue-100 bg-white px-3 py-2">
                    <div className="font-semibold">{item.zone}</div>
                    <div className="mt-1 num">{item.window}</div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-xxs text-blue-600">当前填写按北京时间换算：东部 -12h，中部 -13h，西部 -15h。</div>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-4">
            <FormField label="期望每日总量（全计划）">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={dailyLimit} onChange={(event) => setDailyLimit(Number(event.target.value.replace(/[^0-9]/g, '') || 0))} />
            </FormField>
            <FormField label="计划每小时上限">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={hourlyLimit} onChange={(event) => setHourlyLimit(Number(event.target.value.replace(/[^0-9]/g, '') || 0))} />
            </FormField>
            <FormField label="单邮箱发送间隔（秒）">
              <div className="grid grid-cols-2 gap-2">
                <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={intervalMin} onChange={(event) => setIntervalMin(Number(event.target.value.replace(/[^0-9]/g, '') || 0))} />
                <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={intervalMax} onChange={(event) => setIntervalMax(Number(event.target.value.replace(/[^0-9]/g, '') || 0))} />
              </div>
            </FormField>
            <FormField label="发送方式">
              <select className="w-full rounded-md border border-line px-3 py-2 text-xs" value={sendMode} onChange={(event) => setSendMode(event.target.value as 'draft' | 'send')}>
                <option value="draft">只生成草稿不发送</option>
                <option value="send">生成并自动发送</option>
              </select>
            </FormField>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-4">
            <FormField label="本次生成队列数">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={candidateLimit} onChange={(event) => setCandidateLimit(Number(event.target.value.replace(/[^0-9]/g, '') || 0))} />
            </FormField>
          </div>

          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            <div className="font-semibold text-amber-900">额度保护规则：实际发送量 = min(期望每日总量、邮箱池日额度、本次队列数)</div>
            <div className="mt-2 grid gap-2 md:grid-cols-3 xl:grid-cols-6">
              <QuotaStat label="可用/计入额度邮箱" value={`${usableMailboxes.length}/${capacityMailboxes.length} 个`} />
              <QuotaStat label="单邮箱日额度" value={capacityMailboxes.length ? `${minMailboxQuota}-${maxMailboxQuota} 封` : '无'} />
              <QuotaStat label="邮箱池日额度" value={`${mailboxDailyCapacity} 封`} />
              <QuotaStat label="今日剩余额度" value={`${mailboxRemainingToday} 封`} />
              <QuotaStat label="保存后的日上限" value={`${protectedDailyLimit} 封`} />
              <QuotaStat label="本次生成队列" value={`${protectedCandidateLimit} 条`} />
            </div>
            <div className="mt-2 text-xxs text-amber-700">
              每封真实发送前都会重新检查发件邮箱今日已发量；单个邮箱达到额度后会自动换邮箱，没有可用额度时任务停在队列中。
              {dailyLimitAdjusted ? ` 当前每日总量已从 ${dailyLimit} 自动按邮箱池日额度收紧到 ${protectedDailyLimit}。` : ''}
              {candidateLimitAdjusted ? ` 当前队列数已从 ${candidateLimit} 自动按计划日上限和单次生成上限收紧到 ${protectedCandidateLimit}。` : ''}
              {todayExecutableLimit < protectedDailyLimit ? ` 按今日剩余额度，本日最多还能实际发送 ${todayExecutableLimit} 封。` : ''}
            </div>
          </div>

          <div className="mt-4 rounded-md border border-line p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900"><Users size={15} />达人筛选条件</div>
            <RecommendationRulesPanel />
          </div>

          <div className="mt-4 grid gap-3 rounded-md border border-green-200 bg-green-50 p-4 text-xs text-green-700">
            <CheckLine>只读取客户推荐库中符合筛选条件的达人</CheckLine>
            <CheckLine>发送前检查：有邮箱、未退订、未退信、30 天内未重复首封</CheckLine>
            <CheckLine>AI 自动沿用用户端建联话术和图片素材逻辑，包含 20% commission 邮件内容</CheckLine>
            <CheckLine>发送成功后自动更新达人状态，并进入邮件跟踪系统同步线程</CheckLine>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-line p-4">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn" disabled={previewing} onClick={() => onPreview(createPayload())}><Eye size={13} />邮件预览</button>
          <button className="btn btn-primary" disabled={submitting} onClick={() => onCreate(createPayload())}>创建真实计划</button>
        </div>
      </div>
    </div>
  );
}

function RecommendationRulesPanel({ compact = false }: { compact?: boolean }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
        <div className="font-semibold text-blue-800">沿用客户推荐库高级筛选规则</div>
        <div className="mt-1 text-xxs">字段与推荐库保持一致：来源、关键词、优先级、联系方式、评分、粉丝、产品、合作、状态、复核、归属、入库时间和排序。</div>
      </div>

      <div className={cn('grid gap-3', compact ? 'grid-cols-1' : 'md:grid-cols-2 xl:grid-cols-3')}>
        <RecommendationRuleText label="关键词搜索" value="handle / 邮箱 / 商品 / 推荐理由" />
        {recommendationSelectFields.map((field) => (
          <RecommendationRuleSelect key={field.label} label={field.label} options={field.options} defaultOption={field.defaultOption} />
        ))}
        <div>
          <div className="mb-1 text-xxs font-semibold text-muted">粉丝区间</div>
          <div className="grid grid-cols-2 gap-2">
            <input className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs outline-none focus:border-brand-300" placeholder="最小" defaultValue="" inputMode="numeric" />
            <input className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs outline-none focus:border-brand-300" placeholder="最大" defaultValue="" inputMode="numeric" />
          </div>
        </div>
      </div>

      <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2">
        <div className="mb-2 text-xs font-semibold text-green-800">自动发送保护规则</div>
        <div className="flex flex-wrap gap-1.5">
          {recommendationProtectionRules.map((rule) => (
            <span key={rule} className="rounded border border-green-200 bg-white px-2 py-1 text-xxs text-green-700">{rule}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function RecommendationRuleSelect({ label, options, defaultOption }: { label: string; options: string[]; defaultOption: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xxs font-semibold text-muted">{label}</span>
      <select className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs text-gray-800 outline-none focus:border-brand-300" defaultValue={defaultOption}>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function RecommendationRuleText({ label, value }: { label: string; value: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xxs font-semibold text-muted">{label}</span>
      <input className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs outline-none focus:border-brand-300" defaultValue={value} />
    </label>
  );
}

function MailboxModal({
  mailbox,
  onClose,
  onSave,
  onRemove,
  saving,
  removing,
}: {
  mailbox: MailboxQuota;
  onClose: () => void;
  onSave: (body: { enabled?: boolean; daily_quota?: number; status?: string }) => void;
  onRemove: () => void;
  saving?: boolean;
  removing?: boolean;
}) {
  const [enabled, setEnabled] = useState(mailbox.enabled);
  const [quota, setQuota] = useState(mailbox.quota);
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 p-4">
      <div className="w-full max-w-xl rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-line p-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">编辑邮箱授权和额度</h3>
            <p className="mt-1 text-xs text-muted">{mailbox.email}</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}><X size={14} />关闭</button>
        </div>
        <div className="grid gap-4 p-4">
          <FormField label="授权邮箱">
            <input className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue={mailbox.email} />
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="启用状态">
              <select className="w-full rounded-md border border-line px-3 py-2 text-xs" value={enabled ? 'enabled' : 'disabled'} onChange={(event) => setEnabled(event.target.value === 'enabled')}>
                <option value="enabled">启用自动发送</option>
                <option value="disabled">暂停此邮箱</option>
              </select>
            </FormField>
            <FormField label="每日数量额度">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={quota} onChange={(event) => setQuota(Number(event.target.value.replace(/[^0-9]/g, '') || 0))} />
            </FormField>
          </div>
          <div className="rounded-md border border-line bg-soft p-3 text-xs text-muted">
            保存后会写入邮箱额度中心；授权信息仍沿用现有 Gmail OAuth 绑定。
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-line p-4">
          <button className="btn text-red-600 hover:border-red-200 hover:bg-red-50" disabled={removing || saving} onClick={onRemove}><Trash2 size={13} />取消授权</button>
          <button className="btn" onClick={onClose}>取消</button>
          <a className="btn" href={`/api/local/outreach/gmail/connect?label=${encodeURIComponent(mailbox.email)}&return_to=${encodeURIComponent('/d/email-auto')}`}><RefreshCw size={13} />重新授权</a>
          <button className="btn btn-primary" disabled={saving} onClick={() => onSave({ enabled, daily_quota: quota })}>保存配置</button>
        </div>
      </div>
    </div>
  );
}

function MailPreviewModal({
  job,
  onClose,
}: {
  job: AutoJob;
  onClose: () => void;
}) {
  const html = buildPreviewHtml(job);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line p-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">邮件预览</h3>
            <p className="mt-1 text-xs text-muted">来自真实队列或实时筛选预览，沿用用户端 AI 图片和 20% commission 话术链路。</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}><X size={14} />关闭</button>
        </div>
        <div className="overflow-y-auto bg-soft p-4">
          <div className="rounded-lg border border-line bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Pill tone="good">用户端同款 AI 话术</Pill>
              <Pill tone={job.body?.includes('/api/local/outreach/product-assets/') ? 'info' : 'warn'}>
                {job.body?.includes('/api/local/outreach/product-assets/') ? '系统 SKU 图片' : '当前邮件无图片'}
              </Pill>
              <Pill tone="muted">{job.plan}</Pill>
            </div>
            <div className="grid gap-4">
              <div className="space-y-3">
                <PreviewField label="收件人" value={job.recipient} />
                <PreviewField label="发件邮箱" value={job.sender} />
                <PreviewField label="主题" value={job.subject || '未生成主题'} />
                <div className="rounded-md border border-line bg-white">
                  <div className="flex items-center justify-between border-b border-line px-3 py-2">
                    <div className="flex items-center gap-2 text-xs font-semibold text-gray-800">最终邮件效果</div>
                  </div>
                  <div className="p-3">
                    <div className="overflow-hidden rounded-md border border-line bg-gray-50 px-3 py-4">
                      <div className="mx-auto max-w-[680px] rounded border border-line bg-white p-4 shadow-sm" dangerouslySetInnerHTML={{ __html: html }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-line p-4">
          <button className="btn" onClick={onClose}>关闭</button>
          <button className="btn btn-primary" onClick={onClose}><CheckCircle2 size={13} />确认内容</button>
        </div>
      </div>
    </div>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xxs font-semibold text-muted">{label}</span>
      {children}
    </label>
  );
}

function CheckLine({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function QuotaStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-amber-200 bg-white px-3 py-2">
      <div className="text-xxs text-amber-700">{label}</div>
      <div className="num mt-1 font-bold text-amber-900">{value}</div>
    </div>
  );
}

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xxs font-semibold text-muted">{label}</span>
      <input className="w-full rounded-md border border-line bg-white px-3 py-2 text-xs" readOnly value={value} />
    </label>
  );
}

function buildPreviewHtml(job: AutoJob) {
  if (job.body_format === 'html' && job.body) {
    return `
      <style>
        .x9-email-preview-html p { margin: 0 0 16px; font-size: 14px; line-height: 1.7; color: #111827; }
        .x9-email-preview-html p:last-child { margin-bottom: 0; }
        .x9-email-preview-html img { display: block; margin-bottom: 18px; }
      </style>
      <div class="x9-email-preview-html" style="font-family:Arial,Helvetica,sans-serif;background:#ffffff;color:#111827;">
        ${job.body}
      </div>
    `;
  }
  const paragraphs = (job.body || '当前任务还没有生成邮件正文')
    .split(/\n{2,}/)
    .map((block) => `<p style="margin:0 0 16px;font-size:14px;line-height:1.7;color:#111827;">${escapeHtml(block).replace(/\n/g, '<br/>')}</p>`)
    .join('');
  return `
    <div style="font-family:Arial,Helvetica,sans-serif;background:#ffffff;color:#111827;">
      ${paragraphs}
    </div>
  `;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
