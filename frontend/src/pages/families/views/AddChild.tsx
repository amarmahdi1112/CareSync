// ============================================
// Add Child View - Completely Redesigned
// ============================================

import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeftIcon,
  UserPlusIcon,
  UserIcon,
  HeartIcon,
  XMarkIcon,
  CheckIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

// Form components from registration
import { Input, TextArea, Select, RadioGroup } from '../registration/components/FormFields';

// GraphQL
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Components
import { AgeGroupBadge } from '../components/cards';
import { DetailSkeleton } from '../components/layout';
import type { AgeGroup } from '../types';

// -------------------- Types --------------------

interface ChildFormData {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  startDate: string;
  gender: string;
  healthCareNumber: string;
  allergies: string;
  medicalConditions: string;
  medications: string;
  immunizationUpToDate: boolean | null;
  doctorName: string;
  doctorPhone: string;
}

// -------------------- Constants --------------------

const GENDER_OPTIONS = [
  { value: '', label: 'Select Gender' },
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
];

// -------------------- Helpers --------------------

const calculateAgeGroup = (dob: string): AgeGroup | null => {
  if (!dob) return null;
  const birth = new Date(dob);
  const today = new Date();
  let months = (today.getFullYear() - birth.getFullYear()) * 12 + (today.getMonth() - birth.getMonth());
  if (today.getDate() < birth.getDate()) months--;
  if (months <= 19) return 'Infant';
  if (months <= 36) return 'Toddler';
  if (months <= 77) return 'Preschool';
  return 'School-Age';
};

const calculateAge = (dob: string): string => {
  if (!dob) return '';
  const birth = new Date(dob);
  const today = new Date();
  const years = today.getFullYear() - birth.getFullYear();
  const months = today.getMonth() - birth.getMonth();
  const totalMonths = years * 12 + months - (today.getDate() < birth.getDate() ? 1 : 0);
  
  if (totalMonths < 12) return `${totalMonths} months`;
  const yrs = Math.floor(totalMonths / 12);
  const mos = totalMonths % 12;
  return mos > 0 ? `${yrs} yr ${mos} mo` : `${yrs} years`;
};

const createEmptyChild = (): ChildFormData => ({
  firstName: '',
  lastName: '',
  dateOfBirth: '',
  startDate: new Date().toISOString().split('T')[0], // Default to today
  gender: '',
  healthCareNumber: '',
  allergies: '',
  medicalConditions: '',
  medications: '',
  immunizationUpToDate: null,
  doctorName: '',
  doctorPhone: '',
});

// -------------------- Section Card Component --------------------

interface SectionCardProps {
  icon: React.ReactNode;
  title: string;
  description?: string;
  children: React.ReactNode;
  variant?: 'default' | 'medical';
}

