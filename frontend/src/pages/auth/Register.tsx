// ============================================
// Simplified Registration - Quick Account Creation
// After signup → Auto-login → Onboarding Wizard
// ============================================

import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  EyeIcon,
  EyeSlashIcon,
  CheckCircleIcon,
  ArrowRightIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../context/AuthContext';
import { api, type ApiUser } from '../../api/client';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

interface FormData {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
}

// -------------------- Helpers --------------------

const validatePassword = (password: string) => ({
  length: password.length >= 8,
  uppercase: /[A-Z]/.test(password),
  lowercase: /[a-z]/.test(password),
  number: /[0-9]/.test(password),
  special: /[!@#$%^&*(),.?":{}|<>_\-+=[\]\\;'/`~]/.test(password),
});

// -------------------- Component --------------------

const Register: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  
  const [form, setForm] = useState<FormData>({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [error, setError] = useState('');
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const updateField = (field: keyof FormData, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }));
    if (error) setError('');
  };

  const passwordChecks = validatePassword(form.password);
  const allPasswordValid = Object.values(passwordChecks).every(Boolean);
  const passwordsMatch = form.password === form.confirmPassword && form.confirmPassword.length > 0;

  const canSubmit = 
    form.fullName.trim().length >= 2 &&
    form.email.includes('@') &&
    allPasswordValid &&
    passwordsMatch &&
    agreedToTerms;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    const [firstName, ...lastNameParts] = form.fullName.trim().split(/\s+/);
    try {
      setLoading(true);
      const result = await api.post<{ access_token: string; user: ApiUser }>('/auth/register', {
        email: form.email,
        password: form.password,
        first_name: firstName,
        last_name: lastNameParts.join(' '),
      });
      login({
        id: result.user.id,
        email: result.user.email,
        firstName: result.user.first_name,
        lastName: result.user.last_name,
        role: result.user.role.name,
        organizationId: result.user.organization_id || undefined,
      }, result.access_token);
      navigate('/onboarding');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 via-white to-violet-50 flex">
      {/* Left Side - Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-primary-600 to-violet-600 p-12 flex-col justify-between relative overflow-hidden">
        {/* Background Pattern */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-72 h-72 bg-white rounded-full blur-3xl" />
          <div className="absolute bottom-20 right-20 w-96 h-96 bg-white rounded-full blur-3xl" />
        </div>
        
        <div className="relative">
          <img src={logoSvg} alt="CareSync" className="h-10 brightness-0 invert" />
        </div>
        
        <div className="relative space-y-8">
          <h1 className="text-4xl font-bold text-white leading-tight">
            Streamline your<br />childcare management
          </h1>
          <p className="text-xl text-white/80 max-w-md">
            Join hundreds of daycares using CareSync to manage families, 
            attendance, invoicing, and subsidy claims effortlessly.
          </p>
          
          {/* Feature Pills */}
          <div className="flex flex-wrap gap-3 pt-4">
            {['Family Management', 'Attendance Tracking', 'Invoicing', 'Subsidy Claims'].map((feature) => (
              <span key={feature} className="px-4 py-2 bg-white/10 backdrop-blur rounded-full text-white text-sm">
                {feature}
              </span>
            ))}
          </div>
        </div>

        <div className="relative text-white/60 text-sm">
          © 2024 CareSync. All rights reserved.
        </div>
      </div>

      {/* Right Side - Form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          {/* Mobile Logo */}
          <div className="lg:hidden text-center mb-8">
            <img src={logoSvg} alt="CareSync" className="h-10 mx-auto" />
          </div>

          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary-50 rounded-full text-primary-600 text-sm font-medium mb-4">
              <SparklesIcon className="w-4 h-4" />
              Free 14-day trial
            </div>
            <h2 className="text-3xl font-bold text-gray-900 mb-2">Create your account</h2>
            <p className="text-gray-600">
              Already have an account?{' '}
              <Link to="/login" className="text-primary-600 hover:text-primary-700 font-medium">
                Sign in
              </Link>
            </p>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Full Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Full Name
              </label>
              <input
                type="text"
                value={form.fullName}
                onChange={(e) => updateField('fullName', e.target.value)}
                onFocus={() => setFocusedField('fullName')}
                onBlur={() => setFocusedField(null)}
                placeholder="John Smith"
                className={`w-full px-4 py-3.5 bg-white border rounded-xl transition-all ${
                  focusedField === 'fullName'
                    ? 'border-primary-500 ring-4 ring-primary-500/10'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
              />
            </div>

            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Work Email
              </label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => updateField('email', e.target.value)}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                placeholder="john@sunnydayscare.com"
                className={`w-full px-4 py-3.5 bg-white border rounded-xl transition-all ${
                  focusedField === 'email'
                    ? 'border-primary-500 ring-4 ring-primary-500/10'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => updateField('password', e.target.value)}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  placeholder="Create a strong password"
                  className={`w-full px-4 py-3.5 bg-white border rounded-xl transition-all pr-12 ${
                    focusedField === 'password'
                      ? 'border-primary-500 ring-4 ring-primary-500/10'
                      : 'border-gray-300 hover:border-gray-400'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? <EyeSlashIcon className="w-5 h-5" /> : <EyeIcon className="w-5 h-5" />}
                </button>
              </div>
              
              {/* Password Strength Indicator */}
              {form.password && (
                <div className="mt-3 grid grid-cols-5 gap-2">
                  {Object.entries(passwordChecks).map(([key, valid]) => (
                    <div
                      key={key}
                      className={`h-1 rounded-full transition-colors ${
                        valid ? 'bg-green-500' : 'bg-gray-200'
                      }`}
                    />
                  ))}
                </div>
              )}
              
              {/* Password Requirements */}
              {form.password && !allPasswordValid && (
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
                  {[
                    { key: 'length', label: '8+ characters' },
                    { key: 'uppercase', label: 'Uppercase' },
                    { key: 'lowercase', label: 'Lowercase' },
                    { key: 'number', label: 'Number' },
                    { key: 'special', label: 'Special char' },
                  ].map(({ key, label }) => (
                    <div
                      key={key}
                      className={`flex items-center gap-1.5 text-xs ${
                        passwordChecks[key as keyof typeof passwordChecks]
                          ? 'text-green-600'
                          : 'text-gray-400'
                      }`}
                    >
                      <CheckCircleIcon className="w-3.5 h-3.5" />
                      {label}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Confirm Password */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Confirm Password
              </label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={form.confirmPassword}
                onChange={(e) => updateField('confirmPassword', e.target.value)}
                onFocus={() => setFocusedField('confirmPassword')}
                onBlur={() => setFocusedField(null)}
                placeholder="Confirm your password"
                className={`w-full px-4 py-3.5 bg-white border rounded-xl transition-all ${
                  focusedField === 'confirmPassword'
                    ? 'border-primary-500 ring-4 ring-primary-500/10'
                    : form.confirmPassword
                      ? passwordsMatch
                        ? 'border-green-500 bg-green-50/50'
                        : 'border-red-500 bg-red-50/50'
                      : 'border-gray-300 hover:border-gray-400'
                }`}
              />
              {form.confirmPassword && (
                <p className={`mt-1.5 text-xs flex items-center gap-1 ${passwordsMatch ? 'text-green-600' : 'text-red-500'}`}>
                  <CheckCircleIcon className="w-3.5 h-3.5" />
                  {passwordsMatch ? 'Passwords match' : 'Passwords do not match'}
                </p>
              )}
            </div>

            {/* Terms */}
            <label className="flex items-start gap-3 cursor-pointer group">
              <div className="relative mt-0.5">
                <input
                  type="checkbox"
                  checked={agreedToTerms}
                  onChange={(e) => setAgreedToTerms(e.target.checked)}
                  className="sr-only"
                />
                <div className={`w-5 h-5 rounded border-2 transition-all flex items-center justify-center ${
                  agreedToTerms
                    ? 'bg-primary-500 border-primary-500'
                    : 'border-gray-300 group-hover:border-gray-400'
                }`}>
                  {agreedToTerms && <CheckCircleIcon className="w-3.5 h-3.5 text-white" />}
                </div>
              </div>
              <span className="text-sm text-gray-600">
                I agree to the{' '}
                <Link to="/terms" className="text-primary-600 hover:underline">Terms of Service</Link>
                {' '}and{' '}
                <Link to="/privacy" className="text-primary-600 hover:underline">Privacy Policy</Link>
              </span>
            </label>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={!canSubmit || loading}
              className={`w-full py-4 rounded-xl font-semibold text-white transition-all flex items-center justify-center gap-2 ${
                canSubmit && !loading
                  ? 'bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-600 hover:to-primary-700 shadow-lg shadow-primary-500/30 hover:shadow-xl hover:shadow-primary-500/40'
                  : 'bg-gray-300 cursor-not-allowed'
              }`}
            >
              {loading ? (
                <>
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Creating account...
                </>
              ) : (
                <>
                  Get Started
                  <ArrowRightIcon className="w-5 h-5" />
                </>
              )}
            </button>
          </form>

          {/* Footer */}
          <p className="text-center text-xs text-gray-500 mt-8">
            By signing up, you agree to receive product updates and marketing emails.
            <br />You can unsubscribe at any time.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Register;
