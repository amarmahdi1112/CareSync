// ============================================
// Policies Setup (Unintegrated - For Later)
// TODO: Late fees, payment terms, consent forms
// ============================================

import React from 'react';
import { DocumentTextIcon } from '@heroicons/react/24/outline';

interface PoliciesSetupProps {
  onNext: () => void;
  onBack: () => void;
}

const PoliciesSetup: React.FC<PoliciesSetupProps> = ({ onNext, onBack }) => {
  return (
    <div className="text-center py-12">
      <DocumentTextIcon className="w-16 h-16 mx-auto text-gray-300 mb-4" />
      <h2 className="text-xl font-bold text-gray-900 mb-2">Policies & Terms</h2>
      <p className="text-gray-500 mb-8">Coming soon - Configure policies and consent forms</p>
      <div className="flex justify-center gap-4">
        <button onClick={onBack} className="btn btn-secondary">Back</button>
        <button onClick={onNext} className="btn btn-primary">Skip for now</button>
      </div>
    </div>
  );
};

export default PoliciesSetup;
