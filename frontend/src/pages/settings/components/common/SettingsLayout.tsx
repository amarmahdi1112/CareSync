// ============================================
// Settings Layout Components
// ============================================

import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';

// -------------------- Settings Page Layout --------------------

interface SettingsPageLayoutProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '4xl';
}

export const SettingsPageLayout: React.FC<SettingsPageLayoutProps> = ({
  title,
  description,
  children,
  actions,
  maxWidth = '4xl',
}) => {
  const widthClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl',
    '4xl': 'max-w-4xl',
  };

  return (
    <div className={`${widthClasses[maxWidth]} mx-auto py-8 px-4`}>
      <BackToSettings />
      <SettingsHeader title={title} description={description} actions={actions} />
      {children}
    </div>
  );
};

// -------------------- Back Link --------------------

export const BackToSettings: React.FC = () => (
  <Link
    to="/settings"
    className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 mb-6 transition-colors"
  >
    <ArrowLeftIcon className="h-4 w-4" />
    Back to Settings
  </Link>
);

// -------------------- Settings Header --------------------

interface SettingsHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export const SettingsHeader: React.FC<SettingsHeaderProps> = ({
  title,
  description,
  actions,
}) => (
  <div className="mb-8 flex items-center justify-between">
    <div>
      <h1 className="heading-lg text-gray-900">{title}</h1>
      {description && (
        <p className="mt-2 body-md text-gray-600">{description}</p>
      )}
    </div>
    {actions && <div className="flex items-center gap-3">{actions}</div>}
  </div>
);

// -------------------- Settings Section Card --------------------

interface SettingsSectionProps {
  title?: string;
  icon?: React.ElementType;
  description?: string;
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}

export const SettingsSection: React.FC<SettingsSectionProps> = ({
  title,
  icon: Icon,
  description,
  children,
  className = '',
  noPadding = false,
}) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden ${className}`}>
    {title && (
      <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-5 w-5 text-gray-600" />}
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
            {description && <p className="text-sm text-gray-500">{description}</p>}
          </div>
        </div>
      </div>
    )}
    <div className={noPadding ? '' : 'p-6'}>{children}</div>
  </div>
);

// -------------------- Settings Subsection --------------------

interface SettingsSubsectionProps {
  title: string;
  icon?: React.ElementType;
  children: React.ReactNode;
  className?: string;
}

export const SettingsSubsection: React.FC<SettingsSubsectionProps> = ({
  title,
  icon: Icon,
  children,
  className = '',
}) => (
  <div className={`pt-6 border-t border-gray-200 ${className}`}>
    <h4 className="text-md font-medium text-gray-900 mb-4 flex items-center gap-2">
      {Icon && <Icon className="h-5 w-5 text-gray-500" />}
      {title}
    </h4>
    {children}
  </div>
);

// -------------------- Settings Tabs --------------------

interface Tab {
  id: string;
  name: string;
  icon?: React.ElementType;
}

interface SettingsTabsProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

export const SettingsTabs: React.FC<SettingsTabsProps> = ({
  tabs,
  activeTab,
  onTabChange,
}) => (
  <div className="border-b border-gray-200 mb-6">
    <nav className="-mb-px flex space-x-8">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              isActive
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {Icon && <Icon className="h-5 w-5" />}
            {tab.name}
          </button>
        );
      })}
    </nav>
  </div>
);

// -------------------- Loading Spinner --------------------

export const SettingsLoadingSpinner: React.FC = () => (
  <div className="flex justify-center py-12">
    <div className="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full" />
  </div>
);

// -------------------- Settings Loading Skeleton --------------------

export const SettingsLoadingSkeleton: React.FC = () => (
  <div className="animate-pulse">
    <div className="h-8 bg-gray-200 rounded w-1/3 mb-4"></div>
    <div className="h-4 bg-gray-200 rounded w-2/3 mb-8"></div>
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="space-y-4">
        <div className="h-4 bg-gray-200 rounded w-1/4"></div>
        <div className="h-10 bg-gray-200 rounded"></div>
        <div className="h-4 bg-gray-200 rounded w-1/4"></div>
        <div className="h-10 bg-gray-200 rounded"></div>
      </div>
    </div>
  </div>
);
