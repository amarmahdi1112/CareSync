import React from 'react';
import { TrashIcon, PlusIcon, HeartIcon, UserIcon } from '@heroicons/react/24/outline';
import { Input, TextArea, Select, RadioGroup, NameInput, PhoneInput } from '../components/FormFields';
import { AgeGroupBadge } from '../../../../components/ui';
import { calculateAgeGroup } from '../helpers';
import type { Child } from '../types';

const GENDER_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
];

interface ChildCardProps {
  child: Child;
  index: number;
  canRemove: boolean;
  onUpdate: (field: keyof Child, value: unknown) => void;
  onRemove: () => void;
}

const ChildCard: React.FC<ChildCardProps> = ({ child, index, canRemove, onUpdate, onRemove }) => (
  <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
    {/* Card Header */}
    <div className="bg-gradient-to-r from-primary-50 to-primary-100/50 px-5 py-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center text-lg font-bold text-primary-600">
          {child.firstName?.[0] || index + 1}
        </div>
        <div>
          <h3 className="font-semibold text-gray-900">
            {child.firstName || `Child ${index + 1}`} {child.lastName}
          </h3>
          {child.dateOfBirth && (
            <div className="flex items-center gap-2 mt-0.5">
              <AgeGroupBadge ageGroup={calculateAgeGroup(child.dateOfBirth)!} />
            </div>
          )}
        </div>
      </div>
      {canRemove && (
        <button 
          onClick={onRemove} 
          className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
          title="Remove child"
        >
          <TrashIcon className="w-5 h-5" />
        </button>
      )}
    </div>

    {/* Basic Info Section */}
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <UserIcon className="w-4 h-4 text-gray-400" />
        <h4 className="text-sm font-medium text-gray-700">Basic Information</h4>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <NameInput 
          label="First Name" 
          value={child.firstName} 
          onChange={(v) => onUpdate('firstName', v)} 
          required 
        />
        <NameInput 
          label="Middle Name" 
          value={child.middleName} 
          onChange={(v) => onUpdate('middleName', v)} 
        />
        <NameInput 
          label="Last Name" 
          value={child.lastName} 
          onChange={(v) => onUpdate('lastName', v)} 
          required 
        />
        <Input 
          label="Date of Birth" 
          value={child.dateOfBirth} 
          onChange={(v) => onUpdate('dateOfBirth', v)} 
          required 
          type="date" 
        />
        <Select
          label="Gender"
          value={child.gender}
          onChange={(v) => onUpdate('gender', v)}
          options={GENDER_OPTIONS}
        />
        <Input 
          label="Start Date" 
          value={child.startDate} 
          onChange={(v) => onUpdate('startDate', v)} 
          required 
          type="date" 
        />
      </div>
    </div>

    {/* Medical Info Section */}
    <div className="border-t border-gray-100 bg-red-50/30 p-5 space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <HeartIcon className="w-4 h-4 text-red-500" />
        <h4 className="text-sm font-medium text-gray-700">Medical Information</h4>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Input 
          label="Health Care Number" 
          value={child.healthCareNumber} 
          onChange={(v) => onUpdate('healthCareNumber', v)} 
        />
        <NameInput 
          label="Family Doctor" 
          value={child.doctorName} 
          onChange={(v) => onUpdate('doctorName', v)} 
        />
        <PhoneInput 
          label="Doctor Phone" 
          value={child.doctorPhone} 
          onChange={(v) => onUpdate('doctorPhone', v)} 
        />
        <div className="md:col-span-3">
          <RadioGroup
            label="Immunizations Up to Date?"
            value={child.immunizationUpToDate}
            onChange={(v) => onUpdate('immunizationUpToDate', v)}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <TextArea 
          label="Allergies" 
          value={child.allergies} 
          onChange={(v) => onUpdate('allergies', v)} 
          placeholder='List allergies or "None"' 
        />
        <TextArea 
          label="Medical Conditions" 
          value={child.medicalConditions} 
          onChange={(v) => onUpdate('medicalConditions', v)}
          placeholder='e.g., asthma, diabetes'
        />
        <TextArea 
          label="Current Medications" 
          value={child.medications} 
          onChange={(v) => onUpdate('medications', v)}
          placeholder='List medications or "None"'
        />
      </div>
    </div>
  </div>
);

interface ChildrenStepProps {
  children: Child[];
  onUpdateChild: (id: string, field: keyof Child, value: unknown) => void;
  onAddChild: () => void;
  onRemoveChild: (id: string) => void;
}

export const ChildrenStep: React.FC<ChildrenStepProps> = ({ 
  children, 
  onUpdateChild, 
  onAddChild, 
  onRemoveChild 
}) => (
  <div className="space-y-6">
    {/* Info Banner */}
    <div className="bg-green-50 border border-green-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center flex-shrink-0">
          <UserIcon className="w-4 h-4 text-green-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-green-800">
            {children.length} {children.length === 1 ? 'Child' : 'Children'} to Register
          </p>
          <p className="text-sm text-green-600 mt-0.5">
            Add all children who will be enrolled in the program.
          </p>
        </div>
      </div>
    </div>

    {children.map((child, index) => (
      <ChildCard
        key={child.id}
        child={child}
        index={index}
        canRemove={children.length > 1}
        onUpdate={(field, value) => onUpdateChild(child.id, field, value)}
        onRemove={() => onRemoveChild(child.id)}
      />
    ))}

    <button
      type="button"
      onClick={onAddChild}
      className="w-full py-4 border-2 border-dashed border-gray-200 rounded-xl text-gray-500 hover:border-primary-400 hover:text-primary-600 hover:bg-primary-50/50 transition-all flex items-center justify-center gap-2"
    >
      <PlusIcon className="w-5 h-5" />
      Add Another Child
    </button>
  </div>
);
