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
  Users,
  X,
} from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { cn } from '@/lib/cn';
import { useProductAssets } from '@/hooks/useApi';
import type { ProductAsset } from '@/api/types';

type CampaignStatus = 'running' | 'paused' | 'draft';
type MailboxStatus = 'normal' | 'cooldown' | 'limit' | 'auth_expired' | 'bounce_risk';
type JobStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'skipped';
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
}

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const campaigns: AutoCampaign[] = [
  {
    id: 'campaign-us-daily',
    name: '客户推荐库每日首封',
    status: 'running',
    scheduleType: 'daily',
    scheduleLabel: '每天',
    timeWindow: '09:30-18:00',
    sent: 128,
    dailyLimit: 300,
    hourlyLimit: 40,
    interval: '90-240s',
    mailboxPool: '全部已启用绑定邮箱',
    filters: ['客户推荐库', '有邮箱', '未建联', 'Fit S/A/B', '30 天未联系', '美国/加拿大'],
    action: '发送后更新达人状态并进入邮件跟踪系统',
  },
  {
    id: 'campaign-mid-tier',
    name: '中腰部达人每周测试',
    status: 'paused',
    scheduleType: 'weekly',
    scheduleLabel: '每周一、周三、周五',
    timeWindow: '14:00-17:30',
    sent: 46,
    dailyLimit: 120,
    hourlyLimit: 24,
    interval: '150-360s',
    mailboxPool: 'Creator Team 邮箱池',
    filters: ['客户推荐库', 'P1/P2 优先', '可联系', '粉丝 5k-80k', '合作: 寄样测评'],
    action: '先生成草稿，人工确认后发送',
  },
];

const mailboxes: MailboxQuota[] = [
  {
    id: 'x9m5155',
    email: 'x9m5155@gmail.com',
    owner: 'X9 Outreach',
    status: 'normal',
    enabled: true,
    autoSent: 22,
    quota: 60,
    replies: 4,
    bounces: 1,
    failures: 0,
    nextSendAt: '2 分钟后',
    lastSyncAt: '刚刚',
  },
  {
    id: 'sanitex002',
    email: 'sanitex002@gmail.com',
    owner: 'Sanitex Collab',
    status: 'cooldown',
    enabled: true,
    autoSent: 40,
    quota: 40,
    replies: 2,
    bounces: 3,
    failures: 1,
    nextSendAt: '明天 09:30',
    lastSyncAt: '8 分钟前',
  },
  {
    id: 'hello-x9',
    email: 'hello.x9outreach@gmail.com',
    owner: 'X9 Creator Team',
    status: 'normal',
    enabled: true,
    autoSent: 18,
    quota: 80,
    replies: 6,
    bounces: 0,
    failures: 0,
    nextSendAt: '可立即发送',
    lastSyncAt: '3 分钟前',
  },
  {
    id: 'ops-x9',
    email: 'creator.ops.x9@gmail.com',
    owner: 'Creator Ops',
    status: 'auth_expired',
    enabled: false,
    autoSent: 0,
    quota: 50,
    replies: 0,
    bounces: 0,
    failures: 4,
    nextSendAt: '需重新授权',
    lastSyncAt: '2 天前',
  },
];

