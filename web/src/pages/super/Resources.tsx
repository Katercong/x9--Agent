import { Plus, Database, Table2 } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { resources } from '@/mock/super';

type Resource = typeof resources[number];

const columns: Column<Resource>[] = [
  {
    key: 'name', header: '表名',
    cell: (r) => (
      <div className="flex items-center gap-2">
        <Table2 size={14} className="text-brand-500" />
        <span className="text-xs font-mono font-medium">{r.name}</span>
      </div>
    ),
  },
  { key: 'rows', header: '行数', align: 'right', cell: (r) => <span className="text-xs num">{r.rows.toLocaleString()}</span> },
  { key: 'cols', header: '字段', align: 'right', cell: (r) => <span className="text-xs num">{r.cols}</span> },
  { key: 'last', header: '最近写入', cell: (r) => <span className="text-xs text-muted">{r.lastWrite}</span> },
  { key: 'writable', header: '可写', cell: (r) => <Pill tone={r.writable ? 'good' : 'muted'}>{r.writable ? '是' : '只读'}</Pill> },
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

export default function Resources() {
  const totalRows = resources.reduce((s, r) => s + r.rows, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card card-body">
          <div className="text-xs text-muted">资源数</div>
          <div className="text-3xl num font-bold mt-1">{resources.length}</div>
          <div className="text-xxs text-muted mt-1">SQLite 表</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">总行数</div>
          <div className="text-3xl num font-bold mt-1">{(totalRows / 1000).toFixed(1)}K</div>
          <div className="text-xxs text-muted mt-1">{totalRows.toLocaleString()} 行</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">可写表</div>
          <div className="text-3xl num font-bold mt-1">{resources.filter((r) => r.writable).length}</div>
          <div className="text-xxs text-muted mt-1">/ {resources.length}</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">数据库大小</div>
          <div className="text-3xl num font-bold mt-1">12.4 MB</div>
          <div className="text-xxs text-muted mt-1">SQLite WAL 模式</div>
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
        <DataTable columns={columns} data={resources} rowKey={(r) => r.name} />
      </div>

      <div className="card card-body">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">Schema 可视化(creator 表预览)</h3>
        <div className="overflow-x-auto">
          <table className="table-x9">
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>必填</th>
                <th>默认值</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['id', 'INTEGER', '是', '自增', '主键'],
                ['handle', 'TEXT', '是', '—', 'TikTok 唯一标识 @xxx'],
                ['nickname', 'TEXT', '否', '—', '展示名'],
                ['follower_count', 'INTEGER', '否', '0', '粉丝数'],
                ['tier', 'TEXT', '否', 'D', 'S/A/B/C/D 自动分级'],
                ['current_status', 'TEXT', '否', 'prospect', '状态机当前状态'],
                ['country', 'TEXT', '否', '—', '国家代码'],
                ['owner_user_id', 'INTEGER', '否', '—', '对接 BD'],
                ['priority', 'TEXT', '否', 'P3', '优先级 P1-P4'],
                ['engagement_rate', 'REAL', '否', '0', '互动率'],
              ].map(([field, type, req, def, desc]) => (
                <tr key={field}>
                  <td><span className="text-xs font-mono">{field}</span></td>
                  <td><Pill tone="info">{type}</Pill></td>
                  <td><span className="text-xs">{req}</span></td>
                  <td><span className="text-xs font-mono text-muted">{def}</span></td>
                  <td><span className="text-xs text-muted">{desc}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
