// ============================================
// Financial Setup - Step 6 (Unintegrated)
// Business info, tax ID, banking details
// ============================================

import React, { useState } from 'react';
import {
  BuildingLibraryIcon,
  CreditCardIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline';

// -------------------- Types --------------------

interface FinancialData {
  business_number: string;
  gst_number: string;
  bank_name: string;
  bank_transit: string;
  bank_institution: string;
  bank_account: string;
  payment_terms_days: number;
  late_fee_enabled: boolean;
  late_fee_percentage: number;
  late_fee_grace_days: number;
}

interface FinancialSetupProps {
  data: FinancialData;
  onChange: (data: FinancialData) => void;
  onNext: () => void;
  onBack: () => void;
  onSkip?: () => void;
}

// -------------------- Component --------------------

const FinancialSetup: React.FC<FinancialSetupProps> = ({
  data,
  onChange,
  onNext,
  onBack,
  onSkip,
}) => {
  const [errors, setErrors] = useState<Record<string, string>>({});

  const updateField = <K extends keyof FinancialData>(field: K, value: FinancialData[K]) => {
    onChange({ ...data, [field]: value });
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const formatBusinessNumber = (value: string): string => {
    const digits = value.replace(/\D/g, '');
    if (digits.length <= 9) return digits;
    return `${digits.slice(0, 9)} ${digits.slice(9, 11)}`.trim();
  };

  const validate = (): boolean => {
    // Financial setup is optional, so minimal validation
    return true;
  };

  const handleNext = () => {
    if (validate()) onNext();
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="text-center">
        <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center">
          <BuildingLibraryIcon className="w-8 h-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Financial Setup</h2>
        <p className="text-gray-600">Configure your business and banking information</p>
      </div>

      {/* Security Notice */}
      <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex gap-3">
        <ShieldCheckIcon className="w-6 h-6 text-green-500 flex-shrink-0" />
        <div>
          <p className="text-sm text-green-800 font-medium">Your information is secure</p>
          <p className="text-sm text-green-600 mt-1">
            All financial data is encrypted and stored securely. We never share your banking 
            information with third parties.
          </p>
        </div>
      </div>

      {/* Business Information */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <DocumentTextIcon className="w-5 h-5 text-blue-500" />
          Business Information
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Business Number (BN)
            </label>
            <input
              type="text"
              value={data.business_number}
              onChange={(e) => updateField('business_number', formatBusinessNumber(e.target.value))}
              placeholder="123456789 RT0001"
              maxLength={14}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
            />
            <p className="text-xs text-gray-500 mt-1">CRA 9-digit business number</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              GST/HST Number (Optional)
            </label>
            <input
              type="text"
              value={data.gst_number}
              onChange={(e) => updateField('gst_number', e.target.value)}
              placeholder="RT0001"
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>
      </div>

      {/* Banking Information */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <CreditCardIcon className="w-5 h-5 text-blue-500" />
          Banking Information
          <span className="ml-auto text-xs text-gray-400 flex items-center gap-1">
            <LockClosedIcon className="w-3 h-3" /> Encrypted
          </span>
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Bank Name</label>
            <select
              value={data.bank_name}
              onChange={(e) => updateField('bank_name', e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
            >
              <option value="">Select your bank...</option>
              <option value="TD Canada Trust">TD Canada Trust</option>
              <option value="RBC Royal Bank">RBC Royal Bank</option>
              <option value="Scotiabank">Scotiabank</option>
              <option value="BMO Bank of Montreal">BMO Bank of Montreal</option>
              <option value="CIBC">CIBC</option>
              <option value="ATB Financial">ATB Financial</option>
              <option value="National Bank">National Bank</option>
              <option value="Servus Credit Union">Servus Credit Union</option>
              <option value="Other">Other</option>
            </select>
          </div>
          
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Transit #</label>
              <input
                type="text"
                value={data.bank_transit}
                onChange={(e) => updateField('bank_transit', e.target.value.replace(/\D/g, '').slice(0, 5))}
                placeholder="12345"
                maxLength={5}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Institution #</label>
              <input
                type="text"
                value={data.bank_institution}
                onChange={(e) => updateField('bank_institution', e.target.value.replace(/\D/g, '').slice(0, 3))}
                placeholder="004"
                maxLength={3}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Account #</label>
              <input
                type="text"
                value={data.bank_account}
                onChange={(e) => updateField('bank_account', e.target.value.replace(/\D/g, '').slice(0, 12))}
                placeholder="1234567"
                maxLength={12}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
          <p className="text-xs text-gray-500">
            Find these numbers on a void cheque or in your online banking.
          </p>
        </div>
      </div>

      {/* Payment Terms */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Payment Terms</h3>
        
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Payment Due (days after invoice)
          </label>
          <div className="flex gap-2">
            {[7, 14, 30, 45].map((days) => (
              <button
                key={days}
                type="button"
                onClick={() => updateField('payment_terms_days', days)}
                className={`flex-1 py-3 rounded-xl font-medium transition-all ${
                  data.payment_terms_days === days
                    ? 'bg-primary-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {days} days
              </button>
            ))}
          </div>
        </div>

        {/* Late Fee Toggle */}
        <div className="border-t border-gray-100 pt-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-medium text-gray-900">Enable Late Fees</p>
              <p className="text-sm text-gray-500">Automatically add late fees to overdue invoices</p>
            </div>
            <button
              type="button"
              onClick={() => updateField('late_fee_enabled', !data.late_fee_enabled)}
              className={`relative w-14 h-7 rounded-full transition-colors ${
                data.late_fee_enabled ? 'bg-primary-500' : 'bg-gray-200'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                  data.late_fee_enabled ? 'translate-x-7' : ''
                }`}
              />
            </button>
          </div>

          {data.late_fee_enabled && (
            <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-xl">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Late Fee %</label>
                <div className="relative">
                  <input
                    type="number"
                    min="0"
                    max="25"
                    step="0.5"
                    value={data.late_fee_percentage}
                    onChange={(e) => updateField('late_fee_percentage', parseFloat(e.target.value) || 0)}
                    className="w-full px-4 py-3 pr-8 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">%</span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Grace Period</label>
                <div className="relative">
                  <input
                    type="number"
                    min="0"
                    max="30"
                    value={data.late_fee_grace_days}
                    onChange={(e) => updateField('late_fee_grace_days', parseInt(e.target.value) || 0)}
                    className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">days</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

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

export default FinancialSetup;
