import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CalendarDays,
  Copy,
  ExternalLink,
  MailCheck,
  RefreshCw,
  Search,
  Send,
  User,
  X,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { PaginationControls } from '@/components/PaginationControls';
import { useOutreachArchiveDetail, useOutreachTracking, usePatchOutreachTrackingStatus } from '@/hooks/useApi';
import { pickItems, type OutreachTrackingItem } from '@/api/types';
import { formatRelativeTime, type Language } from '@/lib/i18n';
import { useUiStore } from '@/stores/uiStore';

const PAGE_SIZE = 10;

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
    subtitle: '按达人和邮件线程跟踪建联进度，优先处理已回复但我方未回复的待跟进记录。',
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
    email: '邮箱',
    latestSent: '最近发送',
    latestReply: '最近回复',
    direction: '最新方向',
    subject: '主题',
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
    detailsTitle: '邮件正文',
    selectPrompt: '选择一条记录查看最近发送正文',
    creatorLink: '达人',
    copy: '复制',
    copied: '已复制',
    bodyEmpty: '无正文内容',
    unknownCreator: '未知达人',
    unknownSender: '未知发件人',
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
    subtitle: 'Track outreach by creator and email thread, with unanswered inbound replies prioritized for follow-up.',
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
    email: 'Email',
    latestSent: 'Latest Sent',
    latestReply: 'Latest Reply',
    direction: 'Direction',
    subject: 'Subject',
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
    detailsTitle: 'Email Body',
    selectPrompt: 'Select a record to review the latest sent email',
    creatorLink: 'Creator',
    copy: 'Copy',
    copied: 'Copied',
    bodyEmpty: 'No body content',
    unknownCreator: 'Unknown creator',
    unknownSender: 'Unknown sender',
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
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>body{margin:0;padding:18px;background:#fff;color:#111827;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}img{max-width:100%;height:auto}</style></head><body>${value || ''}</body></html>`;
}

function normalizeStatus(value?: string | null): Exclude<TrackingStatus, 'all'> {
  if (value === '\u5f85\u56de\u590d' || value === 'pending_reply' || value === 'pending_followup') return '待跟进';
  if (TRACKING_STATUSES.includes(value as TrackingStatus) && value !== 'all') return value as Exclude<TrackingStatus, 'all'>;
  return '已建联';
}

function statusLabel(value: string | null | undefined, language: Language) {
  const status = normalizeStatus(value);
  return statusText[status]?.[language] || status;
}

