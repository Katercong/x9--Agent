import { useState } from 'react';
import {
  AtSign,
  Brain,
  Clock3,
  ExternalLink,
  FileText,
  Heart,
  Link as LinkIcon,
  Mail,
  MessageCircle,
  NotebookText,
  Sparkles,
  Telescope,
  Users,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import {
  useForeignTradeCollection,
  type ContactItem,
  type LeadItem,
  type SocialCommentEvidence,
  type SocialNoteEvidence,
  type SocialSourceEvidence,
} from '@/api/foreignTrade';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

const PAGE_SIZE = 25;

const PLATFORM_LABELS: Record<string, string> = { xhs: '小红书', douyin: '抖音' };
const CONTACT_LABELS: Record<string, string> = {
  email: '邮箱',
  phone: '手机',
  wechat: '微信',
  url: '链接',
  xhs_handle: '小红书号',
  douyin_handle: '抖音号',
  platform_handle: '平台账号',
};
const SOURCE_LABELS: Record<string, string> = {
  post_author: '内容作者',
  comment_author: '评论作者',
  reply_author: '回复作者',
  mentioned_user: '提及用户',
  profile_history: '历史作品',
  manual: '手动来源',
};
const DECISION_LABELS: Record<string, string> = {
  target_customer: '目标客户',
  experienced_seller: '经验卖家',
  logistics_partner: '物流伙伴',
  supplier_peer: '供应方同行',
  high_priority: '高意向',
  potential: '潜在线索',
  follow_up: '待跟进',
  nurture: '培育',
  irrelevant: '无关',
  ignore: '忽略',
  error: '判定失败',
};

function parseTimeMs(value: string): number {
  const text = String(value || '').trim();
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(text);
  const normalized = !hasZone && /^\d{4}-\d{2}-\d{2}[T ]/.test(text) ? `${text.replace(' ', 'T')}+08:00` : text;
  return new Date(normalized).getTime();
}

function shortTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const ts = parseTimeMs(value);
  if (!Number.isFinite(ts)) return '暂无';
  const minutes = Math.floor((Date.now() - ts) / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(ts).toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' });
}

function clean(value: unknown): string {
  return String(value ?? '').trim();
}

function countText(value: number | null | undefined): string {
  if (!value) return '0';
  if (value >= 10000) return `${(value / 10000).toFixed(1)}w`;
  return num(value);
}

function decisionTone(value?: string | null): 'good' | 'warn' | 'bad' | 'info' | 'muted' {
  const key = clean(value);
  if (key === 'target_customer' || key === 'experienced_seller' || key === 'high_priority') return 'good';
  if (key === 'potential' || key === 'follow_up' || key === 'nurture' || key === 'logistics_partner') return 'warn';
  if (key === 'supplier_peer' || key === 'irrelevant' || key === 'ignore' || key === 'error') return 'bad';
  return 'muted';
}

function ProfileLink({ href, label = '主页' }: { href?: string | null; label?: string }) {
  if (!clean(href)) return null;
  return (
    <a
      href={href || '#'}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xxs text-brand hover:underline"
    >
      <LinkIcon size={12} /> {label}
    </a>
  );
}

function Avatar({ row }: { row: LeadItem }) {
  const initial = clean(row.name).slice(0, 1) || '社';
  if (row.avatar_url) {
    return <img src={row.avatar_url} alt="" className="h-10 w-10 shrink-0 rounded-full object-cover" />;
  }
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-pink-100 text-sm font-semibold text-pink-600">
      {initial}
    </div>
  );
}

function TagList({ items, max = 5 }: { items?: string[]; max?: number }) {
  const values = (items || []).map(clean).filter(Boolean).slice(0, max);
  if (!values.length) return null;
  return (
    <div className="flex max-w-[480px] flex-wrap gap-1">
      {values.map((item) => <Pill key={item} tone="muted" className="text-[10px]">{item}</Pill>)}
    </div>
  );
}

