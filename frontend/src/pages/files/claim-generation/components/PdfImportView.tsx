import React, { useState, useCallback } from 'react';
import {
  DocumentArrowUpIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
  ArrowPathIcon,
  DocumentTextIcon,
  UserIcon,
  ClockIcon,
  TrashIcon,
  FolderOpenIcon,
  CalendarIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../../stores';
import { api } from '../../../../api/client';
import { useApiQuery } from '../../../../api/hooks';

interface MatchedClaim {
  pdfName: string;
  matchedChildId?: string;
  matchedChildName?: string;
  hours: number;
  careCategory?: string;
  dateOfBirth?: string;
  attendanceDays?: number;
  confidence: 'exact' | 'high' | 'medium' | 'low' | 'none';
  score: number;
  suggestManualReview: boolean;
  reason: string;
}

interface ImportResult {
  success: boolean;
  totalEntriesFound: number;
  matchedCount: number;
  unmatchedCount: number;
  reviewRequiredCount: number;
  claims: MatchedClaim[];
  errors: string[];
}

type Step = 'upload' | 'processing' | 'review';

interface SaveResult {
  success: boolean;
  batchId: string;
  savedCount: number;
  matchedCount?: number;
  unmatchedCount?: number;
  errors: string[];
}

interface ImportedClaimBatch {
  batchId: string;
  claimMonth: number;
  claimYear: number;
  totalClaims: number;
  matchedCount: number;
  unmatchedCount: number;
  sourceFilename?: string;
  importedAt: string;
}

interface PdfImportViewProps {
  onUseForScheduling?: (batchId: string) => void;
}

interface SavedBatchSummary {
  batchId: string;
  savedCount: number;
  matchedCount: number;
  unmatchedCount: number;
}

interface ImportedClaim {
  id: string;
  childName: string;
  hoursClaimed: number;
  careCategory?: string;
  dateOfBirth?: string;
  claimMonth: number;
  claimYear: number;
  importBatchId: string;
  sourceFilename?: string;
  matchedChildId?: string;
  matchConfidence?: number;
  manuallyVerified: boolean;
  importedAt: string;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const PdfImportView: React.FC<PdfImportViewProps> = ({ onUseForScheduling }) => {
  const { success, error: showError } = useNotificationStore();
  const [step, setStep] = useState<Step>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [viewingBatch, setViewingBatch] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedBatch, setSavedBatch] = useState<SavedBatchSummary | null>(null);
  
  // Month/Year for the claim period
  const currentDate = new Date();
  const [claimMonth, setClaimMonth] = useState(currentDate.getMonth() + 1);
  const [claimYear, setClaimYear] = useState(currentDate.getFullYear());

  // Fetch saved batches
  const { data: batches = [], refetch: refetchBatches } = useApiQuery<ImportedClaimBatch[]>('/claim-imports/batches');
  
  // Fetch claims for selected batch
  const { data: batchClaims = [] } = useApiQuery<ImportedClaim[]>(
    `/claim-imports/batches/${viewingBatch || ''}`,
    undefined,
    Boolean(viewingBatch),
  );

  const deleteBatch = async (batchId: string) => {
    try {
      await api.delete(`/claim-imports/batches/${batchId}`);
      success('Batch Deleted', 'Import batch deleted successfully');
      setViewingBatch(null);
      await refetchBatches();
    } catch (err) {
      showError('Delete Failed', err instanceof Error ? err.message : 'Request failed');
    }
  };

  const importPdf = async (pdfBase64: string) => {
    setLoading(true);
    try {
      const importResult = await api.post<ImportResult>('/claim-imports/parse', { pdfBase64 });
      setResult(importResult);
      setStep('review');
      
      if (importResult.success) {
        success(
          'PDF Processed',
          `Found ${importResult.totalEntriesFound} entries, matched ${importResult.matchedCount} children`
        );
      } else {
        showError('Import Failed', importResult.errors.join(', '));
      }
    } catch (err) {
      console.error('PDF import error:', err);
      showError('Import Failed', err instanceof Error ? err.message : 'Request failed');
      setStep('upload');
    } finally {
      setLoading(false);
    }
  };

  const saveClaims = async (payload: object) => {
    setSaving(true);
    try {
      const saveResult = await api.post<SaveResult>('/claim-imports/batches', payload);
      if (saveResult.success) {
        const summary = {
          batchId: saveResult.batchId,
          savedCount: saveResult.savedCount,
          matchedCount: saveResult.matchedCount ?? 0,
          unmatchedCount: saveResult.unmatchedCount ?? 0,
        };
        setSavedBatch(summary);
        success(
          'Claims Saved',
          `Saved ${summary.savedCount} claims; ${summary.matchedCount} are ready for scheduling`
        );
        handleReset();
      } else {
        showError('Save Failed', saveResult.errors.join(', '));
      }
    } catch (err) {
      console.error('Save error:', err);
      showError('Save Failed', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveClaims = () => {
    if (!result || result.claims.length === 0) return;

    const claimsToSave = result.claims.map(c => ({
      childName: c.pdfName,
      hoursClaimed: Math.round(c.hours),
      careCategory: c.careCategory,
      dateOfBirth: c.dateOfBirth,
      matchedChildId: c.matchedChildId,
      matchConfidence: c.score,
    }));

    void saveClaims({
      claims: claimsToSave,
      claimMonth,
      claimYear,
      sourceFilename: selectedFile?.name,
    });
  };

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.type === 'application/pdf') {
        setSelectedFile(file);
      } else {
        showError('Invalid File', 'Please upload a PDF file');
      }
    }
  }, [showError]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.type === 'application/pdf') {
        setSelectedFile(file);
      } else {
        showError('Invalid File', 'Please upload a PDF file');
      }
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setStep('processing');

    try {
      // Read file as base64
      const reader = new FileReader();
      reader.onload = async () => {
        const base64 = (reader.result as string).split(',')[1];
        await importPdf(base64);
      };
      reader.onerror = () => {
        showError('Read Error', 'Failed to read PDF file');
        setStep('upload');
      };
      reader.readAsDataURL(selectedFile);
    } catch (err) {
      console.error('Upload error:', err);
      setStep('upload');
    }
  };

  const handleReset = () => {
    setStep('upload');
    setSelectedFile(null);
    setResult(null);
    refetchBatches();
  };

  const getConfidenceBadge = (confidence: string) => {
    const styles: Record<string, string> = {
      exact: 'bg-green-100 text-green-800 border-green-200',
      high: 'bg-blue-100 text-blue-800 border-blue-200',
      medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
      low: 'bg-orange-100 text-orange-800 border-orange-200',
      none: 'bg-red-100 text-red-800 border-red-200',
    };

    const labels: Record<string, string> = {
      exact: 'Exact Match',
      high: 'High Confidence',
      medium: 'Medium',
      low: 'Low',
      none: 'No Match',
    };

    return (
      <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${styles[confidence] || styles.none}`}>
        {labels[confidence] || confidence}
      </span>
    );
  };

  const getConfidenceIcon = (confidence: string) => {
    switch (confidence) {
      case 'exact':
      case 'high':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'medium':
        return <ExclamationTriangleIcon className="h-5 w-5 text-yellow-500" />;
      case 'low':
        return <ExclamationTriangleIcon className="h-5 w-5 text-orange-500" />;
      default:
        return <XCircleIcon className="h-5 w-5 text-red-500" />;
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Upload Step */}
      {step === 'upload' && (
        <div className="space-y-6">
          {savedBatch && (
            <div className="p-5 bg-green-50 rounded-xl border border-green-200">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-semibold text-green-900">Import saved and ready</p>
                  <p className="text-sm text-green-700">
                    All {savedBatch.savedCount} claims can be scheduled now.
                    {savedBatch.unmatchedCount > 0
                      ? ` ${savedBatch.unmatchedCount} unmatched claim${savedBatch.unmatchedCount === 1 ? '' : 's'} will be scheduled as import-only children.`
                      : ' Every claim is matched.'}
                  </p>
                </div>
                {onUseForScheduling && (
                  <button
                    type="button"
                    onClick={() => onUseForScheduling(savedBatch.batchId)}
                    className="btn btn-primary flex shrink-0 items-center space-x-2 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span>Schedule All Imported Claims</span>
                    <ArrowRightIcon className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
          <div className="text-center mb-8">
            <DocumentTextIcon className="h-16 w-16 text-primary-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Import Claims from PDF</h2>
            <p className="text-gray-500 max-w-md mx-auto">
              Upload a PDF containing claim data. The system will extract names and hours,
              then match them to children in your database.
            </p>
          </div>

          {/* Drop Zone */}
          <div
            className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
              dragActive
                ? 'border-primary-500 bg-primary-50'
                : selectedFile
                ? 'border-green-500 bg-green-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            {selectedFile ? (
              <div className="space-y-4">
                <CheckCircleIcon className="h-12 w-12 text-green-500 mx-auto" />
                <div>
                  <p className="font-medium text-gray-900">{selectedFile.name}</p>
                  <p className="text-sm text-gray-500">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <button
                  onClick={() => setSelectedFile(null)}
                  className="text-sm text-red-600 hover:text-red-700"
                >
                  Remove file
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <DocumentArrowUpIcon className="h-12 w-12 text-gray-400 mx-auto" />
                <div>
                  <p className="font-medium text-gray-900">
                    Drag and drop your PDF here
                  </p>
                  <p className="text-sm text-gray-500">or</p>
                </div>
                <label className="btn btn-secondary cursor-pointer">
                  <span>Browse Files</span>
                  <input
                    type="file"
                    accept="application/pdf"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </label>
              </div>
            )}
          </div>

          {/* Upload Button */}
          {selectedFile && (
            <div className="mt-6 flex justify-center">
              <button
                onClick={handleUpload}
                disabled={loading}
                className="btn btn-primary px-8 py-3 text-lg"
              >
                <DocumentArrowUpIcon className="h-5 w-5 mr-2" />
                Process PDF
              </button>
            </div>
          )}

          {/* Supported Formats */}
          <div className="mt-8 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-medium text-gray-900 mb-2">Supported PDF Formats</h3>
            <ul className="text-sm text-gray-600 space-y-1">
              <li>• Government Child Participation Reports</li>
              <li>• Table format with name and hours columns</li>
              <li>• Portal format: "LastName, FirstName" with hours</li>
            </ul>
          </div>
          </div>
        </div>
      )}

      {/* Saved Import Batches - Show on upload step */}
      {step === 'upload' && batches.length > 0 && (
        <div className="mt-6 bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 flex items-center">
              <FolderOpenIcon className="h-5 w-5 mr-2 text-primary-500" />
              Saved Import Batches
            </h3>
          </div>
          
          <div className="space-y-3">
            {batches.map((batch) => (
              <div
                key={batch.batchId}
                className={`p-4 rounded-lg border transition-colors cursor-pointer ${
                  viewingBatch === batch.batchId
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
                onClick={() => setViewingBatch(viewingBatch === batch.batchId ? null : batch.batchId)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className="p-2 bg-blue-100 rounded-lg">
                      <CalendarIcon className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">
                        {MONTHS[batch.claimMonth - 1]} {batch.claimYear}
                      </p>
                      <p className="text-sm text-gray-500">
                        {batch.totalClaims} claims • {batch.matchedCount} matched
                        {batch.unmatchedCount > 0 ? ` • ${batch.unmatchedCount} import-only` : ''}
                        {' • '}{batch.sourceFilename || 'Unknown file'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs text-gray-400">
                      {new Date(batch.importedAt).toLocaleDateString()}
                    </span>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm('Delete this import batch?')) {
                          void deleteBatch(batch.batchId);
                        }
                      }}
                      className="p-1 text-gray-400 hover:text-red-500"
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                    {onUseForScheduling && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          onUseForScheduling(batch.batchId);
                        }}
                        className="btn btn-primary px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Use for Scheduling
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded Claims View */}
                {viewingBatch === batch.batchId && (
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <div className="max-h-64 overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50 sticky top-0">
                          <tr>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Name</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Hours</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Category</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {batchClaims.map((claim) => (
                            <tr key={claim.id}>
                              <td className="px-3 py-2 font-medium text-gray-900">{claim.childName}</td>
                              <td className="px-3 py-2 text-gray-600">{claim.hoursClaimed}</td>
                              <td className="px-3 py-2 text-gray-500">{claim.careCategory || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Processing Step */}
      {step === 'processing' && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-primary-200 border-t-primary-500 mx-auto mb-6" />
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Processing PDF...</h2>
          <p className="text-gray-500">Extracting claim data and matching names</p>
        </div>
      )}

      {/* Review Step */}
      {step === 'review' && result && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <DocumentTextIcon className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{result.totalEntriesFound}</p>
                  <p className="text-sm text-gray-500">Total Entries</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-green-100 rounded-lg">
                  <CheckCircleIcon className="h-6 w-6 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{result.matchedCount}</p>
                  <p className="text-sm text-gray-500">Matched</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-yellow-100 rounded-lg">
                  <ExclamationTriangleIcon className="h-6 w-6 text-yellow-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{result.reviewRequiredCount}</p>
                  <p className="text-sm text-gray-500">Need Review</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-red-100 rounded-lg">
                  <XCircleIcon className="h-6 w-6 text-red-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{result.unmatchedCount}</p>
                  <p className="text-sm text-gray-500">Unmatched</p>
                </div>
              </div>
            </div>
          </div>

          {/* Errors */}
          {result.errors.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="font-medium text-red-800 mb-2">Errors</h3>
              <ul className="text-sm text-red-700 space-y-1">
                {result.errors.map((error, idx) => (
                  <li key={idx}>• {error}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Claims Table */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">Matched Claims</h3>
              <button
                onClick={handleReset}
                className="btn btn-secondary text-sm"
              >
                <ArrowPathIcon className="h-4 w-4 mr-1" />
                Upload New PDF
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      PDF Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Matched Child
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Hours
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Category
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Confidence
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Reason
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {result.claims.map((claim, idx) => (
                    <tr
                      key={idx}
                      className={claim.suggestManualReview ? 'bg-yellow-50' : ''}
                    >
                      <td className="px-6 py-4">
                        {getConfidenceIcon(claim.confidence)}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center space-x-2">
                          <UserIcon className="h-4 w-4 text-gray-400" />
                          <span className="font-medium text-gray-900">{claim.pdfName}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        {claim.matchedChildName ? (
                          <span className="text-gray-900">{claim.matchedChildName}</span>
                        ) : (
                          <span className="text-gray-400 italic">No match</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center space-x-1">
                          <ClockIcon className="h-4 w-4 text-gray-400" />
                          <span className="font-medium">{claim.hours.toFixed(2)}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-gray-600">{claim.careCategory || '-'}</span>
                      </td>
                      <td className="px-6 py-4">
                        {getConfidenceBadge(claim.confidence)}
                        <span className="ml-2 text-xs text-gray-500">
                          ({(claim.score * 100).toFixed(0)}%)
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-sm text-gray-600">{claim.reason}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Month/Year Selection */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Claim Period</h3>
            <div className="flex items-center space-x-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Month</label>
                <select
                  value={claimMonth}
                  onChange={(e) => setClaimMonth(parseInt(e.target.value, 10))}
                  className="input w-32"
                >
                  {[
                    'January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'
                  ].map((month, idx) => (
                    <option key={idx} value={idx + 1}>{month}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Year</label>
                <select
                  value={claimYear}
                  onChange={(e) => setClaimYear(parseInt(e.target.value, 10))}
                  className="input w-24"
                >
                  {Array.from({ length: 12 }, (_, index) => currentDate.getFullYear() + 1 - index).map((year) => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex justify-end space-x-4">
            <button onClick={handleReset} className="btn btn-secondary">
              Cancel
            </button>
            <button 
              onClick={handleSaveClaims}
              disabled={saving}
              className="btn btn-primary"
            >
              {saving ? (
                <>
                  <ArrowPathIcon className="h-5 w-5 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <CheckCircleIcon className="h-5 w-5 mr-2" />
                  Save {result?.claims.length || 0} Claims
                </>
              )}
            </button>
          </div>
        </div>
      )}


    </div>
  );
};

export default PdfImportView;
