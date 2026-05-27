import { useEffect, useMemo, useState } from 'react';
import {
  AlertOctagon,
  AlignCenter,
  AlignLeft,
  AlignRight,
  ArrowRight,
  CheckCircle2,
  History,
  Image as ImageIcon,
  Mail,
  Package,
  RefreshCw,
  Save,
  Send,
  Sparkles,
  Trash2,
  UploadCloud,
  Wand2,
} from 'lucide-react';
import { SideDrawer } from '@/components/drawer/SideDrawer';
import { Pill } from '@/components/Pill';
import {
  useCreateDraft,
  useCreateProductAsset,
  useDeleteProductAsset,
  useGenerateTkScript,
  useGmailAccounts,
  useGmailDeleteAccount,
  useGmailStatus,
  useOutreachHistory,
  usePatchDraft,
  useProductAssets,
  useSendDraft,
} from '@/hooks/useApi';
import { shortRelative } from '@/lib/format';
import type { Creator, ProductAsset, TkStrategy } from '@/api/types';

interface Props {
  creator: Creator | null;
  open: boolean;
  onClose: () => void;
}

type Step = 'template' | 'preview' | 'edit' | 'sent';
type EmailImagePosition = 'top' | 'after_intro' | 'bottom';
type EmailImageAlign = 'left' | 'center' | 'right';

const PRODUCT_OPTIONS = [
  { key: 'feminine_care', label: '女性护理', hint: '护垫、经期护理、日常私护' },
  { key: 'baby_care', label: '婴儿护理', hint: '纸尿裤、母婴日常护理' },
  { key: 'adult_care', label: '成人护理', hint: '成人失禁、日常防护' },
  { key: 'pet_care', label: '宠物护理', hint: '宠物尿垫、宠物纸尿裤' },
  { key: 'all', label: '全品类', hint: '未确定 SKU 时使用' },
];

const STRATEGIES: Array<{ key: TkStrategy; label: string; desc: string }> = [
  { key: 'ai', label: 'AI 全生成', desc: '直接按达人资料和 SKU 写完整话术' },
  { key: 'hybrid', label: '混合', desc: '固定品牌框架，AI 写个性化开头' },
  { key: 'template', label: '模板', desc: '不调用 AI，快速套用结构化话术' },
];

const COMMISSIONS = [20];
const IMAGE_POSITIONS: Array<{ key: EmailImagePosition; label: string }> = [
  { key: 'top', label: '正文开头' },
  { key: 'after_intro', label: '第一段后' },
  { key: 'bottom', label: '正文结尾' },
];
const DEFAULT_EMAIL_IMAGE_POSITION: EmailImagePosition = 'top';

function productLabel(key?: string | null) {
  return PRODUCT_OPTIONS.find((item) => item.key === key)?.label || key || '未分类';
}

