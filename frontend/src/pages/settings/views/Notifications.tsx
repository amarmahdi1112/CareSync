// ============================================
// Notification Settings View (Refactored)
// ============================================

import React, { useState, useEffect } from 'react';
import {
  BellIcon,
  EnvelopeIcon,
  DevicePhoneMobileIcon,
  ComputerDesktopIcon,
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { NotificationPreferences, NotificationCategory } from '../types';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  CheckboxItem,
  SettingsLoadingSpinner,
  UnsavedChangesWarning,
  InfoBanner,
} from '../components';

// Constants
import { DEFAULT_NOTIFICATION_CATEGORIES } from '../constants';

interface BackendNotificationPreferences {
  attendance?: Record<string, { email: boolean; push: boolean; sms: boolean }>;
  billing?: Record<string, { email: boolean; push: boolean; sms: boolean }>;
  families?: Record<string, { email: boolean; push: boolean; sms: boolean }>;
  system?: Record<string, { email: boolean; push: boolean; sms: boolean }>;
}

interface OrganizationPreferences {
  id: string;
  notification_preferences: BackendNotificationPreferences | null;
}

const Notifications: React.FC = () => {
  const { addNotification } = useNotifications();
  const [preferences, setPreferences] = useState<NotificationPreferences>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);

  const { data, loading } = useApiQuery<OrganizationPreferences>('/organization');

  useEffect(() => {
    if (data?.notification_preferences) {
      const prefs = data.notification_preferences;
      const transformed: NotificationPreferences = {};

      for (const category of DEFAULT_NOTIFICATION_CATEGORIES) {
        const categoryPrefs = prefs[category.id as keyof BackendNotificationPreferences];
        if (categoryPrefs) {
          transformed[category.id] = {};
          for (const setting of category.settings) {
            transformed[category.id][setting.id] = categoryPrefs[setting.id] || { email: setting.email, push: setting.push, sms: setting.sms };
          }
        }
      }

      if (Object.keys(transformed).length > 0) {
        setPreferences(transformed);
      } else {
        initDefaults();
      }
    } else {
      initDefaults();
    }
  }, [data]);

  const initDefaults = () => {
    const defaults: NotificationPreferences = {};
    DEFAULT_NOTIFICATION_CATEGORIES.forEach((category) => {
      defaults[category.id] = {};
      category.settings.forEach((setting) => {
        defaults[category.id][setting.id] = { email: setting.email, push: setting.push, sms: setting.sms };
      });
    });
    setPreferences(defaults);
  };

  const getPreference = (categoryId: string, settingId: string, channel: 'email' | 'push' | 'sms'): boolean => {
    return preferences[categoryId]?.[settingId]?.[channel] ?? false;
  };

  const togglePreference = (categoryId: string, settingId: string, channel: 'email' | 'push' | 'sms') => {
    setPreferences((prev) => ({
      ...prev,
      [categoryId]: {
        ...prev[categoryId],
        [settingId]: {
          ...prev[categoryId]?.[settingId],
          [channel]: !getPreference(categoryId, settingId, channel),
        },
      },
    }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.patch('/organization/preferences/notification', preferences);
      setHasChanges(false);
      addNotification({ type: 'success', title: 'Preferences Saved', message: 'Your notification preferences have been updated.' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Save Failed', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    initDefaults();
    setHasChanges(true);
  };

  if (loading) {
    return (
      <SettingsPageLayout title="Notification Preferences" description="Loading...">
        <SettingsLoadingSpinner />
      </SettingsPageLayout>
    );
  }

  return (
    <SettingsPageLayout
      title="Notification Preferences"
      description="Choose how you want to be notified about important events."
      actions={
        <>
          <button onClick={handleReset} className="btn btn-secondary">Reset to Defaults</button>
          <button onClick={handleSave} disabled={!hasChanges || saving} className="btn btn-primary">
            {saving ? 'Saving...' : 'Save Preferences'}
          </button>
        </>
      }
    >
      {/* Channel Legend */}
      <div className="bg-gray-50 rounded-xl p-4 mb-6 border border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <BellIcon className="h-5 w-5" />
            <span className="font-medium">Notification Channels:</span>
          </div>
          <div className="flex items-center gap-6">
            <ChannelLabel icon={EnvelopeIcon} label="Email" />
            <ChannelLabel icon={ComputerDesktopIcon} label="Push" />
            <ChannelLabel icon={DevicePhoneMobileIcon} label="SMS" />
          </div>
        </div>
      </div>

      {/* Notification Categories */}
      <div className="space-y-6">
        {DEFAULT_NOTIFICATION_CATEGORIES.map((category) => (
          <NotificationCategorySection
            key={category.id}
            category={category}
            getPreference={getPreference}
            togglePreference={togglePreference}
          />
        ))}
      </div>

      <InfoBanner icon={BellIcon} title="About Notifications" className="mt-8">
        <p>
          Email notifications are sent to your registered email address.
          Push notifications require browser permissions.
          SMS notifications may incur additional charges depending on your subscription plan.
        </p>
      </InfoBanner>

      <UnsavedChangesWarning show={hasChanges} onSave={handleSave} saving={saving} />
    </SettingsPageLayout>
  );
};

// -------------------- Sub-components --------------------

const ChannelLabel: React.FC<{ icon: React.ElementType; label: string }> = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 text-sm">
    <Icon className="h-4 w-4 text-gray-500" />
    <span>{label}</span>
  </div>
);

interface NotificationCategorySectionProps {
  category: NotificationCategory;
  getPreference: (categoryId: string, settingId: string, channel: 'email' | 'push' | 'sms') => boolean;
  togglePreference: (categoryId: string, settingId: string, channel: 'email' | 'push' | 'sms') => void;
}

const NotificationCategorySection: React.FC<NotificationCategorySectionProps> = ({
  category,
  getPreference,
  togglePreference,
}) => (
  <SettingsSection title={category.name} icon={category.icon} description={category.description} noPadding>
    <div className="divide-y divide-gray-100">
      {category.settings.map((setting) => (
        <div key={setting.id} className="px-6 py-4 flex items-center justify-between">
          <div className="flex-1 pr-8">
            <p className="font-medium text-gray-900">{setting.label}</p>
            <p className="text-sm text-gray-500">{setting.description}</p>
          </div>
          <div className="flex items-center gap-6">
            <CheckboxItem
              checked={getPreference(category.id, setting.id, 'email')}
              onChange={() => togglePreference(category.id, setting.id, 'email')}
              label=""
              icon={EnvelopeIcon}
            />
            <CheckboxItem
              checked={getPreference(category.id, setting.id, 'push')}
              onChange={() => togglePreference(category.id, setting.id, 'push')}
              label=""
              icon={ComputerDesktopIcon}
            />
            <CheckboxItem
              checked={getPreference(category.id, setting.id, 'sms')}
              onChange={() => togglePreference(category.id, setting.id, 'sms')}
              label=""
              icon={DevicePhoneMobileIcon}
            />
          </div>
        </div>
      ))}
    </div>
  </SettingsSection>
);

export default Notifications;
