import { Route } from 'react-router-dom';
import Monitor from './Monitor';
import Users from './Users';
import Llm from './Llm';
import Webhooks from './Webhooks';
import Audit from './Audit';
import Resources from './Resources';
import Queries from './Queries';
import ApiStats from './ApiStats';

export const superRoutes = (
  <>
    <Route path="/a/monitor" element={<Monitor />} />
    <Route path="/a/users" element={<Users />} />
    <Route path="/a/llm" element={<Llm />} />
    <Route path="/a/webhooks" element={<Webhooks />} />
    <Route path="/a/audit" element={<Audit />} />
    <Route path="/a/resources" element={<Resources />} />
    <Route path="/a/queries" element={<Queries />} />
    <Route path="/a/api-stats" element={<ApiStats />} />
  </>
);
