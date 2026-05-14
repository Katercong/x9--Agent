import { Plus, Webhook, CheckCircle2, AlertTriangle } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { webhooks } from '@/mock/super';

type Hook = typeof webhooks[number];

const columns: Column<Hook>[] = [
  {
    key: 'name', header: '名称',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-md bg-soft flex items-center justify-center">
          <Webhook size={14} className="text-muted" />
        </div>
        <span className="text-xs font-medium">{r.name}</span>
      </div>
    ),
  },
  { key: 'url', header: 'URL', cell: (r) => <span className="text-xs font-mono text-muted truncate">{r.url}</span> },
  { key: 'secret', header: 'Secret', cell: (r) => <Pill tone={r.secret === '已配置' ? 'good' : 'warn'}>{r.secret}</Pill> },
  {
    key: 'triggers', header: '触发规则',
    cell: (r) => (
      <div className="flex flex-wrap gap-1">
        {r.triggers.map((t) => (
          <span key={t} className="pill pill-info text-xxs">{t}</span>
        ))}
      </div>
    ),
  },
  {
    key: 'status', header: '上次发送',
    cell: (r) => (
      <div className="flex items-center gap-2">
        {r.lastStatus === 'ok' ? (
          <CheckCircle2 size={14} className="text-good" />
        ) : (
          <AlertTriangle size={14} className="text-warn" />
        )}
        <span className="text-xs text-muted">{r.lastSent}</span>
      </div>
    ),
  },
  {
    key: 'action', header: '', align: 'right',
    cell: () => (
      <div className="flex items-center justify-end gap-1.5">
        <button className="chip text-xxs">测试</button>
        <button className="chip text-xxs">编辑</button>
        <button className="chip text-xxs text-bad">删除</button>
      </div>
    ),
  },
];

export default function Webhooks() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: '总订阅数', value: webhooks.length, tone: 'info' as const },
          { label: '今日发送', value: 18, tone: 'good' as const },
          { label: '成功率', value: '96.4%', tone: 'good' as const },
          { label: '异常数', value: 1, tone: 'warn' as const },
        ].map((k) => (
          <div key={k.label} className="card card-body">
            <div className="text-xs text-muted">{k.label}</div>
            <div className="text-3xl num font-bold mt-1">{k.value}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">Webhook 列表</h3>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新增 Webhook</button>
          </div>
        </div>
        <DataTable columns={columns} data={webhooks} rowKey={(r) => r.id} />
      </div>

      <div className="card card-body">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">触发事件类型</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {[
            { name: '建联完成', count: 28 },
            { name: '寄样签收', count: 14 },
            { name: '视频发布', count: 9 },
            { name: '广告授权', count: 6 },
            { name: '错误率超阈', count: 2 },
            { name: '日报', count: 1 },
            { name: '周报', count: 1 },
            { name: '自定义', count: 4 },
          ].map((e) => (
            <div key={e.name} className="border border-line rounded p-3">
              <div className="text-muted text-xxs">{e.name}</div>
              <div className="text-lg num font-semibold mt-1">{e.count}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
