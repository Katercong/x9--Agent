import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
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
import {
  useGmailReplySyncStatus,
  useGmailSyncReplies,
  useOutreachArchive,
  useOutreachTracking,
  useReplyOutreachArchive,
} from '@/hooks/useApi';
import { formatDateTime, maskEmail, shortRelative } from '@/lib/format';
import type { GmailReplySyncAccount, OutreachArchiveItem, OutreachTrackingItem } from '@/api/types';

type ThreadStatus = 'waiting' | 'replied' | 'syncing' | 'missing_sender';
type NoticeTone = 'good' | 'bad' | 'info';

interface EmailThread {
  id: string;
  creatorId: string;
  creatorHandle: string | null;
  creatorDisplayName: string | null;
  creatorEmail: string;
  senderEmail: string | null;
  subject: string;
  status: ThreadStatus;
  currentStatus: string;
  gmailThreadId: string | null;
  latestEmailId: string | null;
  bdOwner: string | null;
  lastActivityAt: string | null;
  lastCheckedAt: string | null;
  nextCheckAt: string | null;
  latestDirection: string | null;
  needsFollowup: boolean;
  emailCount: number;
  lastPreview: string | null;
}

const STATUS_META: Record<ThreadStatus, { label: string; tone: 'good' | 'warn' | 'bad' | 'info' | 'muted'; icon: typeof Clock }> = {
  waiting: { label: '待回复', tone: 'warn', icon: Clock },
  replied: { label: '已回复', tone: 'good', icon: Reply },
  syncing: { label: '同步中', tone: 'info', icon: RefreshCw },
  missing_sender: { label: '缺少发件邮箱', tone: 'bad', icon: XCircle },
};

const STATUS_FILTERS: Array<{ key: 'all' | ThreadStatus; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'waiting', label: '待回复' },
  { key: 'replied', label: '已回复' },
  { key: 'syncing', label: '同步中' },
  { key: 'missing_sender', label: '缺少邮箱' },
];

