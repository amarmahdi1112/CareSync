// ============================================
// Staff & Ratios Setup (Unintegrated - For Later)
// TODO: Staff-to-child ratios, director info
// ============================================

import React from 'react';
import { UsersIcon } from '@heroicons/react/24/outline';

interface StaffSetupProps {
  onNext: () => void;
  onBack: () => void;
}

const StaffSetup: React.FC<StaffSetupProps> = ({ onNext, onBack }) => {
  return (
    <div className="text-center py-12">
      <UsersIcon className="w-16 h-16 mx-auto text-gray-300 mb-4" />
      <h2 className="text-xl font-bold text-gray-900 mb-2">Staff & Ratios</h2>
      <p className="text-gray-500 mb-8">Coming soon - Configure staff structure and ratios</p>
      <div className="flex justify-center gap-4">
        <button onClick={onBack} className="btn btn-secondary">Back</button>
        <button onClick={onNext} className="btn btn-primary">Skip for now</button>
      </div>
    </div>
  );
};

export default StaffSetup;
