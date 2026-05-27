import { Outlet, Route } from 'react-router-dom';
import Monitor from './Monitor';
import Users from './Users';
import UserDetail from './UserDetail';
import Llm from './Llm';
import Webhooks from './Webhooks';
import Audit from './Audit';
import Resources from './Resources';
import Queries from './Queries';
import ApiStats from './ApiStats';
import CompanyOverview from '../company/Overview';
import Emails from '../department/Emails';
import CollectShop from '../department/CollectShop';
import CollectLeads from '../department/CollectLeads';
import CollectImport from '../department/CollectImport';
import { RoleGuard } from '@/routes/RoleGuard';

// Layout Route wraps every /a/* path in <RoleGuard required="super"> so URL
// navigation by a non-super_admin user bounces back to their own home before
// the page ever renders. AuthGate also catches this on first load, but this
// is the defense-in-depth layer.
export const superRoutes = (
  <Route element={<RoleGuard required="super"><Outlet /></RoleGuard>}>
    <Route path="/a/dashboard" element={<CompanyOverview />} />
    <Route path="/a/monitor" element={<Monitor />} />
    <Route path="/a/collect-shop" element={<CollectShop />} />
    <Route path="/a/collect-leads" element={<CollectLeads />} />
    <Route path="/a/collect-import" element={<CollectImport />} />
    <Route path="/a/emails" element={<Emails />} />
    <Route path="/a/users" element={<Users />} />
    <Route path="/a/users/:id" element={<UserDetail />} />
    <Route path="/a/llm" element={<Llm />} />
    <Route path="/a/webhooks" element={<Webhooks />} />
    <Route path="/a/audit" element={<Audit />} />
    <Route path="/a/resources" element={<Resources />} />
    <Route path="/a/queries" element={<Queries />} />
    <Route path="/a/api-stats" element={<ApiStats />} />
  </Route>
);
