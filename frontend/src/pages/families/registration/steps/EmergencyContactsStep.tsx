import React from 'react';
import { PhoneIcon, TrashIcon, PlusIcon, CheckCircleIcon, ShieldExclamationIcon } from '@heroicons/react/24/outline';
import { Checkbox, NameInput, PhoneInput, Select } from '../components/FormFields';
import type { EmergencyContact } from '../types';

// Common relationship options for emergency contacts
const EMERGENCY_RELATIONSHIP_OPTIONS = [
  { value: 'Family Friend', label: 'Family Friend' },
  { value: 'Grandparent', label: 'Grandparent' },
  { value: 'Aunt', label: 'Aunt' },
  { value: 'Uncle', label: 'Uncle' },
  { value: 'Cousin', label: 'Cousin' },
  { value: 'Sibling', label: 'Sibling' },
  { value: 'Neighbor', label: 'Neighbor' },
  { value: 'Babysitter', label: 'Babysitter' },
  { value: 'Coworker', label: 'Coworker' },
  { value: 'Other', label: 'Other' },
];

interface ContactCardProps {
  contact: EmergencyContact;
  index: number;
  canRemove: boolean;
  onUpdate: (field: keyof EmergencyContact, value: unknown) => void;
  onRemove: () => void;
}

const ContactCard: React.FC<ContactCardProps> = ({ 
  contact, 
  index, 
  canRemove, 
  onUpdate, 
  onRemove 
}) => (
  <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
    {/* Card Header */}
    <div className="bg-gradient-to-r from-red-50 to-orange-50 px-5 py-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center">
          <PhoneIcon className="w-5 h-5 text-red-500" />
        </div>
        <div>
          <h3 className="font-semibold text-gray-900">
            {contact.firstName || `Contact ${index + 1}`} {contact.lastName}
          </h3>
          <div className="flex items-center gap-2 mt-0.5">
            {contact.relationship && (
              <span className="text-sm text-gray-500">{contact.relationship}</span>
            )}
            {contact.authorizedPickup && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                <CheckCircleIcon className="w-3 h-3" />
                Pickup OK
              </span>
            )}
          </div>
        </div>
      </div>
      {canRemove && (
        <button 
          onClick={onRemove} 
          className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
          title="Remove contact"
        >
          <TrashIcon className="w-5 h-5" />
        </button>
      )}
    </div>

    {/* Form Fields */}
    <div className="p-5 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <NameInput 
          label="First Name" 
          value={contact.firstName} 
          onChange={(v) => onUpdate('firstName', v)} 
          required 
        />
        <NameInput 
          label="Last Name" 
          value={contact.lastName} 
          onChange={(v) => onUpdate('lastName', v)} 
          required 
        />
        <Select 
          label="Relationship to Child" 
          value={contact.relationship} 
          onChange={(v) => onUpdate('relationship', v)} 
          options={EMERGENCY_RELATIONSHIP_OPTIONS}
        />
        <PhoneInput 
          label="Cell Phone" 
          value={contact.cellPhone} 
          onChange={(v) => onUpdate('cellPhone', v)} 
          required 
        />
        <PhoneInput 
          label="Home Phone (Optional)" 
          value={contact.homePhone} 
          onChange={(v) => onUpdate('homePhone', v)} 
        />
      </div>

      {/* Pickup Authorization */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <Checkbox
          label="Authorized for Pickup"
          checked={contact.authorizedPickup}
          onChange={(v) => onUpdate('authorizedPickup', v)}
          description="This person is authorized to pick up the child(ren) from care"
        />
      </div>
    </div>
  </div>
);

interface EmergencyContactsStepProps {
  contacts: EmergencyContact[];
  onUpdateContact: (id: string, field: keyof EmergencyContact, value: unknown) => void;
  onAddContact: () => void;
  onRemoveContact: (id: string) => void;
}

export const EmergencyContactsStep: React.FC<EmergencyContactsStepProps> = ({ 
  contacts, 
  onUpdateContact, 
  onAddContact, 
  onRemoveContact 
}) => (
  <div className="space-y-6">
    {/* Info Banner */}
    <div className="bg-red-50 border border-red-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
          <ShieldExclamationIcon className="w-4 h-4 text-red-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-red-800">Emergency Contacts Required</p>
          <p className="text-sm text-red-600 mt-0.5">
            Please add at least one person we can contact if guardians are unavailable.
          </p>
        </div>
      </div>
    </div>

    {contacts.map((contact, index) => (
      <ContactCard
        key={contact.id}
        contact={contact}
        index={index}
        canRemove={contacts.length > 1}
        onUpdate={(field, value) => onUpdateContact(contact.id, field, value)}
        onRemove={() => onRemoveContact(contact.id)}
      />
    ))}

    <button
      type="button"
      onClick={onAddContact}
      className="w-full py-4 border-2 border-dashed border-gray-200 rounded-xl text-gray-500 hover:border-primary-400 hover:text-primary-600 hover:bg-primary-50/50 transition-all flex items-center justify-center gap-2"
    >
      <PlusIcon className="w-5 h-5" />
      Add Another Contact
    </button>
  </div>
);
