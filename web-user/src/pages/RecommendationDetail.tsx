import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle, ArrowLeft, ExternalLink, Link2, Mail, MessageSquare,
  RefreshCw, Send, ShieldCheck, UserCheck, UserMinus,
} from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { OutreachDrawer } from '@/components/outreach/OutreachDrawer';
import { TkScriptModal } from '@/components/outreach/TkScriptModal';
import { useAcquireOutreachLock, useClaimCreator, useCreator, useReleaseCreator } from '@/hooks/useApi';
import { formatCompact, maskEmail, shortRelative } from '@/lib/format';
import type { Creator, CreatorOutreachLock } from '@/api/types';

type TabKey = 'overview' | 'evidence' | 'risk' | 'history';
type Tone = 'good' | 'warn' | 'muted';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: '推荐判断' },
  { key: 'evidence', label: '证据来源' },
  { key: 'risk', label: '风险复核' },
  { key: 'history', label: '外联历史' },
];

function listify(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return [];
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
    } catch {
      // Plain comma-separated text is handled below.
    }
    return trimmed.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function creatorName(c?: Creator | null) {
  return c?.display_name || c?.handle || (c?.id ? `达人 ${c.id}` : '达人详情');
}

function initial(c?: Creator | null) {
  return (c?.handle || c?.display_name || '?').slice(0, 1).toUpperCase();
}

function followers(c?: Creator | null) {
  return c?.followers_count ?? c?.followers ?? null;
}

function scoreTone(score?: number | null): { label: string; tone: Tone } {
  if ((score ?? 0) >= 85) return { label: '强推荐', tone: 'good' };
  if ((score ?? 0) >= 70) return { label: '可测试', tone: 'warn' };
  return { label: '观察', tone: 'muted' };
}

function Pill({ tone = 'muted', children }: { tone?: Tone | 'info' | 'bad'; children: ReactNode }) {
  const className = tone === 'good'
    ? 'pill-good'
    : tone === 'warn'
      ? 'pill-warn'
      : tone === 'bad'
        ? 'pill-bad'
        : tone === 'info'
          ? 'pill-info'
          : 'pill-muted';
  return <span className={`pill ${className}`}>{children}</span>;
}

function Metric({ label, value, accent }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="text-xxs text-muted">{label}</div>
      <div className="num mt-1 text-lg font-semibold leading-tight" style={{ color: accent ? 'rgb(var(--accent))' : 'rgb(var(--text))' }}>
        {value}
      </div>
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        {action}
      </div>
      <div className="p-4 text-sm leading-relaxed text-text">{children}</div>
    </section>
  );
}

function InfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
      <div className="mb-2 text-xs font-semibold text-text">{title}</div>
      <div className="text-xs leading-relaxed text-muted">{children}</div>
    </div>
  );
}

function ScoreBar({ label, value, tone = 'info' }: { label: string; value?: number | null; tone?: 'info' | 'good' | 'warn' }) {
  const pct = Math.max(0, Math.min(100, Number(value ?? 0)));
  const fill = tone === 'good'
    ? 'rgb(var(--good))'
    : tone === 'warn'
      ? 'rgb(var(--warn))'
      : 'rgb(var(--accent))';

  return (
    <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
      <div className="flex items-center justify-between gap-2 text-xxs text-muted">
        <span>{label}</span>
        <strong className="num text-text">{pct}</strong>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-pill" style={{ background: 'rgb(var(--bg-elev-1))' }}>
        <div className="h-full rounded-pill" style={{ width: `${pct}%`, background: fill }} />
      </div>
    </div>
  );
}

