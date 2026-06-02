import { useEffect } from 'react';
import { X, ExternalLink } from 'lucide-react';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import {
  useCompanyLeadDetail,
  useTalentLeadDetail,
  type CompanyLeadDetail,
  type TalentLeadItem,
} from '@/api/foreignTrade';

export type LeadKind = 'company' | 'talent';

interface LeadDetailDrawerProps {
  kind: LeadKind;
  id: string | null;
  onClose: () => void;
}

const TIER_TONE: Record<string, 'good' | 'warn' | 'muted'> = { A: 'good', B: 'warn', C: 'muted' };
const PLATFORM_LABELS: Record<string, string> = { '51job': '前程无忧', zhaopin: '智联招聘', qzrc: '大泉州人才网', xhs: '小红书', douyin: '抖音' };

function Field({ label, value, mono }: { label: string; value?: React.ReactNode; mono?: boolean }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="border-b border-line py-2.5 last:border-0">
      <div className="text-xxs text-muted">{label}</div>
      <div className={`mt-1 text-xs text-gray-900 ${mono ? 'num' : ''} break-words`}>{value}</div>
    </div>
  );
}

function LinkRow({ url, sub }: { url: string; sub?: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-2 rounded-md border border-line bg-stone-50 px-3 py-2 text-xs text-blue-700 hover:bg-blue-50"
    >
      <ExternalLink size={13} className="shrink-0" />
      <span className="min-w-0 flex-1 truncate">{url}</span>
      {sub && <span className="shrink-0 text-xxs text-muted">{sub}</span>}
    </a>
  );
}

function CompanyBody({ item }: { item: CompanyLeadDetail }) {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {item.tier ? <Pill tone={TIER_TONE[item.tier] || 'muted'}>{item.tier} 级</Pill> : <Pill tone="muted">未评级</Pill>}
        <span className="num text-xs font-semibold text-gray-900">评分 {item.score}</span>
        {item.us_market ? <Pill tone="good">美区</Pill> : null}
        {item.excluded ? <Pill tone="bad">已排除</Pill> : null}
      </div>

      <Section title="原页链接（点击打开）">
        {item.source_urls?.length ? (
          <div className="space-y-2">
            {item.source_urls.map((s) => (
              <LinkRow key={s.url} url={s.url} sub={PLATFORM_LABELS[s.platform || ''] || s.platform || undefined} />
            ))}
          </div>
        ) : (
          <div className="text-xs text-muted">暂无源页链接</div>
        )}
      </Section>

      <Section title="基本信息">
        <Field label="公司名" value={item.company_name} />
        <Field label="行业" value={item.industry} />
        <Field label="规模" value={item.size_range} />
        <Field label="城市 / 省份" value={[item.city, item.province].filter(Boolean).join(' / ')} />
        <Field label="地址" value={item.company_address} />
        <Field label="合作类型" value={item.cooperation_type} />
        <Field label="招聘职位" value={item.raw_jd_titles?.length ? item.raw_jd_titles.join('、') : null} />
        <Field label="公司描述" value={item.company_description} />
      </Section>

      <Section title="联系方式">
        <Field label="联系人 / 职位" value={[item.contact_name, item.contact_title].filter(Boolean).join(' · ')} />
        <Field label="邮箱" value={item.contact_email} mono />
        <Field label="电话" value={item.contact_phone} mono />
        <Field label="微信" value={item.hr_wechat} mono />
        <Field label="来源" value={item.contact_source} />
      </Section>

      <Section title="评分与状态">
        <Field label="分级理由" value={item.score_reason} />
        <Field label="LLM 建议" value={item.llm_score_suggestion} />
        <Field label="标签" value={item.lead_tags?.length ? item.lead_tags.join('、') : null} />
        <Field label="搜索关键词" value={item.search_keywords} />
        <Field label="状态" value={item.status} />
        <Field label="对接 BD" value={item.owner_bd} />
        <Field label="备注" value={item.notes} />
        <Field label="采集时间" value={item.created_at} />
      </Section>
    </>
  );
}

function TalentBody({ item }: { item: TalentLeadItem }) {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {item.tier ? <Pill tone={TIER_TONE[item.tier] || 'muted'}>{item.tier} 级</Pill> : <Pill tone="muted">未评级</Pill>}
        <span className="num text-xs font-semibold text-gray-900">评分 {item.score}</span>
      </div>

      <Section title="链接（点击打开）">
        <div className="space-y-2">
          {item.source_url ? <LinkRow url={item.source_url} sub="简历页" /> : null}
          {item.resume_download_url ? <LinkRow url={item.resume_download_url} sub="简历下载" /> : null}
          {!item.source_url && !item.resume_download_url && <div className="text-xs text-muted">暂无链接</div>}
        </div>
      </Section>

      <Section title="基本信息">
        <Field label="意向职位" value={item.desired_title} />
        <Field label="姓名" value={item.name_masked} />
        <Field label="城市" value={item.city} />
        <Field label="经验 / 学历" value={[item.experience, item.education].filter(Boolean).join(' / ')} />
        <Field label="专业" value={item.major} />
        <Field label="期望薪资" value={item.salary_expectation} />
        <Field label="合作类型" value={item.cooperation_type} />
        <Field label="简历摘要" value={item.raw_summary} />
      </Section>

      <Section title="联系方式">
        <Field label="邮箱" value={item.contact_email} mono />
        <Field label="电话" value={item.contact_phone} mono />
        <Field label="微信" value={item.wechat} mono />
      </Section>

      <Section title="评分与状态">
        <Field label="分级理由" value={item.score_reason} />
        <Field label="LLM 建议" value={item.llm_score_suggestion} />
        <Field label="状态" value={item.status} />
        <Field label="备注" value={item.notes} />
        <Field label="采集时间" value={item.created_at} />
      </Section>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h4 className="mb-1 text-xs font-semibold text-gray-700">{title}</h4>
      <div className="rounded-lg border border-line bg-white px-3">{children}</div>
    </div>
  );
}

export default function LeadDetailDrawer({ kind, id, onClose }: LeadDetailDrawerProps) {
  const companyQ = useCompanyLeadDetail(kind === 'company' ? id : null);
  const talentQ = useTalentLeadDetail(kind === 'talent' ? id : null);
  const q = kind === 'company' ? companyQ : talentQ;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!id) return null;
  const title = kind === 'company' ? '公司客户详情' : '人才详情';

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} aria-hidden />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-stone-50 shadow-xl">
        <div className="flex items-center justify-between border-b border-line bg-white px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-stone-100 hover:text-gray-900" aria-label="关闭">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <AsyncState loading={q.isLoading} error={q.error} height={300}>
            {kind === 'company' && companyQ.data?.item && <CompanyBody item={companyQ.data.item} />}
            {kind === 'talent' && talentQ.data?.item && <TalentBody item={talentQ.data.item} />}
          </AsyncState>
        </div>
      </aside>
    </>
  );
}
