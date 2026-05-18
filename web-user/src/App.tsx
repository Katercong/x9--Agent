import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import Business from './pages/Business';
import Dashboard from './pages/Dashboard';
import Collection from './pages/Collection';
import CreatorInfo from './pages/CreatorInfo';
import CollectShop from './pages/CollectShop';
import CollectLeads from './pages/CollectLeads';
import CollectImport from './pages/CollectImport';
import Recommendations from './pages/Recommendations';
import Review from './pages/Review';
import ExportImport from './pages/ExportImport';
import HotKeywords from './pages/HotKeywords';
import Assistant from './pages/Assistant';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/business" element={<Business />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/collection" element={<Collection />} />
        <Route path="/collect-shop" element={<CollectShop />} />
        <Route path="/collect-leads" element={<CollectLeads />} />
        <Route path="/collect-import" element={<CollectImport />} />
        <Route path="/creators-info" element={<CreatorInfo />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/review" element={<Review />} />
        <Route path="/export" element={<ExportImport />} />
        <Route path="/hotkw" element={<HotKeywords />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function NotFound() {
  return (
    <div className="flex items-center justify-center h-full text-muted">页面未找到</div>
  );
}
