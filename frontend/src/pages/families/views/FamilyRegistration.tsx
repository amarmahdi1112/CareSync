// ============================================
// Family Registration View - Completely Redesigned
// ============================================

import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  UserIcon,
  UsersIcon,
  PhoneIcon,
  ShieldCheckIcon,
  DocumentCheckIcon,
  XMarkIcon,
  ClockIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { UserGroupIcon } from '@heroicons/react/24/solid';

import { api } from '../../../api/client';

// Stores
import { useNotificationStore } from '../../../stores';

// Hooks
import { useRegistrationStorage } from '../hooks';

// Registration module
import {
  type Guardian,
  type Child,
  type EmergencyContact,
  type Consents,
  createEmptyGuardian,
  createEmptyChild,
  createEmptyEmergencyContact,
  validateGuardian1,
  validateChildren,
  validateEmergencyContacts,
  validateConsents,
  Guardian1Step,
  Guardian2Step,
  ChildrenStep,
  EmergencyContactsStep,
  ConsentsStep,
  ReviewStep,
} from '../registration';

// -------------------- Steps Configuration --------------------

interface StepConfig {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
}

const STEPS: StepConfig[] = [
  { id: 'guardian1', title: 'Primary Guardian', description: 'Main contact person', icon: UserIcon },
  { id: 'guardian2', title: 'Secondary Guardian', description: 'Optional second guardian', icon: UsersIcon },
  { id: 'children', title: 'Children', description: 'Add enrolled children', icon: UserGroupIcon },
  { id: 'emergency', title: 'Emergency Contacts', description: 'Emergency contact info', icon: PhoneIcon },
  { id: 'consents', title: 'Consents', description: 'Required permissions', icon: ShieldCheckIcon },
  { id: 'review', title: 'Review & Submit', description: 'Confirm details', icon: DocumentCheckIcon },
];

// -------------------- Modern Stepper Component --------------------

interface StepperProps {
  steps: StepConfig[];
  currentStep: number;
  onStepClick?: (step: number) => void;
}

