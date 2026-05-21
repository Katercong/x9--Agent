// Routes for the v2 preview UI (/preview/*).
// Mounted alongside the existing /a /c /d routes so the old pages remain
// fully functional — this is purely additive.
import { Outlet, Route } from 'react-router-dom';
import Pulse from './Pulse';
import Me from './Me';
import Creators from './Creators';
import CreatorDetail from './CreatorDetail';

// Preview is open to any logged-in user (no RoleGuard) so the team can
// evaluate the new design across roles before we cut over.
export const previewRoutes = (
  <Route element={<Outlet />}>
    <Route path="/preview" element={<Pulse />} />
    <Route path="/preview/pulse" element={<Pulse />} />
    <Route path="/preview/me" element={<Me />} />
    <Route path="/preview/creators" element={<Creators />} />
    <Route path="/preview/creators/:platform/:handle" element={<CreatorDetail />} />
  </Route>
);
