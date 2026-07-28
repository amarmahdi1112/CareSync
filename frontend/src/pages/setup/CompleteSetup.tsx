// ============================================
// Complete Setup Page
// Shows ONLY the missing required fields - nothing else
// ============================================

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BuildingOffice2Icon,
  MapPinIcon,
  ClockIcon,
  PhoneIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import type { Organization } from '../../types';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

// What fields are we checking
interface MissingFields {
  // Organization Identity
  name: boolean;
  license_number: boolean;
  licensed_capacity: boolean;
  // Location
  street_address: boolean;
  city: boolean;
  province: boolean;
  postal_code: boolean;
  // Contact
  phone: boolean;
  // Operations
  opening_time: boolean;
  closing_time: boolean;
  age_groups_served: boolean;
}

interface FormData {
  name: string;
  license_number: string;
  licensed_capacity: number;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  phone: string;
  opening_time: string;
  closing_time: string;
  age_groups_served: string[];
}

const PROVINCES = [
  'Alberta', 'British Columbia', 'Manitoba', 'New Brunswick',
  'Newfoundland and Labrador', 'Nova Scotia', 'Ontario',
  'Prince Edward Island', 'Quebec', 'Saskatchewan',
];

const AGE_GROUPS = [
  { value: 'infant', label: 'Infant (0-18 months)' },
  { value: 'toddler', label: 'Toddler (19 months - 2.5 years)' },
  { value: 'preschool', label: 'Preschool (2.5 - 4 years)' },
  { value: 'kindergarten', label: 'Kindergarten (4-5 years)' },
  { value: 'school_age', label: 'School Age (6-12 years)' },
];

// Check what's missing from organization
const getMissingFields = (org: Organization | null): MissingFields => {
  return {
    name: !org?.name || org.name === 'My Organization',
    license_number: !org?.license_number || org.license_number === 'PENDING',
    licensed_capacity: !org?.licensed_capacity,
    street_address: !org?.street_address,
    city: !org?.city,
    province: !org?.province,
    postal_code: !org?.postal_code,
    phone: !org?.phone,
    opening_time: !org?.opening_time,
    closing_time: !org?.closing_time,
    age_groups_served: !org?.age_groups_served?.length,
  };
};

// Count how many fields are missing
const countMissing = (missing: MissingFields): number => {
  return Object.values(missing).filter(Boolean).length;
};

// Group missing fields by category
const getMissingCategories = (missing: MissingFields) => {
  const categories: { key: string; label: string; icon: React.ElementType; fields: string[] }[] = [];
  
  const identityFields = [];
  if (missing.name) identityFields.push('name');
  if (missing.license_number) identityFields.push('license_number');
  if (missing.licensed_capacity) identityFields.push('licensed_capacity');
  if (identityFields.length > 0) {
    categories.push({ key: 'identity', label: 'Organization Info', icon: BuildingOffice2Icon, fields: identityFields });
  }
  
  const locationFields = [];
  if (missing.street_address) locationFields.push('street_address');
  if (missing.city) locationFields.push('city');
  if (missing.province) locationFields.push('province');
  if (missing.postal_code) locationFields.push('postal_code');
  if (locationFields.length > 0) {
    categories.push({ key: 'location', label: 'Location', icon: MapPinIcon, fields: locationFields });
  }
  
  if (missing.phone) {
    categories.push({ key: 'contact', label: 'Contact', icon: PhoneIcon, fields: ['phone'] });
  }
  
  const operationsFields = [];
  if (missing.opening_time) operationsFields.push('opening_time');
  if (missing.closing_time) operationsFields.push('closing_time');
  if (missing.age_groups_served) operationsFields.push('age_groups_served');
  if (operationsFields.length > 0) {
    categories.push({ key: 'operations', label: 'Operations', icon: ClockIcon, fields: operationsFields });
  }
  
  return categories;
};

