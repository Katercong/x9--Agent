import { useEffect, useMemo, useState } from 'react';
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
  useEmailAutoUpdateCampaign,
  useEmailAutoMailboxRemove,
  useEmailAutoMailboxUpdate,
  useEmailAutoSyncMailboxes,
} from '@/hooks/useApi';
import type { EmailAutoCampaignCreate, EmailAutoHealthCheckResponse, EmailAutoJob } from '@/api/types';

type CampaignStatus = 'running' | 'paused' | 'draft';
type MailboxStatus = 'normal' | 'cooldown' | 'limit' | 'auth_expired' | 'bounce_risk';
type JobStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'skipped' | 'draft_created';
type ScheduleType = 'daily' | 'weekly' | 'monthly';

interface AutoCampaign {
  id: string;
  name: string;
  status: CampaignStatus;
  scheduleType: ScheduleType;
  weekdays: string[];
  monthDays: number[];
  scheduleLabel: string;
  timeWindow: string;
  startTime: string;
  endTime: string;
  sent: number;
  queueTotal: number;
  dailyLimit: number;
  hourlyLimit: number;
  intervalMinSeconds: number;
  intervalMaxSeconds: number;
  interval: string;
  mailboxPool: string;
  mailboxPoolValue: string;
  sendMode: 'draft' | 'send' | string;
  filtersRaw: Record<string, unknown>;
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

type RecommendationFilters = {
  keyword: string;
  source: string;
  priority: string;
  contact: string;
  score: string;
  product: string;
  collab: string;
  status: string;
  review: string;
  owner: string;
  date: string;
  sort: string;
  min_followers: string;
  max_followers: string;
};

type FilterOption = { value: string; label: string };

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const DEFAULT_RECOMMENDATION_FILTERS: RecommendationFilters = {
  keyword: '',
  source: 'all',
  priority: 'all',
  contact: 'email',
  score: 'gte85',
  product: 'all',
  collab: 'all',
  status: 'all',
  review: 'clean',
  owner: 'all',
  date: '30d',
  sort: 'recommended',
  min_followers: '',
  max_followers: '',
};

const JOB_PAGE_SIZE = 10;

const sourceOptions: FilterOption[] = [
  { value: 'all', label: '全部来源' },
  { value: 'tiktok_shop', label: 'TikTok Shop' },
  { value: 'x9_leads', label: 'X9 线索' },
  { value: 'table_import', label: '表格导入' },
  { value: 'other', label: '其他' },
];

const priorityOptions: FilterOption[] = [
  { value: 'all', label: '全部优先级' },
  { value: 'P1', label: 'P1' },
  { value: 'P2', label: 'P2' },
  { value: 'P3', label: 'P3' },
  { value: 'P4', label: 'P4' },
];

const contactOptions: FilterOption[] = [
  { value: 'email', label: '有邮箱' },
  { value: 'all', label: '全部联系' },
  { value: 'contactable', label: '可联系' },
];

const scoreOptions: FilterOption[] = [
  { value: 'all', label: '全部评分' },
  { value: 'gte85', label: '85+ 强推荐' },
  { value: '70_84', label: '70-84 可测试' },
  { value: '50_69', label: '50-69 观察' },
  { value: 'lt50', label: '<50 低分' },
];

const productOptions: FilterOption[] = [
  { value: 'all', label: '全部产品' },
  { value: 'wellness_self_care_bundle', label: '健康自护理组合' },
  { value: 'feminine_care', label: '女性护理' },
  { value: 'feminine_care_daily_liner', label: '日用护垫' },
  { value: 'period_care_pad', label: '经期护理' },
  { value: 'sensitive_skin_care', label: '敏感肌护理' },
  { value: 'travel_hygiene_pack', label: '旅行卫生包' },
  { value: 'postpartum_mom_care', label: '产后妈妈护理' },
  { value: 'teen_first_period_care', label: '青少初潮护理' },
  { value: 'mom_baby', label: '母婴护理' },
  { value: 'adult_care', label: '成人护理' },
  { value: 'pet_care', label: '宠物护理' },
  { value: 'home_care', label: '居家护理' },
  { value: 'health_mask', label: '健康防护口罩' },
  { value: 'general_lifestyle', label: '生活方式' },
];

const collabOptions: FilterOption[] = [
  { value: 'all', label: '全部合作' },
  { value: 'affiliate_collab', label: '联盟佣金合作' },
  { value: 'sample_collab', label: '样品合作' },
  { value: 'brand_awareness_collab', label: '品牌曝光合作' },
  { value: 'gifted_review', label: '赠品测评' },
  { value: 'paid_test_collab', label: '付费测试' },
  { value: 'do_not_contact_now', label: '暂不建联' },
];

const statusOptions: FilterOption[] = [
  { value: 'all', label: '全部状态' },
  { value: 'prospect', label: '待建联' },
  { value: 'new', label: '新达人' },
  { value: 'recommended', label: '推荐建联' },
  { value: 'recommended_after_review', label: '复核后推荐' },
  { value: 'low_cost_test', label: '低成本测试' },
  { value: 'affiliate_test', label: '联盟测试' },
  { value: 'brand_awareness_only', label: '品牌曝光' },
  { value: 'manual_review_before_outreach', label: '建联前复核' },
  { value: 'hold', label: '暂缓' },
  { value: 'not_recommended_now', label: '暂不推荐' },
  { value: 'no_contact_info', label: '无联系方式' },
  { value: '已建联', label: '已建联' },
  { value: 'contacted', label: '已联系' },
  { value: '待跟进', label: '待跟进' },
  { value: '沟通中', label: '沟通中' },
  { value: 'sample_shipped', label: '样品已寄' },
  { value: 'video_published', label: '视频已发布' },
  { value: 'ad_authorized', label: '广告已授权' },
  { value: 'ad_running', label: '广告投放中' },
];

const reviewOptions: FilterOption[] = [
  { value: 'clean', label: '无复核/风险' },
  { value: 'all', label: '全部复核状态' },
  { value: 'need_review', label: '需要复核' },
  { value: 'has_risk', label: '有风险提示' },
];

const ownerOptions: FilterOption[] = [
  { value: 'all', label: '全部归属' },
  { value: 'assigned', label: '已分配 BD' },
  { value: 'unassigned', label: '未分配 BD' },
];

const dateOptions: FilterOption[] = [
  { value: 'all', label: '全部入库时间' },
  { value: '1d', label: '近 24 小时' },
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
];

const sortOptions: FilterOption[] = [
  { value: 'recommended', label: '综合推荐排序' },
  { value: 'score', label: '评分从高到低' },
  { value: 'followers', label: '粉丝从高到低' },
  { value: 'fit', label: '产品匹配优先' },
  { value: 'priority', label: '优先级 P1 优先' },
  { value: 'recent', label: '最近入库优先' },
  { value: 'contactable', label: '可联系优先' },
  { value: 'micro', label: '小达人优先' },
];

const filterOptionLabels: Record<string, Record<string, string>> = {
  source: Object.fromEntries(sourceOptions.map((item) => [item.value, item.label])),
  priority: Object.fromEntries(priorityOptions.map((item) => [item.value, item.label])),
  contact: Object.fromEntries(contactOptions.map((item) => [item.value, item.label])),
  score: Object.fromEntries(scoreOptions.map((item) => [item.value, item.label])),
  product: Object.fromEntries(productOptions.map((item) => [item.value, item.label])),
  collab: Object.fromEntries(collabOptions.map((item) => [item.value, item.label])),
  status: Object.fromEntries(statusOptions.map((item) => [item.value, item.label])),
  review: Object.fromEntries(reviewOptions.map((item) => [item.value, item.label])),
  owner: Object.fromEntries(ownerOptions.map((item) => [item.value, item.label])),
  date: Object.fromEntries(dateOptions.map((item) => [item.value, item.label])),
  sort: Object.fromEntries(sortOptions.map((item) => [item.value, item.label])),
};

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
  const [jobPage, setJobPage] = useState(0);
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<AutoCampaign | null>(null);
  const [previewJob, setPreviewJob] = useState<AutoJob | null>(null);
  const [editingMailbox, setEditingMailbox] = useState<MailboxQuota | null>(null);
  const [scheduleType, setScheduleType] = useState<ScheduleType>('daily');
  const [selectedWeekdays, setSelectedWeekdays] = useState(['周一', '周二', '周三', '周四', '周五']);
  const [notice, setNotice] = useState('');
  const dashboardQ = useEmailAutoDashboard({
    job_status: selectedStatus,
    job_offset: jobPage * JOB_PAGE_SIZE,
    limit_jobs: JOB_PAGE_SIZE,
  });
  const syncMailboxes = useEmailAutoSyncMailboxes();
  const createCampaign = useEmailAutoCreateCampaign();
  const updateCampaign = useEmailAutoUpdateCampaign();
  const campaignStatus = useEmailAutoCampaignStatus();
  const updateMailbox = useEmailAutoMailboxUpdate();
  const removeMailbox = useEmailAutoMailboxRemove();
  const emailAutoActions = useEmailAutoActions();
  const showNotice = (message: string) => setNotice(message);

