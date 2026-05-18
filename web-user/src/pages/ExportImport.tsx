import { useState } from 'react';
import { ArrowDownToLine, ArrowUpToLine, FileSpreadsheet, FileText, Filter } from 'lucide-react';

const exportOptions = [
  {
    name: '推荐达人 · 全量',
    desc: '所有已生成推荐的达人,含评分、理由、邮箱等字段',
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
  { name: '达人导入模板', desc: '必填字段:handle / platform。可选:tier / followers / email 等', url: '/api/local/import/template.csv' },
];

export default function ExportImport() {
  const [importing, setImporting] = useState(false);

  const onUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    const fd = new FormData();
    fd.append('file', file);
    fetch('/api/local/import/creators', { method: 'POST', body: fd, credentials: 'include' })
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (r.ok) {
          alert(`✓ 导入成功:${j.imported || j.count || 0} 行`);
        } else {
          alert(`✗ 导入失败:${j.detail || r.statusText}`);
        }
      })
      .catch((e) => alert(`✗ 导入失败:${e.message}`))
      .finally(() => {
        setImporting(false);
        e.target.value = '';
      });
  };

  return (
    <div className="space-y-4">
      {/* Export */}
      <div className="card">
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
      </div>

      {/* Import */}
      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-border">
          <ArrowUpToLine size={16} className="text-accent" />
          <h3 className="text-sm font-semibold">数据导入</h3>
          <span className="text-xxs text-muted">CSV / Excel 批量上传</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {importTemplates.map((tpl) => (
              <a
                key={tpl.name}
                href={tpl.url}
                className="border border-border rounded-md p-4 hover:border-accent transition-colors"
                style={{ background: 'rgb(var(--bg-elev-2))' }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <FileText size={16} className="text-muted" />
                  <span className="text-sm font-medium">{tpl.name}</span>
                  <span className="pill pill-muted ml-auto text-xxs">模板</span>
                </div>
                <div className="text-xxs text-muted leading-relaxed">{tpl.desc}</div>
              </a>
            ))}
          </div>
          <div className="border border-dashed border-border rounded-md p-6 text-center">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={onUpload}
              disabled={importing}
              className="hidden"
              id="import-file"
            />
            <label htmlFor="import-file" className="btn btn-primary cursor-pointer">
              {importing ? '上传中...' : '选择 CSV / Excel 文件上传'}
            </label>
            <div className="text-xxs text-muted mt-2">支持 .csv / .xlsx / .xls,建议先下载模板填好再上传</div>
          </div>
        </div>
      </div>

      {/* Filter shortcuts */}
      <div className="card card-body">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={14} className="text-muted" />
          <h3 className="text-sm font-semibold">高级筛选导出(占位)</h3>
        </div>
        <div className="text-xs text-muted">后续可加自定义条件:Tier / 国家 / 评分区间 / 标签 → 一键导出 CSV</div>
      </div>
    </div>
  );
}
