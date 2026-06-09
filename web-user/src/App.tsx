import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import { useMe } from './hooks/useApi';
import Workbench from './pages/Workbench';
import Business from './pages/Business';
import Collection from './pages/Collection';
import CollectShop from './pages/CollectShop';
import CollectLeads from './pages/CollectLeads';
import CollectImport from './pages/CollectImport';
import CustomerCollection from './pages/CustomerCollection';
import Recommendations from './pages/Recommendations';
import ForeignTradeRecommendations from './pages/ForeignTradeRecommendations';
import ForeignTradeSocialUserDetail from './pages/ForeignTradeSocialUserDetail';
import RecommendationDetail from './pages/RecommendationDetail';
import OutreachArchive from './pages/OutreachArchive';
import ForeignTradeFollowups from './pages/ForeignTradeFollowups';
import ExportImport from './pages/ExportImport';
import HotKeywords from './pages/HotKeywords';
import Assistant from './pages/Assistant';
import ForeignTradeBusiness from './pages/ForeignTradeBusiness';
import ForeignTradeCollection from './pages/ForeignTradeCollection';
import CollectJobs from './pages/CollectJobs';
import CollectSocial from './pages/CollectSocial';
import ForeignTradeCleaning from './pages/ForeignTradeCleaning';
import ForeignTradeImport from './pages/ForeignTradeImport';

function useIsForeignTrade() {
  const { data: me } = useMe();
  return me?.user?.department_code === 'foreign_trade';
}

function BusinessByDept() {
  return useIsForeignTrade() ? <ForeignTradeBusiness /> : <Business />;
}

function CollectionByDept() {
  return useIsForeignTrade() ? <ForeignTradeCollection /> : <Collection />;
}

function RecommendationsByDept() {
  return useIsForeignTrade() ? <ForeignTradeRecommendations /> : <Recommendations />;
}

function EmailsByDept() {
  return useIsForeignTrade() ? <ForeignTradeFollowups /> : <OutreachArchive />;
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
        <Route path="/collect-shop" element={<CollectShop />} />
        <Route path="/collect-leads" element={<CollectLeads />} />
        <Route path="/collect-import" element={<CollectImport />} />
        <Route path="/customer-collection" element={<CustomerCollection />} />
        <Route path="/hotkw" element={<HotKeywords />} />
        <Route path="/collect-jobs" element={<CollectJobs />} />
        <Route path="/collect-social" element={<CollectSocial />} />
        <Route path="/ft-cleaning" element={<ForeignTradeCleaning />} />
        <Route path="/ft-import" element={<ForeignTradeImport />} />
        <Route path="/creators-info" element={<Navigate to="/recommendations" replace />} />
        <Route path="/recommendations" element={<RecommendationsByDept />} />
        <Route path="/ft-recommendations-preview" element={<ForeignTradeRecommendations />} />
        <Route path="/social-users/:userId" element={<ForeignTradeSocialUserDetail />} />
        <Route path="/recommendations/:creatorId" element={<RecommendationDetail />} />
        <Route path="/emails" element={<EmailsByDept />} />
        <Route path="/ft-followups-preview" element={<ForeignTradeFollowups />} />
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
    <div className="flex h-full items-center justify-center text-muted">页面未找到</div>
  );
}
