import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import styled, { keyframes, ThemeProvider } from 'styled-components';
import { AppShell } from './components/shell/AppShell';
import { CareSyncMark } from './components/brand/CareSyncMark';
import { isFeatureEnabled, type FeatureId } from './config/productFeatures';
import { canAccessFeature } from './auth/accessModel';
import { useSession } from './auth/SessionContext';
import { OnboardingGuard, ProtectedRoute } from './auth/RouteGuards';
import { workspaceTheme } from './styles/theme';
import { TransportRegistryCapabilityProvider, useTransportRegistryCapability } from './features/transport-registry/capability';
import { BillingCapabilityProvider, useBillingCapability } from './features/billing/billingCapability';

const DashboardPage = lazy(() => import('./features/dashboard/DashboardPage'));
const AdmissionsPage = lazy(() => import('./features/admissions'));
const AdmissionApplicationPage = lazy(() => import('./features/admissions/AdmissionApplicationPage'));
const TodayPage = lazy(() => import('./features/daily-care'));
const MedicationsPage = lazy(() => import('./features/medications'));
const IncidentsPage = lazy(() => import('./features/incidents'));
const SchedulingPage = lazy(() => import('./features/scheduling/SchedulingPage'));
const FamiliesPage = lazy(() => import('./features/families'));
const FamilyProfilePage = lazy(() => import('./features/families/FamilyProfilePage'));
const ChildrenPage = lazy(() => import('./features/children'));
const ChildProfilePage = lazy(() => import('./features/children/ChildProfilePage'));
const RoomsPage = lazy(() => import('./features/rooms'));
const AttendancePage = lazy(() => import('./features/attendance'));
const SettingsPage = lazy(() => import('./features/settings'));
const StaffPage = lazy(() => import('./features/staff'));
const StaffRotaPage = lazy(() => import('./features/staff-rota'));
const JobsPage = lazy(() => import('./features/hiring'));
const BillingPage = lazy(() => import('./features/billing/BillingPage'));
const TransportRegistryPage = lazy(() => import('./features/transport-registry'));
const ModulePage = lazy(() => import('./features/modules/ModulePage'));
const NotFoundPage = lazy(() => import('./features/system/NotFoundPage'));
const LoginPage = lazy(() => import('./features/auth/LoginPage'));
const RegisterPage = lazy(() => import('./features/auth/RegisterPage'));
const StaffActivationPage = lazy(() => import('./features/auth/StaffActivationPage'));
const PasswordResetPage = lazy(() => import('./features/auth/PasswordResetPage'));
const AccessDeniedPage = lazy(() => import('./features/system/AccessDeniedPage'));
const OnboardingPage = lazy(() => import('./features/onboarding/OnboardingPage'));
const LandingPage = lazy(() => import('./features/public/LandingPage'));
const ProductPage = lazy(() => import('./features/public/ProductPage'));
const PricingPage = lazy(() => import('./features/public/PricingPage'));
const SecurityPage = lazy(() => import('./features/public/SecurityPage'));

const breathe = keyframes`0%,100% { opacity: .55; transform: scale(.94); } 50% { opacity: 1; transform: scale(1.05); }`;
const Loading = styled.div`
  display: grid;
  min-height: 100vh;
  place-items: center;
  color: ${({ theme }) => theme.color.textMuted};
  text-align: center;
  svg { margin: 0 auto 12px; animation: ${breathe} 1.8s ease-in-out infinite; }
  p { margin: 0; font-size: .75rem; letter-spacing: .1em; text-transform: uppercase; }
`;

const workspaceSegments = new Set([
  'onboarding', 'dashboard', 'admissions', 'today', 'families', 'children', 'rooms', 'attendance', 'medications', 'incidents', 'staff', 'staff-rota', 'jobs', 'billing', 'transport-registry', 'settings',
  'scheduling', 'claims', 'files', 'invoicing', 'letterhead', 'activity', 'support', 'ai',
]);

function RouteEffects() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
    const main = document.getElementById('main-content');
    main?.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}

function Loader() {
  const { pathname } = useLocation();
  const segment = pathname.split('/').filter(Boolean)[0] || '';
  const content = <Loading role="status"><div><CareSyncMark size={58} /><p>Synchronizing interface</p></div></Loading>;
  return workspaceSegments.has(segment) ? <WorkspaceThemeScope>{content}</WorkspaceThemeScope> : content;
}

function FeatureRoute({ featureId, children }: { featureId: FeatureId; children: ReactNode }) {
  const session = useSession();
  if (!isFeatureEnabled(featureId)) return <NotFoundPage />;
  return canAccessFeature(session.user, featureId) ? children : <AccessDeniedPage />;
}

function TransportRegistryRoute({ children }: { children: ReactNode }) {
  const capability = useTransportRegistryCapability();
  if (capability.phase === 'checking') return <Loading role="status"><div><CareSyncMark size={42} /><p>Confirming registry access</p></div></Loading>;
  if (!capability.enabled) return <NotFoundPage />;
  return <FeatureRoute featureId="transport-registry">{children}</FeatureRoute>;
}

function BillingRoute({ children }: { children: ReactNode }) {
  const capability = useBillingCapability();
  if (capability.phase === 'checking') return <Loading role="status"><div><CareSyncMark size={42} /><p>Confirming billing access</p></div></Loading>;
  if (!capability.enabled) return <NotFoundPage />;
  return <FeatureRoute featureId="billing">{children}</FeatureRoute>;
}

