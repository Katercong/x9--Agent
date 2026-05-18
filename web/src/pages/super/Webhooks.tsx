import { Plus, Webhook, CheckCircle2, AlertTriangle } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useWebhooks } from '@/hooks/useApi';
import { shortRelative } from '@/lib/format';
import type { Webhook as WebhookT } from '@/api/types';

const columns: Column<WebhookT>[] = [
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
  { key: 'kind', header: '类型', cell: (r) => <Pill tone="info">{r.kind}</Pill> },
  { key: 'url', header: 'URL', cell: (r) => <span className="text-xs font-mono text-muted truncate max-w-[260px] block">{r.url}</span> },
  {
    key: 'secret', header: 'Secret',
    cell: (r) => <Pill tone={r.secret ? 'good' : 'warn'}>{r.secret ? '已配置' : '未配置'}</Pill>,
  },
  { key: 'keyword', header: '关键词', cell: (r) => <span className="text-xs">{r.keyword || '—'}</span> },
  {
    key: 'status', header: '上次发送',
    cell: (r) => (
      <div className="flex items-center gap-2">
        {r.last_status === 'ok' || r.last_status === 'success' ? (
          <CheckCircle2 size={14} className="text-good" />
        ) : r.last_status ? (
          <AlertTriangle size={14} className="text-warn" />
        ) : (
          <span className="text-xxs text-muted">—</span>
        )}
        <span className="text-xs text-muted">{r.last_fired_at ? shortRelative(r.last_fired_at) : '从未'}</span>
      </div>
    ),
  },
  { key: 'active', header: '启用', cell: (r) => <Pill tone={r.active === 1 ? 'good' : 'muted'}>{r.active === 1 ? '是' : '否'}</Pill> },
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
  const { data, isLoading, error } = useWebhooks({ limit: 100 });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const active = items.filter((w) => w.active === 1).length;
  const errors = items.filter((w) => w.last_status && w.last_status !== 'ok' && w.last_status !== 'success').length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: '总订阅数', value: total },
          { label: '启用中', value: active },
          { label: '最近发送异常', value: errors },
          { label: '类型数', value: new Set(items.map((w) => w.kind)).size },
        ].map((k) => (
          <div key={k.label} className="card card-body">
            <div className="text-xs text-muted">{k.label}</div>
            <div className="text-3xl num font-bold mt-1">{k.value}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <Webhook size={16} className="text-muted" />
          <h3 className="text-sm font-semibold text-gray-800">Webhook 列表</h3>
          <span className="text-xxs text-muted">数据源:webhooks(钉钉/HTTP 通用)</span>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新增 Webhook</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} emptyMessage="还没配置 webhook,点击右上「新增 Webhook」创建" height={280}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
        </AsyncState>
      </div>

      <div className="card card-body">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">支持的触发事件</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {['建联完成', '寄样签收', '视频发布', '广告授权', '错误率超阈', '日报', '周报', '自定义'].map((name) => (
            <div key={name} className="border border-line rounded p-3">
              <div className="text-muted text-xxs">{name}</div>
              <div className="text-lg num font-semibold mt-1 text-muted">—</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