const jobs: AutoJob[] = [
  {
    id: 'job-1042',
    time: '10:42',
    creator: '@hannah.waits.for.no.one',
    recipient: 'hannah.carolinaa@creator.co',
    sender: 'x9m5155@gmail.com',
    product: 'Green Full Category + AI 图片',
    plan: '客户推荐库每日首封',
    status: 'pending',
    reason: '间隔等待',
    filters: ['P1', 'Fit S', 'Home & Kitchen'],
  },
  {
    id: 'job-1038',
    time: '10:38',
    creator: '@momlife_oasis',
    recipient: 'hello@momoasis.com',
    sender: 'hello.x9outreach@gmail.com',
    product: 'Pink Series + AI 图片',
    plan: '客户推荐库每日首封',
    status: 'sent',
    reason: '已进入邮件跟踪',
    filters: ['P2', 'Fit A', '美区'],
  },
  {
    id: 'job-1034',
    time: '10:34',
    creator: '@preview_creator',
    recipient: 'preview.creator@email.com',
    sender: 'x9m5155@gmail.com',
    product: 'Auto Matched Product + AI 图片',
    plan: '中腰部达人每周测试',
    status: 'failed',
    reason: '邮箱处于冷却',
    filters: ['P2', '可联系', '粉丝 5k-80k'],
  },
  {
    id: 'job-1029',
    time: '10:29',
    creator: '@familycare_daily',
    recipient: 'contact@familycare.co',
    sender: 'hello.x9outreach@gmail.com',
    product: 'Baby Care + AI 图片',
    plan: '客户推荐库每日首封',
    status: 'sending',
    reason: '正在发送',
    filters: ['P1', 'Fit A', '30 天未联系'],
  },
];

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
  const productAssetsQuery = useProductAssets();
  const selectedProductAsset = useMemo(() => {
    const items = productAssetsQuery.data?.items ?? [];
    return productAssetsQuery.data?.matched || items.find((item) => item.image_url) || items[0] || null;
  }, [productAssetsQuery.data?.items, productAssetsQuery.data?.matched]);
  const showNotice = (message: string) => setNotice(`${message} · 本地预览`);

  const totalSent = campaigns.reduce((sum, item) => sum + item.sent, 0);
  const totalTarget = campaigns.reduce((sum, item) => sum + item.dailyLimit, 0);
  const availableMailboxes = mailboxes.filter((item) => item.enabled && item.status === 'normal').length;
  const riskMailboxes = mailboxes.filter((item) => item.status !== 'normal').length;
  const queueCount = 742;
  const replyCount = mailboxes.reduce((sum, item) => sum + item.replies, 0);
  const bounceCount = mailboxes.reduce((sum, item) => sum + item.bounces, 0);

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
          <button className="btn btn-ghost" onClick={() => showNotice(row.status === 'paused' ? '已模拟恢复计划' : '已模拟暂停计划')}>{row.status === 'paused' ? <Play size={13} /> : <Pause size={13} />}{row.status === 'paused' ? '恢复' : '暂停'}</button>
          <button className="btn btn-ghost" onClick={() => setShowPlanModal(true)}><Edit3 size={13} />编辑</button>
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
        <button className="btn btn-ghost" onClick={() => setPreviewJob(row)}><Eye size={13} />邮件预览</button>
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
              <button className="btn" onClick={() => showNotice('已模拟暂停全部计划')}><Pause size={14} />暂停全部</button>
              <button className="btn" onClick={() => showNotice('已模拟同步当前绑定邮箱')}><RefreshCw size={14} />同步邮箱</button>
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
          <DataTable columns={campaignColumns} data={campaigns} rowKey={(row) => row.id} />
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
              <button className="btn" onClick={() => showNotice('已模拟同步绑定邮箱')}><RefreshCw size={13} />同步绑定邮箱</button>
              <button className="btn" onClick={() => showNotice('已模拟批量健康检查')}><ShieldCheck size={13} />批量健康检查</button>
            </div>
          </div>
        </div>
        <DataTable columns={mailboxColumns} data={mailboxes} rowKey={(row) => row.id} />
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
                ['pending', '待发送 742'],
                ['sending', '发送中 1'],
                ['sent', '已发送 128'],
                ['failed', '失败 5'],
                ['skipped', '已跳过 31'],
              ].map(([key, label]) => (
                <button
                  key={key}
                  className={cn('btn', selectedStatus === key && 'border-brand-500 bg-blue-50 text-brand-600')}
                  onClick={() => setSelectedStatus(key as 'all' | JobStatus)}
                >
                  {label}
                </button>
              ))}
              <button className="btn" onClick={() => showNotice('已模拟重试失败任务')}><RefreshCw size={13} />重试失败</button>
            </div>
          </div>
        </div>
        <DataTable columns={jobColumns} data={filteredJobs} rowKey={(row) => row.id} emptyText="当前筛选下暂无任务" />
      </section>

      {showPlanModal && (
        <PlanModal
          scheduleType={scheduleType}
          selectedWeekdays={selectedWeekdays}
          onScheduleTypeChange={setScheduleType}
          onWeekdaysChange={setSelectedWeekdays}
          onClose={() => setShowPlanModal(false)}
          onPreview={() => setPreviewJob(jobs[0])}
          onCreate={() => {
            setShowPlanModal(false);
            showNotice('已模拟创建预览计划');
          }}
        />
      )}

      {previewJob && (
        <MailPreviewModal
          job={previewJob}
          productAsset={selectedProductAsset}
          productAssetsLoading={productAssetsQuery.isLoading}
          onClose={() => setPreviewJob(null)}
        />
      )}

      {editingMailbox && (
        <MailboxModal
          mailbox={editingMailbox}
          onClose={() => setEditingMailbox(null)}
          onNotice={showNotice}
        />
      )}
    </div>
  );
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
  onScheduleTypeChange,
  onWeekdaysChange,
  onClose,
  onPreview,
  onCreate,
}: {
  scheduleType: ScheduleType;
  selectedWeekdays: string[];
  onScheduleTypeChange: (value: ScheduleType) => void;
  onWeekdaysChange: (value: string[]) => void;
  onClose: () => void;
  onPreview: () => void;
  onCreate: () => void;
}) {
  const [startTime, setStartTime] = useState('09:30');
  const [endTime, setEndTime] = useState('18:00');
  const usTimeReference = buildUsTimeReference(startTime, endTime);

  const toggleWeekday = (day: string) => {
    if (selectedWeekdays.includes(day)) {
      onWeekdaysChange(selectedWeekdays.filter((item) => item !== day));
    } else {
      onWeekdaysChange([...selectedWeekdays, day]);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-4">
      <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line p-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">新建自动发送计划</h3>
            <p className="mt-1 text-xs text-muted">预览页只更新本地 mock 数据，不写入数据库。</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}><X size={14} />关闭</button>
        </div>

        <div className="overflow-y-auto p-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <FormField label="计划名称">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="客户推荐库每日首封" />
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
            <FormField label="每日总量">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="300" />
            </FormField>
            <FormField label="每小时上限">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="40" />
            </FormField>
            <FormField label="随机间隔">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="90-240 秒" />
            </FormField>
            <FormField label="发送方式">
              <select className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue="send">
                <option value="send">生成并自动发送</option>
                <option value="draft">只生成草稿不发送</option>
              </select>
            </FormField>
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
          <button className="btn" onClick={onPreview}><Eye size={13} />邮件预览</button>
          <button className="btn btn-primary" onClick={onCreate}>创建预览计划</button>
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

function MailboxModal({ mailbox, onClose, onNotice }: { mailbox: MailboxQuota; onClose: () => void; onNotice: (message: string) => void }) {
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
              <select className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue={mailbox.enabled ? 'enabled' : 'disabled'}>
                <option value="enabled">启用自动发送</option>
                <option value="disabled">暂停此邮箱</option>
              </select>
            </FormField>
            <FormField label="每日数量额度">
              <input className="w-full rounded-md border border-line px-3 py-2 text-xs" defaultValue={mailbox.quota} />
            </FormField>
          </div>
          <div className="rounded-md border border-line bg-soft p-3 text-xs text-muted">
            后续接真实接口时，这里会保存 Gmail 授权标签、启用状态、每日自动发送额度、冷却时间和健康阈值。
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-line p-4">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn" onClick={() => onNotice('已模拟重新授权邮箱')}><RefreshCw size={13} />重新授权</button>
          <button className="btn btn-primary" onClick={() => { onClose(); onNotice('已模拟保存邮箱配置'); }}>保存配置</button>
        </div>
      </div>
    </div>
  );
}

function MailPreviewModal({
  job,
  productAsset,
  productAssetsLoading,
  onClose,
}: {
  job: AutoJob;
  productAsset: ProductAsset | null;
  productAssetsLoading: boolean;
  onClose: () => void;
}) {
  const preview = buildUserSideAiPreview(job, productAsset);
  const html = buildEmailHtml(preview);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line p-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">邮件预览</h3>
            <p className="mt-1 text-xs text-muted">创建任务时调用用户端同一套 AI 图片和 20% commission 话术预览。</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}><X size={14} />关闭</button>
        </div>
        <div className="overflow-y-auto bg-soft p-4">
          <div className="rounded-lg border border-line bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Pill tone="good">已替换为 AI 邀约话术</Pill>
              <Pill tone={preview.imageUrl ? 'info' : 'warn'}>{preview.imageUrl ? '系统 SKU 图片' : productAssetsLoading ? '正在读取系统图片' : '未读取到系统图片'}</Pill>
              <Pill tone="muted">{job.plan}</Pill>
            </div>
            <div className="grid gap-4">
              <div className="hidden">
                <div className="aspect-[4/5] overflow-hidden rounded-lg border border-cyan-200 bg-white">
                  <img src={preview.imageUrl} alt={preview.productName} className="h-full w-full object-cover" />
                </div>
                <div className="mt-3 text-sm font-bold text-cyan-900">{preview.productName}</div>
                <div className="mt-1 text-xs text-cyan-700">Generated product image preview</div>
              </div>
              <div className="space-y-3">
                <PreviewField label="收件人" value={job.recipient} />
                <PreviewField label="主题" value={preview.subject} />
                <div className="rounded-md border border-line bg-white">
                  <div className="flex items-center justify-between border-b border-line px-3 py-2">
                    <div className="flex items-center gap-2 text-xs font-semibold text-gray-800">最终邮件效果</div>
                    <label className="hidden">
                      <input type="checkbox" checked readOnly />
                      插入图片
                    </label>
                  </div>
                  <div className="grid gap-3 p-3">
                    <div className="overflow-hidden rounded-md border border-line bg-gray-50 p-3">
                      <div className="mx-auto max-w-[520px] rounded border border-line bg-white p-3" dangerouslySetInnerHTML={{ __html: html }} />
                    </div>
                    <div className="hidden">
                      <div className="rounded-md border border-line bg-soft p-3">
                        <div className="font-semibold text-gray-900">图片设置</div>
                        <div className="mt-2 grid gap-2">
                          <Row label="位置" value="正文开头" />
                          <Row label="对齐" value="居中" />
                          <Row label="宽度" value="560px" />
                          <Row label="说明" value="自动匹配 SKU 图片" />
                        </div>
                      </div>
                      <div className="rounded-md border border-green-200 bg-green-50 p-3 text-green-700">
                        发送后达人状态更新为已发送首封，并进入邮件跟踪系统。
                      </div>
                    </div>
                  </div>
                </div>
                <label className="hidden">
                  <span className="mb-1 block text-xxs font-semibold text-muted">正文</span>
                  <textarea className="h-48 w-full resize-none rounded-md border border-line bg-white px-3 py-2 text-xs leading-6" readOnly value={preview.body} />
                </label>
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

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xxs font-semibold text-muted">{label}</span>
      <input className="w-full rounded-md border border-line bg-white px-3 py-2 text-xs" readOnly value={value} />
    </label>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-gray-900">{value}</span>
    </div>
  );
}

