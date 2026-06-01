import { FormEvent, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Eye, EyeOff, KeyRound, X } from 'lucide-react';
import { useChangePassword } from '@/hooks/useApi';

type Language = 'zh' | 'en';

interface ChangePasswordDialogProps {
  open: boolean;
  language: Language;
  onClose: () => void;
  onChanged?: () => void;
}

const copyByLanguage = {
  zh: {
    title: '修改密码',
    subtitle: '更新当前登录账号的密码',
    current: '当前密码',
    next: '新密码',
    confirm: '确认新密码',
    currentPlaceholder: '输入当前密码',
    nextPlaceholder: '至少 6 位字符',
    confirmPlaceholder: '再次输入新密码',
    show: '显示密码',
    hide: '隐藏密码',
    close: '关闭',
    cancel: '取消',
    save: '保存密码',
    saving: '保存中',
    saved: '密码已更新',
    oldRequired: '请输入当前密码',
    newRequired: '新密码至少 6 位',
    samePassword: '新密码不能和当前密码相同',
    mismatch: '两次输入的新密码不一致',
  },
  en: {
    title: 'Change password',
    subtitle: 'Update the password for this account',
    current: 'Current password',
    next: 'New password',
    confirm: 'Confirm new password',
    currentPlaceholder: 'Enter current password',
    nextPlaceholder: 'At least 6 characters',
    confirmPlaceholder: 'Enter it again',
    show: 'Show password',
    hide: 'Hide password',
    close: 'Close',
    cancel: 'Cancel',
    save: 'Save password',
    saving: 'Saving',
    saved: 'Password updated',
    oldRequired: 'Enter the current password',
    newRequired: 'New password must be at least 6 characters',
    samePassword: 'New password must differ from current password',
    mismatch: 'New passwords do not match',
  },
};

function scorePassword(value: string) {
  let score = 0;
  if (value.length >= 6) score += 1;
  if (value.length >= 10) score += 1;
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
  if (/\d/.test(value) || /[^A-Za-z0-9]/.test(value)) score += 1;
  return Math.min(score, 4);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error || '');
}

export function ChangePasswordDialog({ open, language, onClose, onChanged }: ChangePasswordDialogProps) {
  const copy = copyByLanguage[language];
  const changePassword = useChangePassword();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPasswords, setShowPasswords] = useState(false);
  const [clientError, setClientError] = useState('');
  const [saved, setSaved] = useState(false);
  const strength = useMemo(() => scorePassword(newPassword), [newPassword]);

  useEffect(() => {
    if (!open) {
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowPasswords(false);
      setClientError('');
      setSaved(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose, open]);

  if (!open) return null;

  const inputType = showPasswords ? 'text' : 'password';
  const validate = () => {
    if (!oldPassword) return copy.oldRequired;
    if (newPassword.length < 6) return copy.newRequired;
    if (newPassword === oldPassword) return copy.samePassword;
    if (newPassword !== confirmPassword) return copy.mismatch;
    return '';
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = validate();
    setClientError(message);
    setSaved(false);
    if (message) return;
    try {
      await changePassword.mutateAsync({
        old_password: oldPassword,
        new_password: newPassword,
      });
      onChanged?.();
      setSaved(true);
      window.setTimeout(onClose, 700);
    } catch {
      /* mutation error is rendered below */
    }
  };

  const serverError = changePassword.error ? errorMessage(changePassword.error) : '';
  const visibleError = clientError || serverError;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/55"
        onClick={onClose}
        aria-hidden="true"
      />
      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-[420px] rounded border border-border shadow-soft"
        style={{ background: 'rgb(var(--bg-elev-1))' }}
      >
        <header className="flex items-start gap-3 border-b border-border px-5 py-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-accent/15 text-accent">
            <KeyRound size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold">{copy.title}</h2>
            <p className="mt-0.5 text-xs text-muted">{copy.subtitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded text-muted hover:text-text"
            title={copy.close}
            aria-label={copy.close}
          >
            <X size={16} />
          </button>
        </header>

        <div className="space-y-3 px-5 py-4">
          <PasswordField
            label={copy.current}
            placeholder={copy.currentPlaceholder}
            type={inputType}
            value={oldPassword}
            onChange={setOldPassword}
            toggleLabel={showPasswords ? copy.hide : copy.show}
            showPasswords={showPasswords}
            onToggle={() => setShowPasswords((value) => !value)}
            autoFocus
          />
          <div>
            <PasswordField
              label={copy.next}
              placeholder={copy.nextPlaceholder}
              type={inputType}
              value={newPassword}
              onChange={setNewPassword}
              toggleLabel={showPasswords ? copy.hide : copy.show}
              showPasswords={showPasswords}
              onToggle={() => setShowPasswords((value) => !value)}
            />
            <div className="mt-2 grid grid-cols-4 gap-1" aria-hidden="true">
              {[1, 2, 3, 4].map((level) => (
                <span
                  key={level}
                  className="h-1 rounded-pill"
                  style={{
                    background:
                      strength >= level
                        ? level >= 3
                          ? 'rgb(var(--good))'
                          : 'rgb(var(--accent))'
                        : 'rgb(var(--border))',
                  }}
                />
              ))}
            </div>
          </div>
          <PasswordField
            label={copy.confirm}
            placeholder={copy.confirmPlaceholder}
            type={inputType}
            value={confirmPassword}
            onChange={setConfirmPassword}
            toggleLabel={showPasswords ? copy.hide : copy.show}
            showPasswords={showPasswords}
            onToggle={() => setShowPasswords((value) => !value)}
          />

          {visibleError && (
            <div className="flex items-start gap-2 rounded border border-bad/35 bg-bad/10 px-3 py-2 text-xs text-bad">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>{visibleError}</span>
            </div>
          )}
          {saved && (
            <div className="flex items-start gap-2 rounded border border-good/35 bg-good/10 px-3 py-2 text-xs text-good">
              <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
              <span>{copy.saved}</span>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <button type="button" onClick={onClose} className="btn btn-ghost">
            {copy.cancel}
          </button>
          <button type="submit" className="btn btn-primary" disabled={changePassword.isPending || saved}>
            <KeyRound size={14} />
            {changePassword.isPending ? copy.saving : copy.save}
          </button>
        </footer>
      </form>
    </div>
  );
}

interface PasswordFieldProps {
  label: string;
  placeholder: string;
  type: 'text' | 'password';
  value: string;
  onChange: (value: string) => void;
  toggleLabel: string;
  showPasswords: boolean;
  onToggle: () => void;
  autoFocus?: boolean;
}

function PasswordField({
  label,
  placeholder,
  type,
  value,
  onChange,
  toggleLabel,
  showPasswords,
  onToggle,
  autoFocus,
}: PasswordFieldProps) {
  return (
    <label className="block text-xs font-medium">
      <span>{label}</span>
      <span className="relative mt-1.5 block">
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className="h-10 w-full rounded border border-border bg-elev2 px-3 pr-10 text-sm outline-none transition-colors placeholder:text-muted focus:border-accent"
        />
        <button
          type="button"
          onClick={onToggle}
          className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded text-muted hover:text-text"
          title={toggleLabel}
          aria-label={toggleLabel}
        >
          {showPasswords ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </span>
    </label>
  );
}
