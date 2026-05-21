import { Outlet, Route } from 'react-router-dom';
import Overview from './Overview';
import Revenue from './Revenue';
import Departments from './Departments';
import Growth from './Growth';
import Funnel from './Funnel';
import Products from './Products';
import Creators from './Creators';
import Events from './Events';
import { RoleGuard } from '@/routes/RoleGuard';

// All /c/* paths are gated to the "company" view role. See routes/RoleGuard.tsx.
export const companyRoutes = (
  <Route element={<RoleGuard required="company"><Outlet /></RoleGuard>}>
    <Route path="/c/overview" element={<Overview />} />
    <Route path="/c/revenue" element={<Revenue />} />
    <Route path="/c/departments" element={<Departments />} />
    <Route path="/c/growth" element={<Growth />} />
    <Route path="/c/funnel" element={<Funnel />} />
    <Route path="/c/products" element={<Products />} />
    <Route path="/c/creators" element={<Creators />} />
    <Route path="/c/events" element={<Events />} />
  </Route>
);
