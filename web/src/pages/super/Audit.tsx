import { useState } from 'react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { auditLogs } from '@/mock/super';
import { ChevronRight, ChevronDown } from 'lucide-react';

type Log = typeof auditLogs[number];

const actionTone: Record<string, 'good' | 'info' | 'bad'> = {
  INSERT: 'good',
  UPDATE: 'info',
  DELETE: 'bad',
};

export default function Audit() {
  const [expanded, setExpanded] = useState<number | null>(null);

  const columns: Column<Log>[] = [
    {
      key: 'expand', header: '', align: 'center',
      cell: (r) => (
        <button onClick={() => setExpanded(expanded === r.id ? null : r.id)} className="text-muted hover:text-gray-700">
          {expanded === r.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      ),
      width: '36px',
    },
    { key: 'ts', header: '时间', cell: (r) => <span className="text-xs text-muted">{r.ts}</span> },
    { key: 'user', header: '操作人', cell: (r) => <span className="text-xs">{r.user}</span> },
    { key: 'dept', header: '部门', cell: (r) => <span className="text-xs">{r.dept}</span> },
    { key: 'table', header: '表', cell: (r) => <span className="text-xs font-mono">{r.table}</span> },
    { key: 'action', header: '操作', cell: (r) => <Pill tone={actionTone[r.action] || 'muted'}>{r.action}</Pill> },
    { key: 'record', header: 'Record ID', cell: (r) => <span className="text-xs num">{r.recordId}</span> },
    { key: 'summary', header: '变更摘要', cell: (r) => <span className="text-xs text-muted">{r.summary}</span> },
  ];

  return (
    <div className="space-y-4">
      <div className="card card-body">
        <div className="flex items-center gap-2 flex-wrap">
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部表</option>
            <option>creator</option>
            <option>product</option>
            <option>outreach</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部操作</option>
            <option>INSERT</option>
            <option>UPDATE</option>
            <option>DELETE</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部操作人</option>
          </select>
          <input type="date" className="text-xs border border-line rounded px-2 py-1.5 bg-white" />
          <span className="text-xs text-muted">至</span>
          <input type="date" className="text-xs border border-line rounded px-2 py-1.5 bg-white" />
          <div className="ml-auto flex items-center gap-2">
            <button className="btn">导出 JSON</button>
            <button className="btn">导出 CSV</button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">操作日志</h3>
          <span className="text-xxs text-muted ml-2">共 {auditLogs.length} 条</span>
        </div>
        <div className="relative">
          <DataTable columns={columns} data={auditLogs} rowKey={(r) => r.id} />
          {expanded !== null && (() => {
            const row = auditLogs.find((r) => r.id === expanded);
            if (!row) return null;
            return (
              <div className="border-t-2 border-brand-500 bg-brand-50/30 px-4 py-3">
                <div className="text-xxs text-muted mb-2">变更详情 · Record #{row.recordId}</div>
                <pre className="text-xxs font-mono bg-white border border-line rounded p-3 overflow-x-auto">{`{
  "before": {
    "${row.summary.includes('tier') ? 'tier' : 'status'}": "B",
    "updated_at": "${row.ts}"
  },
  "after": {
    "${row.summary.includes('tier') ? 'tier' : 'status'}": "A",
    "updated_at": "${row.ts}"
  },
  "changed_by": "${row.user}"
}`}</pre>
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