const ModernStepper: React.FC<StepperProps> = ({ steps, currentStep, onStepClick }) => (
  <div className="hidden lg:block">
    <nav aria-label="Progress">
      <ol className="space-y-2">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const isClickable = index < currentStep && onStepClick;

          return (
            <li key={step.id}>
              <button
                onClick={() => isClickable && onStepClick(index)}
                disabled={!isClickable}
                className={`w-full flex items-center gap-4 p-3 rounded-xl transition-all ${isCurrent
                    ? 'bg-primary-50 border-2 border-primary-500'
                    : isCompleted
                      ? 'bg-green-50 border border-green-200 hover:bg-green-100 cursor-pointer'
                      : 'bg-gray-50 border border-gray-200'
                  }`}
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${isCurrent
                    ? 'bg-primary-500 text-white'
                    : isCompleted
                      ? 'bg-green-500 text-white'
                      : 'bg-gray-200 text-gray-500'
                  }`}>
                  {isCompleted ? (
                    <CheckIcon className="w-5 h-5" />
                  ) : (
                    <Icon className="w-5 h-5" />
                  )}
                </div>
                <div className="text-left">
                  <p className={`text-sm font-medium ${isCurrent ? 'text-primary-700' : isCompleted ? 'text-green-700' : 'text-gray-500'
                    }`}>
                    {step.title}
                  </p>
                  <p className="text-xs text-gray-500">{step.description}</p>
                </div>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  </div>
);

// Mobile Progress Bar
const MobileProgress: React.FC<{ current: number; total: number; title: string }> = ({ current, total, title }) => (
  <div className="lg:hidden mb-6">
    <div className="flex items-center justify-between mb-2">
      <span className="text-sm font-medium text-gray-700">{title}</span>
      <span className="text-sm text-gray-500">Step {current + 1} of {total}</span>
    </div>
    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
      <div
        className="h-full bg-gradient-to-r from-primary-500 to-primary-600 rounded-full transition-all duration-500"
        style={{ width: `${((current + 1) / total) * 100}%` }}
      />
    </div>
  </div>
);

// Error Banner
const ErrorBanner: React.FC<{ errors: string[]; onDismiss: () => void }> = ({ errors, onDismiss }) => (
  <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 animate-shake">
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <h4 className="text-sm font-medium text-red-800 mb-1">Please fix the following errors:</h4>
        <ul className="list-disc list-inside text-sm text-red-600 space-y-1">
          {errors.map((err, i) => <li key={i}>{err}</li>)}
        </ul>
      </div>
      <button onClick={onDismiss} className="p-1 text-red-400 hover:text-red-600">
        <XMarkIcon className="w-5 h-5" />
      </button>
    </div>
  </div>
);

// -------------------- Draft Banner Component --------------------

interface DraftBannerProps {
  lastSaved: Date | null;
  onClear: () => void;
}

const DraftBanner: React.FC<DraftBannerProps> = ({ lastSaved, onClear }) => {
  if (!lastSaved) return null;

  const timeAgo = () => {
    const now = new Date();
    const diff = now.getTime() - lastSaved.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    return 'just now';
  };

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ClockIcon className="w-4 h-4 text-amber-600" />
          <span className="text-sm text-amber-800">
            Draft saved {timeAgo()}
          </span>
        </div>
        <button
          onClick={onClear}
          className="flex items-center gap-1 text-sm text-amber-700 hover:text-amber-900 font-medium"
        >
          <TrashIcon className="w-4 h-4" />
          Clear Draft
        </button>
      </div>
    </div>
  );
};

// -------------------- Main Component --------------------

const FamilyRegistration: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get('returnTo') || '/families';

  const { success, error: showError } = useNotificationStore();

  // Use persisted storage hook
  const {
    data,
    currentStep,
    setData,
    setCurrentStep,
    clearStorage,
    hasSavedDraft,
    lastSaved,
  } = useRegistrationStorage();

  const [errors, setErrors] = useState<string[]>([]);
  const [skipSecondGuardian, setSkipSecondGuardian] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Validation
  const validateStep = (): boolean => {
    let errs: string[] = [];

    switch (currentStep) {
      case 0: errs = validateGuardian1(data.primaryGuardian); break;
      case 1: break; // Guardian 2 is optional
      case 2: errs = validateChildren(data.children); break;
      case 3: errs = validateEmergencyContacts(data.emergencyContacts); break;
      case 4: errs = validateConsents(data.consents); break;
    }

    setErrors(errs);
    return errs.length === 0;
  };

  // Navigation
  const handleNext = () => {
    if (!validateStep()) return;
    setCurrentStep(Math.min(currentStep + 1, STEPS.length - 1));
    setErrors([]);
  };

  const handleBack = () => {
    setCurrentStep(Math.max(currentStep - 1, 0));
    setErrors([]);
  };

  const handleStepClick = (step: number) => {
    if (step < currentStep) {
      setCurrentStep(step);
      setErrors([]);
    }
  };

  const handleClearDraft = () => {
    if (window.confirm('Are you sure you want to clear this draft? All progress will be lost.')) {
      clearStorage();
    }
  };

  // Submit
  const handleSubmit = async () => {
    const mapGuardian = (g: Guardian, type: 'primary' | 'secondary') => ({
      first_name: g.firstName,
      last_name: g.lastName,
      relationship: g.relationship,
      guardian_type: type,
      email: g.email,
      cell_phone: g.cellPhone,
      home_phone: g.homePhone || undefined,
      work_phone: g.workPhone || undefined,
      address: g.address || undefined,
      city: g.city || undefined,
      postal_code: g.postalCode || undefined,
    });

    const mapChild = (c: Child) => ({
      first_name: c.firstName,
      middle_name: c.middleName || undefined,
      last_name: c.lastName,
      date_of_birth: c.dateOfBirth,
      start_date: c.startDate,
      gender: c.gender || undefined,
      health_care_number: c.healthCareNumber || undefined,
      allergies: c.allergies || undefined,
      medical_conditions: c.medicalConditions || undefined,
      medications: c.medications || undefined,
      immunization_up_to_date: c.immunizationUpToDate,
      doctor_name: c.doctorName || undefined,
      doctor_phone: c.doctorPhone || undefined,
    });

    const mapEmergencyContact = (e: EmergencyContact) => ({
      first_name: e.firstName,
      last_name: e.lastName,
      relationship: e.relationship,
      cell_phone: e.cellPhone,
      home_phone: e.homePhone || undefined,
      authorized_pickup: e.authorizedPickup,
    });

    const input: Record<string, unknown> = {
      primary_guardian: mapGuardian(data.primaryGuardian, 'primary'),
      children: data.children.map(mapChild),
      emergency_contacts: data.emergencyContacts.map(mapEmergencyContact),
      consents: {
        photo_consent: data.consents.photoConsent,
        field_trip_consent: data.consents.fieldTripConsent,
        emergency_medical_consent: data.consents.emergencyMedicalConsent,
      },
    };

    if (data.secondaryGuardian) {
      input.secondary_guardian = mapGuardian(data.secondaryGuardian, 'secondary');
    }

    try {
      setIsSubmitting(true);
      await api.post('/families', input);
      success('Family Registered', 'The family has been successfully registered.');
      clearStorage();
      navigate(returnTo);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Registration failed. Please try again.';
      showError('Registration Failed', message);
      setErrors([message]);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Data handlers
  const updatePrimaryGuardian = (field: keyof Guardian, value: string) => {
    setData(prev => ({
      ...prev,
      primaryGuardian: { ...prev.primaryGuardian, [field]: value },
    }));
  };

  const updateSecondaryGuardian = (field: keyof Guardian, value: string) => {
    setData(prev => ({
      ...prev,
      secondaryGuardian: { ...(prev.secondaryGuardian || createEmptyGuardian()), [field]: value },
    }));
  };

  const handleSkipSecondGuardian = () => {
    setSkipSecondGuardian(true);
    setData(prev => ({ ...prev, secondaryGuardian: null }));
  };

  const handleAddSecondGuardian = () => {
    setSkipSecondGuardian(false);
    setData(prev => ({ ...prev, secondaryGuardian: createEmptyGuardian() }));
  };

  const addChild = () => {
    setData(prev => ({
      ...prev,
      children: [...prev.children, createEmptyChild(prev.primaryGuardian.lastName)],
    }));
  };

  const removeChild = (id: string) => {
    setData(prev => ({
      ...prev,
      children: prev.children.filter(c => c.id !== id),
    }));
  };

  const updateChild = (id: string, field: keyof Child, value: unknown) => {
    setData(prev => ({
      ...prev,
      children: prev.children.map(c => c.id === id ? { ...c, [field]: value } : c),
    }));
  };

  const addEmergencyContact = () => {
    setData(prev => ({
      ...prev,
      emergencyContacts: [...prev.emergencyContacts, createEmptyEmergencyContact()],
    }));
  };

  const removeEmergencyContact = (id: string) => {
    setData(prev => ({
      ...prev,
      emergencyContacts: prev.emergencyContacts.filter(e => e.id !== id),
    }));
  };

  const updateEmergencyContact = (id: string, field: keyof EmergencyContact, value: unknown) => {
    setData(prev => ({
      ...prev,
      emergencyContacts: prev.emergencyContacts.map(e => e.id === id ? { ...e, [field]: value } : e),
    }));
  };

  const updateConsent = (field: keyof Consents, value: boolean) => {
    setData(prev => ({ ...prev, consents: { ...prev.consents, [field]: value } }));
  };

  const updateNotes = (value: string) => {
    setData(prev => ({ ...prev, additionalNotes: value }));
  };

  // Render current step content
  const renderStep = () => {
    switch (currentStep) {
      case 0:
        return <Guardian1Step guardian={data.primaryGuardian} onUpdate={updatePrimaryGuardian} />;
      case 1:
        return (
          <Guardian2Step
            guardian={data.secondaryGuardian}
            skipSecondGuardian={skipSecondGuardian}
            onUpdate={updateSecondaryGuardian}
            onSkip={handleSkipSecondGuardian}
            onAddGuardian={handleAddSecondGuardian}
          />
        );
      case 2:
        return (
          <ChildrenStep
            children={data.children}
            onUpdateChild={updateChild}
            onAddChild={addChild}
            onRemoveChild={removeChild}
          />
        );
      case 3:
        return (
          <EmergencyContactsStep
            contacts={data.emergencyContacts}
            onUpdateContact={updateEmergencyContact}
            onAddContact={addEmergencyContact}
            onRemoveContact={removeEmergencyContact}
          />
        );
      case 4:
        return (
          <ConsentsStep
            consents={data.consents}
            additionalNotes={data.additionalNotes}
            onUpdateConsent={updateConsent}
            onUpdateNotes={updateNotes}
          />
        );
      case 5:
        return <ReviewStep data={data} />;
      default:
        return null;
    }
  };

  const isLastStep = currentStep === STEPS.length - 1;
  const currentStepConfig = STEPS[currentStep];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(returnTo)}
            className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeftIcon className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
              <UserGroupIcon className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">New Family Registration</h1>
              <p className="text-sm text-gray-500">Complete all steps to register a new family</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto">
        <div className="flex gap-8">
          {/* Sidebar Stepper (Desktop) */}
          <div className="hidden lg:block w-72 flex-shrink-0">
            <div className="sticky top-8">
              <ModernStepper
                steps={STEPS}
                currentStep={currentStep}
                onStepClick={handleStepClick}
              />
            </div>
          </div>

          {/* Form Content */}
          <div className="flex-1 max-w-2xl">
            {/* Mobile Progress */}
            <MobileProgress
              current={currentStep}
              total={STEPS.length}
              title={currentStepConfig.title}
            />

            {/* Draft Banner */}
            {hasSavedDraft && lastSaved && (
              <DraftBanner lastSaved={lastSaved} onClear={handleClearDraft} />
            )}

            {/* Step Header */}
            <div className="mb-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-xl bg-primary-100 flex items-center justify-center">
                  <currentStepConfig.icon className="w-5 h-5 text-primary-600" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900">{currentStepConfig.title}</h2>
                  <p className="text-sm text-gray-500">{currentStepConfig.description}</p>
                </div>
              </div>
            </div>

            {/* Error Banner */}
            {errors.length > 0 && (
              <ErrorBanner errors={errors} onDismiss={() => setErrors([])} />
            )}

            {/* Step Content Card */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 md:p-8 mb-6">
              {renderStep()}
            </div>

            {/* Navigation Buttons */}
            <div className="flex items-center justify-between">
              <button
                onClick={handleBack}
                disabled={currentStep === 0}
                className={`btn btn-secondary ${currentStep === 0 ? 'opacity-40 cursor-not-allowed' : ''}`}
              >
                <ArrowLeftIcon className="w-4 h-4" />
                Back
              </button>

              {isLastStep ? (
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  className="btn btn-primary px-8"
                >
                  {isSubmitting ? (
                    <>
                      <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Submitting...
                    </>
                  ) : (
                    <>
                      <CheckIcon className="w-4 h-4" />
                      Complete Registration
                    </>
                  )}
                </button>
              ) : (
                <button onClick={handleNext} className="btn btn-primary px-8">
                  Continue
                  <ArrowRightIcon className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FamilyRegistration;