export default function Emails() {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | ThreadStatus>('all');
  const [senderFilter, setSenderFilter] = useState('all');
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [draftSubject, setDraftSubject] = useState('');
  const [draftBody, setDraftBody] = useState('');
  const [composerNote, setComposerNote] = useState<{ text: string; tone: NoticeTone } | null>(null);
  const [syncNote, setSyncNote] = useState('');

  const tracking = useOutreachTracking({
    q: query.trim() || undefined,
    from_email: senderFilter === 'all' ? undefined : senderFilter,
  });
  const syncStatus = useGmailReplySyncStatus();
  const syncReplies = useGmailSyncReplies();
  const reply = useReplyOutreachArchive();

  const threads = useMemo(
    () => buildThreads(tracking.data?.items ?? [], syncStatus.data?.background?.running),
    [tracking.data?.items, syncStatus.data?.background?.running],
  );

  const senderOptions = useMemo(
    () => Array.from(new Set(threads.map((thread) => thread.senderEmail).filter(Boolean) as string[])).sort(),
    [threads],
  );

  const filteredThreads = useMemo(() => (
    threads.filter((thread) => statusFilter === 'all' || thread.status === statusFilter)
  ), [statusFilter, threads]);

  const selectedThread = useMemo(() => {
    if (selectedThreadId) {
      const byId = filteredThreads.find((thread) => thread.id === selectedThreadId);
      if (byId) return byId;
    }
    return filteredThreads[0] ?? threads[0] ?? null;
  }, [filteredThreads, selectedThreadId, threads]);

  const archive = useOutreachArchive({
    creator_id: selectedThread?.creatorId ?? '__none__',
    limit: 100,
    offset: 0,
  });

  const accounts = useMemo(
    () => syncStatus.data?.items ?? syncStatus.data?.accounts ?? [],
    [syncStatus.data?.accounts, syncStatus.data?.items],
  );

  const messages = useMemo(
    () => messagesForThread(archive.data?.items ?? [], selectedThread),
    [archive.data?.items, selectedThread],
  );

  const senderStatus = useMemo(
    () => senderStatusFor(selectedThread?.senderEmail, accounts),
    [accounts, selectedThread?.senderEmail],
  );

  const replySourceId = useMemo(
    () => selectReplySourceId(messages, selectedThread),
    [messages, selectedThread],
  );

  useEffect(() => {
    if (!selectedThread) {
      setDraftSubject('');
      setDraftBody('');
      setComposerNote(null);
      return;
    }
    const saved = loadLocalDraft(selectedThread);
    setDraftSubject(saved?.subject || `Re: ${stripReplyPrefix(selectedThread.subject)}`);
    setDraftBody(saved?.body || buildFollowUpDraft(selectedThread));
    setComposerNote(null);
  }, [selectedThread?.id]);

  useEffect(() => {
    if (selectedThreadId && !threads.some((thread) => thread.id === selectedThreadId)) {
      setSelectedThreadId(null);
    }
  }, [selectedThreadId, threads]);

  const kpis = useMemo(() => {
    const waiting = threads.filter((thread) => thread.status === 'waiting').length;
    const replied = threads.filter((thread) => thread.status === 'replied').length;
    const riskyAccounts = accounts.filter((account) => !isReadableAccount(account)).length;
    const missingSender = threads.filter((thread) => thread.status === 'missing_sender').length;
    return { waiting, replied, riskyAccounts, missingSender };
  }, [accounts, threads]);

  const handleSync = async () => {
    setSyncNote('');
    try {
      const result = await syncReplies.mutateAsync({ limit_per_account: 2500 });
      const running = result.running || result.background?.running;
      setSyncNote(`${running ? '同步已启动' : '同步已提交'} · ${formatDateTime(new Date())}`);
      await Promise.all([tracking.refetch(), syncStatus.refetch()]);
    } catch (error) {
      setSyncNote(`同步失败：${errorMessage(error)}`);
    }
  };

  const handleSave = () => {
    if (!selectedThread) return;
    saveLocalDraft(selectedThread, draftSubject, draftBody);
    setComposerNote({ text: '草稿已保存到当前浏览器', tone: 'good' });
  };

  const handleSend = async () => {
    if (!selectedThread || !replySourceId) {
      setComposerNote({ text: '找不到可回复的邮件记录', tone: 'bad' });
      return;
    }
    if (!senderStatus.canSend) {
      setComposerNote({ text: senderStatus.reason, tone: 'bad' });
      return;
    }
    if (!draftBody.trim()) {
      setComposerNote({ text: '正文不能为空', tone: 'bad' });
      return;
    }
    try {
      await reply.mutateAsync({
        id: replySourceId,
        body: {
          subject: draftSubject.trim() || `Re: ${stripReplyPrefix(selectedThread.subject)}`,
          body: draftBody.trim(),
          body_format: 'plain',
        },
      });
      clearLocalDraft(selectedThread);
      setComposerNote({ text: '已发送回复，并写入沟通记录', tone: 'good' });
      await Promise.all([tracking.refetch(), archive.refetch(), syncStatus.refetch()]);
    } catch (error) {
      setComposerNote({ text: `发送失败：${errorMessage(error)}`, tone: 'bad' });
    }
  };

  const isLoading = tracking.isLoading;
  const error = tracking.error;
  const totalThreads = tracking.data?.total ?? threads.length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <KpiCard label="跟踪达人" value={totalThreads} subLabel="已发送邮件自动归档" icon={Inbox} iconBg="#e0f2fe" iconColor="#0284c7" />
        <KpiCard label="待回复" value={kpis.waiting} subLabel="按真实入站回复检查" icon={Clock} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="已有回复" value={kpis.replied} subLabel="Gmail 回信或待跟进" icon={CheckCircle2} iconBg="#dcfce7" iconColor="#16a34a" />
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
          <button type="button" className="btn ml-auto" onClick={handleSync} disabled={syncReplies.isPending}>
            <RefreshCw size={12} className={syncReplies.isPending ? 'animate-spin' : ''} />
            {syncReplies.isPending ? '同步中' : '立即同步'}
          </button>
          <Link to="/d/creators" className="btn btn-primary">
            <Send size={12} />
            新建建联
          </Link>
        </div>
        <AccountStrip accounts={accounts} note={syncNote} />
      </div>

      <AsyncState loading={isLoading} error={error} isEmpty={threads.length === 0} height={420}>
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(340px,0.95fr)_minmax(420px,1.25fr)_minmax(340px,0.9fr)] gap-3 items-start">
          <ThreadList
            threads={filteredThreads}
            total={tracking.data?.total ?? filteredThreads.length}
            selectedThreadId={selectedThread?.id ?? null}
            onSelect={(thread) => setSelectedThreadId(thread.id)}
          />
          <ConversationPanel
            thread={selectedThread}
            accounts={accounts}
            messages={messages}
            loading={archive.isLoading && Boolean(selectedThread)}
            error={archive.error}
          />
          <ComposerPanel
            thread={selectedThread}
            subject={draftSubject}
            body={draftBody}
            note={composerNote}
            senderStatus={senderStatus}
            isSending={reply.isPending}
            onSubjectChange={setDraftSubject}
            onBodyChange={setDraftBody}
            onSave={handleSave}
            onSend={handleSend}
          />
        </div>
      </AsyncState>
    </div>
  );
}

