import React from 'react';
import { CameraIcon, MapPinIcon, HeartIcon, DocumentTextIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { TextArea } from '../components/FormFields';
import type { Consents } from '../types';

interface ConsentCardProps {
  icon: React.ReactNode;
  iconBg: string;
  title: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  required?: boolean;
}

const ConsentCard: React.FC<ConsentCardProps> = ({ 
  icon, 
  iconBg, 
  title, 
  description, 
  checked, 
  onChange,
  required,
}) => (
  <label className={`block cursor-pointer rounded-xl border-2 p-4 transition-all ${
    checked 
      ? 'border-green-500 bg-green-50/50' 
      : 'border-gray-200 hover:border-gray-300 bg-white'
  }`}>
    <div className="flex items-start gap-4">
      <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
        {icon}
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-gray-900">
              {title}
              {required && <span className="text-red-500 ml-1">*</span>}
            </p>
            <p className="text-sm text-gray-500 mt-0.5">{description}</p>
          </div>
          <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all ${
            checked 
              ? 'border-green-500 bg-green-500' 
              : 'border-gray-300'
          }`}>
            {checked && <CheckCircleIcon className="w-4 h-4 text-white" />}
          </div>
        </div>
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
    </div>
  </label>
);

interface ConsentsStepProps {
  consents: Consents;
  additionalNotes: string;
  onUpdateConsent: (field: keyof Consents, value: boolean) => void;
  onUpdateNotes: (value: string) => void;
}

export const ConsentsStep: React.FC<ConsentsStepProps> = ({ 
  consents, 
  additionalNotes, 
  onUpdateConsent, 
  onUpdateNotes 
}) => {
  const allOptionalGranted = consents.photoConsent && consents.fieldTripConsent;
  
  return (
    <div className="space-y-6">
      {/* Info Banner */}
      <div className="bg-green-50 border border-green-200 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center flex-shrink-0">
            <CheckCircleIcon className="w-4 h-4 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-green-800">Parental Consents</p>
            <p className="text-sm text-green-600 mt-0.5">
              Review each consent below. Emergency medical consent is required.
            </p>
          </div>
        </div>
      </div>

      {/* Optional Consents */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Optional Consents</h3>
        
        <ConsentCard
          icon={<CameraIcon className="w-5 h-5 text-blue-600" />}
          iconBg="bg-blue-100"
          title="Photo & Video Consent"
          description="I consent to photographs/videos of my child being taken for program use"
          checked={consents.photoConsent}
          onChange={(v) => onUpdateConsent('photoConsent', v)}
        />
        
        <ConsentCard
          icon={<MapPinIcon className="w-5 h-5 text-purple-600" />}
          iconBg="bg-purple-100"
          title="Field Trip Consent"
          description="I consent to my child participating in supervised off-site activities"
          checked={consents.fieldTripConsent}
          onChange={(v) => onUpdateConsent('fieldTripConsent', v)}
        />
        
        {allOptionalGranted && (
          <p className="text-sm text-green-600 text-center py-2">
            ✓ All optional consents granted
          </p>
        )}
      </div>

      {/* Required Consent */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Required Consent</h3>
        
        <ConsentCard
          icon={<HeartIcon className="w-5 h-5 text-red-600" />}
          iconBg="bg-red-100"
          title="Emergency Medical Treatment"
          description="I authorize emergency medical treatment if guardians cannot be reached"
          checked={consents.emergencyMedicalConsent}
          onChange={(v) => onUpdateConsent('emergencyMedicalConsent', v)}
          required
        />
      </div>

      {/* Additional Notes */}
      <div className="pt-4 border-t border-gray-200">
        <div className="flex items-center gap-2 mb-3">
          <DocumentTextIcon className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-700">Additional Notes (Optional)</h3>
        </div>
        <TextArea
          label=""
          value={additionalNotes}
          onChange={onUpdateNotes}
          rows={3}
          placeholder="Any additional information you'd like us to know about your family..."
        />
      </div>
    </div>
  );
};
