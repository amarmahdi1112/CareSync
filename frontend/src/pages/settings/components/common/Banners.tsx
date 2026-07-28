// ============================================
// Settings Banner Components
// ============================================

import React from 'react';
import { ExclamationCircleIcon, CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline';

// -------------------- Info Banner --------------------

interface InfoBannerProps {
  icon?: React.ElementType;
  title: string;
  children: React.ReactNode;
  variant?: 'info' | 'success' | 'warning' | 'error';
  className?: string;
}

export const InfoBanner: React.FC<InfoBannerProps> = ({
  icon: CustomIcon,
  title,
  children,
  variant = 'info',
  className = '',
}) => {
  const variants = {
    info: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      icon: 'text-blue-600',
      title: 'text-blue-900',
      text: 'text-blue-800',
    },
    success: {
      bg: 'bg-green-50',
      border: 'border-green-200',
      icon: 'text-green-600',
      title: 'text-green-900',
      text: 'text-green-800',
    },
    warning: {
      bg: 'bg-yellow-50',
      border: 'border-yellow-200',
      icon: 'text-yellow-600',
      title: 'text-yellow-900',
      text: 'text-yellow-800',
    },
    error: {
      bg: 'bg-red-50',
      border: 'border-red-200',
      icon: 'text-red-600',
      title: 'text-red-900',
      text: 'text-red-800',
    },
  };

  const style = variants[variant];
  const Icon = CustomIcon;

  return (
    <div className={`${style.bg} rounded-xl p-6 border ${style.border} ${className}`}>
      <div className="flex items-start gap-3">
        {Icon && <Icon className={`h-6 w-6 ${style.icon} flex-shrink-0`} />}
        <div>
          <h3 className={`font-medium ${style.title}`}>{title}</h3>
          <div className={`mt-1 text-sm ${style.text}`}>{children}</div>
        </div>
      </div>
    </div>
  );
};

// -------------------- Unsaved Changes Warning --------------------

interface UnsavedChangesWarningProps {
  show: boolean;
  onSave: () => void;
  saving?: boolean;
}

export const UnsavedChangesWarning: React.FC<UnsavedChangesWarningProps> = ({
  show,
  onSave,
  saving = false,
}) => {
  if (!show) return null;

  return (
    <div className="fixed bottom-4 right-4 bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 shadow-lg flex items-center gap-3 z-50">
      <ExclamationCircleIcon className="h-5 w-5 text-yellow-600" />
      <span className="text-sm text-yellow-800">You have unsaved changes</span>
      <button
        onClick={onSave}
        disabled={saving}
        className="btn btn-primary btn-sm"
      >
        {saving ? 'Saving...' : 'Save Now'}
      </button>
    </div>
  );
};

// -------------------- Status Badge --------------------

interface StatusBadgeProps {
  status: 'active' | 'inactive' | 'pending' | 'configured' | 'coming_soon';
  label?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => {
  const styles = {
    active: 'bg-green-100 text-green-800',
    inactive: 'bg-gray-100 text-gray-800',
    pending: 'bg-yellow-100 text-yellow-800',
    configured: 'bg-green-100 text-green-800',
    coming_soon: 'bg-gray-100 text-gray-600',
  };

  const defaultLabels = {
    active: 'Active',
    inactive: 'Inactive',
    pending: 'Pending',
    configured: 'Configured',
    coming_soon: 'Coming Soon',
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[status]}`}>
      {label || defaultLabels[status]}
    </span>
  );
};

// -------------------- Config Status Badge (with icon) --------------------

interface ConfigStatusProps {
  configured: boolean;
}

export const ConfigStatus: React.FC<ConfigStatusProps> = ({ configured }) => (
  <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${
    configured ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
  }`}>
    {configured ? (
      <>
        <CheckCircleIcon className="w-4 h-4" />
        Configured
      </>
    ) : (
      <>
        <XCircleIcon className="w-4 h-4" />
        Not Configured
      </>
    )}
  </span>
);

// -------------------- Test Result Banner --------------------

interface TestResultProps {
  result: { success: boolean; message: string } | null;
}

export const TestResultBanner: React.FC<TestResultProps> = ({ result }) => {
  if (!result) return null;

  return (
    <div className={`mt-3 p-3 rounded-lg flex items-center gap-2 ${
      result.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
    }`}>
      {result.success ? (
        <CheckCircleIcon className="w-5 h-5" />
      ) : (
        <XCircleIcon className="w-5 h-5" />
      )}
      <span className="text-sm">{result.message}</span>
    </div>
  );
};

// -------------------- Feature Summary Box --------------------

interface FeatureSummaryProps {
  title: string;
  linkText?: string;
  linkHref?: string;
  children: React.ReactNode;
}

export const FeatureSummary: React.FC<FeatureSummaryProps> = ({
  title,
  linkText,
  linkHref,
  children,
}) => (
  <div className="p-4 bg-gray-50 rounded-lg">
    <div className="flex items-center justify-between mb-3">
      <span className="text-sm font-medium text-gray-700">{title}</span>
      {linkText && linkHref && (
        <a
          href={linkHref}
          className="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
        >
          {linkText}
        </a>
      )}
    </div>
    {children}
  </div>
);

// -------------------- Empty State for Settings --------------------

interface SettingsEmptyStateProps {
  icon: React.ElementType;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export const SettingsEmptyState: React.FC<SettingsEmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  action,
}) => (
  <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
    <Icon className="w-10 h-10 text-gray-300 mx-auto mb-3" />
    <p className="text-gray-500">{title}</p>
    <p className="text-sm text-gray-400 mt-1">{description}</p>
    {action && (
      <button
        onClick={action.onClick}
        className="mt-4 btn btn-primary btn-sm"
      >
        {action.label}
      </button>
    )}
  </div>
);
