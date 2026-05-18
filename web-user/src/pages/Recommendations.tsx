import { useState } from 'react';
import { Sparkles, Search, ExternalLink, Mail, Star, UserPlus, UserMinus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { AsyncState } from '@/components/states/States';
import { OutreachDrawer } from '@/components/outreach/OutreachDrawer';
import { useRecommended, useClaimCreator, useReleaseCreator } from '@/hooks/useApi';
import { formatCompact, shortRelative, maskEmail } from '@/lib/format';
import { pickItems } from '@/api/types';
import type { Creator } from '@/api/types';
import { useQueryClient } from '@tanstack/react-query';

export default function Recommendations() {
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('');
  const [drawerCreator, setDrawerCreator] = useState<Creator | null>(null);

  const params: Record<string, unknown> = { limit: 500 };
  if (q) params.q = q;
  if (tier) params.tier = tier;

  const { data, isLoading, error } = useRecommended(params);
  const items = pickItems<Creator>(data as any);
  const qc = useQueryClient();
  const claim = useClaimCreator();
  const release = useReleaseCreator();

  const onClaim = (c: Creator) => {
    claim.mutate({ id: c.id, body: {} }, { onSuccess: () => qc.invalidateQueries({ queryKey: ['creators'] }) });
  };
  const onRelease = (c: Creator) => {
    release.mutate({ id: c.id }, { onSuccess: () => qc.invalidateQueries({ queryKey: ['creators'] }) });
  };

  const highScore = items.filter((c) => (c.recommendation_score ?? 0) >= 80).length;
  const withEmail = items.filter((c) => c.email).length;
  const total = (data as any)?.total ?? items.length;

  const columns: Column<Creator>[] = [
    {
      key: 'score', header: '评分', align: 'center', width: '70px',
      cell: (r) => {
        const score = r.recommendation_score;
        if (score === null || score === undefined) return <span className="text-xxs text-muted">—</span>;
        const tone = score >= 80 ? 'text-good' : score >= 60 ? 'text-warn' : 'text-muted';
        return (
          <div className="flex items-center gap-1 justify-center">
            <Star size={11} className={tone} />
            <span className={`text-xs num font-bold ${tone}`}>{Math.round(score)}</span>
          </div>
        );
      },
    },
    {
      key: 'creator', header: '达人',
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-medium shrink-0"
               style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' }}>
            {(r.handle || r.display_name || '?')[0]?.toUpperCase()}
          </div>
          <div className="min-w-0">
            <a href={r.profile_url || '#'} target="_blank" rel="noreferrer" className="text-xs font-medium hover:underline truncate block">
              @{r.handle}
            </a>
            {r.display_name && <div className="text-xxs text-muted truncate">{r.display_name}</div>}
          </div>
        </div>
      ),
      width: '200px',
    },
    { key: 'tier', header: 'Tier', cell: (r) => r.tier ? <span className="pill pill-info">{r.tier}</span> : <span className="text-xxs text-muted">—</span> },
    { key: 'followers', header: '粉丝', align: 'right', cell: (r) => <span className="text-xs num">{r.followers ? formatCompact(r.followers) : '—'}</span> },
    { key: 'country', header: '国家', cell: (r) => <span className="text-xs">{r.country || '—'}</span> },
    {
      key: 'tags', header: '标签',
      cell: (r) => (
        <div className="flex flex-wrap gap-1">
          {(r.category_tags || []).slice(0, 2).map((t) => (
            <span key={t} className="pill pill-muted text-xxs">{t}</span>
          ))}
          {(!r.category_tags || r.category_tags.length === 0) && <span className="text-xxs text-muted">—</span>}
        </div>
      ),
    },
    { key: 'email', header: '邮箱', cell: (r) => r.email ? <span className="text-xs text-muted">{maskEmail(r.email)}</span> : <span className="text-xxs text-muted">—</span> },
    { key: 'reason', header: '推荐理由', cell: (r) => <span className="text-xs text-muted truncate max-w-[260px] block">{r.recommendation_reason || '—'}</span> },
    { key: 'updated', header: '更新', cell: (r) => <span className="text-xs text-muted">{shortRelative(r.updated_at)}</span> },
    {
      key: 'actions', header: '', align: 'right',
      cell: (r) => (
        <div className="flex items-center justify-end gap-1.5">
          <a href={r.profile_url || '#'} target="_blank" rel="noreferrer" className="chip text-xxs"><ExternalLink size={10} />打开</a>
          {r.email && <button className="chip text-xxs"><Mail size={10} />外联</button>}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="推荐池" value={formatCompact(total)} icon={Sparkles} iconBg="rgb(6 182 212 / 0.18)" iconColor="#22d3ee" />
        <KpiCard label="高分推荐 (≥80)" value={highScore} icon={Star} iconBg="rgb(245 158 11 / 0.18)" iconColor="#fbbf24" />
        <KpiCard label="已带邮箱" value={withEmail} icon={Mail} iconBg="rgb(34 197 94 / 0.18)" iconColor="#4ade80" />
        <KpiCard label="可联系率" value={items.length > 0 ? `${Math.round((withEmail / items.length) * 100)}%` : '—'} icon={ExternalLink} iconBg="rgb(139 92 246 / 0.18)" iconColor="#a78bfa" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap border-b border-border">
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 w-72 rounded border border-border" style={{ background: 'rgb(var(--bg-elev-2))' }}>
            <Search size={14} className="text-muted shrink-0" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索 handle / 备注" className="input-bare flex-1" />
          </div>
          <select value={tier} onChange={(e) => setTier(e.target.value)} className="text-xs border border-border rounded px-2 py-1.5"
                  style={{ background: 'rgb(var(--bg-elev-1))', color: 'rgb(var(--text))' }}>
            <option value="">全部 Tier</option>
            <option value="S">S</option><option value="A">A</option><option value="B">B</option>
            <option value="C">C</option><option value="D">D</option>
          </select>
          <div className="ml-auto flex items-center gap-2">
            <a href="/api/local/export/recommended-creators.csv" className="btn text-xs">导出 CSV</a>
            <button className="btn btn-primary text-xs">批量外联</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} height={300}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
        </AsyncState>
      </div>
    </div>
  );
}
