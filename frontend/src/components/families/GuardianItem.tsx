import React from 'react';
import { 
  UserIcon, 
  PhoneIcon, 
  EnvelopeIcon,
  PencilIcon,
} from '@heroicons/react/24/outline';
import { ColorBadge } from '../ui';
import type { Guardian } from '../../types/family';

interface GuardianItemProps {
  guardian: Guardian;
  onEdit?: () => void;
  variant?: 'compact' | 'detailed';
}

export const GuardianItem: React.FC<GuardianItemProps> = ({ 
  guardian, 
  onEdit,
  variant = 'compact',
}) => {
  if (variant === 'compact') {
    return (
      <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg group">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-gray-200 rounded-full flex items-center justify-center">
            <UserIcon className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <p className="font-medium text-gray-900">
                {guardian.firstName} {guardian.lastName}
              </p>
              {guardian.isPrimary && (
                <ColorBadge label="Primary" color="primary" size="sm" />
              )}
            </div>
            <p className="text-sm text-gray-500">{guardian.relationship}</p>
          </div>
        </div>
        <div className="flex items-center space-x-4 text-sm text-gray-500">
          <a href={`tel:${guardian.phone}`} className="hover:text-primary-600">
            <PhoneIcon className="w-4 h-4" />
          </a>
          <a href={`mailto:${guardian.email}`} className="hover:text-primary-600">
            <EnvelopeIcon className="w-4 h-4" />
          </a>
          {onEdit && (
            <button
              onClick={onEdit}
              className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 hover:bg-white rounded transition-all"
              title="Edit guardian"
            >
              <PencilIcon className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-4">
          <div className="w-12 h-12 bg-gray-200 rounded-full flex items-center justify-center">
            <UserIcon className="w-6 h-6 text-gray-600" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-semibold text-gray-900">
                {guardian.firstName} {guardian.lastName}
              </h3>
              {guardian.isPrimary && (
                <ColorBadge label="Primary Contact" color="primary" size="sm" />
              )}
            </div>
            <p className="text-sm text-gray-500 mt-0.5">{guardian.relationship}</p>
          </div>
        </div>
        {onEdit && (
          <button 
            onClick={onEdit}
            className="p-2 text-gray-400 hover:text-primary-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="Edit guardian"
          >
            <PencilIcon className="w-5 h-5" />
          </button>
        )}
      </div>
      
      <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-2 gap-4">
        <div className="flex items-center space-x-2 text-sm">
          <PhoneIcon className="w-4 h-4 text-gray-400" />
          <a href={`tel:${guardian.phone}`} className="text-gray-600 hover:text-primary-600">
            {guardian.phone}
          </a>
        </div>
        <div className="flex items-center space-x-2 text-sm">
          <EnvelopeIcon className="w-4 h-4 text-gray-400" />
          <a href={`mailto:${guardian.email}`} className="text-gray-600 hover:text-primary-600 truncate">
            {guardian.email}
          </a>
        </div>
      </div>
    </div>
  );
};

// Guardians list component
interface GuardiansListProps {
  guardians: Guardian[];
  onAddGuardian?: () => void;
  onEditGuardian?: (guardian: Guardian) => void;
  variant?: 'compact' | 'detailed';
  title?: string;
}

export const GuardiansList: React.FC<GuardiansListProps> = ({
  guardians,
  onAddGuardian,
  onEditGuardian,
  variant = 'compact',
  title = 'Guardians',
}) => {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        {onAddGuardian && (
          <button
            onClick={onAddGuardian}
            className="inline-flex items-center text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Guardian
          </button>
        )}
      </div>
      
      <div className={variant === 'compact' ? 'space-y-3' : 'space-y-4'}>
        {guardians.map((guardian) => (
          <GuardianItem
            key={guardian.id}
            guardian={guardian}
            onEdit={onEditGuardian ? () => onEditGuardian(guardian) : undefined}
            variant={variant}
          />
        ))}
        
        {guardians.length === 0 && (
          <p className="text-gray-400 text-sm italic text-center py-4">
            No guardians added yet
          </p>
        )}
      </div>
    </div>
  );
};

export default GuardianItem;
