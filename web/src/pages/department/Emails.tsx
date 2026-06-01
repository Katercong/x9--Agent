import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Filter,
  History,
  Inbox,
  Lock,
  Mail,
  MessageSquareText,
  PenLine,
  RefreshCw,
  Reply,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useCreators, useResource, useUnifiedDashboard } from '@/hooks/useApi';
import { formatDateTime, maskEmail, shortRelative } from '@/lib/format';
import type { Creator, UnifiedDashboardGmailAccount } from '@/api/types';

interface OutreachEmail {
  id: string;
  creator_id: string | number;
  to_email: string;
  from_email?: string | null;
  subject: string;
  body: string;
  body_format?: string | null;
  status: string;
  gmail_message_id?: string | null;
  gmail_thread_id?: string | null;
  error_message?: string | null;
  created_by?: string | null;
  sent_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

type ThreadStatus = 'waiting' | 'replied' | 'draft' | 'failed' | 'syncing' | 'missing_sender';

interface EmailThread {
  id: string;
  creatorId: string;
  creator?: Creator;
  creatorEmail: string;
  senderEmail: string | null;
  subject: string;
  status: ThreadStatus;
  gmailThreadId: string | null;
  gmailMessageId: string | null;
  bdOwner: string | null;
  createdBy: string | null;
  firstSentAt: string | null;
  lastActivityAt: string | null;
  lastCheckedAt: string | null;
  nextCheckAt: string | null;
  messages: OutreachEmail[];
  lastBody: string;
  errorMessage: string | null;
}

const PAGE_SIZE = 500;

const STATUS_META: Record<ThreadStatus, { label: string; tone: 'good' | 'warn' | 'bad' | 'info' | 'muted'; icon: typeof Clock }> = {
  waiting: { label: '待回复', tone: 'warn', icon: Clock },
  replied: { label: '已回复', tone: 'good', icon: Reply },
  draft: { label: '草稿', tone: 'muted', icon: PenLine },
  failed: { label: '异常', tone: 'bad', icon: AlertTriangle },
  syncing: { label: '同步中', tone: 'info', icon: RefreshCw },
  missing_sender: { label: '缺少发件邮箱', tone: 'bad', icon: XCircle },
};

const STATUS_FILTERS: Array<{ key: 'all' | ThreadStatus; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'waiting', label: '待回复' },
  { key: 'replied', label: '已回复' },
  { key: 'failed', label: '异常' },
  { key: 'missing_sender', label: '缺少邮箱' },
];

