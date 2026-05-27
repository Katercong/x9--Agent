import { useMemo, useState } from 'react';
import { FileSpreadsheet, Upload, CalendarDays, Globe, Gauge, Download, CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { KpiCard } from '@/components/kpi/KpiCard';
import { ChartCard } from '@/components/charts/ChartCard';
import { EChart } from '@/components/charts/EChart';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState } from '@/components/states/States';
import { useSourceStats, useObservationsFeed, type ObservationItem } from '@/api/collector';
import { ACCENTS, CHART_AXIS, CHART_GRID, CHART_TEXT, CollectHeader, Reveal, dailyAreaOption, num } from './collectShared';

const A = ACCENTS.import;
const PAGE_SIZE = 10;

type ImportResult = {
  ok: boolean;
  filename: string;
  dry_run: boolean;
  total_rows: number;
  upserted: number;
  updated: number;
  inserted: number;
  skipped: number;
  failed: number;
  errors?: { row?: number; handle?: string; detail?: string }[];
};

async function uploadCreatorTable(file: File, dryRun: boolean): Promise<ImportResult> {
  const url = `/api/local/import/creators/table?dry_run=${dryRun ? 'true' : 'false'}&filename=${encodeURIComponent(file.name)}`;
  const res = await fetch(url, {
    method: 'POST',
    body: file,
    credentials: 'include',
  });
  let payload: any = null;
  try { payload = await res.json(); } catch { /* ignore */ }
  if (res.status === 401) {
    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
  }
  if (!res.ok) {
    throw new Error(String(payload?.detail || res.statusText || `HTTP ${res.status}`));
  }
  return payload as ImportResult;
}

