// ============================================
// Invoicing Page Layout Components
// ============================================

import React from 'react';

// -------------------- Page Container --------------------

interface PageContainerProps {
  children: React.ReactNode;
}

export const PageContainer: React.FC<PageContainerProps> = ({ children }) => (
  <div className="min-h-screen bg-gray-50/50">
    {children}
  </div>
);

// -------------------- Page Header --------------------

interface PageHeaderProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  icon,
  actions,
  badge,
}) => (
  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4 sm:pt-6 pb-4">
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div className="flex items-center gap-3 sm:gap-4">
        {icon && (
          <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-lg shadow-primary-500/25 flex-shrink-0">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 truncate">{title}</h1>
            {badge}
          </div>
          {description && (
            <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 truncate">{description}</p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">{actions}</div>
      )}
    </div>
  </div>
);

// -------------------- Tab Navigation --------------------

interface Tab {
  id: string;
  name: string;
  icon: React.ElementType;
  badge?: string | number;
}

interface TabNavigationProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

export const TabNavigation: React.FC<TabNavigationProps> = ({
  tabs,
  activeTab,
  onTabChange,
}) => (
  <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-4 sm:mb-6">
    <nav className="flex space-x-2 sm:space-x-6 overflow-x-auto scrollbar-hide pb-1 -mb-px" aria-label="Tabs">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`
              whitespace-nowrap py-2 px-2 sm:px-1 border-b-2 font-medium text-xs sm:text-sm transition-colors flex items-center gap-1.5 sm:gap-2 flex-shrink-0
              ${isActive 
                ? 'border-primary-500 text-primary-600' 
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}
            `}
          >
            <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
            <span className="hidden sm:inline">{tab.name}</span>
            <span className="sm:hidden">{tab.name.split(' ')[0]}</span>
            {tab.badge !== undefined && (
              <span className={`ml-0.5 sm:ml-1 px-1.5 sm:px-2 py-0.5 text-xs rounded-full ${
                isActive 
                  ? 'bg-primary-100 text-primary-700' 
                  : 'bg-gray-100 text-gray-600'
              }`}>
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  </div>
);

// -------------------- Page Content --------------------

interface PageContentProps {
  children: React.ReactNode;
  className?: string;
}

export const PageContent: React.FC<PageContentProps> = ({ children, className = '' }) => (
  <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 ${className}`}>
    {children}
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
      <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4">
        <div className="min-w-0">
          {title && <h3 className="text-base sm:text-lg font-semibold text-gray-900 truncate">{title}</h3>}
          {description && <p className="mt-0.5 text-xs sm:text-sm text-gray-500">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
      </div>
    )}
    <div className={noPadding ? '' : 'p-4 sm:p-6'}>{children}</div>
  </div>
);

// -------------------- Stats Card (Modern) --------------------

interface ModernStatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: { value: number; isUp: boolean };
  color?: 'default' | 'green' | 'yellow' | 'red' | 'blue' | 'purple';
  onClick?: () => void;
}

const statColorClasses = {
  default: {
    bg: 'bg-gray-50',
    iconBg: 'bg-gray-100',
    icon: 'text-gray-600',
    value: 'text-gray-900',
  },
  green: {
    bg: 'bg-green-50',
    iconBg: 'bg-green-100',
    icon: 'text-green-600',
    value: 'text-green-700',
  },
  yellow: {
    bg: 'bg-amber-50',
    iconBg: 'bg-amber-100',
    icon: 'text-amber-600',
    value: 'text-amber-700',
  },
  red: {
    bg: 'bg-red-50',
    iconBg: 'bg-red-100',
    icon: 'text-red-600',
    value: 'text-red-700',
  },
  blue: {
    bg: 'bg-blue-50',
    iconBg: 'bg-blue-100',
    icon: 'text-blue-600',
    value: 'text-blue-700',
  },
  purple: {
    bg: 'bg-purple-50',
    iconBg: 'bg-purple-100',
    icon: 'text-purple-600',
    value: 'text-purple-700',
  },
};

export const ModernStatCard: React.FC<ModernStatCardProps> = ({
  label,
  value,
  icon,
  trend,
  color = 'default',
  onClick,
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

// -------------------- Stats Grid --------------------

interface StatsGridProps {
  children: React.ReactNode;
  columns?: 2 | 3 | 4;
}

export const StatsGridLayout: React.FC<StatsGridProps> = ({ children, columns = 4 }) => {
  const gridCols = {
    2: 'grid-cols-1 sm:grid-cols-2',
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
  };
  
  return (
    <div className={`grid ${gridCols[columns]} gap-4`}>
      {children}
    </div>
  );
};

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

export const EmptyStateCard: React.FC<EmptyStateProps> = ({
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
      <button onClick={action.onClick} className="btn btn-primary">
        {action.icon}
        {action.label}
      </button>
    )}
  </div>
);