export default function RecommendationDetail() {
  const { creatorId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>('overview');
  const [mailOpen, setMailOpen] = useState(false);
  const [mailLock, setMailLock] = useState<CreatorOutreachLock | null>(null);
  const [mailOpening, setMailOpening] = useState(false);
  const [scriptOpen, setScriptOpen] = useState(false);

  const creatorQ = useCreator(creatorId);
  const claim = useClaimCreator();
  const release = useReleaseCreator();
  const acquireOutreachLock = useAcquireOutreachLock();
  const creator = creatorQ.data;

  const positiveTags = useMemo(() => listify(creator?.positive_tags), [creator]);
  const riskTags = useMemo(() => listify(creator?.risk_tags), [creator]);
  const keywords = useMemo(() => listify(creator?.matched_keywords), [creator]);
  const evidenceSources = useMemo(() => listify(creator?.fit_evidence_sources), [creator]);
  const score = creator?.recommendation_score ?? 0;
  const tone = scoreTone(score);
  const priority = creator?.outreach_priority || creator?.priority_level || 'P?';
  const owner = creator?.owner_bd || creator?.bd_owner || '未认领';

  const refreshCreator = () => {
    qc.invalidateQueries({ queryKey: ['creator', creatorId] });
    qc.invalidateQueries({ queryKey: ['creators'] });
  };

  const onClaim = () => {
    if (!creator) return;
    claim.mutate({ id: creator.id, body: {} }, { onSuccess: refreshCreator });
  };

  const onRelease = () => {
    if (!creator) return;
    release.mutate({ id: creator.id }, { onSuccess: refreshCreator });
  };

  const openMail = async () => {
    if (!creator) return;
    setMailOpening(true);
    try {
      const result = await acquireOutreachLock.mutateAsync({ creator_id: creator.id });
      setMailLock(result.lock);
      setMailOpen(true);
    } catch (error: any) {
      alert(String(error?.body?.detail || error?.message || '达人已被其他用户占用，请刷新后再试'));
    } finally {
      setMailOpening(false);
    }
  };

  return (
    <AsyncState loading={creatorQ.isLoading} error={creatorQ.error} isEmpty={!creatorQ.isLoading && !creator} emptyMessage="没有找到该达人" height={420}>
      {creator && (
        <div className="space-y-4">
          <div className="card card-body">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => navigate('/recommendations')}
                  className="btn btn-ghost !h-9 !w-9 !justify-center !px-0"
                  aria-label="返回达人库"
                  title="返回达人库"
                >
                  <ArrowLeft size={16} />
                </button>
                <div
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-md text-base font-semibold"
                  style={{ background: 'rgb(var(--accent) / 0.16)', color: 'rgb(var(--accent))' }}
                >
                  {initial(creator)}
                </div>
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <h2 className="truncate text-base font-semibold text-text">@{creator.handle || 'unknown'}</h2>
                    <Pill tone="info">{priority}</Pill>
                    <Pill tone={tone.tone}>{tone.label}</Pill>
                  </div>
                  <div className="mt-1 truncate text-xs text-muted">
                    {creatorName(creator)} · {creator.platform || 'tiktok'} · 最近更新 {shortRelative(creator.updated_at || creator.collected_at || creator.created_at)}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="rounded-md border border-border px-3 py-1.5 text-xs text-muted" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
                  推荐分 <strong className="num ml-1 text-base text-text">{Math.round(score)}</strong>
                </div>
                <button type="button" onClick={openMail} disabled={mailOpening} className="btn btn-primary">
                  {mailOpening ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />} 邮件建联
                </button>
                {creator.profile_url && (
                  <a href={creator.profile_url} target="_blank" rel="noreferrer" className="btn">
                    <ExternalLink size={14} /> 主页
                  </a>
                )}
              </div>
            </div>
          </div>

          <main className="grid gap-3 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
            <aside className="card">
              <div className="border-b border-border p-4">
                <div className="flex items-center gap-3">
                  <div
                    className="grid h-14 w-14 shrink-0 place-items-center rounded-md text-xl font-semibold"
                    style={{ background: 'rgb(var(--accent) / 0.16)', color: 'rgb(var(--accent))' }}
                  >
                    {initial(creator)}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-text">{creatorName(creator)}</div>
                    <div className="mt-1 font-mono text-xs text-muted">@{creator.handle || 'unknown'}</div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Pill tone={creator.email || creator.has_contact ? 'good' : 'muted'}>
                        {creator.email || creator.has_contact ? '可联系' : '待补联系方式'}
                      </Pill>
                      <Pill tone="info">{creator.primary_product_category || creator.recommended_product_type || '未分类'}</Pill>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 p-4">
                <Metric label="粉丝数" value={formatCompact(followers(creator))} />
                <Metric label="推荐分" value={Math.round(score)} accent />
                <Metric label="商品匹配" value={creator.primary_product_fit_score ?? '—'} />
                <Metric label="优先级" value={priority} />
              </div>

              <dl className="border-t border-border px-4 py-2">
                {[
                  ['邮箱', creator.email ? maskEmail(creator.email) : '暂无邮箱'],
                  ['负责人', owner],
                  ['合作类型', creator.recommended_collab_type || '未设定'],
                  ['推荐商品', creator.recommended_product_type || creator.primary_product_category || '未设定'],
                  ['状态', creator.recommendation_status || creator.current_status || '待处理'],
                  ['采集来源', creator.source_label || creator.source || '—'],
                ].map(([label, value]) => (
                  <div key={label} className="grid grid-cols-[72px_minmax(0,1fr)] gap-2 border-b border-border/60 py-2.5 text-xs last:border-b-0">
                    <dt className="text-muted">{label}</dt>
                    <dd className="m-0 min-w-0 break-words text-text">{value}</dd>
                  </div>
                ))}
              </dl>
            </aside>

            <section className="card overflow-hidden">
              <div className="border-b border-border p-4">
                <div className="grid gap-4 lg:grid-cols-[132px_minmax(0,1fr)]">
                  <div className="rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
                    <div className="text-xxs uppercase tracking-wide text-muted">Score</div>
                    <div className="num mt-2 text-4xl font-semibold leading-none text-text">{Math.round(score)}</div>
                    <div className="mt-3"><Pill tone={tone.tone}>{tone.label} · {priority}</Pill></div>
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-1.5">
                      <Pill tone={tone.tone}>{tone.label}</Pill>
                      <Pill tone="info">证据 {creator.evidence_strength || '—'}</Pill>
                      {creator.email && <Pill tone="good">邮箱可用</Pill>}
                    </div>
                    <h2 className="mt-3 text-lg font-semibold leading-snug text-text">
                      {creator.next_action || '建议先用样品包 + 联盟佣金发起低成本合作测试。'}
                    </h2>
                    <p className="mt-2 text-sm leading-relaxed text-muted">
                      {creator.recommendation_reason || '暂无推荐理由。可以在这里展示 AI 生成的合作判断、适配商品、外联策略和人工复核结论。'}
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
                  <ScoreBar label="商品匹配" value={creator.primary_product_fit_score} />
                  <ScoreBar label="商业价值" value={creator.commercial_value_score} tone="good" />
                  <ScoreBar label="可联系性" value={creator.contactability_score} />
                  <ScoreBar label="数据完整度" value={creator.data_quality_score} tone="warn" />
                </div>
              </div>

              <div className="flex overflow-x-auto border-b border-border" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
                {TABS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setTab(item.key)}
                    className="h-10 min-w-[104px] border-r border-border px-3 text-xs font-medium transition-colors"
                    style={tab === item.key
                      ? { color: 'rgb(var(--text))', background: 'rgb(var(--bg-elev-1))', boxShadow: 'inset 0 -2px 0 rgb(var(--accent))' }
                      : { color: 'rgb(var(--muted))' }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className="p-4">
                {tab === 'overview' && (
                  <div className="grid gap-3">
                    <div className="grid gap-3 lg:grid-cols-2">
                      <InfoBlock title="推荐理由">
                        {creator.recommendation_reason || '暂无推荐理由。'}
                      </InfoBlock>
                      <InfoBlock title="下一步动作">
                        {creator.next_action || '发送首封合作邮件；72 小时未回复时，切换其他联系方式补触达。'}
                      </InfoBlock>
                    </div>
                    <InfoBlock title="正向标签">
                      <div className="flex flex-wrap gap-1.5">
                        {(positiveTags.length > 0 ? positiveTags : [creator.primary_product_category, creator.recommended_product_type, creator.recommended_collab_type].filter(Boolean)).map((tag) => (
                          <Pill key={tag} tone="good">{tag}</Pill>
                        ))}
                        {positiveTags.length === 0 && !creator.primary_product_category && <span>暂无标签</span>}
                      </div>
                    </InfoBlock>
                  </div>
                )}

                {tab === 'evidence' && (
                  <div className="grid gap-3">
                    <div className="grid gap-3 lg:grid-cols-2">
                      <InfoBlock title="命中关键词">
                        <div className="flex flex-wrap gap-1.5">
                          {keywords.length > 0 ? keywords.map((tag) => (
                            <Pill key={tag} tone="info">{tag}</Pill>
                          )) : <span>暂无关键词</span>}
                        </div>
                      </InfoBlock>
                      <InfoBlock title="证据来源">
                        <div className="flex flex-wrap gap-1.5">
                          {evidenceSources.length > 0 ? evidenceSources.map((source) => (
                            <Pill key={source}>{source}</Pill>
                          )) : <span>暂无证据来源</span>}
                        </div>
                      </InfoBlock>
                    </div>
                    <InfoBlock title="Profile Snapshot">
                      <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded border border-border p-3 text-xs text-text" style={{ background: 'rgb(var(--bg-elev-1))' }}>
                        {JSON.stringify(creator.profile_snapshot || {}, null, 2)}
                      </pre>
                    </InfoBlock>
                  </div>
                )}

                {tab === 'risk' && (
                  <div className="grid gap-3 lg:grid-cols-2">
                    <InfoBlock title="风险摘要">
                      <div className="flex gap-2">
                        <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warn" />
                        <span>{creator.risk_summary || '暂无明显风险。建议首轮仍控制预算，以样品测试和联盟合作验证内容效果。'}</span>
                      </div>
                    </InfoBlock>
                    <InfoBlock title="风险标签">
                      <div className="flex flex-wrap gap-1.5">
                        {riskTags.length > 0 ? riskTags.map((tag) => (
                          <Pill key={tag} tone="warn">{tag}</Pill>
                        )) : <span>暂无风险标签</span>}
                      </div>
                    </InfoBlock>
                  </div>
                )}

                {tab === 'history' && (
                  <div className="grid gap-3">
                    <InfoBlock title="外联记录">
                      <div className="flex items-center gap-2">
                        <Send size={15} />
                        <span>
                          已发送 {creator.outreach_count ?? 0} 封邮件；最近发送：
                          {creator.last_outreach_at ? shortRelative(creator.last_outreach_at) : '暂无'}
                        </span>
                      </div>
                    </InfoBlock>
                    <InfoBlock title="邮件历史">
                      详细邮件历史会在点击“邮件建联”后从外联抽屉中查看。
                    </InfoBlock>
                  </div>
                )}
              </div>
            </section>

            <aside className="space-y-3">
              <Section title="外联动作">
                <div className="flex flex-wrap gap-1.5">
                  <Pill tone="info">ACTION</Pill>
                  <Pill>{creator.current_status || '待建联'}</Pill>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-muted">
                  邮件入口固定保留，外联抽屉会带入达人、邮箱、模板和历史记录。
                </p>
                <button type="button" onClick={openMail} disabled={mailOpening} className="btn btn-primary mt-4 w-full justify-center">
                  {mailOpening ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />} 邮件建联
                </button>
                <button
                  type="button"
                  onClick={() => setScriptOpen(true)}
                  className="btn mt-2 w-full justify-center text-xs"
                >
                  <MessageSquare size={14} /> 生成 TK 邀约话术
                </button>
              </Section>

              <Section title="跟进信息">
                <div className="space-y-2">
                  {[
                    ['负责人', owner],
                    ['店铺归属', creator.store_assigned || '未分配'],
                    ['最近外联', creator.last_outreach_at ? shortRelative(creator.last_outreach_at) : '暂无发送'],
                    ['推荐状态', creator.recommendation_status || '—'],
                    ['证据强度', creator.evidence_strength || '—'],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-start justify-between gap-3 border-b border-border/60 pb-2 text-xs last:border-b-0">
                      <span className="text-muted">{label}</span>
                      <strong className="break-words text-right font-medium text-text">{value}</strong>
                    </div>
                  ))}
                </div>
              </Section>

              <Section title="操作">
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={onClaim} disabled={claim.isPending} className="btn justify-center">
                    {claim.isPending ? <RefreshCw size={13} className="animate-spin" /> : <UserCheck size={13} />} 认领
                  </button>
                  <button type="button" onClick={onRelease} disabled={release.isPending} className="btn justify-center">
                    {release.isPending ? <RefreshCw size={13} className="animate-spin" /> : <UserMinus size={13} />} 释放
                  </button>
                </div>
                <div className="mt-3 rounded-md border border-border p-3" style={{ background: 'rgb(var(--bg-elev-2) / 0.35)' }}>
                  <div className="flex items-center gap-2 text-xs font-semibold text-text"><Mail size={14} /> 邮件预览</div>
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    Hi {creator.display_name || creator.handle}, I came across your content and think our product line may fit your audience...
                  </p>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {creator.profile_url && (
                    <a href={creator.profile_url} target="_blank" rel="noreferrer" className="btn justify-center">
                      <Link2 size={13} /> 主页
                    </a>
                  )}
                  <button type="button" onClick={refreshCreator} className="btn justify-center">
                    <ShieldCheck size={13} /> 刷新
                  </button>
                </div>
              </Section>
            </aside>
          </main>

          <OutreachDrawer
            creator={creator}
            open={mailOpen}
            initialLock={mailLock}
            onClose={() => {
              setMailOpen(false);
              setMailLock(null);
              refreshCreator();
            }}
          />
          {scriptOpen && <TkScriptModal creator={creator} onClose={() => setScriptOpen(false)} />}
        </div>
      )}
    </AsyncState>
  );
}
