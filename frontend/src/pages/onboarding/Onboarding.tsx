// ============================================
// Onboarding Wizard - Organization Setup
// Beautiful multi-step onboarding after registration
// ============================================

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BuildingOffice2Icon,
  MapPinIcon,
  ClockIcon,
  CheckCircleIcon,
  SparklesIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  CameraIcon,
  XMarkIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import type { Organization } from '../../types';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

// -------------------- Types --------------------

interface OrganizationData {
  // Step 1: Identity
  organization_type: 'daycare' | 'osc' | 'both';
  name: string;
  license_number: string;
  licensed_capacity: number;
  description: string;
  logo: string | null;
  
  // Step 2: Location
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  phone: string;
  
  // Step 3: Operations
  opening_time: string;
  closing_time: string;
  operating_days: string[];
  age_groups_served: string[];
  programs_offered: string[];
}

const initialData: OrganizationData = {
  organization_type: 'daycare',
  name: '',
  license_number: '',
  licensed_capacity: 0,
  description: '',
  logo: null,
  street_address: '',
  city: '',
  province: 'Alberta',
  postal_code: '',
  phone: '',
  opening_time: '07:00',
  closing_time: '18:00',
  operating_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
  age_groups_served: [],
  programs_offered: [],
};

// -------------------- Constants --------------------

const STEPS = [
  { id: 0, title: 'Organization', icon: BuildingOffice2Icon, description: 'Tell us about your center' },
  { id: 1, title: 'Location', icon: MapPinIcon, description: 'Where are you located?' },
  { id: 2, title: 'Operations', icon: ClockIcon, description: 'Hours and services' },
  { id: 3, title: 'Complete', icon: CheckCircleIcon, description: 'You\'re all set!' },
];

const PROVINCES = [
  'Alberta', 'British Columbia', 'Manitoba', 'New Brunswick',
  'Newfoundland and Labrador', 'Northwest Territories', 'Nova Scotia',
  'Nunavut', 'Ontario', 'Prince Edward Island', 'Quebec', 'Saskatchewan', 'Yukon'
];

const DAYS_OF_WEEK = [
  { value: 'monday', label: 'Mon' },
  { value: 'tuesday', label: 'Tue' },
  { value: 'wednesday', label: 'Wed' },
  { value: 'thursday', label: 'Thu' },
  { value: 'friday', label: 'Fri' },
  { value: 'saturday', label: 'Sat' },
  { value: 'sunday', label: 'Sun' },
];

const AGE_GROUPS = [
  { value: 'infant', label: 'Infant', desc: '0-18 months', emoji: '👶' },
  { value: 'toddler', label: 'Toddler', desc: '18-36 months', emoji: '🧒' },
  { value: 'preschool', label: 'Preschool', desc: '3-5 years', emoji: '🎨' },
  { value: 'kindergarten', label: 'Kindergarten', desc: '5-6 years', emoji: '📚' },
  { value: 'school_age', label: 'School Age', desc: '6-12 years', emoji: '🎒' },
];

const PROGRAMS = [
  { value: 'full_day', label: 'Full Day', icon: '🌅' },
  { value: 'half_day_am', label: 'Morning', icon: '🌤️' },
  { value: 'half_day_pm', label: 'Afternoon', icon: '🌇' },
  { value: 'before_school', label: 'Before School', icon: '🌄' },
  { value: 'after_school', label: 'After School', icon: '🌆' },
  { value: 'drop_in', label: 'Drop-in', icon: '📍' },
];

const ORG_TYPES = [
  { value: 'daycare', title: 'Daycare', desc: 'Full-time care for ages 0-6', icon: '🏠' },
  { value: 'osc', title: 'Out of School Care', desc: 'Before & after school programs', icon: '🏫' },
  { value: 'both', title: 'Both', desc: 'Daycare and OSC services', icon: '✨' },
];

// -------------------- Helpers --------------------

const formatPhone = (value: string): string => {
  const digits = value.replace(/\D/g, '');
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
};

