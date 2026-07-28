import React from 'react';
import { UserGroupIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { StatusBadge, AgeGroupBadge } from '../ui';
import type { FamilyListItem } from '../../types/family';

interface FamilyCardProps {
  family: FamilyListItem;
  onClick: () => void;
}

export const FamilyCard: React.FC<FamilyCardProps> = ({ family, onClick }) => {
  return (
    <div
      onClick={onClick}
      className="bg-white rounded-lg border border-gray-200 p-5 hover:shadow-md hover:border-primary-200 transition-all cursor-pointer group"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-4">
          {/* Family avatar */}
          <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center">
            <UserGroupIcon className="w-6 h-6 text-primary-600" />
          </div>
          
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors">
                {family.name}
              </h3>
              <StatusBadge status={family.status} />
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              {family.primaryContact.name} • {family.primaryContact.phone}
            </p>
          </div>
        </div>

        <ChevronRightIcon className="w-5 h-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
      </div>

      {/* Children */}
      <div className="mt-4 pt-4 border-t border-gray-100">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            {family.children.length} {family.children.length === 1 ? 'Child' : 'Children'}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {family.children.map((child) => (
            <div
              key={child.id}
              className="inline-flex items-center space-x-2 bg-gray-50 rounded-lg px-3 py-1.5"
            >
              <span className="text-sm font-medium text-gray-700">{child.firstName}</span>
              <AgeGroupBadge ageGroup={child.ageGroup} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// Compact version for list view
export const FamilyListRow: React.FC<FamilyCardProps> = ({ family, onClick }) => {
  return (
    <div
      onClick={onClick}
      className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm hover:border-primary-200 transition-all cursor-pointer group flex items-center justify-between"
    >
      <div className="flex items-center space-x-4">
        <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
          <UserGroupIcon className="w-5 h-5 text-primary-600" />
        </div>
        
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="font-medium text-gray-900 group-hover:text-primary-600 transition-colors">
              {family.name}
            </h3>
            <StatusBadge status={family.status} size="sm" />
          </div>
          <p className="text-sm text-gray-500">
            {family.primaryContact.name}
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2">
          {family.children.slice(0, 3).map((child) => (
            <AgeGroupBadge key={child.id} ageGroup={child.ageGroup} />
          ))}
          {family.children.length > 3 && (
            <span className="text-xs text-gray-500">+{family.children.length - 3}</span>
          )}
        </div>
        <ChevronRightIcon className="w-5 h-5 text-gray-400 group-hover:text-primary-600" />
      </div>
    </div>
  );
};

export default FamilyCard;