export default function Emails() {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | ThreadStatus>('all');
  const [senderFilter, setSenderFilter] = useState('all');
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [draftSubject, setDraftSubject] = useState('');
  const [draftBody, setDraftBody] = useState('');
  const [composerNote, setComposerNote] = useState('');
  const [syncNote, setSyncNote] = useState('');

  const emails = useResource<OutreachEmail>('outreach_emails', {
    limit: PAGE_SIZE,
    offset: 0,
    order_by: 'created_at:desc',
  });
  const creators = useCreators({ limit: PAGE_SIZE, offset: 0 });
  const unified = useUnifiedDashboard();

  const creatorMap = useMemo(() => {
    const map = new Map<string, Creator>();
    (creators.data?.items ?? []).forEach((creator) => {
      map.set(String(creator.id), creator);
    });
    return map;
  }, [creators.data?.items]);

  const threads = useMemo(
    () => buildThreads(emails.data?.items ?? [], creatorMap),
    [emails.data?.items, creatorMap],
  );

  const senderOptions = useMemo(
    () => Array.from(new Set(threads.map((thread) => thread.senderEmail).filter(Boolean) as string[])).sort(),
    [threads],
  );

  const filteredThreads = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return threads.filter((thread) => {
      const statusMatch = statusFilter === 'all' || thread.status === statusFilter;
      const senderMatch = senderFilter === 'all' || thread.senderEmail === senderFilter;
      const creatorName = thread.creator?.handle || thread.creator?.display_name || thread.creatorId;
      const text = [
        creatorName,
        thread.creatorEmail,
        thread.senderEmail,
        thread.subject,
        thread.bdOwner,
        thread.createdBy,
      ].join(' ').toLowerCase();
      return statusMatch && senderMatch && (!needle || text.includes(needle));
    });
  }, [query, senderFilter, statusFilter, threads]);

  const selectedThread = useMemo(() => {
    if (selectedThreadId) {
      const byId = filteredThreads.find((thread) => thread.id === selectedThreadId);
      if (byId) return byId;
    }
    return filteredThreads[0] ?? threads[0] ?? null;
  }, [filteredThreads, selectedThreadId, threads]);

  useEffect(() => {
    if (!selectedThread) {
      setDraftSubject('');
      setDraftBody('');
      return;
    }
    setDraftSubject(`Re: ${stripReplyPrefix(selectedThread.subject)}`);
    setDraftBody(buildFollowUpDraft(selectedThread));
    setComposerNote('');
  }, [selectedThread?.id]);

  const gmailAccounts = unified.data?.gmail_sync.accounts ?? [];
  const kpis = useMemo(() => {
    const waiting = threads.filter((thread) => thread.status === 'waiting').length;
    const replied = threads.filter((thread) => thread.status === 'replied').length;
    const riskyAccounts = gmailAccounts.filter((account) => account.reauthorization_required || !account.readonly_scope).length;
    const missingSender = threads.filter((thread) => thread.status === 'missing_sender').length;
    return { waiting, replied, riskyAccounts, missingSender };
  }, [gmailAccounts, threads]);

  const isLoading = emails.isLoading || creators.isLoading;
  const error = emails.error || creators.error;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <KpiCard label="跟踪达人" value={threads.length} subLabel="已发送邮件自动归档" icon={Inbox} iconBg="#e0f2fe" iconColor="#0284c7" />
        <KpiCard label="待回复" value={kpis.waiting} subLabel="按原发件邮箱检查" icon={Clock} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="已有回复" value={kpis.replied} subLabel="进入沟通跟进" icon={CheckCircle2} iconBg="#dcfce7" iconColor="#16a34a" />
        <KpiCard label="授权风险" value={kpis.riskyAccounts + kpis.missingSender} subLabel="缺少只读或发件邮箱" icon={ShieldCheck} iconBg="#fee2e2" iconColor="#dc2626" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 bg-soft border border-line rounded px-2.5 py-1.5 w-full sm:w-80">
            <Search size={14} className="text-muted shrink-0" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索达人、邮箱、主题、BD"
              className="flex-1 bg-transparent outline-none text-xs min-w-0"
            />
          </div>
          <div className="inline-flex items-center rounded border border-line overflow-hidden bg-white">
            {STATUS_FILTERS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setStatusFilter(item.key)}
                className={`px-3 py-1.5 text-xs border-r border-line last:border-r-0 transition-colors ${
                  statusFilter === item.key ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-soft'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5 border border-line rounded px-2 py-1.5 bg-white">
            <Filter size={13} className="text-muted" />
            <select
              value={senderFilter}
              onChange={(event) => setSenderFilter(event.target.value)}
              className="text-xs bg-transparent outline-none max-w-56"
            >
              <option value="all">全部发件邮箱</option>
              {senderOptions.map((email) => (
                <option key={email} value={email}>{email}</option>
              ))}
            </select>
          </div>
          <button type="button" className="btn ml-auto" onClick={() => setSyncNote(`同步检查已排队 · ${formatDateTime(new Date())}`)}>
            <RefreshCw size={12} />
            立即同步
          </button>
          <button type="button" className="btn btn-primary">
            <Send size={12} />
            新建建联
          </button>
        </div>
        <AccountStrip accounts={gmailAccounts} note={syncNote} />
      </div>

      <AsyncState loading={isLoading} error={error} isEmpty={threads.length === 0} height={420}>
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(340px,0.95fr)_minmax(420px,1.25fr)_minmax(340px,0.9fr)] gap-3 items-start">
          <ThreadList
            threads={filteredThreads}
            selectedThreadId={selectedThread?.id ?? null}
            onSelect={(thread) => setSelectedThreadId(thread.id)}
          />
          <ConversationPanel thread={selectedThread} accounts={gmailAccounts} />
          <ComposerPanel
            thread={selectedThread}
            subject={draftSubject}
            body={draftBody}
            note={composerNote}
            onSubjectChange={setDraftSubject}
            onBodyChange={setDraftBody}
            onSave={() => setComposerNote('草稿已暂存')}
            onSend={() => setComposerNote('已进入发送确认')}
          />
        </div>
      </AsyncState>
    </div>
  );
}

function AccountStrip({ accounts, note }: { accounts: UnifiedDashboardGmailAccount[]; note: string }) {
  if (accounts.length === 0 && !note) return null;
  return (
    <div className="px-4 py-2 border-t border-line flex items-center gap-2 overflow-x-auto">
      <span className="text-xxs text-muted whitespace-nowrap">邮箱授权池</span>
      {accounts.map((account) => {
        const healthy = Boolean(account.readonly_scope && !account.reauthorization_required && account.is_active);
        return (
          <span key={account.account_id} className="inline-flex items-center gap-1.5 border border-line rounded px-2 py-1 text-xxs bg-white whitespace-nowrap">
            <span className={`w-1.5 h-1.5 rounded-full ${healthy ? 'bg-green-500' : 'bg-red-500'}`} />
            {account.email}
            <span className={healthy ? 'text-green-700' : 'text-red-600'}>
              {healthy ? '可读写' : '需重连'}
            </span>
          </span>
        );
      })}
      {note && <span className="text-xxs text-good ml-auto whitespace-nowrap">{note}</span>}
    </div>
  );
}

function ThreadList({
  threads,
  selectedThreadId,
  onSelect,
}: {
  threads: EmailThread[];
  selectedThreadId: string | null;
  onSelect: (thread: EmailThread) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-800">达人邮件线程</h3>
          <div className="text-xxs text-muted">按达人邮箱 + 原发件邮箱归档</div>
        </div>
        <Pill tone="info">{threads.length} 条</Pill>
      </div>
      <div className="max-h-[680px] overflow-y-auto divide-y divide-line/70">
        {threads.length === 0 ? (
          <div className="px-4 py-10 text-center text-xs text-muted">没有匹配的邮件线程</div>
        ) : (
          threads.map((thread) => (
            <ThreadButton
              key={thread.id}
              thread={thread}
              selected={thread.id === selectedThreadId}
              onClick={() => onSelect(thread)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ThreadButton({ thread, selected, onClick }: { thread: EmailThread; selected: boolean; onClick: () => void }) {
  const meta = STATUS_META[thread.status];
  const Icon = meta.icon;
  const creatorName = creatorLabel(thread);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left px-4 py-3 border-l-4 transition-colors ${
        selected ? 'bg-brand-50 border-l-brand-500' : statusBorder(thread.status)
      } hover:bg-soft`}
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded bg-gray-900 text-white flex items-center justify-center text-xs font-semibold shrink-0">
          {creatorName.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-900 truncate">@{creatorName}</span>
            <Pill tone={meta.tone} className="shrink-0">
              <Icon size={10} />
              {meta.label}
            </Pill>
          </div>
          <div className="text-xxs text-muted truncate mt-0.5">{thread.subject || '无主题'}</div>
          <div className="flex items-center gap-2 mt-2 text-xxs text-muted min-w-0">
            <span className="truncate">{maskEmail(thread.creatorEmail)}</span>
            <span className="text-gray-300">/</span>
            <span className="truncate">{thread.senderEmail ? maskEmail(thread.senderEmail) : '未锁定'}</span>
          </div>
        </div>
        <div className="text-xxs text-muted whitespace-nowrap">{shortRelative(thread.lastActivityAt)}</div>
      </div>
    </button>
  );
}

