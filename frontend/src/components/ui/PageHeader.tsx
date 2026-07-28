import React from 'react';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';

interface PageHeaderProps {
  title: string;
  description?: string;
  backButton?: {
    onClick: () => void;
    label?: string;
  };
  actions?: React.ReactNode;
  badge?: React.ReactNode;
  icon?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  backButton,
  actions,
  badge,
  icon,
}) => {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-4">
        {backButton && (
          <button
            onClick={backButton.onClick}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            title={backButton.label || 'Go back'}
          >
            <ArrowLeftIcon className="w-5 h-5 text-gray-600" />
          </button>
        )}
        
        {icon && (
          <div className="w-14 h-14 bg-primary-100 rounded-full flex items-center justify-center">
            {icon}
          </div>
        )}
        
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900 font-comfortaa">{title}</h1>
            {badge}
          </div>
          {description && (
            <p className="mt-1 text-sm text-gray-500">{description}</p>
          )}
        </div>
      </div>
      
      {actions && (
        <div className="flex items-center space-x-3">
          {actions}
        </div>
      )}
    </div>
  );
};

// Simple page header without extras
interface SimpleHeaderProps {
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: React.ReactNode;
  };
}

export const SimpleHeader: React.FC<SimpleHeaderProps> = ({
  title,
  description,
  action,
}) => {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 font-comfortaa">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-gray-500">{description}</p>
        )}
      </div>
      
      {action && (
        <button
          onClick={action.onClick}
          className="btn btn-primary"
        >
          {action.icon}
          {action.label}
        </button>
      )}
    </div>
  );
};

export default PageHeader;
