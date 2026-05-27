import { useState } from 'react';
import { Building, Users, KeyRound, Sliders } from 'lucide-react';
import { DataTable, type Column } from '@/components/table/DataTable';
import { PaginationControls } from '@/components/PaginationControls';
import { Pill } from '@/components/Pill';
import { AsyncState } from '@/components/states/States';
import { useStaff, useCreators, useProducts } from '@/hooks/useApi';
import { staffStats } from '@/lib/derive';

type StaffRow = ReturnType<typeof staffStats>[number];

const memberColumns: Column<StaffRow>[] = [
  {
    key: 'name', header: '成员',
    cell: (r) => (
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-medium">
          {r.name[0]}
        </div>
        <span className="text-xs font-medium">{r.name}</span>
      </div>
    ),
  },
  { key: 'role', header: '角色', cell: (r) => <Pill tone="info">{r.role || '—'}</Pill> },
  { key: 'contacted', header: '已联系', align: 'right', cell: (r) => <span className="text-xs num">{r.contacted}</span> },
  { key: 'confirmed', header: '已确认', align: 'right', cell: (r) => <span className="text-xs num">{r.confirmed}</span> },
  { key: 'samples', header: '寄样', align: 'right', cell: (r) => <span className="text-xs num">{r.samples}</span> },
  { key: 'videos', header: '视频', align: 'right', cell: (r) => <span className="text-xs num">{r.videos}</span> },
  { key: 'month', header: '统计月份', cell: (r) => <span className="text-xs text-muted">{r.month || '—'}</span> },
];

const PAGE_SIZE = 10;

export default function Settings() {
  const [page, setPage] = useState(0);
  const staff = useStaff({ limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const creators = useCreators({ limit: 1 });
  const products = useProducts({ limit: 1 });

  const rows = staff.data?.items ? staffStats(staff.data.items) : [];
  const memberCount = staff.data?.total ?? 0;
  const creatorTotal = creators.data?.total ?? 0;
  const productTotal = products.data?.total ?? 0;

  return (
    <div className="space-y-4">
      <div className="card card-body">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-md bg-brand-100 text-brand-600 flex items-center justify-center">
            <Building size={20} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-800">部门信息</h3>
            <div className="text-xs text-muted">数据源:staff / creators / products</div>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div>
            <div className="text-muted">部门成员</div>
            <div className="num mt-1 text-base font-semibold">{memberCount}</div>
          </div>
          <div>
            <div className="text-muted">管辖达人</div>
            <div className="num mt-1 text-base font-semibold">{creatorTotal}</div>
          </div>
          <div>
            <div className="text-muted">SKU 总数</div>
            <div className="num mt-1 text-base font-semibold">{productTotal}</div>
          </div>
          <div>
            <div className="text-muted">活跃 BD</div>
            <div className="num mt-1 text-base font-semibold">{rows.filter((r) => r.contacted > 0).length}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="px-4 py-3 flex items-center justify-between border-b border-line">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">BD 成员战绩</h3>
          </div>
          <button className="btn btn-primary">+ 添加成员</button>
        </div>
        <AsyncState loading={staff.isLoading} error={staff.error} isEmpty={rows.length === 0} height={200}>
          <DataTable columns={memberColumns} data={rows} rowKey={(r) => r.name} />
        </AsyncState>
        <PaginationControls
          page={page}
          pageSize={PAGE_SIZE}
          total={staff.data?.total ?? 0}
          currentCount={rows.length}
          loading={staff.isLoading}
          onPageChange={setPage}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-3">
            <Sliders size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">部门偏好</h3>
          </div>
          <div className="space-y-3 text-xs">
            <label className="flex items-center justify-between">
              <span>默认建联话术</span>
              <select className="border border-line rounded px-2 py-1">
                <option>初次建联 · 中文</option>
              </select>
            </label>
            <label className="flex items-center justify-between">
              <span>默认承运商</span>
              <select className="border border-line rounded px-2 py-1">
                <option>顺丰</option>
              </select>
            </label>
            <label className="flex items-center justify-between">
              <span>每日报送钉钉</span>
              <input type="checkbox" defaultChecked />
            </label>
          </div>
        </div>
        <div className="card card-body">
          <div className="flex items-center gap-2 mb-3">
            <KeyRound size={16} className="text-muted" />
            <h3 className="text-sm font-semibold text-gray-800">部门权限</h3>
          </div>
          <div className="space-y-2 text-xs">
            {[
              ['查看本部门数据', true],
              ['编辑本部门达人', true],
              ['编辑产品库', false],
              ['访问 LLM 配置', false],
              ['查看其他部门', false],
            ].map(([label, enabled]) => (
              <div key={label as string} className="flex items-center justify-between py-1.5 border-b border-line/60 last:border-0">
                <span>{label}</span>
                <Pill tone={enabled ? 'good' : 'muted'}>{enabled ? '已授权' : '未授权'}</Pill>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
