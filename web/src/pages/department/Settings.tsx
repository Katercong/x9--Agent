import { Building, Users, KeyRound, Sliders } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { deptMembers } from '@/mock/department';

type Member = typeof deptMembers[number];

const memberColumns: Column<Member>[] = [
  {
    key: 'name', header: '成员',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-medium">
          {r.name[0].toUpperCase()}
        </div>
        <span className="text-xs font-medium">{r.name}</span>
      </div>
    ),
  },
  { key: 'role', header: '角色', cell: (r) => <Pill tone="info">{r.role}</Pill> },
  { key: 'email', header: '邮箱', cell: (r) => <span className="text-xs text-muted">{r.email}</span> },
  { key: 'joined', header: '加入时间', cell: (r) => <span className="text-xs text-muted">{r.joined}</span> },
  { key: 'status', header: '状态', cell: (r) => <Pill tone={r.status === 'active' ? 'good' : 'muted'}>{r.status === 'active' ? '在职' : '离职'}</Pill> },
  { key: 'action', header: '', align: 'right', cell: () => <button className="chip text-xxs">编辑</button> },
];

export default function Settings() {
  return (
    <div className="space-y-4">
      {/* 部门信息 */}
      <div className="card card-body">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-md bg-brand-100 text-brand-600 flex items-center justify-center">
            <Building size={20} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-800">女性护理部</h3>
            <div className="text-xs text-muted">负责人:testadmin1 · 创建于 2025-11-10</div>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div>
            <div className="text-muted">部门 ID</div>
            <div className="font-mono mt-1">dept-fc-001</div>
          </div>
          <div>
            <div className="text-muted">成员数</div>
            <div className="num mt-1">{deptMembers.length}</div>
          </div>
          <div>
            <div className="text-muted">管辖达人</div>
            <div className="num mt-1">33</div>
          </div>
          <div>
            <div className="text-muted">本月营收</div>
            <div className="num mt-1">¥ 640,000</div>
          </div>
        </div>
      </div>

      {/* 部门成员 */}
      <div className="card">
        <div className="px-4 py-3 flex items-center justify-between border-b border-line">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">部门成员</h3>
          </div>
          <button className="btn btn-primary">+ 添加成员</button>
        </div>
        <DataTable columns={memberColumns} data={deptMembers} rowKey={(r) => r.name} />
      </div>

      {/* 偏好 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-3">
            <Sliders size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">部门偏好</h3>
          </div>
          <div className="space-y-3 text-xs">
            <label className="flex items-center justify-between">
              <span>默认对接人</span>
              <select className="border border-line rounded px-2 py-1">
                <option>testuser</option>
                <option>codex_smoke</option>
                <option>user_test</option>
              </select>
            </label>
            <label className="flex items-center justify-between">
              <span>默认建联话术模板</span>
              <select className="border border-line rounded px-2 py-1">
                <option>初次建联 · 女性护理</option>
              </select>
            </label>
            <label className="flex items-center justify-between">
              <span>邮件签名</span>
              <button className="chip text-xxs">编辑</button>
            </label>
            <label className="flex items-center justify-between">
              <span>每日报送钉钉</span>
              <input type="checkbox" defaultChecked />
            </label>
          </div>
        </div>
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-3">
            <KeyRound size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">部门权限</h3>
          </div>
          <div className="space-y-2 text-xs">
            {[
              ['查看本部门数据', true],
              ['编辑本部门达人', true],
              ['编辑产品库', false],
              ['访问 LLM 配置', false],
              ['查看其他部门数据', false],
              ['导出全量数据', false],
            ].map(([label, enabled]) => (
              <div key={label as string} className="flex items-center justify-between py-1.5 border-b border-line/60 last:border-0">
                <span>{label}</span>
                <Pill tone={enabled ? 'good' : 'muted'}>{enabled ? '已授权' : '未授权'}</Pill>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
