import { Plus, Play, FileCode } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { namedQueries } from '@/mock/super';

type Query = typeof namedQueries[number];

const columns: Column<Query>[] = [
  {
    key: 'name', header: '查询名',
    cell: (r) => (
      <div className="flex items-center gap-2">
        <FileCode size={14} className="text-brand-500" />
        <span className="text-xs font-mono font-medium">{r.name}</span>
      </div>
    ),
  },
  { key: 'desc', header: '说明', cell: (r) => <span className="text-xs">{r.desc}</span> },
  {
    key: 'sql', header: 'SQL 预览',
    cell: (r) => (
      <code className="text-xxs font-mono text-muted truncate max-w-md block">{r.sqlPreview}</code>
    ),
  },
  { key: 'avg', header: '平均耗时', align: 'right', cell: (r) => <span className={`text-xs num ${r.avgMs > 200 ? 'text-warn' : 'text-good'}`}>{r.avgMs} ms</span> },
  { key: 'last', header: '上次运行', cell: (r) => <span className="text-xs text-muted">{r.lastRun}</span> },
  {
    key: 'action', header: '', align: 'right',
    cell: () => (
      <div className="flex items-center justify-end gap-1.5">
        <button className="chip text-xxs"><Play size={10} />运行</button>
        <button className="chip text-xxs">编辑</button>
      </div>
    ),
  },
];

export default function Queries() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card card-body">
          <div className="text-xs text-muted">命名查询数</div>
          <div className="text-3xl num font-bold mt-1">{namedQueries.length}</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">今日运行</div>
          <div className="text-3xl num font-bold mt-1">142</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">平均耗时</div>
          <div className="text-3xl num font-bold mt-1">186ms</div>
        </div>
        <div className="card card-body">
          <div className="text-xs text-muted">慢查询</div>
          <div className="text-3xl num font-bold mt-1 text-warn">2</div>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">命名查询列表</h3>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新建查询</button>
          </div>
        </div>
        <DataTable columns={columns} data={namedQueries} rowKey={(r) => r.name} />
      </div>

      <div className="card card-body">
        <h3 className="text-sm font-semibold text-gray-800 mb-2">SQL 编辑器</h3>
        <div className="bg-[#1e1e2e] rounded p-3 font-mono text-xs text-[#cdd6f4] overflow-x-auto">
          <div><span style={{ color: '#cba6f7' }}>SELECT</span> creator_id,</div>
          <div className="pl-8"><span style={{ color: '#cba6f7' }}>COUNT</span>(*) <span style={{ color: '#cba6f7' }}>AS</span> outreach_count,</div>
          <div className="pl-8"><span style={{ color: '#cba6f7' }}>MAX</span>(event_date) <span style={{ color: '#cba6f7' }}>AS</span> last_event</div>
          <div><span style={{ color: '#cba6f7' }}>FROM</span> outreach</div>
          <div><span style={{ color: '#cba6f7' }}>WHERE</span> status <span style={{ color: '#f38ba8' }}>=</span> <span style={{ color: '#a6e3a1' }}>'video_published'</span></div>
          <div className="pl-2"><span style={{ color: '#cba6f7' }}>AND</span> event_date <span style={{ color: '#f38ba8' }}>&gt;=</span> <span style={{ color: '#a6e3a1' }}>:since</span></div>
          <div><span style={{ color: '#cba6f7' }}>GROUP BY</span> creator_id</div>
          <div><span style={{ color: '#cba6f7' }}>ORDER BY</span> outreach_count <span style={{ color: '#cba6f7' }}>DESC</span></div>
          <div><span style={{ color: '#cba6f7' }}>LIMIT</span> 20;</div>
        </div>
        <div className="flex items-center justify-between mt-3 text-xs">
          <span className="text-muted">参数: <code className="font-mono">:since</code> (date)</span>
          <div className="flex gap-2">
            <button className="btn">校验</button>
            <button className="btn btn-primary"><Play size={11} />运行</button>
          </div>
        </div>
      </div>
    </div>
  );
}
