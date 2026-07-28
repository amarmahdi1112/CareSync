// ============================================
// Preferences Hooks
// Shortcut hooks for accessing system preferences
// ============================================

import { useContext } from 'react';
import PreferencesContext from '../context/PreferencesContext';

export const usePreferences = () => useContext(PreferencesContext);

// Shortcut hooks for common preferences
export const useTimeFormat = () => usePreferences().preferences.timeFormat;
export const useDateFormat = () => usePreferences().preferences.dateFormat;
