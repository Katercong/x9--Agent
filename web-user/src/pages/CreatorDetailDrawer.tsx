import { useEffect, useMemo } from 'react';
import { X, ExternalLink, Layers, ScanLine, Users, Tag, Link2 } from 'lucide-react';
import { shortRelative } from '@/lib/format';
import type { ObservationItem } from '@/api/collector';

// Skill-designed creator detail: a dark right slide-over that reconstructs a
// creator's full picture from every observation collected for that handle
// (list + detail merged), with a TikTok-Shop signature accent.
const ACCENT = '#FE2C55';
const CYAN = '#25F4EE';

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-lg px-3 py-2.5" style={{ background: 'rgb(var(--bg-elev-2))' }}>
      <div className="text-xxs text-muted">{label}</div>
      <div className={`num mt-0.5 ${strong ? 'text-lg font-bold' : 'text-sm font-medium'} text-text`}>{value}</div>
    </div>
  );
}

export function CreatorDetailDrawer({
  handle,
  rows,
  onClose,
}: {
  handle: string | null;
  rows: ObservationItem[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    if (handle) {
      window.addEventListener('keydown', onKey);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [handle, onClose]);

  const view = useMemo(() => {
    const sorted = [...rows].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    const latest = sorted[0];
    // Prefer the detail observation's shop block; fall back to list.
    const detailRow = sorted.find((r) => r.shop?.lead_status === 'shop_profile_collected');
    const listRow = sorted.find((r) => r.shop?.lead_status === 'shop_list_seen');
    const shop = detailRow?.shop || listRow?.shop || latest?.shop;
    return { sorted, latest, detailRow, listRow, shop };
  }, [rows]);

  if (!handle) return null;
  const { sorted, latest, detailRow, listRow, shop } = view;
  const displayName = latest?.display_name || handle;

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <aside
        className="absolute right-0 top-0 h-full w-full max-w-[540px] flex flex-col shadow-2xl"
        style={{ background: 'rgb(var(--bg-elev-1))', animation: 'crReveal .28s cubic-bezier(.22,1,.36,1)' }}
      >
        <div className="h-1 w-full shrink-0" style={{ background: `linear-gradient(90deg, ${ACCENT}, ${CYAN})` }} />

        {/* Header */}
        <div className="flex items-start gap-3 px-5 pt-4 pb-4 border-b border-border shrink-0">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center text-white text-xl font-bold shrink-0 overflow-hidden"
            style={{ background: `linear-gradient(135deg, ${ACCENT}, #b3123d)` }}
          >
            {latest?.followers_raw && (latest as any).avatar_url ? null : (handle[0] || '?').toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-lg font-bold text-text leading-tight truncate">@{handle}</div>
            <div className="text-xs text-muted truncate">{displayName}</div>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className="pill" style={{ background: 'rgba(254,44,85,0.16)', color: ACCENT }}>TikTok Shop</span>
              {shop?.category_text && (
                <span className="pill" style={{ background: 'rgba(255,255,255,0.08)', color: 'rgb(var(--text))' }}>
                  {shop.category_text}
                </span>
              )}
              {detailRow ? (
                <span className="pill" style={{ background: 'rgba(16,185,129,0.16)', color: '#34d399' }}>详情已采</span>
              ) : (
                <span className="pill" style={{ background: 'rgba(255,255,255,0.08)', color: 'rgb(var(--muted))' }}>仅列表</span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text shrink-0" aria-label="关闭">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Shop metrics */}
          <section>
            <div className="flex items-center gap-2 mb-2.5">
              <Tag size={14} style={{ color: ACCENT }} />
              <h4 className="text-xs font-semibold text-text">Shop 指标</h4>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Stat label="粉丝" value={latest?.followers_raw || '—'} strong />
              <Stat label="GMV" value={shop?.gmv_raw || '—'} strong />
              <Stat label="GPM" value={shop?.gpm_raw || '—'} />
              <Stat label="佣金率" value={shop?.avg_commission_rate_raw || '—'} />
              <Stat label="邀约" value={shop?.invite_status || '—'} />
              <Stat label="收藏" value={shop?.save_status || '—'} />
            </div>
          </section>

          {/* Capture funnel */}
          <section>
            <div className="flex items-center gap-2 mb-2.5">
              <ScanLine size={14} style={{ color: CYAN }} />
              <h4 className="text-xs font-semibold text-text">采集进度</h4>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-3 rounded-lg px-3 py-2.5" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                <Layers size={15} className="text-muted shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-text">列表阶段</div>
                  <div className="text-xxs text-muted">
                    {listRow ? shortRelative(listRow.created_at || listRow.collected_at || '') : '未采集'}
                  </div>
                </div>
                <span className="pill" style={{ background: listRow ? 'rgba(16,185,129,0.16)' : 'rgba(255,255,255,0.06)', color: listRow ? '#34d399' : 'rgb(var(--muted))' }}>
                  {listRow ? '已采' : '—'}
                </span>
              </div>
              <div className="flex items-center gap-3 rounded-lg px-3 py-2.5" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                <ScanLine size={15} className="text-muted shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-text">详情阶段</div>
                  <div className="text-xxs text-muted">
                    {detailRow ? shortRelative(detailRow.created_at || detailRow.collected_at || '') : '未采集'}
                  </div>
                </div>
                <span className="pill" style={{ background: detailRow ? 'rgba(16,185,129,0.16)' : 'rgba(255,255,255,0.06)', color: detailRow ? '#34d399' : 'rgb(var(--muted))' }}>
                  {detailRow ? '已采' : '—'}
                </span>
              </div>
            </div>
          </section>

          {/* Links */}
          <section>
            <div className="flex items-center gap-2 mb-2.5">
              <Link2 size={14} style={{ color: ACCENT }} />
              <h4 className="text-xs font-semibold text-text">链接</h4>
            </div>
            <div className="space-y-1.5">
              <a
                className="flex items-center gap-2 text-xs text-accent hover:underline"
                href={`https://www.tiktok.com/@${handle}`}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={13} /> TikTok 主页
              </a>
              {shop?.shop_profile_url && (
                <a
                  className="flex items-center gap-2 text-xs text-accent hover:underline break-all"
                  href={shop.shop_profile_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={13} className="shrink-0" /> Shop 达人详情页
                </a>
              )}
            </div>
          </section>

          {/* Observation timeline */}
          <section>
            <div className="flex items-center gap-2 mb-2.5">
              <Users size={14} style={{ color: CYAN }} />
              <h4 className="text-xs font-semibold text-text">采集记录 · {sorted.length} 条</h4>
            </div>
            <div className="space-y-1.5">
              {sorted.map((r) => (
                <div key={r.id} className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                  <span className="text-xxs text-text">
                    {r.shop?.lead_status === 'shop_profile_collected' ? '详情采集' : r.shop?.lead_status === 'shop_list_seen' ? '列表发现' : (r.source || '观测')}
                  </span>
                  <span className="text-xxs text-muted">{shortRelative(r.created_at || r.collected_at || '') || '—'}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}
