// ============================================
// Subsidy & Funding Setup - Step 5 (Unintegrated)
// ELCC, AFCC, subsidy rates configuration
// ============================================

import React, { useState } from 'react';
import {
  BanknotesIcon,
  DocumentCheckIcon,
  InformationCircleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

// -------------------- Types --------------------

interface SubsidyRate {
  age_group: string;
  daily_rate: number;
  subsidy_rate: number;
  parent_fee: number;
}

interface SubsidyData {
  elcc_enrolled: boolean;
  elcc_certificate_number: string;
  afcc_provider: boolean;
  afcc_provider_id: string;
  subsidy_rates: SubsidyRate[];
  accepts_subsidy_children: boolean;
}

interface SubsidySetupProps {
  data: SubsidyData;
  onChange: (data: SubsidyData) => void;
  onNext: () => void;
  onBack: () => void;
  onSkip?: () => void;
}

// -------------------- Constants --------------------

const AGE_GROUP_DEFAULTS: SubsidyRate[] = [
  { age_group: 'infant', daily_rate: 65.00, subsidy_rate: 45.00, parent_fee: 20.00 },
  { age_group: 'toddler', daily_rate: 55.00, subsidy_rate: 40.00, parent_fee: 15.00 },
  { age_group: 'preschool', daily_rate: 50.00, subsidy_rate: 35.00, parent_fee: 15.00 },
  { age_group: 'kindergarten', daily_rate: 45.00, subsidy_rate: 30.00, parent_fee: 15.00 },
  { age_group: 'school_age', daily_rate: 35.00, subsidy_rate: 25.00, parent_fee: 10.00 },
];

const AGE_GROUP_LABELS: Record<string, string> = {
  infant: 'Infant (0-18 mo)',
  toddler: 'Toddler (18-36 mo)',
  preschool: 'Preschool (3-5 yr)',
  kindergarten: 'Kindergarten',
  school_age: 'School Age (6-12)',
};

// -------------------- Component --------------------

const SubsidySetup: React.FC<SubsidySetupProps> = ({
  data,
  onChange,
  onNext,
  onBack,
  onSkip,
}) => {
  const [errors, setErrors] = useState<Record<string, string>>({});

  const updateField = <K extends keyof SubsidyData>(field: K, value: SubsidyData[K]) => {
    onChange({ ...data, [field]: value });
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const updateRate = (index: number, field: keyof SubsidyRate, value: number) => {
    const newRates = [...data.subsidy_rates];
    newRates[index] = { ...newRates[index], [field]: value };
    
    // Auto-calculate parent fee
    if (field === 'daily_rate' || field === 'subsidy_rate') {
      newRates[index].parent_fee = Math.max(0, newRates[index].daily_rate - newRates[index].subsidy_rate);
    }
    
    updateField('subsidy_rates', newRates);
  };

  const initializeRates = () => {
    updateField('subsidy_rates', AGE_GROUP_DEFAULTS);
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    if (data.elcc_enrolled && !data.elcc_certificate_number.trim()) {
      newErrors.elcc_certificate_number = 'ELCC certificate number is required';
    }
    
    if (data.afcc_provider && !data.afcc_provider_id.trim()) {
      newErrors.afcc_provider_id = 'AFCC provider ID is required';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (validate()) onNext();
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="text-center">
        <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-green-500 to-emerald-500 flex items-center justify-center">
          <BanknotesIcon className="w-8 h-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Subsidy & Funding</h2>
        <p className="text-gray-600">Configure government funding programs and rates</p>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex gap-3">
        <InformationCircleIcon className="w-6 h-6 text-blue-500 flex-shrink-0" />
        <div>
          <p className="text-sm text-blue-800 font-medium">Alberta Child Care Funding</p>
          <p className="text-sm text-blue-600 mt-1">
            ELCC (Early Learning Child Care) and AFCC (Affordable Child Care) are provincial funding programs 
            that help reduce child care costs for families.
          </p>
        </div>
      </div>

      {/* ELCC Enrollment */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-100 to-purple-100 flex items-center justify-center">
              <SparklesIcon className="w-6 h-6 text-violet-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">ELCC Program</h3>
              <p className="text-sm text-gray-500">Early Learning Child Care subsidy</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => updateField('elcc_enrolled', !data.elcc_enrolled)}
            className={`relative w-14 h-7 rounded-full transition-colors ${
              data.elcc_enrolled ? 'bg-primary-500' : 'bg-gray-200'
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                data.elcc_enrolled ? 'translate-x-7' : ''
              }`}
            />
          </button>
        </div>
        
        {data.elcc_enrolled && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <label className="block text-sm font-medium text-gray-700 mb-2">ELCC Certificate Number</label>
            <input
              type="text"
              value={data.elcc_certificate_number}
              onChange={(e) => updateField('elcc_certificate_number', e.target.value)}
              placeholder="e.g., ELCC-2024-12345"
              className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-primary-500 ${
                errors.elcc_certificate_number ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.elcc_certificate_number && (
              <p className="text-red-500 text-sm mt-1">{errors.elcc_certificate_number}</p>
            )}
          </div>
        )}
      </div>

      {/* AFCC Provider */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-100 to-green-100 flex items-center justify-center">
              <DocumentCheckIcon className="w-6 h-6 text-emerald-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">AFCC Provider</h3>
              <p className="text-sm text-gray-500">Affordable Child Care Benefit provider</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => updateField('afcc_provider', !data.afcc_provider)}
            className={`relative w-14 h-7 rounded-full transition-colors ${
              data.afcc_provider ? 'bg-primary-500' : 'bg-gray-200'
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                data.afcc_provider ? 'translate-x-7' : ''
              }`}
            />
          </button>
        </div>
        
        {data.afcc_provider && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <label className="block text-sm font-medium text-gray-700 mb-2">AFCC Provider ID</label>
            <input
              type="text"
              value={data.afcc_provider_id}
              onChange={(e) => updateField('afcc_provider_id', e.target.value)}
              placeholder="e.g., AFCC-AB-12345"
              className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-primary-500 ${
                errors.afcc_provider_id ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.afcc_provider_id && (
              <p className="text-red-500 text-sm mt-1">{errors.afcc_provider_id}</p>
            )}
          </div>
        )}
      </div>

      {/* Subsidy Rates Table */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <BanknotesIcon className="w-5 h-5 text-green-500" />
            Rate Configuration
          </h3>
          {data.subsidy_rates.length === 0 && (
            <button
              type="button"
              onClick={initializeRates}
              className="text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              Use Default Rates
            </button>
          )}
        </div>
        
        {data.subsidy_rates.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-gray-500 border-b border-gray-100">
                  <th className="pb-3 font-medium">Age Group</th>
                  <th className="pb-3 font-medium text-right">Daily Rate</th>
                  <th className="pb-3 font-medium text-right">Subsidy</th>
                  <th className="pb-3 font-medium text-right">Parent Fee</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.subsidy_rates.map((rate, index) => (
                  <tr key={rate.age_group}>
                    <td className="py-3 font-medium text-gray-900">
                      {AGE_GROUP_LABELS[rate.age_group]}
                    </td>
                    <td className="py-3">
                      <div className="flex items-center justify-end">
                        <span className="text-gray-400 mr-1">$</span>
                        <input
                          type="number"
                          min="0"
                          step="0.50"
                          value={rate.daily_rate}
                          onChange={(e) => updateRate(index, 'daily_rate', parseFloat(e.target.value) || 0)}
                          className="w-20 px-2 py-1 text-right border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                        />
                      </div>
                    </td>
                    <td className="py-3">
                      <div className="flex items-center justify-end">
                        <span className="text-gray-400 mr-1">$</span>
                        <input
                          type="number"
                          min="0"
                          step="0.50"
                          value={rate.subsidy_rate}
                          onChange={(e) => updateRate(index, 'subsidy_rate', parseFloat(e.target.value) || 0)}
                          className="w-20 px-2 py-1 text-right border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                        />
                      </div>
                    </td>
                    <td className="py-3 text-right">
                      <span className="inline-flex items-center px-3 py-1 bg-green-100 text-green-700 rounded-lg font-medium">
                        ${rate.parent_fee.toFixed(2)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <BanknotesIcon className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p>No rates configured yet</p>
            <button
              type="button"
              onClick={initializeRates}
              className="mt-2 text-primary-600 hover:text-primary-700 font-medium"
            >
              Initialize with default rates
            </button>
          </div>
        )}
      </div>

      {/* Accept Subsidy Children */}
      <label className="flex items-center gap-3 p-4 bg-gray-50 rounded-xl cursor-pointer">
        <input
          type="checkbox"
          checked={data.accepts_subsidy_children}
          onChange={(e) => updateField('accepts_subsidy_children', e.target.checked)}
          className="w-5 h-5 text-primary-600 rounded focus:ring-primary-500"
        />
        <span className="text-gray-700">
          We accept children receiving government subsidy assistance
        </span>
      </label>

      {/* Navigation */}
      <div className="flex justify-between pt-4">
        <button
          type="button"
          onClick={onBack}
          className="px-6 py-3 text-gray-600 hover:text-gray-900 font-medium transition-colors"
        >
          ← Back
        </button>
        <div className="flex gap-3">
          {onSkip && (
            <button
              type="button"
              onClick={onSkip}
              className="px-6 py-3 text-gray-500 hover:text-gray-700 font-medium transition-colors"
            >
              Skip for now
            </button>
          )}
          <button
            type="button"
            onClick={handleNext}
            className="px-8 py-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white font-semibold rounded-xl hover:from-primary-600 hover:to-primary-700 transition-all shadow-lg shadow-primary-500/30"
          >
            Continue →
          </button>
        </div>
      </div>
    </div>
  );
};

export default SubsidySetup;
