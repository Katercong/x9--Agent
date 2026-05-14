import { Mail, Send, Eye, Reply, Sparkles, Plus } from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { emailTemplates, emailQueue } from '@/mock/department';
import { formatPercent, formatDate } from '@/lib/format';

type Template = typeof emailTemplates[number];
type EmailItem = typeof emailQueue[number];

const templateColumns: Column<Template>[] = [
  { key: 'name', header: '模板名称', cell: (r) => <span className="text-xs font-medium">{r.name}</span>, width: '220px' },
  { key: 'use', header: '使用次数', align: 'right', cell: (r) => <span className="text-xs num">{r.useCount}</span> },
  {
    key: 'open', header: '打开率', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full rounded-full bg-brand-500" style={{ width: `${r.openRate * 100}%` }} />
        </div>
        <span className="text-xs num">{formatPercent(r.openRate * 100, 0)}</span>
      </div>
    ),
  },
  {
    key: 'reply', header: '回复率', align: 'right',
    cell: (r) => (
      <div className="flex items-center justify-end gap-2">
        <div className="w-16 h-1 rounded-full bg-soft overflow-hidden">
          <div className="h-full rounded-full bg-good" style={{ width: `${r.replyRate * 100}%` }} />
        </div>
        <span className="text-xs num">{formatPercent(r.replyRate * 100, 0)}</span>
      </div>
    ),
  },
  { key: 'action', header: '', cell: () => <button className="chip text-xxs">使用</button> },
];

const queueColumns: Column<EmailItem>[] = [
  { key: 'to', header: '收件人', cell: (r) => <span className="text-xs">{r.to}</span> },
  { key: 'template', header: '模板', cell: (r) => <span className="text-xs text-muted">{r.template}</span> },
  { key: 'sku', header: 'SKU', cell: (r) => <span className="text-xs font-mono">{r.sku}</span> },
  {
    key: 'status', header: '状态',
    cell: (r) => {
      const toneMap: Record<string, 'good' | 'warn' | 'info' | 'muted'> = {
        '草稿': 'muted', '已发送': 'info', '已读': 'warn', '已回复': 'good', '待回复': 'warn',
      };
      return <Pill tone={toneMap[r.status] || 'muted'}>{r.status}</Pill>;
    },
  },
  { key: 'sentAt', header: '发送时间', cell: (r) => <span className="text-xs text-muted">{r.sentAt ? formatDate(r.sentAt) : '—'}</span> },
  { key: 'opened', header: '已打开', align: 'center', cell: (r) => r.opened ? <Eye size={14} className="inline text-good" /> : <span className="text-muted text-xxs">—</span> },
  { key: 'replied', header: '已回复', align: 'center', cell: (r) => r.replied ? <Reply size={14} className="inline text-good" /> : <span className="text-muted text-xxs">—</span> },
];

export default function Emails() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="今日发送" value={3} delta={50} icon={Send} iconBg="#dbeafe" iconColor="#2563eb" />
        <KpiCard label="打开率" value="48%" delta={3} icon={Eye} iconBg="#fef3c7" iconColor="#ca8a04" />
        <KpiCard label="回复率" value="18%" delta={6} icon={Reply} iconBg="#d1fae5" iconColor="#16a34a" />
        <KpiCard label="待回复" value={emailQueue.filter((e) => e.status === '待回复').length} delta={0} icon={Mail} iconBg="#fed7aa" iconColor="#ea580c" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        <div className="card lg:col-span-2">
          <div className="px-4 py-3 flex items-center justify-between border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">话术模板</h3>
            <button className="chip text-xxs"><Sparkles size={11} />AI 生成</button>
          </div>
          <DataTable columns={templateColumns} data={emailTemplates} compact />
        </div>
        <div className="card lg:col-span-3">
          <div className="px-4 py-3 flex items-center justify-between border-b border-line">
            <h3 className="text-sm font-semibold text-gray-800">发送队列</h3>
            <button className="btn btn-primary text-xxs"><Plus size={11} />新建邮件</button>
          </div>
          <DataTable columns={queueColumns} data={emailQueue} rowKey={(r) => r.id} compact />
        </div>
      </div>
    </div>
  );
}
