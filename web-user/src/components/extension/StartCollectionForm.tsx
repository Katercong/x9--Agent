import { useState } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { usePostExtensionCommand } from '@/hooks/useApi';
import { useUiStore } from '@/stores/uiStore';
import type { Language } from '@/lib/i18n';

const PRESETS = [
  { key: 'feminineCare', keywords: 'organic cotton pads, period underwear, leakproof underwear' },
  { key: 'momBaby', keywords: 'baby diaper, training pants, diaper rash' },
  { key: 'homeCare', keywords: 'lavender mat, pet pee pad, charcoal mat' },
  { key: 'generalKoc', keywords: 'wellness routine, self care, daily diary' },
] as const;

const formCopy = {
  zh: {
    title: '启动采集',
    subtitle: '向 Chrome 插件下发指令',
    presets: '预设:',
    keywordsLabel: '关键词，逗号或换行分隔',
    keywordPlaceholder: 'organic cotton pads, period underwear...',
    maxProfiles: '最大达人数',
    language: '语言',
    english: 'English',
    chinese: '中文',
    any: '不限',
    start: '下发采集任务',
    offline: '插件离线时命令无法执行。打开 Chrome 插件侧边栏后，本页会自动显示在线。',
    success: '命令已下发，等待 Chrome 插件轮询接管',
    error: '下发失败',
    presetsMap: {
      feminineCare: '女性护理(英)',
      momBaby: '母婴(英)',
      homeCare: '家居护理(英)',
      generalKoc: '通用 KOC',
    },
  },
  en: {
    title: 'Start Collection',
    subtitle: 'Send a command to the Chrome extension',
    presets: 'Presets:',
    keywordsLabel: 'Keywords, separated by commas or new lines',
    keywordPlaceholder: 'organic cotton pads, period underwear...',
    maxProfiles: 'Max creators',
    language: 'Language',
    english: 'English',
    chinese: 'Chinese',
    any: 'Any',
    start: 'Start collection task',
    offline: 'Commands cannot run while the extension is offline. Open the Chrome extension side panel and this page will update automatically.',
    success: 'Command sent. Waiting for the Chrome extension to pick it up.',
    error: 'Failed to send command',
    presetsMap: {
      feminineCare: 'Feminine care',
      momBaby: 'Mom & baby',
      homeCare: 'Home care',
      generalKoc: 'General KOC',
    },
  },
} satisfies Record<Language, any>;

type StartCollectionFormProps = {
  onStarted?: () => void;
  workerId?: string | null;
  online?: boolean;
};

export function StartCollectionForm({ onStarted, workerId, online = false }: StartCollectionFormProps) {
  const { language: uiLanguage } = useUiStore();
  const copy = formCopy[uiLanguage];
  const [keywords, setKeywords] = useState('');
  const [maxProfiles, setMaxProfiles] = useState(50);
  const [language, setLanguage] = useState('en');
  const post = usePostExtensionCommand();

  const onStart = () => {
    if (!keywords.trim() || post.isPending) return;
    post.mutate({
      command_type: 'start_collection',
      worker_id: workerId || undefined,
      payload: {
        keywords: keywords.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean),
        max_profiles: maxProfiles,
        language,
        source: 'x9_leads',
        command_source: 'portal_collection',
      },
    }, {
      onSuccess: () => {
        setKeywords('');
        onStarted?.();
      },
    });
  };

  return (
    <div className="card card-body space-y-3">
      <div className="flex items-center gap-2">
        <Play size={16} className="text-accent" />
        <h3 className="text-sm font-semibold">{copy.title}</h3>
        <span className="text-xxs text-muted">{copy.subtitle}</span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <span className="text-xxs text-muted self-center">{copy.presets}</span>
        {PRESETS.map((p) => (
          <button key={p.key} onClick={() => setKeywords(p.keywords)} className="chip text-xxs">
            {copy.presetsMap[p.key]}
          </button>
        ))}
      </div>

      <div>
        <label className="text-xxs text-muted block mb-1">{copy.keywordsLabel}</label>
        <textarea
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          rows={2}
          placeholder={copy.keywordPlaceholder}
          className="input-bare w-full px-3 py-2 rounded border border-border resize-none"
          style={{ background: 'rgb(var(--bg-elev-2))' }}
        />
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="min-w-[120px]">
          <label className="text-xxs text-muted block mb-1">{copy.maxProfiles}</label>
          <input
            type="number" min={1} max={500}
            value={maxProfiles}
            onChange={(e) => setMaxProfiles(parseInt(e.target.value) || 50)}
            className="input-bare w-full px-3 py-1.5 rounded border border-border"
            style={{ background: 'rgb(var(--bg-elev-2))' }}
          />
        </div>
        <div className="min-w-[120px]">
          <label className="text-xxs text-muted block mb-1">{copy.language}</label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="text-xs px-2 py-1.5 rounded border border-border w-full"
            style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}
          >
            <option value="en">{copy.english}</option>
            <option value="zh">{copy.chinese}</option>
            <option value="any">{copy.any}</option>
          </select>
        </div>
        <button onClick={onStart} disabled={post.isPending || !keywords.trim() || !online} className="btn btn-primary">
          {post.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {copy.start}
        </button>
      </div>

      {!online && (
        <div className="text-xxs text-warn">{copy.offline}</div>
      )}

      {post.isSuccess && (
        <div className="text-xxs text-good">{copy.success}</div>
      )}
      {post.isError && (
        <div className="text-xxs text-bad">{(post.error as any)?.message || copy.error}</div>
      )}
    </div>
  );
}