function creatorTitle(item?: OutreachTrackingItem | null, language: Language = 'zh') {
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

export default function OutreachArchive() {
  const { language } = useUiStore();
  const t = copy[language];
  const [status, setStatus] = useState<TrackingStatus>('all');
  const [q, setQ] = useState('');
  const [fromEmail, setFromEmail] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(0);
  const [selectedCreatorId, setSelectedCreatorId] = useState<string | null>(null);
  const [copyState, setCopyState] = useState('');
  const patchStatus = usePatchOutreachTrackingStatus();

  const params = useMemo(() => ({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    status: status === 'all' ? undefined : status,
    q: q.trim() || undefined,
    from_email: fromEmail.trim() || undefined,
    to_email: toEmail.trim() || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  }), [dateFrom, dateTo, fromEmail, page, q, status, toEmail]);

  const trackingQ = useOutreachTracking(params);
  const rows = pickItems<OutreachTrackingItem>(trackingQ.data);
  const selected = rows.find((item) => item.creator_id === selectedCreatorId) || rows[0] || null;
  const detailQ = useOutreachArchiveDetail(selected?.latest_email_id || null);
  const detail = detailQ.data?.item ?? null;
  const rel = (value?: string | null) => formatRelativeTime(value, language);

  useEffect(() => {
    if (!selectedCreatorId && rows.length > 0) setSelectedCreatorId(rows[0].creator_id);
    if (selectedCreatorId && rows.length > 0 && !rows.some((item) => item.creator_id === selectedCreatorId)) {
      setSelectedCreatorId(rows[0].creator_id);
    }
  }, [rows, selectedCreatorId]);

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

  const copyBody = async () => {
    if (!detail) return;
    const text = [`Subject: ${detail.subject}`, '', detail.body || ''].join('\n');
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

  return (
    <div className="space-y-4">
      <section className="card overflow-hidden">
        <div className="grid gap-3 border-b border-border p-4 lg:grid-cols-[minmax(320px,1fr)_auto]">
          <div>
            <div className="mb-2 inline-flex items-center gap-1 rounded border border-border bg-elev2 px-2 py-1 text-xxs text-muted">
              <MailCheck size={12} /> {t.badge}
            </div>
            <h2 className="text-lg font-semibold text-text">{t.title}</h2>
            <div className="mt-1 text-xs text-muted">{t.subtitle}</div>
          </div>
          <div className="grid grid-cols-3 gap-2 lg:min-w-[360px]">
            <div className="rounded-md border border-border bg-elev2 p-3">
              <div className="text-xxs text-muted">{t.total}</div>
              <div className="num mt-1 text-xl font-semibold">{trackingQ.data?.total ?? rows.length}</div>
            </div>
            <div className="rounded-md border border-border bg-elev2 p-3">
              <div className="text-xxs text-muted">{t.loaded}</div>
              <div className="num mt-1 text-xl font-semibold">{rows.length}</div>
            </div>
            <div className="rounded-md border border-border bg-elev2 p-3">
              <div className="text-xxs text-muted">{t.urgent}</div>
              <div className="num mt-1 text-xl font-semibold">{rows.filter((item) => item.needs_followup).length}</div>
            </div>
          </div>
        </div>

        <div className="border-b border-border px-3 py-2">
          <div className="flex flex-wrap gap-1.5">
            {TRACKING_STATUSES.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setStatus(item)}
                className={`inline-flex h-8 items-center rounded px-2.5 text-xs font-semibold transition-colors ${
                  status === item ? 'bg-accent text-white shadow-sm' : 'bg-elev2 text-muted hover:text-text'
                }`}
              >
                {item === 'all' ? t.all : statusLabel(item, language)}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 p-3 xl:grid-cols-[minmax(360px,0.95fr)_auto]">
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
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><Send size={12} />{t.from}</span>
              <input value={fromEmail} onChange={(event) => setFromEmail(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><User size={12} />{t.to}</span>
              <input value={toEmail} onChange={(event) => setToEmail(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><CalendarDays size={12} />{t.dateFrom}</span>
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><CalendarDays size={12} />{t.dateTo}</span>
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
          </div>
          <div className="flex items-end justify-end gap-2">
            <button type="button" onClick={() => trackingQ.refetch()} className="btn">
              <RefreshCw size={13} className={trackingQ.isFetching ? 'animate-spin' : ''} />{t.refresh}
            </button>
            <button type="button" onClick={resetFilters} className="btn btn-ghost">{t.reset}</button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(520px,1.05fr)_minmax(360px,0.95fr)]">
        <AsyncState loading={trackingQ.isLoading} error={trackingQ.error} isEmpty={rows.length === 0} emptyMessage={t.empty} height={420}>
          <div className="overflow-hidden rounded-md border border-border bg-elev1">
            <div className="grid grid-cols-[minmax(180px,1.2fr)_120px_120px_90px_100px] gap-3 border-b border-border bg-elev2 px-3 py-2 text-xxs font-semibold text-muted xl:grid-cols-[minmax(180px,1.3fr)_110px_110px_90px_100px_80px]">
              <span>{t.creator}</span>
              <span>{t.latestSent}</span>
              <span>{t.latestReply}</span>
              <span>{t.direction}</span>
              <span>{t.followup}</span>
              <span className="hidden xl:block">{t.count}</span>
            </div>
            <div className="divide-y divide-border">
              {rows.map((item) => {
                const selectedRow = item.creator_id === selected?.creator_id;
                const statusKey = normalizeStatus(item.current_status);
                const flow = actionFlow[statusKey];
                return (
                  <button
                    key={item.creator_id}
                    type="button"
                    onClick={() => setSelectedCreatorId(item.creator_id)}
                    className={`grid w-full grid-cols-[minmax(180px,1.2fr)_120px_120px_90px_100px] gap-3 px-3 py-3 text-left text-xs transition-colors xl:grid-cols-[minmax(180px,1.3fr)_110px_110px_90px_100px_80px] ${
                      selectedRow ? 'bg-accent/10' : 'hover:bg-elev2'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className={`h-2 w-2 shrink-0 rounded-full ${item.needs_followup ? 'bg-warn' : 'bg-accent'}`} />
                        <span className="truncate font-semibold text-text">{creatorTitle(item, language)}</span>
                      </span>
                      <span className="mt-1 block truncate text-muted">{item.to_email || item.creator_email || '-'}</span>
                      <span className="mt-1 block truncate text-muted">{item.last_subject || t.noSubject}</span>
                    </span>
                    <span className="self-start text-muted">{rel(item.latest_outbound_at)}</span>
                    <span className="self-start text-muted">{item.latest_inbound_at ? rel(item.latest_inbound_at) : t.noReply}</span>
                    <span className="self-start text-muted">{directionLabel(item, language)}</span>
                    <span className="self-start">
                      <span className={`rounded px-2 py-0.5 text-xxs font-semibold ${item.needs_followup ? 'bg-warn/15 text-warn' : 'bg-elev2 text-muted'}`}>
                        {formatAge(item, language)}
                      </span>
                      <span className="mt-1 block text-muted">{statusLabel(item.current_status, language)}</span>
                      {flow ? (
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            advanceStatus(item);
                          }}
                          onKeyDown={(event) => {
                            if (event.key !== 'Enter' && event.key !== ' ') return;
                            event.preventDefault();
                            event.stopPropagation();
                            advanceStatus(item);
                          }}
                          className="mt-2 inline-flex h-7 items-center rounded border border-border bg-elev1 px-2 text-xxs font-semibold text-text hover:border-accent disabled:opacity-60"
                        >
                          {t[flow.key]}
                        </span>
                      ) : (
                        <span className="mt-2 block text-xxs text-muted">{t.done}</span>
                      )}
                    </span>
                    <span className="hidden self-start text-muted xl:block">{item.email_count ?? 0}</span>
                  </button>
                );
              })}
            </div>
            <PaginationControls
              page={page}
              pageSize={PAGE_SIZE}
              total={trackingQ.data?.total ?? 0}
              currentCount={rows.length}
              loading={trackingQ.isFetching}
              onPageChange={setPage}
            />
          </div>
        </AsyncState>

        <section className="card overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-text">{selected?.last_subject || t.selectPrompt}</div>
              <div className="mt-1 truncate text-xs text-muted">
                {selected ? `${creatorTitle(selected, language)} · ${selected.from_email || t.unknownSender}` : t.selectPrompt}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {selected?.creator_id && (
                <Link to={`/recommendations/${encodeURIComponent(String(selected.creator_id))}`} className="btn btn-ghost !h-8 text-xs">
                  <ExternalLink size={12} />{t.creatorLink}
                </Link>
              )}
              <button type="button" onClick={copyBody} disabled={!detail} className="btn !h-8 text-xs">
                <Copy size={12} />{copyState || t.copy}
              </button>
            </div>
          </div>
          {selected && (
            <div className="grid grid-cols-2 gap-2 border-b border-border p-3 text-xs md:grid-cols-3">
              {[
                [t.email, selected.to_email || selected.creator_email || '-'],
                [t.account, selected.from_email || '-'],
                [t.owner, selected.owner_bd || '-'],
                [t.latestSent, rel(selected.latest_outbound_at)],
                [t.latestReply, selected.latest_inbound_at ? rel(selected.latest_inbound_at) : t.noReply],
                [t.count, String(selected.email_count ?? 0)],
              ].map(([label, value]) => (
                <div key={label} className="min-w-0 rounded-md border border-border bg-elev2 p-2">
                  <div className="text-xxs text-muted">{label}</div>
                  <div className="mt-1 truncate font-semibold text-text">{value}</div>
                </div>
              ))}
            </div>
          )}
          <AsyncState loading={detailQ.isLoading} error={detailQ.error} isEmpty={!selected?.latest_email_id} emptyMessage={t.selectPrompt} height={420}>
            {detail?.body_format === 'html' ? (
              <iframe title={t.detailsTitle} sandbox="" srcDoc={safeEmailHtml(detail.body)} className="block h-[620px] w-full bg-white" />
            ) : (
              <pre className="h-[620px] overflow-auto whitespace-pre-wrap p-4 text-sm leading-relaxed text-text">{detail?.body || t.bodyEmpty}</pre>
            )}
          </AsyncState>
        </section>
      </div>
    </div>
  );
}
