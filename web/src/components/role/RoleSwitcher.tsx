import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Briefcase, Building, Shield, LogIn, LogOut, Loader2, KeyRound, X } from 'lucide-react';
import {
  useRoleStore, backendRoleLabel,
  type Role,
} from '@/stores/roleStore';
import { useChangePassword, useLogout } from '@/hooks/useAuth';

const roleIcon: Record<Role, typeof Briefcase> = {
  company: Briefcase,
  department: Building,
  super: Shield,
};

const roleColor: Record<Role, string> = {
  company: '#f97316',
  department: '#3370ff',
  super: '#8b5cf6',
};

export default function RoleSwitcher() {
  const { currentRole, currentUser } = useRoleStore();
  const [open, setOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const logout = useLogout();

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const username = currentUser?.display_name || currentUser?.username || '未登录';
  const userRoleLabel = currentUser ? backendRoleLabel[currentUser.role] : '未登录';
  const departmentName = currentUser?.department_name || currentUser?.department_code || '';
  const Icon = roleIcon[currentRole];

  const handleLogout = () => {
    if (!confirm('确定退出登录？')) return;
    logout.mutate(undefined, {
      onSettled: () => { window.location.href = '/login'; },
    });
  };

  const handleLogin = () => {
    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded hover:bg-soft transition-colors"
      >
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
          style={{ background: currentUser ? roleColor[currentRole] : '#86909c' }}
        >
          <Icon size={14} />
        </span>
        <div className="hidden md:flex flex-col items-start leading-tight">
          <span className="text-xs font-medium text-gray-800 truncate max-w-[160px]">{username}</span>
          <span className="text-xxs text-muted">{userRoleLabel}{departmentName ? ` · ${departmentName}` : ''}</span>
        </div>
        <ChevronDown size={14} className="text-muted" />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-72 bg-white border border-line rounded-md shadow-soft py-1 z-50">
          <div className="px-3 py-3 border-b border-line">
            <div className="flex items-center gap-2.5">
              <span
                className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0"
                style={{ background: currentUser ? roleColor[currentRole] : '#86909c' }}
              >
                {username[0]?.toUpperCase() || '?'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-gray-800 truncate">{username}</div>
                <div className="text-xxs text-muted truncate">
                  {currentUser?.username && currentUser.username !== username && (
                    <span>@{currentUser.username} · </span>
                  )}
                  {userRoleLabel}
                </div>
                {departmentName && <div className="text-xxs text-muted truncate">部门：{departmentName}</div>}
              </div>
            </div>
          </div>

          <div className="px-3 py-2 text-xxs text-muted">
            角色由登录会话决定，不能在前端切换身份。
          </div>

          <div className="border-t border-line">
            {currentUser ? (
              <>
                <button
                  onClick={() => {
                    setOpen(false);
                    setPasswordOpen(true);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-soft text-left transition-colors text-xs text-gray-700"
                >
                  <KeyRound size={14} />
                  <span>修改密码</span>
                </button>
                <button
                  onClick={handleLogout}
                  disabled={logout.isPending}
                  className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-soft text-left transition-colors text-xs text-bad disabled:opacity-50"
                >
                  {logout.isPending ? <Loader2 size={14} className="animate-spin" /> : <LogOut size={14} />}
                  <span>退出登录</span>
                </button>
              </>
            ) : (
              <button
                onClick={handleLogin}
                className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-soft text-left transition-colors text-xs text-brand-500"
              >
                <LogIn size={14} />
                <span>前往登录</span>
              </button>
            )}
          </div>
        </div>
      )}
      {passwordOpen && (
        <ChangeOwnPasswordModal
          onClose={() => setPasswordOpen(false)}
        />
      )}
    </div>
  );
}

function ChangeOwnPasswordModal({
  onClose,
}: {
  onClose: () => void;
}) {
  const changePassword = useChangePassword();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function save() {
    setErr(null);
    setSaved(false);
    if (!oldPassword) {
      setErr('请输入当前密码');
      return;
    }
    if (newPassword.length < 6) {
      setErr('新密码至少 6 位');
      return;
    }
    if (newPassword === oldPassword) {
      setErr('新密码不能和当前密码相同');
      return;
    }
    if (newPassword !== confirmPassword) {
      setErr('两次输入的新密码不一致');
      return;
    }
    try {
      await changePassword.mutateAsync({ oldPassword, newPassword });
      setSaved(true);
      window.setTimeout(onClose, 700);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div className="relative card w-full max-w-md">
        <div className="px-4 py-3 border-b border-line flex items-center gap-2">
          <KeyRound size={16} className="text-muted" />
          <div>
            <h3 className="text-sm font-semibold text-gray-800">修改密码</h3>
            <div className="text-xxs text-muted">更新当前登录账号的密码</div>
          </div>
          <button className="ml-auto text-muted hover:text-gray-700" onClick={onClose} aria-label="关闭"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">
          <PasswordInput label="当前密码" value={oldPassword} onChange={setOldPassword} autoFocus />
          <PasswordInput label="新密码" value={newPassword} onChange={setNewPassword} placeholder="至少 6 位字符" />
          <PasswordInput label="确认新密码" value={confirmPassword} onChange={setConfirmPassword} />
          {err && <div className="text-xxs text-red-600">修改失败：{err}</div>}
          {saved && <div className="text-xxs text-green-700">密码已更新</div>}
        </div>
        <div className="px-4 py-3 border-t border-line flex items-center justify-end gap-2">
          <button className="chip text-xs" onClick={onClose}>取消</button>
          <button className="btn btn-primary text-xs disabled:opacity-50" disabled={changePassword.isPending || saved} onClick={save}>
            <KeyRound size={12} />{changePassword.isPending ? '保存中…' : '保存密码'}
          </button>
        </div>
      </div>
    </div>
  );
}

function PasswordInput({
  label,
  value,
  onChange,
  placeholder,
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xxs text-muted">{label}</span>
      <input
        type="password"
        className="mt-1 w-full text-xs border border-line rounded px-2 py-1.5"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
      />
    </label>
  );
}
