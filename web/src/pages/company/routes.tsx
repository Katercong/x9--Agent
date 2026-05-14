import { Route } from 'react-router-dom';
import Overview from './Overview';
import Revenue from './Revenue';
import Departments from './Departments';
import Growth from './Growth';
import Funnel from './Funnel';
import Products from './Products';
import Creators from './Creators';
import Events from './Events';

export const companyRoutes = (
  <>
    <Route path="/c/overview" element={<Overview />} />
    <Route path="/c/revenue" element={<Revenue />} />
    <Route path="/c/departments" element={<Departments />} />
    <Route path="/c/growth" element={<Growth />} />
    <Route path="/c/funnel" element={<Funnel />} />
    <Route path="/c/products" element={<Products />} />
    <Route path="/c/creators" element={<Creators />} />
    <Route path="/c/events" element={<Events />} />
  </>
);
