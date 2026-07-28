/**
 * Edit Modals for Family Members
 * Guardian, Child, and Emergency Contact edit forms
 */

import React, { useState, useEffect } from 'react';
import { Modal } from '../ui';
import { api } from '../../api/client';
import { useNotificationStore } from '../../stores';
import {
  sanitizeName,
  sanitizePhone,
  sanitizePostalCode,
  formatPhoneNumber,
  validateName,
  validateEmail,
  validatePhone,
  validatePostalCode,
} from '../../utils';

// ============================================
// SHARED INPUT COMPONENTS
// ============================================

interface InputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  type?: string;
  error?: string;
}

const Input: React.FC<InputProps> = ({ label, value, onChange, required, type = 'text', error }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">
      {label} {required && <span className="text-red-500">*</span>}
    </label>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full px-3 py-2 bg-white text-gray-900 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
        error ? 'border-red-500' : 'border-gray-300'
      }`}
    />
    {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
  </div>
);

const NameInput: React.FC<InputProps> = ({ label, value, onChange, required, error }) => (
  <Input
    label={label}
    value={value}
    onChange={(v) => onChange(sanitizeName(v))}
    required={required}
    error={error}
  />
);

const PhoneInput: React.FC<InputProps> = ({ label, value, onChange, required, error }) => (
  <Input
    label={label}
    value={value}
    onChange={(v) => onChange(formatPhoneNumber(sanitizePhone(v)))}
    required={required}
    type="tel"
    error={error}
  />
);

const EmailInput: React.FC<InputProps> = ({ label, value, onChange, required, error }) => (
  <Input
    label={label}
    value={value}
    onChange={(v) => onChange(v.toLowerCase())}
    required={required}
    type="email"
    error={error}
  />
);

const PostalCodeInput: React.FC<InputProps> = ({ label, value, onChange, error }) => (
  <Input
    label={label}
    value={value}
    onChange={(v) => onChange(sanitizePostalCode(v))}
    error={error}
  />
);

const Select: React.FC<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}> = ({ label, value, onChange, options }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
    >
      <option value="">Select...</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  </div>
);

const Checkbox: React.FC<{
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
}> = ({ label, checked, onChange, description }) => (
  <label className="flex items-start gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="mt-1 h-4 w-4 text-primary-600 rounded focus:ring-primary-500"
    />
    <div>
      <span className="text-sm font-medium text-gray-900">{label}</span>
      {description && <p className="text-sm text-gray-500">{description}</p>}
    </div>
  </label>
);

// ============================================
// COMMON OPTIONS
// ============================================

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

// ============================================
// GUARDIAN EDIT MODAL
// ============================================

interface GuardianData {
  id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  guardian_type: 'primary' | 'secondary';
  email: string;
  cell_phone: string;
  home_phone?: string;
  work_phone?: string;
  address?: string;
  city?: string;
  postal_code?: string;
}

interface EditGuardianModalProps {
  isOpen: boolean;
  onClose: () => void;
  guardian: GuardianData | null;
  onSuccess: () => void;
}

const RELATIONSHIP_OPTIONS = [
  { value: 'Mother', label: 'Mother' },
  { value: 'Father', label: 'Father' },
  { value: 'Grandparent', label: 'Grandparent' },
  { value: 'Legal Guardian', label: 'Legal Guardian' },
  { value: 'Other', label: 'Other' },
];

export const EditGuardianModal: React.FC<EditGuardianModalProps> = ({
  isOpen,
  onClose,
  guardian,
  onSuccess,
}) => {
  const { success, error: showError } = useNotificationStore();
  const [errors, setErrors] = useState<Record<string, string>>({});
  
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    relationship: '',
    email: '',
    cellPhone: '',
    homePhone: '',
    workPhone: '',
    address: '',
    city: '',
    postalCode: '',
  });

  useEffect(() => {
    if (guardian) {
      setForm({
        firstName: guardian.first_name,
        lastName: guardian.last_name,
        relationship: guardian.relationship,
        email: guardian.email,
        cellPhone: guardian.cell_phone,
        homePhone: guardian.home_phone || '',
        workPhone: guardian.work_phone || '',
        address: guardian.address || '',
        city: guardian.city || '',
        postalCode: guardian.postal_code || '',
      });
      setErrors({});
    }
  }, [guardian]);

  const [loading, setLoading] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    const nameResult = validateName(form.firstName, 'First name');
    if (!nameResult.isValid) newErrors.firstName = nameResult.error!;
    
    const lastNameResult = validateName(form.lastName, 'Last name');
    if (!lastNameResult.isValid) newErrors.lastName = lastNameResult.error!;
    
    const emailResult = validateEmail(form.email, true);
    if (!emailResult.isValid) newErrors.email = emailResult.error!;
    
    const phoneResult = validatePhone(form.cellPhone, true, 'Cell phone');
    if (!phoneResult.isValid) newErrors.cellPhone = phoneResult.error!;
    
    if (form.postalCode) {
      const postalResult = validatePostalCode(form.postalCode);
      if (!postalResult.isValid) newErrors.postalCode = postalResult.error!;
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate() || !guardian) return;
    setLoading(true);
    try {
      await api.resources.update('guardians', guardian.id, {
          first_name: form.firstName,
          last_name: form.lastName,
          relationship: form.relationship,
          guardian_type: guardian.guardian_type,
          email: form.email,
          cell_phone: form.cellPhone,
          home_phone: form.homePhone || undefined,
          work_phone: form.workPhone || undefined,
          address: form.address || undefined,
          city: form.city || undefined,
          postal_code: form.postalCode || undefined,
      });
      success('Guardian Updated', 'Guardian information has been saved.');
      onSuccess();
      onClose();
    } catch (err) {
      showError('Update Failed', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Guardian"
      size="lg"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="First Name"
            value={form.firstName}
            onChange={(v) => setForm({ ...form, firstName: v })}
            required
            error={errors.firstName}
          />
          <NameInput
            label="Last Name"
            value={form.lastName}
            onChange={(v) => setForm({ ...form, lastName: v })}
            required
            error={errors.lastName}
          />
        </div>
        
        <Select
          label="Relationship"
          value={form.relationship}
          onChange={(v) => setForm({ ...form, relationship: v })}
          options={RELATIONSHIP_OPTIONS}
        />
        
        <EmailInput
          label="Email"
          value={form.email}
          onChange={(v) => setForm({ ...form, email: v })}
          required
          error={errors.email}
        />
        
        <div className="grid grid-cols-3 gap-4">
          <PhoneInput
            label="Cell Phone"
            value={form.cellPhone}
            onChange={(v) => setForm({ ...form, cellPhone: v })}
            required
            error={errors.cellPhone}
          />
          <PhoneInput
            label="Home Phone"
            value={form.homePhone}
            onChange={(v) => setForm({ ...form, homePhone: v })}
          />
          <PhoneInput
            label="Work Phone"
            value={form.workPhone}
            onChange={(v) => setForm({ ...form, workPhone: v })}
          />
        </div>
        
        <Input
          label="Address"
          value={form.address}
          onChange={(v) => setForm({ ...form, address: v })}
        />
        
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="City"
            value={form.city}
            onChange={(v) => setForm({ ...form, city: v })}
          />
          <PostalCodeInput
            label="Postal Code"
            value={form.postalCode}
            onChange={(v) => setForm({ ...form, postalCode: v })}
            error={errors.postalCode}
          />
        </div>
        
        <div className="flex justify-end gap-3 pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </Modal>
  );
};

// ============================================
// ADD GUARDIAN MODAL
// ============================================

interface AddGuardianModalProps {
  isOpen: boolean;
  onClose: () => void;
  familyId: string;
  onSuccess: () => void;
  // Pre-fill address from primary guardian (optional)
  suggestedAddress?: {
    address?: string;
    city?: string;
    postalCode?: string;
  };
}

export const AddGuardianModal: React.FC<AddGuardianModalProps> = ({
  isOpen,
  onClose,
  familyId,
  onSuccess,
  suggestedAddress,
}) => {
  const { success, error: showError } = useNotificationStore();
  const [errors, setErrors] = useState<Record<string, string>>({});
  
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    relationship: 'Mother',
    email: '',
    cellPhone: '',
    homePhone: '',
    workPhone: '',
    address: '',
    city: '',
    postalCode: '',
  });

  useEffect(() => {
    if (isOpen) {
      setForm({
        firstName: '',
        lastName: '',
        relationship: 'Mother',
        email: '',
        cellPhone: '',
        homePhone: '',
        workPhone: '',
        // Pre-fill with primary guardian's address if available
        address: suggestedAddress?.address || '',
        city: suggestedAddress?.city || '',
        postalCode: suggestedAddress?.postalCode || '',
      });
      setErrors({});
    }
  }, [isOpen, suggestedAddress]);

  const [loading, setLoading] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    const nameResult = validateName(form.firstName, 'First name');
    if (!nameResult.isValid) newErrors.firstName = nameResult.error!;
    
    const lastNameResult = validateName(form.lastName, 'Last name');
    if (!lastNameResult.isValid) newErrors.lastName = lastNameResult.error!;
    
    const emailResult = validateEmail(form.email, true);
    if (!emailResult.isValid) newErrors.email = emailResult.error!;
    
    const phoneResult = validatePhone(form.cellPhone, true, 'Cell phone');
    if (!phoneResult.isValid) newErrors.cellPhone = phoneResult.error!;
    
    if (form.postalCode) {
      const postalResult = validatePostalCode(form.postalCode);
      if (!postalResult.isValid) newErrors.postalCode = postalResult.error!;
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setLoading(true);
    try {
      await api.resources.create('guardians', {
          family_id: familyId,
          first_name: form.firstName,
          last_name: form.lastName,
          relationship: form.relationship,
          guardian_type: 'secondary', // Additional guardians are secondary
          email: form.email,
          cell_phone: form.cellPhone,
          home_phone: form.homePhone || undefined,
          work_phone: form.workPhone || undefined,
          address: form.address || undefined,
          city: form.city || undefined,
          postal_code: form.postalCode || undefined,
      });
      success('Guardian Added', 'Guardian has been added to the family.');
      onSuccess();
      onClose();
    } catch (err) {
      showError('Failed to Add', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add Guardian"
      size="lg"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="First Name"
            value={form.firstName}
            onChange={(v) => setForm({ ...form, firstName: v })}
            required
            error={errors.firstName}
          />
          <NameInput
            label="Last Name"
            value={form.lastName}
            onChange={(v) => setForm({ ...form, lastName: v })}
            required
            error={errors.lastName}
          />
        </div>
        
        <Select
          label="Relationship"
          value={form.relationship}
          onChange={(v) => setForm({ ...form, relationship: v })}
          options={RELATIONSHIP_OPTIONS}
        />
        
        <EmailInput
          label="Email"
          value={form.email}
          onChange={(v) => setForm({ ...form, email: v })}
          required
          error={errors.email}
        />
        
        <div className="grid grid-cols-3 gap-4">
          <PhoneInput
            label="Cell Phone"
            value={form.cellPhone}
            onChange={(v) => setForm({ ...form, cellPhone: v })}
            required
            error={errors.cellPhone}
          />
          <PhoneInput
            label="Home Phone"
            value={form.homePhone}
            onChange={(v) => setForm({ ...form, homePhone: v })}
          />
          <PhoneInput
            label="Work Phone"
            value={form.workPhone}
            onChange={(v) => setForm({ ...form, workPhone: v })}
          />
        </div>
        
        <Input
          label="Address"
          value={form.address}
          onChange={(v) => setForm({ ...form, address: v })}
        />
        
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="City"
            value={form.city}
            onChange={(v) => setForm({ ...form, city: v })}
          />
          <PostalCodeInput
            label="Postal Code"
            value={form.postalCode}
            onChange={(v) => setForm({ ...form, postalCode: v })}
            error={errors.postalCode}
          />
        </div>
        
        <div className="flex justify-end gap-3 pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Adding...' : 'Add Guardian'}
          </button>
        </div>
      </div>
    </Modal>
  );
};

// ============================================
// CHILD EDIT MODAL
// ============================================

interface ChildData {
  id: string;
  first_name: string;
  middle_name?: string;
  last_name: string;
  date_of_birth: string;
  start_date: string;
  gender?: string;
  health_care_number?: string;
  allergies?: string;
  medical_conditions?: string;
  medications?: string;
  immunization_up_to_date?: boolean;
  doctor_name?: string;
  doctor_phone?: string;
}

interface EditChildModalProps {
  isOpen: boolean;
  onClose: () => void;
  child: ChildData | null;
  onSuccess: () => void;
}

const GENDER_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
];

export const EditChildModal: React.FC<EditChildModalProps> = ({
  isOpen,
  onClose,
  child,
  onSuccess,
}) => {
  const { success, error: showError } = useNotificationStore();
  const [errors, setErrors] = useState<Record<string, string>>({});
  
  const [form, setForm] = useState({
    firstName: '',
    middleName: '',
    lastName: '',
    dateOfBirth: '',
    startDate: '',
    gender: '',
    healthCareNumber: '',
    allergies: '',
    medicalConditions: '',
    medications: '',
    immunizationUpToDate: false,
    doctorName: '',
    doctorPhone: '',
  });

  useEffect(() => {
    if (child) {
      setForm({
        firstName: child.first_name,
        middleName: child.middle_name || '',
        lastName: child.last_name,
        dateOfBirth: child.date_of_birth,
        startDate: child.start_date,
        gender: child.gender || '',
        healthCareNumber: child.health_care_number || '',
        allergies: child.allergies || '',
        medicalConditions: child.medical_conditions || '',
        medications: child.medications || '',
        immunizationUpToDate: child.immunization_up_to_date || false,
        doctorName: child.doctor_name || '',
        doctorPhone: child.doctor_phone || '',
      });
      setErrors({});
    }
  }, [child]);

  const [loading, setLoading] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    const nameResult = validateName(form.firstName, 'First name');
    if (!nameResult.isValid) newErrors.firstName = nameResult.error!;
    
    const lastNameResult = validateName(form.lastName, 'Last name');
    if (!lastNameResult.isValid) newErrors.lastName = lastNameResult.error!;
    
    if (!form.dateOfBirth) newErrors.dateOfBirth = 'Date of birth is required';
    if (!form.startDate) newErrors.startDate = 'Start date is required';
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate() || !child) return;
    setLoading(true);
    try {
      await api.resources.update('children', child.id, {
          first_name: form.firstName,
          middle_name: form.middleName || undefined,
          last_name: form.lastName,
          date_of_birth: form.dateOfBirth,
          start_date: form.startDate,
          gender: form.gender || undefined,
          health_care_number: form.healthCareNumber || undefined,
          allergies: form.allergies || undefined,
          medical_conditions: form.medicalConditions || undefined,
          medications: form.medications || undefined,
          immunization_up_to_date: form.immunizationUpToDate,
          doctor_name: form.doctorName || undefined,
          doctor_phone: form.doctorPhone || undefined,
      });
      success('Child Updated', 'Child information has been saved.');
      onSuccess();
      onClose();
    } catch (err) {
      showError('Update Failed', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Child"
      size="lg"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <NameInput
            label="First Name"
            value={form.firstName}
            onChange={(v) => setForm({ ...form, firstName: v })}
            required
            error={errors.firstName}
          />
          <NameInput
            label="Middle Name"
            value={form.middleName}
            onChange={(v) => setForm({ ...form, middleName: v })}
          />
          <NameInput
            label="Last Name"
            value={form.lastName}
            onChange={(v) => setForm({ ...form, lastName: v })}
            required
            error={errors.lastName}
          />
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Date of Birth"
            value={form.dateOfBirth}
            onChange={(v) => setForm({ ...form, dateOfBirth: v })}
            required
            type="date"
            error={errors.dateOfBirth}
          />
          <Input
            label="Start Date"
            value={form.startDate}
            onChange={(v) => setForm({ ...form, startDate: v })}
            required
            type="date"
            error={errors.startDate}
          />
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <Select
            label="Gender"
            value={form.gender}
            onChange={(v) => setForm({ ...form, gender: v })}
            options={GENDER_OPTIONS}
          />
          <Input
            label="Health Care Number"
            value={form.healthCareNumber}
            onChange={(v) => setForm({ ...form, healthCareNumber: v })}
          />
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="Doctor Name"
            value={form.doctorName}
            onChange={(v) => setForm({ ...form, doctorName: v })}
          />
          <PhoneInput
            label="Doctor Phone"
            value={form.doctorPhone}
            onChange={(v) => setForm({ ...form, doctorPhone: v })}
          />
        </div>
        
        <Checkbox
          label="Immunization Up to Date"
          checked={form.immunizationUpToDate}
          onChange={(v) => setForm({ ...form, immunizationUpToDate: v })}
        />
        
        <div className="border-t pt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Medical Information</h4>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Allergies</label>
              <textarea
                value={form.allergies}
                onChange={(e) => setForm({ ...form, allergies: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                placeholder='List allergies or "None"'
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Medical Conditions</label>
              <textarea
                value={form.medicalConditions}
                onChange={(e) => setForm({ ...form, medicalConditions: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Medications</label>
              <textarea
                value={form.medications}
                onChange={(e) => setForm({ ...form, medications: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
              />
            </div>
          </div>
        </div>
        
        <div className="flex justify-end gap-3 pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </Modal>
  );
};

// ============================================
// EMERGENCY CONTACT EDIT MODAL
// ============================================

interface EmergencyContactData {
  id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  cell_phone: string;
  home_phone?: string;
  authorized_pickup: boolean;
}

interface EditEmergencyContactModalProps {
  isOpen: boolean;
  onClose: () => void;
  contact: EmergencyContactData | null;
  onSuccess: () => void;
}

export const EditEmergencyContactModal: React.FC<EditEmergencyContactModalProps> = ({
  isOpen,
  onClose,
  contact,
  onSuccess,
}) => {
  const { success, error: showError } = useNotificationStore();
  const [errors, setErrors] = useState<Record<string, string>>({});
  
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    relationship: '',
    cellPhone: '',
    homePhone: '',
    authorizedPickup: true,
  });

  useEffect(() => {
    if (contact) {
      setForm({
        firstName: contact.first_name,
        lastName: contact.last_name,
        relationship: contact.relationship,
        cellPhone: contact.cell_phone,
        homePhone: contact.home_phone || '',
        authorizedPickup: contact.authorized_pickup,
      });
      setErrors({});
    }
  }, [contact]);

  const [loading, setLoading] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    const nameResult = validateName(form.firstName, 'First name');
    if (!nameResult.isValid) newErrors.firstName = nameResult.error!;
    
    const lastNameResult = validateName(form.lastName, 'Last name');
    if (!lastNameResult.isValid) newErrors.lastName = lastNameResult.error!;
    
    if (!form.relationship) newErrors.relationship = 'Relationship is required';
    
    const phoneResult = validatePhone(form.cellPhone, true, 'Cell phone');
    if (!phoneResult.isValid) newErrors.cellPhone = phoneResult.error!;
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate() || !contact) return;
    setLoading(true);
    try {
      await api.resources.update('emergency_contacts', contact.id, {
          first_name: form.firstName,
          last_name: form.lastName,
          relationship: form.relationship,
          cell_phone: form.cellPhone,
          home_phone: form.homePhone || undefined,
          authorized_pickup: form.authorizedPickup,
      });
      success('Contact Updated', 'Emergency contact has been saved.');
      onSuccess();
      onClose();
    } catch (err) {
      showError('Update Failed', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Emergency Contact"
      size="md"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="First Name"
            value={form.firstName}
            onChange={(v) => setForm({ ...form, firstName: v })}
            required
            error={errors.firstName}
          />
          <NameInput
            label="Last Name"
            value={form.lastName}
            onChange={(v) => setForm({ ...form, lastName: v })}
            required
            error={errors.lastName}
          />
        </div>
        
        <Select
          label="Relationship"
          value={form.relationship}
          onChange={(v) => setForm({ ...form, relationship: v })}
          options={EMERGENCY_RELATIONSHIP_OPTIONS}
        />
        
        <div className="grid grid-cols-2 gap-4">
          <PhoneInput
            label="Cell Phone"
            value={form.cellPhone}
            onChange={(v) => setForm({ ...form, cellPhone: v })}
            required
            error={errors.cellPhone}
          />
          <PhoneInput
            label="Home Phone"
            value={form.homePhone}
            onChange={(v) => setForm({ ...form, homePhone: v })}
          />
        </div>
        
        <Checkbox
          label="Authorized for Pickup"
          checked={form.authorizedPickup}
          onChange={(v) => setForm({ ...form, authorizedPickup: v })}
          description="This person is authorized to pick up the child(ren)"
        />
        
        <div className="flex justify-end gap-3 pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </Modal>
  );
};

// ============================================
// ADD EMERGENCY CONTACT MODAL
// ============================================

interface AddEmergencyContactModalProps {
  isOpen: boolean;
  onClose: () => void;
  familyId: string;
  onSuccess: () => void;
}

export const AddEmergencyContactModal: React.FC<AddEmergencyContactModalProps> = ({
  isOpen,
  onClose,
  familyId,
  onSuccess,
}) => {
  const { success, error: showError } = useNotificationStore();
  const [errors, setErrors] = useState<Record<string, string>>({});
  
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    relationship: 'Family Friend', // Default relationship
    cellPhone: '',
    homePhone: '',
    authorizedPickup: true,
  });

  useEffect(() => {
    if (isOpen) {
      setForm({
        firstName: '',
        lastName: '',
        relationship: 'Family Friend', // Default relationship
        cellPhone: '',
        homePhone: '',
        authorizedPickup: true,
      });
      setErrors({});
    }
  }, [isOpen]);

  const [loading, setLoading] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    const nameResult = validateName(form.firstName, 'First name');
    if (!nameResult.isValid) newErrors.firstName = nameResult.error!;
    
    const lastNameResult = validateName(form.lastName, 'Last name');
    if (!lastNameResult.isValid) newErrors.lastName = lastNameResult.error!;
    
    if (!form.relationship) newErrors.relationship = 'Relationship is required';
    
    const phoneResult = validatePhone(form.cellPhone, true, 'Cell phone');
    if (!phoneResult.isValid) newErrors.cellPhone = phoneResult.error!;
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setLoading(true);
    try {
      await api.resources.create('emergency_contacts', {
          family_id: familyId,
          first_name: form.firstName,
          last_name: form.lastName,
          relationship: form.relationship,
          cell_phone: form.cellPhone,
          home_phone: form.homePhone || undefined,
          authorized_pickup: form.authorizedPickup,
      });
      success('Contact Added', 'Emergency contact has been added.');
      onSuccess();
      onClose();
    } catch (err) {
      showError('Failed to Add', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add Emergency Contact"
      size="md"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <NameInput
            label="First Name"
            value={form.firstName}
            onChange={(v) => setForm({ ...form, firstName: v })}
            required
            error={errors.firstName}
          />
          <NameInput
            label="Last Name"
            value={form.lastName}
            onChange={(v) => setForm({ ...form, lastName: v })}
            required
            error={errors.lastName}
          />
        </div>
        
        <Select
          label="Relationship"
          value={form.relationship}
          onChange={(v) => setForm({ ...form, relationship: v })}
          options={EMERGENCY_RELATIONSHIP_OPTIONS}
        />
        
        <div className="grid grid-cols-2 gap-4">
          <PhoneInput
            label="Cell Phone"
            value={form.cellPhone}
            onChange={(v) => setForm({ ...form, cellPhone: v })}
            required
            error={errors.cellPhone}
          />
          <PhoneInput
            label="Home Phone"
            value={form.homePhone}
            onChange={(v) => setForm({ ...form, homePhone: v })}
          />
        </div>
        
        <Checkbox
          label="Authorized for Pickup"
          checked={form.authorizedPickup}
          onChange={(v) => setForm({ ...form, authorizedPickup: v })}
          description="This person is authorized to pick up the child(ren)"
        />
        
        <div className="flex justify-end gap-3 pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Adding...' : 'Add Contact'}
          </button>
        </div>
      </div>
    </Modal>
  );
};
