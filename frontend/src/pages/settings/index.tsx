import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import {
  BuildingOffice2Icon,
  UsersIcon,
  CreditCardIcon,
  DocumentTextIcon,
  UserGroupIcon,
  ClockIcon,
  BellIcon,
  PuzzlePieceIcon,
  ShieldCheckIcon,
  Cog6ToothIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';

interface SettingsCategory {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  path: string;
  status: 'active' | 'coming_soon';
  badge?: string;
}

const settingsCategories: SettingsCategory[] = [
  {
    id: 'organization',
    name: 'Organization',
    description: 'Profile, logo, business hours, and compliance',
    icon: BuildingOffice2Icon,
    path: '/settings/organization',
    status: 'active',
  },
  {
    id: 'security',
    name: 'Security',
    description: 'Password, authentication, and security settings',
    icon: ShieldCheckIcon,
    path: '/settings/security',
    status: 'active',
  },
  {
    id: 'team',
    name: 'User Management',
    description: 'Invite staff, manage roles, and access control',
    icon: UsersIcon,
    path: '/settings/users',
    status: 'active',
  },
  {
    id: 'billing',
    name: 'Billing & Subscription',
    description: 'Plans, payment methods, and invoices',
    icon: CreditCardIcon,
    path: '/settings/billing',
    status: 'active',
  },
  {
    id: 'invoicing',
    name: 'Invoicing & Payments',
    description: 'Invoice settings, tax rates, and payment terms',
    icon: DocumentTextIcon,
    path: '/settings/invoicing',
    status: 'active',
  },
  {
    id: 'families',
    name: 'Families & Enrollment',
    description: 'Enrollment workflow, documents, and custom fields',
    icon: UserGroupIcon,
    path: '/settings/families',
    status: 'coming_soon',
  },
  {
    id: 'attendance',
    name: 'Attendance',
    description: 'Check-in methods, rules, and holiday calendar',
    icon: ClockIcon,
    path: '/settings/attendance',
    status: 'coming_soon',
  },
  {
    id: 'notifications',
    name: 'Notifications',
    description: 'Email, SMS, and in-app notification preferences',
    icon: BellIcon,
    path: '/settings/notifications',
    status: 'active',
  },
  {
    id: 'integrations',
    name: 'Integrations',
    description: 'API keys, connected apps, and webhooks',
    icon: PuzzlePieceIcon,
    path: '/settings/integrations',
    status: 'active',
    badge: 'Pro',
  },
  {
    id: 'privacy',
    name: 'Data & Privacy',
    description: 'Data export, retention, and account deletion',
    icon: ShieldCheckIcon,
    path: '/settings/privacy',
    status: 'active',
  },
  {
    id: 'system',
    name: 'System Preferences',
    description: 'Theme, language, timezone, and display',
    icon: Cog6ToothIcon,
    path: '/settings/system',
    status: 'active',
  },
];

const SettingsCard: React.FC<{ category: SettingsCategory }> = ({ category }) => {
  const Icon = category.icon;
  const isComingSoon = category.status === 'coming_soon';

  const cardContent = (
    <div
      className={`
        relative bg-white rounded-xl border border-gray-200 p-5 
        transition-all duration-200 group
        ${isComingSoon 
          ? 'opacity-60 cursor-not-allowed' 
          : 'hover:border-primary-300 hover:shadow-md cursor-pointer'
        }
      `}
    >
      {/* Badge */}
      {category.badge && (
        <span className="absolute top-3 right-3 px-2 py-0.5 text-xs font-medium bg-primary-100 text-primary-700 rounded-full">
          {category.badge}
        </span>
      )}
      
      {/* Coming Soon Badge */}
      {isComingSoon && (
        <span className="absolute top-3 right-3 px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded-full">
          Coming Soon
        </span>
      )}

      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className={`
          flex-shrink-0 w-12 h-12 rounded-lg flex items-center justify-center
          ${isComingSoon 
            ? 'bg-gray-100' 
            : 'bg-primary-50 group-hover:bg-primary-100'
          }
          transition-colors duration-200
        `}>
          <Icon className={`
            h-6 w-6 
            ${isComingSoon ? 'text-gray-400' : 'text-primary-600'}
          `} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h3 className={`
              font-semibold 
              ${isComingSoon ? 'text-gray-500' : 'text-gray-900'}
            `}>
              {category.name}
            </h3>
            {!isComingSoon && (
              <ChevronRightIcon className="h-5 w-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
            )}
          </div>
          <p className={`
            mt-1 text-sm 
            ${isComingSoon ? 'text-gray-400' : 'text-gray-600'}
          `}>
            {category.description}
          </p>
        </div>
      </div>
    </div>
  );

  if (isComingSoon) {
    return cardContent;
  }

  return (
    <Link to={category.path}>
      {cardContent}
    </Link>
  );
};

const SettingsIndex: React.FC = () => {
  const location = useLocation();
  const isMainSettings = location.pathname === '/settings';

  // If we're on a sub-route, render the outlet
  if (!isMainSettings) {
    return <Outlet />;
  }

  return (
    <div className="max-w-6xl mx-auto py-8 px-4">
      {/* Header */}
      <div className="mb-8">
        <h1 className="heading-lg text-gray-900">Settings</h1>
        <p className="mt-2 body-md text-gray-600">
          Manage your organization, account, and application preferences.
        </p>
      </div>

      {/* Settings Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {settingsCategories.map((category) => (
          <SettingsCard key={category.id} category={category} />
        ))}
      </div>

      {/* Footer Help */}
      <div className="mt-12 bg-gray-50 rounded-xl p-6 border border-gray-200">
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center">
            <span className="text-lg">💡</span>
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Need help with settings?</h3>
            <p className="mt-1 text-sm text-gray-600">
              Check out our documentation or contact support for assistance with configuring your account.
            </p>
            <div className="mt-3 flex gap-3">
              <button className="text-sm font-medium text-primary-600 hover:text-primary-700">
                View Documentation →
              </button>
              <button className="text-sm font-medium text-gray-600 hover:text-gray-700">
                Contact Support
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsIndex;
