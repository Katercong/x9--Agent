import { useState } from 'react';
import { Brain, Clock3, FileText, Heart, Link as LinkIcon, Mail, MessageCircle, Telescope, Users } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useForeignTradeCollection, type ContactItem, type LeadItem } from '@/api/foreignTrade';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

const PAGE_SIZE = 25;

const PLATFORM_LABELS: Record<string, string> = { xhs: '小红书', douyin: '抖音' };
const DECISION_LABELS: Record<string, string> = {
  target_customer: '目标客户',
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
  const normalized = !hasZone && /^\d{4}-\d{2}-\d{2}[T ]/.test(text) ? `${text.replace(' ', 'T')}Z` : text;
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
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function clean(value: unknown): string {
  return String(value ?? '').trim();
}

function followers(value: number | null | undefined): string {
  if (!value) return '—';
  if (value >= 10000) return `${(value / 10000).toFixed(1)}w`;
  return num(value);
}

function decisionTone(value?: string | null): 'good' | 'warn' | 'bad' | 'info' | 'muted' {
  const key = clean(value);
  if (key === 'target_customer' || key === 'high_priority') return 'good';
  if (key === 'potential' || key === 'follow_up' || key === 'nurture') return 'warn';
  if (key === 'irrelevant' || key === 'ignore') return 'bad';
  if (key === 'error') return 'bad';
  return 'muted';
}

function TagList({ items, max = 4 }: { items?: string[]; max?: number }) {
  const values = (items || []).map(clean).filter(Boolean).slice(0, max);
  if (!values.length) return <span className="text-xxs text-muted">—</span>;
  return (
    <div className="flex max-w-[420px] flex-wrap gap-1">
      {values.map((item) => <Pill key={item} tone="muted" className="text-[10px]">{item}</Pill>)}
    </div>
  );
}

function ContactList({ contacts, fallback }: { contacts?: ContactItem[]; fallback?: string }) {
  const values = (contacts || []).filter((item) => clean(item.value));
  if (!values.length && !clean(fallback)) return <span className="text-xs text-muted">无</span>;
  if (!values.length) return <span className="text-xs text-text">{fallback}</span>;
  return (
    <div className="space-y-1">
      {values.slice(0, 5).map((item, index) => (
        <div key={`${item.type}-${item.value}-${index}`} className="flex max-w-[320px] items-center gap-1.5 text-xs">
          <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-slate-500">{item.type}</span>
          <span className="break-all text-text">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function ProfileLink({ href }: { href?: string | null }) {
  if (!clean(href)) return null;
  return (
    <a
      href={href || '#'}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xxs text-brand hover:underline"
    >
      <LinkIcon size={12} /> 主页
    </a>
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
      width: '360px',
      cell: (row) => (
        <div className="min-w-[320px] space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="info">{PLATFORM_LABELS[row.platform || ''] || row.platform || '社媒'}</Pill>
            {row.clean_status ? <Pill tone="muted">{row.clean_status}</Pill> : null}
            {row.has_contact ? <Pill tone="good">已提取联系方式</Pill> : null}
          </div>
          <div>
            <div className="whitespace-normal break-words text-sm font-semibold text-text">{row.name || '未命名博主'}</div>
            <div className="mt-1 text-xxs text-muted">{row.location || row.subtitle || '未标注地区'}</div>
          </div>
          <div className="max-w-[520px] whitespace-normal break-words text-xxs leading-5 text-muted">{row.bio || '暂无 bio / 简介'}</div>
          <div className="flex flex-wrap items-center gap-2">
            <ProfileLink href={row.profile_url} />
            <TagList items={(row.contact_signals?.length ? row.contact_signals : row.platform_signals) || []} />
          </div>
        </div>
      ),
    },
    {
      key: 'content',
      header: '内容量',
      width: '170px',
      cell: (row) => (
        <div className="space-y-1 text-xs">
          <div className="num text-base font-semibold text-text">{followers(row.followers)}</div>
          <div className="text-xxs text-muted">粉丝</div>
          <div className="flex flex-wrap gap-1">
            <Pill tone="muted">{num(row.notes_count ?? 0)} 笔记/视频</Pill>
            <Pill tone="muted">{num(row.comments_count ?? 0)} 评论</Pill>
          </div>
        </div>
      ),
    },
    {
      key: 'contacts',
      header: '清洗提取联系方式',
      width: '320px',
      cell: (row) => <ContactList contacts={row.contacts} fallback={row.contact} />,
    },
    {
      key: 'judgment',
      header: 'GPT 意向判定',
      cell: (row) => (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={decisionTone(row.decision)}>{DECISION_LABELS[row.decision || ''] || row.decision || '未判定'}</Pill>
            {row.fit_score !== null && row.fit_score !== undefined ? <span className="num text-sm font-semibold text-text">{row.fit_score}</span> : null}
            {row.fit_level ? <Pill tone="muted">{row.fit_level}</Pill> : null}
            {row.intent_type ? <Pill tone="info">{row.intent_type}</Pill> : null}
          </div>
          <div className="max-w-[560px] whitespace-normal break-words text-xxs leading-5 text-muted">{row.judgment || '清洗完成，暂无 GPT 判定'}</div>
        </div>
      ),
    },
    {
      key: 'created',
      header: '采集时间',
      align: 'right',
      width: '110px',
      cell: (row) => <span className="text-xs text-muted">{shortTime(row.created_at)}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={Heart} title="小红书 / 抖音采集" subtitle="博主 / 笔记 / 评论 · 联系方式与采购意向清洗结果" />

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
              <span className="text-xxs text-muted">{num(total)} 个清洗后博主 · 每页 {PAGE_SIZE}</span>
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
