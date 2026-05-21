import { useState } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { usePostExtensionCommand } from '@/hooks/useApi';

const PRESETS = [
  { name: '女性护理(英)', keywords: 'organic cotton pads, period underwear, leakproof underwear' },
  { name: '母婴(英)', keywords: 'baby diaper, training pants, diaper rash' },
  { name: '家居护理(英)', keywords: 'lavender mat, pet pee pad, charcoal mat' },
  { name: '通用 KOC', keywords: 'wellness routine, self care, daily diary' },
];

type StartCollectionFormProps = {
  onStarted?: () => void;
  workerId?: string | null;
  online?: boolean;
};

export function StartCollectionForm({ onStarted, workerId, online = false }: StartCollectionFormProps) {
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
        <h3 className="text-sm font-semibold">启动采集</h3>
        <span className="text-xxs text-muted">向 Chrome 插件下发指令</span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <span className="text-xxs text-muted self-center">预设:</span>
        {PRESETS.map((p) => (
          <button key={p.name} onClick={() => setKeywords(p.keywords)} className="chip text-xxs">
            {p.name}
          </button>
        ))}
      </div>

      <div>
        <label className="text-xxs text-muted block mb-1">关键词(逗号或换行分隔)</label>
        <textarea
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          rows={2}
          placeholder="organic cotton pads, period underwear..."
          className="input-bare w-full px-3 py-2 rounded border border-border resize-none"
          style={{ background: 'rgb(var(--bg-elev-2))' }}
        />
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="min-w-[120px]">
          <label className="text-xxs text-muted block mb-1">最大达人数</label>
          <input
            type="number" min={1} max={500}
            value={maxProfiles}
            onChange={(e) => setMaxProfiles(parseInt(e.target.value) || 50)}
            className="input-bare w-full px-3 py-1.5 rounded border border-border"
            style={{ background: 'rgb(var(--bg-elev-2))' }}
          />
        </div>
        <div className="min-w-[120px]">
          <label className="text-xxs text-muted block mb-1">语言</label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="text-xs px-2 py-1.5 rounded border border-border w-full"
            style={{ background: 'rgb(var(--bg-elev-2))', color: 'rgb(var(--text))' }}
          >
            <option value="en">English</option>
            <option value="zh">中文</option>
            <option value="any">不限</option>
          </select>
        </div>
        <button onClick={onStart} disabled={post.isPending || !keywords.trim() || !online} className="btn btn-primary">
          {post.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          下发采集任务
        </button>
      </div>

      {!online && (
        <div className="text-xxs text-warn">插件离线时命令无法执行。打开 Chrome 插件侧边栏后，本页会自动显示在线。</div>
      )}

      {post.isSuccess && (
        <div className="text-xxs text-good">✓ 命令已下发，等待 Chrome 插件轮询接管</div>
      )}
      {post.isError && (
        <div className="text-xxs text-bad">✗ {(post.error as any)?.message || '下发失败'}</div>
      )}
    </div>
  );
}
