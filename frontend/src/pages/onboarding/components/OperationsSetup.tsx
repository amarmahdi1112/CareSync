// ============================================
// Operations Setup - Step 4 (Unintegrated)
// Operating hours, days, age groups, programs
// ============================================

import React, { useState } from 'react';
import {
  ClockIcon,
  CalendarDaysIcon,
  UserGroupIcon,
  AcademicCapIcon,
  CheckIcon,
} from '@heroicons/react/24/outline';

// -------------------- Types --------------------

interface OperationsData {
  opening_time: string;
  closing_time: string;
  operating_days: string[];
  age_groups_served: string[];
  programs_offered: string[];
  holiday_closures: string[];
}

interface OperationsSetupProps {
  data: OperationsData;
  onChange: (data: OperationsData) => void;
  onNext: () => void;
  onBack: () => void;
}

// -------------------- Constants --------------------

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
  { value: 'infant', label: 'Infant', desc: '0-18 months', color: 'pink' },
  { value: 'toddler', label: 'Toddler', desc: '18-36 months', color: 'orange' },
  { value: 'preschool', label: 'Preschool', desc: '3-5 years', color: 'purple' },
  { value: 'kindergarten', label: 'Kindergarten', desc: '5-6 years', color: 'blue' },
  { value: 'school_age', label: 'School Age', desc: '6-12 years', color: 'green' },
];

const PROGRAMS = [
  { value: 'full_day', label: 'Full Day Care', icon: '🌅' },
  { value: 'half_day_am', label: 'Half Day (Morning)', icon: '🌤️' },
  { value: 'half_day_pm', label: 'Half Day (Afternoon)', icon: '🌇' },
  { value: 'before_school', label: 'Before School Care', icon: '🌄' },
  { value: 'after_school', label: 'After School Care', icon: '🌆' },
  { value: 'drop_in', label: 'Drop-in Care', icon: '📍' },
  { value: 'summer_camp', label: 'Summer Camp', icon: '☀️' },
];

// -------------------- Component --------------------

const OperationsSetup: React.FC<OperationsSetupProps> = ({
  data,
  onChange,
  onNext,
  onBack,
}) => {
  const [errors, setErrors] = useState<Record<string, string>>({});

  const updateField = <K extends keyof OperationsData>(field: K, value: OperationsData[K]) => {
    onChange({ ...data, [field]: value });
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const toggleArrayValue = (field: 'operating_days' | 'age_groups_served' | 'programs_offered', value: string) => {
    const current = data[field];
    const updated = current.includes(value)
      ? current.filter(v => v !== value)
      : [...current, value];
    updateField(field, updated);
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (!data.opening_time) newErrors.opening_time = 'Opening time is required';
    if (!data.closing_time) newErrors.closing_time = 'Closing time is required';
    if (data.operating_days.length === 0) newErrors.operating_days = 'Select at least one day';
    if (data.age_groups_served.length === 0) newErrors.age_groups_served = 'Select at least one age group';
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
        <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center">
          <ClockIcon className="w-8 h-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Operations & Schedule</h2>
        <p className="text-gray-600">Set up your operating hours and programs</p>
      </div>

      {/* Operating Hours */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <ClockIcon className="w-5 h-5 text-amber-500" />
          Operating Hours
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Opening Time</label>
            <input
              type="time"
              value={data.opening_time}
              onChange={(e) => updateField('opening_time', e.target.value)}
              className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-primary-500 ${
                errors.opening_time ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.opening_time && <p className="text-red-500 text-sm mt-1">{errors.opening_time}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Closing Time</label>
            <input
              type="time"
              value={data.closing_time}
              onChange={(e) => updateField('closing_time', e.target.value)}
              className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-primary-500 ${
                errors.closing_time ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.closing_time && <p className="text-red-500 text-sm mt-1">{errors.closing_time}</p>}
          </div>
        </div>
      </div>

      {/* Operating Days */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <CalendarDaysIcon className="w-5 h-5 text-amber-500" />
          Operating Days
        </h3>
        <div className="flex gap-2">
          {DAYS_OF_WEEK.map((day) => (
            <button
              key={day.value}
              type="button"
              onClick={() => toggleArrayValue('operating_days', day.value)}
              className={`flex-1 py-3 rounded-xl font-medium transition-all ${
                data.operating_days.includes(day.value)
                  ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {day.label}
            </button>
          ))}
        </div>
        {errors.operating_days && <p className="text-red-500 text-sm mt-2">{errors.operating_days}</p>}
      </div>

      {/* Age Groups */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <UserGroupIcon className="w-5 h-5 text-amber-500" />
          Age Groups Served
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {AGE_GROUPS.map((group) => (
            <button
              key={group.value}
              type="button"
              onClick={() => toggleArrayValue('age_groups_served', group.value)}
              className={`relative p-4 rounded-xl border-2 text-left transition-all ${
                data.age_groups_served.includes(group.value)
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              {data.age_groups_served.includes(group.value) && (
                <div className="absolute top-2 right-2 w-5 h-5 bg-primary-500 rounded-full flex items-center justify-center">
                  <CheckIcon className="w-3 h-3 text-white" />
                </div>
              )}
              <p className="font-semibold text-gray-900">{group.label}</p>
              <p className="text-sm text-gray-500">{group.desc}</p>
            </button>
          ))}
        </div>
        {errors.age_groups_served && <p className="text-red-500 text-sm mt-2">{errors.age_groups_served}</p>}
      </div>

      {/* Programs */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <AcademicCapIcon className="w-5 h-5 text-amber-500" />
          Programs Offered
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {PROGRAMS.map((program) => (
            <button
              key={program.value}
              type="button"
              onClick={() => toggleArrayValue('programs_offered', program.value)}
              className={`relative p-4 rounded-xl border-2 text-left transition-all ${
                data.programs_offered.includes(program.value)
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              {data.programs_offered.includes(program.value) && (
                <div className="absolute top-2 right-2 w-5 h-5 bg-primary-500 rounded-full flex items-center justify-center">
                  <CheckIcon className="w-3 h-3 text-white" />
                </div>
              )}
              <span className="text-2xl">{program.icon}</span>
              <p className="font-medium text-gray-900 mt-1">{program.label}</p>
            </button>
          ))}
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
        <button
          type="button"
          onClick={handleNext}
          className="px-8 py-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white font-semibold rounded-xl hover:from-primary-600 hover:to-primary-700 transition-all shadow-lg shadow-primary-500/30"
        >
          Continue →
        </button>
      </div>
    </div>
  );
};

export default OperationsSetup;
