import React from 'react';
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { UIProvider } from './context/UIContext';
import { PreferencesProvider } from './context/PreferencesContext';
import { NotificationProvider, NotificationContainer, ToastContainer } from './components/ui';
import ErrorBoundary from './components/ui/ErrorBoundary';
import { router } from './router';

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <UIProvider>
        <AuthProvider>
          <PreferencesProvider>
            <NotificationProvider>
              <div id="app" className="min-h-screen transition-all duration-300 ease-in-out">
                <RouterProvider router={router} />
                <NotificationContainer />
                <ToastContainer />
              </div>
            </NotificationProvider>
          </PreferencesProvider>
        </AuthProvider>
      </UIProvider>
    </ErrorBoundary>
  );
};

export default App;
