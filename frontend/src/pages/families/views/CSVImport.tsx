// ============================================
// CSV Import View - Completely Redesigned
// ============================================

import React, { useState, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { 
  ArrowUpTrayIcon, 
  DocumentTextIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ArrowLeftIcon,
  UserGroupIcon,
  ArrowRightIcon,
  SparklesIcon,
  CheckIcon,
  XMarkIcon,
  CloudArrowUpIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../stores';
import { useCSVImportStorage } from '../hooks';
import { api } from '../../../api/client';

// -------------------- Types --------------------

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

interface SiblingMatch {
  id: string;
  familyIndices: number[];
  familyNames: string[];
  childNames: string[];
  confidenceScore: number;
  evidence: string[];
}

interface DetectionResult {
  families: ParsedFamily[];
  siblingMatches: SiblingMatch[];
  warnings: string[];
}

interface ImportResult {
  success: boolean;
  totalRows: number;
  familiesCreated: number;
  childrenCreated: number;
  familiesSkipped: number;
  childrenSkipped: number;
  errors: { row: number; childName: string; message: string }[];
  skippedReasons: string[];
}

type StepType = 'upload' | 'review' | 'result';

// -------------------- Step Indicator Component --------------------

interface StepIndicatorProps {
  currentStep: StepType;
}

const steps = [
  { key: 'upload' as StepType, label: 'Upload File', icon: CloudArrowUpIcon },
  { key: 'review' as StepType, label: 'Review Siblings', icon: UserGroupIcon },
  { key: 'result' as StepType, label: 'Complete', icon: CheckCircleIcon },
];

const StepIndicator: React.FC<StepIndicatorProps> = ({ currentStep }) => {
  const currentIndex = steps.findIndex(s => s.key === currentStep);
  
  return (
    <div className="flex items-center justify-center gap-3">
      {steps.map((step, index) => {
        const Icon = step.icon;
        const isActive = step.key === currentStep;
        const isCompleted = index < currentIndex;
        
        return (
          <React.Fragment key={step.key}>
            <div className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
              isActive 
                ? 'bg-primary-100 text-primary-700' 
                : isCompleted 
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-400'
            }`}>
              {isCompleted ? (
                <CheckIcon className="w-5 h-5" />
              ) : (
                <Icon className="w-5 h-5" />
              )}
              <span className="font-medium text-sm hidden sm:inline">{step.label}</span>
            </div>
            {index < steps.length - 1 && (
              <div className={`w-8 h-0.5 ${index < currentIndex ? 'bg-green-300' : 'bg-gray-200'}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};

// -------------------- Confidence Badge --------------------

const ConfidenceBadge: React.FC<{ score: number }> = ({ score }) => {
  const colors = score >= 70 
    ? 'bg-green-100 text-green-700 border-green-200' 
    : score >= 40 
    ? 'bg-amber-100 text-amber-700 border-amber-200'
    : 'bg-gray-100 text-gray-600 border-gray-200';
  
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${colors}`}>
      {score}% match
    </span>
  );
};

// -------------------- Sibling Match Card --------------------

interface SiblingMatchCardProps {
  match: SiblingMatch;
  onApprove: () => void;
  onDismiss: () => void;
}

const SiblingMatchCard: React.FC<SiblingMatchCardProps> = ({ match, onApprove, onDismiss }) => (
  <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md hover:border-primary-300 transition-all">
    <div className="flex items-start justify-between gap-4">
      <div className="flex-1">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-primary-100 flex items-center justify-center">
            <UserGroupIcon className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <h4 className="font-semibold text-gray-900">
              {match.familyNames.join(' + ')}
            </h4>
            <ConfidenceBadge score={match.confidenceScore} />
          </div>
        </div>
        
        <div className="mb-3">
          <p className="text-sm text-gray-500 mb-1">Children to merge:</p>
          <p className="text-sm font-medium text-gray-700">
            {match.childNames.join(', ')}
          </p>
        </div>
        
        <div className="flex flex-wrap gap-1.5">
          {match.evidence.map((e, i) => (
            <span key={i} className="px-2 py-1 bg-blue-50 text-blue-600 rounded-lg text-xs font-medium">
              {e}
            </span>
          ))}
        </div>
      </div>
      
      <div className="flex flex-col gap-2">
        <button 
          onClick={onApprove}
          className="btn btn-primary btn-sm whitespace-nowrap"
        >
          <CheckIcon className="w-4 h-4" />
          Merge
        </button>
        <button 
          onClick={onDismiss}
          className="btn btn-secondary btn-sm whitespace-nowrap"
        >
          <XMarkIcon className="w-4 h-4" />
          Keep Separate
        </button>
      </div>
    </div>
  </div>
);

// -------------------- Main Component --------------------

const CSVImport: React.FC = () => {
  const navigate = useNavigate();
  const { success, error: showError } = useNotificationStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Persisted state
  const { state, setState, clearStorage } = useCSVImportStorage();
  const { csvContent, fileName, detectionResult, approvedMerges, dismissedMatches, step } = state;
  
  // Local state (not persisted)
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [deleteExisting, setDeleteExisting] = useState(false);
  const [detectLoading, setDetectLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [directLoading, setDirectLoading] = useState(false);
  
  // Convert dismissedMatches array to Set for easier operations
  const dismissedSet = new Set(dismissedMatches);
  
  // File handlers
  const handleFileSelect = (file: File) => {
    setState({ fileName: file.name });
    const reader = new FileReader();
    reader.onload = (e) => setState({ csvContent: e.target?.result as string });
    reader.readAsText(file);
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.name.endsWith('.csv')) {
      handleFileSelect(file);
    } else {
      showError('Invalid File', 'Please upload a CSV file.');
    }
  };
  
  // Upload and detect
  const handleUploadAndDetect = async () => {
    if (!csvContent) {
      showError('No File', 'Please select a CSV file first.');
      return;
    }
    
    setDetectLoading(true);
    try {
      const detection = await api.post<DetectionResult>('/csv-imports/detect', { csvContent });
      if (detection) {
        setState({ 
          detectionResult: detection,
          step: 'review',
        });
        
        const matchCount = detection.siblingMatches.length;
        if (matchCount > 0) {
          success('Analysis Complete', `Found ${matchCount} potential sibling groups to review.`);
        } else {
          success('Ready to Import', `Parsed ${detection.families.length} families.`);
        }
      }
    } catch (err: unknown) {
      const error = err as Error;
      showError('Analysis Failed', error.message);
    } finally {
      setDetectLoading(false);
    }
  };
  
  // Merge handlers
  const handleApproveMerge = (match: SiblingMatch) => {
    const newMerges = [...approvedMerges, match.familyIndices];
    
    const takenIndices = new Set<number>();
    newMerges.forEach(group => group.forEach(idx => takenIndices.add(idx)));
    
    const newDismissed = [...dismissedMatches, match.id];
    detectionResult?.siblingMatches.forEach(m => {
      if (m.id !== match.id && m.familyIndices.some(idx => takenIndices.has(idx))) {
        if (!newDismissed.includes(m.id)) newDismissed.push(m.id);
      }
    });
    
    setState({ approvedMerges: newMerges, dismissedMatches: newDismissed });
  };
  
  const handleDismissMatch = (matchId: string) => {
    setState({ dismissedMatches: [...dismissedMatches, matchId] });
  };
  
  // Direct Import - bypasses all merging and duplicate detection
  const handleDirectImport = async () => {
    if (!csvContent) {
      showError('No File', 'Please select a CSV file first.');
      return;
    }
    
    setDirectLoading(true);
    try {
      const result = await api.post<ImportResult>('/csv-imports/import-direct', { csvContent, deleteExisting });
      if (result) {
        setImportResult(result);
        setState({ step: 'result' });
        clearStorage();
        
        if (result.success) {
          success('Import Complete', `Created ${result.familiesCreated} families with ${result.childrenCreated} children.`);
        }
      }
    } catch (err: unknown) {
      const error = err as Error;
      showError('Import Failed', error.message);
    } finally {
      setDirectLoading(false);
    }
  };
  
  // Import
  const handleImport = async () => {
    if (!csvContent) return;
    
    setImportLoading(true);
    try {
      const result = await api.post<ImportResult>('/csv-imports/import', {
        csvContent,
        mergeGroups: approvedMerges,
      });
      if (result) {
        setImportResult(result);
        setState({ step: 'result' });
        clearStorage(); // Clear storage after successful import
        
        if (result.success) {
          success('Import Complete', `Created ${result.familiesCreated} families.`);
        }
      }
    } catch (err: unknown) {
      const error = err as Error;
      showError('Import Failed', error.message);
    } finally {
      setImportLoading(false);
    }
  };
  
  // Reset
  const handleReset = () => {
    clearStorage();
    setImportResult(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };
  
  // Computed values
  const pendingMatches = detectionResult?.siblingMatches.filter(m => !dismissedSet.has(m.id)) || [];
  
  const getFinalFamilyCount = () => {
    if (!detectionResult) return 0;
    const totalFamilies = detectionResult.families.length;
    const mergedAway = approvedMerges.reduce((sum, group) => sum + group.length - 1, 0);
    return totalFamilies - mergedAway;
  };
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          to="/families"
          className="p-2 -ml-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5" />
        </Link>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
            <ArrowUpTrayIcon className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900">Import Families</h1>
            <p className="text-sm text-gray-500">Upload CSV and detect sibling groups</p>
          </div>
        </div>
      </div>

      {/* Step Indicator */}
        <div className="mb-8">
          <StepIndicator currentStep={step} />
        </div>
        
        {/* Step 1: Upload */}
        {step === 'upload' && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <div className="max-w-lg mx-auto">
              <div className="text-center mb-8">
                <div className="w-16 h-16 rounded-2xl bg-primary-100 flex items-center justify-center mx-auto mb-4">
                  <DocumentTextIcon className="w-8 h-8 text-primary-600" />
                </div>
                <h2 className="text-xl font-bold text-gray-900 mb-2">Upload CSV File</h2>
                <p className="text-gray-500">
                  We'll analyze your data and detect potential sibling groups before importing.
                </p>
              </div>
              
              {/* Drop Zone */}
              <label 
                className={`block cursor-pointer mb-6`}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
              >
                <div className={`border-2 border-dashed rounded-2xl p-8 text-center transition-all ${
                  isDragging 
                    ? 'border-primary-500 bg-primary-50' 
                    : fileName 
                    ? 'border-green-300 bg-green-50'
                    : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
                }`}>
                  <input 
                    ref={fileInputRef}
                    type="file" 
                    accept=".csv" 
                    onChange={handleInputChange} 
                    className="hidden" 
                  />
                  {fileName ? (
                    <>
                      <CheckCircleIcon className="w-12 h-12 text-green-500 mx-auto mb-3" />
                      <p className="text-green-700 font-semibold">{fileName}</p>
                      <p className="text-sm text-green-600 mt-1">Click to change file</p>
                    </>
                  ) : (
                    <>
                      <CloudArrowUpIcon className={`w-12 h-12 mx-auto mb-3 ${isDragging ? 'text-primary-500' : 'text-gray-400'}`} />
                      <p className="text-gray-600 font-medium">
                        {isDragging ? 'Drop your file here' : 'Drag & drop or click to upload'}
                      </p>
                      <p className="text-sm text-gray-400 mt-1">CSV files only</p>
                    </>
                  )}
                </div>
              </label>
              
              {csvContent && (
                <div className="space-y-3">
                  <button
                    onClick={handleUploadAndDetect}
                    disabled={detectLoading || directLoading}
                    className="w-full btn btn-primary py-3"
                  >
                    {detectLoading ? (
                      <>
                        <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Analyzing CSV...
                      </>
                    ) : (
                      <>
                        <SparklesIcon className="w-5 h-5" />
                        Detect Siblings & Continue
                      </>
                    )}
                  </button>
                  
                  <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                    <label className="flex items-center gap-3 cursor-pointer mb-3">
                      <input
                        type="checkbox"
                        checked={deleteExisting}
                        onChange={(e) => setDeleteExisting(e.target.checked)}
                        className="w-5 h-5 rounded border-gray-300 text-red-600 focus:ring-red-500"
                      />
                      <span className="font-medium text-gray-700">Delete all existing families first</span>
                    </label>
                    {deleteExisting && (
                      <p className="text-sm text-red-600 mb-3 pl-8">
                        ⚠️ This will permanently delete ALL existing families before importing!
                      </p>
                    )}
                    <button
                      onClick={handleDirectImport}
                      disabled={detectLoading || directLoading}
                      className={`w-full btn py-3 ${deleteExisting ? 'bg-red-600 hover:bg-red-700 text-white' : 'border-2 border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100'}`}
                    >
                      {directLoading ? (
                        <>
                          <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          {deleteExisting ? 'Deleting & Importing...' : 'Importing All...'}
                        </>
                      ) : (
                        <>
                          <ArrowUpTrayIcon className="w-5 h-5" />
                          {deleteExisting ? 'Delete All & Import Fresh' : 'Import ALL (Skip Detection)'}
                        </>
                      )}
                    </button>
                  </div>
                  <p className="text-xs text-center text-gray-500">
                    Creates one family per row - no merging, no duplicate check
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* Step 2: Review */}
        {step === 'review' && detectionResult && (
          <div className="space-y-6">
            {/* Summary Card */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Review Before Import</h2>
                  <p className="text-gray-500 mt-1">
                    {detectionResult.families.length} entries • {detectionResult.siblingMatches.length} sibling groups detected
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-bold text-primary-600">{getFinalFamilyCount()}</div>
                  <div className="text-sm text-gray-500">families to create</div>
                </div>
              </div>
            </div>
            
            {/* Warnings - Collapsible */}
            {detectionResult.warnings.length > 0 && (
              <details className="bg-white border border-gray-200 rounded-xl overflow-hidden group">
                <summary className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                      <ExclamationTriangleIcon className="w-4 h-4 text-gray-500" />
                    </div>
                    <div>
                      <span className="font-medium text-gray-700">Data Quality Notes</span>
                      <span className="ml-2 text-sm text-gray-400">
                        ({detectionResult.warnings.length} items with placeholders)
                      </span>
                    </div>
                  </div>
                  <span className="text-xs text-gray-400 group-open:hidden">Click to expand</span>
                </summary>
                <div className="border-t border-gray-100 p-4 bg-gray-50/50">
                  <ul className="text-sm text-gray-600 space-y-1.5 max-h-32 overflow-auto">
                    {detectionResult.warnings.slice(0, 10).map((w, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-gray-300 mt-1">•</span>
                        <span>{w}</span>
                      </li>
                    ))}
                    {detectionResult.warnings.length > 10 && (
                      <li className="text-gray-400 italic">
                        ...and {detectionResult.warnings.length - 10} more
                      </li>
                    )}
                  </ul>
                </div>
              </details>
            )}
            
            {/* Sibling Matches */}
            {pendingMatches.length > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <UserGroupIcon className="w-5 h-5 text-primary-600" />
                  <h3 className="font-semibold text-gray-900">
                    Potential Siblings ({pendingMatches.length} to review)
                  </h3>
                </div>
                {pendingMatches.map((match) => (
                  <SiblingMatchCard
                    key={match.id}
                    match={match}
                    onApprove={() => handleApproveMerge(match)}
                    onDismiss={() => handleDismissMatch(match.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="bg-green-50 border border-green-200 rounded-2xl p-8 text-center">
                <CheckCircleIcon className="w-12 h-12 text-green-500 mx-auto mb-3" />
                <h3 className="font-semibold text-green-800 mb-1">Ready to Import!</h3>
                <p className="text-green-600">
                  {approvedMerges.length > 0 
                    ? `${approvedMerges.length} merge(s) approved. Will create ${getFinalFamilyCount()} families.`
                    : `Will create ${getFinalFamilyCount()} families.`}
                </p>
              </div>
            )}
            
            {/* Actions */}
            <div className="flex justify-between pt-4">
              <button onClick={handleReset} className="btn btn-secondary">
                <ArrowLeftIcon className="w-4 h-4" />
                Start Over
              </button>
              <button
                onClick={handleImport}
                disabled={importLoading}
                className="btn btn-primary px-8"
              >
                {importLoading ? (
                  <>
                    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Importing...
                  </>
                ) : (
                  <>
                    Import {getFinalFamilyCount()} Families
                    <ArrowRightIcon className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}
        
        {/* Step 3: Result */}
        {step === 'result' && importResult && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
            {importResult.success && importResult.errors.length === 0 ? (
              <>
                <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-6">
                  <CheckCircleIcon className="w-10 h-10 text-green-600" />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Import Successful!</h2>
                <p className="text-gray-500 mb-4">
                  Created <span className="font-semibold text-gray-700">{importResult.familiesCreated}</span> families with <span className="font-semibold text-gray-700">{importResult.childrenCreated}</span> children.
                </p>
                {importResult.familiesSkipped > 0 && (
                  <p className="text-amber-600 mb-4">
                    Skipped <span className="font-semibold">{importResult.familiesSkipped}</span> duplicate families ({importResult.childrenSkipped} children).
                  </p>
                )}
              </>
            ) : (
              <>
                <div className="w-20 h-20 rounded-full bg-amber-100 flex items-center justify-center mx-auto mb-6">
                  <ExclamationTriangleIcon className="w-10 h-10 text-amber-600" />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Import Completed with Issues</h2>
                <p className="text-gray-500 mb-4">
                  Created {importResult.familiesCreated} families, but encountered {importResult.errors.length} errors.
                  {importResult.familiesSkipped > 0 && ` Skipped ${importResult.familiesSkipped} duplicates.`}
                </p>
              </>
            )}
            
            {/* Show skipped reasons */}
            {importResult.skippedReasons && importResult.skippedReasons.length > 0 && (
              <details className="bg-amber-50 border border-amber-200 rounded-xl p-4 max-w-lg mx-auto mb-6 text-left">
                <summary className="font-semibold text-amber-800 cursor-pointer">
                  {importResult.familiesSkipped} Duplicate Families Skipped (click to expand)
                </summary>
                <ul className="mt-3 space-y-1 text-sm text-amber-700 max-h-40 overflow-auto">
                  {importResult.skippedReasons.map((reason, i) => (
                    <li key={i}>• {reason}</li>
                  ))}
                </ul>
              </details>
            )}
            
            {importResult.errors.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 max-w-md mx-auto mb-8 text-left">
                <h4 className="font-semibold text-red-800 mb-2">Errors:</h4>
                <ul className="space-y-1 text-sm text-red-700">
                  {importResult.errors.map((err, i) => (
                    <li key={i}>
                      {err.childName && <strong>{err.childName}:</strong>} {err.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            <div className="flex justify-center gap-4">
              <button onClick={handleReset} className="btn btn-secondary">
                Import Another
              </button>
              <button onClick={() => navigate('/families')} className="btn btn-primary">
                View Families
              </button>
            </div>
          </div>
        )}
    </div>
  );
};

export default CSVImport;
