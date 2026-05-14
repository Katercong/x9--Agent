import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, Briefcase, Building, Shield } from 'lucide-react';
import { useRoleStore, roleLabel, roleSubtitle, roleHome, type Role } from '@/stores/roleStore';
import { cn } from '@/lib/cn';

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
  const { currentRole, switchRole } = useRoleStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const handleSwitch = (role: Role) => {
    switchRole(role);
    navigate(roleHome[role]);
    setOpen(false);
  };

  const Icon = roleIcon[currentRole];

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded hover:bg-soft transition-colors"
      >
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
          style={{ background: roleColor[currentRole] }}
        >
          <Icon size={14} />
        </span>
        <div className="flex flex-col items-start leading-tight">
          <span className="text-xs font-medium text-gray-800">testadmin1</span>
          <span className="text-xxs text-muted">{roleLabel[currentRole]}</span>
        </div>
        <ChevronDown size={14} className="text-muted" />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-64 bg-white border border-line rounded-md shadow-soft py-1 z-50">
          <div className="px-3 py-2 text-xxs text-muted border-b border-line">切换视角(预览专用)</div>
          {(['company', 'department', 'super'] as Role[]).map((r) => {
            const RI = roleIcon[r];
            const active = r === currentRole;
            return (
              <button
                key={r}
                onClick={() => handleSwitch(r)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2 hover:bg-soft text-left transition-colors',
                  active && 'bg-soft',
                )}
              >
                <span
                  className="w-8 h-8 rounded-full flex items-center justify-center text-white shrink-0"
                  style={{ background: roleColor[r] }}
                >
                  <RI size={14} />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-800">{roleLabel[r]}</div>
                  <div className="text-xxs text-muted truncate">{roleSubtitle[r]}</div>
                </div>
                {active && <span className="text-xxs text-brand-500">当前</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
