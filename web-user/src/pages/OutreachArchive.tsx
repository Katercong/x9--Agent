import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Archive,
  CalendarDays,
  Copy,
  ExternalLink,
  MailCheck,
  RefreshCw,
  Search,
  User,
  X,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { PaginationControls } from '@/components/PaginationControls';
import { useOutreachArchive, useOutreachArchiveDetail } from '@/hooks/useApi';
import { pickItems, type OutreachArchiveItem } from '@/api/types';
import { shortRelative } from '@/lib/format';

const PAGE_SIZE = 10;

function safeEmailHtml(value?: string | null) {
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>body{margin:0;padding:18px;background:#fff;color:#111827;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}img{max-width:100%;height:auto}</style></head><body>${value || ''}</body></html>`;
}

function creatorTitle(item?: OutreachArchiveItem | null) {
  if (!item) return '未选择邮件';
  return item.creator_display_name || item.creator_handle || `达人 ${item.creator_id}`;
}

function sender(item?: OutreachArchiveItem | null) {
  return item?.from_email || '未知发件人';
}

export default function OutreachArchive() {
  const [q, setQ] = useState('');
  const [fromEmail, setFromEmail] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [copyState, setCopyState] = useState('');

  const params = useMemo(() => ({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    q: q.trim() || undefined,
    from_email: fromEmail.trim() || undefined,
    to_email: toEmail.trim() || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  }), [dateFrom, dateTo, fromEmail, page, q, toEmail]);

  const archiveQ = useOutreachArchive(params);
  const rows = pickItems<OutreachArchiveItem>(archiveQ.data);
  const detailQ = useOutreachArchiveDetail(selectedId);
  const detail = detailQ.data?.item ?? null;
  const selected = detail || rows.find((item) => item.id === selectedId) || null;

  useEffect(() => {
    if (!selectedId && rows.length > 0) setSelectedId(rows[0].id);
    if (selectedId && rows.length > 0 && !rows.some((item) => item.id === selectedId)) {
      setSelectedId(rows[0].id);
    }
  }, [rows, selectedId]);

  useEffect(() => {
    setPage(0);
  }, [dateFrom, dateTo, fromEmail, q, toEmail]);

  const resetFilters = () => {
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
    setCopyState('已复制');
    window.setTimeout(() => setCopyState(''), 1600);
  };

  return (
    <div className="space-y-4">
      <section className="card overflow-hidden">
        <div className="grid gap-3 border-b border-border p-4 lg:grid-cols-[minmax(320px,1fr)_auto]">
          <div>
            <div className="mb-2 inline-flex items-center gap-1 rounded border border-border bg-elev2 px-2 py-1 text-xxs text-muted">
              <Archive size={12} /> 已发送邮件存档
            </div>
            <h2 className="text-lg font-semibold text-text">邮件存档复查</h2>
            <div className="mt-1 text-xs text-muted">同部门成员可复查已发送邮件正文、发件账号和对应达人。</div>
          </div>
          <div className="grid grid-cols-3 gap-2 lg:min-w-[360px]">
            <div className="rounded-md border border-border bg-elev2 p-3">
              <div className="text-xxs text-muted">当前结果</div>
              <div className="num mt-1 text-xl font-semibold">{archiveQ.data?.total ?? rows.length}</div>
            </div>
            <div className="rounded-md border border-border bg-elev2 p-3">
              <div className="text-xxs text-muted">已载入</div>
              <div className="num mt-1 text-xl font-semibold">{rows.length}</div>
            </div>
            <div className="rounded-md border border-border bg-elev2 p-3">
              <div className="text-xxs text-muted">正文格式</div>
              <div className="mt-1 text-sm font-semibold">{detail?.body_format || '-'}</div>
            </div>
          </div>
        </div>

        <div className="grid gap-3 p-3 xl:grid-cols-[minmax(360px,0.95fr)_minmax(420px,1.05fr)]">
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
            <label className="md:col-span-2 xl:col-span-1 2xl:col-span-2">
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><Search size={12} />关键词</span>
              <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-elev1 px-3">
                <input
                  value={q}
                  onChange={(event) => setQ(event.target.value)}
                  placeholder="主题 / 正文 / 达人 / 邮箱"
                  className="min-w-0 flex-1 bg-transparent text-xs outline-none"
                />
                {q && <button type="button" onClick={() => setQ('')} className="text-muted hover:text-text"><X size={13} /></button>}
              </div>
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><MailCheck size={12} />发件人</span>
              <input value={fromEmail} onChange={(event) => setFromEmail(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><User size={12} />收件人</span>
              <input value={toEmail} onChange={(event) => setToEmail(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><CalendarDays size={12} />开始日期</span>
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
            <label>
              <span className="mb-1 flex items-center gap-1 text-xxs font-semibold text-muted"><CalendarDays size={12} />结束日期</span>
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className="input-bare h-9 w-full rounded-md border border-border bg-elev1 px-3" />
            </label>
          </div>
          <div className="flex items-end justify-end gap-2">
            <button type="button" onClick={() => archiveQ.refetch()} className="btn">
              <RefreshCw size={13} className={archiveQ.isFetching ? 'animate-spin' : ''} />刷新
            </button>
            <button type="button" onClick={resetFilters} className="btn btn-ghost">重置</button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(380px,0.9fr)_minmax(0,1.1fr)]">
        <AsyncState loading={archiveQ.isLoading} error={archiveQ.error} isEmpty={rows.length === 0} emptyMessage="暂无已发送邮件存档" height={420}>
          <div className="space-y-2">
            {rows.map((item) => {
              const selectedRow = item.id === selectedId;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={`block w-full rounded-md border p-3 text-left transition-colors ${
                    selectedRow ? 'border-accent bg-accent/10' : 'border-border bg-elev1 hover:border-accent/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-text">{item.subject || '(无主题)'}</div>
                      <div className="mt-1 truncate text-xs text-muted">@{item.creator_handle || item.creator_id} · {sender(item)}</div>
                    </div>
                    <span className="shrink-0 rounded bg-elev2 px-2 py-0.5 text-xxs text-muted">{shortRelative(item.sent_at || item.created_at)}</span>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted">{item.body_preview || '无正文摘要'}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xxs text-muted">
                    <span>To: {item.to_email}</span>
                    <span>{item.body_format || 'plain'}</span>
                  </div>
                </button>
              );
            })}
            <PaginationControls
              page={page}
              pageSize={PAGE_SIZE}
              total={archiveQ.data?.total ?? 0}
              currentCount={rows.length}
              loading={archiveQ.isFetching}
              onPageChange={setPage}
            />
          </div>
        </AsyncState>

        <section className="card overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-text">{selected?.subject || '选择一封邮件查看正文'}</div>
              <div className="mt-1 truncate text-xs text-muted">{creatorTitle(selected)} · {sender(selected)}</div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {selected?.creator_id && (
                <Link to={`/recommendations/${encodeURIComponent(String(selected.creator_id))}`} className="btn btn-ghost !h-8 text-xs">
                  <ExternalLink size={12} />达人
                </Link>
              )}
              <button type="button" onClick={copyBody} disabled={!detail} className="btn !h-8 text-xs">
                <Copy size={12} />{copyState || '复制'}
              </button>
            </div>
          </div>
          <AsyncState loading={detailQ.isLoading} error={detailQ.error} isEmpty={!selectedId} emptyMessage="请选择左侧邮件" height={420}>
            {detail?.body_format === 'html' ? (
              <iframe title="已发送邮件正文" sandbox="" srcDoc={safeEmailHtml(detail.body)} className="block h-[620px] w-full bg-white" />
            ) : (
              <pre className="h-[620px] overflow-auto whitespace-pre-wrap p-4 text-sm leading-relaxed text-text">{detail?.body || '无正文内容'}</pre>
            )}
          </AsyncState>
        </section>
      </div>
    </div>
  );
}
