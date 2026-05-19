import { useState } from 'react';
import { Plus, ShieldCheck, UserCheck, UserX, Clock, Pencil, X } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useAuthUsers } from '@/hooks/useApi';
import { authApi, type AuthUserRow } from '@/api/authClient';

const ROLE_OPTIONS = [
  { v: 'super_admin', l: '超级管理员' },
  { v: 'company_admin', l: '公司管理员' },
  { v: 'department_admin', l: '部门管理员' },
  { v: 'department_user', l: '普通用户' },
];
const ROLE_LABEL: Record<string, string> = Object.fromEntries(ROLE_OPTIONS.map((r) => [r.v, r.l]));
const STATUS_OPTIONS = [
  { v: 'active', l: '正常' },
  { v: 'pending', l: '待审核' },
  { v: 'rejected', l: '已拒绝' },
  { v: 'disabled', l: '已禁用' },
];
const STATUS_LABEL: Record<string, string> = Object.fromEntries(STATUS_OPTIONS.map((s) => [s.v, s.l]));
const NEEDS_DEPT = (role: string) => role === 'department_admin' || role === 'department_user';

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
const cellTone = (v: string): 'good' | 'info' | 'bad' | 'muted' =>
  v === '读写' ? 'good' : v === '只读' ? 'info' : v === '禁止' ? 'bad' : 'muted';

function Avatar({ name, bg }: { name: string; bg: string }) {
  return (
    <div className={`w-7 h-7 rounded-full ${bg} flex items-center justify-center text-xs font-medium`}>
      {name[0]?.toUpperCase() || '?'}
    </div>
  );
}


function fmt(n: number | null | undefined) {
  return new Intl.NumberFormat('zh-CN').format(Number(n || 0));
}

function scopeLabel(scope: string | undefined) {
  return scope === 'company' ? '全公司' : '部门';
}

function StatLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 leading-5">
      <span className="text-xxs text-muted whitespace-nowrap">{label}</span>
      <span className="text-xs num font-semibold text-gray-800 whitespace-nowrap">{value}</span>
    </div>
  );
}

function StatCell({ children }: { children: React.ReactNode }) {
  return <div className="min-w-[132px] space-y-0.5">{children}</div>;
}


