import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import { departmentRoutes } from './pages/department/routes';
import { companyRoutes } from './pages/company/routes';
import { superRoutes } from './pages/super/routes';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<Navigate to="/d/dashboard" replace />} />
        {departmentRoutes}
        {companyRoutes}
        {superRoutes}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function NotFound() {
  return (
    <div className="flex items-center justify-center h-full text-muted">
      页面未找到
    </div>
  );
}
