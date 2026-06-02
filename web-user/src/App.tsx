import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import { useMe } from './hooks/useApi';
import Workbench from './pages/Workbench';
import Business from './pages/Business';
import Collection from './pages/Collection';
import CollectShop from './pages/CollectShop';
import CollectLeads from './pages/CollectLeads';
import CollectImport from './pages/CollectImport';
import Recommendations from './pages/Recommendations';
import RecommendationDetail from './pages/RecommendationDetail';
import OutreachArchive from './pages/OutreachArchive';
import ExportImport from './pages/ExportImport';
import HotKeywords from './pages/HotKeywords';
import Assistant from './pages/Assistant';
// 外贸部专属页面
import ForeignTradeBusiness from './pages/ForeignTradeBusiness';
import ForeignTradeCollection from './pages/ForeignTradeCollection';
import CollectJobs from './pages/CollectJobs';
import CollectSocial from './pages/CollectSocial';
import ForeignTradeImport from './pages/ForeignTradeImport';

function useIsForeignTrade() {
  const { data: me } = useMe();
  return me?.user?.department_code === 'foreign_trade';
}

// /business 与 /collection 按部门切换内容：外贸部 → 招聘+社媒；其余 → 原达人界面。
function BusinessByDept() {
  return useIsForeignTrade() ? <ForeignTradeBusiness /> : <Business />;
}
function CollectionByDept() {
  return useIsForeignTrade() ? <ForeignTradeCollection /> : <Collection />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<Workbench />} />
        <Route path="/workbench" element={<Navigate to="/" replace />} />
        <Route path="/business" element={<BusinessByDept />} />
        <Route path="/dashboard" element={<Navigate to="/collection" replace />} />
        <Route path="/collection" element={<CollectionByDept />} />
        {/* 跨境部采集 */}
        <Route path="/collect-shop" element={<CollectShop />} />
        <Route path="/collect-leads" element={<CollectLeads />} />
        <Route path="/collect-import" element={<CollectImport />} />
        <Route path="/hotkw" element={<HotKeywords />} />
        {/* 外贸部采集 */}
        <Route path="/collect-jobs" element={<CollectJobs />} />
        <Route path="/collect-social" element={<CollectSocial />} />
        <Route path="/ft-import" element={<ForeignTradeImport />} />
        {/* 共用 */}
        <Route path="/creators-info" element={<Navigate to="/recommendations" replace />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/recommendations/:creatorId" element={<RecommendationDetail />} />
        <Route path="/emails" element={<OutreachArchive />} />
        <Route path="/emails/:creatorId" element={<OutreachArchive />} />
        <Route path="/review" element={<Navigate to="/business" replace />} />
        <Route path="/export" element={<ExportImport />} />
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
