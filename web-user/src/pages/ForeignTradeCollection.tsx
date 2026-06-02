import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  Briefcase,
  Chrome,
  Clock,
  Download,
  FileSpreadsheet,
  Heart,
  Radio,
  Users,
  Wand2,
  type LucideIcon,
} from 'lucide-react';
import { KpiCard } from '@/components/kpi/KpiCard';
import { AsyncState } from '@/components/states/States';
import { Pill } from '@/components/Pill';
import { useExtensionSessions, useRunProgress } from '@/hooks/useApi';
import { useForeignTradeCollection, useForeignTradeDashboard, type LeadChannel } from '@/api/foreignTrade';
import { ACCENTS, num, type Accent } from './collectShared';

export default function Collection() {
  const sessQ = useExtensionSessions();
  const progressQ = useRunProgress();
  const dashQ = useForeignTradeDashboard();

  const sessions = sessQ.data?.sessions ?? [];
  const onlineCount = sessions.filter((s: any) => s.online).length;
  const progressRows = (progressQ.data as any)?.items ?? [];
  const running = progressRows.some((row: any) => row?.running);
  const summary = dashQ.data?.summary;
  const totalLeads = (summary?.total_company_leads ?? 0) + (summary?.total_talent_leads ?? 0) + (summary?.total_social_leads ?? 0);

  return (
    <AsyncState loading={sessQ.isLoading} error={sessQ.error} height={400}>
      <div className="space-y-4">
        {/* 下载插件 — 外贸部采集从这里开始 */}
        <div className="card overflow-hidden">
          <div className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'rgb(6 182 212 / 0.18)', color: '#22d3ee' }}>
                <Download size={22} />
              </div>
              <div className="min-w-0">
                <div className="text-base font-bold text-text">下载采集插件</div>
                <div className="text-xs text-muted mt-0.5">安装浏览器插件后，在招聘网站 / 小红书 / 抖音 页面一键采集线索</div>
              </div>
            </div>
            <a
              href="/api/local/extension/download"
              className="btn shrink-0 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white"
              style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' }}
            >
              <Download size={16} /> 下载插件
            </a>
          </div>
          <div className="h-1 w-full" style={{ background: '#22d3ee' }} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard
            label="插件在线"
            value={onlineCount > 0 ? `${onlineCount}` : '离线'}
            icon={Chrome}
            iconBg={onlineCount > 0 ? 'rgb(34 197 94 / 0.18)' : 'rgb(134 145 162 / 0.18)'}
            iconColor={onlineCount > 0 ? '#22c55e' : '#8691a2'}
          />
          <KpiCard
            label="当前任务"
            value={running ? '运行中' : '空闲'}
            icon={Radio}
            iconBg={running ? 'rgb(6 182 212 / 0.18)' : 'rgb(134 145 162 / 0.18)'}
            iconColor={running ? '#22d3ee' : '#8691a2'}
          />
          <KpiCard
            label="今日新增"
            value={num(summary?.today_new ?? 0)}
            icon={Clock}
            iconBg="rgb(99 102 241 / 0.16)"
            iconColor="#818cf8"
            subLabel="所有渠道累计"
          />
          <KpiCard
            label="线索总量"
            value={num(totalLeads)}
            icon={Users}
            iconBg="rgb(124 58 237 / 0.16)"
            iconColor="#a78bfa"
          />
        </div>

        <section>
          <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="sec-title !mb-0">数据采集总览</h3>
            <span className="text-xxs text-muted">招聘网站 / 小红书抖音 / 表格导入 三类采集渠道统一入口</span>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
            <ChannelCard icon={Briefcase} accent={ACCENTS.jobs} title="招聘网站采集" subtitle="51job / 智联 / 大泉州" to="/collect-jobs" channel="jobs" />
            <ChannelCard icon={Heart} accent={ACCENTS.social} title="小红书 / 抖音采集" subtitle="博主 / 笔记 / 评论 · 采购意向" to="/collect-social" channel="social" />
            <CleaningChannelCard />
            <ImportChannelCard />
          </div>
        </section>
      </div>
    </AsyncState>
  );
}

function ChannelCard({
  icon: Icon,
  accent,
  title,
  subtitle,
  to,
  channel,
}: {
  icon: LucideIcon;
  accent: Accent;
  title: string;
  subtitle: string;
  to: string;
  channel: LeadChannel;
}) {
  const feed = useForeignTradeCollection({ channel, limit: 1 });
  const stats = feed.data?.stats ?? {};
  const total = Number(stats.total ?? 0);
  const today = Number(stats.today ?? 0);
  const active = total > 0 || today > 0;

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-md flex items-center justify-center shrink-0" style={{ background: accent.dim, color: accent.key }}>
              <Icon size={19} />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-text truncate">{title}</h4>
              <div className="text-xxs text-muted truncate">{subtitle}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Pill tone={active ? 'good' : 'muted'}>{active ? '有数据' : '等待数据'}</Pill>
            <Link to={to} className="chip text-xxs">详情 <ArrowUpRight size={11} /></Link>
          </div>
        </div>
      </div>
      <div className="p-4">
        <div className="grid grid-cols-2 gap-2">
          <Tile label="总线索" value={num(total)} accent={accent} />
          <Tile label="今日采集" value={num(today)} accent={accent} />
        </div>
      </div>
      <div className="h-1" style={{ background: accent.key }} />
    </div>
  );
}

function CleaningChannelCard() {
  const accent = ACCENTS.social;
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-md flex items-center justify-center shrink-0" style={{ background: accent.dim, color: accent.key }}>
              <Wand2 size={19} />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-text truncate">数据清洗</h4>
              <div className="text-xxs text-muted truncate">重新清洗 / 联系方式 / GPT 判定</div>
            </div>
          </div>
          <Link to="/ft-cleaning" className="chip text-xxs shrink-0">详情 <ArrowUpRight size={11} /></Link>
        </div>
      </div>
      <div className="p-4 text-xs text-muted">招聘线索评分、社媒联系方式提取、原始快照补处理。</div>
      <div className="h-1" style={{ background: accent.key }} />
    </div>
  );
}

function ImportChannelCard() {
  const accent = ACCENTS.import;
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-md flex items-center justify-center shrink-0" style={{ background: accent.dim, color: accent.key }}>
              <FileSpreadsheet size={19} />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-text truncate">表格导入</h4>
              <div className="text-xxs text-muted truncate">CSV / XLSX 批量导入线索</div>
            </div>
          </div>
          <Link to="/ft-import" className="chip text-xxs shrink-0">详情 <ArrowUpRight size={11} /></Link>
        </div>
      </div>
      <div className="p-4 text-xs text-muted">支持下载模板、字段映射与入库前预检，导入后自动评分分级。</div>
      <div className="h-1" style={{ background: accent.key }} />
    </div>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent: Accent }) {
  return (
    <div className="rounded-md border border-border px-3 py-2" style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}>
      <div className="text-xxs text-muted">{label}</div>
      <div className="text-base font-semibold num mt-1" style={{ color: accent.key }}>{value}</div>
    </div>
  );
}
