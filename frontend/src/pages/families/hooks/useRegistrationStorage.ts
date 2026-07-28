// ============================================
// Registration Storage Hook
// Persists registration progress to localStorage
// ============================================

import { useState, useEffect, useCallback } from 'react';
import type { RegistrationData } from '../registration/types';
import { createInitialData } from '../registration/helpers';

const STORAGE_KEY = 'family_registration_draft';
const STORAGE_STEP_KEY = 'family_registration_step';
const STORAGE_TIMESTAMP_KEY = 'family_registration_timestamp';

// Auto-expire drafts after 24 hours
const DRAFT_EXPIRY_MS = 24 * 60 * 60 * 1000;

interface UseRegistrationStorageResult {
  data: RegistrationData;
  currentStep: number;
  setData: (data: RegistrationData | ((prev: RegistrationData) => RegistrationData)) => void;
  setCurrentStep: (step: number) => void;
  clearStorage: () => void;
  hasSavedDraft: boolean;
  lastSaved: Date | null;
}

export const useRegistrationStorage = (): UseRegistrationStorageResult => {
  const [data, setDataState] = useState<RegistrationData>(createInitialData);
  const [currentStep, setCurrentStepState] = useState(0);
  const [hasSavedDraft, setHasSavedDraft] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const storedDataStr = localStorage.getItem(STORAGE_KEY);
      const storedStepStr = localStorage.getItem(STORAGE_STEP_KEY);
      const storedTimestamp = localStorage.getItem(STORAGE_TIMESTAMP_KEY);

      if (storedDataStr && storedTimestamp) {
        const timestamp = parseInt(storedTimestamp, 10);
        const now = Date.now();

        // Check if draft has expired
        if (now - timestamp > DRAFT_EXPIRY_MS) {
          // Clear expired draft
          localStorage.removeItem(STORAGE_KEY);
          localStorage.removeItem(STORAGE_STEP_KEY);
          localStorage.removeItem(STORAGE_TIMESTAMP_KEY);
        } else {
          const storedData = JSON.parse(storedDataStr) as RegistrationData;
          const storedStep = storedStepStr ? parseInt(storedStepStr, 10) : 0;

          setDataState(storedData);
          setCurrentStepState(storedStep);
          setHasSavedDraft(true);
          setLastSaved(new Date(timestamp));
        }
      }
    } catch (error) {
      console.error('Error loading registration draft:', error);
      // Clear corrupted data
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_STEP_KEY);
      localStorage.removeItem(STORAGE_TIMESTAMP_KEY);
    }
    
    setInitialized(true);
  }, []);

  // Save to localStorage whenever data or step changes
  useEffect(() => {
    if (!initialized) return;

    try {
      const timestamp = Date.now();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      localStorage.setItem(STORAGE_STEP_KEY, currentStep.toString());
      localStorage.setItem(STORAGE_TIMESTAMP_KEY, timestamp.toString());
      setLastSaved(new Date(timestamp));
      setHasSavedDraft(true);
    } catch (error) {
      console.error('Error saving registration draft:', error);
    }
  }, [data, currentStep, initialized]);

  // Setter that mimics useState
  const setData = useCallback((
    update: RegistrationData | ((prev: RegistrationData) => RegistrationData)
  ) => {
    if (typeof update === 'function') {
      setDataState(prev => update(prev));
    } else {
      setDataState(update);
    }
  }, []);

  const setCurrentStep = useCallback((step: number) => {
    setCurrentStepState(step);
  }, []);

  const clearStorage = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_STEP_KEY);
    localStorage.removeItem(STORAGE_TIMESTAMP_KEY);
    setDataState(createInitialData());
    setCurrentStepState(0);
    setHasSavedDraft(false);
    setLastSaved(null);
  }, []);

  return {
    data,
    currentStep,
    setData,
    setCurrentStep,
    clearStorage,
    hasSavedDraft,
    lastSaved,
  };
};

export default useRegistrationStorage;
