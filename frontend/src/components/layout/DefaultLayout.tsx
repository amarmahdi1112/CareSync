import React from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useUI } from '../../context/UIContext';
import Sidebar from './Sidebar';
import Header from './Header';
import TopLoader from '../ui/TopLoader';

const DefaultLayout: React.FC = () => {
  const { state: authState } = useAuth();
  const { state: uiState, setSidebarOpen, toggleSidebar } = useUI();

  const handleCloseSidebar = () => {
    setSidebarOpen(false);
  };

  const handleToggleSidebar = () => {
    toggleSidebar();
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Top Loading Bar */}
      <TopLoader />
      
      {/* Sidebar - Only show for authenticated users */}
      {authState.isAuthenticated && (
        <Sidebar 
          open={uiState.sidebarOpen} 
          onClose={handleCloseSidebar} 
        />
      )}
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <Header onToggleSidebar={handleToggleSidebar} />
        
        {/* Main Content */}
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-gray-50">
          <div className="container mx-auto px-6 py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};

export default DefaultLayout;
