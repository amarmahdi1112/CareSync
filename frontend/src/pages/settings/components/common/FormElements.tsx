// ============================================
// Settings Form Elements
// ============================================

import React from 'react';
import { ExclamationTriangleIcon, CheckCircleIcon } from '@heroicons/react/24/outline';

// -------------------- Toggle Switch --------------------

interface ToggleSwitchProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  label?: string;
  description?: string;
  disabled?: boolean;
}

export const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  enabled,
  onChange,
  label,
  description,
  disabled = false,
}) => (
  <div className="flex items-center justify-between">
    {(label || description) && (
      <div>
        {label && <p className="font-medium text-gray-900">{label}</p>}
        {description && <p className="text-sm text-gray-500">{description}</p>}
      </div>
    )}
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        enabled ? 'bg-primary-600' : 'bg-gray-200'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  </div>
);

// -------------------- Toggle Card (for prominent toggles) --------------------

interface ToggleCardProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  title: string;
  description: string;
}

export const ToggleCard: React.FC<ToggleCardProps> = ({
  enabled,
  onChange,
  title,
  description,
}) => (
  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
    <div>
      <p className="font-medium text-gray-900">{title}</p>
      <p className="text-sm text-gray-500">{description}</p>
    </div>
    <label className="relative inline-flex items-center cursor-pointer">
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only peer"
      />
      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
    </label>
  </div>
);

// -------------------- Form Field --------------------

interface FormFieldProps {
  label: string;
  icon?: React.ElementType;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}

export const FormField: React.FC<FormFieldProps> = ({
  label,
  icon: Icon,
  required,
  error,
  hint,
  children,
  className = '',
}) => (
  <div className={className}>
    <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-2">
      {Icon && <Icon className="h-4 w-4 text-gray-400" />}
      {label}
      {required && <span className="text-red-500">*</span>}
    </label>
    {children}
    {error && (
      <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
        <ExclamationTriangleIcon className="h-4 w-4" />
        {error}
      </p>
    )}
    {hint && !error && (
      <p className="mt-1 text-xs text-gray-500">{hint}</p>
    )}
  </div>
);

// -------------------- Form Input --------------------

interface FormInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  icon?: React.ElementType;
  error?: string;
  hint?: string;
}

export const FormInput: React.FC<FormInputProps> = ({
  label,
  icon,
  error,
  hint,
  required,
  className = '',
  ...props
}) => (
  <FormField label={label} icon={icon} required={required} error={error} hint={hint}>
    <input
      {...props}
      className={`input ${error ? 'border-red-500' : ''} ${className}`}
    />
  </FormField>
);

// -------------------- Form Select --------------------

interface SelectOption {
  value: string;
  label: string;
}

interface FormSelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label: string;
  icon?: React.ElementType;
  options: SelectOption[];
  error?: string;
  hint?: string;
}

export const FormSelect: React.FC<FormSelectProps> = ({
  label,
  icon,
  options,
  error,
  hint,
  required,
  className = '',
  ...props
}) => (
  <FormField label={label} icon={icon} required={required} error={error} hint={hint}>
    <select {...props} className={`input ${error ? 'border-red-500' : ''} ${className}`}>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  </FormField>
);

// -------------------- Form Textarea --------------------

interface FormTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  icon?: React.ElementType;
  error?: string;
  hint?: string;
}

export const FormTextarea: React.FC<FormTextareaProps> = ({
  label,
  icon,
  error,
  hint,
  required,
  className = '',
  ...props
}) => (
  <FormField label={label} icon={icon} required={required} error={error} hint={hint}>
    <textarea
      {...props}
      className={`input ${error ? 'border-red-500' : ''} ${className}`}
    />
  </FormField>
);

// -------------------- Radio Group --------------------

interface RadioOption {
  value: string;
  label: string;
}

interface RadioGroupProps {
  name: string;
  options: RadioOption[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
}

export const RadioGroup: React.FC<RadioGroupProps> = ({
  name,
  options,
  value,
  onChange,
  label,
}) => (
  <div>
    {label && <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>}
    <div className="flex gap-4">
      {options.map((opt) => (
        <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            name={name}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500"
          />
          <span className="text-sm text-gray-700">{opt.label}</span>
        </label>
      ))}
    </div>
  </div>
);

// -------------------- Checkbox List --------------------

interface CheckboxItemProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  icon?: React.ElementType;
}

export const CheckboxItem: React.FC<CheckboxItemProps> = ({
  checked,
  onChange,
  label,
  icon: Icon,
}) => (
  <label className="flex items-center gap-2 cursor-pointer">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
    />
    {Icon && <Icon className="h-4 w-4 text-gray-400" />}
    <span className="text-sm text-gray-700">{label}</span>
  </label>
);

// -------------------- Password Match Indicator --------------------

interface PasswordMatchIndicatorProps {
  isMatch: boolean;
}

export const PasswordMatchIndicator: React.FC<PasswordMatchIndicatorProps> = ({ isMatch }) => (
  <p className="mt-1 text-sm text-green-600 flex items-center gap-1">
    <CheckCircleIcon className="h-4 w-4" />
    {isMatch ? 'Passwords match' : ''}
  </p>
);

// -------------------- Password Strength Indicator --------------------

interface PasswordStrengthProps {
  password: string;
}

export const PasswordStrengthIndicator: React.FC<PasswordStrengthProps> = ({ password }) => {
  const getStrength = () => {
    if (!password) return { strength: 0, label: '', color: '' };
    
    let strength = 0;
    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++;
    if (/[0-9]/.test(password)) strength++;
    if (/[^a-zA-Z0-9]/.test(password)) strength++;

    if (strength <= 2) return { strength, label: 'Weak', color: 'bg-red-500' };
    if (strength <= 3) return { strength, label: 'Medium', color: 'bg-yellow-500' };
    if (strength <= 4) return { strength, label: 'Strong', color: 'bg-green-500' };
    return { strength, label: 'Very Strong', color: 'bg-green-600' };
  };

  const { strength, label, color } = getStrength();

  if (!password) return null;

  return (
    <div className="mt-2">
      <div className="flex items-center gap-2 mb-1">
        <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${color}`}
            style={{ width: `${(strength / 5) * 100}%` }}
          />
        </div>
        <span className={`text-xs font-medium ${
          strength <= 2 ? 'text-red-600' :
          strength <= 3 ? 'text-yellow-600' : 'text-green-600'
        }`}>
          {label}
        </span>
      </div>
    </div>
  );
};

// -------------------- Password Requirements Checklist --------------------

interface PasswordRequirementsProps {
  password: string;
}

export const PasswordRequirements: React.FC<PasswordRequirementsProps> = ({ password }) => {
  const requirements = [
    { label: 'At least 8 characters', met: password.length >= 8 },
    { label: 'Mix of uppercase and lowercase', met: /[A-Z]/.test(password) && /[a-z]/.test(password) },
    { label: 'At least one number', met: /[0-9]/.test(password) },
    { label: 'Special character (recommended)', met: /[^a-zA-Z0-9]/.test(password) },
  ];

  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <h4 className="text-sm font-medium text-gray-700 mb-2">Password Requirements</h4>
      <ul className="text-sm text-gray-600 space-y-1">
        {requirements.map((req, idx) => (
          <li key={idx} className={`flex items-center gap-2 ${req.met ? 'text-green-600' : ''}`}>
            {req.met ? (
              <CheckCircleIcon className="h-4 w-4" />
            ) : (
              <span className="w-4 h-4 rounded-full border border-gray-300" />
            )}
            {req.label}
          </li>
        ))}
      </ul>
    </div>
  );
};
