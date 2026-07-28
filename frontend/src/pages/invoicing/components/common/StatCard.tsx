// ============================================
// Stat Card Components
// ============================================

import React from 'react';

// -------------------- Single Stat Card --------------------

interface StatCardProps {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: string | number;
  valueColor?: string;
  subtext?: React.ReactNode;
}

export const StatCard: React.FC<StatCardProps> = ({
  icon,
  iconBg,
  label,
  value,
  valueColor = 'text-gray-900',
  subtext,
}) => {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-center gap-3">
        <div className={`p-2 ${iconBg} rounded-lg`}>
          {icon}
        </div>
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className={`text-2xl font-bold ${valueColor}`}>{value}</p>
          {subtext && <div className="mt-1">{subtext}</div>}
        </div>
      </div>
    </div>
  );
};

// -------------------- Stat Card with Trend --------------------

interface StatCardWithTrendProps {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: string | number;
  valueColor?: string;
  trend?: {
    value: string;
    direction: 'up' | 'down';
    label?: string;
  };
}

export const StatCardWithTrend: React.FC<StatCardWithTrendProps> = ({
  icon,
  iconBg,
  label,
  value,
  valueColor = 'text-gray-900',
  trend,
}) => {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 ${iconBg} rounded-lg`}>
          {icon}
        </div>
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${valueColor}`}>{value}</p>
      {trend && (
        <div className="flex items-center gap-1 mt-2 text-sm">
          <span className={trend.direction === 'up' ? 'text-green-600' : 'text-red-600'}>
            {trend.direction === 'up' ? '↑' : '↓'} {trend.value}
          </span>
          {trend.label && <span className="text-gray-400">{trend.label}</span>}
        </div>
      )}
    </div>
  );
};

// -------------------- Stat Card with Progress --------------------

interface StatCardWithProgressProps {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: string | number;
  valueColor?: string;
  progress: number;
  progressColor?: string;
}

export const StatCardWithProgress: React.FC<StatCardWithProgressProps> = ({
  icon,
  iconBg,
  label,
  value,
  valueColor = 'text-gray-900',
  progress,
  progressColor = 'bg-primary-500',
}) => {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 ${iconBg} rounded-lg`}>
          {icon}
        </div>
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${valueColor}`}>{value}</p>
      <div className="w-full h-2 bg-gray-100 rounded-full mt-3">
        <div
          className={`h-full ${progressColor} rounded-full`}
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>
    </div>
  );
};

// -------------------- Gradient Stat Card --------------------

interface GradientStatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  gradient: string; // e.g., 'from-blue-500 to-blue-600'
}

export const GradientStatCard: React.FC<GradientStatCardProps> = ({
  icon,
  label,
  value,
  gradient,
}) => {
  return (
    <div className={`bg-gradient-to-br ${gradient} rounded-xl p-5 text-white`}>
      <div className="w-8 h-8 opacity-80 mb-3">{icon}</div>
      <p className="text-white/80 text-sm">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
};

// -------------------- Stats Grid --------------------

interface StatsGridProps {
  children: React.ReactNode;
  columns?: 3 | 4 | 5;
}

export const StatsGrid: React.FC<StatsGridProps> = ({ children, columns = 4 }) => {
  const gridCols = {
    3: 'md:grid-cols-3',
    4: 'md:grid-cols-4',
    5: 'md:grid-cols-5',
  };

  return (
    <div className={`grid grid-cols-1 ${gridCols[columns]} gap-4`}>
      {children}
    </div>
  );
};
