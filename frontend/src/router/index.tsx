/* eslint-disable react-refresh/only-export-components */
import React, { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import DefaultLayout from '../components/layout/DefaultLayout';
import AuthLayout from '../components/layout/AuthLayout';
import ProtectedRoute from '../components/routing/ProtectedRoute';

// Lazy load components for better performance
const Dashboard = lazy(() => import('../pages/Dashboard'));
const Login = lazy(() => import('../pages/auth/Login'));

// Public pages
const Landing = lazy(() => import('../pages/public_view/Landing'));
const About = lazy(() => import('../pages/public_view/About'));
const Pricing = lazy(() => import('../pages/public_view/Pricing'));
const Contact = lazy(() => import('../pages/public_view/Contact'));
const Register = lazy(() => import('../pages/auth/Register')); // Simplified registration → onboarding
const Terms = lazy(() => import('../pages/public_view/Terms'));
const Privacy = lazy(() => import('../pages/public_view/Privacy'));

// Onboarding & Profile Completion
const Onboarding = lazy(() => import('../pages/onboarding'));
const CompleteSetup = lazy(() => import('../pages/setup/CompleteSetup'));
const PricingSetup = lazy(() => import('../pages/setup/PricingSetup'));
const CompleteProfile = lazy(() => import('../pages/auth/CompleteProfile'));
const MyFiles = lazy(() => import('../pages/files/MyFiles'));
const DataArchiveView = lazy(() => import('../pages/files/data-archive/DataArchiveView'));
const DataUploadView = lazy(() => import('../pages/files/data-upload/DataUploadView'));
const DataViewingView = lazy(() => import('../pages/files/data-viewing/DataViewingView'));
const SingleCsvUpload = lazy(() => import('../pages/files/data-upload/components/SingleCsvUpload'));
const BatchUpload = lazy(() => import('../pages/files/data-upload/components/BatchUpload'));
const ScheduledUpload = lazy(() => import('../pages/files/data-upload/components/ScheduledUpload'));
const SchedulingHub = lazy(() => import('../pages/scheduling/SchedulingHub'));
const PrintableTimesheet = lazy(() => import('../pages/printable-timesheet/PrintableTimesheet'));

// Families pages
const FamiliesList = lazy(() => import('../pages/families/views/FamiliesList'));
const FamilyDetail = lazy(() => import('../pages/families/views/FamilyDetail'));
const FamilyRegistration = lazy(() => import('../pages/families/views/FamilyRegistration'));
const CSVImport = lazy(() => import('../pages/families/views/CSVImport'));
const AddChild = lazy(() => import('../pages/families/views/AddChild'));
const SiblingAssignment = () => <div className="p-4">Sibling Assignment - Coming Soon</div>;

// Children pages
const ChildrenList = lazy(() => import('../pages/children/views/ChildrenList'));
const ChildDetail = lazy(() => import('../pages/children/views/ChildDetail'));
const EditChild = lazy(() => import('../pages/children/views/EditChild'));

// Invoicing pages
const Invoicing = lazy(() => import('../pages/invoicing'));

// Settings pages
const Settings = lazy(() => import('../pages/settings'));
const OrganizationSettings = lazy(() => import('../pages/settings/views/Organization'));
const UserManagement = lazy(() => import('../pages/settings/views/Users'));
const SecuritySettings = lazy(() => import('../pages/settings/views/Security'));
const NotificationSettings = lazy(() => import('../pages/settings/views/Notifications'));
const BillingSettings = lazy(() => import('../pages/settings/views/Billing'));
const SystemSettings = lazy(() => import('../pages/settings/views/System'));
const DataPrivacy = lazy(() => import('../pages/settings/views/Privacy'));
const IntegrationsSettings = lazy(() => import('../pages/settings/views/Integrations'));
const InvoicingSettings = lazy(() => import('../pages/settings/views/Invoicing'));

// Profile page
const Profile = lazy(() => import('../pages/profile'));

// Support page
const Support = lazy(() => import('../pages/support'));

// Activity Log
const ActivityLog = lazy(() => import('../pages/ActivityLog'));

// Letterhead Generator
const LetterheadGenerator = lazy(() => import('../pages/letterhead/LetterheadGenerator'));

// Placeholder pages
const Notifications = () => <div className="p-4">Notifications - Coming Soon</div>;
const NotFound = () => (
  <div className="text-center p-8">
    <h1 className="text-2xl font-bold mb-4">404 - Page Not Found</h1>
    <p>The page you're looking for doesn't exist.</p>
  </div>
);

// Loading component
const LoadingSpinner = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
  </div>
);

