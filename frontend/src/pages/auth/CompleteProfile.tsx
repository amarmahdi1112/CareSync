// ============================================
// Complete Profile Page
// For users who need to fill in missing profile data
// ============================================

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UserIcon,
  CheckCircleIcon,
  ArrowRightIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../context/AuthContext';
import { api, type ApiUser } from '../../api/client';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

interface UserProfileData {
  firstName: string;
  lastName: string;
  phone?: string;
}

const CompleteProfile: React.FC = () => {
  const navigate = useNavigate();
  const { state: authState, setUser } = useAuth();
  const [data, setData] = useState<UserProfileData>({
    firstName: authState.user?.firstName || '',
    lastName: authState.user?.lastName || '',
    phone: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const updateField = (field: keyof UserProfileData, value: string) => {
    setData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    if (!data.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    }
    if (!data.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validate()) return;
    
    setSaveError(null);
    
    try {
      setLoading(true);
      const updated = await api.patch<ApiUser>('/auth/me', {
        first_name: data.firstName.trim(),
        last_name: data.lastName.trim(),
      });
      setUser({
        ...authState.user!,
        email: updated.email,
        firstName: updated.first_name,
        lastName: updated.last_name,
        role: updated.role.name,
      });
      navigate('/dashboard');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-primary-50/30 flex flex-col">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-xl border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-center">
          <img src={logoSvg} alt="CareSync" className="h-8" />
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          {/* Icon */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-violet-500 shadow-xl shadow-primary-500/30 mb-4">
              <UserIcon className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Complete Your Profile</h1>
            <p className="text-gray-600">Please provide your name to continue</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-xl shadow-gray-200/50 p-8">
            <div className="space-y-5">
              {/* First Name */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  First Name *
                </label>
                <input
                  type="text"
                  value={data.firstName}
                  onChange={(e) => updateField('firstName', e.target.value)}
                  placeholder="Enter your first name"
                  className={`w-full px-4 py-3 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
                    errors.firstName ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
                  }`}
                />
                {errors.firstName && (
                  <p className="text-red-500 text-sm mt-1">{errors.firstName}</p>
                )}
              </div>

              {/* Last Name */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Last Name *
                </label>
                <input
                  type="text"
                  value={data.lastName}
                  onChange={(e) => updateField('lastName', e.target.value)}
                  placeholder="Enter your last name"
                  className={`w-full px-4 py-3 bg-white border-2 rounded-xl transition-all focus:ring-4 focus:ring-primary-500/20 ${
                    errors.lastName ? 'border-red-500' : 'border-gray-200 focus:border-primary-500'
                  }`}
                />
                {errors.lastName && (
                  <p className="text-red-500 text-sm mt-1">{errors.lastName}</p>
                )}
              </div>
            </div>

            {/* Error Message */}
            {saveError && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
                <ExclamationCircleIcon className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-red-600">{saveError}</p>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className={`w-full mt-6 flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-primary-500 to-primary-600 text-white font-semibold rounded-xl transition-all shadow-lg shadow-primary-500/30 ${
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
                  Continue to Dashboard
                  <ArrowRightIcon className="w-5 h-5" />
                </>
              )}
            </button>
          </form>

          {/* Info */}
          <p className="text-center text-sm text-gray-500 mt-6">
            Your profile information helps us personalize your experience
          </p>
        </div>
      </main>
    </div>
  );
};

export default CompleteProfile;
