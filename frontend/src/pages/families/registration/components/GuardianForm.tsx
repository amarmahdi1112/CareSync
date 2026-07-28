import React from 'react';
import { Input, Select, NameInput, PhoneInput, EmailInput, PostalCodeInput } from './FormFields';
import type { Guardian } from '../types';

const RELATIONSHIP_OPTIONS = [
  { value: 'Mother', label: 'Mother' },
  { value: 'Father', label: 'Father' },
  { value: 'Grandparent', label: 'Grandparent' },
  { value: 'Legal Guardian', label: 'Legal Guardian' },
  { value: 'Other', label: 'Other' },
];

interface GuardianFormProps {
  guardian: Guardian;
  onChange: (field: keyof Guardian, value: string) => void;
  title?: string;
  isPrimary?: boolean;
}

export const GuardianForm: React.FC<GuardianFormProps> = ({ guardian, onChange, title, isPrimary = true }) => (
  <div className="space-y-4">
    {title && <h3 className="text-lg font-medium text-gray-900">{title}</h3>}
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <NameInput 
        label="First Name" 
        value={guardian.firstName} 
        onChange={(v) => onChange('firstName', v)} 
        required={isPrimary}
      />
      <NameInput 
        label="Last Name" 
        value={guardian.lastName} 
        onChange={(v) => onChange('lastName', v)} 
        required={isPrimary}
      />
      <Select
        label="Relationship"
        value={guardian.relationship}
        onChange={(v) => onChange('relationship', v)}
        options={RELATIONSHIP_OPTIONS}
      />
      <EmailInput 
        label="Email" 
        value={guardian.email} 
        onChange={(v) => onChange('email', v)} 
        required={isPrimary}
      />
      <PhoneInput 
        label="Cell Phone" 
        value={guardian.cellPhone} 
        onChange={(v) => onChange('cellPhone', v)} 
        required={isPrimary}
      />
      <PhoneInput 
        label="Home Phone" 
        value={guardian.homePhone} 
        onChange={(v) => onChange('homePhone', v)} 
      />
      <PhoneInput 
        label="Work Phone" 
        value={guardian.workPhone} 
        onChange={(v) => onChange('workPhone', v)} 
      />
      <div className="md:col-span-2">
        <Input 
          label="Address" 
          value={guardian.address} 
          onChange={(v) => onChange('address', v)} 
        />
      </div>
      <NameInput 
        label="City" 
        value={guardian.city} 
        onChange={(v) => onChange('city', v)} 
      />
      <PostalCodeInput 
        label="Postal Code" 
        value={guardian.postalCode} 
        onChange={(v) => onChange('postalCode', v)} 
      />
    </div>
  </div>
);