  useEffect(() => {
    setJobPage(0);
  }, [selectedStatus]);

  const openCreatePlan = () => {
    setEditingCampaign(null);
    setScheduleType('daily');
    setSelectedWeekdays(WEEKDAYS.slice(0, 5));
    setShowPlanModal(true);
  };

  const openEditPlan = (campaign: AutoCampaign) => {
    setEditingCampaign(campaign);
    setScheduleType(campaign.scheduleType);
    setSelectedWeekdays(campaign.weekdays.length ? campaign.weekdays : WEEKDAYS.slice(0, 5));
    setShowPlanModal(true);
  };

  const campaigns: AutoCampaign[] = useMemo(() => (dashboardQ.data?.campaigns ?? []).map((item) => ({
    id: item.id,
    name: item.name,
    status: item.status as CampaignStatus,
    scheduleType: item.schedule_type as ScheduleType,
    weekdays: Array.isArray(item.weekdays) ? item.weekdays : [],
    monthDays: Array.isArray(item.month_days) ? item.month_days : [],
    scheduleLabel: item.schedule_label,
    timeWindow: item.time_window,
    startTime: item.start_time,
    endTime: item.end_time,
    sent: item.sent,
    queueTotal: item.queue_total ?? item.daily_limit,
    dailyLimit: item.daily_limit,
    hourlyLimit: item.hourly_limit,
    intervalMinSeconds: item.interval_min_seconds,
    intervalMaxSeconds: item.interval_max_seconds,
    interval: item.interval,
    mailboxPool: item.mailbox_pool === 'all' ? '全部已启用绑定邮箱' : item.mailbox_pool,
    mailboxPoolValue: item.mailbox_pool,
    sendMode: item.send_mode,
    filtersRaw: item.filters ?? {},
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
  const jobStatusCounts = useMemo(() => {
    if (dashboardQ.data?.job_status_counts) return dashboardQ.data.job_status_counts;
    return jobs.reduce<Record<string, number>>((acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    }, {});
  }, [dashboardQ.data?.job_status_counts, jobs]);

  const filteredJobs = useMemo(
    () => jobs.filter((item) => selectedStatus === 'all' || item.status === selectedStatus),
    [jobs, selectedStatus],
  );
  const filteredJobTotal = dashboardQ.data?.jobs_total ?? filteredJobs.length;
  const totalJobPages = Math.max(1, Math.ceil(filteredJobTotal / JOB_PAGE_SIZE));
  const currentJobPage = Math.min(jobPage, totalJobPages - 1);
  const jobPageStart = filteredJobTotal > 0 ? currentJobPage * JOB_PAGE_SIZE + 1 : 0;
  const jobPageEnd = Math.min(filteredJobTotal, (currentJobPage + 1) * JOB_PAGE_SIZE);
  useEffect(() => {
    if (jobPage > totalJobPages - 1) {
      setJobPage(totalJobPages - 1);
    }
  }, [jobPage, totalJobPages]);

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
          <div className="num font-semibold text-gray-900">{row.sent}/{row.queueTotal}</div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, (row.sent / Math.max(1, row.queueTotal)) * 100)}%` }} />
          </div>
          <div className="mt-1 text-xxs text-muted">{row.hourlyLimit}/小时 · 计划总量 {row.dailyLimit}</div>
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
          <button className="btn btn-ghost" onClick={() => openEditPlan(row)}><Edit3 size={13} />编辑</button>
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
            onClick={() => emailAutoActions.generateJobs.mutate({ id: row.id, limit: row.dailyLimit }, { onSuccess: (res) => showNotice(res.reason || `已生成 ${res.created_jobs} 个队列任务`) })}
          ><Sparkles size={13} />补充队列</button>
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
              <button className="btn btn-primary" onClick={openCreatePlan}><CalendarClock size={14} />新建计划</button>
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

      <section className="card">
          <div className="card-body border-b border-line">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">运行计划</h3>
                <p className="mt-0.5 text-xxs text-muted">支持每天 / 每周指定周几 / 每月指定日期，发送窗口精确到小时分钟。</p>
              </div>
              <button className="btn btn-primary" onClick={openCreatePlan}><Sparkles size={13} />创建自动发送计划</button>
            </div>
          </div>
          <DataTable columns={campaignColumns} data={campaigns} rowKey={(row) => row.id} emptyText={dashboardQ.isLoading ? '正在读取自动邮件计划…' : '暂无自动发送计划'} />
        </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="card min-w-0">
        <div className="card-body border-b border-line">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">邮箱健康</h3>
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
        <HealthCheckPanel result={emailAutoActions.healthCheck.isPending ? null : (emailAutoActions.healthCheck.data ?? null)} running={emailAutoActions.healthCheck.isPending} />
      </section>

        <section className="card min-w-0">
        <div className="card-body border-b border-line">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">任务队列</h3>
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
        <div className="flex flex-col gap-2 border-t border-line px-4 py-3 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <span>显示 {jobPageStart}-{jobPageEnd} / {filteredJobTotal} 条</span>
          <div className="flex items-center gap-2">
            <button
              className="btn"
              disabled={dashboardQ.isFetching || currentJobPage <= 0}
              onClick={() => setJobPage((page) => Math.max(0, page - 1))}
            >
              上一页
            </button>
            <span className="num text-xxs text-gray-500">{currentJobPage + 1}/{totalJobPages}</span>
            <button
              className="btn"
              disabled={dashboardQ.isFetching || currentJobPage >= totalJobPages - 1}
              onClick={() => setJobPage((page) => Math.min(totalJobPages - 1, page + 1))}
            >
              下一页
            </button>
          </div>
        </div>
        </section>
      </div>

      {showPlanModal && (
        <PlanModal
          campaign={editingCampaign}
          scheduleType={scheduleType}
          selectedWeekdays={selectedWeekdays}
          mailboxes={mailboxes}
          onScheduleTypeChange={setScheduleType}
          onWeekdaysChange={setSelectedWeekdays}
          onClose={() => {
            setShowPlanModal(false);
            setEditingCampaign(null);
          }}
          onPreview={(payload) => {
            emailAutoActions.previewCampaign.mutate(payload, {
              onSuccess: (res) => setPreviewJob(mapApiJob(res.item)),
              onError: (error) => showNotice(error instanceof Error ? error.message : '没有找到符合筛选条件的达人'),
            });
          }}
          onSubmit={(payload) => {
            if (editingCampaign) {
              updateCampaign.mutate({ id: editingCampaign.id, body: payload }, {
                onSuccess: (res) => {
                  setShowPlanModal(false);
                  setEditingCampaign(null);
                  showNotice(res.reason || '计划已保存');
                },
              });
              return;
            }
            createCampaign.mutate(payload, {
              onSuccess: (res) => {
                setShowPlanModal(false);
                setEditingCampaign(null);
                showNotice(res.reason || `计划已创建，生成 ${res.created_jobs} 个真实队列任务`);
              },
            });
          }}
          submitting={createCampaign.isPending || updateCampaign.isPending}
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
  for (const key of ['source', 'priority', 'contact', 'score', 'product', 'collab', 'status', 'review', 'owner', 'date', 'sort']) {
    const value = String(filters[key] ?? 'all');
    const label = filterOptionLabels[key]?.[value];
    if (label && !label.startsWith('全部')) labels.push(label);
  }
  const keyword = String(filters.keyword ?? '').trim();
  if (keyword) labels.push(`关键词 ${keyword}`);
  const minFollowers = filters.min_followers;
  const maxFollowers = filters.max_followers;
  if (minFollowers || maxFollowers) labels.push(`粉丝 ${minFollowers || 0}-${maxFollowers || '不限'}`);
  if (filters.pause_on_failure) labels.push('失败暂停');
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

function normalizeRecommendationFilters(filters?: Record<string, unknown> | null): RecommendationFilters {
  const source = filters ?? {};
  const toText = (key: keyof RecommendationFilters) => String(source[key] ?? DEFAULT_RECOMMENDATION_FILTERS[key] ?? '');
  const toNumberText = (key: 'min_followers' | 'max_followers') => {
    const value = source[key];
    return value === undefined || value === null || value === '' ? '' : String(value);
  };
  return {
    keyword: toText('keyword'),
    source: toText('source'),
    priority: toText('priority'),
    contact: toText('contact'),
    score: toText('score'),
    product: toText('product'),
    collab: toText('collab'),
    status: toText('status'),
    review: toText('review'),
    owner: toText('owner'),
    date: toText('date'),
    sort: toText('sort'),
    min_followers: toNumberText('min_followers'),
    max_followers: toNumberText('max_followers'),
  };
}

function formatDurationCompact(totalSeconds: number) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const restSeconds = seconds % 60;
  if (minutes < 60) return restSeconds ? `${minutes} 分 ${restSeconds} 秒` : `${minutes} 分`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return restMinutes ? `${hours} 小时 ${restMinutes} 分` : `${hours} 小时`;
}

function PlanModal({
  campaign,
  scheduleType,
  selectedWeekdays,
  mailboxes,
  onScheduleTypeChange,
  onWeekdaysChange,
  onClose,
  onPreview,
  onSubmit,
  submitting,
  previewing,
}: {
  campaign?: AutoCampaign | null;
  scheduleType: ScheduleType;
  selectedWeekdays: string[];
  mailboxes: MailboxQuota[];
  onScheduleTypeChange: (value: ScheduleType) => void;
  onWeekdaysChange: (value: string[]) => void;
  onClose: () => void;
  onPreview: (payload: EmailAutoCampaignCreate) => void;
  onSubmit: (payload: EmailAutoCampaignCreate) => void;
  submitting?: boolean;
  previewing?: boolean;
}) {
  const isEditing = Boolean(campaign);
  const [planName, setPlanName] = useState(campaign?.name ?? '客户推荐库每日首封');
  const [startTime, setStartTime] = useState(campaign?.startTime ?? '09:30');
  const [endTime, setEndTime] = useState(campaign?.endTime ?? '18:00');
  const [dailyLimit, setDailyLimit] = useState(campaign?.dailyLimit ?? 300);
  const [hourlyLimit, setHourlyLimit] = useState(campaign?.hourlyLimit ?? 40);
  const [intervalMin, setIntervalMin] = useState(campaign?.intervalMinSeconds ?? 90);
  const [intervalMax, setIntervalMax] = useState(campaign?.intervalMaxSeconds ?? 240);
  const [sendMode, setSendMode] = useState<'draft' | 'send'>(campaign?.sendMode === 'draft' ? 'draft' : 'send');
  const [mailboxPool, setMailboxPool] = useState(campaign?.mailboxPoolValue || 'all');
  const [pauseOnFailure, setPauseOnFailure] = useState(Boolean(campaign?.filtersRaw?.pause_on_failure));
  const [candidateLimit, setCandidateLimit] = useState(campaign?.dailyLimit ?? 200);
  const [filters, setFilters] = useState<RecommendationFilters>(() => normalizeRecommendationFilters(campaign?.filtersRaw));
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
  const activeMailboxCount = Math.max(1, usableMailboxes.length || capacityMailboxes.length);
  const intervalFloor = Math.max(30, Math.min(intervalMin, intervalMax) || 30);
  const intervalCeiling = Math.max(intervalFloor, Math.max(intervalMin, intervalMax) || intervalFloor);
  const maxTasksPerMailbox = Math.ceil(protectedCandidateLimit / activeMailboxCount);
  const intervalSlotsPerMailbox = Math.max(0, maxTasksPerMailbox - 1);
  const estimatedMinSeconds = intervalSlotsPerMailbox * intervalFloor;
  const estimatedMaxSeconds = intervalSlotsPerMailbox * intervalCeiling;
  const estimatedAverageSeconds = intervalSlotsPerMailbox * Math.round((intervalFloor + intervalCeiling) / 2);
  const estimatedDurationLabel = estimatedMinSeconds === estimatedMaxSeconds
    ? formatDurationCompact(estimatedAverageSeconds)
    : `${formatDurationCompact(estimatedMinSeconds)} - ${formatDurationCompact(estimatedMaxSeconds)}`;
  const dailySlotsPerMailbox = Math.max(0, Math.ceil(protectedDailyLimit / activeMailboxCount) - 1);
  const estimatedDailyMinSeconds = dailySlotsPerMailbox * intervalFloor;
  const estimatedDailyMaxSeconds = dailySlotsPerMailbox * intervalCeiling;
  const estimatedDailyAverageSeconds = dailySlotsPerMailbox * Math.round((intervalFloor + intervalCeiling) / 2);
  const estimatedDailyDurationLabel = estimatedDailyMinSeconds === estimatedDailyMaxSeconds
    ? formatDurationCompact(estimatedDailyAverageSeconds)
    : `${formatDurationCompact(estimatedDailyMinSeconds)} - ${formatDurationCompact(estimatedDailyMaxSeconds)}`;

  const toggleWeekday = (day: string) => {
    if (selectedWeekdays.includes(day)) {
      onWeekdaysChange(selectedWeekdays.filter((item) => item !== day));
    } else {
      onWeekdaysChange([...selectedWeekdays, day]);
    }
  };

  const updateFilter = (key: keyof RecommendationFilters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const filterPayload = () => ({
    keyword: filters.keyword.trim(),
    source: filters.source,
    priority: filters.priority,
    contact: filters.contact,
    score: filters.score,
    product: filters.product,
    collab: filters.collab,
    status: filters.status,
    review: filters.review,
    owner: filters.owner,
    date: filters.date,
    sort: filters.sort,
    min_followers: filters.min_followers ? Number(filters.min_followers) : null,
    max_followers: filters.max_followers ? Number(filters.max_followers) : null,
    pause_on_failure: pauseOnFailure,
  });

  const createPayload = (): EmailAutoCampaignCreate => ({
    name: planName,
    status: campaign?.status ?? 'running',
    schedule_type: scheduleType,
    weekdays: selectedWeekdays,
    month_days: campaign?.monthDays?.length ? campaign.monthDays : [1],
    start_time: startTime,
    end_time: endTime,
    daily_limit: protectedDailyLimit,
    hourly_limit: protectedHourlyLimit,
    interval_min_seconds: Math.min(intervalMin, intervalMax),
    interval_max_seconds: Math.max(intervalMin, intervalMax),
    mailbox_pool: mailboxPool,
    send_mode: sendMode,
    filters: filterPayload(),
    generate_jobs: !isEditing,
    candidate_limit: protectedCandidateLimit,
  });

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-4">
      <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line p-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">{isEditing ? '编辑自动发送计划' : '新建自动发送计划'}</h3>
            <p className="mt-1 text-xs text-muted">{isEditing ? '只更新计划配置，不自动补充新队列任务。' : '计划会写入数据库，并按客户推荐库筛选生成真实队列任务。'}</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}><X size={14} />关闭</button>
        </div>

        <div className="overflow-y-auto p-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <FormField label="计划名称">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" value={planName} onChange={(event) => setPlanName(event.target.value)} />
            </FormField>
            <FormField label="邮箱池">
              <select className="w-full rounded-md border border-line px-3 py-2 text-xs" value={mailboxPool} onChange={(event) => setMailboxPool(event.target.value)}>
                <option value="all">全部已启用绑定邮箱</option>
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
            <FormField label="失败处理">
              <div className="flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-xs text-gray-800">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-line text-brand-600"
                  checked={pauseOnFailure}
                  onChange={(event) => setPauseOnFailure(event.target.checked)}
                />
                <span>发送失败立即暂停计划</span>
              </div>
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
              <QuotaStat label="单邮箱最多分摊" value={`${maxTasksPerMailbox} 封`} />
              <QuotaStat label="本次队列预计耗时" value={estimatedDurationLabel} />
              <QuotaStat label="日总量预计耗时" value={estimatedDailyDurationLabel} />
            </div>
            <div className="mt-2 text-xxs text-amber-700">
              单邮箱发送间隔按每个发件邮箱分别计算，系统会用可用邮箱并行分摊队列；每封真实发送前都会重新检查发件邮箱今日已发量，单个邮箱达到额度后会自动换邮箱，没有可用额度时任务停在队列中。
              {dailyLimitAdjusted ? ` 当前每日总量已从 ${dailyLimit} 自动按邮箱池日额度收紧到 ${protectedDailyLimit}。` : ''}
              {candidateLimitAdjusted ? ` 当前队列数已从 ${candidateLimit} 自动按计划日上限和单次生成上限收紧到 ${protectedCandidateLimit}。` : ''}
              {todayExecutableLimit < protectedDailyLimit ? ` 按今日剩余额度，本日最多还能实际发送 ${todayExecutableLimit} 封。` : ''}
            </div>
          </div>

          <div className="mt-4 rounded-md border border-line p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900"><Users size={15} />达人筛选条件</div>
            <RecommendationRulesPanel filters={filters} onChange={updateFilter} />
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
          <button className="btn btn-primary" disabled={submitting} onClick={() => onSubmit(createPayload())}>{isEditing ? '保存计划' : '创建真实计划'}</button>
        </div>
      </div>
    </div>
  );
}

function RecommendationRulesPanel({
  filters,
  onChange,
  compact = false,
  readOnly = false,
}: {
  filters: RecommendationFilters;
  onChange: (key: keyof RecommendationFilters, value: string) => void;
  compact?: boolean;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
        <div className="font-semibold text-blue-800">沿用客户推荐库高级筛选规则</div>
        <div className="mt-1 text-xxs">所有条件均为固定选项，保存计划时按当前选择写入筛选规则。</div>
      </div>

      <div className={cn('grid gap-3', compact ? 'grid-cols-1' : 'md:grid-cols-2 xl:grid-cols-3')}>
        <RecommendationRuleText
          label="关键词搜索"
          value={filters.keyword}
          placeholder="handle / 邮箱 / 商品 / 推荐理由"
          readOnly={readOnly}
          onChange={(value) => onChange('keyword', value)}
        />
        <RecommendationRuleSelect label="来源" value={filters.source} options={sourceOptions} readOnly={readOnly} onChange={(value) => onChange('source', value)} />
        <RecommendationRuleSelect label="优先级" value={filters.priority} options={priorityOptions} readOnly={readOnly} onChange={(value) => onChange('priority', value)} />
        <RecommendationRuleSelect label="联系方式" value={filters.contact} options={contactOptions} readOnly={readOnly} onChange={(value) => onChange('contact', value)} />
        <RecommendationRuleSelect label="评分" value={filters.score} options={scoreOptions} readOnly={readOnly} onChange={(value) => onChange('score', value)} />
        <RecommendationRuleSelect label="产品" value={filters.product} options={productOptions} readOnly={readOnly} onChange={(value) => onChange('product', value)} />
        <RecommendationRuleSelect label="合作" value={filters.collab} options={collabOptions} readOnly={readOnly} onChange={(value) => onChange('collab', value)} />
        <RecommendationRuleSelect label="建联状态" value={filters.status} options={statusOptions} readOnly={readOnly} onChange={(value) => onChange('status', value)} />
        <RecommendationRuleSelect label="复核状态" value={filters.review} options={reviewOptions} readOnly={readOnly} onChange={(value) => onChange('review', value)} />
        <RecommendationRuleSelect label="归属" value={filters.owner} options={ownerOptions} readOnly={readOnly} onChange={(value) => onChange('owner', value)} />
        <RecommendationRuleSelect label="入库时间" value={filters.date} options={dateOptions} readOnly={readOnly} onChange={(value) => onChange('date', value)} />
        <RecommendationRuleSelect label="排序" value={filters.sort} options={sortOptions} readOnly={readOnly} onChange={(value) => onChange('sort', value)} />
        <div>
          <div className="mb-1 text-xxs font-semibold text-muted">粉丝区间</div>
          <div className="grid grid-cols-2 gap-2">
            <input
              className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs outline-none focus:border-brand-300 disabled:bg-soft"
              placeholder="最小"
              value={filters.min_followers}
              disabled={readOnly}
              inputMode="numeric"
              onChange={(event) => onChange('min_followers', event.target.value.replace(/[^0-9]/g, ''))}
            />
            <input
              className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs outline-none focus:border-brand-300 disabled:bg-soft"
              placeholder="最大"
              value={filters.max_followers}
              disabled={readOnly}
              inputMode="numeric"
              onChange={(event) => onChange('max_followers', event.target.value.replace(/[^0-9]/g, ''))}
            />
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

function RecommendationRuleSelect({
  label,
  options,
  value,
  onChange,
  readOnly = false,
}: {
  label: string;
  options: FilterOption[];
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xxs font-semibold text-muted">{label}</span>
      <select
        className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs text-gray-800 outline-none focus:border-brand-300 disabled:bg-soft"
        value={value}
        disabled={readOnly}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function RecommendationRuleText({
  label,
  value,
  placeholder,
  onChange,
  readOnly = false,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xxs font-semibold text-muted">{label}</span>
      <input
        className="h-9 w-full rounded-md border border-line bg-white px-3 text-xs outline-none focus:border-brand-300 disabled:bg-soft"
        value={value}
        placeholder={placeholder}
        disabled={readOnly}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function HealthCheckPanel({
  result,
  running,
}: {
  result: EmailAutoHealthCheckResponse | null;
  running: boolean;
}) {
  if (!running && !result) return null;
  const items = result?.items ?? [];
  return (
    <div className="border-t border-line bg-soft/60 p-4">
      <div className="rounded-md border border-line bg-white">
        <div className="flex flex-col gap-2 border-b border-line px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
              <ShieldCheck size={15} className={running ? 'text-blue-600' : 'text-green-600'} />
              批量健康检查动作状态
            </div>
            <div className="mt-1 text-xxs text-muted">
              {running
                ? '正在执行真实 Gmail 内部互发互读，完成后显示每个邮箱的发送、等待、读取和状态更新结果。'
                : `完成时间 ${result?.completed_at ? formatShortTime(result.completed_at) : '-'} · ${result?.passed ?? 0}/${result?.total ?? 0} 通过`}
            </div>
          </div>
          {result ? (
            <div className="flex flex-wrap gap-2">
              <Pill tone="good">通过 {result.passed}</Pill>
              <Pill tone={result.failed > 0 ? 'warn' : 'muted'}>失败 {result.failed}</Pill>
              {result.marker ? <Pill tone="muted">{result.marker}</Pill> : null}
            </div>
          ) : (
            <Pill tone="info">检查中</Pill>
          )}
        </div>

        {running && items.length === 0 ? (
          <div className="grid gap-2 p-4 text-xs text-muted md:grid-cols-5">
            {['准备邮箱池', '发送测试邮件', '等待邮件入箱', '读取收件箱确认', '更新邮箱状态'].map((label, index) => (
              <div key={label} className="flex items-center gap-2 rounded border border-line bg-white px-3 py-2">
                {index === 0 ? <RefreshCw size={13} className="animate-spin text-blue-600" /> : <span className="h-2 w-2 rounded-full bg-gray-300" />}
                <span>{label}</span>
              </div>
            ))}
          </div>
        ) : null}

        {items.length > 0 ? (
          <div className="grid gap-3 p-4">
            {items.map((item, index) => (
              <div key={item.check_id || `${item.sender_email}-${index}`} className="rounded-md border border-line bg-white p-3">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="num text-xs font-semibold text-gray-900">
                      {item.sender_email || '-'} <span className="text-muted">-&gt;</span> {item.recipient_email || '-'}
                    </div>
                    <div className="mt-1 text-xxs text-muted">
                      当前动作：{item.current_action || healthStatusLabel(item.status)}
                      {item.reason ? ` · ${item.reason}` : ''}
                    </div>
                  </div>
                  <HealthStatusBadge status={item.status} />
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-5">
                  {(item.steps || []).map((step) => (
                    <div key={step.action} className="rounded border border-line bg-soft px-3 py-2">
                      <div className="flex items-center gap-2 text-xxs font-semibold text-gray-800">
                        <StepDot status={step.status} />
                        <span>{step.label}</span>
                      </div>
                      <div className="mt-1 text-[11px] leading-4 text-muted">{step.detail || healthStatusLabel(step.status)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function HealthStatusBadge({ status }: { status: string }) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'passed') return <Pill tone="good">通过</Pill>;
  if (normalized === 'failed') return <Pill tone="warn">失败</Pill>;
  if (normalized === 'sent' || normalized === 'running' || normalized === 'pending') return <Pill tone="info">执行中</Pill>;
  return <Pill tone="muted">{healthStatusLabel(status)}</Pill>;
}

function StepDot({ status }: { status: string }) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'passed') return <CheckCircle2 size={13} className="text-green-600" />;
  if (normalized === 'failed') return <X size={13} className="text-red-500" />;
  if (normalized === 'running') return <RefreshCw size={13} className="animate-spin text-blue-600" />;
  if (normalized === 'skipped') return <span className="h-2 w-2 rounded-full bg-amber-400" />;
  return <span className="h-2 w-2 rounded-full bg-gray-300" />;
}

function healthStatusLabel(status: string) {
  const normalized = String(status || '').toLowerCase();
  return ({
    pending: '等待中',
    running: '执行中',
    sent: '已发送',
    passed: '通过',
    failed: '失败',
    skipped: '已跳过',
  } as Record<string, string>)[normalized] || status || '-';
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
