// ============================================
// System Settings View (Refactored)
// ============================================

import React, { useState, useEffect } from 'react';
import {
  SunIcon,
  MoonIcon,
  ComputerDesktopIcon,
  GlobeAltIcon,
  ClockIcon,
  CalendarIcon,
  LanguageIcon,
  CurrencyDollarIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { SystemPreferences } from '../types';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  ToggleSwitch,
  FormSelect,
  RadioGroup,
  SettingsLoadingSpinner,
  UnsavedChangesWarning,
  InfoBanner,
} from '../components';

// Constants
import {
  TIMEZONES,
  DATE_FORMATS,
  LANGUAGES,
  CURRENCIES,
  DEFAULT_SYSTEM_PREFERENCES,
} from '../constants';

interface BackendSystemPreferences {
  theme?: string;
  date_format?: string;
  time_format?: string;
  language?: string;
  currency?: string;
  week_starts_on?: string;
  compact_mode?: boolean;
  animations_enabled?: boolean;
}

interface OrganizationPreferences {
  id: string;
  timezone?: string;
  system_preferences: BackendSystemPreferences | null;
}

const System: React.FC = () => {
  const { addNotification } = useNotifications();
  const [preferences, setPreferences] = useState<SystemPreferences>(DEFAULT_SYSTEM_PREFERENCES);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);

  const { data, loading } = useApiQuery<OrganizationPreferences>('/organization');

  useEffect(() => {
    if (data?.system_preferences) {
      const prefs = data.system_preferences;
      setPreferences({
        theme: (prefs.theme as 'light' | 'dark' | 'system') || 'light',
        timezone: data.timezone || 'America/New_York',
        dateFormat: prefs.date_format || 'MM/DD/YYYY',
        timeFormat: (prefs.time_format as '12h' | '24h') || '12h',
        language: prefs.language || 'en',
        currency: prefs.currency || 'USD',
        weekStartsOn: (prefs.week_starts_on as 'sunday' | 'monday') || 'sunday',
        compactMode: prefs.compact_mode ?? false,
        animationsEnabled: prefs.animations_enabled ?? true,
      });
    }
  }, [data]);

  const updatePref = <K extends keyof SystemPreferences>(key: K, value: SystemPreferences[K]) => {
    setPreferences((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await Promise.all([
        api.patch('/organization/preferences/system', {
          theme: preferences.theme,
          date_format: preferences.dateFormat,
          time_format: preferences.timeFormat,
          language: preferences.language,
          currency: preferences.currency,
          week_starts_on: preferences.weekStartsOn,
          compact_mode: preferences.compactMode,
          animations_enabled: preferences.animationsEnabled,
        }),
        api.patch('/organization', { timezone: preferences.timezone }),
      ]);
      setHasChanges(false);
      addNotification({ type: 'success', title: 'Preferences Saved', message: 'Your system preferences have been updated.' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Save Failed', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setPreferences(DEFAULT_SYSTEM_PREFERENCES);
    setHasChanges(true);
  };

  if (loading) {
    return (
      <SettingsPageLayout title="System Preferences" description="Loading...">
        <SettingsLoadingSpinner />
      </SettingsPageLayout>
    );
  }

  return (
    <SettingsPageLayout
      title="System Preferences"
      description="Customize your display, regional settings, and app behavior."
      actions={
        <>
          <button onClick={handleReset} className="btn btn-secondary">Reset to Defaults</button>
          <button onClick={handleSave} disabled={!hasChanges || saving} className="btn btn-primary">
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </>
      }
    >
      {/* Appearance */}
      <SettingsSection title="Appearance" icon={Cog6ToothIcon} className="mb-6">
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-3">Theme</label>
          <div className="grid grid-cols-3 gap-4">
            <ThemeButton theme="light" current={preferences.theme} onChange={(t) => updatePref('theme', t)} icon={SunIcon} label="Light" />
            <ThemeButton theme="dark" current={preferences.theme} onChange={(t) => updatePref('theme', t)} icon={MoonIcon} label="Dark" isDark />
            <ThemeButton theme="system" current={preferences.theme} onChange={(t) => updatePref('theme', t)} icon={ComputerDesktopIcon} label="System" isGradient />
          </div>
          <p className="mt-2 text-xs text-gray-500">Dark mode coming soon. Currently only light mode is available.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-6 border-t border-gray-200">
          <ToggleSwitch enabled={preferences.compactMode} onChange={(v) => updatePref('compactMode', v)} label="Compact Mode" description="Reduce spacing for more content" />
          <ToggleSwitch enabled={preferences.animationsEnabled} onChange={(v) => updatePref('animationsEnabled', v)} label="Animations" description="Enable interface animations" />
        </div>
      </SettingsSection>

      {/* Regional Settings */}
      <SettingsSection title="Regional Settings" icon={GlobeAltIcon} className="mb-6">
        <div className="space-y-6">
          <FormSelect label="Timezone" icon={ClockIcon} value={preferences.timezone} onChange={(e) => updatePref('timezone', e.target.value)} options={TIMEZONES} />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <FormSelect label="Date Format" icon={CalendarIcon} value={preferences.dateFormat} onChange={(e) => updatePref('dateFormat', e.target.value)} options={DATE_FORMATS} />
            <RadioGroup name="timeFormat" label="Time Format" value={preferences.timeFormat} onChange={(v) => updatePref('timeFormat', v as '12h' | '24h')} options={[
              { value: '12h', label: '12-hour (3:00 PM)' },
              { value: '24h', label: '24-hour (15:00)' },
            ]} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <FormSelect label="Language" icon={LanguageIcon} value={preferences.language} onChange={(e) => updatePref('language', e.target.value)} options={LANGUAGES} hint="Additional languages coming soon." />
            </div>
            <FormSelect label="Currency" icon={CurrencyDollarIcon} value={preferences.currency} onChange={(e) => updatePref('currency', e.target.value)} options={CURRENCIES} />
          </div>

          <RadioGroup name="weekStartsOn" label="Week Starts On" value={preferences.weekStartsOn} onChange={(v) => updatePref('weekStartsOn', v as 'sunday' | 'monday')} options={[
            { value: 'sunday', label: 'Sunday' },
            { value: 'monday', label: 'Monday' },
          ]} />
        </div>
      </SettingsSection>

      {/* Preview */}
      <InfoBanner title="Preview" variant="info">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-2">
          <div>
            <p className="text-blue-600">Date</p>
            <p className="font-medium text-blue-900">{new Date().toLocaleDateString('en-US', { year: 'numeric', month: preferences.dateFormat.includes('MMM') ? 'short' : '2-digit', day: '2-digit' })}</p>
          </div>
          <div>
            <p className="text-blue-600">Time</p>
            <p className="font-medium text-blue-900">{new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: preferences.timeFormat === '12h' })}</p>
          </div>
          <div>
            <p className="text-blue-600">Currency</p>
            <p className="font-medium text-blue-900">{new Intl.NumberFormat('en-US', { style: 'currency', currency: preferences.currency }).format(1234.56)}</p>
          </div>
          <div>
            <p className="text-blue-600">Timezone</p>
            <p className="font-medium text-blue-900">{TIMEZONES.find((tz) => tz.value === preferences.timezone)?.label.split(' (')[0] || preferences.timezone}</p>
          </div>
        </div>
      </InfoBanner>

      <UnsavedChangesWarning show={hasChanges} onSave={handleSave} saving={saving} />
    </SettingsPageLayout>
  );
};

// -------------------- Theme Button Component --------------------

interface ThemeButtonProps {
  theme: 'light' | 'dark' | 'system';
  current: string;
  onChange: (theme: 'light' | 'dark' | 'system') => void;
  icon: React.ElementType;
  label: string;
  isDark?: boolean;
  isGradient?: boolean;
}

const ThemeButton: React.FC<ThemeButtonProps> = ({ theme, current, onChange, icon: Icon, label, isDark, isGradient }) => (
  <button
    onClick={() => onChange(theme)}
    className={`p-4 border-2 rounded-xl transition-all ${current === theme ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:border-gray-300'}`}
  >
    <div className="flex flex-col items-center gap-2">
      <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${isDark ? 'bg-gray-800' : isGradient ? 'bg-gradient-to-br from-white to-gray-800 border border-gray-200' : 'bg-white border border-gray-200 shadow-sm'}`}>
        <Icon className={`h-6 w-6 ${isDark ? 'text-gray-200' : theme === 'light' ? 'text-yellow-500' : 'text-gray-600'}`} />
      </div>
      <span className="text-sm font-medium text-gray-900">{label}</span>
    </div>
  </button>
);

export default System;
