import { Link } from 'react-router-dom';
import { ArrowDownToLine, ArrowUpRight, FileSpreadsheet, Filter } from 'lucide-react';

const exportOptions = [
  {
    name: '推荐达人 · 全量',
    desc: '所有已生成推荐的达人，含评分、理由、邮箱等字段',
    url: '/api/local/export/recommended-creators.csv',
    format: 'CSV',
  },
  {
    name: '推荐达人 · 仅 P1/P2',
    desc: '只导出优先级 P1/P2 的高质量推荐',
    url: '/api/local/export/recommended-creators.csv?priority=p1p2',
    format: 'CSV',
  },
  {
    name: '所有达人',
    desc: '当前部门下全部达人快照',
    url: '/api/local/export/creators.csv',
    format: 'CSV',
  },
];

const importTemplates = [
  {
    name: '达人导入模板 · Excel',
    desc: '必填字段：handle / platform。可选：tier / followers / email 等',
    url: '/api/local/import/creators/template.xlsx',
    format: 'XLSX',
  },
  {
    name: '达人导入模板 · CSV',
    desc: '轻量模板，适合从表格工具快速整理后导入',
    url: '/api/local/import/creators/template.csv',
    format: 'CSV',
  },
];

export default function ExportImport() {
  return (
    <div className="space-y-4">
      <section className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-border">
          <ArrowDownToLine size={16} className="text-accent" />
          <h3 className="text-sm font-semibold">数据导出</h3>
          <span className="text-xxs text-muted">基于当前部门权限范围</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4">
          {exportOptions.map((opt) => (
            <a
              key={opt.name}
              href={opt.url}
              className="border border-border rounded-md p-4 hover:border-accent transition-colors"
              style={{ background: 'rgb(var(--bg-elev-2))' }}
            >
              <div className="flex items-center gap-2 mb-2">
                <FileSpreadsheet size={16} className="text-accent" />
                <span className="text-sm font-medium">{opt.name}</span>
                <span className="pill pill-info ml-auto text-xxs">{opt.format}</span>
              </div>
              <div className="text-xxs text-muted leading-relaxed">{opt.desc}</div>
            </a>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-border">
          <FileSpreadsheet size={16} className="text-accent" />
          <h3 className="text-sm font-semibold">导入模板</h3>
          <span className="text-xxs text-muted">正式导入统一进入“采集 · 表格导入”</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {importTemplates.map((item) => (
              <a
                key={item.name}
                href={item.url}
                className="border border-border rounded-md p-4 hover:border-accent transition-colors"
                style={{ background: 'rgb(var(--bg-elev-2))' }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <FileSpreadsheet size={16} className="text-muted" />
                  <span className="text-sm font-medium">{item.name}</span>
                  <span className="pill pill-muted text-xxs ml-auto">{item.format}</span>
                </div>
                <div className="text-xxs text-muted leading-relaxed">{item.desc}</div>
              </a>
            ))}
          </div>
          <div
            className="border border-border rounded-md p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
            style={{ background: 'rgb(var(--bg-elev-2) / 0.45)' }}
          >
            <div>
              <div className="text-sm font-medium">需要上传 CSV / XLSX？</div>
              <div className="text-xxs text-muted mt-1">上传入口只保留一处，避免和数据工具页重复。</div>
            </div>
            <Link to="/collect-import" className="btn btn-primary w-fit">
              前往表格导入 <ArrowUpRight size={12} />
            </Link>
          </div>
        </div>
      </section>

      <section className="card card-body">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={14} className="text-muted" />
          <h3 className="text-sm font-semibold">高级筛选导出</h3>
        </div>
        <div className="text-xs text-muted">后续可加自定义条件：Tier / 国家 / 评分区间 / 标签，一键导出 CSV。</div>
      </section>
    </div>
  );
}
