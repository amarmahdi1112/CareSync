import React from 'react';
import { UserIcon, UserPlusIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { GuardianForm } from '../components/GuardianForm';
import { createEmptyGuardian } from '../helpers';
import type { Guardian } from '../types';

// ============================================
// GUARDIAN 1 STEP (Primary) - Redesigned
// ============================================

interface Guardian1StepProps {
  guardian: Guardian;
  onUpdate: (field: keyof Guardian, value: string) => void;
}

export const Guardian1Step: React.FC<Guardian1StepProps> = ({ guardian, onUpdate }) => (
  <div className="space-y-6">
    {/* Info Banner */}
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
          <UserIcon className="w-4 h-4 text-blue-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-blue-800">Primary Guardian</p>
          <p className="text-sm text-blue-600 mt-0.5">
            This person will be the main point of contact for the family.
          </p>
        </div>
      </div>
    </div>

    <GuardianForm 
      guardian={guardian} 
      onChange={onUpdate}
    />
  </div>
);

// ============================================
// GUARDIAN 2 STEP (Secondary) - Redesigned
// ============================================

interface Guardian2StepProps {
  guardian: Guardian | null;
  skipSecondGuardian: boolean;
  onUpdate: (field: keyof Guardian, value: string) => void;
  onSkip: () => void;
  onAddGuardian: () => void;
}

export const Guardian2Step: React.FC<Guardian2StepProps> = ({ 
  guardian, 
  skipSecondGuardian,
  onUpdate, 
  onSkip,
  onAddGuardian,
}) => (
  <div className="space-y-6">
    {skipSecondGuardian ? (
      <div className="text-center py-12">
        <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
          <UserIcon className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">No Second Guardian</h3>
        <p className="text-gray-500 mb-6 max-w-sm mx-auto">
          You've chosen to skip adding a second guardian. You can always add one later.
        </p>
        <button
          type="button"
          onClick={onAddGuardian}
          className="btn btn-primary"
        >
          <UserPlusIcon className="w-4 h-4" />
          Add Second Guardian
        </button>
      </div>
    ) : (
      <>
        {/* Info Banner */}
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
              <UserIcon className="w-4 h-4 text-purple-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-purple-800">Secondary Guardian (Optional)</p>
              <p className="text-sm text-purple-600 mt-0.5">
                Add another parent, guardian, or authorized contact.
              </p>
            </div>
          </div>
        </div>

        <GuardianForm 
          guardian={guardian || createEmptyGuardian()} 
          onChange={onUpdate}
        />
        
        <button
          type="button"
          onClick={onSkip}
          className="w-full py-4 border-2 border-dashed border-gray-200 rounded-xl text-gray-500 hover:border-gray-300 hover:text-gray-600 transition-colors flex items-center justify-center gap-2"
        >
          <XMarkIcon className="w-5 h-5" />
          Skip - No second guardian needed
        </button>
      </>
    )}
  </div>
);
