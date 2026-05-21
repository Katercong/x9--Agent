import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { queryClient } from '@/api/queryClient';

type Feedback = {
  tone: 'success' | 'error';
  title: string;
  message: string;
};

const ERROR_MESSAGES: Record<string, string> = {
  access_denied: 'Google 授权已取消，Gmail 没有绑定。',
  missing_code: 'Google 没有返回授权码，请重新连接 Gmail。',
  missing_state: '授权状态缺失，请从系统内重新点击连接 Gmail。',
  invalid_state: '授权状态校验失败，请重新连接 Gmail。',
  state_user_mismatch: '授权发起账号和当前登录账号不一致，请用当前账号重新连接 Gmail。',
  login_required: '请先登录系统账号，再连接 Gmail。',
};

function readableError(raw: string): string {
  const msg = raw.trim();
  if (!msg) return 'Gmail 绑定失败，请重新连接。';
  if (ERROR_MESSAGES[msg]) return ERROR_MESSAGES[msg];
  if (msg.includes('Missing code verifier') || msg.includes('invalid_grant')) {
    return '本次 Google 授权参数已失效，请重新点击连接 Gmail。';
  }
  if (msg.includes('already linked to another local user')) {
    return '这个 Gmail 已经绑定到另一个系统账号，不能重复绑定。';
  }
  if (msg.includes('Login is required')) {
    return '请先登录系统账号，再连接 Gmail。';
  }
  if (msg.includes('client not configured') || msg.includes('OAuth client')) {
    return 'Gmail OAuth 配置不完整，请联系管理员检查 Google OAuth 客户端配置。';
  }
  return msg.length > 180 ? `${msg.slice(0, 180)}...` : msg;
}

export function GmailOAuthFeedback() {
  const location = useLocation();
  const navigate = useNavigate();
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const status = params.get('gmail');
    if (!status) return;

    if (status === 'ok') {
      const email = params.get('email') || 'Gmail';
      void queryClient.invalidateQueries({ queryKey: ['gmail', 'accounts'] });
      setFeedback({
        tone: 'success',
        title: 'Gmail 已绑定',
        message: `${email} 已绑定到当前账号，现在可以用它发送建联邮件。`,
      });
    } else if (status === 'error') {
      setFeedback({
        tone: 'error',
        title: 'Gmail 绑定失败',
        message: readableError(params.get('msg') || ''),
      });
    }

    params.delete('gmail');
    params.delete('email');
    params.delete('msg');
    const nextSearch = params.toString();
    navigate(`${location.pathname}${nextSearch ? `?${nextSearch}` : ''}${location.hash}`, { replace: true });
  }, [location.hash, location.pathname, location.search, navigate]);

  useEffect(() => {
    if (!feedback) return;
    const timer = window.setTimeout(() => setFeedback(null), 6500);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  if (!feedback) return null;

  const ok = feedback.tone === 'success';
  const Icon = ok ? CheckCircle2 : AlertTriangle;

  return (
    <div
      className="fixed right-4 top-4 z-50 w-[min(420px,calc(100vw-32px))] rounded border px-3 py-3 shadow-lg"
      style={{
        background: 'rgb(var(--bg-elev-2))',
        borderColor: ok ? 'rgb(var(--good) / 0.45)' : 'rgb(var(--bad) / 0.45)',
        boxShadow: '0 18px 40px rgb(0 0 0 / 0.28)',
      }}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-2">
        <Icon size={17} className={ok ? 'text-good shrink-0 mt-0.5' : 'text-bad shrink-0 mt-0.5'} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text">{feedback.title}</div>
          <div className="text-xs text-muted mt-1 leading-5">{feedback.message}</div>
        </div>
        <button
          type="button"
          className="text-muted hover:text-text shrink-0"
          aria-label="关闭 Gmail 绑定提示"
          onClick={() => setFeedback(null)}
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}