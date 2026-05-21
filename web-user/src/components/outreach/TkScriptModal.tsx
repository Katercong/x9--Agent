import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  BookmarkPlus, Check, ChevronDown, ChevronUp, Copy, RefreshCw,
  Sparkles, Trash2, X, Zap,
} from 'lucide-react';
import { useCreateTkPrompt, useDeleteTkPrompt, useGenerateTkScript, useTkPrompts } from '@/hooks/useApi';
import type { Creator, TkStrategy } from '@/api/types';

const COMMISSION_OPTIONS = [5, 10, 15, 20];

const STRATEGY_META: Record<TkStrategy, { label: string; desc: string; icon: typeof Zap }> = {
  template: { label: '模板', desc: '用达人 bio / 视频 / 关键词填充固定模板', icon: Zap },
  hybrid:   { label: '混合', desc: '固定品牌框架 + AI 写个性化开场白', icon: Sparkles },
  ai:       { label: 'AI 全生成', desc: 'AI 根据达人数据完整生成话术', icon: Sparkles },
};

const PRODUCT_KEY_LABELS: Record<string, string> = {
  feminine_care: '女性护理',
  adult_care: '成人护理',
  pet_care: '宠物护理',
  baby_care: '婴儿护理',
  all: '全品类',
};

const AI_STATUS_LABELS: Record<string, string> = {
  template: '模板生成',
  generated: 'AI 生成',
  hybrid: '混合生成',
  fallback: '模板兜底',
  not_configured: '未配置 LLM',
};

const LS_KEY = 'tk_script_last_strategy';

function readStoredStrategy(): TkStrategy {
  try { return (localStorage.getItem(LS_KEY) as TkStrategy) || 'template'; } catch { return 'template'; }
}
function writeStoredStrategy(s: TkStrategy) {
  try { localStorage.setItem(LS_KEY, s); } catch { /* ignore */ }
}

