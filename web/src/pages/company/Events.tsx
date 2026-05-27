import { useState } from 'react';
import { CheckCircle2, AlertTriangle, Info, AlertOctagon } from 'lucide-react';
import { Pill } from '@/components/Pill';
import { PaginationControls } from '@/components/PaginationControls';
import { AsyncState, Empty } from '@/components/states/States';
import { useOutreach } from '@/hooks/useApi';
import { formatDate } from '@/lib/format';

const levelMeta = {
  good: { icon: CheckCircle2, bg: '#d1fae5', color: '#16a34a' },
  info: { icon: Info, bg: '#dbeafe', color: '#2563eb' },
  warn: { icon: AlertTriangle, bg: '#fef3c7', color: '#ca8a04' },
  bad: { icon: AlertOctagon, bg: '#fee2e2', color: '#dc2626' },
};

function levelOf(status: string | null): 'good' | 'info' | 'warn' | 'bad' {
  if (!status) return 'info';
  if (status === 'ad_running' || status === 'ad_authorized') return 'good';
  if (status === 'dropped') return 'bad';
  if (status === 'video_published') return 'warn';
  return 'info';
}

const PAGE_SIZE = 10;

export default function Events() {
  const [page, setPage] = useState(0);
  const { data, isLoading, error } = useOutreach({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, order_by: 'created_at:desc' });
  const events = (data?.items ?? []).map((o) => ({
    id: o.id,
    date: formatDate(o.event_date || o.created_at),
    type: o.action || o.status || '事件',
    level: levelOf(o.status),
    title: o.message
      ? o.message.slice(0, 60) + (o.message.length > 60 ? '...' : '')
      : `BD ${o.bd_owner || '-'} 对达人 #${o.creator_id} 执行 ${o.action || o.status || '操作'}`,
    dept: o.store_name || '—',
    channel: o.channel || '',
    raw: o,
  }));

  return (
    <AsyncState loading={isLoading} error={error} height={400}>
      <div className="space-y-4">
        <div className="card card-body">
          <div className="flex items-center gap-2 flex-wrap mb-4">
            <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
              <option>全部店铺</option>
            </select>
            <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
              <option>全部动作</option>
            </select>
            <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
              <option>全部严重度</option>
            </select>
            <span className="text-xxs text-muted ml-auto">共 {data?.total ?? 0} 条事件</span>
          </div>

          {events.length === 0 ? (
            <Empty height={200} />
          ) : (
            <div className="relative pl-7 ml-4">
              <div className="absolute left-0 top-2 bottom-2 w-px bg-line" />
              {events.map((e) => {
                const meta = levelMeta[e.level];
                const Icon = meta.icon;
                return (
                  <div key={e.id} className="relative pb-5 last:pb-0">
                    <div
                      className="absolute -left-7 w-5 h-5 rounded-full flex items-center justify-center"
                      style={{ background: meta.bg, color: meta.color }}
                    >
                      <Icon size={11} />
                    </div>
                    <div className="flex items-center gap-3 mb-1.5 flex-wrap">
                      <span className="text-xs font-medium text-gray-800">{e.date}</span>
                      <Pill tone={e.level}>{e.type}</Pill>
                      <span className="text-xxs text-muted">{e.dept}</span>
                      {e.channel && <span className="text-xxs text-muted">· {e.channel}</span>}
                    </div>
                    <div className="text-xs text-gray-700">{e.title}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <PaginationControls
          page={page}
          pageSize={PAGE_SIZE}
          total={data?.total ?? 0}
          currentCount={events.length}
          loading={isLoading}
          onPageChange={setPage}
        />
      </div>
    </AsyncState>
  );
}
