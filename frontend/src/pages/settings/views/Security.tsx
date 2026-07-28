// ============================================
// Security Settings View (Refactored)
// ============================================

import React, { useState } from 'react';
import { KeyIcon, ShieldCheckIcon } from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';

// Types
import type { PasswordForm } from '../types';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  FormInput,
  PasswordStrengthIndicator,
  PasswordRequirements,
  PasswordMatchIndicator,
  InfoBanner,
} from '../components';

const Security: React.FC = () => {
  const { addNotification } = useNotifications();
  const [form, setForm] = useState<PasswordForm>({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [errors, setErrors] = useState<Partial<PasswordForm>>({});
  const [loading, setLoading] = useState(false);

  const validateForm = (): boolean => {
    const newErrors: Partial<PasswordForm> = {};

    if (!form.currentPassword) {
      newErrors.currentPassword = 'Current password is required';
    }
    if (!form.newPassword) {
      newErrors.newPassword = 'New password is required';
    } else if (form.newPassword.length < 8) {
      newErrors.newPassword = 'Password must be at least 8 characters';
    }
    if (!form.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your new password';
    } else if (form.newPassword !== form.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }
    if (form.currentPassword && form.newPassword && form.currentPassword === form.newPassword) {
      newErrors.newPassword = 'New password must be different from current password';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    try {
      setLoading(true);
      await api.post('/auth/change-password', {
        current_password: form.currentPassword,
        new_password: form.newPassword,
      });
      setForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
      setErrors({});
      addNotification({ type: 'success', title: 'Password Changed', message: 'Your password has been updated successfully.' });
    } catch (error) {
      addNotification({ type: 'error', title: 'Password Change Failed', message: error instanceof Error ? error.message : 'Request failed' });
    } finally {
      setLoading(false);
    }
  };

  const showMatchIndicator =
    form.confirmPassword && form.newPassword === form.confirmPassword && !errors.confirmPassword;

  return (
    <SettingsPageLayout
      title="Security Settings"
      description="Manage your account security and password."
      maxWidth="2xl"
    >
      <SettingsSection title="Change Password" icon={KeyIcon}>
        <form onSubmit={handleSubmit} className="space-y-6">
          <FormInput
            label="Current Password"
            type="password"
            value={form.currentPassword}
            onChange={(e) => setForm({ ...form, currentPassword: e.target.value })}
            error={errors.currentPassword}
            placeholder="Enter your current password"
          />

          <div>
            <FormInput
              label="New Password"
              type="password"
              value={form.newPassword}
              onChange={(e) => setForm({ ...form, newPassword: e.target.value })}
              error={errors.newPassword}
              placeholder="Enter new password"
            />
            <PasswordStrengthIndicator password={form.newPassword} />
          </div>

          <div>
            <FormInput
              label="Confirm New Password"
              type="password"
              value={form.confirmPassword}
              onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })}
              error={errors.confirmPassword}
              placeholder="Confirm new password"
            />
            {showMatchIndicator && <PasswordMatchIndicator isMatch={true} />}
          </div>

          <PasswordRequirements password={form.newPassword} />

          <div className="flex justify-end pt-4 border-t border-gray-200">
            <button type="submit" disabled={loading} className="btn btn-primary">
              {loading ? 'Changing Password...' : 'Change Password'}
            </button>
          </div>
        </form>
      </SettingsSection>

      <InfoBanner
        icon={ShieldCheckIcon}
        title="Security Tips"
        className="mt-8"
      >
        <ul className="mt-2 space-y-1">
          <li>• Never share your password with anyone</li>
          <li>• Use a unique password for each account</li>
          <li>• Change your password regularly</li>
          <li>• Enable two-factor authentication when available</li>
        </ul>
      </InfoBanner>
    </SettingsPageLayout>
  );
};

export default Security;