function ConversationPanel({
  thread,
  accounts,
}: {
  thread: EmailThread | null;
  accounts: UnifiedDashboardGmailAccount[];
}) {
  if (!thread) return <EmptyPanel title="沟通历史" />;
  const meta = STATUS_META[thread.status];
  const account = thread.senderEmail
    ? accounts.find((item) => item.email?.toLowerCase() === thread.senderEmail?.toLowerCase())
    : null;

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-start gap-3">
        <div className="w-11 h-11 rounded bg-gradient-to-br from-gray-900 to-gray-700 text-white flex items-center justify-center text-sm font-semibold shrink-0">
          {creatorLabel(thread).slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-gray-900">@{creatorLabel(thread)}</h3>
            <Pill tone={meta.tone}>{meta.label}</Pill>
            {thread.bdOwner && <Pill tone="muted">BD {thread.bdOwner}</Pill>}
          </div>
          <div className="text-xxs text-muted mt-1 truncate">{thread.subject || '无主题'}</div>
        </div>
      </div>

      <div className="px-4 py-3 bg-soft border-b border-line grid grid-cols-1 md:grid-cols-2 gap-2">
        <Fact icon={<Mail size={12} />} label="达人邮箱" value={thread.creatorEmail} />
        <Fact icon={<Lock size={12} />} label="锁定发件" value={thread.senderEmail || '未锁定'} tone={thread.senderEmail ? 'normal' : 'bad'} />
        <Fact icon={<History size={12} />} label="Gmail Thread" value={thread.gmailThreadId || '待回写'} />
        <Fact icon={<RefreshCw size={12} />} label="下次检查" value={thread.nextCheckAt ? formatDateTime(thread.nextCheckAt) : '10 分钟轮询'} />
      </div>

      <div className="p-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="text-xs font-semibold text-gray-800">沟通记录</div>
          <div className="flex items-center gap-1.5">
            {account && (
              <Pill tone={account.readonly_scope && !account.reauthorization_required ? 'good' : 'bad'}>
                {account.readonly_scope && !account.reauthorization_required ? '可同步' : '需授权'}
              </Pill>
            )}
            <Pill tone="muted">{thread.messages.length} 封</Pill>
          </div>
        </div>
        <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
          {thread.messages.map((message) => (
            <MessageRow key={message.id} message={message} />
          ))}
          {thread.status === 'waiting' && (
            <SystemCheckpoint
              icon={<Clock size={13} />}
              title="等待达人回复"
              meta={thread.lastCheckedAt ? `最近检查 ${formatDateTime(thread.lastCheckedAt)}` : '等待首次同步'}
            />
          )}
          {thread.status === 'failed' && (
            <SystemCheckpoint
              icon={<AlertTriangle size={13} />}
              title="发送或同步异常"
              meta={thread.errorMessage || '需要人工确认授权和线程状态'}
              tone="bad"
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ComposerPanel({
  thread,
  subject,
  body,
  note,
  onSubjectChange,
  onBodyChange,
  onSave,
  onSend,
}: {
  thread: EmailThread | null;
  subject: string;
  body: string;
  note: string;
  onSubjectChange: (value: string) => void;
  onBodyChange: (value: string) => void;
  onSave: () => void;
  onSend: () => void;
}) {
  const disabled = !thread || !thread.senderEmail;
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-800">邮件编辑</h3>
          <div className="text-xxs text-muted">强制使用建联发件邮箱</div>
        </div>
        <Pill tone={disabled ? 'bad' : 'good'}>
          <Lock size={10} />
          {disabled ? '不可发送' : '已锁定'}
        </Pill>
      </div>

      <div className="p-4 space-y-3">
        <ReadonlyField label="From" value={thread?.senderEmail || '缺少发件邮箱'} bad={!thread?.senderEmail} />
        <ReadonlyField label="To" value={thread?.creatorEmail || '未选择达人'} />
        <label className="block">
          <span className="text-xxs text-muted">Subject</span>
          <input
            type="text"
            value={subject}
            onChange={(event) => onSubjectChange(event.target.value)}
            disabled={!thread}
            className="mt-1 w-full border border-line rounded px-3 py-2 text-xs outline-none focus:border-brand-400 disabled:bg-soft"
          />
        </label>
        <label className="block">
          <span className="text-xxs text-muted">Body</span>
          <textarea
            value={body}
            onChange={(event) => onBodyChange(event.target.value)}
            disabled={!thread}
            rows={14}
            className="mt-1 w-full border border-line rounded px-3 py-2 text-xs outline-none focus:border-brand-400 resize-none disabled:bg-soft"
          />
        </label>

        <div className="grid grid-cols-3 gap-2">
          <button type="button" className="btn justify-center" disabled={!thread} onClick={onSave}>
            <PenLine size={12} />
            保存草稿
          </button>
          <button type="button" className="btn justify-center" disabled={!thread}>
            <Sparkles size={12} />
            AI润色
          </button>
          <button type="button" className="btn btn-primary justify-center" disabled={disabled} onClick={onSend}>
            <Send size={12} />
            发送
          </button>
        </div>
        {note && (
          <div className="text-xxs text-good bg-green-50 border border-green-100 rounded px-3 py-2">
            {note}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageRow({ message }: { message: OutreachEmail }) {
  const sentAt = message.sent_at || message.created_at || message.updated_at;
  const failed = message.status === 'failed';
  return (
    <div className="flex items-start gap-3">
      <div className={`w-8 h-8 rounded flex items-center justify-center shrink-0 ${failed ? 'bg-red-50 text-red-600' : 'bg-blue-50 text-blue-600'}`}>
        {failed ? <AlertTriangle size={15} /> : <Send size={15} />}
      </div>
      <div className="min-w-0 flex-1 border border-line rounded p-3 bg-white">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-semibold text-gray-900 truncate">{message.subject || '无主题'}</div>
          <Pill tone={failed ? 'bad' : message.status === 'sent' ? 'good' : 'muted'}>{statusLabel(message.status)}</Pill>
        </div>
        <div className="text-xxs text-muted mt-1">
          {message.from_email || '未选择'} → {message.to_email} · {formatDateTime(sentAt)}
        </div>
        <div className="text-xs text-gray-700 mt-2 whitespace-pre-line line-clamp-4">
          {message.body || message.error_message || '—'}
        </div>
      </div>
    </div>
  );
}

function SystemCheckpoint({
  icon,
  title,
  meta,
  tone = 'muted',
}: {
  icon: ReactNode;
  title: string;
  meta: string;
  tone?: 'muted' | 'bad';
}) {
  return (
    <div className={`flex items-start gap-3 rounded border border-dashed px-3 py-2 ${tone === 'bad' ? 'border-red-200 bg-red-50 text-red-700' : 'border-line bg-soft text-muted'}`}>
      <div className="mt-0.5">{icon}</div>
      <div className="min-w-0">
        <div className="text-xs font-medium">{title}</div>
        <div className="text-xxs truncate">{meta}</div>
      </div>
    </div>
  );
}

function Fact({
  icon,
  label,
  value,
  tone = 'normal',
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: 'normal' | 'bad';
}) {
  return (
    <div className="flex items-start gap-2 min-w-0">
      <span className={tone === 'bad' ? 'text-red-500 mt-0.5' : 'text-muted mt-0.5'}>{icon}</span>
      <div className="min-w-0">
        <div className="text-xxs text-muted">{label}</div>
        <div className={`text-xs truncate ${tone === 'bad' ? 'text-red-600 font-medium' : 'text-gray-800'}`}>{value}</div>
      </div>
    </div>
  );
}

function ReadonlyField({ label, value, bad = false }: { label: string; value: string; bad?: boolean }) {
  return (
    <label className="block">
      <span className="text-xxs text-muted">{label}</span>
      <div className={`mt-1 border rounded px-3 py-2 text-xs min-h-9 flex items-center truncate ${bad ? 'border-red-200 bg-red-50 text-red-700' : 'border-line bg-soft text-gray-800'}`}>
        {value}
      </div>
    </label>
  );
}

function EmptyPanel({ title }: { title: string }) {
  return (
    <div className="card card-body min-h-[360px] flex items-center justify-center text-center">
      <div>
        <MessageSquareText size={26} className="mx-auto text-muted mb-2" />
        <div className="text-sm font-semibold text-gray-800">{title}</div>
        <div className="text-xxs text-muted mt-1">请选择一条邮件线程</div>
      </div>
    </div>
  );
}

function buildThreads(rows: OutreachEmail[], creatorMap: Map<string, Creator>): EmailThread[] {
  const groups = new Map<string, OutreachEmail[]>();
  rows
    .filter((row) => row.to_email)
    .forEach((row) => {
      const creatorId = String(row.creator_id);
      const key = row.gmail_thread_id || [
        creatorId,
        normalizeEmail(row.to_email),
        normalizeEmail(row.from_email || 'pending'),
      ].join(':');
      const list = groups.get(key) ?? [];
      list.push(row);
      groups.set(key, list);
    });

  return Array.from(groups.entries())
    .map(([id, messages]) => {
      const ordered = [...messages].sort((a, b) => timestamp(a) - timestamp(b));
      const first = ordered[0];
      const latest = ordered[ordered.length - 1];
      const creatorId = String(latest.creator_id || first.creator_id);
      const creator = creatorMap.get(creatorId);
      const senderEmail = latest.from_email || first.from_email || null;
      const status = deriveThreadStatus(ordered, creator, senderEmail);
      const lastActivityAt = latest.sent_at || latest.updated_at || latest.created_at || null;
      return {
        id,
        creatorId,
        creator,
        creatorEmail: latest.to_email || first.to_email,
        senderEmail,
        subject: latest.subject || first.subject || '',
        status,
        gmailThreadId: latest.gmail_thread_id || first.gmail_thread_id || null,
        gmailMessageId: latest.gmail_message_id || first.gmail_message_id || null,
        bdOwner: creator?.owner_bd || null,
        createdBy: latest.created_by || first.created_by || null,
        firstSentAt: first.sent_at || first.created_at || null,
        lastActivityAt,
        lastCheckedAt: lastActivityAt,
        nextCheckAt: addMinutes(lastActivityAt, 10),
        messages: ordered,
        lastBody: latest.body || '',
        errorMessage: latest.error_message || null,
      } satisfies EmailThread;
    })
    .sort((a, b) => dateValue(b.lastActivityAt) - dateValue(a.lastActivityAt));
}

function deriveThreadStatus(messages: OutreachEmail[], creator: Creator | undefined, senderEmail: string | null): ThreadStatus {
  if (!senderEmail && messages.some((message) => message.status === 'sent')) return 'missing_sender';
  if (messages.some((message) => message.status === 'failed')) return 'failed';
  if (messages.some((message) => message.status === 'queued')) return 'syncing';
  if (messages.every((message) => message.status === 'draft')) return 'draft';
  const creatorStatus = `${creator?.current_status || ''}`.toLowerCase();
  if (creatorStatus.includes('回复') || creatorStatus.includes('replied') || creatorStatus.includes('沟通')) return 'replied';
  return 'waiting';
}

function creatorLabel(thread: EmailThread): string {
  return thread.creator?.handle || thread.creator?.display_name || `creator-${thread.creatorId}`;
}

function buildFollowUpDraft(thread: EmailThread): string {
  const name = thread.creator?.display_name || thread.creator?.handle || 'there';
  return [
    `Hi ${name},`,
    '',
    'Thanks again for taking a look at X9. I wanted to follow up and see if the collaboration direction works for you.',
    '',
    'If it is a fit, I can send over the product details, commission setup, and next steps.',
    '',
    'Best,',
    'X9 Team',
  ].join('\n');
}

function stripReplyPrefix(subject: string): string {
  return (subject || '').replace(/^(\s*(re|fw|fwd):\s*)+/i, '').trim() || 'Collaboration with X9';
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    queued: '队列中',
    sent: '已发送',
    failed: '失败',
    cancelled: '已取消',
  };
  return map[status] || status || '未知';
}

function statusBorder(status: ThreadStatus): string {
  const map: Record<ThreadStatus, string> = {
    waiting: 'border-l-amber-400',
    replied: 'border-l-green-500',
    draft: 'border-l-gray-300',
    failed: 'border-l-red-500',
    syncing: 'border-l-blue-500',
    missing_sender: 'border-l-red-500',
  };
  return map[status];
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function timestamp(row: OutreachEmail): number {
  return dateValue(row.sent_at || row.updated_at || row.created_at);
}

function dateValue(value: string | null | undefined): number {
  if (!value) return 0;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function addMinutes(value: string | null | undefined, minutes: number): string | null {
  const base = dateValue(value);
  if (!base) return null;
  return new Date(base + minutes * 60_000).toISOString();
}
