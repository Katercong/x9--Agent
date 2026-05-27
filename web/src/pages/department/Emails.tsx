import { useState } from 'react';
import { Mail, Send, Eye, Reply, Sparkles, Plus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { PaginationControls } from '@/components/PaginationControls';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useResource } from '@/hooks/useApi';
import { formatDate } from '@/lib/format';

// outreach 事件中 channel='email' 的事件
interface OutreachEvent {
  id: number;
  creator_id: number;
  event_date: string | null;
  store_name: string | null;
  bd_owner: string | null;
  action: string | null;
  status: string | null;
  channel: string | null;
  message: string | null;
  remark: string | null;
  created_at: string;
}

interface OutreachExample {
  id: number;
  name: string;
  body_en?: string | null;
  body_zh?: string | null;
  channel?: string | null;
  scenario?: string | null;
  language?: string | null;
}

const queueColumns: Column<OutreachEvent>[] = [
  { key: 'creator', header: '达人 ID', cell: (r) => <span className="text-xs font-mono">#{r.creator_id}</span> },
  { key: 'channel', header: '渠道', cell: (r) => <Pill tone="info">{r.channel || '—'}</Pill> },
  { key: 'action', header: '动作', cell: (r) => <span className="text-xs">{r.action || '—'}</span> },
  {
    key: 'status', header: '状态',
    cell: (r) => <Pill tone="info">{r.status || '—'}</Pill>,
  },
  { key: 'bd', header: 'BD', cell: (r) => <span className="text-xs">{r.bd_owner || '—'}</span> },
  { key: 'date', header: '时间', cell: (r) => <span className="text-xs text-muted">{formatDate(r.event_date || r.created_at)}</span> },
  { key: 'remark', header: '备注', cell: (r) => <span className="text-xs text-muted truncate max-w-[200px] block">{r.remark || '—'}</span> },
];

const tplColumns: Column<OutreachExample>[] = [
  { key: 'name', header: '模板名称', cell: (r) => <span className="text-xs font-medium">{r.name}</span> },
  { key: 'scenario', header: '场景', cell: (r) => <span className="text-xs">{r.scenario || '—'}</span> },
  { key: 'channel', header: '渠道', cell: (r) => <Pill tone="info">{r.channel || '—'}</Pill> },
  { key: 'lang', header: '语言', cell: (r) => <span className="text-xs">{r.language || '—'}</span> },
  { key: 'action', header: '', align: 'right', cell: () => <button className="chip text-xxs">使用</button> },
];

const PAGE_SIZE = 10;

export default function Emails() {
  const [tplPage, setTplPage] = useState(0);
  const [eventPage, setEventPage] = useState(0);
  const examples = useResource<OutreachExample>('outreach_example', { limit: PAGE_SIZE, offset: tplPage * PAGE_SIZE });
  const outreach = useResource<OutreachEvent>('outreach', {
    limit: PAGE_SIZE,
    offset: eventPage * PAGE_SIZE,
    order_by: 'created_at:desc',
    channel__in: 'dm,email',
  });

  const events = outreach.data?.items ?? [];
  const dmEvents = events.filter((e) => e.channel === 'dm' || e.channel === 'email');
  const emailCount = events.filter((e) => e.channel === 'email').length;
  const dmCount = events.filter((e) => e.channel === 'dm').length;
  const tpls = examples.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="DM 触达" value={dmCount} icon={Send} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="邮件触达" value={emailCount} icon={Mail} iconBg="#fed7aa" iconColor="#ea580c" />
        <KpiCard label="话术模板" value={tpls.length} icon={Sparkles} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="近 30 天" value={events.length} icon={Reply} iconBg="#d1fae5" iconColor="#16a34a" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <div className="card lg:col-span-2">
          <div className="px-4 py-3 flex items-center justify-between border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">话术模板</h3>
            <button className="chip text-xxs"><Sparkles size={11} />AI 生成</button>
          </div>
          <AsyncState loading={examples.isLoading} error={examples.error} isEmpty={tpls.length === 0} height={300}>
            <DataTable columns={tplColumns} data={tpls} rowKey={(r) => r.id} compact />
          </AsyncState>
          <PaginationControls
            page={tplPage}
            pageSize={PAGE_SIZE}
            total={examples.data?.total ?? 0}
            currentCount={tpls.length}
            loading={examples.isLoading}
            onPageChange={setTplPage}
          />
        </div>
        <div className="card lg:col-span-3">
          <div className="px-4 py-3 flex items-center justify-between border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">发送队列(近期 DM / 邮件)</h3>
            <button className="btn btn-primary text-xxs"><Plus size={11} />新建</button>
          </div>
          <AsyncState loading={outreach.isLoading} error={outreach.error} isEmpty={dmEvents.length === 0} height={300}>
            <DataTable columns={queueColumns} data={dmEvents} rowKey={(r) => r.id} compact />
          </AsyncState>
          <PaginationControls
            page={eventPage}
            pageSize={PAGE_SIZE}
            total={outreach.data?.total ?? 0}
            currentCount={events.length}
            loading={outreach.isLoading}
            onPageChange={setEventPage}
          />
        </div>
      </div>
    </div>
  );
}
