import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  AtSign,
  Brain,
  ExternalLink,
  FileText,
  Link2,
  MessageSquareText,
  NotebookText,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useForeignTradeSocialUser, type LeadItem, type SocialCommentEvidence, type SocialNoteEvidence, type SocialSourceEvidence } from '@/api/foreignTrade';

const PLATFORM_LABELS: Record<string, string> = {
  xhs: '小红书',
  douyin: '抖音',
};

const DECISION_LABELS: Record<string, string> = {
  high_priority: '高意向',
  follow_up: '待跟进',
  nurture: '培育',
  target_customer: '目标客户',
  experienced_seller: '经验卖家',
  potential: '潜在线索',
  ignore: '忽略',
  irrelevant: '无关',
  supplier_peer: '供应方同行',
  logistics_partner: '物流伙伴',
  error: '判定失败',
};

function text(value: unknown) {
  return String(value ?? '').trim();
}

function countText(value?: number | null) {
  if (!value) return '0';
  if (value >= 10000) return `${(value / 10000).toFixed(1)}w`;
  return new Intl.NumberFormat('zh-CN').format(value);
}

function decisionTone(value?: string | null): 'good' | 'warn' | 'bad' | 'info' | 'muted' {
  if (value === 'high_priority' || value === 'target_customer' || value === 'experienced_seller') return 'good';
  if (value === 'follow_up' || value === 'nurture' || value === 'potential') return 'warn';
  if (value === 'ignore' || value === 'irrelevant' || value === 'supplier_peer' || value === 'error') return 'bad';
  return 'muted';
}

function timeText(value?: string | null) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export default function ForeignTradeSocialUserDetail() {
  const { userId } = useParams<{ userId: string }>();
  const query = useForeignTradeSocialUser(userId);
  const row = query.data?.item || null;

  return (
    <AsyncState loading={query.isLoading} error={query.error} isEmpty={!query.isLoading && !row} emptyMessage="没有找到这个用户" height={520}>
      {row && <DetailBody row={row} promptVersion={query.data?.prompt_version} />}
    </AsyncState>
  );
}

function DetailBody({ row, promptVersion }: { row: LeadItem; promptVersion?: string }) {
  const platform = PLATFORM_LABELS[row.platform || ''] || row.platform || '社媒';
  const avatarText = text(row.name).slice(0, 1) || '客';
  const decision = row.decision || 'unjudged';
  const score = row.fit_score ?? row.score ?? 0;
  const profileUrl = text(row.profile_url);
  const firstCommentUrl = text(row.recent_comments?.[0]?.note_url);

  return (
    <div className="space-y-4">
      <section className="rounded-md border border-border bg-elev1 p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <Link to="/recommendations" className="btn btn-ghost !h-9 !w-9 !justify-center !px-0" title="返回客户推荐">
              <ArrowLeft size={16} />
            </Link>
            {row.avatar_url ? (
              <img src={row.avatar_url} alt="" className="h-14 w-14 shrink-0 rounded-full object-cover" />
            ) : (
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-accent/15 text-lg font-semibold text-accent">
                {avatarText}
              </div>
            )}
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="truncate text-xl font-semibold text-text">{row.name || row.account || '未命名客户'}</h1>
                <Pill tone="info">{platform}</Pill>
                <Pill tone={decisionTone(decision)}>{DECISION_LABELS[decision] || decision}</Pill>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                {row.account && <span className="inline-flex items-center gap-1"><AtSign size={12} />{row.account}</span>}
                {row.location && <span>{row.location}</span>}
                <span>评分版本 {promptVersion || '--'}</span>
              </div>
              {row.bio && <p className="mt-3 max-w-4xl whitespace-pre-wrap text-sm leading-6 text-text/90">{row.bio}</p>}
            </div>
          </div>
          <div className="grid min-w-[220px] grid-cols-3 gap-2 text-right">
            <Metric label="推荐分" value={countText(score)} accent />
            <Metric label="粉丝" value={countText(row.followers)} />
            <Metric label="评论" value={countText(row.comments_count)} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {profileUrl && (
            <a href={profileUrl} target="_blank" rel="noreferrer" className="btn btn-primary">
              <ExternalLink size={14} />打开主页
            </a>
          )}
          {firstCommentUrl && (
            <a href={firstCommentUrl} target="_blank" rel="noreferrer" className="btn">
              <MessageSquareText size={14} />打开评论原文
            </a>
          )}
          <Link to="/emails" className="btn btn-ghost">
            <ShieldCheck size={14} />查看跟进记录
          </Link>
        </div>
      </section>

      <main className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          <Panel title="互动证据链" icon={<MessageSquareText size={15} />}>
            <CommentList items={row.recent_comments} />
          </Panel>
          <Panel title="视频 / 笔记内容" icon={<NotebookText size={15} />}>
            <NoteList items={[...(row.recent_notes || []), ...(row.history_posts || [])]} />
          </Panel>
          <Panel title="采集来源" icon={<Link2 size={15} />}>
            <SourceList items={row.source_samples} />
          </Panel>
        </div>

        <aside className="space-y-3">
          <Panel title="GPT 意向判定" icon={<Brain size={15} />}>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={decisionTone(row.decision)}>{DECISION_LABELS[row.decision || ''] || row.decision || '未判定'}</Pill>
                {row.fit_level && <Pill tone="muted">{row.fit_level}</Pill>}
                {row.intent_type && <Pill tone="info">{row.intent_type}</Pill>}
                {row.customer_priority && <Pill tone={decisionTone(row.decision)}>{row.customer_priority}</Pill>}
              </div>
              <Fact label="推荐分" value={countText(score)} />
              <Fact label="判定时间" value={timeText(row.judged_at)} />
              <Fact label="判定证据" value={row.judgment_evidence || row.judgment || '--'} multiline />
              <Fact label="建联建议" value={row.judgment_suggestion || '--'} multiline />
            </div>
          </Panel>

          <Panel title="联系方式与信号" icon={<UserRound size={15} />}>
            <div className="space-y-3">
              <Fact label="联系方式" value={row.contact || '--'} multiline />
              <TagBlock title="联系信号" values={row.contact_signals} />
              <TagBlock title="平台信号" values={row.platform_signals} />
              <Fact label="作品数" value={countText(row.profile_note_count ?? row.notes_count)} />
              <Fact label="获赞收藏" value={countText(row.liked_collect_count)} />
              <Fact label="清洗状态" value={row.clean_status || '--'} />
              <Fact label="入库时间" value={timeText(row.created_at)} />
            </div>
          </Panel>

          <Panel title="原始资料快照" icon={<FileText size={15} />}>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded border border-border bg-bg p-3 text-xxs leading-5 text-muted">
              {JSON.stringify(row.raw_user || row.profile_quality || {}, null, 2)}
            </pre>
          </Panel>
        </aside>
      </main>
    </div>
  );
}

