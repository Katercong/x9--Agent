import { useEffect, useState } from 'react';
import { Mail, Sparkles, Send, Save, RefreshCw, History, ArrowRight, AlertOctagon } from 'lucide-react';
import { SideDrawer } from '@/components/drawer/SideDrawer';
import { Pill } from '@/components/Pill';
import {
  useOutreachTemplates, usePreviewOutreach, useCreateDraft, usePatchDraft, useSendDraft, useOutreachHistory,
  useGmailAccounts,
} from '@/hooks/useApi';
import { shortRelative } from '@/lib/format';
import type { Creator, OutreachTemplate } from '@/api/types';

interface Props {
  creator: Creator | null;
  open: boolean;
  onClose: () => void;
}

type Step = 'template' | 'preview' | 'edit' | 'sent';

export function OutreachDrawer({ creator, open, onClose }: Props) {
  const [step, setStep] = useState<Step>('template');
  const [tplId, setTplId] = useState<string>('');
  const [tone, setTone] = useState<string>('friendly');
  const [useAi, setUseAi] = useState(true);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [draftId, setDraftId] = useState<string | null>(null);
  const [sentSummary, setSentSummary] = useState<string>('');

  const tplsQ = useOutreachTemplates({ include_inactive: false });
  const accountsQ = useGmailAccounts();
  const historyQ = useOutreachHistory(open && creator ? creator.id : undefined);
  const preview = usePreviewOutreach();
  const createDraft = useCreateDraft();
  const patchDraft = usePatchDraft();
  const sendDraft = useSendDraft();

  const templates = tplsQ.data?.items ?? [];
  const accounts = accountsQ.data?.items ?? [];
  const defaultAcc = accounts.find((a) => a.is_default === 1) || accounts[0];
  const history = historyQ.data?.items ?? [];

  // Reset on close / creator change
  useEffect(() => {
    if (!open || !creator) return;
    setStep('template');
    setTplId(templates.find((t) => t.is_default === 1)?.id || templates[0]?.id || '');
    setSubject('');
    setBody('');
    setToEmail(creator.email || '');
    setDraftId(null);
    setSentSummary('');
  }, [open, creator?.id]);

  const onPreview = () => {
    if (!creator) return;
    preview.mutate(
      { creator_id: creator.id, body: { template_id: tplId || undefined, language: 'zh', use_ai: useAi, tone, n: 1 } },
      {
        onSuccess: (r) => {
          setSubject(r.subject || '');
          setBody(r.body || '');
          setStep('preview');
        },
      },
    );
  };

  const onSaveDraft = () => {
    if (!creator) return;
    if (!toEmail) { alert('收件邮箱必填'); return; }
    if (!draftId) {
      createDraft.mutate(
        {
          creator_id: String(creator.id),
          template_id: tplId || undefined,
          to_email: toEmail,
          subject, body,
          body_format: 'plain',
          ai_tone: tone,
        },
        {
          onSuccess: (d) => { setDraftId(d.id); setStep('edit'); },
        },
      );
    } else {
      patchDraft.mutate(
        { id: draftId, body: { subject, body, to_email: toEmail } },
        { onSuccess: () => setStep('edit') },
      );
    }
  };

  const onSend = () => {
    if (!draftId) return;
    if (!confirm('确认发送此邮件?')) return;
    sendDraft.mutate(
      { id: draftId, body: { confirm: true, update_creator_status: true, from_account_id: defaultAcc?.id } },
      {
        onSuccess: (d) => {
          setSentSummary(`已发送 · 主题:${d.subject} · 收件人:${d.to_email}`);
          setStep('sent');
        },
      },
    );
  };

  const onReset = () => {
    setStep('template'); setSubject(''); setBody(''); setDraftId(null); setSentSummary('');
  };

  if (!creator) return null;

  return (
    <SideDrawer
      open={open} onClose={onClose} width={640}
      title={<span>外联 · @{creator.handle}</span>}
      subtitle={<span>{creator.display_name} · {creator.country || '—'} · {creator.tier || '?'} 级 · 邮箱:{creator.email || '未知'}</span>}
      footer={
        <>
          {step === 'sent' ? (
            <>
              <button onClick={onReset} className="btn"><RefreshCw size={12} />再来一封</button>
              <button onClick={onClose} className="btn btn-primary">完成</button>
            </>
          ) : (
            <>
              <button onClick={onClose} className="btn">取消</button>
              {step === 'template' && (
                <button onClick={onPreview} disabled={preview.isPending || !tplId} className="btn btn-primary">
                  <Sparkles size={12} />{useAi ? 'AI 生成预览' : '渲染预览'} <ArrowRight size={12} />
                </button>
              )}
              {(step === 'preview' || step === 'edit') && (
                <>
                  <button onClick={onSaveDraft} disabled={createDraft.isPending || patchDraft.isPending} className="btn">
                    <Save size={12} />保存草稿
                  </button>
                  <button onClick={onSend} disabled={!draftId || sendDraft.isPending} className="btn btn-primary">
                    <Send size={12} />发送
                  </button>
                </>
              )}
            </>
          )}
        </>
      }
    >
      {/* Gmail account banner */}
      {accounts.length === 0 ? (
        <div className="card card-body mb-3" style={{ background: 'rgb(var(--warn) / 0.12)' }}>
          <div className="flex items-center gap-2 text-xs text-warn">
            <AlertOctagon size={14} /> 还没绑定 Gmail 账户 — 请先去 <a href="/settings" className="underline">设置中心</a> 绑定后才能发送
          </div>
        </div>
      ) : (
        <div className="text-xxs text-muted mb-3 flex items-center gap-2">
          <Mail size={11} />发件账户:<span className="text-text font-medium">{defaultAcc?.email}</span>
        </div>
      )}

      {/* Stepper */}
      <div className="flex items-center gap-2 mb-4 text-xxs">
        {(['template', 'preview', 'edit', 'sent'] as Step[]).map((s, i) => {
          const active = s === step;
          const passed = ['template', 'preview', 'edit', 'sent'].indexOf(step) >= i;
          return (
            <div key={s} className="flex items-center gap-2">
              <span className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-white ${
                active ? '' : passed ? 'opacity-70' : 'opacity-30'
              }`} style={{ background: active || passed ? 'rgb(var(--accent))' : 'rgb(var(--muted))' }}>
                {i + 1}
              </span>
              <span className={active ? 'text-text font-semibold' : 'text-muted'}>
                {['选模板', 'AI 预览', '编辑发送', '已发送'][i]}
              </span>
              {i < 3 && <span className="text-muted">›</span>}
            </div>
          );
        })}
      </div>

      {/* Step 1: Template */}
      {step === 'template' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted block mb-1">选择话术模板</label>
            <div className="space-y-1.5">
              {templates.map((t: OutreachTemplate) => (
                <label key={t.id} className={`flex items-start gap-2 p-2.5 rounded border cursor-pointer transition-colors ${
                  tplId === t.id ? 'border-accent' : 'border-border hover:border-muted'
                }`} style={{ background: 'rgb(var(--bg-elev-2))' }}>
                  <input type="radio" name="tpl" checked={tplId === t.id} onChange={() => setTplId(t.id)} className="mt-1" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium">{t.name}</span>
                      <Pill tone={t.language === 'zh' ? 'info' : 'warn'}>{t.language?.toUpperCase()}</Pill>
                      {t.is_default === 1 && <Pill tone="good">默认</Pill>}
                    </div>
                    {t.description && <div className="text-xxs text-muted mt-0.5">{t.description}</div>}
                    {t.collab_type && <div className="text-xxs text-muted mt-0.5">合作:{t.collab_type} · 语气:{t.tone || '—'}</div>}
                  </div>
                </label>
              ))}
              {templates.length === 0 && (
                <div className="text-xxs text-muted">没有模板,先去 <a href="/settings" className="underline">设置中心</a> 创建</div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
              使用 AI 增强(基于达人画像生成)
            </label>
            <div>
              <label className="text-xxs text-muted block mb-1">语气</label>
              <select value={tone} onChange={(e) => setTone(e.target.value)}
                      className="text-xs px-2 py-1.5 rounded border border-border w-full"
                      style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}>
                <option value="friendly">友好</option>
                <option value="formal">正式</option>
                <option value="casual">随意</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Step 2 / 3: Preview + Edit */}
      {(step === 'preview' || step === 'edit') && (
        <div className="space-y-3">
          <div>
            <label className="text-xxs text-muted block mb-1">收件人</label>
            <input value={toEmail} onChange={(e) => setToEmail(e.target.value)}
                   className="input-bare w-full px-3 py-2 rounded border border-border"
                   style={{ background: 'rgb(var(--bg-elev-2))' }} placeholder="contact@example.com" />
          </div>
          <div>
            <label className="text-xxs text-muted block mb-1">主题</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)}
                   className="input-bare w-full px-3 py-2 rounded border border-border"
                   style={{ background: 'rgb(var(--bg-elev-2))' }} />
          </div>
          <div>
            <label className="text-xxs text-muted block mb-1">正文</label>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14}
                      className="input-bare w-full px-3 py-2 rounded border border-border resize-y font-mono text-xs"
                      style={{ background: 'rgb(var(--bg-elev-2))' }} />
          </div>
          {preview.data?.ai_used && (
            <div className="text-xxs text-good">✓ AI 已增强 · 上下文已注入 · 可继续手工微调</div>
          )}
          {preview.isPending && (
            <div className="text-xxs text-muted flex items-center gap-1"><RefreshCw size={11} className="animate-spin" />AI 生成中...</div>
          )}
          {draftId && <div className="text-xxs text-muted">草稿 ID: {draftId}</div>}
        </div>
      )}

      {/* Step 4: Sent */}
      {step === 'sent' && (
        <div className="card card-body" style={{ background: 'rgb(var(--good) / 0.12)' }}>
          <div className="flex items-center gap-2 text-good">
            <Send size={14} />
            <span className="text-sm font-medium">发送成功</span>
          </div>
          <div className="text-xxs text-muted mt-2">{sentSummary}</div>
        </div>
      )}

      {/* History */}
      <div className="mt-6">
        <div className="flex items-center gap-2 mb-2">
          <History size={13} className="text-muted" />
          <h4 className="text-xs font-semibold">历史外联记录</h4>
          <span className="text-xxs text-muted">共 {history.length} 条</span>
        </div>
        {history.length === 0 ? (
          <div className="text-xxs text-muted">还没有给这位达人发过邮件</div>
        ) : (
          <div className="space-y-1.5">
            {history.map((h: any) => (
              <div key={h.id} className="text-xxs border border-border rounded px-2 py-1.5" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                <div className="flex items-center justify-between">
                  <span className="font-medium truncate flex-1 min-w-0">{h.subject}</span>
                  <Pill tone={h.status === 'sent' ? 'good' : h.status === 'queued' ? 'warn' : 'muted'}>{h.status}</Pill>
                </div>
                <div className="text-muted mt-0.5">{h.to_email} · {shortRelative(h.sent_at)} · {h.from_email}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </SideDrawer>
  );
}