function tally(items: ObservationItem[], pick: (i: ObservationItem) => string | null | undefined) {
  const m = new Map<string, number>();
  for (const it of items) {
    const v = pick(it);
    if (v) m.set(v, (m.get(v) ?? 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

export default function CollectImport() {
  const stats = useSourceStats();
  const [page, setPage] = useState(0);
  const feed = useObservationsFeed({ source: 'table_import', limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<'check' | 'import' | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState('');

  const bucket = stats.data?.sources?.table_import;
  const items = feed.data?.items ?? [];

  const d = useMemo(() => {
    const countries = tally(items, (i) => i.import_meta?.country);
    const tiers = tally(items, (i) => i.import_meta?.tier);
    const qs = items.map((i) => i.import_meta?.quality_score).filter((x): x is number => typeof x === 'number');
    const avgQuality = qs.length ? qs.reduce((a, b) => a + b, 0) / qs.length : null;
    return { countries, tiers, avgQuality, countryCount: countries.length };
  }, [items]);

  const tierOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: CHART_AXIS } },
    series: [
      {
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        label: { show: false },
        data: d.tiers.map(([name, value], idx) => ({
          name,
          value,
          itemStyle: { color: ['#f59e0b', '#fbbf24', '#fcd34d', '#d97706', '#92400e'][idx % 5] },
        })),
      },
    ],
  };

  const countryOption = {
    grid: { top: 10, right: 24, bottom: 20, left: 70, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: CHART_GRID } }, axisLabel: { fontSize: 11, color: CHART_AXIS } },
    yAxis: {
      type: 'category',
      data: d.countries.slice(0, 8).map((c) => c[0]).reverse(),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { fontSize: 11, color: CHART_TEXT, fontWeight: 600 },
    },
    series: [
      {
        type: 'bar',
        data: d.countries.slice(0, 8).map((c) => c[1]).reverse(),
        barWidth: 14,
        itemStyle: { color: A.key, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: CHART_TEXT, fontWeight: 600 },
      },
    ],
  };

  const columns: Column<ObservationItem>[] = [
    {
      key: 'creator',
      header: '达人',
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0" style={{ background: A.key }}>
            {(r.handle[0] || '?').toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium text-text truncate">@{r.handle}</div>
            <div className="text-xxs text-muted truncate">{r.display_name || '—'}</div>
          </div>
        </div>
      ),
      width: '210px',
    },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num text-text">{r.followers_raw || '—'}</span> },
    { key: 'country', header: '国家', cell: (r) => <span className="text-xs text-text">{r.import_meta?.country || '—'}</span> },
    { key: 'tier', header: 'Tier', cell: (r) => (r.import_meta?.tier ? <Pill tone="warn">{r.import_meta.tier}</Pill> : <span className="text-xxs text-muted">—</span>) },
    { key: 'lang', header: '语言', cell: (r) => <span className="text-xs text-text">{r.import_meta?.language || '—'}</span> },
    {
      key: 'eng',
      header: '互动率',
      align: 'right',
      cell: (r) => <span className="text-xs num text-text">{typeof r.import_meta?.engagement_rate === 'number' ? r.import_meta.engagement_rate + '%' : '—'}</span>,
    },
    {
      key: 'q',
      header: '质量分',
      align: 'right',
      cell: (r) => <span className="text-xs num text-text">{typeof r.import_meta?.quality_score === 'number' ? r.import_meta.quality_score : '—'}</span>,
    },
  ];

  async function runImport(dryRun: boolean) {
    if (!file || busy) return;
    setBusy(dryRun ? 'check' : 'import');
    setImportError('');
    try {
      const next = await uploadCreatorTable(file, dryRun);
      setResult(next);
      if (!dryRun) {
        qc.invalidateQueries({ queryKey: ['collector', 'source-stats'] });
        qc.invalidateQueries({ queryKey: ['collector', 'feed'] });
        qc.invalidateQueries({ queryKey: ['biz', 'dashboard'] });
        qc.invalidateQueries({ queryKey: ['creators'] });
      }
    } catch (err: any) {
      setImportError(err?.message || '导入失败');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <CollectHeader accent={A} icon={FileSpreadsheet} title="采集 · 表格导入" subtitle="CSV / XLSX 批量导入达人 · 中英文表头自动映射" />

      <section className="card card-body">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text">表格导入</h3>
            <div className="text-xs text-muted mt-1 truncate">{file ? file.name : 'CSV / XLSX'}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <a className="btn btn-ghost" href="/api/local/import/creators/template.xlsx">
              <Download size={14} /> XLSX 模板
            </a>
            <a className="btn btn-ghost" href="/api/local/import/creators/template.csv">
              <Download size={14} /> CSV 模板
            </a>
            <label className="btn btn-ghost cursor-pointer">
              <Upload size={14} /> 选择文件
              <input
                className="hidden"
                type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setResult(null);
                  setImportError('');
                }}
              />
            </label>
            <button className="btn btn-ghost" type="button" disabled={!file || !!busy} onClick={() => runImport(true)}>
              {busy === 'check' ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} 校验导入
            </button>
            <button className="btn btn-primary" type="button" disabled={!file || !!busy} onClick={() => runImport(false)}>
              {busy === 'import' ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} 确认导入
            </button>
          </div>
        </div>

        {(result || importError) && (
          <div className="mt-4 rounded-md border border-border bg-elev2 px-3 py-2">
            {importError ? (
              <div className="flex items-center gap-2 text-xs text-bad">
                <AlertTriangle size={14} /> {importError}
              </div>
            ) : result && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-xs text-text">
                  <CheckCircle2 size={14} className={result.ok ? 'text-good' : 'text-warn'} />
                  <span>{result.dry_run ? '校验完成' : '导入完成'}</span>
                  <span className="text-muted">总行数 {num(result.total_rows)}</span>
                  <span className="text-muted">新增 {num(result.inserted)}</span>
                  <span className="text-muted">更新 {num(result.updated)}</span>
                  <span className="text-muted">失败 {num(result.failed)}</span>
                </div>
                {!!result.errors?.length && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {result.errors.slice(0, 4).map((err, idx) => (
                      <div key={`${err.row}-${idx}`} className="text-xxs text-bad bg-red-500/10 rounded px-2 py-1">
                        第 {err.row ?? '-'} 行 {err.handle ? `@${err.handle} ` : ''}{err.detail || '解析失败'}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      <AsyncState
        loading={stats.isLoading || feed.isLoading}
        error={stats.error || feed.error}
        isEmpty={!feed.isLoading && items.length === 0}
        emptyMessage="还没有表格导入数据"
        height={400}
      >
        <Reveal i={1}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="导入回传" value={num(bucket?.total ?? items.length)} icon={Upload} iconBg={A.dim} iconColor={A.key} />
            <KpiCard label="今日回传" value={num(bucket?.today ?? 0)} icon={CalendarDays} iconBg="rgba(6,182,212,0.14)" iconColor="#06b6d4" />
            <KpiCard label="覆盖国家" value={num(d.countryCount)} icon={Globe} iconBg="rgba(99,102,241,0.16)" iconColor="#818cf8" />
            <KpiCard label="平均质量分" value={d.avgQuality === null ? '—' : d.avgQuality.toFixed(1)} icon={Gauge} iconBg="rgba(245,158,11,0.14)" iconColor="#f59e0b" />
          </div>
        </Reveal>

        <Reveal i={2}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
            <ChartCard title="Tier 分布">
              <EChart option={tierOption} height={260} />
            </ChartCard>
            <ChartCard title="近 7 天导入回传" className="lg:col-span-2">
              <EChart option={dailyAreaOption(bucket?.daily ?? [], A.key)} height={260} />
            </ChartCard>
          </div>
        </Reveal>

        <Reveal i={3}>
          <div className="card mt-4">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text">导入明细 · {num(feed.data?.total ?? items.length)} 条</h3>
              <span className="text-xxs text-muted">实时来自 /observations-feed</span>
            </div>
            <div className="p-2">
              <DataTable columns={columns} data={items} rowKey={(r) => r.id} emptyText="还没有表格导入数据" />
              <PaginationControls
                page={page}
                pageSize={PAGE_SIZE}
                total={feed.data?.total ?? 0}
                currentCount={items.length}
                loading={feed.isFetching}
                onPageChange={setPage}
              />
            </div>
          </div>
        </Reveal>
      </AsyncState>
    </div>
  );
}
