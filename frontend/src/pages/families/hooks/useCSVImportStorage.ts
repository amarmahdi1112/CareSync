// ============================================
// CSV Import Storage Hook
// Persists import progress to localStorage
// ============================================

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'csv_import_draft';
const STORAGE_TIMESTAMP_KEY = 'csv_import_timestamp';

// Auto-expire drafts after 1 hour (CSV imports are usually done in one session)
const DRAFT_EXPIRY_MS = 60 * 60 * 1000;

interface SiblingMatch {
  id: string;
  familyIndices: number[];
  familyNames: string[];
  childNames: string[];
  confidenceScore: number;
  evidence: string[];
}

interface ParsedChild {
  firstName: string;
  middleName?: string;
  lastName: string;
  dateOfBirth: string;
}

interface ParsedGuardian {
  firstName: string;
  lastName: string;
  phone: string;
  email: string;
  relationship: string;
}

interface ParsedFamily {
  familyKey: string;
  familyName: string;
  address: string;
  primaryGuardian: ParsedGuardian;
  children: ParsedChild[];
}

interface DetectionResult {
  families: ParsedFamily[];
  siblingMatches: SiblingMatch[];
  warnings: string[];
}

type StepType = 'upload' | 'review' | 'result';

interface CSVImportState {
  csvContent: string;
  fileName: string;
  detectionResult: DetectionResult | null;
  approvedMerges: number[][];
  dismissedMatches: string[];
  step: StepType;
}

interface UseCSVImportStorageResult {
  state: CSVImportState;
  setState: (update: Partial<CSVImportState>) => void;
  clearStorage: () => void;
  hasSavedDraft: boolean;
}

const initialState: CSVImportState = {
  csvContent: '',
  fileName: '',
  detectionResult: null,
  approvedMerges: [],
  dismissedMatches: [],
  step: 'upload',
};

export const useCSVImportStorage = (): UseCSVImportStorageResult => {
  const [state, setStateInternal] = useState<CSVImportState>(initialState);
  const [hasSavedDraft, setHasSavedDraft] = useState(false);
  const [initialized, setInitialized] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const storedDataStr = localStorage.getItem(STORAGE_KEY);
      const storedTimestamp = localStorage.getItem(STORAGE_TIMESTAMP_KEY);

      if (storedDataStr && storedTimestamp) {
        const timestamp = parseInt(storedTimestamp, 10);
        const now = Date.now();

        // Check if draft has expired
        if (now - timestamp > DRAFT_EXPIRY_MS) {
          localStorage.removeItem(STORAGE_KEY);
          localStorage.removeItem(STORAGE_TIMESTAMP_KEY);
        } else {
          const storedData = JSON.parse(storedDataStr) as CSVImportState;
          // Only restore if we're in the review step (upload step doesn't need persistence)
          if (storedData.step === 'review' && storedData.detectionResult) {
            setStateInternal(storedData);
            setHasSavedDraft(true);
          }
        }
      }
    } catch (error) {
      console.error('Error loading CSV import draft:', error);
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_TIMESTAMP_KEY);
    }
    
    setInitialized(true);
  }, []);

  // Save to localStorage whenever state changes (only in review step)
  useEffect(() => {
    if (!initialized) return;

    // Only persist if we have detection results and are in review step
    if (state.step === 'review' && state.detectionResult) {
      try {
        const timestamp = Date.now();
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        localStorage.setItem(STORAGE_TIMESTAMP_KEY, timestamp.toString());
        setHasSavedDraft(true);
      } catch (error) {
        console.error('Error saving CSV import draft:', error);
      }
    }
  }, [state, initialized]);

  const setState = useCallback((update: Partial<CSVImportState>) => {
    setStateInternal(prev => ({ ...prev, ...update }));
  }, []);

  const clearStorage = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_TIMESTAMP_KEY);
    setStateInternal(initialState);
    setHasSavedDraft(false);
  }, []);

  return {
    state,
    setState,
    clearStorage,
    hasSavedDraft,
  };
};

export default useCSVImportStorage;
