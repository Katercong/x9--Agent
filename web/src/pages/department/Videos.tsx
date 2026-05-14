import { Video, Eye, Heart, AlertTriangle, ExternalLink } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { videos } from '@/mock/department';
import { formatCompact, formatDate } from '@/lib/format';

export default function Videos() {
  const stale = videos.filter((v) => v.hoursAgo >= 24).length;
  const totalViews = videos.reduce((s, v) => s + v.views, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="在投视频" value={videos.length} delta={11} icon={Video} iconBg="#ede9fe" iconColor="#7c3aed" />
        <KpiCard label="累计播放" value={formatCompact(totalViews)} delta={28} icon={Eye} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="24h 未更新" value={stale} delta={-12} icon={AlertTriangle} iconBg="#fee2e2" iconColor="#dc2626" />
        <KpiCard label="平均点赞率" value="4.8%" delta={2} icon={Heart} iconBg="#fce7f3" iconColor="#db2777" />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center justify-between border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">在投视频墙</h3>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>按播放量倒序</option>
            <option>按最近更新</option>
            <option>按发布时间</option>
          </select>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 p-4">
          {videos.map((v) => (
            <div key={v.id} className="border border-line rounded-lg overflow-hidden bg-white hover:shadow-soft transition-shadow">
              <div className="aspect-[3/4] bg-soft relative overflow-hidden">
                <img src={v.thumbnail} alt="" className="w-full h-full object-cover" />
                {v.hoursAgo >= 24 && (
                  <span className="absolute top-2 left-2 pill pill-bad text-xxs">
                    <AlertTriangle size={10} className="inline mr-0.5" />超时
                  </span>
                )}
                <span className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-xxs text-white">
                  <span className="flex items-center gap-0.5 bg-black/40 px-1.5 py-0.5 rounded">
                    <Eye size={10} />{formatCompact(v.views)}
                  </span>
                  <span className="flex items-center gap-0.5 bg-black/40 px-1.5 py-0.5 rounded">
                    <Heart size={10} />{formatCompact(v.likes)}
                  </span>
                </span>
              </div>
              <div className="p-2.5">
                <div className="text-xs font-medium truncate">@{v.creator}</div>
                <div className="text-xxs text-muted truncate font-mono">{v.sku}</div>
                <div className="flex items-center justify-between mt-1.5">
                  <span className="text-xxs text-muted">{formatDate(v.publishedAt)}</span>
                  <a href={v.url} target="_blank" rel="noreferrer" className="text-xxs text-brand-500 hover:underline flex items-center gap-0.5">
                    打开 <ExternalLink size={10} />
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
