import { useMemo, useState } from 'react';
import {
  BadgeCheck,
  Brain,
  DatabaseZap,
  FileWarning,
  MailCheck,
  RefreshCw,
  Rows3,
  Sparkles,
  Wand2,
  type LucideIcon,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import {
  useForeignTradeCleaningStatus,
  useRunForeignTradeCleaning,
  type CleaningChannel,
  type CleaningRunResult,
} from '@/api/foreignTrade';
import { ACCENTS, num } from './collectShared';

const channelIcons: Record<string, LucideIcon> = {
  company: DatabaseZap,
  talent: BadgeCheck,
  social: Sparkles,
};

function pct(cleaned: number, total: number): number {
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((cleaned / total) * 100)));
}

function time(value?: string): string {
  if (!value) return '-';
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d.toLocaleString() : '-';
}

export default function ForeignTradeCleaning() {
  const statusQ = useForeignTradeCleaningStatus();
  const runCleaning = useRunForeignTradeCleaning();
  const [lastRun, setLastRun] = useState<CleaningRunResult | null>(null);
  const data = lastRun?.status ?? statusQ.data;
  const summary = data?.summary;
  const channels = data?.channels ?? [];
  const running = runCleaning.isPending;

  const kpis = useMemo(() => [
    { label: '待清洗', value: summary?.needs_cleaning ?? 0, icon: FileWarning, bg: '#fef3c7', fg: '#ca8a04' },
    { label: '已就绪', value: summary?.ready_total ?? 0, icon: BadgeCheck, bg: '#dcfce7', fg: '#16a34a' },
    { label: '联系方式', value: summary?.contacts_total ?? 0, icon: MailCheck, bg: '#dbeafe', fg: '#2563eb' },
    { label: 'GPT 判定', value: summary?.judgments_total ?? 0, icon: Brain, bg: '#ede9fe', fg: '#7c3aed' },
    { label: '原始快照', value: summary?.raw_snapshots ?? 0, icon: Rows3, bg: '#cffafe', fg: '#0891b2' },
  ], [summary]);

  const handleRun = async (includeGpt: boolean) => {
    const result = await runCleaning.mutateAsync({ include_gpt: includeGpt });
    setLastRun(result);
  };

  return (
    <AsyncState loading={statusQ.isLoading} error={statusQ.error} height={420}>
      <div className="space-y-4">
        <section className="card overflow-hidden">
          <div className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md"
                style={{ background: ACCENTS.social.dim, color: ACCENTS.social.key }}
              >
                <Wand2 size={22} />
              </div>
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-text">数据清洗</h2>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xxs text-muted">
                  <span>范围: {data?.scope?.department_code || '全部'}</span>
                  <span>刷新: {time(data?.generated_at)}</span>
                  <Pill tone={summary?.openai_configured ? 'good' : 'muted'}>
                    {summary?.openai_configured ? 'GPT 已配置' : 'GPT 未配置'}
                  </Pill>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #2563eb 100%)' }}
                disabled={running}
                onClick={() => void handleRun(false)}
              >
                <RefreshCw size={16} className={running ? 'animate-spin' : ''} />
                重跑清洗
              </button>
              <button
                type="button"
                className="btn inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
                disabled={running || !summary?.openai_configured}
                onClick={() => void handleRun(true)}
              >
                <Brain size={16} />
                清洗 + GPT 判定
              </button>
            </div>
          </div>
          <div className="h-1" style={{ background: ACCENTS.social.key }} />
        </section>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {kpis.map((item) => (
            <KpiCard
              key={item.label}
              label={item.label}
              value={num(item.value)}
              icon={item.icon}
              iconBg={item.bg}
              iconColor={item.fg}
            />
          ))}
        </div>

        <section className="card overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
            <h3 className="text-sm font-semibold text-text">渠道清洗状态</h3>
            <span className="text-xxs text-muted">{num(channels.length)} 个渠道</span>
          </div>
          <div className="divide-y divide-border">
            {channels.map((row) => <ChannelRow key={row.key} row={row} />)}
          </div>
        </section>

        {lastRun && (
          <section className="card overflow-hidden">
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-text">最近一次重跑</h3>
              <Pill tone="good">{lastRun.duration_ms} ms</Pill>
            </div>
            <div className="grid grid-cols-1 gap-3 p-4 lg:grid-cols-4">
              <RunBlock title="公司客户" rows={lastRun.company} />
              <RunBlock title="跨境人才" rows={lastRun.talent} />
              <RunBlock title="社媒线索" rows={lastRun.social} />
              <RunBlock title="GPT 判定" rows={lastRun.gpt} />
            </div>
          </section>
        )}
      </div>
    </AsyncState>
  );
}

function ChannelRow({ row }: { row: CleaningChannel }) {
  const Icon = channelIcons[row.key] ?? DatabaseZap;
  const value = pct(row.cleaned, row.total);
  const tone = row.pending > 0 ? 'warn' : 'good';

  return (
    <div className="grid grid-cols-1 gap-3 px-4 py-3 lg:grid-cols-[260px_1fr_180px] lg:items-center">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/5 text-text">
          <Icon size={17} />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-text">{row.name}</div>
          <div className="text-xxs text-muted">
            {num(row.cleaned)} / {num(row.total)}
          </div>
        </div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/[0.08]">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${value}%`, background: row.pending > 0 ? '#f59e0b' : '#22c55e' }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:justify-end">
        <Pill tone={tone}>{row.pending > 0 ? `待处理 ${num(row.pending)}` : '已就绪'}</Pill>
        {row.with_contact !== undefined && <Pill tone="good">联系方式 {num(row.with_contact)}</Pill>}
        {row.unjudged_with_contact !== undefined && row.unjudged_with_contact > 0 && (
          <Pill tone="warn">待判定 {num(row.unjudged_with_contact)}</Pill>
        )}
      </div>
    </div>
  );
}

function RunBlock({ title, rows }: { title: string; rows: Record<string, unknown> }) {
  return (
    <div className="rounded-md border border-border bg-white/[0.03] p-3">
      <div className="mb-2 text-xs font-semibold text-text">{title}</div>
      <div className="space-y-1">
        {Object.entries(rows).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-3 text-xxs">
            <span className="text-muted">{key}</span>
            <span className="num text-text">{typeof value === 'number' ? num(value) : String(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
