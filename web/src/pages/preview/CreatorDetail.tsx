// /preview/creators/:platform/:handle — Single creator 360° page.
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Loader2, Mail, Globe, Calendar, Activity, Users, Target, Eye } from 'lucide-react';
import { v2Api, type HealthColor } from '@/api/v2';
import { Pill } from '@/components/Pill';

const fmt = (n: number | null | undefined) => new Intl.NumberFormat('zh-CN').format(Number(n || 0));
const HEALTH_BG: Record<HealthColor, string> = { green: 'bg-emerald-500', yellow: 'bg-amber-500', red: 'bg-rose-500', grey: 'bg-gray-300' };
const HEALTH_LABEL: Record<HealthColor, string> = { green: '健康', yellow: '需关注', red: '紧急', grey: '休眠' };

export default function CreatorDetail() {
  const { platform, handle } = useParams<{ platform: string; handle: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ['v2', 'creator-detail', platform, handle],
    queryFn: () => v2Api.creatorDetail(platform!, handle!),
    enabled: !!platform && !!handle,
  });

  if (isLoading) {
    return <div className="flex items-center gap-2 text-muted text-sm p-4"><Loader2 size={14} className="animate-spin" />加载达人 360°...</div>;
  }
  if (error || !data?.ok) {
    return (
      <div className="card card-body">
        <div className="text-bad text-sm">{(error as Error)?.message || '加载失败'}</div>
        <Link to="/preview/creators" className="btn btn-primary mt-3 inline-flex"><ArrowLeft size={14} />返回达人主表</Link>
      </div>
    );
  }

  const c = data.creator;
  return (
    <div className="space-y-4">
      <PreviewBanner />

      {/* Header */}
      <div className="card card-body">
        <div className="flex items-start gap-4">
          <Link to="/preview/creators" className="chip text-xxs flex-shrink-0"><ArrowLeft size={11} />返回</Link>
          {c.avatar_url ? (
            <img src={c.avatar_url} alt="" className="w-16 h-16 rounded-full object-cover" />
          ) : (
            <div className="w-16 h-16 rounded-full bg-brand-100 text-brand-700 text-2xl font-bold flex items-center justify-center">
              {(c.handle?.[0] || '?').toUpperCase()}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-lg font-bold text-gray-900">@{c.handle}</span>
              <Pill tone="muted">{c.platform}</Pill>
              {c.tier && <Pill tone="info">Tier {c.tier}</Pill>}
              {c.country && <Pill tone="muted">{c.country}</Pill>}
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xxs`}>
                <span className={`w-2 h-2 rounded-full ${HEALTH_BG[data.health.color]}`} />
                {HEALTH_LABEL[data.health.color]} — {data.health.reason}
              </span>
            </div>
            <div className="text-sm text-gray-700 mt-1">{c.display_name || '—'}</div>
            {c.bio && <div className="text-xxs text-muted mt-2 line-clamp-2">{c.bio}</div>}
          </div>
          {c.profile_url && (
            <a href={c.profile_url} target="_blank" rel="noreferrer" className="chip text-xxs">
              <Globe size={11} />原站
            </a>
          )}
        </div>
      </div>

      {/* KPI grid (6) */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <KpiCell icon={Users} label="粉丝" value={fmt(c.followers_count)} color="text-blue-600" />
        <KpiCell icon={Target} label="推荐分" value={String(c.recommendation_score)} color={c.recommendation_score >= 70 ? 'text-emerald-600' : 'text-gray-700'} />
        <KpiCell icon={Activity} label="当前阶段" value={c.stage_label || c.current_status || '—'} color="text-purple-600" small />
        <KpiCell icon={Mail} label="邮件" value={c.email ? '有' : '无'} sub={c.email || ''} color={c.email ? 'text-emerald-600' : 'text-gray-400'} small />
        <KpiCell icon={Eye} label="原始采集" value={fmt(data.observation_count)} sub="raw_observations" color="text-amber-600" />
        <KpiCell icon={Calendar} label="最近联系" value={c.last_contact_date?.slice(0, 10) || '—'} color="text-rose-600" small />
      </div>

      {/* Two-column body */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Profile facts */}
        <div className="card lg:col-span-1">
          <div className="px-4 py-3 border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">基本面</h3>
          </div>
          <div className="p-4 space-y-2 text-xs">
            <FactRow label="平台" value={c.platform} />
            <FactRow label="国家" value={c.country} />
            <FactRow label="语言" value={c.language} />
            <FactRow label="Tier" value={c.tier} />
            <FactRow label="主品类" value={c.primary_product_category} />
            <FactRow label="Fit 等级" value={c.fit_level} />
            <FactRow label="30 天 GMV" value={c.gmv_30d_usd ? `$${fmt(c.gmv_30d_usd)}` : null} />
            <FactRow label="负责 BD" value={c.owner_bd} />
            <FactRow label="所属店铺" value={c.store_assigned} />
            <FactRow label="部门" value={c.department_code} />
            <FactRow label="队列" value={c.queue_type} />
            <FactRow label="数据来源表" value={<code className="text-xxs">{c.source_table}</code>} />
            <FactRow label="首次采集" value={c.collected_at?.slice(0, 19).replace('T', ' ')} />
            <FactRow label="最近见过" value={c.last_seen_at?.slice(0, 19).replace('T', ' ')} />
            <FactRow label="更新于" value={c.updated_at?.slice(0, 19).replace('T', ' ')} />
            {c.notes && (
              <div className="pt-2 border-t border-line">
                <div className="text-xxs text-muted">备注</div>
                <div className="text-xs text-gray-700 mt-1 whitespace-pre-line">{c.notes}</div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Timeline + Emails */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card">
            <div className="px-4 py-3 border-b border-line">
              <h3 className="text-sm font-semibold text-gray-800">事件时间线</h3>
            </div>
            <div className="p-4">
              {data.timeline.length === 0 ? (
                <div className="text-xxs text-muted text-center py-4">暂无事件</div>
              ) : (
                <div className="space-y-2">
                  {data.timeline.slice(0, 20).map((e, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="w-2 h-2 rounded-full bg-brand-400 flex-shrink-0 mt-1.5" />
                      <div className="flex-1 min-w-0">
                        <div className="text-gray-800 truncate">{e.label}</div>
                        <div className="text-xxs text-muted">{e.ts.slice(0, 19).replace('T', ' ')}</div>
                      </div>
                      <Pill tone="muted">{e.kind}</Pill>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="px-4 py-3 border-b border-line flex items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-800">邮件历史</h3>
              <span className="text-xxs text-muted">{data.emails.length} 封</span>
            </div>
            <div className="overflow-x-auto">
              {data.emails.length === 0 ? (
                <div className="text-xxs text-muted text-center py-6">尚无邮件</div>
              ) : (
                <table className="table-x9">
                  <thead>
                    <tr>
                      <th>主题</th>
                      <th>收件人</th>
                      <th>状态</th>
                      <th>回复</th>
                      <th className="!text-right">发送时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.emails.map((e) => (
                      <tr key={e.id}>
                        <td className="text-xs truncate max-w-xs">{e.subject}</td>
                        <td className="text-xxs num">{e.to_email}</td>
                        <td><Pill tone={e.status === 'sent' ? 'good' : e.status === 'failed' ? 'bad' : 'muted'}>{e.status}</Pill></td>
                        <td>{e.has_reply ? <Pill tone="info">已回复(占位)</Pill> : <span className="text-xxs text-muted">—</span>}</td>
                        <td className="text-xxs text-right">{(e.sent_at || e.created_at)?.slice(0, 16).replace('T', ' ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCell({ icon: Icon, label, value, sub, color, small }: any) {
  return (
    <div className="card card-body !p-3">
      <div className="flex items-start gap-2">
        <Icon size={14} className={color} />
        <div className="flex-1 min-w-0">
          <div className="text-xxs text-muted">{label}</div>
          <div className={`${small ? 'text-sm' : 'text-xl'} font-bold ${color} leading-tight num truncate`}>{value}</div>
          {sub && <div className="text-xxs text-muted truncate">{sub}</div>}
        </div>
      </div>
    </div>
  );
}

function FactRow({ label, value }: { label: string; value: any }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-xxs text-muted whitespace-nowrap">{label}</span>
      <span className="text-xs text-gray-800 text-right break-all">{value}</span>
    </div>
  );
}

function PreviewBanner() {
  return (
    <div className="card card-body bg-amber-50 border-amber-200 flex items-center gap-2 text-xs">
      <span className="px-2 py-0.5 rounded bg-amber-200 text-amber-900 font-semibold text-xxs">PREVIEW</span>
      <span className="text-amber-900">v2 看板 · 达人 360° 详情</span>
      <Link to="/preview/pulse" className="ml-auto chip text-xxs">公司脉搏</Link>
      <Link to="/preview/me" className="chip text-xxs">我的工作台</Link>
      <Link to="/preview/creators" className="chip text-xxs">达人主表</Link>
    </div>
  );
}
