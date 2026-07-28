import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from 'styled-components';
import App from './App';
import { GlobalStyle } from './styles/GlobalStyle';
import { theme } from './styles/theme';
import { SessionProvider } from './auth/SessionContext';
import { AppErrorBoundary } from './components/system/AppErrorBoundary';
import { MotionProvider } from './motion';
import { RealtimeProvider } from './realtime/RealtimeContext';
import { ChildcareCommandRecoveryProvider } from './childcare-commands/ChildcareCommandRecoveryContext';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <GlobalStyle />
      <BrowserRouter>
        <AppErrorBoundary>
          <SessionProvider>
            <ChildcareCommandRecoveryProvider>
              <RealtimeProvider>
                <MotionProvider>
                  <App />
                </MotionProvider>
              </RealtimeProvider>
            </ChildcareCommandRecoveryProvider>
          </SessionProvider>
        </AppErrorBoundary>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