function PendingRegistrations({ onChanged }: { onChanged: () => void }) {
  const { data, isLoading, error, refetch } = useAuthUsers();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const pending = (data?.items ?? []).filter((u) => u.approval_status === 'pending');

  async function act(u: AuthUserRow, kind: 'approve' | 'reject') {
    setBusy(u.id);
    setMsg(null);
    try {
      if (kind === 'approve') await authApi.approveUser(u.id);
      else await authApi.rejectUser(u.id);
      await refetch();
      onChanged();
      setMsg(`已${kind === 'approve' ? '通过' : '拒绝'} @${u.username}`);
    } catch (e) {
      setMsg(`操作失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  const columns: Column<AuthUserRow>[] = [
    {
      key: 'user', header: '申请用户',
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          <Avatar name={r.username} bg="bg-amber-100 text-amber-700" />
          <div className="min-w-0">
            <div className="text-xs font-medium">{r.username}</div>
            <div className="text-xxs text-muted truncate">{r.display_name || r.email || '—'}</div>
          </div>
        </div>
      ),
    },
    { key: 'email', header: '邮箱', cell: (r) => <span className="text-xs num">{r.email || '—'}</span> },
    { key: 'role', header: '申请角色', cell: (r) => <Pill tone="muted">{ROLE_LABEL[r.role] || r.role}</Pill> },
    { key: 'dept', header: '部门', cell: (r) => <span className="text-xs">{r.department_name || '—'}</span> },
    {
      key: 'action', header: '', align: 'right',
      cell: (r) => (
        <div className="flex items-center justify-end gap-1.5">
          <button className="btn btn-primary text-xxs disabled:opacity-50" disabled={busy === r.id} onClick={() => act(r, 'approve')}>
            <UserCheck size={12} />{busy === r.id ? '处理中…' : '通过'}
          </button>
          <button className="chip text-xxs disabled:opacity-50" disabled={busy === r.id} onClick={() => act(r, 'reject')}>
            <UserX size={12} />拒绝
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="card">
      <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
        <Clock size={16} className="text-amber-600" />
        <h3 className="text-sm font-semibold text-gray-800">待审核注册申请</h3>
        <span className="text-xxs text-muted">{pending.length} 条</span>
        {msg && <span className="ml-auto text-xxs text-muted">{msg}</span>}
      </div>
      <AsyncState loading={isLoading} error={error} isEmpty={pending.length === 0} emptyMessage="暂无待审核的注册申请" height={140}>
        <DataTable columns={columns} data={pending} rowKey={(r) => r.id} />
      </AsyncState>
    </div>
  );
}

function EditUserModal({ user, onClose, onSaved }: { user: AuthUserRow; onClose: () => void; onSaved: () => void }) {
  const [role, setRole] = useState(ROLE_OPTIONS.some((r) => r.v === user.role) ? user.role : 'department_user');
  const [dept, setDept] = useState(user.department_name || 'cross_border');
  const [displayName, setDisplayName] = useState(user.display_name || '');
  const [status, setStatus] = useState(user.approval_status || 'active');
  const [active, setActive] = useState(user.is_active);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {
        role,
        display_name: displayName || null,
        is_active: active,
        approval_status: status,
      };
      if (NEEDS_DEPT(role) && dept.trim()) body.department_code = dept.trim();
      await authApi.patchUser(user.id, body as never);
      onSaved();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div className="relative card w-full max-w-md">
        <div className="px-4 py-3 border-b border-line flex items-center">
          <h3 className="text-sm font-semibold text-gray-800">编辑用户 · @{user.username}</h3>
          <button className="ml-auto text-muted hover:text-gray-700" onClick={onClose} aria-label="关闭"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">
          <label className="block">
            <span className="text-xxs text-muted">角色 / 权限</span>
            <select className="mt-1 w-full text-xs border border-line rounded px-2 py-1.5 bg-white" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLE_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </label>
          {NEEDS_DEPT(role) && (
            <label className="block">
              <span className="text-xxs text-muted">部门代码（部门角色必填）</span>
              <input className="mt-1 w-full text-xs border border-line rounded px-2 py-1.5" value={dept} onChange={(e) => setDept(e.target.value)} placeholder="cross_border" />
            </label>
          )}
          <label className="block">
            <span className="text-xxs text-muted">显示名</span>
            <input className="mt-1 w-full text-xs border border-line rounded px-2 py-1.5" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xxs text-muted">审批状态</span>
              <select className="mt-1 w-full text-xs border border-line rounded px-2 py-1.5 bg-white" value={status} onChange={(e) => setStatus(e.target.value)}>
                {STATUS_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xxs text-muted">账号启用</span>
              <select className="mt-1 w-full text-xs border border-line rounded px-2 py-1.5 bg-white" value={active ? '1' : '0'} onChange={(e) => setActive(e.target.value === '1')}>
                <option value="1">启用</option>
                <option value="0">禁用</option>
              </select>
            </label>
          </div>
          {err && <div className="text-xxs text-red-600">保存失败：{err}</div>}
        </div>
        <div className="px-4 py-3 border-t border-line flex items-center justify-end gap-2">
          <button className="chip text-xs" onClick={onClose}>取消</button>
          <button className="btn btn-primary text-xs disabled:opacity-50" disabled={saving} onClick={save}>
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

function AllUsers() {
  const { data, isLoading, error, refetch } = useAuthUsers();
  const [editing, setEditing] = useState<AuthUserRow | null>(null);
  const users = data?.items ?? [];
  const columns: Column<AuthUserRow>[] = [
    {
      key: 'user', header: '用户',
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          <Avatar name={r.username} bg="bg-brand-100 text-brand-700" />
          <div className="min-w-0">
            <div className="text-xs font-medium">{r.username}</div>
            <div className="text-xxs text-muted truncate">{r.display_name || '—'}</div>
          </div>
        </div>
      ),
    },
    { key: 'email', header: '邮箱', cell: (r) => <span className="text-xs num">{r.email || '—'}</span> },
    {
      key: 'role', header: '角色',
      cell: (r) => {
        const tone: 'warn' | 'info' | 'good' | 'muted' =
          r.role === 'super_admin' ? 'warn' : r.role === 'company_admin' ? 'info' : r.role === 'department_admin' ? 'good' : 'muted';
        return <Pill tone={tone}>{ROLE_LABEL[r.role] || r.role}</Pill>;
      },
    },
    { key: 'dept', header: '部门', cell: (r) => <span className="text-xs">{r.department_name || '—'}</span> },
    {
      key: 'collectionStats', header: '采集', width: '150px',
      cell: (r) => (
        <StatCell>
          <StatLine label={`${scopeLabel(r.stats?.collection?.scope)}总量`} value={fmt(r.stats?.collection?.total)} />
          <StatLine label="今日采集" value={fmt(r.stats?.collection?.today)} />
        </StatCell>
      ),
    },
    {
      key: 'creatorStats', header: '达人 / 建联', width: '160px',
      cell: (r) => (
        <StatCell>
          <StatLine label="负责达人" value={fmt(r.stats?.creators?.owned)} />
          <StatLine label="已建联" value={fmt(r.stats?.creators?.contacted)} />
        </StatCell>
      ),
    },
    {
      key: 'outreachStats', header: '邮件建联', width: '170px',
      cell: (r) => (
        <StatCell>
          <StatLine label="已发送" value={fmt(r.stats?.outreach?.sent)} />
          <StatLine label="草稿 / 失败" value={`${fmt(r.stats?.outreach?.drafts)} / ${fmt(r.stats?.outreach?.failed)}`} />
        </StatCell>
      ),
    },
    {
      key: 'status', header: '状态',
      cell: (r) => {
        const ok = r.approval_status === 'active' && r.is_active;
        return <Pill tone={ok ? 'good' : r.approval_status === 'pending' ? 'warn' : 'muted'}>{!r.is_active ? '已禁用' : STATUS_LABEL[r.approval_status] || r.approval_status}</Pill>;
      },
    },
    {
      key: 'action', header: '', align: 'right',
      cell: (r) => (
        <div className="flex items-center justify-end gap-1.5">
          <button className="chip text-xxs" onClick={() => setEditing(r)}><Pencil size={12} />编辑</button>
        </div>
      ),
    },
  ];

  return (
    <div className="card">
      <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
        <ShieldCheck size={16} className="text-muted" />
        <h3 className="text-sm font-semibold text-gray-800">全公司用户</h3>
        <span className="text-xxs text-muted">{users.length} 人</span>
        <div className="ml-auto">
          <button className="btn btn-primary disabled:opacity-50" disabled title="新增用户暂由后端注册流程处理"><Plus size={12} />新增用户</button>
        </div>
      </div>
      <AsyncState loading={isLoading} error={error} isEmpty={users.length === 0} height={200}>
        <DataTable columns={columns} data={users} rowKey={(r) => r.id} />
      </AsyncState>
      {editing && (
        <EditUserModal
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={() => refetch()}
        />
      )}
    </div>
  );
}

export default function Users() {
  return (
    <div className="space-y-4">
      <PendingRegistrations onChanged={() => { /* AllUsers shares the same query cache and refetches on its own actions */ }} />
      <AllUsers />

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
