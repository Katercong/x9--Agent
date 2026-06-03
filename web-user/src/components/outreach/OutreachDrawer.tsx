import { useEffect, useMemo, useRef, useState } from 'react';
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
import { PaginationControls } from '@/components/PaginationControls';
import {
  useCreateDraft,
  useCreateProductAsset,
  useDeleteProductAsset,
  useGenerateTkScript,
  useGmailAccounts,
  useGmailDeleteAccount,
  useGmailStatus,
  useAcquireOutreachLock,
  useHeartbeatOutreachLock,
  useOutreachHistory,
  usePatchDraft,
  useProductAssets,
  useReleaseOutreachLock,
  useSendDraft,
} from '@/hooks/useApi';
import { shortRelative } from '@/lib/format';
import { formatRelativeTime, type Language } from '@/lib/i18n';
import type { Creator, CreatorOutreachLock, OutreachHistoryItem, ProductAsset, TkStrategy } from '@/api/types';
import { useUiStore } from '@/stores/uiStore';

interface Props {
  creator: Creator | null;
  open: boolean;
  onClose: () => void;
  initialLock?: CreatorOutreachLock | null;
}

type Step = 'template' | 'preview' | 'edit' | 'sent';
type EmailImagePosition = 'top' | 'after_intro' | 'bottom';
type EmailImageAlign = 'left' | 'center' | 'right';

const PRODUCT_OPTIONS = [
  { key: 'feminine_care', zh: '女性护理', en: 'Feminine Care', hintZh: '护垫、经期护理、日常私护', hintEn: 'Pads, period care, daily feminine care' },
  { key: 'baby_care', zh: '婴儿护理', en: 'Baby Care', hintZh: '纸尿裤、母婴日常护理', hintEn: 'Diapers and daily baby care' },
  { key: 'adult_care', zh: '成人护理', en: 'Adult Care', hintZh: '成人失禁、日常防护', hintEn: 'Adult incontinence and daily protection' },
  { key: 'pet_care', zh: '宠物护理', en: 'Pet Care', hintZh: '宠物尿垫、宠物纸尿裤', hintEn: 'Pet pads and pet diapers' },
  { key: 'all', zh: '全品类', en: 'All Categories', hintZh: '未确定 SKU 时使用', hintEn: 'Use when SKU is not decided' },
];

const STRATEGIES: Array<{ key: TkStrategy; zh: string; en: string; descZh: string; descEn: string }> = [
  { key: 'ai', zh: 'AI 全生成', en: 'AI Full Draft', descZh: '直接按达人资料和 SKU 写完整话术', descEn: 'Write the full pitch from creator profile and SKU' },
  { key: 'hybrid', zh: '混合', en: 'Hybrid', descZh: '固定品牌框架，AI 写个性化开头', descEn: 'Keep brand structure and let AI personalize the opening' },
  { key: 'template', zh: '模板', en: 'Template', descZh: '不调用 AI，快速套用结构化话术', descEn: 'Use the structured template without AI' },
];

const COMMISSIONS = [20];
const HISTORY_PAGE_SIZE = 10;
const IMAGE_POSITIONS: Array<{ key: EmailImagePosition; zh: string; en: string }> = [
  { key: 'top', zh: '正文开头', en: 'Top of email' },
  { key: 'after_intro', zh: '第一段后', en: 'After first paragraph' },
  { key: 'bottom', zh: '正文结尾', en: 'End of email' },
];
const DEFAULT_EMAIL_IMAGE_POSITION: EmailImagePosition = 'top';

