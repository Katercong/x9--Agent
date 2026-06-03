import { Outlet, Route } from 'react-router-dom';
import Dashboard from './Dashboard';
import Creators from './Creators';
import Leads from './Leads';
import Emails from './Emails';
import EmailAutoConsole from './EmailAutoConsole';
import Samples from './Samples';
import Videos from './Videos';
import Products from './Products';
import Settings from './Settings';
import CollectShop from './CollectShop';
import CollectLeads from './CollectLeads';
import CollectImport from './CollectImport';
// 外贸部专属页面
import ForeignTradeDashboard from './ForeignTradeDashboard';
import CollectJobs from './CollectJobs';
import CollectSocial from './CollectSocial';
import ForeignTradeImport from './ForeignTradeImport';
import CompanyLeads from './CompanyLeads';
import TalentLeads from './TalentLeads';
import SocialLeads from './SocialLeads';
import { useRoleStore } from '@/stores/roleStore';
import { RoleGuard } from '@/routes/RoleGuard';

// /d/dashboard 按登录用户部门切换：外贸部 → 招聘+社媒看板；其余 → 原达人看板。
function DepartmentDashboard() {
  const isForeignTrade = useRoleStore((s) => s.currentUser?.department_code === 'foreign_trade');
  return isForeignTrade ? <ForeignTradeDashboard /> : <Dashboard />;
}

// All /d/* paths are gated to the "department" view role. See routes/RoleGuard.tsx.
// Routes are the UNION of both departments' pages; the sidebar (menus.ts) decides
// which subset each department actually navigates to.
export const departmentRoutes = (
  <Route element={<RoleGuard required="department"><Outlet /></RoleGuard>}>
    <Route path="/d/dashboard" element={<DepartmentDashboard />} />
    {/* 跨境部（达人采集） */}
    <Route path="/d/collect-shop" element={<CollectShop />} />
    <Route path="/d/collect-leads" element={<CollectLeads />} />
    <Route path="/d/collect-import" element={<CollectImport />} />
    <Route path="/d/creators" element={<Creators />} />
    <Route path="/d/leads" element={<Leads />} />
    <Route path="/d/samples" element={<Samples />} />
    <Route path="/d/videos" element={<Videos />} />
    <Route path="/d/products" element={<Products />} />
    {/* 外贸部（招聘 + 社媒） */}
    <Route path="/d/collect-jobs" element={<CollectJobs />} />
    <Route path="/d/collect-social" element={<CollectSocial />} />
    <Route path="/d/ft-import" element={<ForeignTradeImport />} />
    <Route path="/d/company-leads" element={<CompanyLeads />} />
    <Route path="/d/talent-leads" element={<TalentLeads />} />
    <Route path="/d/social-leads" element={<SocialLeads />} />
    {/* 共用 */}
    <Route path="/d/emails" element={<Emails />} />
    <Route path="/d/email-auto" element={<EmailAutoConsole />} />
    <Route path="/d/settings" element={<Settings />} />
  </Route>
);
