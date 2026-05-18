import { Plus, Database, Table2 } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useResources } from '@/hooks/useApi';
import type { Resource } from '@/api/types';

export default function Resources() {
  const { data, isLoading, error } = useResources();
  const items = data?.items ?? [];

  const columns: Column<Resource>[] = [
    {
      key: 'name', header: '资源名',
      cell: (r) => (
        <div className="flex items-center gap-2">
          <Table2 size={14} className="text-brand-500" />
          <div>
            <div className="text-xs font-mono font-medium">{r.name}</div>
            <div className="text-xxs text-muted">{r.table}</div>
          </div>
        </div>
      ),
    },
    { key: 'pk', header: '主键', cell: (r) => <span className="text-xs font-mono">{r.pk}</span> },
    { key: 'cols', header: '字段', align: 'right', cell: (r) => <span className="text-xs num">{r.columns?.length || 0}</span> },
    { key: 'dyn', header: '动态', cell: (r) => <Pill tone={r.is_dynamic ? 'info' : 'muted'}>{r.is_dynamic ? '是' : '否'}</Pill> },
    { key: 'writable', header: '可写', cell: (r) => <Pill tone={r.writable ? 'good' : 'muted'}>{r.writable ? '是' : '只读'}</Pill> },
    { key: 'desc', header: '说明', cell: (r) => <span className="text-xs text-muted truncate max-w-md block">{r.description || '—'}</span> },
    {
      key: 'action', header: '', align: 'right',
      cell: () => (
        <div className="flex items-center justify-end gap-1.5">
          <button className="chip text-xxs">浏览</button>
          <button className="chip text-xxs">Schema</button>
          <button className="chip text-xxs">+ 字段</button>
        </div>
      ),
    },
  ];

  const dynamicCount = items.filter((r) => r.is_dynamic).length;
  const writableCount = items.filter((r) => r.writable).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card card-body">
          <div className="text-xs text-muted">资源数</div>
          <div className="text-3xl num font-bold mt-1">{items.length}</div>
          <div className="text-xxs text-muted mt-1">SQLite 表</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">动态资源</div>
          <div className="text-3xl num font-bold mt-1">{dynamicCount}</div>
          <div className="text-xxs text-muted mt-1">通过 /tables 接口创建</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">可写表</div>
          <div className="text-3xl num font-bold mt-1">{writableCount}</div>
          <div className="text-xxs text-muted mt-1">/ {items.length}</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">数据库</div>
          <div className="text-3xl num font-bold mt-1">SQLite</div>
          <div className="text-xxs text-muted mt-1">core/database.db</div>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <Database size={16} className="text-muted" />
          <h3 className="text-sm font-semibold text-gray-800">数据库资源</h3>
          <div className="ml-auto flex items-center gap-2">
            <button className="btn">下载 Schema</button>
            <button className="btn btn-primary"><Plus size={12} />新建表</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} height={300}>
          <DataTable columns={columns} data={items} rowKey={(r) => r.name} />
        </AsyncState>
      </div>
    </div>
  );
}
