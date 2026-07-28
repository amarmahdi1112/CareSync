import React from 'react';
import type { AgeGroup } from '../../types/family';

// Status Badge variants
export type StatusVariant = 'active' | 'inactive' | 'pending' | 'archived' | 'success' | 'warning' | 'error';

// Re-export AgeGroup for consumers
export type { AgeGroup };

interface StatusBadgeProps {
  status: StatusVariant;
  label?: string;
  size?: 'sm' | 'md';
}

const statusStyles: Record<StatusVariant, string> = {
  active: 'bg-green-100 text-green-800',
  inactive: 'bg-gray-100 text-gray-800',
  pending: 'bg-yellow-100 text-yellow-800',
  archived: 'bg-red-100 text-red-800',
  success: 'bg-green-100 text-green-800',
  warning: 'bg-yellow-100 text-yellow-800',
  error: 'bg-red-100 text-red-800',
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, size = 'sm' }) => {
  const displayLabel = label || status.charAt(0).toUpperCase() + status.slice(1);
  const sizeClass = size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-sm';

  return (
    <span className={`inline-flex items-center rounded-full font-medium ${statusStyles[status]} ${sizeClass}`}>
      {displayLabel}
    </span>
  );
};

// Age Group Badge
interface AgeGroupBadgeProps {
  ageGroup: AgeGroup;
}

const ageGroupStyles: Record<AgeGroup, string> = {
  'Infant': 'bg-pink-100 text-pink-700',
  'Toddler': 'bg-primary-100 text-primary-700',
  'Preschool': 'bg-purple-100 text-purple-700',
  'School-Age': 'bg-orange-100 text-orange-700',
};

export const AgeGroupBadge: React.FC<AgeGroupBadgeProps> = ({ ageGroup }) => {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ageGroupStyles[ageGroup]}`}>
      {ageGroup}
    </span>
  );
};

// Generic colored badge
interface ColorBadgeProps {
  label: string;
  color: 'primary' | 'gray' | 'green' | 'blue' | 'yellow' | 'red' | 'purple' | 'pink' | 'orange';
  size?: 'sm' | 'md';
}

const colorStyles: Record<ColorBadgeProps['color'], string> = {
  primary: 'bg-primary-100 text-primary-700',
  gray: 'bg-gray-100 text-gray-700',
  green: 'bg-green-100 text-green-700',
  blue: 'bg-primary-100 text-primary-700',
  yellow: 'bg-yellow-100 text-yellow-700',
  red: 'bg-red-100 text-red-700',
  purple: 'bg-purple-100 text-purple-700',
  pink: 'bg-pink-100 text-pink-700',
  orange: 'bg-orange-100 text-orange-700',
};

export const ColorBadge: React.FC<ColorBadgeProps> = ({ label, color, size = 'sm' }) => {
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm';

  return (
    <span className={`inline-flex items-center rounded font-medium ${colorStyles[color]} ${sizeClass}`}>
      {label}
    </span>
  );
};

export default StatusBadge;
