import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import Workbench from './pages/Workbench';
import Business from './pages/Business';
import Collection from './pages/Collection';
import CollectShop from './pages/CollectShop';
import CollectLeads from './pages/CollectLeads';
import CollectImport from './pages/CollectImport';
import Recommendations from './pages/Recommendations';
import RecommendationDetail from './pages/RecommendationDetail';
import ExportImport from './pages/ExportImport';
import HotKeywords from './pages/HotKeywords';
import Assistant from './pages/Assistant';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<Workbench />} />
        <Route path="/workbench" element={<Navigate to="/" replace />} />
        <Route path="/business" element={<Business />} />
        <Route path="/dashboard" element={<Navigate to="/collection" replace />} />
        <Route path="/collection" element={<Collection />} />
        <Route path="/collect-shop" element={<CollectShop />} />
        <Route path="/collect-leads" element={<CollectLeads />} />
        <Route path="/collect-import" element={<CollectImport />} />
        <Route path="/creators-info" element={<Navigate to="/recommendations" replace />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/recommendations/:creatorId" element={<RecommendationDetail />} />
        <Route path="/review" element={<Navigate to="/business" replace />} />
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
