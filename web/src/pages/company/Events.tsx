import { CheckCircle2, AlertTriangle, Info, AlertOctagon } from 'lucide-react';
import { Pill } from '@/components/Pill';
import { importantEvents } from '@/mock/company';

const levelMeta: Record<string, { icon: typeof CheckCircle2; bg: string; color: string }> = {
  good: { icon: CheckCircle2, bg: '#d1fae5', color: '#16a34a' },
  info: { icon: Info, bg: '#dbeafe', color: '#2563eb' },
  warn: { icon: AlertTriangle, bg: '#fef3c7', color: '#ca8a04' },
  bad: { icon: AlertOctagon, bg: '#fee2e2', color: '#dc2626' },
};

export default function Events() {
  return (
    <div className="space-y-4">
      <div className="card card-body">
        <div className="flex items-center gap-2 mb-4">
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部部门</option>
            <option>女性护理部</option>
            <option>母婴护理部</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部类型</option>
            <option>签约</option>
            <option>里程碑</option>
            <option>异常</option>
            <option>运营</option>
          </select>
          <select className="text-xs border border-line rounded px-2 py-1.5 bg-white">
            <option>全部严重度</option>
            <option>good</option>
            <option>info</option>
            <option>warn</option>
            <option>bad</option>
          </select>
        </div>

        <div className="relative pl-7 ml-4">
          <div className="absolute left-0 top-2 bottom-2 w-px bg-line" />
          {importantEvents.map((e, i) => {
            const meta = levelMeta[e.level] || levelMeta.info;
            const Icon = meta.icon;
            return (
              <div key={i} className="relative pb-5 last:pb-0">
                <div
                  className="absolute -left-7 w-5 h-5 rounded-full flex items-center justify-center"
                  style={{ background: meta.bg, color: meta.color }}
                >
                  <Icon size={11} />
                </div>
                <div className="flex items-center gap-3 mb-1.5 flex-wrap">
                  <span className="text-xs font-medium text-gray-800">{e.date}</span>
                  <Pill tone={e.level === 'good' ? 'good' : e.level === 'warn' ? 'warn' : e.level === 'bad' ? 'bad' : 'info'}>{e.type}</Pill>
                  <span className="text-xxs text-muted">{e.dept}</span>
                </div>
                <div className="text-xs text-gray-700">{e.title}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
