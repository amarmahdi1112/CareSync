// ============================================
// Families Module - Layout Components
// ============================================

import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';

// -------------------- Page Container --------------------

interface PageContainerProps {
  children: React.ReactNode;
}

export const PageContainer: React.FC<PageContainerProps> = ({ children }) => (
  <div className="space-y-6">{children}</div>
);

// -------------------- Page Header --------------------

interface PageHeaderProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  backLink?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  icon,
  actions,
  backLink,
}) => (
  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
    <div className="flex items-center gap-4">
      {backLink && (
        <Link
          to={backLink}
          className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5" />
        </Link>
      )}
      {icon && (
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-lg shadow-primary-500/25">
          {icon}
        </div>
      )}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-gray-500">{description}</p>
        )}
      </div>
    </div>
    {actions && (
      <div className="flex items-center gap-3">{actions}</div>
    )}
  </div>
);

// -------------------- Stats Grid --------------------

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color?: 'default' | 'green' | 'yellow' | 'red' | 'blue' | 'purple' | 'pink';
  onClick?: () => void;
  trend?: { value: number; isUp: boolean };
}

const statColorClasses = {
  default: { bg: 'bg-gray-50', iconBg: 'bg-gray-100', icon: 'text-gray-600', value: 'text-gray-900' },
  green: { bg: 'bg-green-50', iconBg: 'bg-green-100', icon: 'text-green-600', value: 'text-green-700' },
  yellow: { bg: 'bg-amber-50', iconBg: 'bg-amber-100', icon: 'text-amber-600', value: 'text-amber-700' },
  red: { bg: 'bg-red-50', iconBg: 'bg-red-100', icon: 'text-red-600', value: 'text-red-700' },
  blue: { bg: 'bg-blue-50', iconBg: 'bg-blue-100', icon: 'text-blue-600', value: 'text-blue-700' },
  purple: { bg: 'bg-purple-50', iconBg: 'bg-purple-100', icon: 'text-purple-600', value: 'text-purple-700' },
  pink: { bg: 'bg-pink-50', iconBg: 'bg-pink-100', icon: 'text-pink-600', value: 'text-pink-700' },
};

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  icon,
  color = 'default',
  onClick,
  trend,
}) => {
  const colors = statColorClasses[color];
  
  return (
    <div 
      className={`${colors.bg} rounded-xl p-5 transition-all duration-200 ${onClick ? 'cursor-pointer hover:shadow-md hover:scale-[1.02]' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-lg ${colors.iconBg} flex items-center justify-center`}>
          <div className={colors.icon}>{icon}</div>
        </div>
        {trend && (
          <span className={`text-xs font-medium px-2 py-1 rounded-full ${
            trend.isUp ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}>
            {trend.isUp ? '↑' : '↓'} {Math.abs(trend.value)}%
          </span>
        )}
      </div>
      <div className="mt-4">
        <p className={`text-2xl font-bold ${colors.value}`}>{value}</p>
        <p className="text-sm text-gray-500 mt-1">{label}</p>
      </div>
    </div>
  );
};

export const StatsGrid: React.FC<{ children: React.ReactNode; columns?: 2 | 3 | 4 | 5 }> = ({ 
  children, 
  columns = 4 
}) => {
  const gridCols = {
    2: 'grid-cols-1 sm:grid-cols-2',
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
    5: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5',
  };
  
  return <div className={`grid ${gridCols[columns]} gap-4`}>{children}</div>;
};

// -------------------- Search & Filter Bar --------------------

interface FilterOption {
  value: string;
  label: string;
}

interface SearchFilterBarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  filters?: {
    value: string;
    onChange: (value: string) => void;
    options: FilterOption[];
  }[];
  viewMode?: 'grid' | 'list';
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  actions?: React.ReactNode;
}

export const SearchFilterBar: React.FC<SearchFilterBarProps> = ({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search...',
  filters,
  viewMode,
  onViewModeChange,
  actions,
}) => (
  <div className="flex flex-col sm:flex-row gap-4">
    {/* Search */}
    <div className="relative flex-1 max-w-md">
      <input
        type="text"
        value={searchValue}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder={searchPlaceholder}
        className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
      />
      <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    </div>

    {/* Filters */}
    <div className="flex items-center gap-3">
      {filters?.map((filter, idx) => (
        <select
          key={idx}
          value={filter.value}
          onChange={(e) => filter.onChange(e.target.value)}
          className="px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
        >
          {filter.options.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      ))}

      {/* View Mode Toggle */}
      {viewMode && onViewModeChange && (
        <div className="flex items-center bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => onViewModeChange('grid')}
            className={`p-2 rounded-md transition-colors ${viewMode === 'grid' ? 'bg-white shadow-sm text-primary-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>
          <button
            onClick={() => onViewModeChange('list')}
            className={`p-2 rounded-md transition-colors ${viewMode === 'list' ? 'bg-white shadow-sm text-primary-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      )}

      {actions}
    </div>
  </div>
);

// -------------------- Content Card --------------------

interface ContentCardProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}

export const ContentCard: React.FC<ContentCardProps> = ({
  children,
  title,
  description,
  actions,
  className = '',
  noPadding = false,
}) => (
  <div className={`bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden ${className}`}>
    {(title || actions) && (
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          {title && <h3 className="text-lg font-semibold text-gray-900">{title}</h3>}
          {description && <p className="mt-0.5 text-sm text-gray-500">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    )}
    <div className={noPadding ? '' : 'p-6'}>{children}</div>
  </div>
);

// -------------------- Empty State --------------------

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
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
}) => (
  <div className="text-center py-16 px-6">
    <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
      {icon}
    </div>
    <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
    <p className="text-gray-500 max-w-sm mx-auto mb-6">{description}</p>
    {action && (
      <button onClick={action.onClick} className="btn btn-primary inline-flex items-center gap-2">
        {action.icon}
        {action.label}
      </button>
    )}
  </div>
);

// -------------------- Loading States --------------------

export const LoadingSkeleton: React.FC<{ count?: number }> = ({ count = 6 }) => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-gray-200 rounded-full" />
          <div className="flex-1">
            <div className="h-4 bg-gray-200 rounded w-2/3 mb-2" />
            <div className="h-3 bg-gray-200 rounded w-1/2" />
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-gray-100">
          <div className="flex gap-2">
            <div className="h-6 bg-gray-200 rounded-lg w-20" />
            <div className="h-6 bg-gray-200 rounded-lg w-16" />
          </div>
        </div>
      </div>
    ))}
  </div>
);

export const DetailSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-6">
    <div className="flex items-center gap-4">
      <div className="w-16 h-16 bg-gray-200 rounded-full" />
      <div>
        <div className="h-6 bg-gray-200 rounded w-48 mb-2" />
        <div className="h-4 bg-gray-200 rounded w-32" />
      </div>
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 bg-gray-200 rounded-xl" />
        ))}
      </div>
      <div className="space-y-4">
        <div className="h-48 bg-gray-200 rounded-xl" />
        <div className="h-32 bg-gray-200 rounded-xl" />
      </div>
    </div>
  </div>
);
