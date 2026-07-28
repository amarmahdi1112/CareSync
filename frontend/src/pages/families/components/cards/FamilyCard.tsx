// ============================================
// Family Card Components - Modern Design
// ============================================

import React from 'react';
import {
  ChevronRightIcon,
  PhoneIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';
import { UserGroupIcon } from '@heroicons/react/24/solid';
import type { FamilyListItem, FamilyStatus, AgeGroup } from '../../types';
import { STATUS_COLORS, AGE_GROUP_COLORS } from '../../constants';

// -------------------- Status Badge --------------------

export const StatusBadge: React.FC<{ status: FamilyStatus; size?: 'sm' | 'md' }> = ({ 
  status, 
  size = 'md' 
}) => {
  const colors = STATUS_COLORS[status];
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';
  
  return (
    <span className={`inline-flex items-center gap-1.5 ${sizeClasses} rounded-full font-medium ${colors.bg} ${colors.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
};

// -------------------- Age Group Badge --------------------

export const AgeGroupBadge: React.FC<{ ageGroup: AgeGroup }> = ({ ageGroup }) => {
  const colors = AGE_GROUP_COLORS[ageGroup];
  
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${colors.bg} ${colors.text}`}>
      {ageGroup}
    </span>
  );
};

// -------------------- Family Card (Grid View) --------------------

interface FamilyCardProps {
  family: FamilyListItem;
  onClick: () => void;
}

export const FamilyCard: React.FC<FamilyCardProps> = ({ family, onClick }) => {
  return (
    <div
      onClick={onClick}
      className="group bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg hover:border-primary-300 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center group-hover:from-primary-200 group-hover:to-primary-300 transition-colors">
            <UserGroupIcon className="w-6 h-6 text-primary-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors">
              {family.name}
            </h3>
            <StatusBadge status={family.status} size="sm" />
          </div>
        </div>
        <ChevronRightIcon className="w-5 h-5 text-gray-300 group-hover:text-primary-500 group-hover:translate-x-0.5 transition-all" />
      </div>

      {/* Contact Info */}
      <div className="mt-4 space-y-2">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <div className="w-7 h-7 rounded-lg bg-gray-50 flex items-center justify-center">
            <PhoneIcon className="w-4 h-4 text-gray-400" />
          </div>
          <span className="truncate">{family.primaryContact.phone || 'No phone'}</span>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <div className="w-7 h-7 rounded-lg bg-gray-50 flex items-center justify-center">
            <EnvelopeIcon className="w-4 h-4 text-gray-400" />
          </div>
          <span className="truncate">{family.primaryContact.email || 'No email'}</span>
        </div>
      </div>

      {/* Children */}
      <div className="mt-4 pt-4 border-t border-gray-100">
        {(() => {
          const activeChildren = family.children.filter(c => c.isActive !== false);
          return (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  {activeChildren.length} {activeChildren.length === 1 ? 'Child' : 'Children'}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {activeChildren.slice(0, 3).map((child) => (
                  <div
                    key={child.id}
                    className="inline-flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5"
                  >
                    <span className="text-sm font-medium text-gray-700">{child.firstName}</span>
                    <AgeGroupBadge ageGroup={child.ageGroup} />
                  </div>
                ))}
                {activeChildren.length > 3 && (
                  <span className="inline-flex items-center px-3 py-1.5 text-sm text-gray-500">
                    +{activeChildren.length - 3} more
                  </span>
                )}
              </div>
            </>
          );
        })()}
      </div>
    </div>
  );
};

// -------------------- Family Row (List View) --------------------

export const FamilyRow: React.FC<FamilyCardProps> = ({ family, onClick }) => {
  return (
    <div
      onClick={onClick}
      className="group bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-primary-300 transition-all cursor-pointer flex items-center gap-4"
    >
      {/* Avatar */}
      <div className="w-12 h-12 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center flex-shrink-0">
        <UserGroupIcon className="w-6 h-6 text-primary-600" />
      </div>

      {/* Main Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors truncate">
            {family.name}
          </h3>
          <StatusBadge status={family.status} size="sm" />
        </div>
        <p className="text-sm text-gray-500 truncate">
          {family.primaryContact.name} • {family.primaryContact.phone}
        </p>
      </div>

      {/* Children Badges */}
      <div className="hidden md:flex items-center gap-2 flex-shrink-0">
        {(() => {
          const activeChildren = family.children.filter(c => c.isActive !== false);
          return (
            <>
              {activeChildren.slice(0, 2).map((child) => (
                <div
                  key={child.id}
                  className="inline-flex items-center gap-1.5 bg-gray-50 rounded-lg px-2.5 py-1"
                >
                  <span className="text-sm text-gray-600">{child.firstName}</span>
                  <AgeGroupBadge ageGroup={child.ageGroup} />
                </div>
              ))}
              {activeChildren.length > 2 && (
                <span className="text-sm text-gray-400">+{activeChildren.length - 2}</span>
              )}
            </>
          );
        })()}
      </div>

      {/* Arrow */}
      <ChevronRightIcon className="w-5 h-5 text-gray-300 group-hover:text-primary-500 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
    </div>
  );
};

// -------------------- Quick Actions --------------------

interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'danger';
}

export const QuickAction: React.FC<QuickActionProps> = ({
  icon,
  label,
  onClick,
  variant = 'default',
}) => {
  const variants = {
    default: 'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
    primary: 'text-primary-600 hover:text-primary-700 hover:bg-primary-50',
    danger: 'text-red-600 hover:text-red-700 hover:bg-red-50',
  };

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${variants[variant]}`}
    >
      {icon}
      {label}
    </button>
  );
};
