import { useEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  AtSign,
  Bold,
  CalendarDays,
  CheckCircle2,
  Copy,
  Eye,
  ExternalLink,
  History,
  ImagePlus,
  Inbox,
  Link as LinkIcon,
  List,
  MailCheck,
  MessageSquareText,
  Paperclip,
  RefreshCw,
  Save,
  Search,
  Send,
  Trash2,
  User,
  X,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { PaginationControls } from '@/components/PaginationControls';
import {
  useOutreachArchive,
  useOutreachArchiveDetail,
  useOutreachTracking,
  usePatchOutreachTrackingStatus,
  useReplyOutreachArchive,
  useGmailReplySyncStatus,
  useGmailSyncReplies,
} from '@/hooks/useApi';
import {
  pickItems,
  type EmailReplyAttachment,
  type GmailReplySyncAccount,
  type OutreachArchiveItem,
  type OutreachTrackingItem,
} from '@/api/types';
import { formatRelativeTime, type Language } from '@/lib/i18n';
import { useUiStore } from '@/stores/uiStore';

const PAGE_SIZE = 10;
const THREAD_PAGE_SIZE = 80;

const TRACKING_STATUSES = [
  'all',
  '已建联',
  '待跟进',
  '沟通中',
  '已寄样',
  '样品签收',
  '视频已发布',
  '已授权',
  '广告投放中',
] as const;

type TrackingStatus = typeof TRACKING_STATUSES[number];

const statusText: Record<Exclude<TrackingStatus, 'all'>, { zh: string; en: string }> = {
  已建联: { zh: '已建联', en: 'Contacted' },
  待跟进: { zh: '待跟进', en: 'Follow Up' },
  沟通中: { zh: '沟通中', en: 'Communicating' },
  已寄样: { zh: '已寄样', en: 'Sample Shipped' },
  样品签收: { zh: '样品签收', en: 'Sample Delivered' },
  视频已发布: { zh: '视频已发布', en: 'Video Published' },
  已授权: { zh: '已授权', en: 'Authorized' },
  广告投放中: { zh: '广告投放中', en: 'Ad Running' },
};

const copy = {
  zh: {
    badge: '邮件跟踪系统',
    title: '邮件跟踪系统',
    subtitle: '点击达人标签进入单个达人邮件跟踪页；在沟通记录里点开任一邮件查看完整 From / To / Subject / 正文。',
    total: '当前结果',
    loaded: '已载入',
    urgent: '待跟进',
    keyword: '关键词',
    keywordPlaceholder: '达人 / 主题 / 邮箱 / 摘要',
    from: '发件人',
    to: '收件人',
    dateFrom: '开始日期',
    dateTo: '结束日期',
    refresh: '刷新',
    reset: '重置',
    all: '全部',
    creator: '达人',
    creatorThread: '达人邮件跟踪',
    email: '邮箱',
    latestSent: '最近发送',
    latestReply: '最近回复',
    direction: '最新方向',
    account: '发件账号',
    owner: '负责人',
    count: '邮件数',
    followup: '跟进时效',
    empty: '暂无邮件跟踪记录',
    noSubject: '(无主题)',
    noPreview: '暂无摘要',
    inbound: '对方回复',
    outbound: '我方发送',
    now: '马上跟进',
    noReply: '暂无回复',
    detailsTitle: '邮件详情',
    selectPrompt: '选择一位达人查看沟通记录',
    selectEmailPrompt: '点击左侧沟通记录查看完整邮件',
    backAll: '全部达人',
    creatorLink: '达人详情',
    copy: '复制',
    copied: '已复制',
    bodyEmpty: '无正文内容',
    unknownCreator: '未知达人',
    unknownSender: '未知发件人',
    threadList: '沟通记录',
    sentHistory: '邮箱发送历史',
    fullEmail: '完整邮件',
    bodyPreview: '正文摘要',
    senderAccount: '建联邮箱',
    creatorMailbox: '达人邮箱',
    createdBy: '建联用户',
    gmailThread: 'Gmail 线程',
    gmailMessage: 'Gmail 消息',
    sentAt: '发送时间',
    currentStatus: '当前状态',
    openCreator: '进入',
    actionContacted: '标记待跟进',
    actionFollowup: '回复并进入沟通中',
    actionCommunicating: '推进到已寄样',
    actionSampleShipped: '标记签收',
    actionSampleDelivered: '标记视频发布',
    actionVideoPublished: '推进授权',
    actionAuthorized: '开始投放',
    done: '流程完成',
  },
  en: {
    badge: 'Email Tracking System',
    title: 'Email Tracking System',
    subtitle: 'Click a creator tag to open the creator email tracking page, then open any conversation record for full From / To / Subject / body details.',
    total: 'Results',
    loaded: 'Loaded',
    urgent: 'Follow Up',
    keyword: 'Keyword',
    keywordPlaceholder: 'Creator / subject / email / preview',
    from: 'Sender',
    to: 'Recipient',
    dateFrom: 'Start Date',
    dateTo: 'End Date',
    refresh: 'Refresh',
    reset: 'Reset',
    all: 'All',
    creator: 'Creator',
    creatorThread: 'Creator Email Tracking',
    email: 'Email',
    latestSent: 'Latest Sent',
    latestReply: 'Latest Reply',
    direction: 'Direction',
    account: 'Sending Account',
    owner: 'Owner',
    count: 'Emails',
    followup: 'SLA',
    empty: 'No email tracking records',
    noSubject: '(No subject)',
    noPreview: 'No preview yet',
    inbound: 'Inbound',
    outbound: 'Outbound',
    now: 'Follow up now',
    noReply: 'No reply',
    detailsTitle: 'Email Detail',
    selectPrompt: 'Select a creator to view communication history',
    selectEmailPrompt: 'Click a conversation record to inspect the full email',
    backAll: 'All Creators',
    creatorLink: 'Creator Detail',
    copy: 'Copy',
    copied: 'Copied',
    bodyEmpty: 'No body content',
    unknownCreator: 'Unknown creator',
    unknownSender: 'Unknown sender',
    threadList: 'Communication Records',
    sentHistory: 'Mailbox Sent History',
    fullEmail: 'Full Email',
    bodyPreview: 'Body Preview',
    senderAccount: 'Outreach Mailbox',
    creatorMailbox: 'Creator Mailbox',
    createdBy: 'Outreach User',
    gmailThread: 'Gmail Thread',
    gmailMessage: 'Gmail Message',
    sentAt: 'Sent At',
    currentStatus: 'Current Status',
    openCreator: 'Open',
    actionContacted: 'Mark Follow Up',
    actionFollowup: 'Reply and Communicate',
    actionCommunicating: 'Move to Shipped',
    actionSampleShipped: 'Mark Delivered',
    actionSampleDelivered: 'Mark Published',
    actionVideoPublished: 'Move to Authorized',
    actionAuthorized: 'Start Ads',
    done: 'Complete',
  },
} satisfies Record<Language, Record<string, string>>;

const actionFlow: Partial<Record<Exclude<TrackingStatus, 'all'>, { next: Exclude<TrackingStatus, 'all'>; key: keyof typeof copy.zh }>> = {
  已建联: { next: '待跟进', key: 'actionContacted' },
  待跟进: { next: '沟通中', key: 'actionFollowup' },
  沟通中: { next: '已寄样', key: 'actionCommunicating' },
  已寄样: { next: '样品签收', key: 'actionSampleShipped' },
  样品签收: { next: '视频已发布', key: 'actionSampleDelivered' },
  视频已发布: { next: '已授权', key: 'actionVideoPublished' },
  已授权: { next: '广告投放中', key: 'actionAuthorized' },
};

function safeEmailHtml(value?: string | null) {
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>body{margin:0;padding:20px;background:#fff;color:#111827;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}img{max-width:100%;height:auto}a{color:#0ea5e9}</style></head><body>${value || ''}</body></html>`;
}

function htmlToPlainText(value?: string | null) {
  const raw = String(value || '');
  if (!raw) return '';
  if (typeof window !== 'undefined' && 'DOMParser' in window) {
    const doc = new DOMParser().parseFromString(raw, 'text/html');
    return (doc.body.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
  }
  return raw
    .replace(/<(br|\/p|\/div|\/li)\b[^>]*>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function normalizeStatus(value?: string | null): Exclude<TrackingStatus, 'all'> {
  if (value === '待回复' || value === 'pending_reply' || value === 'pending_followup') return '待跟进';
  if (TRACKING_STATUSES.includes(value as TrackingStatus) && value !== 'all') return value as Exclude<TrackingStatus, 'all'>;
  return '已建联';
}

function statusLabel(value: string | null | undefined, language: Language) {
  const status = normalizeStatus(value);
  return statusText[status]?.[language] || status;
}

function creatorTitle(item?: OutreachTrackingItem | OutreachArchiveItem | null, language: Language = 'zh') {
  if (!item) return copy[language].unknownCreator;
  return item.creator_display_name || item.creator_handle || `${copy[language].creator} ${item.creator_id}`;
}

function directionLabel(item: OutreachTrackingItem, language: Language) {
  const c = copy[language];
  return item.latest_direction === 'inbound' ? c.inbound : c.outbound;
}

function formatAge(item: OutreachTrackingItem, language: Language) {
  const c = copy[language];
  if (item.needs_followup) return item.followup_age_hours ? `${item.followup_age_hours}h` : c.now;
  return c.noReply;
}

function mailTime(item?: OutreachArchiveItem | null) {
  return item?.sent_at || item?.created_at || null;
}

function replySubject(value?: string | null) {
  const subject = (value || '').trim() || '(no subject)';
  return subject.toLowerCase().startsWith('re:') ? subject : `Re: ${subject}`;
}

export default function OutreachArchive() {
  const { creatorId: routeCreatorId } = useParams<{ creatorId?: string }>();
  const navigate = useNavigate();
  const { language } = useUiStore();
  const t = copy[language];
  const [status, setStatus] = useState<TrackingStatus>('all');
  const [q, setQ] = useState('');
  const [fromEmail, setFromEmail] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(0);
  const [fallbackCreatorId, setFallbackCreatorId] = useState<string | null>(null);
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);
  const [copyState, setCopyState] = useState('');
  const [hadBackgroundSync, setHadBackgroundSync] = useState(false);
  const patchStatus = usePatchOutreachTrackingStatus();
  const syncStatusQ = useGmailReplySyncStatus();
  const syncReplies = useGmailSyncReplies();

  const params = useMemo(() => ({
    limit: PAGE_SIZE,
    offset: routeCreatorId ? 0 : page * PAGE_SIZE,
    status: routeCreatorId ? undefined : status === 'all' ? undefined : status,
    q: routeCreatorId ? routeCreatorId : q.trim() || undefined,
    from_email: routeCreatorId ? undefined : fromEmail.trim() || undefined,
    to_email: routeCreatorId ? undefined : toEmail.trim() || undefined,
    date_from: routeCreatorId ? undefined : dateFrom || undefined,
    date_to: routeCreatorId ? undefined : dateTo || undefined,
  }), [dateFrom, dateTo, fromEmail, page, q, routeCreatorId, status, toEmail]);

  const trackingQ = useOutreachTracking(params);
  const rows = pickItems<OutreachTrackingItem>(trackingQ.data);
  const activeCreatorId = routeCreatorId || fallbackCreatorId || rows[0]?.creator_id || null;
  const selected = activeCreatorId
    ? rows.find((item) => item.creator_id === activeCreatorId) || null
    : rows[0] || null;

  const archiveQ = useOutreachArchive({
    creator_id: activeCreatorId || undefined,
    limit: THREAD_PAGE_SIZE,
    offset: 0,
  });
  const archiveRows = activeCreatorId ? pickItems<OutreachArchiveItem>(archiveQ.data) : [];
  const fallbackMessage = selected?.latest_email_id ? [trackingToArchiveItem(selected)] : [];
  const communicationRows = archiveRows.length > 0 ? archiveRows : fallbackMessage;
  const selectedEmail = communicationRows.find((item) => item.id === selectedEmailId) || communicationRows[0] || null;
  const detailQ = useOutreachArchiveDetail(selectedEmail?.id || null);
  const detail = detailQ.data?.item ?? null;
  const rel = (value?: string | null) => formatRelativeTime(value, language);
  const syncTotals = syncStatusQ.data?.totals || {};
  const trackingMeta = trackingQ.data as typeof trackingQ.data & {
    status_counts?: Record<string, number>;
    direction_counts?: Record<string, number>;
  };
  const statusCounts = trackingMeta?.status_counts || {};
  const directionCounts = trackingMeta?.direction_counts || {};
  const backgroundSyncing = Boolean(syncStatusQ.data?.background?.running || syncReplies.data?.background?.running);
  const isSyncing = syncReplies.isPending || backgroundSyncing;

  useEffect(() => {
    if (backgroundSyncing) {
      setHadBackgroundSync(true);
      return;
    }
    if (hadBackgroundSync) {
      setHadBackgroundSync(false);
      void Promise.all([trackingQ.refetch(), archiveQ.refetch(), syncStatusQ.refetch()]);
    }
  }, [archiveQ.refetch, backgroundSyncing, hadBackgroundSync, syncStatusQ.refetch, trackingQ.refetch]);

  useEffect(() => {
    if (!routeCreatorId && !fallbackCreatorId && rows.length > 0) {
      setFallbackCreatorId(rows[0].creator_id);
    }
    if (!routeCreatorId && fallbackCreatorId && rows.length > 0 && !rows.some((item) => item.creator_id === fallbackCreatorId)) {
      setFallbackCreatorId(rows[0].creator_id);
    }
  }, [fallbackCreatorId, routeCreatorId, rows]);

  useEffect(() => {
    setSelectedEmailId(null);
  }, [activeCreatorId]);

  useEffect(() => {
    if (!selectedEmailId && communicationRows.length > 0) {
      setSelectedEmailId(communicationRows[0].id);
    }
  }, [communicationRows, selectedEmailId]);

  useEffect(() => {
    setPage(0);
  }, [dateFrom, dateTo, fromEmail, q, status, toEmail]);

  const resetFilters = () => {
    setStatus('all');
    setQ('');
    setFromEmail('');
    setToEmail('');
    setDateFrom('');
    setDateTo('');
    setPage(0);
  };

  const openCreator = (creatorId: string) => {
    setFallbackCreatorId(creatorId);
    navigate(`/emails/${encodeURIComponent(String(creatorId))}`);
  };

  const copyBody = async () => {
    if (!detail) return;
    const text = [
      `From: ${detail.from_email || ''}`,
      `To: ${detail.to_email || ''}`,
      `Subject: ${detail.subject || ''}`,
      '',
      detail.body || '',
    ].join('\n');
    await navigator.clipboard?.writeText(text);
    setCopyState(t.copied);
    window.setTimeout(() => setCopyState(''), 1600);
  };

  const advanceStatus = async (item: OutreachTrackingItem) => {
    const flow = actionFlow[normalizeStatus(item.current_status)];
    if (!flow) return;
    await patchStatus.mutateAsync({ creator_id: item.creator_id, current_status: flow.next });
    await trackingQ.refetch();
  };

  const syncNow = async () => {
    await syncReplies.mutateAsync({ limit_per_account: 2500 });
    await syncStatusQ.refetch();
  };

  const refreshMailThread = async () => {
    await Promise.all([trackingQ.refetch(), archiveQ.refetch(), syncStatusQ.refetch()]);
  };

  if (routeCreatorId) {
    return (
      <div className="space-y-4">
        <section className="card overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="mb-2 inline-flex items-center gap-1 rounded border border-border bg-elev2 px-2 py-1 text-xxs text-muted">
                <MailCheck size={12} /> {t.creatorThread}
              </div>
              <h2 className="truncate text-lg font-semibold text-text">{creatorTitle(selected || communicationRows[0], language)}</h2>
              <div className="mt-1 text-xxs text-muted">
                {language === 'zh' ? '已抓取回复' : 'Stored replies'}: {Number(syncTotals.stored_replies || 0)} · {language === 'zh' ? '跟踪线程' : 'Tracked threads'}: {Number(syncTotals.tracked_threads || 0)}
              </div>
              <div className="mt-1 text-xs text-muted">
                {t.senderAccount}: {selected?.from_email || communicationRows[0]?.from_email || '-'} · {t.count}: {archiveQ.data?.total ?? communicationRows.length}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Link to="/emails" className="btn btn-ghost !h-8">
                <ArrowLeft size={13} />
                {t.backAll}
              </Link>
              <button type="button" onClick={syncNow} disabled={isSyncing} className="btn !h-8">
                <RefreshCw size={13} className={isSyncing ? 'animate-spin' : ''} />
                {syncReplies.isPending ? (language === 'zh' ? '抓取中' : 'Syncing') : t.refresh}
              </button>
            </div>
          </div>
        </section>

        <CreatorMailThread
          t={t}
          language={language}
          selected={selected}
          activeCreatorId={activeCreatorId}
          rows={communicationRows}
          selectedEmailId={selectedEmail?.id ?? null}
          detail={detail}
          detailLoading={detailQ.isLoading}
          detailError={detailQ.error}
          archiveLoading={archiveQ.isLoading}
          archiveError={archiveQ.error}
          onSelectEmail={setSelectedEmailId}
          onCopy={copyBody}
          copyState={copyState}
          onReplySent={refreshMailThread}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <HeaderPanel
        t={t}
        language={language}
        rows={rows}
        trackingTotal={trackingQ.data?.total ?? rows.length}
        status={status}
        setStatus={setStatus}
        q={q}
        setQ={setQ}
        fromEmail={fromEmail}
        setFromEmail={setFromEmail}
        toEmail={toEmail}
        setToEmail={setToEmail}
        dateFrom={dateFrom}
        setDateFrom={setDateFrom}
        dateTo={dateTo}
        setDateTo={setDateTo}
        onRefresh={syncNow}
        onReset={resetFilters}
        refreshing={isSyncing}
        syncTotals={syncTotals}
        syncAccounts={syncStatusQ.data?.items || []}
        statusCounts={statusCounts}
        directionCounts={directionCounts}
      />
      <div className="grid gap-4 2xl:grid-cols-[minmax(460px,0.95fr)_minmax(560px,1.05fr)]">
        <AsyncState loading={trackingQ.isLoading} error={trackingQ.error} isEmpty={rows.length === 0} emptyMessage={t.empty} height={420}>
          <CreatorTrackingList
            t={t}
            language={language}
            rows={rows}
            selectedCreatorId={activeCreatorId}
            page={page}
            pageSize={PAGE_SIZE}
            total={trackingQ.data?.total ?? 0}
            loading={trackingQ.isFetching}
            onPageChange={setPage}
            onOpenCreator={openCreator}
            onAdvance={advanceStatus}
          />
        </AsyncState>

        <CreatorMailThread
          t={t}
          language={language}
          selected={selected}
          activeCreatorId={activeCreatorId}
          rows={communicationRows}
          selectedEmailId={selectedEmail?.id ?? null}
          detail={detail}
          detailLoading={detailQ.isLoading}
          detailError={detailQ.error}
          archiveLoading={archiveQ.isLoading}
          archiveError={archiveQ.error}
          onSelectEmail={setSelectedEmailId}
          onCopy={copyBody}
          copyState={copyState}
          onReplySent={refreshMailThread}
        />
      </div>
    </div>
  );
}

function HeaderPanel({
  t,
  language,
  rows,
  trackingTotal,
  status,
  setStatus,
  q,
  setQ,
  fromEmail,
  setFromEmail,
  toEmail,
  setToEmail,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  onRefresh,
  onReset,
  refreshing,
  syncTotals,
  syncAccounts,
  statusCounts,
  directionCounts,
}: {
  t: typeof copy.zh;
  language: Language;
  rows: OutreachTrackingItem[];
  trackingTotal: number;
  status: TrackingStatus;
  setStatus: (value: TrackingStatus) => void;
  q: string;
  setQ: (value: string) => void;
  fromEmail: string;
  setFromEmail: (value: string) => void;
  toEmail: string;
  setToEmail: (value: string) => void;
  dateFrom: string;
  setDateFrom: (value: string) => void;
  dateTo: string;
  setDateTo: (value: string) => void;
  onRefresh: () => void;
  onReset: () => void;
  refreshing: boolean;
  syncTotals: Record<string, number>;
  syncAccounts: GmailReplySyncAccount[];
  statusCounts: Record<string, number>;
  directionCounts: Record<string, number>;
}) {
  const communicating = Number(statusCounts['沟通中'] || 0);
  const shipped = Number(statusCounts['已寄样'] || 0) + Number(statusCounts['样品签收'] || 0);
  const authorized = Number(statusCounts['已授权'] || 0) + Number(statusCounts['广告投放中'] || 0);
  return (
    <section className="card overflow-hidden">
      <div className="grid gap-3 border-b border-border p-4 lg:grid-cols-[minmax(320px,1fr)_auto]">
        <div>
          <div className="mb-2 inline-flex items-center gap-1 rounded border border-border bg-elev2 px-2 py-1 text-xxs text-muted">
            <MailCheck size={12} /> {t.badge}
          </div>
          <h2 className="text-lg font-semibold text-text">{t.title}</h2>
          <div className="mt-1 max-w-3xl text-xs text-muted">{t.subtitle}</div>
        </div>
        <WorkflowStatusStrip
          language={language}
          total={trackingTotal}
          loaded={rows.length}
          pending={Number(directionCounts.needs_followup || rows.filter((item) => item.needs_followup).length)}
          communicating={communicating}
          shipped={shipped}
          authorized={authorized}
          replies={Number(syncTotals.stored_replies || 0)}
          readable={Number(syncTotals.readable_accounts || 0)}
          mailboxes={Number(syncTotals.accounts || 0)}
          refreshing={refreshing}
          onManualSync={onRefresh}
        />
      </div>

      {syncAccounts.length > 0 && (
        <div className="border-b border-border px-3 py-2">
          <div className="flex flex-wrap gap-2">
            {syncAccounts.map((account) => (
              <div key={account.account_id} className="inline-flex min-w-[220px] items-center justify-between gap-3 rounded-md border border-border bg-elev2 px-2.5 py-2 text-xxs">
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-text">{account.email}</span>
                  <span className="mt-0.5 block text-muted">
                    {language === 'zh' ? '线程' : 'Threads'} {Number(account.tracked_threads || 0)} · {language === 'zh' ? '回复' : 'Replies'} {Number(account.stored_replies || 0)} · {language === 'zh' ? '退信' : 'Bounces'} {Number(account.stored_bounces || 0)}
                  </span>
                </span>
                <span className={`shrink-0 rounded px-2 py-0.5 font-semibold ${account.status === 'idle' ? 'bg-good/10 text-good' : account.status === 'needs_reauth' ? 'bg-warn/10 text-warn' : 'bg-elev1 text-muted'}`}>
                  {account.status || 'idle'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="border-b border-border px-3 py-2">
        <div className="flex flex-wrap gap-1.5">
          {TRACKING_STATUSES.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setStatus(item)}
              className={`inline-flex h-8 items-center rounded px-2.5 text-xs font-semibold transition-colors ${
                status === item ? 'bg-accent text-[#001218] shadow-sm' : 'bg-elev2 text-muted hover:text-text'
              }`}
            >
              {item === 'all' ? t.all : statusLabel(item, language)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-3 p-3 xl:grid-cols-[minmax(360px,1fr)_auto]">
        <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-5">
          <label className="md:col-span-2 2xl:col-span-1">
            <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><Search size={12} />{t.keyword}</span>
            <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-elev1 px-3">
              <input
                value={q}
                onChange={(event) => setQ(event.target.value)}
                placeholder={t.keywordPlaceholder}
                className="min-w-0 flex-1 bg-transparent text-xs outline-none"
              />
              {q && <button type="button" onClick={() => setQ('')} className="text-muted hover:text-text"><X size={13} /></button>}
            </div>
          </label>
          <FilterInput icon={<Send size={12} />} label={t.from} value={fromEmail} onChange={setFromEmail} />
          <FilterInput icon={<User size={12} />} label={t.to} value={toEmail} onChange={setToEmail} />
          <DateInput label={t.dateFrom} value={dateFrom} onChange={setDateFrom} />
          <DateInput label={t.dateTo} value={dateTo} onChange={setDateTo} />
        </div>
        <div className="flex items-end justify-end gap-2">
          <button type="button" onClick={onRefresh} className="btn">
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />{refreshing ? (language === 'zh' ? '抓取中' : 'Syncing') : t.refresh}
          </button>
          <button type="button" onClick={onReset} className="btn btn-ghost">{t.reset}</button>
        </div>
      </div>
    </section>
  );
}

function CreatorTrackingList({
  t,
  language,
  rows,
  selectedCreatorId,
  page,
  pageSize,
  total,
  loading,
  onPageChange,
  onOpenCreator,
  onAdvance,
}: {
  t: typeof copy.zh;
  language: Language;
  rows: OutreachTrackingItem[];
  selectedCreatorId: string | null;
  page: number;
  pageSize: number;
  total: number;
  loading: boolean;
  onPageChange: (page: number) => void;
  onOpenCreator: (creatorId: string) => void;
  onAdvance: (item: OutreachTrackingItem) => void;
}) {
  return (
    <section className="overflow-hidden rounded-md border border-border bg-elev1">
      <div className="grid grid-cols-[minmax(190px,1.25fr)_104px_104px_92px] gap-3 border-b border-border bg-elev2 px-3 py-2 text-xxs font-semibold text-muted xl:grid-cols-[minmax(190px,1.3fr)_104px_104px_92px_96px]">
        <span>{t.creator}</span>
        <span>{t.latestSent}</span>
        <span>{t.latestReply}</span>
        <span>{t.followup}</span>
        <span className="hidden xl:block">{t.count}</span>
      </div>
      <div className="divide-y divide-border">
        {rows.map((item) => {
          const selectedRow = item.creator_id === selectedCreatorId;
          const statusKey = normalizeStatus(item.current_status);
          const flow = actionFlow[statusKey];
          return (
            <div
              key={item.creator_id}
              role="button"
              tabIndex={0}
              onClick={() => onOpenCreator(item.creator_id)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                onOpenCreator(item.creator_id);
              }}
              className={`grid cursor-pointer grid-cols-[minmax(190px,1.25fr)_104px_104px_92px] gap-3 px-3 py-3 text-left text-xs transition-colors xl:grid-cols-[minmax(190px,1.3fr)_104px_104px_92px_96px] ${
                selectedRow ? 'bg-accent/10' : 'hover:bg-elev2'
              }`}
            >
              <span className="min-w-0">
                <span className="flex min-w-0 items-center gap-2">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${item.needs_followup ? 'bg-warn' : 'bg-accent'}`} />
                  <Link
                    to={`/emails/${encodeURIComponent(String(item.creator_id))}`}
                    onClick={(event) => event.stopPropagation()}
                    className="inline-flex min-w-0 items-center gap-1 rounded border border-accent/30 bg-accent/10 px-2 py-0.5 font-semibold text-accent hover:bg-accent/20"
                    title={t.creatorThread}
                  >
                    <AtSign size={11} className="shrink-0" />
                    <span className="truncate">{creatorTitle(item, language)}</span>
                  </Link>
                </span>
                <span className="mt-1 block truncate text-muted">{item.to_email || item.creator_email || '-'}</span>
                <span className="mt-1 block truncate text-muted">{item.last_subject || t.noSubject}</span>
              </span>
              <span className="self-start text-muted">{relText(item.latest_outbound_at, language)}</span>
              <span className="self-start text-muted">{item.latest_inbound_at ? relText(item.latest_inbound_at, language) : t.noReply}</span>
              <span className="self-start">
                <span className={`rounded px-2 py-0.5 text-xxs font-semibold ${item.needs_followup ? 'bg-warn/15 text-warn' : 'bg-elev2 text-muted'}`}>
                  {formatAge(item, language)}
                </span>
                <span className="mt-1 block text-muted">{statusLabel(item.current_status, language)}</span>
                {flow ? (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onAdvance(item);
                    }}
                    className="mt-2 inline-flex h-7 items-center rounded border border-border bg-elev1 px-2 text-xxs font-semibold text-text hover:border-accent disabled:opacity-60"
                  >
                    {t[flow.key]}
                  </button>
                ) : (
                  <span className="mt-2 block text-xxs text-muted">{t.done}</span>
                )}
              </span>
              <span className="hidden self-start text-muted xl:block">{item.email_count ?? 0}</span>
            </div>
          );
        })}
      </div>
      <PaginationControls
        page={page}
        pageSize={pageSize}
        total={total}
        currentCount={rows.length}
        loading={loading}
        language={language}
        onPageChange={onPageChange}
      />
    </section>
  );
}

function CreatorMailThread({
  t,
  language,
  selected,
  activeCreatorId,
  rows,
  selectedEmailId,
  detail,
  detailLoading,
  detailError,
  archiveLoading,
  archiveError,
  onSelectEmail,
  onCopy,
  copyState,
  onReplySent,
}: {
  t: typeof copy.zh;
  language: Language;
  selected: OutreachTrackingItem | null;
  activeCreatorId: string | null;
  rows: OutreachArchiveItem[];
  selectedEmailId: string | null;
  detail: (OutreachArchiveItem & { body?: string | null; gmail_message_id?: string | null; error_message?: string | null; updated_at?: string | null }) | null;
  detailLoading: boolean;
  detailError: unknown;
  archiveLoading: boolean;
  archiveError: unknown;
  onSelectEmail: (id: string) => void;
  onCopy: () => void;
  copyState: string;
  onReplySent: () => Promise<void> | void;
}) {
  if (!activeCreatorId) {
    return (
      <section className="card card-body flex min-h-[520px] items-center justify-center text-center">
        <div>
          <MessageSquareText size={28} className="mx-auto mb-2 text-muted" />
          <div className="text-sm font-semibold text-text">{t.selectPrompt}</div>
          <div className="mt-1 text-xs text-muted">{t.selectEmailPrompt}</div>
        </div>
      </section>
    );
  }

  const firstRow = rows[0];
  const headerSource = selected || firstRow;
  const sender = selected?.from_email || firstRow?.from_email || '-';
  const recipient = selected?.to_email || selected?.creator_email || firstRow?.to_email || '-';

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-border p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-2 inline-flex items-center gap-1 rounded border border-border bg-elev2 px-2 py-1 text-xxs text-muted">
              <History size={12} /> {t.creatorThread}
            </div>
            <h3 className="truncate text-base font-semibold text-text">{creatorTitle(headerSource, language)}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="inline-flex items-center gap-1"><Send size={12} />{sender}</span>
              <span className="text-border">→</span>
              <span className="inline-flex items-center gap-1"><User size={12} />{recipient}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {activeCreatorId && (
              <Link to={`/recommendations/${encodeURIComponent(String(activeCreatorId))}`} className="btn btn-ghost !h-8 text-xs">
                <ExternalLink size={12} />{t.creatorLink}
              </Link>
            )}
            <button type="button" onClick={onCopy} disabled={!detail} className="btn !h-8 text-xs">
              <Copy size={12} />{copyState || t.copy}
            </button>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-xs xl:grid-cols-4">
          <Fact label={t.senderAccount} value={sender} icon={<Send size={12} />} />
          <Fact label={t.creatorMailbox} value={recipient} icon={<AtSign size={12} />} />
          <Fact label={t.currentStatus} value={selected ? statusLabel(selected.current_status, language) : '-'} icon={<CheckCircle2 size={12} />} />
          <Fact label={t.gmailThread} value={selected?.gmail_thread_id || firstRow?.gmail_thread_id || '-'} icon={<History size={12} />} />
        </div>
      </div>

      <div className="grid min-h-[640px] xl:grid-cols-[minmax(260px,0.72fr)_minmax(360px,1fr)]">
        <div className="border-b border-border xl:border-b-0 xl:border-r">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <div>
              <div className="text-xs font-semibold text-text">{t.threadList}</div>
              <div className="text-xxs text-muted">{t.sentHistory}</div>
            </div>
            <span className="rounded bg-elev2 px-2 py-0.5 text-xxs text-muted">{rows.length}</span>
          </div>
          <AsyncState loading={archiveLoading} error={archiveError} isEmpty={rows.length === 0} emptyMessage={t.empty} height={420}>
            <div className="max-h-[584px] overflow-y-auto">
              {rows.map((item) => (
                <EmailHistoryRow
                  key={item.id}
                  item={item}
                  selected={item.id === selectedEmailId}
                  language={language}
                  t={t}
                  onClick={() => onSelectEmail(item.id)}
                />
              ))}
            </div>
          </AsyncState>
        </div>

        <div className="min-w-0">
          <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-muted">{t.fullEmail}</div>
              <div className="mt-1 truncate text-sm font-semibold text-text">{detail?.subject || t.noSubject}</div>
            </div>
            {detail?.status && <span className="rounded bg-elev2 px-2 py-1 text-xxs font-semibold text-muted">{detail.status}</span>}
          </div>
          <AsyncState loading={detailLoading} error={detailError} isEmpty={!selectedEmailId} emptyMessage={t.selectEmailPrompt} height={520}>
            <FullEmailView t={t} detail={detail} language={language} />
          </AsyncState>
          <ReplyComposer
            detail={detail}
            selected={selected}
            language={language}
            onSent={onReplySent}
          />
        </div>
      </div>
    </section>
  );
}

const REPLY_MAX_IMAGES = 8;
const REPLY_MAX_IMAGE_BYTES = 5 * 1024 * 1024;

type ReplyAttachment = EmailReplyAttachment & {
  preview_url: string;
  created_at: number;
};

type ReplyDraft = {
  subject: string;
  body_html: string;
  attachments: EmailReplyAttachment[];
  saved_at: number;
};

const REPLY_TEMPLATES = {
  zh: [
    '感谢你的回复，我们可以继续沟通合作细节。',
    '我们可以根据你的内容风格调整寄样和拍摄要求。',
    '如果方便的话，请发一下你的报价和可合作档期。',
    '这边可以先确认产品信息，再安排下一步。',
    '期待你的反馈，谢谢！',
  ],
  en: [
    'Thanks for getting back to us. We can keep discussing the collaboration details.',
    'We can adjust the sample and content requirements to fit your style.',
    'When convenient, could you share your rate and available timeline?',
    'We can confirm the product details first and then move to the next step.',
    'Looking forward to your thoughts. Thank you!',
  ],
};

function ReplyComposer({
  detail,
  selected,
  language,
  onSent,
}: {
  detail: (OutreachArchiveItem & { body?: string | null; gmail_message_id?: string | null; error_message?: string | null; updated_at?: string | null }) | null;
  selected: OutreachTrackingItem | null;
  language: Language;
  onSent: () => Promise<void> | void;
}) {
  const reply = useReplyOutreachArchive();
  const editorRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const autoSaveTimerRef = useRef<number | null>(null);
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [bodyText, setBodyText] = useState('');
  const [attachments, setAttachments] = useState<ReplyAttachment[]>([]);
  const [notice, setNotice] = useState('');
  const [draftSavedAt, setDraftSavedAt] = useState<number | null>(null);
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const draftKey = detail ? replyDraftKey(detail.id) : '';

  useEffect(() => {
    if (!detail) return;
    const defaultSubject = replySubject(detail.subject || selected?.last_subject || '');
    const draft = loadReplyDraft(detail.id);
    const nextSubject = draft?.subject || defaultSubject;
    const nextHtml = draft?.body_html || '';
    const nextAttachments = (draft?.attachments || []).map(restoreReplyAttachment);
    setSubject(nextSubject);
    setBodyHtml(nextHtml);
    setBodyText(htmlToPlainText(nextHtml));
    setAttachments(nextAttachments);
    setNotice('');
    setDraftSavedAt(draft?.saved_at || null);
    setQuoteOpen(false);
    setPreviewOpen(false);
    setTemplatesOpen(false);
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => {
        if (editorRef.current) editorRef.current.innerHTML = nextHtml;
      });
    }
  }, [detail?.id, detail?.subject, selected?.last_subject]);

  useEffect(() => () => {
    if (autoSaveTimerRef.current) window.clearTimeout(autoSaveTimerRef.current);
  }, []);

  useEffect(() => {
    if (!detail || !draftKey || String(detail.direction || detail.status || '').toLowerCase() === 'bounce') return;
    if (autoSaveTimerRef.current) window.clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = window.setTimeout(() => {
      if (!hasDraftContent(subject, bodyHtml, attachments)) return;
      const savedAt = Date.now();
      if (saveReplyDraft(draftKey, {
        subject,
        body_html: bodyHtml,
        attachments: attachments.map(toEmailReplyAttachment),
        saved_at: savedAt,
      })) {
        setDraftSavedAt(savedAt);
      }
    }, 1100);
  }, [attachments, bodyHtml, detail, draftKey, subject]);

  if (!detail) return null;

  const direction = String(detail.direction || detail.status || '').toLowerCase();
  const isBounce = direction === 'bounce';
  const fromEmail = direction === 'inbound'
    ? detail.to_email
    : detail.from_email || selected?.from_email || '';
  const replyTo = direction === 'inbound'
    ? detail.from_email
    : detail.to_email || selected?.to_email || selected?.creator_email || '';
  const defaultSubject = replySubject(detail.subject || selected?.last_subject || '');
  const currentEditorHtml = editorRef.current?.innerHTML || bodyHtml;
  const finalHtml = buildReplyHtml(currentEditorHtml, attachments);
  const previewHtml = buildReplyPreviewHtml(currentEditorHtml, attachments);
  const canSend = Boolean(!isBounce && !reply.isPending && replyTo && fromEmail && (bodyText.trim() || attachments.length));
  const draftStatus = draftSavedAt
    ? `${language === 'zh' ? '草稿已保存' : 'Draft saved'} · ${new Date(draftSavedAt).toLocaleTimeString()}`
    : (language === 'zh' ? '尚未保存草稿' : 'Draft not saved');

  const syncEditor = () => {
    const html = editorRef.current?.innerHTML || '';
    setBodyHtml(html);
    setBodyText(htmlToPlainText(html));
  };

  const runCommand = (command: string, value?: string) => {
    if (isBounce) return;
    editorRef.current?.focus();
    document.execCommand(command, false, value);
    syncEditor();
  };

  const insertHtml = (html: string) => {
    if (isBounce) return;
    editorRef.current?.focus();
    document.execCommand('insertHTML', false, html);
    syncEditor();
  };

  const insertLink = () => {
    const url = window.prompt(language === 'zh' ? '输入链接地址' : 'Enter link URL');
    if (!url) return;
    runCommand('createLink', url);
  };

  const insertTemplate = (text: string) => {
    setTemplatesOpen(false);
    insertHtml(`<p>${escapeHtml(text)}</p>`);
  };

  const insertAttachmentNode = (item: ReplyAttachment) => {
    if (editorRef.current?.querySelector(`[data-x9-attachment-id="${cssEscape(item.id)}"]`)) return;
    const nodeHtml = [
      `<figure data-x9-attachment-card="${escapeAttr(item.id)}" contenteditable="false" style="margin:12px 0;padding:10px;border:1px solid #d9e2ec;border-radius:8px;background:#f8fafc;max-width:360px;">`,
      `<img data-x9-attachment-id="${escapeAttr(item.id)}" src="${escapeAttr(item.preview_url)}" alt="${escapeAttr(item.name)}" style="display:block;max-width:100%;max-height:220px;border-radius:6px;object-fit:contain;background:#fff;" />`,
      `<figcaption style="margin-top:6px;font-size:12px;color:#64748b;">${escapeHtml(item.name)} · ${formatBytes(item.size)}</figcaption>`,
      '</figure><p><br></p>',
    ].join('');
    insertHtml(nodeHtml);
  };

  const removeAttachmentNode = (id: string) => {
    const root = editorRef.current;
    root?.querySelectorAll(`[data-x9-attachment-card="${cssEscape(id)}"], img[data-x9-attachment-id="${cssEscape(id)}"]`).forEach((node) => {
      const figure = node instanceof HTMLElement ? node.closest('[data-x9-attachment-card]') : null;
      (figure || node).remove();
    });
    syncEditor();
  };

  const addFiles = async (files: File[]) => {
    const imageFiles = files.filter((file) => file.type.startsWith('image/'));
    if (!imageFiles.length) return;
    const slots = REPLY_MAX_IMAGES - attachments.length;
    if (slots <= 0) {
      setNotice(language === 'zh' ? `最多只能添加 ${REPLY_MAX_IMAGES} 张图片` : `You can add up to ${REPLY_MAX_IMAGES} images.`);
      return;
    }
    const accepted = imageFiles.slice(0, slots);
    const tooLarge = accepted.find((file) => file.size > REPLY_MAX_IMAGE_BYTES);
    if (tooLarge) {
      setNotice(language === 'zh' ? '单张图片不能超过 5MB' : 'Each image must be 5MB or smaller.');
      return;
    }
    const nextItems = await Promise.all(accepted.map(fileToReplyAttachment));
    setAttachments((prev) => [...prev, ...nextItems]);
    nextItems.filter((item) => item.disposition === 'inline').forEach(insertAttachmentNode);
    setNotice(language === 'zh' ? `已添加 ${nextItems.length} 张图片` : `${nextItems.length} image(s) added.`);
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const files = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === 'file')
      .map((item) => item.getAsFile())
      .filter((file): file is File => Boolean(file && file.type.startsWith('image/')));
    if (!files.length) return;
    event.preventDefault();
    void addFiles(files);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    void addFiles(Array.from(event.dataTransfer.files));
  };

  const toggleDisposition = (id: string, disposition: 'inline' | 'attachment') => {
    const item = attachments.find((entry) => entry.id === id);
    setAttachments((prev) => prev.map((entry) => entry.id === id ? { ...entry, disposition } : entry));
    if (disposition === 'inline' && item) {
      insertAttachmentNode({ ...item, disposition });
    } else {
      removeAttachmentNode(id);
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((item) => item.id !== id));
    removeAttachmentNode(id);
  };

  const saveDraftNow = () => {
    if (!draftKey) return;
    const savedAt = Date.now();
    const saved = saveReplyDraft(draftKey, {
      subject,
      body_html: editorRef.current?.innerHTML || bodyHtml,
      attachments: attachments.map(toEmailReplyAttachment),
      saved_at: savedAt,
    });
    if (saved) {
      setDraftSavedAt(savedAt);
      setNotice(language === 'zh' ? '草稿已保存到本地' : 'Draft saved locally.');
    } else {
      setNotice(language === 'zh' ? '草稿保存失败，图片可能过大' : 'Draft save failed. Images may be too large.');
    }
  };

  const sendReply = async () => {
    if (!canSend) return;
    setNotice('');
    await reply.mutateAsync({
      id: detail.id,
      body: {
        subject: subject.trim() || defaultSubject,
        body: finalHtml,
        body_format: 'html',
        attachments: attachments.map(toEmailReplyAttachment),
      },
    });
    clearReplyDraft(draftKey);
    setBodyHtml('');
    setBodyText('');
    setAttachments([]);
    setDraftSavedAt(null);
    setPreviewOpen(false);
    if (editorRef.current) editorRef.current.innerHTML = '';
    setNotice(language === 'zh' ? '已发送回复，并进入沟通中' : 'Reply sent. Status moved to communicating.');
    await onSent();
  };

  return (
    <div className="border-t border-border bg-elev1/70 p-4">
      <div className="overflow-hidden rounded-md border border-border bg-elev1 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-sm font-semibold text-text">{language === 'zh' ? '邮件回复' : 'Reply'}</div>
              <span className={`rounded px-2 py-1 text-xxs font-semibold ${isBounce ? 'bg-warn/10 text-warn' : 'bg-good/10 text-good'}`}>
                {isBounce ? (language === 'zh' ? '退信不可回复' : 'Bounce') : (language === 'zh' ? '同线程回复' : 'Thread reply')}
              </span>
            </div>
            <div className="mt-2 flex min-w-0 flex-wrap gap-x-4 gap-y-1 text-xxs text-muted">
              <span className="truncate">{language === 'zh' ? '发件邮箱' : 'From'}: <b className="text-text">{fromEmail || '-'}</b></span>
              <span className="truncate">To: <b className="text-text">{replyTo || '-'}</b></span>
            </div>
          </div>
          <button type="button" onClick={() => setQuoteOpen((value) => !value)} className="btn btn-ghost h-8" title={language === 'zh' ? '显示原邮件引用' : 'Show original quote'}>
            <MessageSquareText size={14} />
            {quoteOpen ? (language === 'zh' ? '收起引用' : 'Hide quote') : (language === 'zh' ? '原邮件' : 'Quote')}
          </button>
        </div>

        {quoteOpen ? (
          <div className="max-h-32 overflow-auto border-b border-border bg-elev2/50 px-4 py-3 text-xs leading-relaxed text-muted">
            <div className="mb-1 font-semibold text-text">{detail.subject || defaultSubject}</div>
            <div className="whitespace-pre-wrap">{htmlToPlainText(detail.body || detail.body_preview || '') || (language === 'zh' ? '暂无原邮件内容' : 'No original body.')}</div>
          </div>
        ) : null}

        <div className="space-y-3 p-4">
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
            <input
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              disabled={isBounce}
              className="input-bare h-10 w-full rounded-md border border-border bg-elev2 px-3 text-sm transition-colors focus:border-accent"
              placeholder={language === 'zh' ? '回复主题' : 'Reply subject'}
            />
            <button type="button" onClick={() => setSubject(defaultSubject)} disabled={isBounce} className="btn h-10 justify-center">
              {language === 'zh' ? '恢复主题' : 'Restore'}
            </button>
          </div>

          <div className="overflow-hidden rounded-md border border-border bg-white text-slate-900 shadow-sm focus-within:border-accent">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-2 py-1.5">
              <div className="flex flex-wrap items-center gap-1">
                <ToolbarButton title={language === 'zh' ? '加粗' : 'Bold'} onClick={() => runCommand('bold')} disabled={isBounce}><Bold size={14} /></ToolbarButton>
                <ToolbarButton title={language === 'zh' ? '列表' : 'List'} onClick={() => runCommand('insertUnorderedList')} disabled={isBounce}><List size={14} /></ToolbarButton>
                <ToolbarButton title={language === 'zh' ? '链接' : 'Link'} onClick={insertLink} disabled={isBounce}><LinkIcon size={14} /></ToolbarButton>
                <ToolbarButton title={language === 'zh' ? '插入图片' : 'Insert image'} onClick={() => fileInputRef.current?.click()} disabled={isBounce || attachments.length >= REPLY_MAX_IMAGES}><ImagePlus size={14} /></ToolbarButton>
                <div className="relative">
                  <ToolbarButton title={language === 'zh' ? '常用话术' : 'Templates'} onClick={() => setTemplatesOpen((value) => !value)} disabled={isBounce}><MessageSquareText size={14} /></ToolbarButton>
                  {templatesOpen ? (
                    <div className="absolute left-0 top-8 z-20 w-72 rounded-md border border-slate-200 bg-white p-1 shadow-lg">
                      {REPLY_TEMPLATES[language].map((text) => (
                        <button key={text} type="button" onClick={() => insertTemplate(text)} className="block w-full rounded px-2 py-2 text-left text-xs leading-relaxed text-slate-700 hover:bg-slate-100">
                          {text}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-slate-500">
                <Paperclip size={13} />
                {attachments.length}/{REPLY_MAX_IMAGES}
              </div>
            </div>
            <div
              className={`relative ${isDragging ? 'bg-cyan-50' : 'bg-white'}`}
              onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            >
              {!bodyText.trim() && !bodyHtml.includes('data-x9-attachment-id') ? (
                <div className="pointer-events-none absolute left-4 top-4 text-sm text-slate-400">
                  {isBounce ? (language === 'zh' ? '这是一封退信通知，不能直接回复。' : 'This is a bounce notification and cannot be replied to.') : (language === 'zh' ? '输入要发送给达人的回复内容，可粘贴或拖拽图片' : 'Write the reply. Paste or drag images here.')}
                </div>
              ) : null}
              <div
                ref={editorRef}
                contentEditable={!isBounce}
                suppressContentEditableWarning
                onInput={(event: FormEvent<HTMLDivElement>) => {
                  setBodyHtml(event.currentTarget.innerHTML);
                  setBodyText(htmlToPlainText(event.currentTarget.innerHTML));
                }}
                onPaste={handlePaste}
                className="min-h-[176px] max-h-[280px] overflow-auto px-4 py-4 text-sm leading-6 outline-none"
              />
            </div>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(event) => {
              void addFiles(Array.from(event.target.files || []));
              event.target.value = '';
            }}
          />

          {attachments.length ? (
            <div className="grid gap-2 md:grid-cols-2">
              {attachments.map((item) => (
                <div key={item.id} className="flex min-w-0 items-center gap-3 rounded-md border border-border bg-elev2/60 p-2">
                  <img src={item.preview_url} alt={item.name} className="h-12 w-12 shrink-0 rounded object-cover" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold text-text">{item.name}</div>
                    <div className="mt-0.5 text-xxs text-muted">{formatBytes(item.size)}</div>
                    <div className="mt-1 flex gap-1">
                      <button type="button" onClick={() => toggleDisposition(item.id, 'inline')} className={`rounded px-2 py-0.5 text-[11px] ${item.disposition === 'inline' ? 'bg-accent text-[#001218]' : 'bg-elev1 text-muted'}`}>{language === 'zh' ? '正文内' : 'Inline'}</button>
                      <button type="button" onClick={() => toggleDisposition(item.id, 'attachment')} className={`rounded px-2 py-0.5 text-[11px] ${item.disposition === 'attachment' ? 'bg-accent text-[#001218]' : 'bg-elev1 text-muted'}`}>{language === 'zh' ? '附件' : 'Attach'}</button>
                    </div>
                  </div>
                  <button type="button" onClick={() => removeAttachment(item.id)} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded text-muted hover:bg-bad/10 hover:text-bad" title={language === 'zh' ? '删除图片' : 'Remove image'}>
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0 text-xxs text-muted">
              <span>{bodyText.trim().length} {language === 'zh' ? '字' : 'chars'}</span>
              <span className="mx-2">·</span>
              <span>{attachments.length} {language === 'zh' ? '张图片' : 'images'}</span>
              <span className="mx-2">·</span>
              <span>{draftStatus}</span>
              {notice ? <span className="ml-2 text-accent">{notice}</span> : null}
              {reply.error ? <span className="ml-2 text-warn">{String((reply.error as Error).message || reply.error)}</span> : null}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setPreviewOpen(true)} disabled={!bodyText.trim() && !attachments.length} className="btn">
                <Eye size={13} />
                {language === 'zh' ? '预览' : 'Preview'}
              </button>
              <button type="button" onClick={saveDraftNow} disabled={isBounce} className="btn">
                <Save size={13} />
                {language === 'zh' ? '保存草稿' : 'Save draft'}
              </button>
              <button type="button" onClick={sendReply} disabled={!canSend} className="btn btn-primary">
                <Send size={13} className={reply.isPending ? 'animate-pulse' : ''} />
                {reply.isPending ? (language === 'zh' ? '发送中' : 'Sending') : (language === 'zh' ? '发送回复' : 'Send reply')}
              </button>
            </div>
          </div>
        </div>
      </div>

      {previewOpen ? (
        <ReplyPreviewModal
          language={language}
          subject={subject.trim() || defaultSubject}
          from={fromEmail || '-'}
          to={replyTo || '-'}
          html={previewHtml}
          attachments={attachments}
          onClose={() => setPreviewOpen(false)}
          onSend={sendReply}
          sendDisabled={!canSend}
          sending={reply.isPending}
        />
      ) : null}
    </div>
  );
}

function ToolbarButton({ title, disabled, onClick, children }: { title: string; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-7 w-7 items-center justify-center rounded text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function ReplyPreviewModal({
  language,
  subject,
  from,
  to,
  html,
  attachments,
  onClose,
  onSend,
  sendDisabled,
  sending,
}: {
  language: Language;
  subject: string;
  from: string;
  to: string;
  html: string;
  attachments: ReplyAttachment[];
  onClose: () => void;
  onSend: () => void;
  sendDisabled: boolean;
  sending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-md border border-border bg-elev1 shadow-soft">
        <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-text">{language === 'zh' ? '发送前预览' : 'Preview before send'}</div>
            <div className="mt-1 truncate text-xxs text-muted">From: {from} · To: {to}</div>
          </div>
          <button type="button" onClick={onClose} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-elev2 hover:text-text">
            <X size={15} />
          </button>
        </header>
        <div className="overflow-auto p-4">
          <div className="mb-3 rounded-md border border-border bg-elev2 px-3 py-2 text-xs">
            <span className="text-muted">Subject: </span>
            <span className="font-semibold text-text">{subject || '(no subject)'}</span>
          </div>
          <iframe title="reply-preview" sandbox="" srcDoc={safeEmailHtml(html)} className="h-[360px] w-full rounded-md border border-border bg-white" />
          {attachments.length ? (
            <div className="mt-3 rounded-md border border-border bg-elev2 p-3">
              <div className="mb-2 text-xs font-semibold text-text">{language === 'zh' ? '图片' : 'Images'} · {attachments.length}</div>
              <div className="flex flex-wrap gap-2">
                {attachments.map((item) => (
                  <span key={item.id} className="rounded bg-elev1 px-2 py-1 text-xxs text-muted">
                    {item.name} · {item.disposition} · {formatBytes(item.size)}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          <button type="button" onClick={onClose} className="btn">{language === 'zh' ? '返回编辑' : 'Back'}</button>
          <button type="button" onClick={onSend} disabled={sendDisabled} className="btn btn-primary">
            <Send size={13} className={sending ? 'animate-pulse' : ''} />
            {sending ? (language === 'zh' ? '发送中' : 'Sending') : (language === 'zh' ? '发送回复' : 'Send reply')}
          </button>
        </footer>
      </div>
    </div>
  );
}

function replyDraftKey(emailId: string) {
  return `reply-draft:${emailId}`;
}

function loadReplyDraft(emailId: string): ReplyDraft | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(replyDraftKey(emailId));
    return raw ? JSON.parse(raw) as ReplyDraft : null;
  } catch {
    return null;
  }
}

function saveReplyDraft(key: string, draft: ReplyDraft): boolean {
  if (typeof window === 'undefined') return false;
  try {
    window.localStorage.setItem(key, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

function clearReplyDraft(key: string) {
  if (typeof window === 'undefined' || !key) return;
  window.localStorage.removeItem(key);
}

function hasDraftContent(subject: string, bodyHtml: string, attachments: ReplyAttachment[]) {
  return Boolean(subject.trim() || htmlToPlainText(bodyHtml).trim() || attachments.length);
}

function restoreReplyAttachment(item: EmailReplyAttachment): ReplyAttachment {
  return {
    ...item,
    preview_url: `data:${item.mime_type};base64,${item.content_base64}`,
    created_at: Date.now(),
  };
}

function toEmailReplyAttachment(item: ReplyAttachment): EmailReplyAttachment {
  return {
    id: item.id,
    name: item.name,
    mime_type: item.mime_type,
    size: item.size,
    content_base64: item.content_base64,
    disposition: item.disposition,
  };
}

async function fileToReplyAttachment(file: File): Promise<ReplyAttachment> {
  const previewUrl = await readFileAsDataUrl(file);
  const contentBase64 = previewUrl.split(',', 2)[1] || '';
  return {
    id: makeReplyAttachmentId(),
    name: file.name || 'image',
    mime_type: file.type || 'image/png',
    size: file.size,
    content_base64: contentBase64,
    disposition: 'inline',
    preview_url: previewUrl,
    created_at: Date.now(),
  };
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('file read failed'));
    reader.readAsDataURL(file);
  });
}

function makeReplyAttachmentId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `reply_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function buildReplyHtml(editorHtml: string, attachments: ReplyAttachment[]) {
  return normalizeReplyHtml(editorHtml, attachments, false);
}

function buildReplyPreviewHtml(editorHtml: string, attachments: ReplyAttachment[]) {
  return normalizeReplyHtml(editorHtml, attachments, true);
}

function normalizeReplyHtml(editorHtml: string, attachments: ReplyAttachment[], keepPreviewUrls: boolean) {
  const html = editorHtml || '';
  if (typeof window === 'undefined' || !('DOMParser' in window)) {
    return html.trim() || '<p></p>';
  }
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html');
  doc.querySelectorAll('script,style,meta,link').forEach((node) => node.remove());
  doc.body.querySelectorAll('*').forEach((node) => {
    [...node.attributes].forEach((attr) => {
      if (/^on/i.test(attr.name) || attr.name === 'contenteditable') node.removeAttribute(attr.name);
    });
  });
  const byId = new Map(attachments.map((item) => [item.id, item]));
  doc.querySelectorAll('img[data-x9-attachment-id]').forEach((node) => {
    const img = node as HTMLImageElement;
    const id = img.getAttribute('data-x9-attachment-id') || '';
    const item = byId.get(id);
    if (!item) {
      img.remove();
      return;
    }
    img.setAttribute('src', keepPreviewUrls ? item.preview_url : `x9-attachment:${id}`);
    img.setAttribute('alt', item.name);
    img.setAttribute('style', 'display:block;max-width:100%;max-height:360px;border-radius:6px;object-fit:contain;background:#fff;');
  });
  return doc.body.firstElementChild?.innerHTML.trim() || '<p></p>';
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(value: string) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

function cssEscape(value: string) {
  if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(value);
  return value.replace(/["\\]/g, '\\$&');
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function EmailHistoryRow({
  item,
  selected,
  language,
  t,
  onClick,
}: {
  item: OutreachArchiveItem;
  selected: boolean;
  language: Language;
  t: typeof copy.zh;
  onClick: () => void;
}) {
  const direction = String(item.direction || item.status || '').toLowerCase();
  const isInbound = direction === 'inbound';
  const isBounce = direction === 'bounce';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`block w-full border-b border-border px-3 py-3 text-left transition-colors ${
        selected ? 'bg-accent/10' : 'hover:bg-elev2'
      }`}
    >
      <div className="flex items-start gap-2">
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          selected ? 'bg-accent text-[#001218]' : isInbound ? 'bg-good/10 text-good' : isBounce ? 'bg-warn/10 text-warn' : 'bg-elev2 text-muted'
        }`}>
          {isInbound ? <Inbox size={14} /> : isBounce ? <X size={14} /> : <Send size={14} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="truncate text-xs font-semibold text-text">{item.subject || t.noSubject}</div>
            <div className="shrink-0 text-xxs text-muted">{relText(mailTime(item), language)}</div>
          </div>
          <div className="mt-1 truncate text-xxs text-muted">{item.from_email || t.unknownSender} → {item.to_email}</div>
          <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">{item.body_preview || t.noPreview}</div>
        </div>
      </div>
    </button>
  );
}

function FullEmailView({
  t,
  detail,
  language,
}: {
  t: typeof copy.zh;
  detail: (OutreachArchiveItem & { body?: string | null; gmail_message_id?: string | null; error_message?: string | null; updated_at?: string | null }) | null;
  language: Language;
}) {
  if (!detail) {
    return <div className="p-4 text-xs text-muted">{t.selectEmailPrompt}</div>;
  }
  return (
    <div>
      <div className="border-b border-border p-4">
        <div className="grid gap-2 text-xs md:grid-cols-2">
          <Fact label="From" value={detail.from_email || '-'} icon={<Send size={12} />} />
          <Fact label="To" value={detail.to_email || '-'} icon={<User size={12} />} />
          <Fact label="Subject" value={detail.subject || t.noSubject} icon={<MessageSquareText size={12} />} />
          <Fact label={t.sentAt} value={mailTime(detail) ? `${relText(mailTime(detail), language)} · ${mailTime(detail)}` : '-'} icon={<CalendarDays size={12} />} />
          <Fact label={t.gmailThread} value={detail.gmail_thread_id || '-'} icon={<History size={12} />} />
          <Fact label={t.gmailMessage} value={detail.gmail_message_id || '-'} icon={<MailCheck size={12} />} />
          <Fact label={t.createdBy} value={detail.created_by || '-'} icon={<User size={12} />} />
          <Fact label={t.bodyPreview} value={detail.body_preview || t.noPreview} icon={<Inbox size={12} />} />
        </div>
      </div>
      {detail.body_format === 'html' ? (
        <iframe title={t.detailsTitle} sandbox="" srcDoc={safeEmailHtml(detail.body)} className="block h-[520px] w-full bg-white" />
      ) : (
        <pre className="h-[520px] overflow-auto whitespace-pre-wrap p-4 text-sm leading-relaxed text-text">{detail.body || detail.error_message || t.bodyEmpty}</pre>
      )}
    </div>
  );
}

function Fact({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-elev2 p-2">
      <div className="flex items-center gap-1 text-xxs text-muted">{icon}{label}</div>
      <div className="mt-1 truncate font-semibold text-text" title={value}>{value}</div>
    </div>
  );
}

function FilterInput({
  icon,
  label,
  value,
  onChange,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted">{icon}{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
    </label>
  );
}

function DateInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><CalendarDays size={12} />{label}</span>
      <input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
    </label>
  );
}

function WorkflowStatusStrip({
  language,
  total,
  loaded,
  pending,
  communicating,
  shipped,
  authorized,
  replies,
  readable,
  mailboxes,
  refreshing,
  onManualSync,
}: {
  language: Language;
  total: number;
  loaded: number;
  pending: number;
  communicating: number;
  shipped: number;
  authorized: number;
  replies: number;
  readable: number;
  mailboxes: number;
  refreshing: boolean;
  onManualSync: () => void;
}) {
  const zh = language === 'zh';
  const stages = [
    { label: zh ? '建联池' : 'Outreach', value: total, sub: zh ? `本页 ${loaded}` : `Loaded ${loaded}`, tone: 'normal' },
    { label: zh ? '真实回复' : 'Fetched replies', value: replies, sub: zh ? 'Gmail 已落库' : 'Stored from Gmail', tone: replies > 0 ? 'good' : 'normal' },
    { label: zh ? '待跟进' : 'Follow-up queue', value: pending, sub: zh ? '含历史/手动标记' : 'Includes manual/history', tone: pending > 0 ? 'warn' : 'normal' },
    { label: zh ? '沟通中' : 'Communicating', value: communicating, sub: zh ? '已进入对话' : 'Active talks', tone: 'good' },
    { label: zh ? '样品阶段' : 'Sample stage', value: shipped, sub: zh ? '寄样 / 签收' : 'Shipped / delivered', tone: 'normal' },
    { label: zh ? '授权投放' : 'Authorized', value: authorized, sub: zh ? '授权 / 投放' : 'Authorized / ads', tone: 'normal' },
    { label: zh ? '邮箱同步' : 'Mailbox sync', value: `${readable}/${mailboxes || 0}`, sub: zh ? '10 分钟自动抓取' : '10 min auto sync', tone: readable === mailboxes ? 'good' : 'warn' },
  ] as const;
  return (
    <div className="grid gap-2 lg:min-w-[760px] xl:grid-cols-7">
      {stages.map((stage, index) => (
        <div key={stage.label} className={`relative overflow-hidden rounded-md border p-3 ${
          stage.tone === 'warn'
            ? 'border-warn/30 bg-warn/10'
            : stage.tone === 'good'
              ? 'border-good/25 bg-good/10'
              : 'border-border bg-elev2'
        }`}>
          {index < stages.length - 1 && <span className="absolute right-2 top-3 text-muted/40">→</span>}
          <div className="pr-4 text-xxs font-semibold text-muted">{stage.label}</div>
          <div className={`num mt-1 text-xl font-semibold ${stage.tone === 'warn' ? 'text-warn' : stage.tone === 'good' ? 'text-good' : 'text-text'}`}>{stage.value}</div>
          <div className="mt-1 truncate text-xxs text-muted">{stage.sub}</div>
          {index === stages.length - 1 && (
            <button
              type="button"
              onClick={onManualSync}
              disabled={refreshing}
              className="mt-2 inline-flex h-7 w-full items-center justify-center gap-1 rounded border border-border bg-elev1 px-2 text-xxs font-semibold text-text transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
              {refreshing ? (zh ? '更新中' : 'Updating') : (zh ? '立即更新' : 'Update now')}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function Metric({ label, value, tone = 'normal' }: { label: string; value: number; tone?: 'normal' | 'warn' }) {
  return (
    <div className="rounded-md border border-border bg-elev2 p-3">
      <div className="text-xxs text-muted">{label}</div>
      <div className={`num mt-1 text-xl font-semibold ${tone === 'warn' ? 'text-warn' : 'text-text'}`}>{value}</div>
    </div>
  );
}

function trackingToArchiveItem(item: OutreachTrackingItem): OutreachArchiveItem {
  return {
    id: item.latest_email_id || `${item.creator_id}:latest`,
    creator_id: item.creator_id,
    creator_handle: item.creator_handle,
    creator_display_name: item.creator_display_name,
    creator_profile_url: item.creator_profile_url,
    creator_platform: item.creator_platform,
    to_email: item.to_email || item.creator_email || '',
    from_email: item.from_email,
    subject: item.last_subject || '',
    body_preview: item.last_preview,
    status: 'sent',
    sent_at: item.latest_outbound_at || item.latest_message_at,
    created_at: item.latest_message_at,
    gmail_thread_id: item.gmail_thread_id,
  };
}

function relText(value: string | null | undefined, language: Language) {
  return formatRelativeTime(value, language);
}
