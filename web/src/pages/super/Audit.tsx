import { useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useAuditLog } from '@/hooks/useApi';
import type { AuditLog } from '@/api/types';

const actionTone: Record<string, 'good' | 'info' | 'bad'> = {
  INSERT: 'good',
  UPDATE: 'info',
  DELETE: 'bad',
};

export default function Audit() {
  const [expanded, setExpanded] = useState<number | null>(null);
  const { data, isLoading, error } = useAuditLog({ limit: 100, order_by: 'ts:desc' });
  const items = data?.items ?? [];

  const columns: Column<AuditLog>[] = [
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
    { key: 'operator', header: '操作人', cell: (r) => <span className="text-xs">{r.operator || '—'}</span> },
    { key: 'table', header: '表', cell: (r) => <span className="text-xs font-mono">{r.table_name}</span> },
    { key: 'action', header: '操作', cell: (r) => <Pill tone={actionTone[r.action] || 'muted'}>{r.action}</Pill> },
    { key: 'record', header: 'Record ID', cell: (r) => <span className="text-xs num">{r.record_id ?? '—'}</span> },
    { key: 'changes', header: '摘要', cell: (r) => <span className="text-xs text-muted truncate max-w-md block">{r.changes?.slice(0, 80) || '—'}</span> },
  ];

  const expandedRow = items.find((r) => r.id === expanded);

  return (
    <div className="space-y-4">
      <div className="card card-body">
        <div className="flex items-center gap-2 flex-wrap">
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部表</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部操作</option>
            <option>INSERT</option><option>UPDATE</option><option>DELETE</option>
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
          <span className="text-xxs text-muted ml-2">共 {data?.total ?? 0} 条</span>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={items.length === 0} emptyMessage="审计日志为空(触发任何编辑后会自动落数)" height={300}>
          <div>
            <DataTable columns={columns} data={items} rowKey={(r) => r.id} />
            {expandedRow && (
              <div className="border-t-2 border-brand-500 bg-brand-50/30 px-4 py-3">
                <div className="text-xxs text-muted mb-2">变更详情 · Record #{expandedRow.record_id}</div>
                <pre className="text-xxs font-mono bg-white border border-line rounded p-3 overflow-x-auto whitespace-pre-wrap">
                  {expandedRow.changes || '(无 changes 字段)'}
                </pre>
              </div>
            )}
          </div>
        </AsyncState>
      </div>
    </div>
  );
}
