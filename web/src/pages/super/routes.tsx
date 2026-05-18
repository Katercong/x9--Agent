import { Route } from 'react-router-dom';
import Monitor from './Monitor';
import Users from './Users';
import Llm from './Llm';
import Webhooks from './Webhooks';
import Audit from './Audit';
import Resources from './Resources';
import Queries from './Queries';
import ApiStats from './ApiStats';
import CompanyOverview from '../company/Overview';
import CollectShop from '../department/CollectShop';
import CollectLeads from '../department/CollectLeads';
import CollectImport from '../department/CollectImport';

export const superRoutes = (
  <>
    <Route path="/a/dashboard" element={<CompanyOverview />} />
    <Route path="/a/monitor" element={<Monitor />} />
    <Route path="/a/collect-shop" element={<CollectShop />} />
    <Route path="/a/collect-leads" element={<CollectLeads />} />
    <Route path="/a/collect-import" element={<CollectImport />} />
    <Route path="/a/users" element={<Users />} />
    <Route path="/a/llm" element={<Llm />} />
    <Route path="/a/webhooks" element={<Webhooks />} />
    <Route path="/a/audit" element={<Audit />} />
    <Route path="/a/resources" element={<Resources />} />
    <Route path="/a/queries" element={<Queries />} />
    <Route path="/a/api-stats" element={<ApiStats />} />
  </>
);