export function TkScriptModal({
  creator,
  onClose,
}: {
  creator: Creator;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [strategy, setStrategyState] = useState<TkStrategy>(readStoredStrategy);
  const [commission, setCommission] = useState(20);
  const [script, setScript] = useState('');
  const [productKey, setProductKey] = useState('');
  const [aiStatus, setAiStatus] = useState('');
  const [contextUsed, setContextUsed] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState(false);
  const [showContext, setShowContext] = useState(false);
  const [showPromptEditor, setShowPromptEditor] = useState(false);
  const [customPrompt, setCustomPrompt] = useState('');
  const [selectedPromptId, setSelectedPromptId] = useState('');
  const [savePromptName, setSavePromptName] = useState('');
  const [showSaveForm, setShowSaveForm] = useState(false);
  const generatedForRef = useRef('');

  const gen = useGenerateTkScript();
  const promptsQ = useTkPrompts();
  const createPrompt = useCreateTkPrompt();
  const deletePrompt = useDeleteTkPrompt();

  const setStrategy = (s: TkStrategy) => {
    setStrategyState(s);
    writeStoredStrategy(s);
  };

  const savedPrompts = (promptsQ.data?.items ?? []).filter(
    (p) => p.strategy === strategy || (strategy === 'hybrid' && p.strategy === 'hybrid') || (strategy === 'ai' && p.strategy === 'ai'),
  );

  const generate = (opts?: { comm?: number; strat?: TkStrategy; prompt?: string; pid?: string }) => {
    const comm = opts?.comm ?? commission;
    const strat = opts?.strat ?? strategy;
    const cPrompt = opts?.prompt !== undefined ? opts.prompt : (customPrompt || undefined);
    const pId = opts?.pid !== undefined ? opts.pid : (selectedPromptId || undefined);
    const key = `${creator.id}:${comm}:${strat}:${cPrompt || pId || ''}`;
    generatedForRef.current = key;
    gen.mutate(
      { creator_id: creator.id, commission: comm, strategy: strat, custom_prompt: cPrompt, prompt_id: pId },
      {
        onSuccess: (r) => {
          if (generatedForRef.current !== key) return;
          setScript(r.script);
          setProductKey(r.product_key);
          setAiStatus(r.ai_status);
          setContextUsed(r.context_used ?? {});
        },
      },
    );
  };

  // Auto-generate on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { generate(); }, []);

  const onCopy = async () => {
    if (!script) return;
    await navigator.clipboard.writeText(script);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const onSavePrompt = async () => {
    if (!savePromptName.trim() || !customPrompt.trim()) return;
    await createPrompt.mutateAsync({ name: savePromptName.trim(), prompt: customPrompt.trim(), strategy });
    qc.invalidateQueries({ queryKey: ['tk-prompts'] });
    setSavePromptName('');
    setShowSaveForm(false);
  };

  const onDeletePrompt = async (id: string) => {
    await deletePrompt.mutateAsync(id);
    qc.invalidateQueries({ queryKey: ['tk-prompts'] });
    if (selectedPromptId === id) setSelectedPromptId('');
  };

  const onSelectPrompt = (id: string) => {
    setSelectedPromptId(id);
    const found = promptsQ.data?.items.find((p) => p.id === id);
    if (found) setCustomPrompt(found.prompt);
  };

  const hasPersonalization = Boolean(
    contextUsed.bio_excerpt || contextUsed.video_title || contextUsed.matched_keywords,
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgb(0 0 0 / 0.55)' }}>
      <div className="card flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">TK DM 邀约话术</span>
            <span className="text-xxs text-muted">@{creator.handle}</span>
            {productKey && (
              <span className="chip text-xxs">{PRODUCT_KEY_LABELS[productKey] ?? productKey}</span>
            )}
            {aiStatus && (
              <span className="chip text-xxs" style={{ background: 'rgb(var(--accent) / 0.12)', color: 'rgb(var(--accent))' }}>
                {AI_STATUS_LABELS[aiStatus] ?? aiStatus}
              </span>
            )}
          </div>
          <button type="button" onClick={onClose} className="btn btn-ghost !h-8 !w-8 !justify-center !px-0">
            <X size={15} />
          </button>
        </div>

        {/* Strategy selector */}
        <div className="flex items-center gap-1 border-b border-border px-4 py-2">
          <span className="mr-2 text-xs text-muted shrink-0">生成策略</span>
          {(Object.entries(STRATEGY_META) as [TkStrategy, typeof STRATEGY_META.template][]).map(([key, meta]) => {
            const Icon = meta.icon;
            return (
              <button
                key={key}
                type="button"
                title={meta.desc}
                onClick={() => {
                  setStrategy(key);
                  setScript('');
                  generate({ strat: key });
                }}
                className={`flex h-7 items-center gap-1.5 rounded px-3 text-xs font-semibold transition-colors ${
                  strategy === key ? 'bg-accent text-white' : 'bg-elev2 text-muted hover:text-text'
                }`}
              >
                <Icon size={11} /> {meta.label}
              </button>
            );
          })}
        </div>

        {/* Commission + prompt row */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
          <span className="text-xs text-muted shrink-0">佣金</span>
          <div className="flex gap-1">
            {COMMISSION_OPTIONS.map((pct) => (
              <button
                key={pct}
                type="button"
                onClick={() => { setCommission(pct); generate({ comm: pct }); }}
                className={`h-7 rounded px-2.5 text-xs font-semibold transition-colors ${
                  commission === pct ? 'bg-accent text-white' : 'bg-elev2 text-muted hover:text-text'
                }`}
              >
                {pct}%
              </button>
            ))}
          </div>

          {strategy !== 'template' && (
            <button
              type="button"
              onClick={() => setShowPromptEditor((v) => !v)}
              className="ml-auto btn btn-ghost !h-7 text-xs"
            >
              {showPromptEditor ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              自定义提示词
            </button>
          )}

          {gen.isPending && <RefreshCw size={13} className="animate-spin text-muted" style={{ marginLeft: strategy === 'template' ? 'auto' : undefined }} />}
        </div>

        {/* Prompt editor — AI / Hybrid only */}
        {strategy !== 'template' && showPromptEditor && (
          <div className="border-b border-border bg-elev1/40 px-4 py-3 space-y-2">
            {/* Saved prompts row */}
            {savedPrompts.length > 0 && (
              <div className="flex items-center gap-2">
                <select
                  value={selectedPromptId}
                  onChange={(e) => onSelectPrompt(e.target.value)}
                  className="flex-1 h-8 rounded border border-border bg-elev1 px-2 text-xs text-text"
                >
                  <option value="">— 选择已保存的提示词 —</option>
                  {savedPrompts.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                {selectedPromptId && (
                  <button
                    type="button"
                    onClick={() => onDeletePrompt(selectedPromptId)}
                    className="btn btn-ghost !h-8 !w-8 !justify-center !px-0 text-bad"
                    title="删除这个提示词"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            )}

            <textarea
              value={customPrompt}
              onChange={(e) => { setCustomPrompt(e.target.value); setSelectedPromptId(''); }}
              rows={5}
              placeholder={strategy === 'ai'
                ? '在这里写完整的 System Prompt，AI 会按这个提示词生成整封话术…'
                : '在这里写 AI 开场白的提示词，系统会把它用于生成个性化开场（品牌框架固定）…'}
              className="w-full resize-none rounded border border-border bg-elev1 p-2.5 text-xs leading-relaxed text-text outline-none placeholder:text-muted font-mono"
            />

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => generate()}
                disabled={gen.isPending}
                className="btn btn-primary !h-7 text-xs disabled:opacity-50"
              >
                <RefreshCw size={11} className={gen.isPending ? 'animate-spin' : ''} /> 用此提示词生成
              </button>

              <button
                type="button"
                onClick={() => setShowSaveForm((v) => !v)}
                className="btn !h-7 text-xs"
              >
                <BookmarkPlus size={11} /> 保存提示词
              </button>
            </div>

            {showSaveForm && (
              <div className="flex gap-2">
                <input
                  value={savePromptName}
                  onChange={(e) => setSavePromptName(e.target.value)}
                  placeholder="提示词名称…"
                  className="flex-1 h-8 rounded border border-border bg-elev1 px-2.5 text-xs text-text outline-none"
                />
                <button
                  type="button"
                  onClick={onSavePrompt}
                  disabled={!savePromptName.trim() || !customPrompt.trim() || createPrompt.isPending}
                  className="btn btn-primary !h-8 text-xs disabled:opacity-50"
                >
                  {createPrompt.isPending ? <RefreshCw size={11} className="animate-spin" /> : '保存'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Creator context — collapsible */}
        {hasPersonalization && (
          <div className="border-b border-border">
            <button
              type="button"
              onClick={() => setShowContext((v) => !v)}
              className="flex w-full items-center gap-2 px-4 py-2 text-xs text-muted hover:text-text"
            >
              {showContext ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              <span>已引用的达人数据</span>
              <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
                {[contextUsed.bio_excerpt, contextUsed.video_title, contextUsed.matched_keywords].filter(Boolean).length} 项
              </span>
            </button>

            {showContext && (
              <div className="grid gap-2 px-4 pb-3 text-xs">
                {contextUsed.video_title && (
                  <div className="flex gap-2">
                    <span className="w-20 shrink-0 text-muted">视频标题</span>
                    <span className="text-text">「{contextUsed.video_title}」</span>
                  </div>
                )}
                {contextUsed.bio_excerpt && (
                  <div className="flex gap-2">
                    <span className="w-20 shrink-0 text-muted">Bio 摘录</span>
                    <span className="text-text">「{contextUsed.bio_excerpt}」</span>
                  </div>
                )}
                {contextUsed.matched_keywords && (
                  <div className="flex gap-2">
                    <span className="w-20 shrink-0 text-muted">命中关键词</span>
                    <span className="text-text">{contextUsed.matched_keywords}</span>
                  </div>
                )}
                {contextUsed.recommendation_reason && (
                  <div className="flex gap-2">
                    <span className="w-20 shrink-0 text-muted">推荐理由</span>
                    <span className="text-text">{contextUsed.recommendation_reason}</span>
                  </div>
                )}
                {contextUsed.product_label && (
                  <div className="flex gap-2">
                    <span className="w-20 shrink-0 text-muted">匹配产品</span>
                    <span className="text-text">{contextUsed.product_label}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Script body */}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {gen.error ? (
            <div className="text-xs text-bad">{String((gen.error as any)?.message || '生成失败，请重试')}</div>
          ) : (
            <textarea
              readOnly
              value={script}
              rows={14}
              className="w-full resize-none rounded border border-border bg-elev1 p-3 font-mono text-xs leading-relaxed text-text outline-none"
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3">
          <button
            type="button"
            onClick={() => { setScript(''); generate(); }}
            disabled={gen.isPending}
            className="btn text-xs disabled:opacity-50"
          >
            <RefreshCw size={12} className={gen.isPending ? 'animate-spin' : ''} /> 重新生成
          </button>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="btn text-xs">关闭</button>
            <button
              type="button"
              onClick={onCopy}
              disabled={!script}
              className="btn btn-primary text-xs disabled:opacity-50"
            >
              {copied ? <><Check size={13} /> 已复制</> : <><Copy size={13} /> 复制话术</>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