const copy = {
  zh: {
    outreachTitle: '外联',
    unknownRegion: '地区未知',
    level: '级',
    email: '邮箱',
    unknown: '未知',
    cancel: '取消',
    again: '再来一封',
    done: '完成',
    generating: '生成中...',
    generatePreview: '生成邮件预览',
    saving: '保存中...',
    saveDraft: '保存草稿',
    sending: '发送中...',
    send: '发送',
    saveAndSend: '保存并发送',
    connectGmailFirst: '请先连接 Gmail 账户',
    fillRecipient: '请填写收件邮箱',
    fillContent: '请先生成或填写邮件内容',
    noGmail: '还没绑定 Gmail 账户',
    connectGmail: '连接 Gmail',
    gmailHelp: '授权后系统会把该 Gmail 绑定到当前登录账号，仅在你确认发送时调用 Gmail API。',
    senderAccount: '发件账户',
    disconnecting: '断开中...',
    disconnect: '断开',
    steps: ['生成预览', '预览', '编辑发送', '已发送'],
    aiTitle: 'AI 邀约话术生成',
    autoMatch: '自动匹配',
    aiDesc: '新话术会直接替换旧模板预览，并写入后续邮件正文。图片/SKU 素材保存在本机，后续可复用。',
    assetsTitle: '产品 SKU / 图片素材',
    uploadImage: '上传图片',
    deleteAsset: '删除素材',
    skuMissing: '未填写 SKU 编码',
    noSelectedSku: '暂无已选 SKU。可以上传产品图，也可以先用达人品类自动生成。',
    chooseImage: '选择图片',
    skuNamePlaceholder: 'SKU 名称，例如 Organic Cotton Pads',
    skuCodePlaceholder: 'SKU 编码',
    sellingPointsPlaceholder: '卖点，用逗号分隔，例如 soft, breathable, leak protection',
    targetTypesPlaceholder: '匹配达人类型，例如 wellness, mom, pet',
    imageOptional: '图片可选，填写 SKU 和卖点也能参与匹配',
    clear: '清空',
    saveAsset: '保存素材',
    settings: '生成设置',
    commission: '佣金',
    aiReplaced: '已替换为 AI 邀约话术',
    editableAfterAi: '仍可手动编辑正文，保存草稿或直接保存并发送。',
    recipient: '收件人',
    subject: '主题',
    emailImage: '邮件图片',
    inlineImage: '将作为 inline 图片发送',
    emailImageHelp: '保存或发送时会把 SKU 图片插入邮件正文；本地图片会转换为 Gmail 内联图片，收件人可以直接看到。',
    insertImage: '插入图片',
    position: '插入位置',
    caption: '图片说明',
    width: '显示宽度',
    align: '对齐',
    currentSkuNoImage: '当前 SKU 没有图片。回到上一步上传图片后，这里就可以插入并调整。',
    body: '正文',
    draftId: '草稿 ID',
    sentOk: '发送成功',
    historyTitle: '历史外联记录',
    total: '共',
    records: '条',
    noHistory: '还没有给这位达人发过邮件',
    review: '复查',
    apply: '套用',
    close: '关闭',
    reviewTitle: '邮件正文复查',
    noBody: '无正文内容',
    notSent: '未发送',
    onlyImage: '只能上传图片文件',
    imageTooLarge: '图片不能超过 8MB',
    imageReadFailed: '图片读取失败，请重试',
    skuNameRequired: '请填写 SKU 名称',
    missingCreator: '缺少达人信息',
    recipientRequired: '收件邮箱必填',
    confirmSend: '确认发送此邮件?',
    sentSummary: '已发送',
    disconnectConfirmPrefix: '断开',
    disconnectConfirmSuffix: '后，此账号将无法继续用该 Gmail 发送邮件。确认断开?',
    htmlConverted: '已将历史 HTML 邮件转成可编辑文本，请复查后再发送',
    operationFailed: '操作失败，请稍后重试',
    unclassified: '未分类',
  },
  en: {
    outreachTitle: 'Outreach',
    unknownRegion: 'Unknown Region',
    level: 'tier',
    email: 'Email',
    unknown: 'Unknown',
    cancel: 'Cancel',
    again: 'Another Email',
    done: 'Done',
    generating: 'Generating...',
    generatePreview: 'Generate Preview',
    saving: 'Saving...',
    saveDraft: 'Save Draft',
    sending: 'Sending...',
    send: 'Send',
    saveAndSend: 'Save and Send',
    connectGmailFirst: 'Connect a Gmail account first',
    fillRecipient: 'Enter recipient email',
    fillContent: 'Generate or write the email first',
    noGmail: 'No Gmail account connected',
    connectGmail: 'Connect Gmail',
    gmailHelp: 'After authorization, this Gmail is linked to the current account and only used when you confirm sending.',
    senderAccount: 'Sender account',
    disconnecting: 'Disconnecting...',
    disconnect: 'Disconnect',
    steps: ['Generate Preview', 'Preview', 'Edit and Send', 'Sent'],
    aiTitle: 'AI Invite Draft',
    autoMatch: 'Auto matched',
    aiDesc: 'The new pitch replaces the old preview and becomes the email body. Images and SKU assets stay local for reuse.',
    assetsTitle: 'Product SKU / Image Assets',
    uploadImage: 'Upload Image',
    deleteAsset: 'Delete asset',
    skuMissing: 'SKU code not filled',
    noSelectedSku: 'No SKU selected. Upload a product image or let creator category pick one automatically.',
    chooseImage: 'Choose image',
    skuNamePlaceholder: 'SKU name, e.g. Organic Cotton Pads',
    skuCodePlaceholder: 'SKU code',
    sellingPointsPlaceholder: 'Selling points, comma separated, e.g. soft, breathable, leak protection',
    targetTypesPlaceholder: 'Creator types, e.g. wellness, mom, pet',
    imageOptional: 'Image is optional. SKU and selling points can still be matched.',
    clear: 'Clear',
    saveAsset: 'Save Asset',
    settings: 'Generation Settings',
    commission: 'Commission',
    aiReplaced: 'Replaced with AI invite draft',
    editableAfterAi: 'You can still edit the body, save as draft, or send directly.',
    recipient: 'Recipient',
    subject: 'Subject',
    emailImage: 'Email Image',
    inlineImage: 'Will be sent as an inline image',
    emailImageHelp: 'When saving or sending, the SKU image is inserted into the email. Local images are converted to Gmail inline images.',
    insertImage: 'Insert image',
    position: 'Position',
    caption: 'Caption',
    width: 'Display width',
    align: 'Align',
    currentSkuNoImage: 'The current SKU has no image. Go back and upload one to insert and adjust it here.',
    body: 'Body',
    draftId: 'Draft ID',
    sentOk: 'Sent successfully',
    historyTitle: 'Outreach History',
    total: 'Total',
    records: 'records',
    noHistory: 'No emails have been sent to this creator yet',
    review: 'Review',
    apply: 'Apply',
    close: 'Close',
    reviewTitle: 'Email Body Review',
    noBody: 'No body content',
    notSent: 'Not sent',
    onlyImage: 'Only image files can be uploaded',
    imageTooLarge: 'Image cannot exceed 8MB',
    imageReadFailed: 'Failed to read image. Try again.',
    skuNameRequired: 'Enter SKU name',
    missingCreator: 'Creator info is missing',
    recipientRequired: 'Recipient email is required',
    confirmSend: 'Send this email?',
    sentSummary: 'Sent',
    disconnectConfirmPrefix: 'Disconnect',
    disconnectConfirmSuffix: '? This account will no longer be able to send through this Gmail.',
    htmlConverted: 'Historical HTML email was converted to editable text. Review before sending.',
    operationFailed: 'Operation failed. Try again later.',
    unclassified: 'Unclassified',
  },
} satisfies Record<Language, Record<string, any>>;

