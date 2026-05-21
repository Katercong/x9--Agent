import { Video, Eye, Heart, AlertTriangle, ExternalLink } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { AsyncState } from '@/components/states/States';
import { Empty } from '@/components/states/States';
import { useOutreach } from '@/hooks/useApi';
import { formatCompact, formatDate } from '@/lib/format';

export default function Videos() {
  const { data, isLoading, error } = useOutreach({ limit: 500 });
  const all = data?.items ?? [];

  // 有 video_url 的 outreach 事件
  const videos = all.filter((o) => o.video_url);
  const withMetrics = videos.filter((v) => v.video_views !== null && v.video_views > 0);
  const totalViews = withMetrics.reduce((s, v) => s + (v.video_views || 0), 0);
  const totalLikes = withMetrics.reduce((s, v) => s + (v.video_likes || 0), 0);

  // 24h 未更新
  const now = Date.now();
  const stale = videos.filter((v) => {
    if (!v.metrics_updated_at) return true;
    return now - new Date(v.metrics_updated_at).getTime() > 24 * 3600_000;
  }).length;

  const sorted = videos.sort((a, b) => (b.video_views || 0) - (a.video_views || 0));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="在投视频" value={videos.length} icon={Video} iconBg="#ede9fe" iconColor="#7c3aed" />
        <KpiCard label="累计播放" value={formatCompact(totalViews)} icon={Eye} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="累计点赞" value={formatCompact(totalLikes)} icon={Heart} iconBg="#fce7f3" iconColor="#db2777" />
        <KpiCard label="24h 未更新" value={stale} icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center justify-between border-b border-line">
          <div>
            <h3 className="text-sm font-semibold text-gray-800">在投视频墙</h3>
            <div className="text-xxs text-muted mt-0.5">数据源:outreach.video_url</div>
          </div>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>按播放量倒序</option>
            <option>按最近更新</option>
          </select>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={videos.length === 0} height={300}>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 p-4">
            {sorted.slice(0, 40).map((v) => {
              const staleFlag = !v.metrics_updated_at ||
                now - new Date(v.metrics_updated_at).getTime() > 24 * 3600_000;
              return (
                <div key={v.id} className="border border-line rounded-lg overflow-hidden bg-white hover:shadow-soft transition-shadow">
                  <div className="aspect-[3/4] bg-soft relative flex items-center justify-center text-muted">
                    <Video size={40} />
                    {staleFlag && (
                      <span className="absolute top-2 left-2 pill pill-bad text-xxs">
                        <AlertTriangle size={10} className="inline mr-0.5" />超时
                      </span>
                    )}
                    <span className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-xxs text-white">
                      {v.video_views !== null && (
                        <span className="flex items-center gap-0.5 bg-black/40 px-1.5 py-0.5 rounded">
                          <Eye size={10} />{formatCompact(v.video_views)}
                        </span>
                      )}
                      {v.video_likes !== null && (
                        <span className="flex items-center gap-0.5 bg-black/40 px-1.5 py-0.5 rounded">
                          <Heart size={10} />{formatCompact(v.video_likes)}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="p-2.5">
                    <div className="text-xs font-medium truncate">#{v.creator_id}</div>
                    <div className="text-xxs text-muted truncate font-mono">{v.store_name || '—'}</div>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-xxs text-muted">{formatDate(v.event_date || v.created_at)}</span>
                      <a href={v.video_url!} target="_blank" rel="noreferrer" className="text-xxs text-brand-500 hover:underline flex items-center gap-0.5">
                        打开 <ExternalLink size={10} />
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {sorted.length === 0 && <Empty height={200} />}
        </AsyncState>
      </div>
    </div>
  );
}
