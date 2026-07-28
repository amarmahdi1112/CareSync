/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect } from 'react';
import {
  ArrowsRightLeftIcon,
  DocumentArrowDownIcon,
  CheckCircleIcon,
  XCircleIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
  CloudArrowUpIcon,
  UserGroupIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  CheckIcon,
  XMarkIcon,
  PrinterIcon,
  FolderOpenIcon,
  AdjustmentsHorizontalIcon,
  ChartBarIcon,
  PencilSquareIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { matchNames } from './algorithms/nameMatcher';
import type { NameMatch, MatchThresholds } from './algorithms/nameMatcher';
import { parsePortalCSV } from './utils/csvParser';
import { 
  saveToHistory, 
  getHistoryById, 
  getHistory,
  saveWorkInProgress, 
  loadWorkInProgress, 
  clearWorkInProgress,
  type MatchHistory 
} from './utils/localStorage';
import { exportApprovedNamesPDF, exportApprovedNamesCSV, exportFullMappingCSV } from './utils/exportResults';
import { api } from '../../../../api/client';
import { useApiQuery } from '../../../../api/hooks';

interface SavedReport {
  id: string;
  reportName: string;
  report: {
    totalChildrenProcessed: number;
    claims: Array<{
      childName: string;
      dateOfBirth?: string;
    }>;
  };
}

interface NameSyncViewProps {
  claimsData?: Array<{
    childId: string;
    childName: string;
    projectedHours: number;
    careCategory: string;
    dateOfBirth?: string;
  }>;
  onSyncComplete?: (matches: NameMatch[]) => void;
}

type TabType = 'upload' | 'results' | 'history';
type FilterType = 'all' | 'exact' | 'high' | 'medium' | 'low' | 'none' | 'review' | 'approved' | 'rejected' | 'duplicates';

export default function NameSyncView({ claimsData }: NameSyncViewProps) {
  // State
  const [portalNames, setPortalNames] = useState<string[]>([]);
  const [timeSavrNames, setTimeSavrNames] = useState<string[]>([]);
  const [matches, setMatches] = useState<NameMatch[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('upload');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [portalData, setPortalData] = useState<any[]>([]);
  const [timeSavrData, setTimeSavrData] = useState<Array<{ name: string; dob?: string }>>([]);
  const [reverseMatches, setReverseMatches] = useState<Array<{ portalName: string; timeSavrName: string; dob?: string }>>([]);
  const [selectedReportId, setSelectedReportId] = useState<string>('');
  const [selectedReportName, setSelectedReportName] = useState<string>('');
  const [showThresholds, setShowThresholds] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [dropdownSearch, setDropdownSearch] = useState('');
  const [thresholds, setThresholds] = useState<MatchThresholds>({
    exact: 0.98,
    high: 0.85,
    medium: 0.70,
    low: 0.50,
  });

  const { data: savedReports = [], loading: reportsLoading } = useApiQuery<SavedReport[]>('/claim-reports');
  const [reportLoading, setReportLoading] = useState(false);

  // Load claims from saved report
  const handleReportSelect = async (reportId: string) => {
    if (!reportId) {
      setSelectedReportId('');
      setSelectedReportName('');
      return;
    }
    
    setSelectedReportId(reportId);
    setReportLoading(true);
    try {
      const report = await api.get<SavedReport>(`/claim-reports/${reportId}`);
      if (report) {
        const transformedData = report.report.claims.map((claim: any) => ({
          name: claim.childName,
          dob: claim.dateOfBirth,
        }));
        setTimeSavrData(transformedData);
        setTimeSavrNames(transformedData.map((c: any) => c.name));
        setSelectedReportName(report.reportName);
        
        if (portalData.length > 0) {
          performMatching(portalData, transformedData);
        }
      }
    } catch (error) {
      console.error('Error loading report:', error);
    } finally {
      setReportLoading(false);
    }
  };

  // Load from claims data prop
  useEffect(() => {
    if (claimsData && claimsData.length > 0) {
      const transformedData = claimsData.map(claim => ({
        name: claim.childName,
        dob: claim.dateOfBirth,
      }));
      setTimeSavrData(transformedData);
      setTimeSavrNames(claimsData.map(c => c.childName));
      setSelectedReportName('Current Generation');
    }
  }, [claimsData]);

  // Load work-in-progress on mount
  useEffect(() => {
    const wip = loadWorkInProgress();
    if (wip && wip.matches.length > 0) {
      setMatches(wip.matches);
      setReverseMatches(wip.reverseMatches || []);
      setPortalData(wip.portalData || []);
      setTimeSavrNames(wip.timeSavrNames || []);
      setPortalNames(wip.portalData?.map((p: any) => p.name) || []);
      setActiveTab('results');
    }
  }, []);

  // Auto-save work in progress
  useEffect(() => {
    if (matches.length > 0) {
      saveWorkInProgress(matches, reverseMatches, portalData, timeSavrNames);
    }
  }, [matches, reverseMatches, portalData, timeSavrNames]);

  // Matching logic
  const performMatching = (portal: any[], claims: Array<{ name: string; dob?: string }>) => {
    setIsProcessing(true);
    
    setTimeout(() => {
      try {
        // matchNames expects (timeSavrRecords, portalChildren, thresholds)
        // where timeSavrRecords can be strings and portalChildren must have name and parsed properties
        const results = matchNames(claims, portal, thresholds);
        
        // Auto-approve exact and high confidence matches
        const autoApprovedResults = results.map(match => ({
          ...match,
          manuallyApproved: match.confidence === 'exact' || match.confidence === 'high',
          rejected: false,
        }));
        
        // Find reverse matches (portal names not matched)
        const matchedPortalNames = new Set(autoApprovedResults.filter(m => m.portalName).map(m => m.portalName));
        const unmatchedPortal = portal.filter(p => !matchedPortalNames.has(p.name));
        
        const reverseMatchResults: Array<{ portalName: string; timeSavrName: string; dob?: string }> = [];
        unmatchedPortal.forEach(portalChild => {
          const matchingClaim = claims.find(c => {
            if (portalChild.dob && c.dob) {
              return portalChild.dob === c.dob;
            }
            return false;
          });
          
          if (matchingClaim) {
            reverseMatchResults.push({
              portalName: portalChild.name,
              timeSavrName: matchingClaim.name,
              dob: matchingClaim.dob,
            });
          }
        });
        
        setReverseMatches(reverseMatchResults);
        setMatches(autoApprovedResults);
        setActiveTab('results');
        saveToHistory(portal.length, claims.length, autoApprovedResults, reverseMatchResults);
      } finally {
        setIsProcessing(false);
      }
    }, 100);
  };

  // Get assigned portal names (to detect duplicates and filter dropdown)
  const getAssignedPortalNames = (): Map<string, string[]> => {
    const assigned = new Map<string, string[]>();
    matches.forEach(match => {
      if (match.portalName && !(match as any).rejected) {
        const existing = assigned.get(match.portalName) || [];
        existing.push(match.timeSavrName);
        assigned.set(match.portalName, existing);
      }
    });
    return assigned;
  };

  // Get all portal names from uploaded CSV for manual assignment dropdown
  // Returns all names, with indication of which are already assigned
  const getPortalNamesForDropdown = (): Array<{ name: string; isAssigned: boolean; assignedTo?: string }> => {
    const assigned = getAssignedPortalNames();
    return portalNames.map(name => ({
      name,
      isAssigned: assigned.has(name),
      assignedTo: assigned.get(name)?.[0], // First claim it's assigned to
    }));
  };

  // Check if a portal name is duplicated (assigned to multiple claims)
  const isDuplicate = (portalName: string): boolean => {
    const assigned = getAssignedPortalNames();
    const assignedTo = assigned.get(portalName);
    return assignedTo ? assignedTo.length > 1 : false;
  };

  // Handle manual assignment
  const handleManualAssign = (index: number, newPortalName: string) => {
    setMatches(prev => prev.map((m, i) => 
      i === index ? { 
        ...m, 
        portalName: newPortalName || '', 
        manuallyApproved: !!newPortalName,
        rejected: !newPortalName,
        confidence: newPortalName ? 'high' : 'low',
        score: newPortalName ? 1 : 0,
        reason: newPortalName ? 'Manually assigned' : 'No match',
      } : m
    ));
    setEditingIndex(null);
  };

  // File handlers
  const handlePortalUpload = async (file: File) => {
    const content = await file.text();
    try {
      const portalChildren = parsePortalCSV(content);
      const names = portalChildren.map(c => c.name);
      setPortalNames(names);
      setPortalData(portalChildren);
      
      if (timeSavrData.length > 0) {
        performMatching(portalChildren, timeSavrData);
      }
    } catch (error) {
      console.error('Error parsing Portal CSV:', error);
      alert('Error parsing Portal CSV file. Please check the format.');
    }
  };

  const handleClaimsUpload = async (file: File) => {
    const content = await file.text();
    try {
      const lines = content.trim().split('\n');
      const hasHeader = lines[0].toLowerCase().includes('name');
      const dataLines = hasHeader ? lines.slice(1) : lines;
      
      const parsedData = dataLines
        .filter(line => line.trim())
        .map(line => {
          const parts = line.split(',').map(p => p.trim().replace(/^"|"$/g, ''));
          return {
            name: parts[0] || '',
            dob: parts.find(p => /\d{4}-\d{2}-\d{2}/.test(p) || /\d{1,2}[/-]\d{1,2}[/-]\d{2,4}/.test(p)),
          };
        })
        .filter(d => d.name);

      setTimeSavrData(parsedData);
      setTimeSavrNames(parsedData.map(d => d.name));
      setSelectedReportName('Uploaded CSV');
      
      if (portalData.length > 0) {
        performMatching(portalData, parsedData);
      }
    } catch (error) {
      console.error('Error parsing claims CSV:', error);
      alert('Error parsing CSV file.');
    }
  };

  // Match actions
  const handleApprove = (index: number) => {
    setMatches(prev => prev.map((m, i) => 
      i === index ? { ...m, manuallyApproved: true, rejected: false } : m
    ));
  };

  const handleReject = (index: number) => {
    setMatches(prev => prev.map((m, i) => 
      i === index ? { ...m, rejected: true, manuallyApproved: false } : m
    ));
  };

  const handleReset = () => {
    setPortalNames([]);
    setTimeSavrNames([]);
    setPortalData([]);
    setTimeSavrData([]);
    setMatches([]);
    setReverseMatches([]);
    setActiveTab('upload');
    clearWorkInProgress();
  };

  const handleLoadHistory = (id: string) => {
    const entry = getHistoryById(id);
    if (entry) {
      setMatches(entry.matches);
      if (entry.reverseMatches) {
        setReverseMatches(entry.reverseMatches);
      }
      setActiveTab('results');
    }
  };

  // Filter matches
  const filteredMatches = matches.filter(match => {
    const matchesSearch = match.timeSavrName.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (match.portalName?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false);
    
    if (!matchesSearch) return false;
    
    switch (filterType) {
      case 'exact': return match.confidence === 'exact';
      case 'high': return match.confidence === 'high';
      case 'medium': return match.confidence === 'medium';
      case 'low': return match.confidence === 'low';
      case 'none': return !match.portalName;
      case 'review': return match.suggestManualReview;
      case 'approved': return (match as any).manuallyApproved;
      case 'rejected': return (match as any).rejected;
      case 'duplicates': return match.portalName && isDuplicate(match.portalName);
      default: return true;
    }
  });

  // Stats
  const assignedMap = getAssignedPortalNames();
  const duplicateCount = Array.from(assignedMap.values()).filter(arr => arr.length > 1).length;
  
  const stats = {
    total: matches.length,
    exact: matches.filter(m => m.confidence === 'exact').length,
    high: matches.filter(m => m.confidence === 'high').length,
    medium: matches.filter(m => m.confidence === 'medium').length,
    low: matches.filter(m => m.confidence === 'low').length,
    noMatch: matches.filter(m => !m.portalName).length,
    approved: matches.filter(m => (m as any).manuallyApproved).length,
    rejected: matches.filter(m => (m as any).rejected).length,
    needsReview: matches.filter(m => m.suggestManualReview && !(m as any).manuallyApproved && !(m as any).rejected).length,
    duplicates: duplicateCount,
  };

  const getConfidenceBadge = (confidence: string, match: NameMatch) => {
    const isApproved = (match as any).manuallyApproved;
    const isRejected = (match as any).rejected;
    const isAutoApproved = isApproved && (confidence === 'exact' || confidence === 'high') && match.reason !== 'Manually assigned';
    
    if (isRejected) {
      return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">Rejected</span>;
    }
    if (isApproved) {
      if (isAutoApproved) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Auto ✓</span>;
      }
      return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Manual ✓</span>;
    }
    
    const colors: Record<string, string> = {
      exact: 'bg-emerald-100 text-emerald-800',
      high: 'bg-blue-100 text-blue-800',
      medium: 'bg-yellow-100 text-yellow-800',
      low: 'bg-orange-100 text-orange-800',
      none: 'bg-gray-100 text-gray-800',
    };
    
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[confidence] || colors.none}`}>
        {confidence || 'None'}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-indigo-100 rounded-lg">
            <ArrowsRightLeftIcon className="h-6 w-6 text-indigo-600" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Name Sync</h2>
            <p className="text-sm text-gray-500">Match claim names with portal enrollment names</p>
          </div>
        </div>
        
        {/* Tab Navigation */}
        <div className="flex items-center bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setActiveTab('upload')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === 'upload' 
                ? 'bg-white text-gray-900 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            Upload
          </button>
          <button
            onClick={() => setActiveTab('results')}
            disabled={matches.length === 0}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === 'results' 
                ? 'bg-white text-gray-900 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            } ${matches.length === 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Results
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === 'history' 
                ? 'bg-white text-gray-900 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            History
          </button>
        </div>
      </div>

      {/* Upload Tab */}
      {activeTab === 'upload' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Portal Upload */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center space-x-3 mb-4">
              <div className="p-2 bg-blue-100 rounded-lg">
                <CloudArrowUpIcon className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900">Portal Names</h3>
                <p className="text-sm text-gray-500">Upload enrollment data from portal</p>
              </div>
            </div>
            
            <div className="border-2 border-dashed border-gray-200 rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
              <input
                type="file"
                accept=".csv"
                onChange={(e) => e.target.files?.[0] && handlePortalUpload(e.target.files[0])}
                className="hidden"
                id="portal-upload"
              />
              <label htmlFor="portal-upload" className="cursor-pointer">
                <CloudArrowUpIcon className="h-10 w-10 text-gray-400 mx-auto mb-3" />
                <p className="text-sm text-gray-600 mb-1">Drop CSV file here or click to browse</p>
                <p className="text-xs text-gray-400">Expected columns: Name, DOB</p>
              </label>
            </div>
            
            {portalNames.length > 0 && (
              <div className="mt-4 flex items-center justify-between bg-green-50 border border-green-200 rounded-lg p-3">
                <div className="flex items-center space-x-2">
                  <CheckCircleIcon className="h-5 w-5 text-green-500" />
                  <span className="text-sm text-green-700">{portalNames.length} names loaded</span>
                </div>
              </div>
            )}
          </div>

          {/* Claims Upload */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center space-x-3 mb-4">
              <div className="p-2 bg-purple-100 rounded-lg">
                <UserGroupIcon className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900">Claim Names</h3>
                <p className="text-sm text-gray-500">Select saved report or upload CSV</p>
              </div>
            </div>
            
            {/* Report Selector */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">Load from Saved Report</label>
              <select
                value={selectedReportId}
                onChange={(e) => handleReportSelect(e.target.value)}
                disabled={reportsLoading || reportLoading}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option value="">Select a saved report...</option>
                {savedReports.map((report) => (
                  <option key={report.id} value={report.id}>
                    {report.reportName} ({report.report?.totalChildrenProcessed || 0} children)
                  </option>
                ))}
              </select>
            </div>
            
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200"></div>
              </div>
              <div className="relative flex justify-center">
                <span className="bg-white px-3 text-sm text-gray-500">or upload CSV</span>
              </div>
            </div>
            
            <div className="border-2 border-dashed border-gray-200 rounded-lg p-8 text-center hover:border-purple-400 transition-colors">
              <input
                type="file"
                accept=".csv"
                onChange={(e) => e.target.files?.[0] && handleClaimsUpload(e.target.files[0])}
                className="hidden"
                id="claims-upload"
              />
              <label htmlFor="claims-upload" className="cursor-pointer">
                <CloudArrowUpIcon className="h-10 w-10 text-gray-400 mx-auto mb-3" />
                <p className="text-sm text-gray-600 mb-1">Drop CSV file here or click to browse</p>
                <p className="text-xs text-gray-400">Expected columns: Name, DOB (optional)</p>
              </label>
            </div>
            
            {timeSavrNames.length > 0 && (
              <div className="mt-4 flex items-center justify-between bg-green-50 border border-green-200 rounded-lg p-3">
                <div className="flex items-center space-x-2">
                  <CheckCircleIcon className="h-5 w-5 text-green-500" />
                  <span className="text-sm text-green-700">{timeSavrNames.length} names loaded</span>
                  {selectedReportName && (
                    <span className="text-xs text-green-600">from {selectedReportName}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Processing Indicator */}
      {isProcessing && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-4 border-indigo-500 border-t-transparent mx-auto mb-4"></div>
          <p className="text-gray-600">Matching names...</p>
        </div>
      )}

      {/* Results Tab */}
      {activeTab === 'results' && matches.length > 0 && !isProcessing && (
        <div className="space-y-6">
          {/* Stats Summary */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-gray-100 rounded-lg">
                  <UserGroupIcon className="h-5 w-5 text-gray-600" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">Total</p>
                  <p className="text-xl font-bold text-gray-900">{stats.total}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-emerald-100 rounded-lg">
                  <CheckCircleIcon className="h-5 w-5 text-emerald-600" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">Exact</p>
                  <p className="text-xl font-bold text-emerald-600">{stats.exact}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <ChartBarIcon className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">High</p>
                  <p className="text-xl font-bold text-blue-600">{stats.high}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-yellow-100 rounded-lg">
                  <ExclamationTriangleIcon className="h-5 w-5 text-yellow-600" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">Review</p>
                  <p className="text-xl font-bold text-yellow-600">{stats.needsReview}</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-red-100 rounded-lg">
                  <XCircleIcon className="h-5 w-5 text-red-600" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">No Match</p>
                  <p className="text-xl font-bold text-red-600">{stats.noMatch}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Reverse Matches */}
          {reverseMatches.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <div className="flex items-center space-x-2 mb-3">
                <ExclamationTriangleIcon className="h-5 w-5 text-amber-600" />
                <h3 className="font-semibold text-amber-800">DOB-Based Matches Found ({reverseMatches.length})</h3>
              </div>
              <p className="text-sm text-amber-700 mb-3">These names were matched by date of birth when name matching failed:</p>
              <div className="space-y-2">
                {reverseMatches.slice(0, 5).map((rm, idx) => (
                  <div key={idx} className="bg-white rounded-lg p-3 flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                      <span className="text-sm font-medium text-gray-900">{rm.timeSavrName}</span>
                      <ArrowsRightLeftIcon className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-indigo-600">{rm.portalName}</span>
                    </div>
                    <span className="text-xs text-gray-500">DOB: {rm.dob}</span>
                  </div>
                ))}
                {reverseMatches.length > 5 && (
                  <p className="text-sm text-amber-600">+{reverseMatches.length - 5} more matches</p>
                )}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <button
                onClick={handleReset}
                className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
              >
                <ArrowPathIcon className="h-4 w-4 mr-2" />
                Start Over
              </button>
              <button
                onClick={() => setShowThresholds(!showThresholds)}
                className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
              >
                <AdjustmentsHorizontalIcon className="h-4 w-4 mr-2" />
                Thresholds
              </button>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => exportApprovedNamesPDF(matches, reverseMatches)}
                className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
              >
                <PrinterIcon className="h-4 w-4 mr-2" />
                Print PDF
              </button>
              <button
                onClick={() => exportApprovedNamesCSV(matches, reverseMatches)}
                className="inline-flex items-center px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700"
                title="Export portal names only (for claims)"
              >
                <DocumentArrowDownIcon className="h-4 w-4 mr-2" />
                Portal Names CSV
              </button>
              <button
                onClick={() => exportFullMappingCSV(matches, reverseMatches)}
                className="inline-flex items-center px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700"
                title="Export both portal and original names (mapping reference)"
              >
                <DocumentArrowDownIcon className="h-4 w-4 mr-2" />
                Full Mapping CSV
              </button>
            </div>
          </div>

          {/* Threshold Settings */}
          {showThresholds && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <h4 className="font-medium text-gray-900 mb-4">Match Thresholds</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(thresholds).map(([key, value]) => (
                  <div key={key}>
                    <label className="block text-sm font-medium text-gray-700 mb-1 capitalize">{key}</label>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      value={value}
                      onChange={(e) => setThresholds({ ...thresholds, [key]: parseFloat(e.target.value) })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Results Table */}
          <div className="bg-white rounded-xl border border-gray-200">
            <div className="p-4 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-900">Match Results</h3>
                <div className="flex items-center space-x-3">
                  <div className="relative">
                    <MagnifyingGlassIcon className="h-5 w-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search names..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm w-64"
                    />
                  </div>
                  <select
                    value={filterType}
                    onChange={(e) => setFilterType(e.target.value as FilterType)}
                    className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  >
                    <option value="all">All ({stats.total})</option>
                    <option value="approved">✓ Approved ({stats.approved})</option>
                    <option value="rejected">✗ Rejected ({stats.rejected})</option>
                    <option value="exact">Exact ({stats.exact})</option>
                    <option value="high">High ({stats.high})</option>
                    <option value="medium">Medium ({stats.medium})</option>
                    <option value="low">Low ({stats.low})</option>
                    <option value="none">No Match ({stats.noMatch})</option>
                    <option value="review">Needs Review ({stats.needsReview})</option>
                    {stats.duplicates > 0 && (
                      <option value="duplicates">⚠ Duplicates ({stats.duplicates})</option>
                    )}
                  </select>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
              <table className="w-full">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Claim Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Portal Match</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Confidence</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Score</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredMatches.map((match, idx) => {
                    const isApproved = (match as any).manuallyApproved;
                    const isRejected = (match as any).rejected;
                    const originalIndex = matches.findIndex(m => m.timeSavrName === match.timeSavrName);
                    const isEditing = editingIndex === originalIndex;
                    const hasDuplicate = match.portalName && isDuplicate(match.portalName);
                    const allPortalNames = getPortalNamesForDropdown();
                    
                    return (
                      <tr 
                        key={idx} 
                        className={`hover:bg-gray-50 ${isApproved ? 'bg-green-50' : ''} ${isRejected ? 'bg-red-50' : ''} ${match.suggestManualReview && !isApproved && !isRejected ? 'bg-yellow-50' : ''} ${hasDuplicate ? 'bg-amber-50' : ''}`}
                      >
                        <td className="px-4 py-3 font-medium text-gray-900">{match.timeSavrName}</td>
                        <td className="px-4 py-3 relative">
                          {isEditing ? (
                            <div className="relative">
                              <input
                                type="text"
                                placeholder="Search portal names..."
                                value={dropdownSearch}
                                onChange={(e) => setDropdownSearch(e.target.value)}
                                autoFocus
                                className="w-full px-2 py-1 text-sm border border-indigo-300 rounded-t-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                              />
                              <div className="absolute z-50 w-full max-h-48 overflow-y-auto bg-white border border-t-0 border-indigo-300 rounded-b-lg shadow-lg">
                                <button
                                  type="button"
                                  onClick={() => {
                                    handleManualAssign(originalIndex, '');
                                    setDropdownSearch('');
                                  }}
                                  className="w-full px-2 py-1.5 text-left text-sm text-gray-500 hover:bg-gray-100 border-b"
                                >
                                  -- No match --
                                </button>
                                {allPortalNames
                                  .filter(item => item.name.toLowerCase().includes(dropdownSearch.toLowerCase()))
                                  .map(item => (
                                    <button
                                      type="button"
                                      key={item.name}
                                      onClick={() => {
                                        handleManualAssign(originalIndex, item.name);
                                        setDropdownSearch('');
                                      }}
                                      className={`w-full px-2 py-1.5 text-left text-sm hover:bg-indigo-50 ${
                                        item.name === match.portalName ? 'bg-indigo-100 font-medium' : ''
                                      } ${item.isAssigned && item.name !== match.portalName ? 'text-amber-700' : 'text-gray-900'}`}
                                    >
                                      {item.name}
                                      {item.isAssigned && item.name !== match.portalName && (
                                        <span className="text-xs text-amber-500 ml-1">(→ {item.assignedTo})</span>
                                      )}
                                    </button>
                                  ))}
                                {allPortalNames.filter(item => item.name.toLowerCase().includes(dropdownSearch.toLowerCase())).length === 0 && (
                                  <div className="px-2 py-2 text-sm text-gray-400 italic">No matches found</div>
                                )}
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingIndex(null);
                                  setDropdownSearch('');
                                }}
                                className="absolute -top-1 -right-1 p-0.5 bg-gray-200 rounded-full hover:bg-gray-300"
                                title="Close"
                              >
                                <XMarkIcon className="h-3 w-3 text-gray-600" />
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center space-x-2">
                              <span className={match.portalName ? 'text-gray-900' : 'text-gray-400 italic'}>
                                {match.portalName || 'No match'}
                              </span>
                              {hasDuplicate && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800" title="This portal name is assigned to multiple claims">
                                  <ExclamationCircleIcon className="h-3 w-3 mr-0.5" />
                                  Dup
                                </span>
                              )}
                              <button
                                onClick={() => setEditingIndex(originalIndex)}
                                className="p-1 hover:bg-gray-100 rounded text-gray-400 hover:text-indigo-600"
                                title="Manual Assignment"
                              >
                                <PencilSquareIcon className="h-4 w-4" />
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">{getConfidenceBadge(match.confidence, match)}</td>
                        <td className="px-4 py-3 text-center text-sm text-gray-600">{(match.score * 100).toFixed(0)}%</td>
                        <td className="px-4 py-3 text-center">
                          <div className="flex items-center justify-center space-x-2">
                            <button
                              onClick={() => handleApprove(originalIndex)}
                              disabled={isApproved}
                              className={`p-1.5 rounded-lg ${isApproved ? 'bg-green-200 text-green-700' : 'hover:bg-green-100 text-gray-400 hover:text-green-600'}`}
                              title="Approve"
                            >
                              <CheckIcon className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleReject(originalIndex)}
                              disabled={isRejected}
                              className={`p-1.5 rounded-lg ${isRejected ? 'bg-red-200 text-red-700' : 'hover:bg-red-100 text-gray-400 hover:text-red-600'}`}
                              title="Reject / Disapprove"
                            >
                              <XMarkIcon className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {filteredMatches.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                No matches found for your search criteria
              </div>
            )}
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <HistoryPanel onLoadHistory={handleLoadHistory} />
      )}
    </div>
  );
}

// History Panel Component
function HistoryPanel({ onLoadHistory }: { onLoadHistory: (id: string) => void }) {
  const history = getHistory();
  
  if (history.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <ClockIcon className="h-8 w-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">No History Yet</h3>
        <p className="text-gray-500">Your matching history will appear here after you run a match.</p>
      </div>
    );
  }

  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <div className="p-4 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">Match History</h3>
      </div>
      <div className="divide-y divide-gray-200">
        {history.map((entry: MatchHistory) => (
          <div key={entry.id} className="p-4 hover:bg-gray-50">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900">{formatDate(entry.timestamp)}</p>
                <p className="text-sm text-gray-500">
                  {entry.portalCount} portal names × {entry.timeSavrCount} claim names
                </p>
                <div className="flex items-center space-x-3 mt-2">
                  <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
                    {entry.summary.exact} exact
                  </span>
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                    {entry.summary.high} high
                  </span>
                  {entry.summary.manuallyApproved ? (
                    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                      {entry.summary.manuallyApproved} approved
                    </span>
                  ) : null}
                </div>
              </div>
              <button
                onClick={() => onLoadHistory(entry.id)}
                className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
              >
                <FolderOpenIcon className="h-4 w-4 mr-2" />
                Load
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