function AccountStrip({ accounts, note }: { accounts: GmailReplySyncAccount[]; note: string }) {
  if (accounts.length === 0 && !note) {
    return (
      <div className="px-4 py-2 border-t border-line flex items-center gap-2 overflow-x-auto">
        <span className="text-xxs text-muted whitespace-nowrap">邮箱授权池</span>
        <a href={gmailAuthorizeHref()} className="inline-flex items-center gap-1.5 rounded border border-blue-100 bg-blue-50 px-2 py-1 text-xxs font-semibold text-blue-700 whitespace-nowrap">
          授权 Gmail
        </a>
      </div>
    );
  }
  return (
    <div className="px-4 py-2 border-t border-line flex items-center gap-2 overflow-x-auto">
      <span className="text-xxs text-muted whitespace-nowrap">邮箱授权池</span>
      {accounts.map((account) => {
        const healthy = isReadableAccount(account);
        return (
          <span key={account.account_id} className="inline-flex items-center gap-1.5 border border-line rounded px-2 py-1 text-xxs bg-white whitespace-nowrap">
            <span className={`w-1.5 h-1.5 rounded-full ${healthy ? 'bg-green-500' : 'bg-red-500'}`} />
            {account.email}
            <span className={healthy ? 'text-green-700' : 'text-red-700'}>
              {healthy ? '已完整授权' : '未授权'}
            </span>
            {!healthy && (
              <a
                href={gmailAuthorizeHref(account.email)}
                className="rounded bg-red-100 px-1.5 py-0.5 font-semibold text-red-800 hover:bg-red-200"
              >
                立即授权
              </a>
            )}
          </span>
        );
      })}
      {note && <span className={`text-xxs ml-auto whitespace-nowrap ${note.includes('失败') ? 'text-bad' : 'text-good'}`}>{note}</span>}
    </div>
  );
}

