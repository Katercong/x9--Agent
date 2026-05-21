import { Plus, Play, FileCode } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useNamedQueries } from '@/hooks/useApi';
import type { NamedQuery } from '@/api/types';

export default function Queries() {
  const { data, isLoading, error } = useNamedQueries();
  const items = data?.items ?? [];

  const columns: Column<NamedQuery>[] = [
    {
      key: 'name', header: '查询名',
      cell: (r) => (
        <div className="flex items-center gap-2">
          <FileCode size={14} className="text-brand-500" />
          <span className="text-xs font-mono font-medium">{r.name}</span>
        </div>
      ),
    },
    { key: 'desc', header: '说明', cell: (r) => <span className="text-xs">{r.description}</span> },
    {
      key: 'params', header: '参数',
      cell: (r) => (
        <div className="flex flex-wrap gap-1">
          {(r.params || []).map((p) => (
            <span key={p.name} className="pill pill-muted text-xxs font-mono">{p.name}: {p.type}</span>
          ))}
          {(!r.params || r.params.length === 0) && <span className="text-xxs text-muted">—</span>}
        </div>
      ),
    },
    { key: 'builtin', header: '内置', cell: (r) => <Pill tone={r.is_builtin ? 'info' : 'good'}>{r.is_builtin ? '内置' : '自定义'}</Pill> },
    { key: 'url', header: 'URL', cell: (r) => <code className="text-xxs font-mono text-muted truncate max-w-md block">{r.url}</code> },
    {
      key: 'action', header: '', align: 'right',
      cell: () => (
        <div className="flex items-center justify-end gap-1.5">
          <button className="chip text-xxs"><Play size={10} />运行</button>
        </div>
      ),
    },
  ];

  const builtin = items.filter((q) => q.is_builtin).length;
  const custom = items.length - builtin;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card card-body">
          <div className="text-xs text-muted">命名查询数</div>
          <div className="text-3xl num font-bold mt-1">{items.length}</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">内置查询</div>
          <div className="text-3xl num font-bold mt-1">{builtin}</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">自定义查询</div>
          <div className="text-3xl num font-bold mt-1">{custom}</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">参数化</div>
          <div className="text-3xl num font-bold mt-1">{items.filter((q) => q.params && q.params.length > 0).length}</div>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">命名查询列表</h3>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新建查询</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} height={300}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.name} />
        </AsyncState>
      </div>
    </div>
  );
}