// Wrapper for lazy-loaded components
const LazyWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Suspense fallback={<LoadingSpinner />}>
    {children}
  </Suspense>
);

export const router = createBrowserRouter([
  // ===== PUBLIC ROUTES =====
  {
    path: '/',
    element: (
      <LazyWrapper>
        <Landing />
      </LazyWrapper>
    ),
  },
  {
    path: '/about',
    element: (
      <LazyWrapper>
        <About />
      </LazyWrapper>
    ),
  },
  {
    path: '/pricing',
    element: (
      <LazyWrapper>
        <Pricing />
      </LazyWrapper>
    ),
  },
  {
    path: '/contact',
    element: (
      <LazyWrapper>
        <Contact />
      </LazyWrapper>
    ),
  },
  {
    path: '/register',
    element: (
      <LazyWrapper>
        <Register />
      </LazyWrapper>
    ),
  },
  {
    path: '/terms',
    element: (
      <LazyWrapper>
        <Terms />
      </LazyWrapper>
    ),
  },
  {
    path: '/privacy',
    element: (
      <LazyWrapper>
        <Privacy />
      </LazyWrapper>
    ),
  },
  // ===== AUTH ROUTES =====
  {
    path: '/login',
    element: (
      <ProtectedRoute requiresAuth={false}>
        <AuthLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: (
          <LazyWrapper>
            <Login />
          </LazyWrapper>
        )
      }
    ]
  },
  // ===== ONBOARDING (Protected, no layout, skip profile check) =====
  {
    path: '/onboarding',
    element: (
      <ProtectedRoute requiresAuth={true} skipProfileCheck={true}>
        <LazyWrapper>
          <Onboarding />
        </LazyWrapper>
      </ProtectedRoute>
    ),
  },
  // ===== COMPLETE SETUP (Protected, shows ONLY missing org fields) =====
  {
    path: '/complete-setup',
    element: (
      <ProtectedRoute requiresAuth={true} skipProfileCheck={true}>
        <LazyWrapper>
          <CompleteSetup />
        </LazyWrapper>
      </ProtectedRoute>
    ),
  },
  // ===== COMPLETE PROFILE (Protected, shows ONLY missing user fields) =====
  {
    path: '/complete-profile',
    element: (
      <ProtectedRoute requiresAuth={true} skipProfileCheck={true}>
        <LazyWrapper>
          <CompleteProfile />
        </LazyWrapper>
      </ProtectedRoute>
    ),
  },
  // ===== PRICING SETUP (Protected, required before dashboard) =====
  {
    path: '/setup/pricing',
    element: (
      <ProtectedRoute requiresAuth={true} skipProfileCheck={true} skipPricingCheck={true}>
        <LazyWrapper>
          <PricingSetup />
        </LazyWrapper>
      </ProtectedRoute>
    ),
  },
  // ===== PROTECTED ROUTES (with layout) =====
  {
    path: '/',
    element: (
      <ProtectedRoute requiresAuth={true}>
        <DefaultLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        path: 'dashboard',
        element: (
          <LazyWrapper>
            <Dashboard />
          </LazyWrapper>
        )
      },
      {
        path: 'files',
        element: (
          <LazyWrapper>
            <MyFiles />
          </LazyWrapper>
        ),
        children: [
          {
            index: true,
            element: <Navigate to="/files/data-archive" replace />
          },
          {
            path: 'data-archive',
            element: (
              <LazyWrapper>
                <DataArchiveView />
              </LazyWrapper>
            )
          },
          {
            path: 'data-upload',
            element: (
              <LazyWrapper>
                <DataUploadView />
              </LazyWrapper>
            ),
            children: [
              {
                path: 'single-csv',
                element: (
                  <LazyWrapper>
                    <SingleCsvUpload />
                  </LazyWrapper>
                )
              },
              {
                path: 'batch-upload',
                element: (
                  <LazyWrapper>
                    <BatchUpload />
                  </LazyWrapper>
                )
              },
              {
                path: 'scheduled-upload',
                element: (
                  <LazyWrapper>
                    <ScheduledUpload />
                  </LazyWrapper>
                )
              }
            ]
          },
          {
            path: 'data-viewing',
            element: (
              <LazyWrapper>
                <DataViewingView />
              </LazyWrapper>
            )
          },
          {
            path: 'claim-generation',
            element: <Navigate to="/scheduling" replace />
          }
        ]
      },
      {
        path: 'families',
        element: (
          <LazyWrapper>
            <FamiliesList />
          </LazyWrapper>
        )
      },
      {
        path: 'families/create',
        element: (
          <LazyWrapper>
            <FamilyRegistration />
          </LazyWrapper>
        )
      },
      {
        path: 'families/import',
        element: (
          <LazyWrapper>
            <CSVImport />
          </LazyWrapper>
        )
      },
      {
        path: 'families/:id',
        element: (
          <LazyWrapper>
            <FamilyDetail />
          </LazyWrapper>
        )
      },
      {
        path: 'families/:familyId/add-child',
        element: (
          <LazyWrapper>
            <AddChild />
          </LazyWrapper>
        )
      },
      {
        path: 'sibling-assignment',
        element: <SiblingAssignment />
      },
      {
        path: 'children',
        element: (
          <LazyWrapper>
            <ChildrenList />
          </LazyWrapper>
        )
      },
      {
        path: 'children/:id',
        element: (
          <LazyWrapper>
            <ChildDetail />
          </LazyWrapper>
        )
      },
      {
        path: 'children/:id/edit',
        element: (
          <LazyWrapper>
            <EditChild />
          </LazyWrapper>
        )
      },
      {
        path: 'invoicing',
        element: (
          <LazyWrapper>
            <Invoicing />
          </LazyWrapper>
        )
      },
      {
        path: 'scheduling',
        element: (
          <LazyWrapper>
            <SchedulingHub />
          </LazyWrapper>
        )
      },
      {
        path: 'scheduler',
        element: <Navigate to="/scheduling" replace />
      },
      {
        path: 'daily-attendance',
        element: <Navigate to="/scheduling" replace />
      },
      {
        path: 'printable-timesheet',
        element: (
          <LazyWrapper>
            <PrintableTimesheet />
          </LazyWrapper>
        )
      },
      {
        path: 'letterhead',
        element: (
          <LazyWrapper>
            <LetterheadGenerator />
          </LazyWrapper>
        )
      },
      {
        path: 'notifications',
        element: <Notifications />
      },
      {
        path: 'settings',
        element: (
          <LazyWrapper>
            <Settings />
          </LazyWrapper>
        ),
        children: [
          {
            path: 'organization',
            element: (
              <LazyWrapper>
                <OrganizationSettings />
              </LazyWrapper>
            )
          },
          {
            path: 'users',
            element: (
              <LazyWrapper>
                <UserManagement />
              </LazyWrapper>
            )
          },
          {
            path: 'security',
            element: (
              <LazyWrapper>
                <SecuritySettings />
              </LazyWrapper>
            )
          },
          {
            path: 'notifications',
            element: (
              <LazyWrapper>
                <NotificationSettings />
              </LazyWrapper>
            )
          },
          {
            path: 'billing',
            element: (
              <LazyWrapper>
                <BillingSettings />
              </LazyWrapper>
            )
          },
          {
            path: 'system',
            element: (
              <LazyWrapper>
                <SystemSettings />
              </LazyWrapper>
            )
          },
          {
            path: 'privacy',
            element: (
              <LazyWrapper>
                <DataPrivacy />
              </LazyWrapper>
            )
          },
          {
            path: 'integrations',
            element: (
              <LazyWrapper>
                <IntegrationsSettings />
              </LazyWrapper>
            )
          },
          {
            path: 'invoicing',
            element: (
              <LazyWrapper>
                <InvoicingSettings />
              </LazyWrapper>
            )
          }
        ]
      },
      {
        path: 'support',
        element: (
          <LazyWrapper>
            <Support />
          </LazyWrapper>
        )
      },
      {
        path: 'profile',
        element: (
          <LazyWrapper>
            <Profile />
          </LazyWrapper>
        )
      },
      {
        path: 'activity',
        element: (
          <LazyWrapper>
            <ActivityLog />
          </LazyWrapper>
        )
      }
    ]
  },
  {
    path: '*',
    element: <NotFound />
  }
]);

export default router;
