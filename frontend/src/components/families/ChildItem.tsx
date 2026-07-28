import React from 'react';
import { UserIcon, CalendarIcon, PencilIcon } from '@heroicons/react/24/outline';
import { AgeGroupBadge } from '../ui';
import { calculateAge } from '../../utils/date';
import type { Child } from '../../types/family';

interface ChildItemProps {
  child: Child;
  onClick?: () => void;
  onEdit?: () => void;
  variant?: 'compact' | 'detailed';
}

export const ChildItem: React.FC<ChildItemProps> = ({ 
  child, 
  onClick,
  onEdit,
  variant = 'compact',
}) => {
  const isClickable = !!onClick;
  const baseClass = isClickable 
    ? 'hover:bg-gray-100 cursor-pointer transition-colors' 
    : '';

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit?.();
  };

  if (variant === 'compact') {
    return (
      <div
        onClick={onClick}
        className={`flex items-center justify-between p-4 bg-gray-50 rounded-lg group ${baseClass}`}
      >
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
            <UserIcon className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <p className="font-medium text-gray-900">
              {child.firstName} {child.lastName}
            </p>
            {child.dateOfBirth && (
              <p className="text-sm text-gray-500">{calculateAge(child.dateOfBirth)} old</p>
            )}
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <AgeGroupBadge ageGroup={child.ageGroup} />
          {child.status && (
            <span className={`w-2 h-2 rounded-full ${
              child.status === 'active' ? 'bg-green-500' : 'bg-gray-400'
            }`} />
          )}
          {onEdit && (
            <button
              onClick={handleEdit}
              className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 hover:bg-white rounded transition-all"
              title="Edit child"
            >
              <PencilIcon className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onClick}
      className={`border border-gray-200 rounded-lg p-4 hover:border-primary-200 group ${baseClass}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-4">
          <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center">
            <UserIcon className="w-6 h-6 text-primary-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">
              {child.firstName} {child.lastName}
            </h3>
            <div className="flex items-center space-x-4 mt-1 text-sm text-gray-500">
              {child.dateOfBirth && (
                <>
                  <span className="flex items-center">
                    <CalendarIcon className="w-4 h-4 mr-1" />
                    {new Date(child.dateOfBirth).toLocaleDateString()}
                  </span>
                  <span>{calculateAge(child.dateOfBirth)} old</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <div className="flex flex-col items-end space-y-2">
            <AgeGroupBadge ageGroup={child.ageGroup} />
            {child.status && (
              <span className={`text-xs font-medium ${
                child.status === 'active' ? 'text-green-600' : 'text-gray-500'
              }`}>
                {child.status.charAt(0).toUpperCase() + child.status.slice(1)}
              </span>
            )}
          </div>
          {onEdit && (
            <button
              onClick={handleEdit}
              className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 hover:bg-gray-100 rounded transition-all"
              title="Edit child"
            >
              <PencilIcon className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// Children list component
interface ChildrenListProps {
  children: Child[];
  onChildClick?: (child: Child) => void;
  onAddChild?: () => void;
  onEditChild?: (child: Child) => void;
  variant?: 'compact' | 'detailed';
  title?: string;
}

export const ChildrenList: React.FC<ChildrenListProps> = ({
  children,
  onChildClick,
  onAddChild,
  onEditChild,
  variant = 'compact',
  title = 'Children',
}) => {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        {onAddChild && (
          <button
            onClick={onAddChild}
            className="inline-flex items-center text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Child
          </button>
        )}
      </div>
      
      <div className={variant === 'compact' ? 'space-y-3' : 'space-y-4'}>
        {children.map((child) => (
          <ChildItem
            key={child.id}
            child={child}
            onClick={onChildClick ? () => onChildClick(child) : undefined}
            onEdit={onEditChild ? () => onEditChild(child) : undefined}
            variant={variant}
          />
        ))}
        
        {children.length === 0 && (
          <p className="text-gray-400 text-sm italic text-center py-4">
            No children added yet
          </p>
        )}
      </div>
    </div>
  );
};

export default ChildItem;
