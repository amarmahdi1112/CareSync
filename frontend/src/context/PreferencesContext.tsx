// ============================================
// Preferences Context
// Provides system preferences (time format, date format, etc.) across the app
// ============================================

import React, { createContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useApiQuery } from '../api/hooks';

export interface SystemPreferences {
  timeFormat: '12h' | '24h';
  dateFormat: string;
  timezone: string;
  language: string;
  currency: string;
  weekStartsOn: 'sunday' | 'monday';
}

const DEFAULT_PREFERENCES: SystemPreferences = {
  timeFormat: '12h',
  dateFormat: 'MM/DD/YYYY',
  timezone: 'America/Edmonton',
  language: 'en',
  currency: 'CAD',
  weekStartsOn: 'sunday',
};

interface PreferencesContextType {
  preferences: SystemPreferences;
  loading: boolean;
}

const PreferencesContext = createContext<PreferencesContextType>({
  preferences: DEFAULT_PREFERENCES,
  loading: true,
});

interface BackendSystemPreferences {
  theme?: string;
  date_format?: string;
  time_format?: string;
  language?: string;
  currency?: string;
  week_starts_on?: string;
}

interface OrganizationPreferences {
  id: string;
  timezone?: string;
  system_preferences: BackendSystemPreferences | null;
}

export const PreferencesProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [preferences, setPreferences] = useState<SystemPreferences>(DEFAULT_PREFERENCES);
  
  const { data: organization, loading } = useApiQuery<OrganizationPreferences>(
    '/organization',
    undefined,
    Boolean(localStorage.getItem('token')),
  );

  useEffect(() => {
    if (organization) {
      const prefs = organization.system_preferences;
      setPreferences({
        timeFormat: (prefs?.time_format as '12h' | '24h') || '12h',
        dateFormat: prefs?.date_format || 'MM/DD/YYYY',
        timezone: organization.timezone || 'America/Edmonton',
        language: prefs?.language || 'en',
        currency: prefs?.currency || 'CAD',
        weekStartsOn: (prefs?.week_starts_on as 'sunday' | 'monday') || 'sunday',
      });
    }
  }, [organization]);

  return (
    <PreferencesContext.Provider value={{ preferences, loading }}>
      {children}
    </PreferencesContext.Provider>
  );
};

export default PreferencesContext;