const SectionCard: React.FC<SectionCardProps> = ({ icon, title, description, children, variant = 'default' }) => (
  <div className={`rounded-2xl border p-6 ${
    variant === 'medical' 
      ? 'bg-red-50/50 border-red-100' 
      : 'bg-white border-gray-200'
  }`}>
    <div className="flex items-center gap-3 mb-6">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
        variant === 'medical' 
          ? 'bg-red-100 text-red-600' 
          : 'bg-primary-100 text-primary-600'
      }`}>
        {icon}
      </div>
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        {description && <p className="text-sm text-gray-500">{description}</p>}
      </div>
    </div>
    {children}
  </div>
);

// -------------------- Error Banner --------------------

const ErrorBanner: React.FC<{ errors: string[]; onDismiss: () => void }> = ({ errors, onDismiss }) => (
  <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
    <div className="flex items-start justify-between">
      <div className="flex items-start gap-3">
        <ExclamationTriangleIcon className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
        <div>
          <p className="text-sm font-medium text-red-800 mb-1">Please fix the following:</p>
          <ul className="list-disc list-inside text-sm text-red-600 space-y-0.5">
            {errors.map((err, i) => <li key={i}>{err}</li>)}
          </ul>
        </div>
      </div>
      <button onClick={onDismiss} className="p-1 text-red-400 hover:text-red-600">
        <XMarkIcon className="w-5 h-5" />
      </button>
    </div>
  </div>
);

// -------------------- Main Component --------------------

const AddChild: React.FC = () => {
  const { familyId } = useParams<{ familyId: string }>();
  const navigate = useNavigate();
  
  const [child, setChild] = useState<ChildFormData>(createEmptyChild());
  const [errors, setErrors] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Get family data
  const { data: family, loading: familyLoading } = useApiQuery<{ name: string }>(`/families/${familyId || ''}`, undefined, Boolean(familyId));

  const familyName = family?.name || 'Family';

  // Update field
  const updateField = (field: keyof ChildFormData, value: unknown) => {
    setChild(prev => ({ ...prev, [field]: value }));
    if (errors.length > 0) setErrors([]);
  };

  // Validate form
  const validate = (): string[] => {
    const errs: string[] = [];
    if (!child.firstName.trim()) errs.push('First name is required');
    if (!child.lastName.trim()) errs.push('Last name is required');
    if (!child.dateOfBirth) errs.push('Date of birth is required');
    if (!child.startDate) errs.push('Start date is required');
    return errs;
  };

  // Handle submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const validationErrors = validate();
    if (validationErrors.length > 0) {
      setErrors(validationErrors);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    const input = {
      first_name: child.firstName,
      last_name: child.lastName,
      date_of_birth: child.dateOfBirth,
      start_date: child.startDate,
      gender: child.gender || undefined,
      health_care_number: child.healthCareNumber || undefined,
      allergies: child.allergies || undefined,
      medical_conditions: child.medicalConditions || undefined,
      medications: child.medications || undefined,
      immunization_up_to_date: child.immunizationUpToDate,
      doctor_name: child.doctorName || undefined,
      doctor_phone: child.doctorPhone || undefined,
    };

    try {
      setIsSubmitting(true);
      await api.resources.create('children', { family_id: familyId, ...input });
      navigate(`/families/${familyId}`);
    } catch (error) {
      setErrors([error instanceof Error ? error.message : 'Failed to add child. Please try again.']);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => navigate(`/families/${familyId}`);

  if (familyLoading) {
    return (
      <div className="max-w-3xl mx-auto py-8 px-4">
        <DetailSkeleton />
      </div>
    );
  }

  const ageGroup = calculateAgeGroup(child.dateOfBirth);
  const age = calculateAge(child.dateOfBirth);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          to={`/families/${familyId}`}
          className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5" />
        </Link>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
            <UserPlusIcon className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900">Add New Child</h1>
            <p className="text-sm text-gray-500">Adding to {familyName}</p>
          </div>
        </div>
      </div>
        {/* Error Banner */}
        {errors.length > 0 && (
          <ErrorBanner errors={errors} onDismiss={() => setErrors([])} />
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Information */}
          <SectionCard
            icon={<UserIcon className="w-5 h-5" />}
            title="Basic Information"
            description="Required details about the child"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                label="First Name"
                value={child.firstName}
                onChange={(v) => updateField('firstName', v)}
                placeholder="Enter first name"
                required
              />
              <Input
                label="Last Name"
                value={child.lastName}
                onChange={(v) => updateField('lastName', v)}
                placeholder="Enter last name"
                required
              />
              <div>
                <Input
                  label="Date of Birth"
                  value={child.dateOfBirth}
                  onChange={(v) => updateField('dateOfBirth', v)}
                  type="date"
                  required
                />
                {child.dateOfBirth && ageGroup && (
                  <div className="mt-2 flex items-center gap-2">
                    <AgeGroupBadge ageGroup={ageGroup} />
                    <span className="text-sm text-gray-500">{age}</span>
                  </div>
                )}
              </div>
              <Input
                label="Start Date"
                value={child.startDate}
                onChange={(v) => updateField('startDate', v)}
                type="date"
                required
              />
              <Select
                label="Gender"
                value={child.gender}
                onChange={(v) => updateField('gender', v)}
                options={GENDER_OPTIONS}
              />
            </div>
          </SectionCard>

          {/* Medical Information */}
          <SectionCard
            icon={<HeartIcon className="w-5 h-5" />}
            title="Medical Information"
            description="Health and emergency medical details"
            variant="medical"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <Input
                label="Health Care Number"
                value={child.healthCareNumber}
                onChange={(v) => updateField('healthCareNumber', v)}
                placeholder="e.g., 123-456-789"
              />
              <Input
                label="Family Doctor"
                value={child.doctorName}
                onChange={(v) => updateField('doctorName', v)}
                placeholder="Doctor's name"
              />
              <Input
                label="Doctor Phone"
                value={child.doctorPhone}
                onChange={(v) => updateField('doctorPhone', v)}
                placeholder="(xxx) xxx-xxxx"
              />
              <RadioGroup
                label="Immunizations Up to Date?"
                value={child.immunizationUpToDate}
                onChange={(v) => updateField('immunizationUpToDate', v)}
              />
            </div>

            <div className="space-y-4">
              <TextArea
                label="Allergies"
                value={child.allergies}
                onChange={(v) => updateField('allergies', v)}
                placeholder='List any allergies (food, medication, environmental) or write "None"'
              />
              <TextArea
                label="Medical Conditions"
                value={child.medicalConditions}
                onChange={(v) => updateField('medicalConditions', v)}
                placeholder='List any medical conditions (asthma, diabetes, etc.) or write "None"'
              />
              <TextArea
                label="Current Medications"
                value={child.medications}
                onChange={(v) => updateField('medications', v)}
                placeholder='List any medications the child takes regularly or write "None"'
              />
            </div>
          </SectionCard>

          {/* Action Buttons */}
          <div className="flex items-center justify-between pt-4">
            <button
              type="button"
              onClick={handleCancel}
              disabled={isSubmitting}
              className="btn btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn btn-primary px-6"
            >
              {isSubmitting ? (
                <>
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Adding Child...
                </>
              ) : (
                <>
                  <CheckIcon className="w-4 h-4" />
                  Add Child
                </>
              )}
            </button>
          </div>
        </form>
    </div>
  );
};

export default AddChild;
