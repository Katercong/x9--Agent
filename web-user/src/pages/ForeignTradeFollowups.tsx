import { useEffect, useMemo, useState } from 'react';
import {
  Building2,
  CalendarClock,
  ClipboardCopy,
  ExternalLink,
  FileText,
  Handshake,
  Loader2,
  MessageSquareText,
  Search,
  Send,
  UserRound,
} from 'lucide-react';
import {
  useForeignTradeFollowups,
  useSubmitForeignTradeFollowup,
  type ForeignTradeContactStatus,
  type ForeignTradeFollowupRecord,
  type ForeignTradeLeadType,
} from '@/api/foreignTrade';

const STATUS_META: Record<ForeignTradeContactStatus, { label: string; tone: string }> = {
  pending_contact: { label: '待建联', tone: 'bg-slate-500/10 text-slate-300 border-slate-500/25' },
  contact_started: { label: '已打开主页', tone: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/25' },
  follow_up: { label: '待跟进', tone: 'bg-amber-500/10 text-amber-300 border-amber-500/25' },
  replied: { label: '已回复', tone: 'bg-sky-500/10 text-sky-300 border-sky-500/25' },
  interested: { label: '有意向', tone: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/25' },
  invalid: { label: '无效', tone: 'bg-rose-500/10 text-rose-300 border-rose-500/25' },
  converted: { label: '已转化', tone: 'bg-lime-500/10 text-lime-300 border-lime-500/25' },
};

const STATUS_OPTIONS: ForeignTradeContactStatus[] = [
  'contact_started',
  'follow_up',
  'replied',
  'interested',
  'invalid',
  'converted',
];

function statusClass(status: ForeignTradeContactStatus) {
  return `inline-flex items-center rounded-full border px-2 py-0.5 text-xxs ${STATUS_META[status].tone}`;
}

function leadTypeLabel(value: ForeignTradeLeadType) {
  return value === 'customer' ? '客户推荐' : '公司推荐';
}

function platformLabel(value?: string | null) {
  if (value === 'xhs') return '小红书';
  if (value === 'douyin') return '抖音';
  if (value === '51job') return '51job';
  if (value === 'zhaopin') return '智联招聘';
  if (value === 'qzrc') return '大泉州人才网';
  return value || '来源';
}

function formatTime(value?: string | null) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function toDatetimeLocal(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function ForeignTradeFollowups() {
  const [leadType, setLeadType] = useState<ForeignTradeLeadType | 'all'>('all');
  const [status, setStatus] = useState<ForeignTradeContactStatus | 'all'>('all');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formStatus, setFormStatus] = useState<ForeignTradeContactStatus>('follow_up');
  const [note, setNote] = useState('');
  const [nextAt, setNextAt] = useState('');

  const followupsQuery = useForeignTradeFollowups({
    lead_type: leadType === 'all' ? undefined : leadType,
    status,
    limit: 500,
    offset: 0,
  });
  const submitMutation = useSubmitForeignTradeFollowup();

  const items = followupsQuery.data?.items || [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      if (!q) return true;
      return [
        item.lead_name,
        item.account,
        item.platform,
        item.contact_label,
        item.followup_note,
        item.owner_name,
      ].some((value) => String(value || '').toLowerCase().includes(q));
    });
  }, [items, query]);

  const selected = filtered.find((item) => item.id === selectedId) || filtered[0] || null;

  useEffect(() => {
    if (!selected) return;
    setSelectedId(selected.id);
    setFormStatus(selected.status === 'pending_contact' ? 'contact_started' : selected.status);
    setNote(selected.followup_note || '');
    setNextAt(toDatetimeLocal(selected.next_followup_at));
  }, [selected?.id]);

  const counts = followupsQuery.data?.counts || {};
  const activeCount = (counts.contact_started || 0) + (counts.follow_up || 0) + (counts.replied || 0) + (counts.interested || 0);
  const customerCount = items.filter((item) => item.lead_type === 'customer').length;
  const companyCount = items.filter((item) => item.lead_type === 'company').length;

  const copyCard = async (item: ForeignTradeFollowupRecord) => {
    const text = [
      `类型: ${leadTypeLabel(item.lead_type)}`,
      `名称: ${item.lead_name || '--'}`,
      item.account ? `账号: ${item.account}` : '',
      item.profile_url ? `主页: ${item.profile_url}` : '',
      item.comment_url ? `评论链接: ${item.comment_url}` : '',
      item.source_url ? `来源链接: ${item.source_url}` : '',
      `状态: ${STATUS_META[item.status].label}`,
      item.followup_note ? `备注: ${item.followup_note}` : '',
    ].filter(Boolean).join('\n');
    await navigator.clipboard?.writeText(text);
  };

  const submit = async () => {
    if (!selected) return;
    await submitMutation.mutateAsync({
      recordId: selected.id,
      status: formStatus,
      note,
      result: STATUS_META[formStatus].label,
      next_followup_at: nextAt || undefined,
    });
  };

  return (
    <div className="space-y-4">
      <section className="rounded-md border border-border bg-elev1 p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xxs uppercase tracking-[0.18em] text-muted">
              <Handshake size={14} className="text-accent" />
              Foreign Trade Follow-up Desk
            </div>
            <h1 className="mt-2 text-xl font-semibold text-text">建联跟进系统</h1>
            <p className="mt-1 max-w-3xl text-xs text-muted">
              客户推荐页点击建联后会进入这里。联系人提交状态、备注和下次跟进时间，形成外贸客户建联记录。
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-right">
            <Kpi label="跟进中" value={activeCount} />
            <Kpi label="客户" value={customerCount} />
            <Kpi label="公司" value={companyCount} />
          </div>
        </div>
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-3">
          <div className="rounded-md border border-border bg-elev1 p-3">
            <div className="grid gap-2 lg:grid-cols-[1fr_auto_auto]">
              <label className="flex h-9 items-center gap-2 rounded-md border border-border bg-bg px-3">
                <Search size={14} className="text-muted" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索客户 / 公司 / 账号 / 负责人 / 备注"
                  className="input-bare w-full"
                />
              </label>
              <Segmented
                value={leadType}
                onChange={(value) => setLeadType(value as ForeignTradeLeadType | 'all')}
                items={[
                  ['all', '全部'],
                  ['customer', '客户'],
                  ['company', '公司'],
                ]}
              />
              <Segmented
                value={status}
                onChange={(value) => setStatus(value as ForeignTradeContactStatus | 'all')}
                items={[
                  ['all', '全部状态'],
                  ['contact_started', '已打开'],
                  ['follow_up', '待跟进'],
                  ['interested', '有意向'],
                ]}
              />
            </div>
          </div>

          {followupsQuery.isLoading && (
            <div className="flex h-48 items-center justify-center gap-2 rounded-md border border-border bg-elev1 text-xs text-muted">
              <Loader2 size={14} className="animate-spin" />正在加载跟进记录
            </div>
          )}
          {!followupsQuery.isLoading && followupsQuery.error && (
            <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-200">
              跟进记录加载失败：{followupsQuery.error instanceof Error ? followupsQuery.error.message : String(followupsQuery.error)}
            </div>
          )}
          {!followupsQuery.isLoading && !followupsQuery.error && filtered.length === 0 && (
            <div className="rounded-md border border-dashed border-border bg-elev1 p-8 text-center text-xs text-muted">
              暂无建联跟进记录
            </div>
          )}

          <div className="space-y-2">
            {filtered.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedId(item.id)}
                className={`w-full rounded-md border p-3 text-left transition ${selected?.id === item.id ? 'border-accent bg-accent/10' : 'border-border bg-elev1 hover:border-accent/60 hover:bg-elev2/60'}`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent/15 text-accent">
                    {item.lead_type === 'customer' ? <UserRound size={18} /> : <Building2 size={18} />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-semibold">{item.lead_name || '未命名线索'}</span>
                      <span className={statusClass(item.status)}>{STATUS_META[item.status].label}</span>
                      <span className="rounded-full bg-bg px-2 py-0.5 text-xxs text-muted">{leadTypeLabel(item.lead_type)}</span>
                    </div>
                    <div className="mt-1 truncate text-xxs text-muted">
                      {platformLabel(item.platform)} · {item.account || item.contact_label || '无账号'} · 负责人 {item.owner_name || '--'}
                    </div>
                    <div className="mt-2 line-clamp-2 text-xs leading-5 text-text/90">
                      {item.followup_note || item.contact_label || '点击右侧提交本次跟进结果'}
                    </div>
                  </div>
                  <div className="w-24 shrink-0 text-right text-xxs text-muted">
                    <div>{formatTime(item.opened_at)}</div>
                    <div className="mt-1">打开 {item.opened_count || 0} 次</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <aside className="rounded-md border border-border bg-elev1">
          {!selected ? (
            <div className="flex h-96 items-center justify-center text-xs text-muted">选择一条记录查看名片和提交跟进</div>
          ) : (
            <div className="flex h-full flex-col">
              <div className="border-b border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="truncate text-lg font-semibold">{selected.lead_name || '未命名线索'}</h2>
                      <span className={statusClass(selected.status)}>{STATUS_META[selected.status].label}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted">{leadTypeLabel(selected.lead_type)} · {platformLabel(selected.platform)}</div>
                  </div>
                </div>
                <div className="mt-4 grid gap-2">
                  <InfoLine icon={<UserRound size={14} />} label="账号" value={selected.account || '--'} />
                  <InfoLine icon={<LinkTextIcon />} label="联系方式" value={selected.contact_label || '--'} />
                  <InfoLine icon={<CalendarClock size={14} />} label="下次跟进" value={formatTime(selected.next_followup_at)} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {selected.profile_url && <a className="btn btn-primary !h-8" href={selected.profile_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />主页</a>}
                  {selected.comment_url && <a className="btn !h-8" href={selected.comment_url} target="_blank" rel="noreferrer"><MessageSquareText size={13} />评论</a>}
                  {selected.source_url && <a className="btn !h-8" href={selected.source_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />来源</a>}
                  <button type="button" className="btn btn-ghost !h-8" onClick={() => copyCard(selected)}><ClipboardCopy size={13} />复制名片</button>
                </div>
              </div>

              <div className="space-y-3 p-4">
                <label className="block">
                  <span className="mb-1 block text-xxs text-muted">跟进状态</span>
                  <select className="input h-9 w-full" value={formStatus} onChange={(event) => setFormStatus(event.target.value as ForeignTradeContactStatus)}>
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>{STATUS_META[option].label}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xxs text-muted">下次跟进时间</span>
                  <input className="input h-9 w-full" type="datetime-local" value={nextAt} onChange={(event) => setNextAt(event.target.value)} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xxs text-muted">跟进备注</span>
                  <textarea
                    className="input min-h-[140px] w-full resize-y py-2"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="记录对方是否回复、需求品类、货源痛点、下一步动作"
                  />
                </label>
                <button type="button" className="btn btn-primary w-full" onClick={submit} disabled={submitMutation.isPending}>
                  {submitMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                  提交跟进
                </button>
              </div>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}

function Segmented({ value, items, onChange }: { value: string; items: Array<[string, string]>; onChange: (value: string) => void }) {
  return (
    <div className="flex h-9 rounded-md border border-border bg-bg p-1">
      {items.map(([key, label]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`rounded px-3 text-xxs transition ${value === key ? 'bg-accent text-slate-950' : 'text-muted hover:text-text'}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-[92px] rounded-md border border-border bg-bg px-3 py-2">
      <div className="num text-lg font-semibold">{value}</div>
      <div className="text-xxs text-muted">{label}</div>
    </div>
  );
}

function LinkTextIcon() {
  return <FileText size={14} />;
}

function InfoLine({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-bg px-3 py-2">
      <div className="flex items-center gap-1.5 text-xxs text-muted">{icon}{label}</div>
      <div className="mt-1 truncate text-xs">{value}</div>
    </div>
  );
}
