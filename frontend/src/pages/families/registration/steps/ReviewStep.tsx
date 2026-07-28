import React from 'react';
import { 
  UserIcon, 
  UsersIcon, 
  PhoneIcon, 
  ShieldCheckIcon,
  CheckCircleIcon,
  XCircleIcon,
  CalendarIcon,
} from '@heroicons/react/24/outline';
import { AgeGroupBadge } from '../../../../components/ui';
import { calculateAgeGroup } from '../helpers';
import type { RegistrationData } from '../types';

interface SummaryCardProps {
  icon: React.ReactNode;
  iconBg: string;
  title: string;
  count?: number;
  children: React.ReactNode;
}

const SummaryCard: React.FC<SummaryCardProps> = ({ icon, iconBg, title, count, children }) => (
  <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
    <div className="bg-gray-50 px-5 py-3 flex items-center gap-3 border-b border-gray-100">
      <div className={`w-8 h-8 rounded-lg ${iconBg} flex items-center justify-center`}>
        {icon}
      </div>
      <h3 className="font-semibold text-gray-900">
        {title}
        {count !== undefined && (
          <span className="ml-2 text-sm font-normal text-gray-500">({count})</span>
        )}
      </h3>
    </div>
    <div className="p-5">{children}</div>
  </div>
);

interface ConsentBadgeProps {
  granted: boolean;
  label: string;
}

const ConsentBadge: React.FC<ConsentBadgeProps> = ({ granted, label }) => (
  <div className={`flex items-center gap-2 px-3 py-2 rounded-xl ${
    granted ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-500'
  }`}>
    {granted ? (
      <CheckCircleIcon className="w-5 h-5 text-green-500" />
    ) : (
      <XCircleIcon className="w-5 h-5 text-gray-400" />
    )}
    <span className="text-sm font-medium">{label}</span>
  </div>
);

interface ReviewStepProps {
  data: RegistrationData;
}

export const ReviewStep: React.FC<ReviewStepProps> = ({ data }) => (
    <div className="space-y-6">
      {/* Success Banner */}
      <div className="bg-primary-50 border border-primary-200 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center flex-shrink-0">
            <CheckCircleIcon className="w-4 h-4 text-primary-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-primary-800">Almost Done!</p>
            <p className="text-sm text-primary-600 mt-0.5">
              Review the information below and click "Complete Registration" to finish.
            </p>
          </div>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-blue-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-blue-600">
            {data.secondaryGuardian ? 2 : 1}
          </div>
          <div className="text-xs text-blue-700">Guardians</div>
        </div>
        <div className="bg-green-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-green-600">{data.children.length}</div>
          <div className="text-xs text-green-700">Children</div>
        </div>
        <div className="bg-red-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-red-600">{data.emergencyContacts.length}</div>
          <div className="text-xs text-red-700">Emergency</div>
        </div>
        <div className="bg-purple-50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-purple-600">
            {[data.consents.photoConsent, data.consents.fieldTripConsent, data.consents.emergencyMedicalConsent].filter(Boolean).length}/3
          </div>
          <div className="text-xs text-purple-700">Consents</div>
        </div>
      </div>

      {/* Primary Guardian */}
      <SummaryCard 
        icon={<UserIcon className="w-4 h-4 text-blue-600" />}
        iconBg="bg-blue-100"
        title="Primary Guardian"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-gray-900">
              {data.primaryGuardian.firstName} {data.primaryGuardian.lastName}
            </p>
            <p className="text-sm text-gray-500 mt-0.5">
              {data.primaryGuardian.email}
            </p>
            <p className="text-sm text-gray-500">
              {data.primaryGuardian.cellPhone}
            </p>
          </div>
          <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-lg text-xs font-medium">
            Primary
          </span>
        </div>
      </SummaryCard>

      {/* Secondary Guardian */}
      {data.secondaryGuardian && (
        <SummaryCard 
          icon={<UserIcon className="w-4 h-4 text-purple-600" />}
          iconBg="bg-purple-100"
          title="Secondary Guardian"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-gray-900">
                {data.secondaryGuardian.firstName} {data.secondaryGuardian.lastName}
              </p>
              <p className="text-sm text-gray-500 mt-0.5">
                {data.secondaryGuardian.email}
              </p>
              <p className="text-sm text-gray-500">
                {data.secondaryGuardian.cellPhone}
              </p>
            </div>
            <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium">
              Secondary
            </span>
          </div>
        </SummaryCard>
      )}

      {/* Children */}
      <SummaryCard 
        icon={<UsersIcon className="w-4 h-4 text-green-600" />}
        iconBg="bg-green-100"
        title="Children"
        count={data.children.length}
      >
        <div className="space-y-3">
          {data.children.map((child, index) => (
            <div key={child.id} className={`flex items-center justify-between ${index > 0 ? 'pt-3 border-t border-gray-100' : ''}`}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-100 to-green-200 flex items-center justify-center text-green-600 font-bold">
                  {child.firstName[0]}
                </div>
                <div>
                  <p className="font-medium text-gray-900">
                    {child.firstName} {child.lastName}
                  </p>
                  {child.startDate && (
                    <p className="text-xs text-gray-500 flex items-center gap-1">
                      <CalendarIcon className="w-3 h-3" />
                      Starts: {new Date(child.startDate).toLocaleDateString()}
                    </p>
                  )}
                </div>
              </div>
              {child.dateOfBirth && (
                <AgeGroupBadge ageGroup={calculateAgeGroup(child.dateOfBirth)!} />
              )}
            </div>
          ))}
        </div>
      </SummaryCard>

      {/* Emergency Contacts */}
      <SummaryCard 
        icon={<PhoneIcon className="w-4 h-4 text-red-600" />}
        iconBg="bg-red-100"
        title="Emergency Contacts"
        count={data.emergencyContacts.length}
      >
        <div className="space-y-2">
          {data.emergencyContacts.map((ec) => (
            <div key={ec.id} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
              <div>
                <p className="font-medium text-gray-900 text-sm">
                  {ec.firstName} {ec.lastName}
                </p>
                <p className="text-xs text-gray-500">{ec.relationship} • {ec.cellPhone}</p>
              </div>
              {ec.authorizedPickup && (
                <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs font-medium">
                  Pickup OK
                </span>
              )}
            </div>
          ))}
        </div>
      </SummaryCard>

      {/* Consents */}
      <SummaryCard 
        icon={<ShieldCheckIcon className="w-4 h-4 text-amber-600" />}
        iconBg="bg-amber-100"
        title="Consents"
      >
        <div className="flex flex-wrap gap-2">
          <ConsentBadge granted={data.consents.photoConsent} label="Photo/Video" />
          <ConsentBadge granted={data.consents.fieldTripConsent} label="Field Trips" />
          <ConsentBadge granted={data.consents.emergencyMedicalConsent} label="Emergency Medical" />
        </div>
      </SummaryCard>

      {/* Additional Notes */}
      {data.additionalNotes && (
        <div className="bg-gray-50 rounded-xl p-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Additional Notes</h4>
          <p className="text-sm text-gray-600">{data.additionalNotes}</p>
        </div>
      )}
    </div>
);