function ThreadList({
  threads,
  total,
  selectedThreadId,
  onSelect,
}: {
  threads: EmailThread[];
  total: number;
  selectedThreadId: string | null;
  onSelect: (thread: EmailThread) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-800">达人邮件线程</h3>
          <div className="text-xxs text-muted">按达人 + Gmail 线程归档真实回信</div>
        </div>
        <Pill tone="info">{total} 条</Pill>
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
  messages,
  loading,
  error,
}: {
  thread: EmailThread | null;
  accounts: GmailReplySyncAccount[];
  messages: OutreachArchiveItem[];
  loading: boolean;
  error: unknown;
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
        <Fact icon={<RefreshCw size={12} />} label="下次检查" value={thread.nextCheckAt ? formatDateTime(thread.nextCheckAt) : '等待同步'} />
      </div>

      <div className="p-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="text-xs font-semibold text-gray-800">沟通记录</div>
          <div className="flex items-center gap-1.5">
            {account && (
              <Pill tone={isReadableAccount(account) ? 'good' : 'bad'}>
                {isReadableAccount(account) ? '可同步' : '需授权'}
              </Pill>
            )}
            <Pill tone="muted">{messages.length || thread.emailCount} 封</Pill>
          </div>
        </div>
        <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
          {loading && <SystemCheckpoint icon={<RefreshCw size={13} className="animate-spin" />} title="正在加载沟通记录" meta="从邮件归档读取真实入站/出站消息" />}
          {Boolean(error) && <SystemCheckpoint icon={<AlertTriangle size={13} />} title="沟通记录加载失败" meta={errorMessage(error)} tone="bad" />}
          {!loading && !error && messages.map((message) => (
            <MessageRow key={message.id} message={message} />
          ))}
          {!loading && !error && messages.length === 0 && (
            <MessageRow message={fallbackMessage(thread)} />
          )}
          {thread.status === 'waiting' && (
            <SystemCheckpoint
              icon={<Clock size={13} />}
              title="等待达人回复"
              meta={thread.lastCheckedAt ? `最近检查 ${formatDateTime(thread.lastCheckedAt)}` : '等待首次同步'}
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
  senderStatus,
  isSending,
  onSubjectChange,
  onBodyChange,
  onSave,
  onSend,
}: {
  thread: EmailThread | null;
  subject: string;
  body: string;
  note: { text: string; tone: NoticeTone } | null;
  senderStatus: { canSend: boolean; canSync: boolean; reason: string };
  isSending: boolean;
  onSubjectChange: (value: string) => void;
  onBodyChange: (value: string) => void;
  onSave: () => void;
  onSend: () => void;
}) {
  const disabled = !thread || !thread.senderEmail || !senderStatus.canSend || isSending;
  const noteClass = note?.tone === 'bad'
    ? 'text-bad bg-red-50 border-red-100'
    : note?.tone === 'info'
      ? 'text-blue-700 bg-blue-50 border-blue-100'
      : 'text-good bg-green-50 border-green-100';
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-800">邮件编辑</h3>
          <div className="text-xxs text-muted">同线程回复，发件邮箱按原建联记录锁定</div>
        </div>
        <Pill tone={disabled ? 'bad' : 'good'}>
          <Lock size={10} />
          {disabled ? '不可发送' : '已锁定'}
        </Pill>
      </div>

      <div className="p-4 space-y-3">
        <ReadonlyField label="From" value={thread?.senderEmail || '缺少发件邮箱'} bad={!thread?.senderEmail || !senderStatus.canSend} />
        <ReadonlyField label="To" value={thread?.creatorEmail || '未选择达人'} />
        {!senderStatus.canSync && thread && (
          <div className="rounded border border-red-100 bg-red-50 px-3 py-2 text-xxs text-red-700">
            {senderStatus.reason}
          </div>
        )}
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
          <button type="button" className="btn justify-center" disabled title="当前跟踪页暂未接入 AI 润色">
            <Sparkles size={12} />
            AI润色
          </button>
          <button type="button" className="btn btn-primary justify-center" disabled={disabled} onClick={onSend}>
            <Send size={12} className={isSending ? 'animate-pulse' : ''} />
            {isSending ? '发送中' : '发送'}
          </button>
        </div>
        {note && (
          <div className={`text-xxs border rounded px-3 py-2 ${noteClass}`}>
            {note.text}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageRow({ message }: { message: OutreachArchiveItem }) {
  const sentAt = mailTime(message);
  const direction = messageDirection(message);
  const failed = direction === 'bounce' || message.status === 'failed';
  const inbound = direction === 'inbound';
  const Icon = failed ? AlertTriangle : inbound ? Inbox : Send;
  const iconClass = failed ? 'bg-red-50 text-red-600' : inbound ? 'bg-green-50 text-green-700' : 'bg-blue-50 text-blue-600';
  return (
    <div className="flex items-start gap-3">
      <div className={`w-8 h-8 rounded flex items-center justify-center shrink-0 ${iconClass}`}>
        <Icon size={15} />
      </div>
      <div className="min-w-0 flex-1 border border-line rounded p-3 bg-white">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-semibold text-gray-900 truncate">{message.subject || '无主题'}</div>
          <Pill tone={failed ? 'bad' : inbound ? 'warn' : 'good'}>{messageStatusLabel(message)}</Pill>
        </div>
        <div className="text-xxs text-muted mt-1">
          {message.from_email || '未选择'} → {message.to_email || '—'} · {formatDateTime(sentAt)}
        </div>
        <div className="text-xs text-gray-700 mt-2 whitespace-pre-line line-clamp-4">
          {messagePreview(message)}
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

function buildThreads(rows: OutreachTrackingItem[], backgroundSyncing?: boolean): EmailThread[] {
  return rows.map((row) => {
    const senderEmail = row.from_email || null;
    const status = deriveThreadStatus(row, senderEmail, backgroundSyncing);
    const lastActivityAt = row.latest_message_at || row.latest_inbound_at || row.latest_outbound_at || null;
    return {
      id: row.gmail_thread_id || [row.creator_id, normalizeEmail(row.to_email || row.creator_email || ''), normalizeEmail(senderEmail || 'pending')].join(':'),
      creatorId: String(row.creator_id),
      creatorHandle: row.creator_handle || null,
      creatorDisplayName: row.creator_display_name || null,
      creatorEmail: row.to_email || row.creator_email || '',
      senderEmail,
      subject: row.last_subject || '',
      status,
      currentStatus: row.current_status || '',
      gmailThreadId: row.gmail_thread_id || null,
      latestEmailId: row.latest_email_id || null,
      bdOwner: row.owner_bd || null,
      lastActivityAt,
      lastCheckedAt: row.latest_inbound_at || row.latest_outbound_at || lastActivityAt,
      nextCheckAt: addMinutes(lastActivityAt, 10),
      latestDirection: row.latest_direction || null,
      needsFollowup: Boolean(row.needs_followup),
      emailCount: Number(row.email_count || 1),
      lastPreview: row.last_preview || null,
    } satisfies EmailThread;
  });
}

function deriveThreadStatus(row: OutreachTrackingItem, senderEmail: string | null, backgroundSyncing?: boolean): ThreadStatus {
  if (!senderEmail) return 'missing_sender';
  if (backgroundSyncing && row.latest_direction !== 'inbound' && !row.latest_inbound_at) return 'syncing';
  if (row.needs_followup || row.latest_direction === 'inbound' || row.latest_inbound_at) return 'replied';
  const currentStatus = `${row.current_status || ''}`.toLowerCase();
  if (/(沟通|已寄样|样品|视频|授权|广告|communicat|sample|published|authorized)/.test(currentStatus)) return 'replied';
  return 'waiting';
}

function messagesForThread(rows: OutreachArchiveItem[], thread: EmailThread | null): OutreachArchiveItem[] {
  if (!thread) return [];
  return thread.gmailThreadId
    ? rows.filter((row) => row.gmail_thread_id === thread.gmailThreadId)
    : rows;
}

function fallbackMessage(thread: EmailThread): OutreachArchiveItem {
  return {
    id: thread.latestEmailId || thread.id,
    creator_id: thread.creatorId,
    to_email: thread.creatorEmail,
    from_email: thread.senderEmail,
    subject: thread.subject || '无主题',
    body_preview: thread.lastPreview || '暂无正文预览',
    body_format: 'plain',
    status: thread.latestDirection === 'inbound' ? 'inbound' : 'sent',
    direction: thread.latestDirection === 'inbound' ? 'inbound' : 'outbound',
    sent_at: thread.lastActivityAt,
    created_at: thread.lastActivityAt,
    gmail_thread_id: thread.gmailThreadId,
  };
}

function selectReplySourceId(messages: OutreachArchiveItem[], thread: EmailThread | null): string | null {
  const inbound = messages.find((message) => messageDirection(message) === 'inbound');
  const outbound = messages.find((message) => messageDirection(message) !== 'bounce');
  return inbound?.id || outbound?.id || thread?.latestEmailId || null;
}

function senderStatusFor(senderEmail: string | null | undefined, accounts: GmailReplySyncAccount[]): { canSend: boolean; canSync: boolean; reason: string } {
  if (!senderEmail) return { canSend: false, canSync: false, reason: '缺少锁定发件邮箱，不能发送同线程回复' };
  const account = accounts.find((item) => item.email?.toLowerCase() === senderEmail.toLowerCase());
  if (!account) return { canSend: false, canSync: false, reason: '发件邮箱未授权，请先完成 Gmail 授权' };
  if (!isReadableAccount(account)) {
    return { canSend: false, canSync: false, reason: '该邮箱未完成完整授权，请先重新授权后再发送或同步回信。' };
  }
  return { canSend: true, canSync: true, reason: '已锁定发件邮箱' };
}

function isReadableAccount(account: GmailReplySyncAccount): boolean {
  const status = `${account.status || ''}`.toLowerCase();
  return Boolean(account.has_readonly_scope && status !== 'needs_reauth' && !account.error);
}

function creatorLabel(thread: EmailThread): string {
  return thread.creatorDisplayName || thread.creatorHandle || `creator-${thread.creatorId}`;
}

function buildFollowUpDraft(thread: EmailThread): string {
  const name = thread.creatorDisplayName || thread.creatorHandle || 'there';
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

function messageDirection(message: OutreachArchiveItem): string {
  const value = `${message.direction || message.status || ''}`.toLowerCase();
  if (value === 'inbound' || value === 'bounce') return value;
  return 'outbound';
}

function messageStatusLabel(message: OutreachArchiveItem): string {
  const direction = messageDirection(message);
  if (direction === 'inbound') return '达人回复';
  if (direction === 'bounce') return '退信';
  const map: Record<string, string> = {
    draft: '草稿',
    queued: '队列中',
    sent: '已发送',
    failed: '失败',
    cancelled: '已取消',
  };
  return map[message.status] || '已发送';
}

function messagePreview(message: OutreachArchiveItem): string {
  const body = 'body' in message ? String((message as OutreachArchiveItem & { body?: string | null }).body || '') : '';
  return message.body_preview || plainText(body, message.body_format) || '—';
}

function plainText(value: string, format?: string | null): string {
  if (!value) return '';
  let text = value;
  if ((format || '').toLowerCase() === 'html' || /<\/?[a-z][\s\S]*>/i.test(value)) {
    text = value
      .replace(/<(br|\/p|\/div|\/li)\b[^>]*>/gi, '\n')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<[^>]+>/g, ' ');
  }
  return decodeHtml(text).replace(/\s+/g, ' ').trim();
}

function decodeHtml(value: string): string {
  return value
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function statusBorder(status: ThreadStatus): string {
  const map: Record<ThreadStatus, string> = {
    waiting: 'border-l-amber-400',
    replied: 'border-l-green-500',
    syncing: 'border-l-blue-500',
    missing_sender: 'border-l-red-500',
  };
  return map[status];
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function mailTime(row: OutreachArchiveItem): string | null {
  return row.sent_at || row.created_at || null;
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

function draftStorageKey(thread: EmailThread): string {
  return `x9-email-thread-draft:${thread.id}`;
}

function loadLocalDraft(thread: EmailThread): { subject: string; body: string } | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(thread));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { subject?: unknown; body?: unknown };
    if (typeof parsed.subject === 'string' && typeof parsed.body === 'string') {
      return { subject: parsed.subject, body: parsed.body };
    }
  } catch {
    return null;
  }
  return null;
}

function saveLocalDraft(thread: EmailThread, subject: string, body: string) {
  window.localStorage.setItem(draftStorageKey(thread), JSON.stringify({ subject, body }));
}

function clearLocalDraft(thread: EmailThread) {
  window.localStorage.removeItem(draftStorageKey(thread));
}

function gmailAuthorizeHref(email?: string | null): string {
  const label = email ? `email-sync:${email}` : 'email-sync';
  return `/api/local/outreach/gmail/connect?label=${encodeURIComponent(label)}&return_to=${encodeURIComponent('/d/emails')}`;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error || '未知错误');
}
