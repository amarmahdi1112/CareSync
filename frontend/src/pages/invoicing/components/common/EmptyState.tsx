// ============================================
// Empty State Components
// ============================================

import React from 'react';

// -------------------- Empty State --------------------

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: React.ReactNode;
  };
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
}) => {
  return (
    <div className="p-12 text-center">
      <div className="text-gray-300 mx-auto mb-4 w-12 h-12">
        {icon}
      </div>
      <h3 className="text-lg font-medium text-gray-900 mb-2">{title}</h3>
      {description && <p className="text-gray-500 mb-4">{description}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          {action.icon}
          {action.label}
        </button>
      )}
    </div>
  );
};

// -------------------- Loading State --------------------

interface LoadingStateProps {
  message?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({ message = 'Loading...' }) => {
  return (
    <div className="p-12 text-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto" />
      <p className="mt-4 text-gray-500">{message}</p>
    </div>
  );
};

// -------------------- Loading Spinner --------------------

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ size = 'md', className = '' }) => {
  const sizes = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-4',
    lg: 'w-16 h-16 border-4',
  };

  return (
    <div
      className={`${sizes[size]} border-primary-600 border-t-transparent rounded-full animate-spin ${className}`}
    />
  );
};

// -------------------- Centered Loading --------------------

export const CenteredLoading: React.FC = () => {
  return (
    <div className="flex justify-center py-12">
      <LoadingSpinner />
    </div>
  );
};

// -------------------- Processing Overlay --------------------

interface ProcessingOverlayProps {
  message: string;
  progress?: number;
  total?: number;
}

export const ProcessingOverlay: React.FC<ProcessingOverlayProps> = ({
  message,
  progress,
  total,
}) => {
  return (
    <div className="p-8 text-center">
      <LoadingSpinner size="lg" className="mx-auto mb-4" />
      <p className="text-lg font-medium text-gray-900 mb-2">{message}</p>
      {progress !== undefined && total !== undefined && (
        <>
          <p className="text-sm text-gray-500 mb-4">
            Processing {Math.floor((progress / 100) * total)} of {total}
          </p>
          <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </>
      )}
    </div>
  );
};