function ContactList({ contacts, fallback }: { contacts?: ContactItem[]; fallback?: string }) {
  const values = (contacts || []).filter((item) => clean(item.value));
  if (!values.length && !clean(fallback)) return <span className="text-xs text-muted">无</span>;
  if (!values.length) return <span className="text-xs text-text">{fallback}</span>;
  return (
    <div className="space-y-1.5">
      {values.slice(0, 8).map((item, index) => (
        <div key={`${item.type}-${item.value}-${index}`} className="flex max-w-[360px] items-start gap-1.5 text-xs">
          <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
            {clean(item.label) || CONTACT_LABELS[item.type] || item.type}
          </span>
          <span className="break-all text-text">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function CommentEvidence({ items }: { items?: SocialCommentEvidence[] }) {
  const rows = (items || []).filter((item) => clean(item.content)).slice(0, 4);
  if (!rows.length) return <span className="text-xs text-muted">暂无评论证据</span>;
  return (
    <div className="space-y-2">
      {rows.map((item, index) => (
        <div key={item.id || index} className="space-y-1">
          <div className="whitespace-normal break-words text-xs leading-5 text-text">{item.content}</div>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted">
            {item.location ? <span>{item.location}</span> : null}
            {item.published_at_text ? <span>{item.published_at_text}</span> : null}
            {item.note_title ? <span className="max-w-[220px] truncate">来自: {item.note_title}</span> : null}
            <ProfileLink href={item.note_url} label="原文" />
          </div>
        </div>
      ))}
    </div>
  );
}

function NoteEvidence({ notes, history }: { notes?: SocialNoteEvidence[]; history?: SocialNoteEvidence[] }) {
  const rows = [...(notes || []), ...(history || [])].filter((item) => clean(item.title || item.desc)).slice(0, 3);
  if (!rows.length) return null;
  return (
    <div className="mt-3 space-y-2 border-t border-border pt-2">
      {rows.map((item, index) => (
        <div key={`${item.id || item.url || index}`} className="grid grid-cols-[38px_1fr] gap-2">
          {item.cover_url ? (
            <img src={item.cover_url} alt="" className="h-10 w-10 rounded object-cover" />
          ) : (
            <div className="flex h-10 w-10 items-center justify-center rounded bg-slate-100 text-slate-400">
              <NotebookText size={14} />
            </div>
          )}
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-text">{item.title || item.desc}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-muted">
              {item.like_count !== null && item.like_count !== undefined ? <span>赞 {countText(item.like_count)}</span> : null}
              {item.comment_count !== null && item.comment_count !== undefined ? <span>评 {countText(item.comment_count)}</span> : null}
              {item.keyword ? <span>{item.keyword}</span> : null}
              <ProfileLink href={item.url} label="查看" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SourceEvidence({ items }: { items?: SocialSourceEvidence[] }) {
  const rows = (items || []).filter((item) => clean(item.evidence_text || item.keyword)).slice(0, 4);
  if (!rows.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {rows.map((item, index) => (
        <Pill key={`${item.source_type}-${item.keyword}-${index}`} tone="info" className="text-[10px]">
          {SOURCE_LABELS[item.source_type || ''] || item.source_type || '来源'} · {item.keyword || clean(item.evidence_text).slice(0, 18)}
        </Pill>
      ))}
    </div>
  );
}

function JudgmentCell({ row }: { row: LeadItem }) {
  const label = DECISION_LABELS[row.decision || ''] || row.decision || '未判定';
  const evidence = clean(row.judgment_evidence) || clean(row.judgment);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={decisionTone(row.decision)}>{label}</Pill>
        {row.fit_score !== null && row.fit_score !== undefined ? <span className="num text-sm font-semibold text-text">{row.fit_score}</span> : null}
        {row.customer_priority ? <Pill tone={decisionTone(row.decision)}>{row.customer_priority}</Pill> : null}
        {row.fit_level ? <Pill tone="muted">{row.fit_level}</Pill> : null}
        {row.intent_type ? <Pill tone="info">{row.intent_type}</Pill> : null}
      </div>
      <div className="max-w-[420px] whitespace-normal break-words text-xxs leading-5 text-muted">
        {evidence || '清洗完成，等待自动评分'}
      </div>
      {row.judgment_suggestion ? (
        <div className="max-w-[420px] whitespace-normal break-words text-xxs leading-5 text-text">{row.judgment_suggestion}</div>
      ) : null}
    </div>
  );
}

export default function CollectSocial() {
  const A = ACCENTS.social;
  const [page, setPage] = useState(0);
  const feed = useForeignTradeCollection({ channel: 'social', limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const stats = feed.data?.stats ?? {};
  const items = feed.data?.items ?? [];
  const total = feed.data?.total ?? 0;

  const columns: Column<LeadItem>[] = [
    {
      key: 'profile',
      header: '清洗后博主资料',
      width: '390px',
      cell: (row) => (
        <div className="min-w-[340px] space-y-2">
          <div className="flex items-start gap-3">
            <Avatar row={row} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone="info">{PLATFORM_LABELS[row.platform || ''] || row.platform || '社媒'}</Pill>
                {row.clean_status ? <Pill tone="muted">{row.clean_status}</Pill> : null}
                {row.has_contact ? <Pill tone="good">已提取联系入口</Pill> : null}
              </div>
              <div className="mt-1 whitespace-normal break-words text-sm font-semibold text-text">{row.name || '未命名博主'}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xxs text-muted">
                {row.account ? <span className="inline-flex items-center gap-1"><AtSign size={11} />{row.account}</span> : null}
                <ProfileLink href={row.profile_url} />
              </div>
            </div>
          </div>
          <div className="max-w-[560px] whitespace-normal break-words text-xxs leading-5 text-muted">{row.bio || '暂无简介'}</div>
          <TagList items={(row.platform_signals?.length ? row.platform_signals : row.contact_signals) || []} />
        </div>
      ),
    },
    {
      key: 'evidence',
      header: '清洗证据内容',
      width: '520px',
      cell: (row) => (
        <div className="min-w-[460px]">
          <CommentEvidence items={row.recent_comments} />
          <NoteEvidence notes={row.recent_notes} history={row.history_posts} />
          <SourceEvidence items={row.source_samples} />
        </div>
      ),
    },
    {
      key: 'contacts',
      header: '清洗提取联系方式',
      width: '310px',
      cell: (row) => <ContactList contacts={row.contacts} fallback={row.contact} />,
    },
    {
      key: 'judgment',
      header: 'GPT 意向判定',
      width: '360px',
      cell: (row) => <JudgmentCell row={row} />,
    },
    {
      key: 'metrics',
      header: '内容量 / 时间',
      align: 'right',
      width: '170px',
      cell: (row) => (
        <div className="space-y-1 text-right text-xs">
          <div className="num text-sm font-semibold text-text">{countText(row.followers)}</div>
          <div className="text-xxs text-muted">粉丝</div>
          <div className="flex flex-wrap justify-end gap-1">
            <Pill tone="muted">{countText(row.profile_note_count ?? row.notes_count ?? 0)} 作品</Pill>
            <Pill tone="muted">{countText(row.comments_count ?? 0)} 评论</Pill>
            {row.liked_collect_count ? <Pill tone="muted">获赞 {countText(row.liked_collect_count)}</Pill> : null}
          </div>
          <div className="text-xxs text-muted">{shortTime(row.created_at)}</div>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={Heart} title="小红书 / 抖音采集" subtitle="博主 / 笔记 / 评论 / 联系方式与采购意向清洗结果" />

      <AsyncState loading={feed.isLoading} error={feed.error} height={420}>
        <Reveal i={1}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <KpiCard label="总博主线索" value={num(stats.total)} icon={Users} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="今日采集" value={num(stats.today)} icon={Clock3} iconBg="rgb(99 102 241 / 0.16)" iconColor="#818cf8" />
            <KpiCard label="采集批次" value={num(stats.runs)} icon={Telescope} iconBg="rgb(6 182 212 / 0.16)" iconColor="#22d3ee" />
            <KpiCard label="内容 / 评论" value={`${num(stats.notes)} / ${num(stats.comments)}`} icon={MessageCircle} iconBg="rgb(16 185 129 / 0.16)" iconColor="#10b981" />
            <KpiCard label="联系方式" value={num(stats.contacts ?? stats.with_contact)} icon={Mail} iconBg="rgb(37 99 235 / 0.16)" iconColor="#60a5fa" />
            <KpiCard label="GPT 判定" value={num(stats.judgments ?? stats.high_intent)} icon={Brain} iconBg="rgb(239 68 68 / 0.16)" iconColor="#f87171" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <FileText size={16} style={{ color: A.key }} />
                <h3 className="text-sm font-semibold text-text">全端采集后清洗入库的社媒线索</h3>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xxs text-muted">
                <span>{num(total)} 个清洗后博主</span>
                <span>每页 {PAGE_SIZE}</span>
                {stats.sources ? <span className="inline-flex items-center gap-1"><Sparkles size={12} />{num(stats.sources)} 条来源</span> : null}
                {stats.media ? <span className="inline-flex items-center gap-1"><ExternalLink size={12} />{num(stats.media)} 个媒体</span> : null}
              </div>
            </div>
            <div className="p-2">
              <AsyncState
                loading={feed.isLoading}
                error={feed.error}
                isEmpty={!feed.isLoading && items.length === 0}
                emptyMessage="还没有小红书 / 抖音采集后的清洗数据"
                height={300}
              >
                <DataTable columns={columns} data={items} rowKey={(row) => row.id} emptyText="还没有采集记录" />
                <PaginationControls
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={total}
                  currentCount={items.length}
                  loading={feed.isFetching}
                  onPageChange={setPage}
                />
              </AsyncState>
            </div>
            <div className="h-1" style={{ background: A.key }} />
          </section>
        </Reveal>
      </AsyncState>
    </div>
  );
}