function WorkspaceThemeScope({ children }: { children: ReactNode }) {
  useEffect(() => {
    const previousBody = document.body.dataset.caresyncTheme;
    const previousHtml = document.documentElement.dataset.caresyncTheme;
    document.body.dataset.caresyncTheme = 'workspace';
    document.documentElement.dataset.caresyncTheme = 'workspace';
    return () => {
      if (previousBody) document.body.dataset.caresyncTheme = previousBody;
      else delete document.body.dataset.caresyncTheme;
      if (previousHtml) document.documentElement.dataset.caresyncTheme = previousHtml;
      else delete document.documentElement.dataset.caresyncTheme;
    };
  }, []);

  return <ThemeProvider theme={workspaceTheme}>{children}</ThemeProvider>;
}

export default function App() {
  return (
    <Suspense fallback={<Loader />}>
      <RouteEffects />
      <Routes>
        <Route index element={<LandingPage />} />
        <Route path="product" element={<ProductPage />} />
        <Route path="pricing" element={<PricingPage />} />
        <Route path="security" element={<SecurityPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="activate-staff" element={<StaffActivationPage />} />
        <Route path="reset-password" element={<PasswordResetPage />} />
        <Route path="onboarding" element={<ProtectedRoute><WorkspaceThemeScope><OnboardingPage /></WorkspaceThemeScope></ProtectedRoute>} />
        <Route element={<ProtectedRoute><WorkspaceThemeScope><TransportRegistryCapabilityProvider><BillingCapabilityProvider><OnboardingGuard><AppShell /></OnboardingGuard></BillingCapabilityProvider></TransportRegistryCapabilityProvider></WorkspaceThemeScope></ProtectedRoute>}>
          <Route path="dashboard" element={<FeatureRoute featureId="dashboard"><DashboardPage /></FeatureRoute>} />
          <Route path="admissions" element={<FeatureRoute featureId="admissions"><AdmissionsPage /></FeatureRoute>} />
          <Route path="admissions/applications/:applicationId" element={<FeatureRoute featureId="admissions"><AdmissionApplicationPage /></FeatureRoute>} />
          <Route path="admissions/*" element={<NotFoundPage />} />
          <Route path="today" element={<FeatureRoute featureId="today"><TodayPage /></FeatureRoute>} />
          <Route path="today/*" element={<NotFoundPage />} />
          <Route path="medications" element={<FeatureRoute featureId="medications"><MedicationsPage /></FeatureRoute>} />
          <Route path="medications/*" element={<NotFoundPage />} />
          <Route path="incidents" element={<FeatureRoute featureId="incidents"><IncidentsPage /></FeatureRoute>} />
          <Route path="incidents/*" element={<NotFoundPage />} />
          <Route path="families" element={<FeatureRoute featureId="families"><FamiliesPage /></FeatureRoute>} />
          <Route path="families/:familyId" element={<FeatureRoute featureId="families"><FamilyProfilePage /></FeatureRoute>} />
          <Route path="families/*" element={<NotFoundPage />} />
          <Route path="children" element={<FeatureRoute featureId="children"><ChildrenPage /></FeatureRoute>} />
          <Route path="children/:childId" element={<FeatureRoute featureId="children"><ChildProfilePage /></FeatureRoute>} />
          <Route path="children/*" element={<NotFoundPage />} />
          <Route path="rooms/*" element={<FeatureRoute featureId="rooms"><RoomsPage /></FeatureRoute>} />
          <Route path="attendance/*" element={<FeatureRoute featureId="attendance"><AttendancePage /></FeatureRoute>} />
          <Route path="staff/*" element={<FeatureRoute featureId="staff"><StaffPage /></FeatureRoute>} />
          <Route path="staff-rota/*" element={<FeatureRoute featureId="staff-rota"><StaffRotaPage /></FeatureRoute>} />
          <Route path="jobs/*" element={<FeatureRoute featureId="hiring"><JobsPage /></FeatureRoute>} />
          <Route path="billing/*" element={<BillingRoute><BillingPage /></BillingRoute>} />
          <Route path="transport-registry/*" element={<TransportRegistryRoute><TransportRegistryPage /></TransportRegistryRoute>} />
          <Route path="settings/*" element={<FeatureRoute featureId="settings"><SettingsPage /></FeatureRoute>} />

          {/* Deferred routes remain compiled and explicit, but Basic never exposes them. */}
          <Route path="scheduling/*" element={<FeatureRoute featureId="scheduling"><SchedulingPage /></FeatureRoute>} />
          <Route path="claims/*" element={<FeatureRoute featureId="claims"><ModulePage /></FeatureRoute>} />
          <Route path="files/*" element={<FeatureRoute featureId="data-vault"><ModulePage /></FeatureRoute>} />
          <Route path="invoicing/*" element={<NotFoundPage />} />
          <Route path="letterhead/*" element={<FeatureRoute featureId="documents"><ModulePage /></FeatureRoute>} />
          <Route path="activity/*" element={<FeatureRoute featureId="activity"><ModulePage /></FeatureRoute>} />
          <Route path="support/*" element={<FeatureRoute featureId="support"><ModulePage /></FeatureRoute>} />
          <Route path="ai/*" element={<FeatureRoute featureId="ai-assistance"><ModulePage /></FeatureRoute>} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