const formatPostalCode = (value: string): string => {
  const clean = value.replace(/\s/g, '').toUpperCase();
  if (clean.length <= 3) return clean;
  return `${clean.slice(0, 3)} ${clean.slice(3, 6)}`;
};

// -------------------- Progress Bar --------------------

const ProgressBar: React.FC<{ currentStep: number; totalSteps: number }> = ({ currentStep, totalSteps }) => (
  <div className="flex items-center gap-2">
    {Array.from({ length: totalSteps }).map((_, i) => (
      <div
        key={i}
        className={`h-2 rounded-full flex-1 transition-all duration-500 ${
          i < currentStep
            ? 'bg-primary-500'
            : i === currentStep
              ? 'bg-primary-300'
              : 'bg-gray-200'
        }`}
      />
    ))}
  </div>
);

// -------------------- Step Indicator --------------------

const StepIndicator: React.FC<{ steps: typeof STEPS; currentStep: number }> = ({ steps, currentStep }) => (
  <div className="hidden md:flex items-center justify-center gap-2 mb-8">
    {steps.slice(0, -1).map((step, i) => (
      <React.Fragment key={step.id}>
        <div className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
          i < currentStep
            ? 'bg-primary-100 text-primary-700'
            : i === currentStep
              ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30'
              : 'bg-gray-100 text-gray-400'
        }`}>
          {i < currentStep ? (
            <CheckCircleIcon className="w-5 h-5" />
          ) : (
            <step.icon className="w-5 h-5" />
          )}
          <span className="font-medium text-sm">{step.title}</span>
        </div>
        {i < steps.length - 2 && (
          <div className={`w-12 h-0.5 ${i < currentStep ? 'bg-primary-300' : 'bg-gray-200'}`} />
        )}
      </React.Fragment>
    ))}
  </div>
);

// -------------------- Main Component --------------------

const Onboarding: React.FC = () => {
  const navigate = useNavigate();
  const { state: authState, setOrganization } = useAuth();
  const [currentStep, setCurrentStep] = useState(0);
  const [data, setData] = useState<OrganizationData>(initialData);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isAnimating, setIsAnimating] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const updateField = <K extends keyof OrganizationData>(field: K, value: OrganizationData[K]) => {
    setData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const toggleArrayValue = (field: 'operating_days' | 'age_groups_served' | 'programs_offered', value: string) => {
    const current = data[field];
    const updated = current.includes(value)
      ? current.filter(v => v !== value)
      : [...current, value];
    updateField(field, updated);
  };

  const validateStep = (): boolean => {
    const newErrors: Record<string, string> = {};

    switch (currentStep) {
      case 0:
        if (!data.name.trim()) newErrors.name = 'Organization name is required';
        if (!data.license_number.trim()) newErrors.license_number = 'License number is required';
        if (!data.licensed_capacity || data.licensed_capacity < 1) {
          newErrors.licensed_capacity = 'Please enter a valid capacity';
        }
        break;
      case 1:
        if (!data.street_address.trim()) newErrors.street_address = 'Address is required';
        if (!data.city.trim()) newErrors.city = 'City is required';
        if (!data.postal_code.trim()) newErrors.postal_code = 'Postal code is required';
        if (!data.phone.trim()) newErrors.phone = 'Phone number is required';
        break;
      case 2:
        if (data.age_groups_served.length === 0) {
          newErrors.age_groups_served = 'Select at least one age group';
        }
        break;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (!validateStep()) return;
    
    setIsAnimating(true);
    setTimeout(() => {
      if (currentStep === 2) {
        handleComplete();
      } else {
        setCurrentStep(prev => prev + 1);
      }
      setIsAnimating(false);
    }, 300);
  };

  const handleBack = () => {
    setIsAnimating(true);
    setTimeout(() => {
      setCurrentStep(prev => prev - 1);
      setIsAnimating(false);
    }, 300);
  };

  const handleComplete = async () => {
    const orgId = authState.organization?.id;
    if (!orgId) {
      setSaveError('Organization not found. Please try logging in again.');
      return;
    }

    setSaveError(null);
    
    try {
      setLoading(true);
      const updated = await api.patch<Organization>('/organization', {
        name: data.name,
        organization_type: data.organization_type,
        license_number: data.license_number,
        licensed_capacity: data.licensed_capacity,
        description: data.description || undefined,
        street_address: data.street_address,
        city: data.city,
        province: data.province,
        postal_code: data.postal_code,
        phone: data.phone,
        opening_time: data.opening_time,
        closing_time: data.closing_time,
        age_groups_served: data.age_groups_served,
        programs_offered: data.programs_offered.length > 0 ? data.programs_offered : undefined,
      });
      setOrganization(updated);
      setCurrentStep(3);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save organization. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const goToDashboard = () => {
    navigate('/dashboard');
  };

  // ============================================
  // Step Renders
  // ============================================

  const renderStep0 = () => (
    <div className={`space-y-8 transition-all duration-300 ${isAnimating ? 'opacity-0 translate-x-4' : 'opacity-100'}`}>
      {/* Org Type Selection */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-4">
          What type of organization are you?
        </label>
        <div className="grid grid-cols-3 gap-4">
          {ORG_TYPES.map((type) => (
            <button
              key={type.value}
              type="button"
              onClick={() => updateField('organization_type', type.value as OrganizationData['organization_type'])}
              className={`relative p-6 rounded-2xl border-2 text-center transition-all hover:scale-[1.02] ${
                data.organization_type === type.value
                  ? 'border-primary-500 bg-primary-50 shadow-lg shadow-primary-500/20'
                  : 'border-gray-200 hover:border-gray-300 bg-white'
              }`}
            >
              {data.organization_type === type.value && (
                <div className="absolute top-3 right-3 w-6 h-6 bg-primary-500 rounded-full flex items-center justify-center">
                  <CheckCircleIcon className="w-4 h-4 text-white" />
                </div>
              )}
              <span className="text-3xl mb-3 block">{type.icon}</span>
              <h3 className="font-semibold text-gray-900">{type.title}</h3>
              <p className="text-xs text-gray-500 mt-1">{type.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Logo Upload */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-4">
          Organization Logo (Optional)
        </label>
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className={`w-24 h-24 rounded-2xl border-2 border-dashed flex items-center justify-center transition-all overflow-hidden ${
              data.logo ? 'border-primary-500 bg-primary-50' : 'border-gray-300 hover:border-gray-400'
            }`}>
              {data.logo ? (
                <img src={data.logo} alt="Logo" className="w-full h-full object-cover" />
              ) : (
                <CameraIcon className="w-8 h-8 text-gray-400" />
              )}
            </div>
            {data.logo && (
              <button
                type="button"
                onClick={() => updateField('logo', null)}
                className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 rounded-full flex items-center justify-center text-white shadow-lg hover:bg-red-600 z-10"
              >
                <XMarkIcon className="w-4 h-4" />
              </button>
            )}
          </div>
          <div>
            <input
              type="file"
              id="logo-upload"
              accept="image/png,image/jpeg,image/jpg,image/webp"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  if (file.size > 2 * 1024 * 1024) {
                    alert('File size must be less than 2MB');
                    return;
                  }
                  const reader = new FileReader();
                  reader.onload = () => {
                    updateField('logo', reader.result as string);
                  };
                  reader.readAsDataURL(file);
                }
                // Reset input so same file can be selected again
                e.target.value = '';
              }}
            />
            <label
              htmlFor="logo-upload"
              className="inline-block px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium text-gray-700 transition-colors cursor-pointer"
            >
              {data.logo ? 'Change Image' : 'Upload Image'}
            </label>
            <p className="text-xs text-gray-500 mt-2">PNG, JPG up to 2MB</p>
          </div>
        </div>
      </div>

      {/* Organization Name */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-2">
          Organization Name *
        </label>
        <input
          type="text"
          value={data.name}
          onChange={(e) => updateField('name', e.target.value)}
          placeholder="Sunny Days Childcare Center"
          className={`w-full px-4 py-4 bg-white border-2 rounded-xl text-lg transition-all focus:ring-4 focus:ring-primary-500/20 ${
            errors.name ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
          }`}
        />
        {errors.name && <p className="text-red-500 text-sm mt-1">{errors.name}</p>}
      </div>

      {/* License & Capacity */}
      <div className="grid grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            License Number *
          </label>
          <input
            type="text"
            value={data.license_number}
            onChange={(e) => updateField('license_number', e.target.value)}
            placeholder="AB-12345"
            className={`w-full px-4 py-4 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
              errors.license_number ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
            }`}
          />
          {errors.license_number && <p className="text-red-500 text-sm mt-1">{errors.license_number}</p>}
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Licensed Capacity *
          </label>
          <input
            type="number"
            min="1"
            value={data.licensed_capacity || ''}
            onChange={(e) => updateField('licensed_capacity', parseInt(e.target.value) || 0)}
            placeholder="50"
            className={`w-full px-4 py-4 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
              errors.licensed_capacity ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
            }`}
          />
          {errors.licensed_capacity && <p className="text-red-500 text-sm mt-1">{errors.licensed_capacity}</p>}
        </div>
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-2">
          Description (Optional)
        </label>
        <textarea
          rows={3}
          value={data.description}
          onChange={(e) => updateField('description', e.target.value)}
          placeholder="Tell families what makes your center special..."
          className="w-full px-4 py-4 bg-white border-2 border-gray-200 rounded-xl resize-none transition-all focus:border-primary-500 focus:ring-4 focus:ring-primary-500/20"
        />
      </div>
    </div>
  );

  const renderStep1 = () => (
    <div className={`space-y-6 transition-all duration-300 ${isAnimating ? 'opacity-0 translate-x-4' : 'opacity-100'}`}>
      {/* Address */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-2">
          Street Address *
        </label>
        <input
          type="text"
          value={data.street_address}
          onChange={(e) => updateField('street_address', e.target.value)}
          placeholder="123 Main Street"
          className={`w-full px-4 py-4 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
            errors.street_address ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
          }`}
        />
        {errors.street_address && <p className="text-red-500 text-sm mt-1">{errors.street_address}</p>}
      </div>

      {/* City & Province */}
      <div className="grid grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            City *
          </label>
          <input
            type="text"
            value={data.city}
            onChange={(e) => updateField('city', e.target.value)}
            placeholder="Edmonton"
            className={`w-full px-4 py-4 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
              errors.city ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
            }`}
          />
          {errors.city && <p className="text-red-500 text-sm mt-1">{errors.city}</p>}
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Province
          </label>
          <select
            value={data.province}
            onChange={(e) => updateField('province', e.target.value)}
            className="w-full px-4 py-4 bg-white border-2 border-gray-200 rounded-xl transition-all focus:border-primary-500 focus:ring-4 focus:ring-primary-500/20"
          >
            {PROVINCES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Postal & Phone */}
      <div className="grid grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Postal Code *
          </label>
          <input
            type="text"
            value={data.postal_code}
            onChange={(e) => updateField('postal_code', formatPostalCode(e.target.value))}
            maxLength={7}
            placeholder="T5K 2R6"
            className={`w-full px-4 py-4 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
              errors.postal_code ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
            }`}
          />
          {errors.postal_code && <p className="text-red-500 text-sm mt-1">{errors.postal_code}</p>}
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Phone Number *
          </label>
          <input
            type="tel"
            value={data.phone}
            onChange={(e) => updateField('phone', formatPhone(e.target.value))}
            maxLength={14}
            placeholder="(780) 555-0123"
            className={`w-full px-4 py-4 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
              errors.phone ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
            }`}
          />
          {errors.phone && <p className="text-red-500 text-sm mt-1">{errors.phone}</p>}
        </div>
      </div>

      {/* Map Preview Placeholder */}
      <div className="bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl h-48 flex items-center justify-center">
        <div className="text-center">
          <MapPinIcon className="w-12 h-12 text-gray-400 mx-auto mb-2" />
          <p className="text-sm text-gray-500">Map preview will appear here</p>
        </div>
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className={`space-y-8 transition-all duration-300 ${isAnimating ? 'opacity-0 translate-x-4' : 'opacity-100'}`}>
      {/* Operating Hours */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-4">
          Operating Hours
        </label>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Opens at</label>
            <input
              type="time"
              value={data.opening_time}
              onChange={(e) => updateField('opening_time', e.target.value)}
              className="w-full px-4 py-3 bg-white border-2 border-gray-200 rounded-xl focus:border-primary-500"
            />
          </div>
          <span className="text-gray-400 mt-5">to</span>
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Closes at</label>
            <input
              type="time"
              value={data.closing_time}
              onChange={(e) => updateField('closing_time', e.target.value)}
              className="w-full px-4 py-3 bg-white border-2 border-gray-200 rounded-xl focus:border-primary-500"
            />
          </div>
        </div>
      </div>

      {/* Operating Days */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-4">
          Operating Days
        </label>
        <div className="flex gap-2">
          {DAYS_OF_WEEK.map((day) => (
            <button
              key={day.value}
              type="button"
              onClick={() => toggleArrayValue('operating_days', day.value)}
              className={`flex-1 py-4 rounded-xl font-semibold transition-all ${
                data.operating_days.includes(day.value)
                  ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {day.label}
            </button>
          ))}
        </div>
      </div>

      {/* Age Groups */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-4">
          Age Groups Served *
        </label>
        <div className="grid grid-cols-5 gap-3">
          {AGE_GROUPS.map((group) => (
            <button
              key={group.value}
              type="button"
              onClick={() => toggleArrayValue('age_groups_served', group.value)}
              className={`relative p-4 rounded-xl border-2 text-center transition-all hover:scale-105 ${
                data.age_groups_served.includes(group.value)
                  ? 'border-primary-500 bg-primary-50 shadow-lg shadow-primary-500/20'
                  : 'border-gray-200 hover:border-gray-300 bg-white'
              }`}
            >
              {data.age_groups_served.includes(group.value) && (
                <div className="absolute -top-1 -right-1 w-5 h-5 bg-primary-500 rounded-full flex items-center justify-center">
                  <CheckCircleIcon className="w-3 h-3 text-white" />
                </div>
              )}
              <span className="text-2xl block mb-1">{group.emoji}</span>
              <p className="text-xs font-semibold text-gray-900">{group.label}</p>
              <p className="text-xs text-gray-500">{group.desc}</p>
            </button>
          ))}
        </div>
        {errors.age_groups_served && <p className="text-red-500 text-sm mt-2">{errors.age_groups_served}</p>}
      </div>

      {/* Programs */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-4">
          Programs Offered
        </label>
        <div className="grid grid-cols-3 gap-3">
          {PROGRAMS.map((program) => (
            <button
              key={program.value}
              type="button"
              onClick={() => toggleArrayValue('programs_offered', program.value)}
              className={`relative p-4 rounded-xl border-2 text-left transition-all ${
                data.programs_offered.includes(program.value)
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-gray-300 bg-white'
              }`}
            >
              {data.programs_offered.includes(program.value) && (
                <div className="absolute top-2 right-2 w-5 h-5 bg-primary-500 rounded-full flex items-center justify-center">
                  <CheckCircleIcon className="w-3 h-3 text-white" />
                </div>
              )}
              <span className="text-xl">{program.icon}</span>
              <p className="text-sm font-medium text-gray-900 mt-1">{program.label}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  const renderComplete = () => (
    <div className="text-center py-12">
      {/* Success Animation */}
      <div className="relative w-32 h-32 mx-auto mb-8">
        <div className="absolute inset-0 bg-green-100 rounded-full animate-ping opacity-50" />
        <div className="relative w-32 h-32 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center shadow-2xl shadow-green-500/40">
          <CheckCircleIcon className="w-16 h-16 text-white" />
        </div>
      </div>

      <h2 className="text-3xl font-bold text-gray-900 mb-3">You're All Set!</h2>
      <p className="text-lg text-gray-600 mb-8 max-w-md mx-auto">
        <span className="font-semibold text-primary-600">{data.name}</span> is ready to go. 
        Start managing your families, attendance, and more.
      </p>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-4 max-w-lg mx-auto mb-10">
        <div className="bg-primary-50 rounded-xl p-4">
          <p className="text-2xl font-bold text-primary-600">{data.licensed_capacity}</p>
          <p className="text-xs text-primary-600/70">Capacity</p>
        </div>
        <div className="bg-violet-50 rounded-xl p-4">
          <p className="text-2xl font-bold text-violet-600">{data.age_groups_served.length}</p>
          <p className="text-xs text-violet-600/70">Age Groups</p>
        </div>
        <div className="bg-amber-50 rounded-xl p-4">
          <p className="text-2xl font-bold text-amber-600">{data.programs_offered.length || '1'}</p>
          <p className="text-xs text-amber-600/70">Programs</p>
        </div>
      </div>

      <button
        onClick={goToDashboard}
        className="inline-flex items-center gap-3 px-10 py-4 bg-gradient-to-r from-primary-500 to-primary-600 text-white font-semibold rounded-xl hover:from-primary-600 hover:to-primary-700 transition-all shadow-xl shadow-primary-500/30 hover:shadow-2xl hover:shadow-primary-500/40"
      >
        <SparklesIcon className="w-5 h-5" />
        Go to Dashboard
        <ArrowRightIcon className="w-5 h-5" />
      </button>
    </div>
  );

  // ============================================
  // Main Render
  // ============================================

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-primary-50/30">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-center">
          <img src={logoSvg} alt="CareSync" className="h-8" />
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-6 py-12">
        {currentStep < 3 && (
          <>
            {/* Progress Bar */}
            <div className="mb-8">
              <ProgressBar currentStep={currentStep} totalSteps={3} />
              <p className="text-center text-sm text-gray-500 mt-2">
                Step {currentStep + 1} of 3
              </p>
            </div>

            {/* Step Indicator */}
            <StepIndicator steps={STEPS} currentStep={currentStep} />

            {/* Step Title */}
            <div className="text-center mb-10">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-violet-500 shadow-xl shadow-primary-500/30 mb-4">
                {React.createElement(STEPS[currentStep].icon, { className: 'w-8 h-8 text-white' })}
              </div>
              <h1 className="text-2xl font-bold text-gray-900 mb-2">{STEPS[currentStep].title}</h1>
              <p className="text-gray-600">{STEPS[currentStep].description}</p>
            </div>
          </>
        )}

        {/* Step Content */}
        <div className="bg-white rounded-3xl shadow-xl shadow-gray-200/50 p-8 mb-8">
          {currentStep === 0 && renderStep0()}
          {currentStep === 1 && renderStep1()}
          {currentStep === 2 && renderStep2()}
          {currentStep === 3 && renderComplete()}
        </div>

        {/* Error Message */}
        {saveError && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
            <ExclamationCircleIcon className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-800">Failed to save</p>
              <p className="text-sm text-red-600">{saveError}</p>
            </div>
          </div>
        )}

        {/* Navigation */}
        {currentStep < 3 && (
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={handleBack}
              disabled={currentStep === 0 || loading}
              className={`flex items-center gap-2 px-6 py-3 font-medium rounded-xl transition-all ${
                currentStep === 0 || loading
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              <ArrowLeftIcon className="w-5 h-5" />
              Back
            </button>
            <button
              type="button"
              onClick={handleNext}
              disabled={loading}
              className={`flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-primary-500 to-primary-600 text-white font-semibold rounded-xl transition-all shadow-lg shadow-primary-500/30 ${
                loading ? 'opacity-70 cursor-wait' : 'hover:from-primary-600 hover:to-primary-700 hover:shadow-xl'
              }`}
            >
              {loading ? (
                <>
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Saving...
                </>
              ) : (
                <>
                  {currentStep === 2 ? 'Complete Setup' : 'Continue'}
                  <ArrowRightIcon className="w-5 h-5" />
                </>
              )}
            </button>
          </div>
        )}
      </main>
    </div>
  );
};

export default Onboarding;
