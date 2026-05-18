import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import FloatingAssistant from '@/components/FloatingAssistant';

export default function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-y-auto bg-soft">
          <div className="p-3 md:p-5">
            <Outlet />
          </div>
        </main>
      </div>
      <FloatingAssistant />
    </div>
  );
}
