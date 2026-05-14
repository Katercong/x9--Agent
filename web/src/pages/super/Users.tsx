import { Plus, KeyRound, ShieldCheck } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { users, apiKeys } from '@/mock/super';

type User = typeof users[number];
type ApiKey = typeof apiKeys[number];

const userColumns: Column<User>[] = [
  {
    key: 'user', header: '用户',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-medium">
          {r.username[0].toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="text-xs font-medium">{r.username}</div>
          <div className="text-xxs text-muted truncate">{r.display}</div>
        </div>
      </div>
    ),
  },
  {
    key: 'role', header: '角色',
    cell: (r) => {
      const toneMap: Record<string, 'info' | 'warn' | 'good' | 'muted'> = {
        '公司管理员': 'warn',
        '超级管理员': 'info',
        '部门管理员': 'good',
        '普通用户': 'muted',
        '只读': 'muted',
      };
      return <Pill tone={toneMap[r.role] || 'muted'}>{r.role}</Pill>;
    },
  },
  { key: 'dept', header: '部门', cell: (r) => <span className="text-xs">{r.dept}</span> },
  { key: 'last', header: '最近登录', cell: (r) => <span className="text-xs text-muted">{r.lastLogin}</span> },
  { key: 'status', header: '状态', cell: (r) => <Pill tone={r.status === 'active' ? 'good' : 'muted'}>{r.status === 'active' ? '正常' : '已禁用'}</Pill> },
  {
    key: 'action', header: '', align: 'right',
    cell: () => (
      <div className="flex items-center justify-end gap-1.5">
        <button className="chip text-xxs">编辑</button>
        <button className="chip text-xxs">Key</button>
      </div>
    ),
  },
];

const keyColumns: Column<ApiKey>[] = [
  { key: 'user', header: '所属', cell: (r) => <span className="text-xs">{r.user}</span> },
  { key: 'prefix', header: 'Key 前缀', cell: (r) => <span className="text-xs font-mono">{r.prefix}...</span> },
  {
    key: 'scopes', header: '权限',
    cell: (r) => (
      <div className="flex flex-wrap gap-1">
        {r.scopes.map((s) => (
          <span key={s} className="pill pill-muted text-xxs font-mono">{s}</span>
        ))}
      </div>
    ),
  },
  { key: 'created', header: '创建', cell: (r) => <span className="text-xs text-muted">{r.created}</span> },
  { key: 'last', header: '最近使用', cell: (r) => <span className="text-xs text-good">{r.lastUsed}</span> },
  {
    key: 'action', header: '', align: 'right',
    cell: () => (
      <div className="flex items-center justify-end gap-1.5">
        <button className="chip text-xxs">改 scope</button>
        <button className="chip text-xxs text-bad">撤销</button>
      </div>
    ),
  },
];

const permMatrix = [
  { module: '产品库', su: '读写', co: '只读', dp: '读写', usr: '只读', ro: '只读' },
  { module: '达人库', su: '读写', co: '只读', dp: '读写', usr: '读写', ro: '只读' },
  { module: '建联流水', su: '读写', co: '只读', dp: '读写', usr: '读写', ro: '只读' },
  { module: 'BI 看板', su: '读写', co: '读写', dp: '只读', usr: '只读', ro: '只读' },
  { module: 'LLM 配置', su: '读写', co: '禁止', dp: '禁止', usr: '禁止', ro: '禁止' },
  { module: '用户管理', su: '读写', co: '只读', dp: '禁止', usr: '禁止', ro: '禁止' },
  { module: '审计日志', su: '读写', co: '只读', dp: '只读', usr: '禁止', ro: '禁止' },
  { module: '系统监控', su: '读写', co: '只读', dp: '禁止', usr: '禁止', ro: '禁止' },
];

const cellTone = (v: string) => {
  if (v === '读写') return 'good';
  if (v === '只读') return 'info';
  if (v === '禁止') return 'bad';
  return 'muted';
};

export default function Users() {
  return (
    <div className="space-y-4">
      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <ShieldCheck size={16} className="text-muted" />
          <h3 className="text-sm font-semibold text-gray-800">全公司用户</h3>
          <span className="text-xxs text-muted">{users.length} 人</span>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新增用户</button>
          </div>
        </div>
        <DataTable columns={userColumns} data={users} rowKey={(r) => r.id} />
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <KeyRound size={16} className="text-muted" />
          <h3 className="text-sm font-semibold text-gray-800">API Key 管理</h3>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />签发 Key</button>
          </div>
        </div>
        <DataTable columns={keyColumns} data={apiKeys} rowKey={(r) => r.id} />
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">角色权限矩阵</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="table-x9">
            <thead>
              <tr>
                <th>模块</th>
                <th className="!text-center">超级管理员</th>
                <th className="!text-center">公司管理员</th>
                <th className="!text-center">部门管理员</th>
                <th className="!text-center">普通用户</th>
                <th className="!text-center">只读</th>
              </tr>
            </thead>
            <tbody>
              {permMatrix.map((r) => (
                <tr key={r.module}>
                  <td className="text-xs font-medium">{r.module}</td>
                  {(['su', 'co', 'dp', 'usr', 'ro'] as const).map((k) => (
                    <td key={k} className="text-center">
                      <Pill tone={cellTone(r[k])}>{r[k]}</Pill>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
