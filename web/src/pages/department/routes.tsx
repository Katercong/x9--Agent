import { Route } from 'react-router-dom';
import Dashboard from './Dashboard';
import Creators from './Creators';
import Leads from './Leads';
import Emails from './Emails';
import Samples from './Samples';
import Videos from './Videos';
import Products from './Products';
import Settings from './Settings';
import CollectShop from './CollectShop';
import CollectLeads from './CollectLeads';
import CollectImport from './CollectImport';

export const departmentRoutes = (
  <>
    <Route path="/d/dashboard" element={<Dashboard />} />
    <Route path="/d/collect-shop" element={<CollectShop />} />
    <Route path="/d/collect-leads" element={<CollectLeads />} />
    <Route path="/d/collect-import" element={<CollectImport />} />
    <Route path="/d/creators" element={<Creators />} />
    <Route path="/d/leads" element={<Leads />} />
    <Route path="/d/emails" element={<Emails />} />
    <Route path="/d/samples" element={<Samples />} />
    <Route path="/d/videos" element={<Videos />} />
    <Route path="/d/products" element={<Products />} />
    <Route path="/d/settings" element={<Settings />} />
  </>
);
