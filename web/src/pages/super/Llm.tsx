import { Plus, Zap, CheckCircle2, AlertTriangle, HelpCircle, Star, XCircle } from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { useLlmProviders } from '@/hooks/useApi';

const testIcon: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  ok: { icon: CheckCircle2, color: '#16a34a' },
  warn: { icon: AlertTriangle, color: '#f5a623' },
  error: { icon: XCircle, color: '#ef4444' },
  unknown: { icon: HelpCircle, color: '#86909c' },
};

export default function Llm() {
  const { data, isLoading, error } = useLlmProviders();
  const providers = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-line">
          <h3 className="text-sm font-semibold text-gray-800">Provider 管理</h3>
          <span className="text-xxs text-muted">{providers.length} 个 Provider</span>
          <div className="ml-auto">
            <button className="btn btn-primary"><Plus size={12} />新增 Provider</button>
          </div>
        </div>
        <AsyncState loading={isLoading} error={error} isEmpty={providers.length === 0} height={300}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-4">
            {providers.map((p) => {
              const status = p.last_test_status || 'unknown';
              const meta = testIcon[status] || testIcon.unknown;
              const TestIcon = meta.icon;
              return (
                <div
                  key={p.code}
                  className={`border rounded-lg p-4 ${p.is_active === 1 ? 'border-brand-500 bg-brand-50/30' : 'border-line'}`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-9 h-9 rounded-md bg-soft flex items-center justify-center">
                        <Zap size={16} className="text-brand-500" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold">{p.display_name}</span>
                          {p.is_active === 1 && (
                            <span className="pill bg-amber-100 text-amber-700 text-xxs">
                              <Star size={9} className="inline mr-0.5" />当前活跃
                            </span>
                          )}
                          {p.enabled === 0 && <span className="pill pill-muted text-xxs">已禁用</span>}
                        </div>
                        <div className="text-xxs text-muted font-mono mt-0.5">{p.code} · {p.type}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <TestIcon size={16} style={{ color: meta.color }} />
                      <span className="text-xxs" style={{ color: meta.color }}>{status}</span>
                    </div>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex gap-2">
                      <span className="text-muted w-16 shrink-0">Base URL</span>
                      <span className="font-mono truncate">{p.base_url || '—'}</span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-muted w-16 shrink-0">默认模型</span>
                      <span className="font-mono">{p.default_model || '—'}</span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-muted w-16 shrink-0">最近测试</span>
                      <span className="text-muted">{p.last_tested_at || '从未'}</span>
                    </div>
                    {p.last_test_message && (
                      <div className="flex gap-2">
                        <span className="text-muted w-16 shrink-0">消息</span>
                        <span className="text-xxs text-bad truncate">{p.last_test_message}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-line">
                    <button className="chip text-xxs">编辑</button>
                    <button className="chip text-xxs">测试</button>
                    {p.is_active !== 1 && <button className="chip text-xxs text-brand-500">激活</button>}
                  </div>
                </div>
              );
            })}
          </div>
        </AsyncState>
      </div>

      <div className="card card-body">
        <h3 className="text-sm font-semibold text-gray-800 mb-3">Feature 绑定</h3>
        <div className="text-xs text-muted">通过后端 <code className="font-mono">/api/v1/llm/features</code> 查询(占位)。当前活跃 Provider 自动承担所有功能。</div>
      </div>
    </div>
  );
}
