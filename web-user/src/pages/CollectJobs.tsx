import { useState } from 'react';
import { BadgeCheck, Briefcase, Building2, Clock3, Database, FileText, Link as LinkIcon, MapPin, Star, Users } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useForeignTradeCollection, type ContactItem, type LeadItem } from '@/api/foreignTrade';
import { ACCENTS, CollectHeader, Reveal, num } from './collectShared';

const PAGE_SIZE = 25;

const PLATFORM_LABELS: Record<string, string> = {
  '51job': '前程无忧',
  '51job_talent': '前程无忧',
  zhaopin: '智联招聘',
  zhaopin_resume: '智联招聘',
  qzrc: '大泉州人才网',
  qzrc_job: '大泉州人才网',
  qzrc_resume: '大泉州人才网',
};

const TIER_TONE: Record<string, 'good' | 'warn' | 'muted'> = { A: 'good', B: 'warn', C: 'muted' };
const TYPE_TONE: Record<string, 'info' | 'good' | 'muted'> = { company: 'info', talent: 'good', social: 'muted' };

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

function platformLabel(value: string | null | undefined): string {
  const key = clean(value);
  return PLATFORM_LABELS[key] || key || '未标注';
}

function TextBlock({ value, fallback = '—' }: { value?: string | null; fallback?: string }) {
  const text = clean(value);
  return <div className="max-w-[520px] whitespace-normal break-words text-xxs leading-5 text-muted">{text || fallback}</div>;
}

function TagList({ items, max = 5 }: { items?: string[]; max?: number }) {
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
      {values.slice(0, 4).map((item, index) => (
        <div key={`${item.type}-${item.value}-${index}`} className="flex max-w-[300px] items-center gap-1.5 text-xs">
          <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-slate-500">{item.type}</span>
          <span className="break-all text-text">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function ExternalLink({ href }: { href?: string | null }) {
  if (!clean(href)) return null;
  return (
    <a
      href={href || '#'}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xxs text-brand hover:underline"
    >
      <LinkIcon size={12} /> 来源链接
    </a>
  );
}

export default function CollectJobs() {
  const A = ACCENTS.jobs;
  const [page, setPage] = useState(0);
  const feed = useForeignTradeCollection({ channel: 'jobs', limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const stats = feed.data?.stats ?? {};
  const items = feed.data?.items ?? [];
  const total = feed.data?.total ?? 0;

  const columns: Column<LeadItem>[] = [
    {
      key: 'lead',
      header: '清洗后线索',
      width: '340px',
      cell: (row) => (
        <div className="min-w-[300px] space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={TYPE_TONE[row.kind] || 'muted'}>{row.kind_label || (row.kind === 'talent' ? '跨境人才' : '公司客户')}</Pill>
            {row.tier ? <Pill tone={TIER_TONE[row.tier] || 'muted'}>{row.tier} 级</Pill> : <Pill tone="muted">未评级</Pill>}
            {row.us_market ? <Pill tone="good">美国市场</Pill> : null}
          </div>
          <div>
            <div className="whitespace-normal break-words text-sm font-semibold text-text">{row.name || '未命名线索'}</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xxs text-muted">
              {row.title ? <span className="inline-flex items-center gap-1"><FileText size={12} />{row.title}</span> : null}
              {row.location ? <span className="inline-flex items-center gap-1"><MapPin size={12} />{row.location}</span> : null}
              {row.size_range || row.experience ? <span>{row.size_range || row.experience}</span> : null}
            </div>
          </div>
          <TagList items={(row.tags?.length ? row.tags : row.keywords) || []} />
        </div>
      ),
    },
    {
      key: 'source',
      header: '采集来源',
      width: '190px',
      cell: (row) => (
        <div className="space-y-1 text-xs">
          <div className="font-medium text-text">{platformLabel(row.platform)}</div>
          <div className="text-xxs text-muted">{row.source_type || row.source_mode || row.consent_status || '已清洗入库'}</div>
          <ExternalLink href={row.source_url || row.resume_download_url || row.profile_url} />
        </div>
      ),
    },
    {
      key: 'score',
      header: '评分 / 质量',
      width: '170px',
      cell: (row) => (
        <div className="space-y-1 text-xs">
          <div className="num text-base font-semibold text-text">{num(row.score ?? 0)}</div>
          <div className="flex flex-wrap gap-1">
            {row.data_quality ? <Pill tone="info">{row.data_quality}</Pill> : null}
            {row.llm_score_status ? <Pill tone="muted">{row.llm_score_status}</Pill> : null}
          </div>
          <div className="text-xxs text-muted">{row.next_action || row.cooperation_type || '待跟进'}</div>
        </div>
      ),
    },
    {
      key: 'contact',
      header: '联系方式',
      width: '300px',
      cell: (row) => (
        <div className="space-y-1">
          <ContactList contacts={row.contacts} fallback={row.contact} />
          {(row.contact_name || row.contact_title || row.contact_source) && (
            <div className="text-xxs text-muted">
              {[row.contact_name, row.contact_title, row.contact_source].map(clean).filter(Boolean).join(' / ')}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'clean',
      header: '清洗结果 / 原始信号',
      cell: (row) => (
        <div className="space-y-2">
          <TextBlock value={row.score_reason || row.summary || row.score_suggestion} />
          <TagList items={(row.raw_titles?.length ? row.raw_titles : row.keywords) || []} max={4} />
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
      <CollectHeader accent={A} icon={Briefcase} title="招聘网站采集" subtitle="51job / 智联 / 大泉州 · 公司客户与跨境人才清洗结果" />

      <AsyncState loading={feed.isLoading} error={feed.error} height={420}>
        <Reveal i={1}>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <KpiCard label="总线索" value={num(stats.total)} icon={Database} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="今日采集" value={num(stats.today)} icon={Clock3} iconBg="rgb(99 102 241 / 0.16)" iconColor="#818cf8" />
            <KpiCard label="公司客户" value={num(stats.company_total)} icon={Building2} iconBg="rgb(37 99 235 / 0.16)" iconColor="#60a5fa" />
            <KpiCard label="跨境人才" value={num(stats.talent_total)} icon={Users} iconBg="rgb(34 197 94 / 0.16)" iconColor="#22c55e" />
            <KpiCard label="A 级线索" value={num(stats.tier_a)} icon={Star} iconBg="rgb(245 158 11 / 0.16)" iconColor="#fbbf24" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <BadgeCheck size={16} style={{ color: A.key }} />
                <h3 className="text-sm font-semibold text-text">全端采集后清洗入库的招聘线索</h3>
              </div>
              <span className="text-xxs text-muted">{num(total)} 条清洗后线索 · 每页 {PAGE_SIZE}</span>
            </div>
            <div className="p-2">
              <AsyncState
                loading={feed.isLoading}
                error={feed.error}
                isEmpty={!feed.isLoading && items.length === 0}
                emptyMessage="还没有招聘网站采集后的清洗数据"
                height={300}
              >
                <DataTable columns={columns} data={items} rowKey={(row) => `${row.kind}-${row.id}`} emptyText="还没有采集记录" />
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