function productLabel(key?: string | null, language: Language = 'zh') {
  return PRODUCT_OPTIONS.find((item) => item.key === key)?.[language] || key || copy[language].unclassified;
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
  const product = asset?.name || productLabel(asset?.product_key, 'en') || 'X9';
  return `X9 x ${name} - ${product} collaboration`;
}

function translateMessage(value: unknown, language: Language) {
  const text = String(value || '');
  if (language === 'zh' || !text) return text;
  if (text.includes('Gmail token 已加密')) return 'Gmail token is encrypted but currently uses fallback key material.';
  if (text.includes('生产环境请设置独立的 GMAIL_TOKEN_ENCRYPTION_KEY')) return 'Set a dedicated GMAIL_TOKEN_ENCRYPTION_KEY in production so OAuth secret rotation does not affect token decryption.';
  if (text.includes('字段级加密未启用')) return 'Gmail token field encryption is not enabled.';
  if (text.includes('连接 Gmail')) return copy.en.connectGmailFirst;
  return text;
}

function formatError(error: any, language: Language) {
  const detail = error?.body?.detail || error?.response?.data?.detail || error?.message || copy[language].operationFailed;
  return translateMessage(detail, language);
}

function relativeByLanguage(value: string | null | undefined, language: Language) {
  if (language === 'zh') return shortRelative(value);
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value || '—';
  return formatRelativeTime(value, language);
}