function splitList(value: string) {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function alignMargin(align: EmailImageAlign) {
  if (align === 'left') return '0 auto 0 0';
  if (align === 'right') return '0 0 0 auto';
  return '0 auto';
}

function textToEmailParagraphs(value: string) {
  const parts = value
    .trim()
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return [''];
  return parts.map((part) => (
    `<p style="margin:0 0 16px 0;color:#111827;font:14px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">${escapeHtml(part).replace(/\n/g, '<br />')}</p>`
  ));
}

function buildEmailImageBlock(
  asset: ProductAsset,
  options: {
    align: EmailImageAlign;
    caption: string;
    width: number;
  },
) {
  if (!asset.image_url) return '';
  const width = Math.max(180, Math.min(680, Number(options.width) || 520));
  const caption = options.caption.trim();
  return [
    `<figure style="margin:18px 0 20px 0;text-align:${options.align};">`,
    `<img src="${escapeHtml(asset.image_url)}" alt="${escapeHtml(caption || asset.name)}" width="${width}" style="display:block;width:100%;max-width:${width}px;height:auto;margin:${alignMargin(options.align)};border:1px solid #e5e7eb;border-radius:12px;" data-x9-product-asset-id="${escapeHtml(asset.id)}" />`,
    caption
      ? `<figcaption style="margin-top:8px;color:#6b7280;font:12px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;text-align:${options.align};">${escapeHtml(caption)}</figcaption>`
      : '',
    '</figure>',
  ].join('');
}

function buildEmailHtml(
  value: string,
  asset: ProductAsset,
  options: {
    align: EmailImageAlign;
    caption: string;
    position: EmailImagePosition;
    width: number;
  },
) {
  const paragraphs = textToEmailParagraphs(value);
  const imageBlock = buildEmailImageBlock(asset, options);
  const content = [...paragraphs];
  if (imageBlock) {
    if (options.position === 'top') content.unshift(imageBlock);
    else if (options.position === 'bottom') content.push(imageBlock);
    else content.splice(Math.min(2, content.length), 0, imageBlock);
  }
  return `<div style="margin:0;padding:0;background:#ffffff;">${content.join('')}</div>`;
}

function fallbackSubject(creator: Creator, asset?: ProductAsset | null) {
  const name = creator.display_name || creator.handle || 'Creator';
  const product = asset?.name || productLabel(asset?.product_key) || 'X9';
  return `X9 x ${name} - ${product} collaboration`;
}

function formatError(error: any) {
  const detail = error?.body?.detail || error?.response?.data?.detail || error?.message || '操作失败，请稍后重试';
  return String(detail);
}

export function OutreachDrawer({ creator, open, onClose }: Props) {
  const [step, setStep] = useState<Step>('template');
  const [strategy, setStrategy] = useState<TkStrategy>('ai');
  const [commission, setCommission] = useState(20);
  const [selectedAssetId, setSelectedAssetId] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [includeProductImage, setIncludeProductImage] = useState(false);
  const [emailImagePosition, setEmailImagePosition] = useState<EmailImagePosition>(DEFAULT_EMAIL_IMAGE_POSITION);
  const [emailImageAlign, setEmailImageAlign] = useState<EmailImageAlign>('center');
  const [emailImageWidth, setEmailImageWidth] = useState(520);
  const [emailImageCaption, setEmailImageCaption] = useState('');
  const [draftId, setDraftId] = useState<string | null>(null);
  const [sentSummary, setSentSummary] = useState('');
  const [sendError, setSendError] = useState('');
  const [generationMeta, setGenerationMeta] = useState<{
    aiStatus?: string;
    productName?: string;
    productKey?: string;
  } | null>(null);

  const [assetFormOpen, setAssetFormOpen] = useState(false);
  const [assetName, setAssetName] = useState('');
  const [assetSku, setAssetSku] = useState('');
  const [assetProductKey, setAssetProductKey] = useState('feminine_care');
  const [assetPoints, setAssetPoints] = useState('');
  const [assetTargets, setAssetTargets] = useState('');
  const [assetImageDataUrl, setAssetImageDataUrl] = useState('');
  const [assetFileName, setAssetFileName] = useState('');
  const [assetError, setAssetError] = useState('');

  const gmailStatusQ = useGmailStatus();
  const accountsQ = useGmailAccounts();
  const assetsQ = useProductAssets(open && creator ? creator.id : undefined);
  const historyQ = useOutreachHistory(open && creator ? creator.id : undefined);
  const generateTk = useGenerateTkScript();
  const createAsset = useCreateProductAsset();
  const deleteAsset = useDeleteProductAsset();
  const createDraft = useCreateDraft();
  const patchDraft = usePatchDraft();
  const sendDraft = useSendDraft();
  const deleteGmail = useGmailDeleteAccount();

  const accounts = accountsQ.data?.items ?? [];
  const defaultAcc = accounts.find((a) => Boolean(a.is_default)) || accounts[0];
  const history = historyQ.data?.items ?? [];
  const productAssets = assetsQ.data?.items ?? [];
  const matchedAsset = assetsQ.data?.matched ?? null;
  const selectedAsset = useMemo(
    () => productAssets.find((item) => item.id === selectedAssetId) || matchedAsset || null,
    [matchedAsset, productAssets, selectedAssetId],
  );

  const gmailDiagnostics = gmailStatusQ.data?.diagnostics ?? [];
  const blockingGmailDiagnostic = gmailDiagnostics.find((item) => item.level === 'error') || gmailDiagnostics.find((item) => item.level === 'warn');
  const isPersistingDraft = createDraft.isPending || patchDraft.isPending;
  const isSending = isPersistingDraft || sendDraft.isPending;
  const hasGmailAccount = accounts.length > 0;
  const canSaveDraft = Boolean(toEmail.trim() && subject.trim() && body.trim());
  const canSendDraft = Boolean(hasGmailAccount && toEmail.trim() && subject.trim() && body.trim() && !isSending);
  const gmailReturnTo = typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '/';
  const gmailConnectHref = `/api/local/outreach/gmail/connect?return_to=${encodeURIComponent(gmailReturnTo)}`;
  const sendDisabledReason = !hasGmailAccount
    ? '请先连接 Gmail 账户'
    : !toEmail.trim()
      ? '请填写收件邮箱'
      : !subject.trim() || !body.trim()
        ? '请先生成或填写邮件内容'
        : '';

  useEffect(() => {
    if (!open || !creator) return;
    setStep('template');
    setStrategy('ai');
    setCommission(20);
    setSelectedAssetId('');
    setSubject('');
    setBody('');
    setToEmail(creator.email || '');
    setIncludeProductImage(false);
    setEmailImagePosition(DEFAULT_EMAIL_IMAGE_POSITION);
    setEmailImageAlign('center');
    setEmailImageWidth(520);
    setEmailImageCaption('');
    setDraftId(null);
    setSentSummary('');
    setSendError('');
    setGenerationMeta(null);
    setAssetFormOpen(false);
    resetAssetForm();
  }, [open, creator?.id]);

  useEffect(() => {
    if (!open || selectedAssetId || !matchedAsset?.id) return;
    setSelectedAssetId(matchedAsset.id);
  }, [matchedAsset?.id, open, selectedAssetId]);

  useEffect(() => {
    if (!open) return;
    if (selectedAsset?.image_url) {
      setIncludeProductImage(true);
    } else {
      setIncludeProductImage(false);
      setEmailImageCaption('');
    }
  }, [open, selectedAsset?.id, selectedAsset?.image_url, selectedAsset?.name]);

  const resetAssetForm = () => {
    setAssetName('');
    setAssetSku('');
    setAssetProductKey('feminine_care');
    setAssetPoints('');
    setAssetTargets('');
    setAssetImageDataUrl('');
    setAssetFileName('');
    setAssetError('');
  };

  const onAssetFileChange = (file?: File | null) => {
    setAssetError('');
    if (!file) {
      setAssetImageDataUrl('');
      setAssetFileName('');
      return;
    }
    if (!file.type.startsWith('image/')) {
      setAssetError('只能上传图片文件');
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setAssetError('图片不能超过 8MB');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setAssetImageDataUrl(String(reader.result || ''));
      setAssetFileName(file.name);
      if (!assetName.trim()) setAssetName(file.name.replace(/\.[^.]+$/, ''));
    };
    reader.onerror = () => setAssetError('图片读取失败，请重试');
    reader.readAsDataURL(file);
  };

  const onSaveAsset = () => {
    if (!assetName.trim()) {
      setAssetError('请填写 SKU 名称');
      return;
    }
    createAsset.mutate(
      {
        name: assetName.trim(),
        sku_code: assetSku.trim() || undefined,
        product_key: assetProductKey,
        selling_points: splitList(assetPoints),
        target_creator_types: splitList(assetTargets),
        image_data_url: assetImageDataUrl || undefined,
      },
      {
        onSuccess: (result) => {
          setSelectedAssetId(result.asset.id);
          setAssetFormOpen(false);
          resetAssetForm();
          assetsQ.refetch();
        },
        onError: (error) => setAssetError(formatError(error)),
      },
    );
  };

  const onDeleteAsset = (asset: ProductAsset) => {
    if (!confirm(`删除素材「${asset.name}」?`)) return;
    deleteAsset.mutate(asset.id, {
      onSuccess: () => {
        if (selectedAssetId === asset.id) setSelectedAssetId('');
        assetsQ.refetch();
      },
    });
  };

  const onGenerate = () => {
    if (!creator) return;
    setSendError('');
    generateTk.mutate(
      {
        creator_id: creator.id,
        commission,
        strategy,
        product_asset_id: selectedAsset?.id,
      },
      {
        onSuccess: (result) => {
          const asset = result.product_asset || selectedAsset;
          setSubject(result.subject || fallbackSubject(creator, asset));
          setBody(result.body || result.script || '');
          setGenerationMeta({
            aiStatus: result.ai_status,
            productName: asset?.name || result.context_used?.product_asset_name || result.context_used?.product_label,
            productKey: result.product_key,
          });
          setStep('preview');
        },
        onError: (error) => setSendError(formatError(error)),
      },
    );
  };

  const persistDraft = async () => {
    if (!creator) throw new Error('缺少达人信息');
    if (!toEmail.trim()) throw new Error('收件邮箱必填');
    if (!subject.trim() || !body.trim()) throw new Error('请先生成并确认邮件内容');
    const imageEnabled = Boolean(includeProductImage && selectedAsset?.image_url);
    const emailBody = imageEnabled
      ? buildEmailHtml(body, selectedAsset!, {
          align: emailImageAlign,
          caption: emailImageCaption,
          position: emailImagePosition,
          width: emailImageWidth,
        })
      : body;
    const bodyFormat = imageEnabled ? 'html' : 'plain';
    const payload = {
      creator_id: String(creator.id),
      to_email: toEmail.trim(),
      subject: subject.trim(),
      body: emailBody,
      body_format: bodyFormat as 'plain' | 'html',
    };
    if (!draftId) {
      const draft = await createDraft.mutateAsync(payload);
      setDraftId(draft.id);
      return draft.id;
    }
    await patchDraft.mutateAsync({
      id: draftId,
      body: { subject: subject.trim(), body: emailBody, body_format: bodyFormat, to_email: toEmail.trim() },
    });
    return draftId;
  };

  const onSaveDraft = async () => {
    setSendError('');
    try {
      await persistDraft();
      setStep('edit');
    } catch (error: any) {
      setSendError(formatError(error));
    }
  };

  const onSend = async () => {
    setSendError('');
    if (!defaultAcc) {
      setSendError('请先连接 Gmail 账户');
      return;
    }
    if (!confirm('确认发送此邮件?')) return;
    try {
      const persistedDraftId = await persistDraft();
      const sent = await sendDraft.mutateAsync({
        id: persistedDraftId,
        body: { confirm: true, update_creator_status: true, from_account_id: defaultAcc.id },
      });
      setSentSummary(`已发送 · 主题:${sent.subject} · 收件人:${sent.to_email}`);
      setStep('sent');
      historyQ.refetch();
    } catch (error: any) {
      setSendError(formatError(error));
    }
  };

  const onDisconnectGmail = () => {
    if (!defaultAcc) return;
    if (!confirm(`断开 ${defaultAcc.email} 后，此账号将无法继续用该 Gmail 发送邮件。确认断开?`)) return;
    deleteGmail.mutate(defaultAcc.id, { onSuccess: () => { accountsQ.refetch(); gmailStatusQ.refetch(); } });
  };

  const onReset = () => {
    setStep('template');
    setSubject('');
    setBody('');
    setDraftId(null);
    setSentSummary('');
    setSendError('');
    setGenerationMeta(null);
  };

  if (!creator) return null;

  const activeStrategy = STRATEGIES.find((item) => item.key === strategy);
  const selectedProductLabel = selectedAsset?.name || productLabel(selectedAsset?.product_key);
  const generationBusy = generateTk.isPending;
  const emailImageEnabled = Boolean(includeProductImage && selectedAsset?.image_url);
  const emailImagePreviewHtml = selectedAsset?.image_url
    ? buildEmailImageBlock(selectedAsset, {
        align: emailImageAlign,
        caption: emailImageCaption,
        width: emailImageWidth,
      })
    : '';

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      width={640}
      title={<span>外联 · @{creator.handle}</span>}
      subtitle={<span>{creator.display_name} · {creator.country || '地区未知'} · {creator.tier || '?'} 级 · 邮箱:{creator.email || '未知'}</span>}
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
                <button onClick={onGenerate} disabled={generationBusy} className="btn btn-primary">
                  {generationBusy ? <RefreshCw size={12} className="animate-spin" /> : <Wand2 size={12} />}
                  {generationBusy ? '生成中...' : '生成邮件预览'} <ArrowRight size={12} />
                </button>
              )}
              {(step === 'preview' || step === 'edit') && (
                <>
                  <button onClick={onSaveDraft} disabled={!canSaveDraft || isSending} className="btn">
                    <Save size={12} />{isPersistingDraft ? '保存中...' : '保存草稿'}
                  </button>
                  <button onClick={onSend} disabled={!canSendDraft} className="btn btn-primary">
                    <Send size={12} />{isSending ? '发送中...' : draftId ? '发送' : '保存并发送'}
                  </button>
                </>
              )}
            </>
          )}
        </>
      }
    >
      {accounts.length === 0 ? (
        <div className="card card-body mb-3" style={{ background: 'rgb(var(--warn) / 0.12)' }}>
          <div className="flex items-start gap-2 text-xs text-warn">
            <AlertOctagon size={14} className="mt-0.5 shrink-0" />
            <div className="min-w-0">
              <div>还没绑定 Gmail 账户 · 请先 <a href={gmailConnectHref} className="underline font-medium">连接 Gmail</a> 后再发送</div>
              <div className="text-xxs mt-1 opacity-90">授权后系统会把该 Gmail 绑定到当前登录账号，仅在你确认发送时调用 Gmail API。</div>
              {blockingGmailDiagnostic?.message && (
                <div className="mt-2 rounded border border-warn/40 px-2 py-1.5 text-xxs">
                  <div>{blockingGmailDiagnostic.message}</div>
                  {blockingGmailDiagnostic.action && <div className="mt-1 opacity-90">{blockingGmailDiagnostic.action}</div>}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-xxs text-muted mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Mail size={11} className="shrink-0" />
            <span>发件账户:</span><span className="text-text font-medium truncate">{defaultAcc?.email}</span>
          </div>
          <button type="button" onClick={onDisconnectGmail} disabled={deleteGmail.isPending} className="underline shrink-0">
            {deleteGmail.isPending ? '断开中...' : '断开'}
          </button>
        </div>
      )}

      {(sendDisabledReason || sendError || generateTk.error) && step !== 'sent' && (
        <div className={`mb-3 rounded-md border px-3 py-2 text-xs ${
          sendError || generateTk.error ? 'border-bad/40 bg-bad/10 text-bad' : 'border-border bg-elev2 text-muted'
        }`}>
          {sendError || (generateTk.error ? formatError(generateTk.error) : sendDisabledReason)}
        </div>
      )}

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
                {['生成预览', '预览', '编辑发送', '已发送'][i]}
              </span>
              {i < 3 && <span className="text-muted">›</span>}
            </div>
          );
        })}
      </div>

      {step === 'template' && (
        <div className="space-y-4">
          <section className="rounded-md border border-border bg-elev1/70 p-3">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-white">
                <Sparkles size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">AI 邀约话术生成</h3>
                  {matchedAsset && (
                    <span className="chip text-xxs">自动匹配: {matchedAsset.name}</span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted">新话术会直接替换旧模板预览，并写入后续邮件正文。图片/SKU 素材保存在本机，后续可复用。</p>
              </div>
            </div>
          </section>

          <section className="rounded-md border border-border bg-elev1/60 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Package size={14} className="text-accent" />
                <h3 className="text-xs font-semibold">产品 SKU / 图片素材</h3>
              </div>
              <button type="button" className="btn btn-ghost !h-7 text-xs" onClick={() => setAssetFormOpen((v) => !v)}>
                <UploadCloud size={12} />上传图片
              </button>
            </div>

            {selectedAsset ? (
              <div className="mb-3 grid grid-cols-[64px_minmax(0,1fr)] gap-3 rounded-md border border-accent/35 bg-accent/10 p-2">
                <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded border border-border bg-elev2">
                  {selectedAsset.image_url ? (
                    <img src={selectedAsset.image_url} alt={selectedAsset.name} className="h-full w-full object-cover" />
                  ) : (
                    <ImageIcon size={18} className="text-muted" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{selectedAsset.name}</span>
                    <span className="chip text-xxs">{productLabel(selectedAsset.product_key)}</span>
                    <button
                      type="button"
                      onClick={() => onDeleteAsset(selectedAsset)}
                      disabled={deleteAsset.isPending}
                      className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded text-muted hover:bg-bad/10 hover:text-bad"
                      title="删除素材"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                  <div className="mt-1 text-xxs text-muted">{selectedAsset.sku_code || '未填写 SKU 编码'}</div>
                  {(selectedAsset.selling_points ?? []).length > 0 && (
                    <div className="mt-1 line-clamp-2 text-xs text-muted">{selectedAsset.selling_points?.join(' · ')}</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="mb-3 rounded-md border border-dashed border-border p-3 text-xs text-muted">
                暂无已选 SKU。可以上传产品图，也可以先用达人品类自动生成。
              </div>
            )}

            {productAssets.length > 0 && (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {productAssets.map((asset) => {
                  const selected = asset.id === selectedAsset?.id;
                  return (
                    <button
                      key={asset.id}
                      type="button"
                      onClick={() => setSelectedAssetId(asset.id)}
                      className={`group flex min-h-[72px] items-center gap-2 rounded-md border p-2 text-left transition-colors ${
                        selected ? 'border-accent bg-accent/10' : 'border-border bg-elev2/50 hover:border-accent/60'
                      }`}
                    >
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded border border-border bg-elev1">
                        {asset.image_url ? (
                          <img src={asset.image_url} alt={asset.name} className="h-full w-full object-cover" />
                        ) : (
                          <ImageIcon size={15} className="text-muted" />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-semibold">{asset.name}</span>
                        <span className="mt-0.5 block truncate text-xxs text-muted">{asset.sku_code || productLabel(asset.product_key)}</span>
                      </span>
                      {selected ? <CheckCircle2 size={14} className="text-accent" /> : null}
                    </button>
                  );
                })}
              </div>
            )}

            {assetFormOpen && (
              <div className="mt-3 rounded-md border border-border bg-elev2/50 p-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-[96px_minmax(0,1fr)]">
                  <label className="flex h-24 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-border bg-elev1 text-xxs text-muted hover:border-accent">
                    {assetImageDataUrl ? (
                      <img src={assetImageDataUrl} alt={assetFileName} className="h-full w-full rounded-md object-cover" />
                    ) : (
                      <>
                        <UploadCloud size={18} />
                        <span>选择图片</span>
                      </>
                    )}
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(event) => onAssetFileChange(event.target.files?.[0])}
                    />
                  </label>
                  <div className="grid gap-2">
                    <input
                      value={assetName}
                      onChange={(event) => setAssetName(event.target.value)}
                      className="input-bare rounded border border-border px-3 py-2 text-xs"
                      style={{ background: 'rgb(var(--bg-elev-2))' }}
                      placeholder="SKU 名称，例如 Organic Cotton Pads"
                    />
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <input
                        value={assetSku}
                        onChange={(event) => setAssetSku(event.target.value)}
                        className="input-bare rounded border border-border px-3 py-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))' }}
                        placeholder="SKU 编码"
                      />
                      <select
                        value={assetProductKey}
                        onChange={(event) => setAssetProductKey(event.target.value)}
                        className="rounded border border-border px-3 py-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}
                      >
                        {PRODUCT_OPTIONS.map((item) => (
                          <option key={item.key} value={item.key}>{item.label}</option>
                        ))}
                      </select>
                    </div>
                    <textarea
                      value={assetPoints}
                      onChange={(event) => setAssetPoints(event.target.value)}
                      rows={2}
                      className="input-bare resize-none rounded border border-border px-3 py-2 text-xs"
                      style={{ background: 'rgb(var(--bg-elev-2))' }}
                      placeholder="卖点，用逗号分隔，例如 soft, breathable, leak protection"
                    />
                    <input
                      value={assetTargets}
                      onChange={(event) => setAssetTargets(event.target.value)}
                      className="input-bare rounded border border-border px-3 py-2 text-xs"
                      style={{ background: 'rgb(var(--bg-elev-2))' }}
                      placeholder="匹配达人类型，例如 wellness, mom, pet"
                    />
                  </div>
                </div>
                {assetError && <div className="mt-2 text-xxs text-bad">{assetError}</div>}
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="min-w-0 text-xxs text-muted">{assetFileName || '图片可选，填写 SKU 和卖点也能参与匹配'}</div>
                  <div className="flex gap-2">
                    <button type="button" className="btn btn-ghost !h-8 text-xs" onClick={resetAssetForm}>清空</button>
                    <button type="button" className="btn btn-primary !h-8 text-xs" onClick={onSaveAsset} disabled={createAsset.isPending}>
                      {createAsset.isPending ? <RefreshCw size={12} className="animate-spin" /> : <Save size={12} />}
                      保存素材
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="rounded-md border border-border bg-elev1/60 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Wand2 size={14} className="text-accent" />
              <h3 className="text-xs font-semibold">生成设置</h3>
              <span className="text-xxs text-muted">{activeStrategy?.desc}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {STRATEGIES.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`h-8 rounded px-3 text-xs font-semibold transition-colors ${
                    strategy === item.key ? 'bg-accent text-white' : 'bg-elev2 text-muted hover:text-text'
                  }`}
                  onClick={() => setStrategy(item.key)}
                  title={item.desc}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-xs text-muted">佣金</span>
              {COMMISSIONS.map((pct) => (
                <button
                  key={pct}
                  type="button"
                  onClick={() => setCommission(pct)}
                  className={`h-7 rounded px-2.5 text-xs font-semibold ${
                    commission === pct ? 'bg-accent text-white' : 'bg-elev2 text-muted hover:text-text'
                  }`}
                >
                  {pct}%
                </button>
              ))}
            </div>
          </section>
        </div>
      )}

      {(step === 'preview' || step === 'edit') && (
        <div className="space-y-3">
          {generationMeta && (
            <div className="rounded-md border border-border bg-elev1/70 px-3 py-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">已替换为 AI 邀约话术</span>
                <span className="chip text-xxs">{generationMeta.aiStatus || 'generated'}</span>
                {generationMeta.productName && <span className="chip text-xxs">{generationMeta.productName}</span>}
              </div>
              <div className="mt-1 text-xxs text-muted">仍可手动编辑正文，保存草稿或直接保存并发送。</div>
            </div>
          )}
          <div>
            <label className="text-xxs text-muted block mb-1">收件人</label>
            <input
              value={toEmail}
              onChange={(event) => setToEmail(event.target.value)}
              className="input-bare w-full rounded border border-border px-3 py-2"
              style={{ background: 'rgb(var(--bg-elev-2))' }}
              placeholder="contact@example.com"
            />
          </div>
          <div>
            <label className="text-xxs text-muted block mb-1">主题</label>
            <input
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="input-bare w-full rounded border border-border px-3 py-2"
              style={{ background: 'rgb(var(--bg-elev-2))' }}
            />
          </div>
          <section className="rounded-md border border-border bg-elev1/60 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <ImageIcon size={14} className="text-accent" />
                  <h3 className="text-xs font-semibold">邮件图片</h3>
                  {emailImageEnabled && <span className="chip text-xxs">将作为 inline 图片发送</span>}
                </div>
                <p className="mt-1 text-xxs text-muted">保存或发送时会把 SKU 图片插入邮件正文；本地图片会转换为 Gmail 内联图片，收件人可以直接看到。</p>
              </div>
              <label className={`inline-flex h-8 shrink-0 items-center gap-2 rounded border px-2.5 text-xs ${
                selectedAsset?.image_url ? 'cursor-pointer border-border bg-elev2 text-text' : 'cursor-not-allowed border-border bg-elev2/50 text-muted'
              }`}>
                <input
                  type="checkbox"
                  checked={includeProductImage}
                  disabled={!selectedAsset?.image_url}
                  onChange={(event) => setIncludeProductImage(event.target.checked)}
                />
                插入图片
              </label>
            </div>

            {selectedAsset?.image_url ? (
              <div className="mt-3 grid gap-3 lg:grid-cols-[148px_minmax(0,1fr)]">
                <div className="overflow-hidden rounded-md border border-border bg-elev2">
                  <img src={selectedAsset.image_url} alt={selectedAsset.name} className="h-32 w-full object-cover" />
                  <div className="border-t border-border px-2 py-1.5">
                    <div className="truncate text-xs font-semibold">{selectedAsset.name}</div>
                    <div className="truncate text-xxs text-muted">{selectedAsset.sku_code || selectedProductLabel}</div>
                  </div>
                </div>
                <div className="min-w-0 space-y-3">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="space-y-1">
                      <span className="text-xxs text-muted">插入位置</span>
                      <select
                        value={emailImagePosition}
                        onChange={(event) => setEmailImagePosition(event.target.value as EmailImagePosition)}
                        disabled={!includeProductImage}
                        className="h-9 w-full rounded border border-border px-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}
                      >
                        {IMAGE_POSITIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                      </select>
                    </label>
                    <label className="space-y-1">
                      <span className="text-xxs text-muted">图片说明</span>
                      <input
                        value={emailImageCaption}
                        onChange={(event) => setEmailImageCaption(event.target.value)}
                        disabled={!includeProductImage}
                        className="input-bare h-9 w-full rounded border border-border px-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))' }}
                        placeholder={selectedAsset.name}
                      />
                    </label>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_132px]">
                    <label className="space-y-1">
                      <span className="flex items-center justify-between text-xxs text-muted">
                        <span>显示宽度</span>
                        <span>{emailImageWidth}px</span>
                      </span>
                      <input
                        type="range"
                        min={240}
                        max={640}
                        step={20}
                        value={emailImageWidth}
                        disabled={!includeProductImage}
                        onChange={(event) => setEmailImageWidth(Number(event.target.value))}
                        className="w-full accent-[rgb(var(--accent))]"
                      />
                    </label>
                    <div className="space-y-1">
                      <span className="block text-xxs text-muted">对齐</span>
                      <div className="grid grid-cols-3 gap-1">
                        {([
                          ['left', AlignLeft],
                          ['center', AlignCenter],
                          ['right', AlignRight],
                        ] as Array<[EmailImageAlign, typeof AlignLeft]>).map(([align, Icon]) => (
                          <button
                            key={align}
                            type="button"
                            onClick={() => setEmailImageAlign(align)}
                            disabled={!includeProductImage}
                            className={`inline-flex h-9 items-center justify-center rounded border ${
                              emailImageAlign === align ? 'border-accent bg-accent text-white' : 'border-border bg-elev2 text-muted hover:text-text'
                            }`}
                            title={align}
                          >
                            <Icon size={14} />
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  {includeProductImage && emailImagePreviewHtml && (
                    <div className="rounded-md border border-border bg-white p-3">
                      <div dangerouslySetInnerHTML={{ __html: emailImagePreviewHtml }} />
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-border p-3 text-xs text-muted">
                <span>当前 SKU 没有图片。回到上一步上传图片后，这里就可以插入并调整。</span>
                <button type="button" className="btn btn-ghost !h-8 text-xs" onClick={() => setStep('template')}>
                  <UploadCloud size={12} /> 上传图片
                </button>
              </div>
            )}
          </section>
          <div>
            <label className="text-xxs text-muted block mb-1">正文</label>
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={14}
              className="input-bare w-full resize-y rounded border border-border px-3 py-2 font-mono text-xs"
              style={{ background: 'rgb(var(--bg-elev-2))' }}
            />
          </div>
          {generationBusy && (
            <div className="text-xxs text-muted flex items-center gap-1"><RefreshCw size={11} className="animate-spin" />生成中...</div>
          )}
          {draftId && <div className="text-xxs text-muted">草稿 ID: {draftId}</div>}
        </div>
      )}

      {step === 'sent' && (
        <div className="card card-body" style={{ background: 'rgb(var(--good) / 0.12)' }}>
          <div className="flex items-center gap-2 text-good">
            <Send size={14} />
            <span className="text-sm font-medium">发送成功</span>
          </div>
          <div className="text-xxs text-muted mt-2">{sentSummary}</div>
        </div>
      )}

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
                <div className="text-muted mt-0.5">{h.to_email} · {shortRelative(h.sent_at || h.created_at)} · {h.from_email || '未发送'}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </SideDrawer>
  );
}