function buildUserSideAiPreview(job: AutoJob, productAsset?: ProductAsset | null) {
  const displayName = job.creator.replace(/^@/, '') || 'creator';
  const greetingName = displayName.split(/[._-]/)[0] || 'there';
  const productName = productAsset?.name || job.product.replace(/\s*\+\s*AI 图片$/, '') || 'X9 Green Full Category';
  return {
    productName,
    imageUrl: productAsset?.image_url || '',
    subject: `X9 x ${displayName} - collaboration idea with 20% commission`,
    body: [
      `Hi ${capitalize(greetingName)},`,
      '',
      "I'm reaching out from X9. We're a care brand with four product series: women care, baby care, adult care, and pet care. They cover everyday needs for women, babies, adults, and pets.",
      '',
      'Your content feels natural and easy to trust, so we think there could be a good fit between your page and our care products.',
      '',
      "We'd love to explore a collaboration with you. If you're interested, we can first share the product line that best matches your audience, along with product images, key details, and a simple content idea for you to review.",
      '',
      "For this collaboration, we offer 20% commission on sales generated through your content. We'll also provide the product information and tracking support before you decide how to present it.",
      '',
      "Looking forward to your reply. If this sounds interesting, just let us know and we'll send over the next details.",
      '',
      'Best regards,',
      'X9 Outreach Team',
    ].join('\n'),
  };
}

function buildEmailHtml(preview: ReturnType<typeof buildUserSideAiPreview>) {
  const paragraphs = preview.body
    .split(/\n{2,}/)
    .map((block) => `<p style="margin:0 0 14px;font-size:14px;line-height:1.65;color:#111827;">${escapeHtml(block).replace(/\n/g, '<br/>')}</p>`)
    .join('');
  const imageMarkup = preview.imageUrl
    ? `<img src="${escapeHtml(preview.imageUrl)}" alt="${escapeHtml(preview.productName)}" style="width:100%;max-width:420px;max-height:280px;object-fit:contain;border-radius:8px;border:1px solid #d1d5db;display:block;margin:0 auto;background:#f8fafc;"/>`
    : '<div style="max-width:420px;margin:0 auto;padding:32px 16px;border:1px dashed #cbd5e1;border-radius:8px;background:#f8fafc;color:#64748b;font:13px/1.6 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;">未读取到系统 SKU 图片</div>';

  return `
    <div style="font-family:Arial,Helvetica,sans-serif;background:#ffffff;color:#111827;">
      <div style="text-align:center;margin:0 0 18px;">
        ${imageMarkup}
      </div>
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

function capitalize(value: string) {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}