function lockExpiresMs(lock: CreatorOutreachLock | null | undefined): number {
  if (!lock?.expires_at) return 0;
  const ts = parseLockTimestamp(lock.expires_at);
  return Number.isFinite(ts) ? ts : 0;
}

function isLockFresh(lock: CreatorOutreachLock | null | undefined): lock is CreatorOutreachLock {
  return Boolean(lock?.id && lockExpiresMs(lock) > Date.now());
}

function parseLockTimestamp(value: string | null | undefined): number {
  const text = String(value || '').trim();
  if (!text) return Number.NaN;
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(text);
  return new Date(hasZone ? text : `${text.replace(' ', 'T')}Z`).getTime();
}

function lockExpiryText(lock: CreatorOutreachLock | null | undefined, language: Language): string {
  const ts = lockExpiresMs(lock);
  if (!Number.isFinite(ts)) return '—';
  return formatRelativeTime(new Date(ts).toISOString(), language);
}

function htmlToPlainText(value: string) {
  if (typeof window !== 'undefined' && 'DOMParser' in window) {
    const doc = new DOMParser().parseFromString(value, 'text/html');
    return (doc.body.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
  }
  return value
    .replace(/<(br|\/p|\/div|\/li)\b[^>]*>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function safeEmailHtml(value?: string | null) {
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>body{margin:0;padding:14px;background:#fff;color:#111827;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}img{max-width:100%;height:auto}</style></head><body>${value || ''}</body></html>`;
}

export function OutreachDrawer({ creator, open, onClose, initialLock = null }: Props) {
  const { language } = useUiStore();
  const t = copy[language];
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
  const [lockError, setLockError] = useState('');
  const [activeLock, setActiveLock] = useState<CreatorOutreachLock | null>(initialLock);
  const [reviewEmail, setReviewEmail] = useState<OutreachHistoryItem | null>(null);
  const [historyPage, setHistoryPage] = useState(0);
  const lockRequestKeyRef = useRef('');
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
  const historyQ = useOutreachHistory(
    open && creator ? creator.id : undefined,
    { limit: HISTORY_PAGE_SIZE, offset: historyPage * HISTORY_PAGE_SIZE },
  );
  const acquireLock = useAcquireOutreachLock();
  const heartbeatLock = useHeartbeatOutreachLock();
  const releaseLock = useReleaseOutreachLock();
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
  const historyTotal = historyQ.data?.total ?? history.length;
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
  const isLocking = false;
  const hasOutreachLock = true;
  const hasGmailAccount = accounts.length > 0;
  const canSaveDraft = Boolean(toEmail.trim() && subject.trim() && body.trim());
  const canSendDraft = Boolean(hasGmailAccount && toEmail.trim() && subject.trim() && body.trim() && !isSending);
  const gmailReturnTo = typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '/';
  const gmailConnectHref = `/api/local/outreach/gmail/connect?return_to=${encodeURIComponent(gmailReturnTo)}`;
  const sendDisabledReason = !hasGmailAccount
    ? t.connectGmailFirst
    : !toEmail.trim()
      ? t.fillRecipient
      : !subject.trim() || !body.trim()
        ? t.fillContent
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
    setLockError('');
    setReviewEmail(null);
    setHistoryPage(0);
    setActiveLock(null);
    lockRequestKeyRef.current = '';
    setGenerationMeta(null);
    setAssetFormOpen(false);
    resetAssetForm();
  }, [open, creator?.id, initialLock?.id]);

  useEffect(() => {
    if (!open || !creator) return;
    setLockError('');
    setActiveLock(null);
    lockRequestKeyRef.current = '';
  }, [creator, open]);

  useEffect(() => {
    return undefined;
  }, [open]);

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
      setAssetError(t.onlyImage);
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setAssetError(t.imageTooLarge);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setAssetImageDataUrl(String(reader.result || ''));
      setAssetFileName(file.name);
      if (!assetName.trim()) setAssetName(file.name.replace(/\.[^.]+$/, ''));
    };
    reader.onerror = () => setAssetError(t.imageReadFailed);
    reader.readAsDataURL(file);
  };

  const onSaveAsset = () => {
    if (!assetName.trim()) {
      setAssetError(t.skuNameRequired);
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
        onError: (error) => setAssetError(formatError(error, language)),
      },
    );
  };

  const onDeleteAsset = (asset: ProductAsset) => {
    if (!confirm(language === 'zh' ? `删除素材「${asset.name}」?` : `Delete asset "${asset.name}"?`)) return;
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
        onError: (error) => setSendError(formatError(error, language)),
      },
    );
  };

  const persistDraft = async () => {
    if (!creator) throw new Error(t.missingCreator);
    if (!toEmail.trim()) throw new Error(t.recipientRequired);
    if (!subject.trim() || !body.trim()) throw new Error(t.fillContent);
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
      setSendError(formatError(error, language));
    }
  };

  const onSend = async () => {
    setSendError('');
    if (!defaultAcc) {
      setSendError(t.connectGmailFirst);
      return;
    }
    if (!confirm(t.confirmSend)) return;
    try {
      const persistedDraftId = await persistDraft();
      const sent = await sendDraft.mutateAsync({
        id: persistedDraftId,
        body: { confirm: true, update_creator_status: true, from_account_id: defaultAcc.id },
      });
      setSentSummary(`${t.sentSummary} · ${t.subject}: ${sent.subject} · ${t.recipient}: ${sent.to_email}`);
      setStep('sent');
      setActiveLock(null);
      lockRequestKeyRef.current = '';
      historyQ.refetch();
    } catch (error: any) {
      setSendError(formatError(error, language));
    }
  };

  const onDisconnectGmail = () => {
    if (!defaultAcc) return;
    if (!confirm(`${t.disconnectConfirmPrefix} ${defaultAcc.email} ${t.disconnectConfirmSuffix}`)) return;
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

  const handleClose = () => {
    setActiveLock(null);
    lockRequestKeyRef.current = '';
    onClose();
  };

  const applyHistoryEmail = (item: OutreachHistoryItem) => {
    setSubject(item.subject || '');
    setBody(item.body_format === 'html' ? htmlToPlainText(item.body || '') : item.body || '');
    setIncludeProductImage(false);
    setSendError(item.body_format === 'html' ? t.htmlConverted : '');
    setStep('edit');
  };

  if (!creator) return null;

  const activeStrategy = STRATEGIES.find((item) => item.key === strategy);
  const selectedProductLabel = selectedAsset?.name || productLabel(selectedAsset?.product_key, language);
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
      onClose={handleClose}
      width={640}
      title={<span>{t.outreachTitle} · @{creator.handle}</span>}
      subtitle={<span>{creator.display_name} · {creator.country || t.unknownRegion} · {creator.tier || '?'} {t.level} · {t.email}: {creator.email || t.unknown}</span>}
      footer={
        <>
          {step === 'sent' ? (
            <>
              <button onClick={onReset} className="btn"><RefreshCw size={12} />{t.again}</button>
              <button onClick={handleClose} className="btn btn-primary">{t.done}</button>
            </>
          ) : (
            <>
              <button onClick={handleClose} className="btn">{t.cancel}</button>
              {step === 'template' && (
                <button onClick={onGenerate} disabled={generationBusy || isLocking} className="btn btn-primary">
                  {generationBusy ? <RefreshCw size={12} className="animate-spin" /> : <Wand2 size={12} />}
                  {generationBusy ? t.generating : t.generatePreview} <ArrowRight size={12} />
                </button>
              )}
              {(step === 'preview' || step === 'edit') && (
                <>
                  <button onClick={onSaveDraft} disabled={!canSaveDraft || isSending} className="btn">
                    <Save size={12} />{isPersistingDraft ? t.saving : t.saveDraft}
                  </button>
                  <button onClick={onSend} disabled={!canSendDraft} className="btn btn-primary">
                    <Send size={12} />{isSending ? t.sending : draftId ? t.send : t.saveAndSend}
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
              <div>{t.noGmail} · <a href={gmailConnectHref} className="underline font-medium">{t.connectGmail}</a></div>
              <div className="text-xxs mt-1 opacity-90">{t.gmailHelp}</div>
              {blockingGmailDiagnostic?.message && (
                <div className="mt-2 rounded border border-warn/40 px-2 py-1.5 text-xxs">
                  <div>{translateMessage(blockingGmailDiagnostic.message, language)}</div>
                  {blockingGmailDiagnostic.action && <div className="mt-1 opacity-90">{translateMessage(blockingGmailDiagnostic.action, language)}</div>}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-xxs text-muted mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Mail size={11} className="shrink-0" />
            <span>{t.senderAccount}:</span><span className="text-text font-medium truncate">{defaultAcc?.email}</span>
          </div>
          <button type="button" onClick={onDisconnectGmail} disabled={deleteGmail.isPending} className="underline shrink-0">
            {deleteGmail.isPending ? t.disconnecting : t.disconnect}
          </button>
        </div>
      )}

      {(sendDisabledReason || sendError || generateTk.error) && step !== 'sent' && (
        <div className={`mb-3 rounded-md border px-3 py-2 text-xs ${
          sendError || generateTk.error ? 'border-bad/40 bg-bad/10 text-bad' : 'border-border bg-elev2 text-muted'
        }`}>
          {sendError || (generateTk.error ? formatError(generateTk.error, language) : sendDisabledReason)}
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
                {t.steps[i]}
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
                  <h3 className="text-sm font-semibold">{t.aiTitle}</h3>
                  {matchedAsset && (
                    <span className="chip text-xxs">{t.autoMatch}: {matchedAsset.name}</span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted">{t.aiDesc}</p>
              </div>
            </div>
          </section>

          <section className="rounded-md border border-border bg-elev1/60 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Package size={14} className="text-accent" />
                <h3 className="text-xs font-semibold">{t.assetsTitle}</h3>
              </div>
              <button type="button" className="btn btn-ghost !h-7 text-xs" onClick={() => setAssetFormOpen((v) => !v)}>
                <UploadCloud size={12} />{t.uploadImage}
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
                    <span className="chip text-xxs">{productLabel(selectedAsset.product_key, language)}</span>
                    <button
                      type="button"
                      onClick={() => onDeleteAsset(selectedAsset)}
                      disabled={deleteAsset.isPending}
                      className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded text-muted hover:bg-bad/10 hover:text-bad"
                      title={t.deleteAsset}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                  <div className="mt-1 text-xxs text-muted">{selectedAsset.sku_code || t.skuMissing}</div>
                  {(selectedAsset.selling_points ?? []).length > 0 && (
                    <div className="mt-1 line-clamp-2 text-xs text-muted">{selectedAsset.selling_points?.join(' · ')}</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="mb-3 rounded-md border border-dashed border-border p-3 text-xs text-muted">
                {t.noSelectedSku}
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
                        <span className="mt-0.5 block truncate text-xxs text-muted">{asset.sku_code || productLabel(asset.product_key, language)}</span>
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
                        <span>{t.chooseImage}</span>
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
                      placeholder={t.skuNamePlaceholder}
                    />
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <input
                        value={assetSku}
                        onChange={(event) => setAssetSku(event.target.value)}
                        className="input-bare rounded border border-border px-3 py-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))' }}
                        placeholder={t.skuCodePlaceholder}
                      />
                      <select
                        value={assetProductKey}
                        onChange={(event) => setAssetProductKey(event.target.value)}
                        className="rounded border border-border px-3 py-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}
                      >
                        {PRODUCT_OPTIONS.map((item) => (
                          <option key={item.key} value={item.key}>{item[language]}</option>
                        ))}
                      </select>
                    </div>
                    <textarea
                      value={assetPoints}
                      onChange={(event) => setAssetPoints(event.target.value)}
                      rows={2}
                      className="input-bare resize-none rounded border border-border px-3 py-2 text-xs"
                      style={{ background: 'rgb(var(--bg-elev-2))' }}
                      placeholder={t.sellingPointsPlaceholder}
                    />
                    <input
                      value={assetTargets}
                      onChange={(event) => setAssetTargets(event.target.value)}
                      className="input-bare rounded border border-border px-3 py-2 text-xs"
                      style={{ background: 'rgb(var(--bg-elev-2))' }}
                      placeholder={t.targetTypesPlaceholder}
                    />
                  </div>
                </div>
                {assetError && <div className="mt-2 text-xxs text-bad">{assetError}</div>}
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="min-w-0 text-xxs text-muted">{assetFileName || t.imageOptional}</div>
                  <div className="flex gap-2">
                    <button type="button" className="btn btn-ghost !h-8 text-xs" onClick={resetAssetForm}>{t.clear}</button>
                    <button type="button" className="btn btn-primary !h-8 text-xs" onClick={onSaveAsset} disabled={createAsset.isPending}>
                      {createAsset.isPending ? <RefreshCw size={12} className="animate-spin" /> : <Save size={12} />}
                      {t.saveAsset}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="rounded-md border border-border bg-elev1/60 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Wand2 size={14} className="text-accent" />
              <h3 className="text-xs font-semibold">{t.settings}</h3>
              <span className="text-xxs text-muted">{language === 'zh' ? activeStrategy?.descZh : activeStrategy?.descEn}</span>
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
                  title={language === 'zh' ? item.descZh : item.descEn}
                >
                  {item[language]}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-xs text-muted">{t.commission}</span>
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
                <span className="font-semibold">{t.aiReplaced}</span>
                <span className="chip text-xxs">{generationMeta.aiStatus || 'generated'}</span>
                {generationMeta.productName && <span className="chip text-xxs">{generationMeta.productName}</span>}
              </div>
              <div className="mt-1 text-xxs text-muted">{t.editableAfterAi}</div>
            </div>
          )}
          <div>
            <label className="text-xxs text-muted block mb-1">{t.recipient}</label>
            <input
              value={toEmail}
              onChange={(event) => setToEmail(event.target.value)}
              className="input-bare w-full rounded border border-border px-3 py-2"
              style={{ background: 'rgb(var(--bg-elev-2))' }}
              placeholder="contact@example.com"
            />
          </div>
          <div>
            <label className="text-xxs text-muted block mb-1">{t.subject}</label>
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
                  <h3 className="text-xs font-semibold">{t.emailImage}</h3>
                  {emailImageEnabled && <span className="chip text-xxs">{t.inlineImage}</span>}
                </div>
                <p className="mt-1 text-xxs text-muted">{t.emailImageHelp}</p>
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
                {t.insertImage}
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
                      <span className="text-xxs text-muted">{t.position}</span>
                      <select
                        value={emailImagePosition}
                        onChange={(event) => setEmailImagePosition(event.target.value as EmailImagePosition)}
                        disabled={!includeProductImage}
                        className="h-9 w-full rounded border border-border px-2 text-xs"
                        style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}
                      >
                        {IMAGE_POSITIONS.map((item) => <option key={item.key} value={item.key}>{item[language]}</option>)}
                      </select>
                    </label>
                    <label className="space-y-1">
                      <span className="text-xxs text-muted">{t.caption}</span>
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
                        <span>{t.width}</span>
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
                      <span className="block text-xxs text-muted">{t.align}</span>
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
                <span>{t.currentSkuNoImage}</span>
                <button type="button" className="btn btn-ghost !h-8 text-xs" onClick={() => setStep('template')}>
                  <UploadCloud size={12} /> {t.uploadImage}
                </button>
              </div>
            )}
          </section>
          <div>
            <label className="text-xxs text-muted block mb-1">{t.body}</label>
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={14}
              className="input-bare w-full resize-y rounded border border-border px-3 py-2 font-mono text-xs"
              style={{ background: 'rgb(var(--bg-elev-2))' }}
            />
          </div>
          {generationBusy && (
            <div className="text-xxs text-muted flex items-center gap-1"><RefreshCw size={11} className="animate-spin" />{t.generating}</div>
          )}
          {draftId && <div className="text-xxs text-muted">{t.draftId}: {draftId}</div>}
        </div>
      )}

      {step === 'sent' && (
        <div className="card card-body" style={{ background: 'rgb(var(--good) / 0.12)' }}>
          <div className="flex items-center gap-2 text-good">
            <Send size={14} />
            <span className="text-sm font-medium">{t.sentOk}</span>
          </div>
          <div className="text-xxs text-muted mt-2">{sentSummary}</div>
        </div>
      )}

      <div className="mt-6">
        <div className="flex items-center gap-2 mb-2">
          <History size={13} className="text-muted" />
          <h4 className="text-xs font-semibold">{t.historyTitle}</h4>
          <span className="text-xxs text-muted">{t.total} {historyTotal} {t.records}</span>
        </div>
        {history.length === 0 ? (
          <div className="text-xxs text-muted">{t.noHistory}</div>
        ) : (
          <div className="space-y-1.5">
            {history.map((h: OutreachHistoryItem) => (
              <div key={h.id} className="text-xxs border border-border rounded px-2 py-1.5" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setReviewEmail(h)}
                    className="min-w-0 flex-1 truncate text-left font-medium hover:text-accent"
                    title={t.reviewTitle}
                  >
                    {h.subject}
                  </button>
                  <Pill tone={h.status === 'sent' ? 'good' : h.status === 'queued' ? 'warn' : 'muted'}>{h.status}</Pill>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center justify-between gap-2 text-muted">
                  <span>{h.to_email} · {relativeByLanguage(h.sent_at || h.created_at, language)} · {h.from_email || t.notSent}</span>
                  <span className="flex items-center gap-1">
                    <button type="button" onClick={() => setReviewEmail(h)} className="underline hover:text-accent">{t.review}</button>
                    {h.body && <button type="button" onClick={() => applyHistoryEmail(h)} className="underline hover:text-accent">{t.apply}</button>}
                  </span>
                </div>
              </div>
            ))}
            <PaginationControls
              page={historyPage}
              pageSize={HISTORY_PAGE_SIZE}
              total={historyTotal}
              currentCount={history.length}
              loading={historyQ.isFetching}
              language={language}
              onPageChange={setHistoryPage}
            />
          </div>
        )}
        {reviewEmail && (
          <div className="mt-3 overflow-hidden rounded-md border border-border bg-elev2">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-xs font-semibold">{reviewEmail.subject}</div>
                <div className="mt-0.5 text-xxs text-muted">{reviewEmail.from_email || t.notSent} → {reviewEmail.to_email}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {reviewEmail.body && (
                  <button type="button" onClick={() => applyHistoryEmail(reviewEmail)} className="btn btn-ghost !h-8 text-xs">{t.apply}</button>
                )}
                <button type="button" onClick={() => setReviewEmail(null)} className="btn btn-ghost !h-8 text-xs">{t.close}</button>
              </div>
            </div>
            {reviewEmail.body_format === 'html' ? (
              <iframe
                title={t.reviewTitle}
                sandbox=""
                srcDoc={safeEmailHtml(reviewEmail.body)}
                className="block h-72 w-full bg-white"
              />
            ) : (
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap p-3 text-xs leading-relaxed text-text">{reviewEmail.body || t.noBody}</pre>
            )}
          </div>
        )}
      </div>
    </SideDrawer>
  );
}
