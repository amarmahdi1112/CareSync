import React, { useState } from 'react';
import { 
  sanitizeName, 
  sanitizePhone, 
  sanitizePostalCode,
  formatPhoneNumber,
  validateName,
  validateEmail,
  validatePhone,
  validatePostalCode,
} from '../../../../utils';

// ============================================
// BASE INPUT
// ============================================

interface InputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  type?: string;
  placeholder?: string;
  error?: string;
  helperText?: string;
}

export const Input: React.FC<InputProps> = ({ 
  label, 
  value, 
  onChange, 
  required, 
  type = 'text', 
  placeholder,
  error,
  helperText,
}) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">
      {label} {required && <span className="text-red-500">*</span>}
    </label>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full px-4 py-2.5 bg-white border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
        error ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300'
      }`}
    />
    {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
    {helperText && !error && <p className="mt-1 text-sm text-gray-500">{helperText}</p>}
  </div>
);

// ============================================
// NAME INPUT (letters only)
// ============================================

interface NameInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  placeholder?: string;
}

export const NameInput: React.FC<NameInputProps> = ({ 
  label, 
  value, 
  onChange, 
  required,
  placeholder 
}) => {
  const [touched, setTouched] = useState(false);
  const validation = touched ? validateName(value, label) : { isValid: true };
  
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(sanitizeName(e.target.value))}
        onBlur={() => setTouched(true)}
        placeholder={placeholder}
        className={`w-full px-4 py-2.5 bg-white border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
          !validation.isValid ? 'border-red-500' : 'border-gray-300'
        }`}
      />
      {!validation.isValid && <p className="mt-1 text-sm text-red-600">{validation.error}</p>}
    </div>
  );
};

// ============================================
// PHONE INPUT (digits with formatting)
// ============================================

interface PhoneInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  placeholder?: string;
}

export const PhoneInput: React.FC<PhoneInputProps> = ({ 
  label, 
  value, 
  onChange, 
  required,
  placeholder = '(555) 123-4567'
}) => {
  const [touched, setTouched] = useState(false);
  const validation = touched ? validatePhone(value, required || false, label) : { isValid: true };
  
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const sanitized = sanitizePhone(e.target.value);
    const formatted = formatPhoneNumber(sanitized);
    onChange(formatted);
  };
  
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type="tel"
        value={value}
        onChange={handleChange}
        onBlur={() => setTouched(true)}
        placeholder={placeholder}
        className={`w-full px-4 py-2.5 bg-white border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
          !validation.isValid ? 'border-red-500' : 'border-gray-300'
        }`}
      />
      {!validation.isValid && <p className="mt-1 text-sm text-red-600">{validation.error}</p>}
    </div>
  );
};

// ============================================
// EMAIL INPUT
// ============================================

interface EmailInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  placeholder?: string;
}

export const EmailInput: React.FC<EmailInputProps> = ({ 
  label, 
  value, 
  onChange, 
  required,
  placeholder = 'email@example.com'
}) => {
  const [touched, setTouched] = useState(false);
  const validation = touched ? validateEmail(value, required || false) : { isValid: true };
  
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type="email"
        value={value}
        onChange={(e) => onChange(e.target.value.toLowerCase())}
        onBlur={() => setTouched(true)}
        placeholder={placeholder}
        className={`w-full px-4 py-2.5 bg-white border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
          !validation.isValid ? 'border-red-500' : 'border-gray-300'
        }`}
      />
      {!validation.isValid && <p className="mt-1 text-sm text-red-600">{validation.error}</p>}
    </div>
  );
};

// ============================================
// POSTAL CODE INPUT
// ============================================

interface PostalCodeInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  placeholder?: string;
}

export const PostalCodeInput: React.FC<PostalCodeInputProps> = ({ 
  label, 
  value, 
  onChange, 
  required,
  placeholder = 'A1A 1A1'
}) => {
  const [touched, setTouched] = useState(false);
  const validation = touched ? validatePostalCode(value, required || false) : { isValid: true };
  
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(sanitizePostalCode(e.target.value))}
        onBlur={() => setTouched(true)}
        placeholder={placeholder}
        maxLength={7}
        className={`w-full px-4 py-2.5 bg-white border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
          !validation.isValid ? 'border-red-500' : 'border-gray-300'
        }`}
      />
      {!validation.isValid && <p className="mt-1 text-sm text-red-600">{validation.error}</p>}
    </div>
  );
};

// ============================================
// TEXTAREA
// ============================================

interface TextAreaProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
}

export const TextArea: React.FC<TextAreaProps> = ({ 
  label, 
  value, 
  onChange, 
  rows = 2, 
  placeholder 
}) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      rows={rows}
      placeholder={placeholder}
      className="w-full px-4 py-2.5 bg-white border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
    />
  </div>
);

// ============================================
// CHECKBOX
// ============================================

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
}

export const Checkbox: React.FC<CheckboxProps> = ({ 
  label, 
  checked, 
  onChange, 
  description 
}) => (
  <label className="flex items-start space-x-3 cursor-pointer p-3 rounded-lg hover:bg-gray-50">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="mt-1 h-5 w-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
    />
    <div>
      <span className="text-sm font-medium text-gray-900">{label}</span>
      {description && <p className="text-xs text-gray-500 mt-0.5">{description}</p>}
    </div>
  </label>
);

// ============================================
// SELECT
// ============================================

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
}

export const Select: React.FC<SelectProps> = ({ 
  label, 
  value, 
  onChange, 
  options, 
  placeholder = 'Select...' 
}) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-4 py-2.5 bg-white border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  </div>
);

// ============================================
// RADIO GROUP
// ============================================

interface RadioGroupProps {
  label: string;
  value: boolean | null;
  onChange: (value: boolean) => void;
  options?: { label: string; value: boolean }[];
}

export const RadioGroup: React.FC<RadioGroupProps> = ({ 
  label, 
  value, 
  onChange,
  options = [{ label: 'Yes', value: true }, { label: 'No', value: false }]
}) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    <div className="flex space-x-4 mt-2">
      {options.map((opt) => (
        <label key={String(opt.value)} className="flex items-center">
          <input
            type="radio"
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="mr-2"
          />
          {opt.label}
        </label>
      ))}
    </div>
  </div>
);