function Metric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-bg px-3 py-2">
      <div className={`num text-lg font-semibold ${accent ? 'text-accent' : 'text-text'}`}>{value}</div>
      <div className="text-xxs text-muted">{label}</div>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-elev1">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3 text-sm font-semibold">
        <span className="text-accent">{icon}</span>
        {title}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function CommentList({ items }: { items?: SocialCommentEvidence[] }) {
  const rows = (items || []).filter((item) => text(item.content));
  if (!rows.length) return <div className="text-xs text-muted">暂无评论证据</div>;
  return (
    <div className="space-y-3">
      {rows.map((item, index) => (
        <div key={item.id || index} className="rounded-md border border-border bg-bg p-3">
          <div className="whitespace-pre-wrap text-sm leading-6 text-text">{item.content}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xxs text-muted">
            {item.location && <span>{item.location}</span>}
            {item.published_at_text && <span>{item.published_at_text}</span>}
            {item.note_title && <span className="max-w-[360px] truncate">来自：{item.note_title}</span>}
            {item.note_url && <a className="text-accent hover:underline" href={item.note_url} target="_blank" rel="noreferrer">原文</a>}
          </div>
        </div>
      ))}
    </div>
  );
}

function NoteList({ items }: { items?: SocialNoteEvidence[] }) {
  const rows = (items || []).filter((item) => text(item.title || item.desc));
  if (!rows.length) return <div className="text-xs text-muted">暂无视频/笔记内容</div>;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {rows.map((item, index) => (
        <article key={item.id || item.url || index} className="grid grid-cols-[72px_minmax(0,1fr)] gap-3 rounded-md border border-border bg-bg p-3">
          {item.cover_url ? (
            <img src={item.cover_url} alt="" className="h-20 w-20 rounded object-cover" />
          ) : (
            <div className="flex h-20 w-20 items-center justify-center rounded bg-elev2 text-muted">
              <NotebookText size={18} />
            </div>
          )}
          <div className="min-w-0">
            <div className="line-clamp-2 text-sm font-semibold text-text">{item.title || item.desc}</div>
            {item.desc && item.title && <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{item.desc}</div>}
            <div className="mt-2 flex flex-wrap gap-2 text-xxs text-muted">
              <span>赞 {countText(item.like_count)}</span>
              <span>评 {countText(item.comment_count)}</span>
              {item.keyword && <span>{item.keyword}</span>}
              {item.url && <a className="text-accent hover:underline" href={item.url} target="_blank" rel="noreferrer">查看</a>}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function SourceList({ items }: { items?: SocialSourceEvidence[] }) {
  const rows = (items || []).filter((item) => text(item.evidence_text || item.keyword || item.evidence_url));
  if (!rows.length) return <div className="text-xs text-muted">暂无来源记录</div>;
  return (
    <div className="space-y-2">
      {rows.map((item, index) => (
        <div key={`${item.source_type}-${item.keyword}-${index}`} className="rounded-md border border-border bg-bg p-3 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="info">{item.source_type || '来源'}</Pill>
            {item.keyword && <Pill>{item.keyword}</Pill>}
            {item.created_at && <span className="text-muted">{timeText(item.created_at)}</span>}
          </div>
          {item.evidence_text && <div className="mt-2 whitespace-pre-wrap leading-5">{item.evidence_text}</div>}
          {item.evidence_url && <a className="mt-2 inline-flex items-center gap-1 text-accent hover:underline" href={item.evidence_url} target="_blank" rel="noreferrer"><ExternalLink size={12} />打开来源</a>}
        </div>
      ))}
    </div>
  );
}

function Fact({ label, value, multiline = false }: { label: string; value: string | number | null | undefined; multiline?: boolean }) {
  return (
    <div className="border-b border-border/70 pb-2 last:border-b-0">
      <div className="text-xxs text-muted">{label}</div>
      <div className={`mt-1 text-xs text-text ${multiline ? 'whitespace-pre-wrap leading-5' : 'truncate'}`}>{value || '--'}</div>
    </div>
  );
}

function TagBlock({ title, values }: { title: string; values?: string[] }) {
  const list = (values || []).map(text).filter(Boolean);
  return (
    <div>
      <div className="mb-1 text-xxs text-muted">{title}</div>
      {list.length ? (
        <div className="flex flex-wrap gap-1.5">
          {list.map((item) => <Pill key={item} tone="muted">{item}</Pill>)}
        </div>
      ) : (
        <div className="text-xs text-muted">--</div>
      )}
    </div>
  );
}