const CompleteSetup: React.FC = () => {
  const navigate = useNavigate();
  const { state: authState, setOrganization } = useAuth();
  const org = authState.organization;
  
  const [missing, setMissing] = useState<MissingFields>(() => getMissingFields(org));
  const [formData, setFormData] = useState<FormData>({
    name: org?.name === 'My Organization' ? '' : (org?.name || ''),
    license_number: org?.license_number === 'PENDING' ? '' : (org?.license_number || ''),
    licensed_capacity: org?.licensed_capacity || 0,
    street_address: org?.street_address || '',
    city: org?.city || '',
    province: org?.province || '',
    postal_code: org?.postal_code || '',
    phone: org?.phone || '',
    opening_time: org?.opening_time || '07:00',
    closing_time: org?.closing_time || '18:00',
    age_groups_served: org?.age_groups_served || [],
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Recalculate missing when org changes
  useEffect(() => {
    setMissing(getMissingFields(org));
  }, [org]);

  const updateField = (field: keyof FormData, value: FormData[keyof FormData]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const toggleAgeGroup = (value: string) => {
    setFormData(prev => ({
      ...prev,
      age_groups_served: prev.age_groups_served.includes(value)
        ? prev.age_groups_served.filter(v => v !== value)
        : [...prev.age_groups_served, value],
    }));
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    if (missing.name && !formData.name.trim()) {
      newErrors.name = 'Organization name is required';
    }
    if (missing.license_number && !formData.license_number.trim()) {
      newErrors.license_number = 'License number is required';
    }
    if (missing.licensed_capacity && !formData.licensed_capacity) {
      newErrors.licensed_capacity = 'Licensed capacity is required';
    }
    if (missing.street_address && !formData.street_address.trim()) {
      newErrors.street_address = 'Street address is required';
    }
    if (missing.city && !formData.city.trim()) {
      newErrors.city = 'City is required';
    }
    if (missing.province && !formData.province) {
      newErrors.province = 'Province is required';
    }
    if (missing.postal_code && !formData.postal_code.trim()) {
      newErrors.postal_code = 'Postal code is required';
    }
    if (missing.phone && !formData.phone.trim()) {
      newErrors.phone = 'Phone number is required';
    }
    if (missing.age_groups_served && formData.age_groups_served.length === 0) {
      newErrors.age_groups_served = 'Select at least one age group';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validate()) return;
    if (!org?.id) {
      setSaveError('Organization not found. Please try logging in again.');
      return;
    }

    setSaveError(null);

    // Build input with only the fields that were missing
    const input: Record<string, unknown> = {};
    if (missing.name) input.name = formData.name;
    if (missing.license_number) input.license_number = formData.license_number;
    if (missing.licensed_capacity) input.licensed_capacity = formData.licensed_capacity;
    if (missing.street_address) input.street_address = formData.street_address;
    if (missing.city) input.city = formData.city;
    if (missing.province) input.province = formData.province;
    if (missing.postal_code) input.postal_code = formData.postal_code;
    if (missing.phone) input.phone = formData.phone;
    if (missing.opening_time) input.opening_time = formData.opening_time;
    if (missing.closing_time) input.closing_time = formData.closing_time;
    if (missing.age_groups_served) input.age_groups_served = formData.age_groups_served;

    try {
      setLoading(true);
      const updated = await api.patch<Organization>('/organization', input);
      setOrganization(updated);
      const newMissing = getMissingFields(updated);
      if (countMissing(newMissing) === 0) navigate('/dashboard');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const missingCount = countMissing(missing);
  const categories = getMissingCategories(missing);

  // If nothing is missing, redirect to dashboard
  if (missingCount === 0) {
    navigate('/dashboard');
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-primary-50/30">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-2xl mx-auto px-6 py-4 flex items-center justify-center">
          <img src={logoSvg} alt="CareSync" className="h-8" />
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-2xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 shadow-xl shadow-amber-500/30 mb-4">
            <ExclamationCircleIcon className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Complete Your Setup</h1>
          <p className="text-gray-600">
            {missingCount === 1 
              ? "Just one more thing needed to get started"
              : `${missingCount} fields needed to get started`
            }
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-xl shadow-gray-200/50 p-8">
          <div className="space-y-8">
            {categories.map((category) => (
              <div key={category.key}>
                {/* Category Header */}
                <div className="flex items-center gap-3 mb-4 pb-2 border-b border-gray-100">
                  <category.icon className="w-5 h-5 text-primary-600" />
                  <h2 className="font-semibold text-gray-900">{category.label}</h2>
                </div>

                {/* Fields */}
                <div className="space-y-4">
                  {/* Organization Name */}
                  {category.fields.includes('name') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Organization Name *
                      </label>
                      <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => updateField('name', e.target.value)}
                        placeholder="Sunny Days Childcare"
                        className={`input w-full ${errors.name ? 'border-red-500' : ''}`}
                      />
                      {errors.name && <p className="text-red-500 text-sm mt-1">{errors.name}</p>}
                    </div>
                  )}

                  {/* License Number */}
                  {category.fields.includes('license_number') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        License Number *
                      </label>
                      <input
                        type="text"
                        value={formData.license_number}
                        onChange={(e) => updateField('license_number', e.target.value)}
                        placeholder="DCC-12345"
                        className={`input w-full ${errors.license_number ? 'border-red-500' : ''}`}
                      />
                      {errors.license_number && <p className="text-red-500 text-sm mt-1">{errors.license_number}</p>}
                    </div>
                  )}

                  {/* Licensed Capacity */}
                  {category.fields.includes('licensed_capacity') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Licensed Capacity *
                      </label>
                      <input
                        type="number"
                        value={formData.licensed_capacity || ''}
                        onChange={(e) => updateField('licensed_capacity', parseInt(e.target.value) || 0)}
                        placeholder="50"
                        min="1"
                        className={`input w-full ${errors.licensed_capacity ? 'border-red-500' : ''}`}
                      />
                      {errors.licensed_capacity && <p className="text-red-500 text-sm mt-1">{errors.licensed_capacity}</p>}
                    </div>
                  )}

                  {/* Street Address */}
                  {category.fields.includes('street_address') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Street Address *
                      </label>
                      <input
                        type="text"
                        value={formData.street_address}
                        onChange={(e) => updateField('street_address', e.target.value)}
                        placeholder="123 Main Street"
                        className={`input w-full ${errors.street_address ? 'border-red-500' : ''}`}
                      />
                      {errors.street_address && <p className="text-red-500 text-sm mt-1">{errors.street_address}</p>}
                    </div>
                  )}

                  {/* City */}
                  {category.fields.includes('city') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        City *
                      </label>
                      <input
                        type="text"
                        value={formData.city}
                        onChange={(e) => updateField('city', e.target.value)}
                        placeholder="Calgary"
                        className={`input w-full ${errors.city ? 'border-red-500' : ''}`}
                      />
                      {errors.city && <p className="text-red-500 text-sm mt-1">{errors.city}</p>}
                    </div>
                  )}

                  {/* Province */}
                  {category.fields.includes('province') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Province *
                      </label>
                      <select
                        value={formData.province}
                        onChange={(e) => updateField('province', e.target.value)}
                        className={`input w-full ${errors.province ? 'border-red-500' : ''}`}
                      >
                        <option value="">Select province</option>
                        {PROVINCES.map(p => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                      {errors.province && <p className="text-red-500 text-sm mt-1">{errors.province}</p>}
                    </div>
                  )}

                  {/* Postal Code */}
                  {category.fields.includes('postal_code') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Postal Code *
                      </label>
                      <input
                        type="text"
                        value={formData.postal_code}
                        onChange={(e) => updateField('postal_code', e.target.value.toUpperCase())}
                        placeholder="T2P 1J9"
                        maxLength={7}
                        className={`input w-full ${errors.postal_code ? 'border-red-500' : ''}`}
                      />
                      {errors.postal_code && <p className="text-red-500 text-sm mt-1">{errors.postal_code}</p>}
                    </div>
                  )}

                  {/* Phone */}
                  {category.fields.includes('phone') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Phone Number *
                      </label>
                      <input
                        type="tel"
                        value={formData.phone}
                        onChange={(e) => updateField('phone', e.target.value)}
                        placeholder="(403) 555-0123"
                        className={`input w-full ${errors.phone ? 'border-red-500' : ''}`}
                      />
                      {errors.phone && <p className="text-red-500 text-sm mt-1">{errors.phone}</p>}
                    </div>
                  )}

                  {/* Operating Hours */}
                  {(category.fields.includes('opening_time') || category.fields.includes('closing_time')) && (
                    <div className="grid grid-cols-2 gap-4">
                      {category.fields.includes('opening_time') && (
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Opening Time *
                          </label>
                          <input
                            type="time"
                            value={formData.opening_time}
                            onChange={(e) => updateField('opening_time', e.target.value)}
                            className="input w-full"
                          />
                        </div>
                      )}
                      {category.fields.includes('closing_time') && (
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Closing Time *
                          </label>
                          <input
                            type="time"
                            value={formData.closing_time}
                            onChange={(e) => updateField('closing_time', e.target.value)}
                            className="input w-full"
                          />
                        </div>
                      )}
                    </div>
                  )}

                  {/* Age Groups */}
                  {category.fields.includes('age_groups_served') && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Age Groups Served *
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {AGE_GROUPS.map((group) => (
                          <button
                            key={group.value}
                            type="button"
                            onClick={() => toggleAgeGroup(group.value)}
                            className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                              formData.age_groups_served.includes(group.value)
                                ? 'bg-primary-500 text-white'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            }`}
                          >
                            {group.label}
                          </button>
                        ))}
                      </div>
                      {errors.age_groups_served && (
                        <p className="text-red-500 text-sm mt-1">{errors.age_groups_served}</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Error Message */}
          {saveError && (
            <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
              <ExclamationCircleIcon className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-600">{saveError}</p>
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className={`w-full mt-8 flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-primary-500 to-primary-600 text-white font-semibold rounded-xl transition-all shadow-lg shadow-primary-500/30 ${
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
                <CheckCircleIcon className="w-5 h-5" />
                Complete Setup
              </>
            )}
          </button>
        </form>
      </main>
    </div>
  );
};

export default CompleteSetup;
