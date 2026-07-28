import React, { useState } from 'react';
import {
  XMarkIcon,
  DocumentArrowDownIcon,
  UserGroupIcon,
  ClockIcon,
  ChartBarIcon,
  CalendarIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
  PrinterIcon,
} from '@heroicons/react/24/outline';
import { useApiQuery } from '../../../../api/hooks';
import { getPortalName, getApprovedNameMappings } from '../name-sync/utils/localStorage';

interface Claim {
  childId: string;
  childName: string;
  ageInYears: number;
  ageInMonths: number;
  careCategory: string;
  behavioralProfile: string;
  isProrated: boolean;
  enrollmentDate?: string;
  projectedHours: number;
  projectedAttendanceDays: number;
  baseHoursBeforeProration?: number;
  notes?: string[];
  calculationDetails?: {
    totalBusinessDays: number;
    schoolBreakDays: number;
    regularSchoolDays: number;
    averageHoursPerDay: number;
    capacityLimitedDays: number;
  };
}

interface ReportDetail {
  id: string;
  reportName: string;
  created_at: string;
  createdBy: string;
  description?: string;
  report: {
    targetMonth: number;
    targetYear: number;
    totalChildrenProcessed: number;
    totalProjectedHours: number;
    averageHoursPerChild: number;
    fullTimeChildren: number;
    schoolAgeChildren: number;
    proratedChildren: number;
    claims: Claim[];
  };
}

interface ReportDetailModalProps {
  reportId: string;
  isOpen: boolean;
  onClose: () => void;
  onRegenerate?: (reportId: string) => void;
}

const ReportDetailModal: React.FC<ReportDetailModalProps> = ({
  reportId,
  isOpen,
  onClose,
  onRegenerate,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [profileFilter, setProfileFilter] = useState<string>('all');

  const { data: report, loading, error } = useApiQuery<ReportDetail>(
    `/claim-reports/${reportId}`,
    undefined,
    isOpen && Boolean(reportId),
  );

  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  if (!isOpen) return null;

  const filteredClaims = report?.report.claims.filter((claim) => {
    const matchesSearch = claim.childName.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = categoryFilter === 'all' || claim.careCategory === categoryFilter;
    const matchesProfile = profileFilter === 'all' || claim.behavioralProfile === profileFilter;
    return matchesSearch && matchesCategory && matchesProfile;
  }) || [];

  const downloadCSV = () => {
    if (!report) return;
    
    // Check if we have approved name mappings
    const nameMappings = getApprovedNameMappings();
    const hasNameMappings = nameMappings.length > 0;
    
    const headers = [
      hasNameMappings ? 'Portal Name' : 'Child Name',
      'Original Name',
      'Age (Years)',
      'Care Category',
      'Behavioral Profile',
      'Projected Hours',
      'Attendance Days',
      'Avg Hours/Day',
      'Prorated',
      'Notes',
    ];
    
    // Transform claims to use portal names
    const claimsWithPortalNames = report.report.claims.map((c) => ({
      ...c,
      displayName: getPortalName(c.childName),
    }));
    
    // Sort alphabetically by display name
    const sortedClaims = [...claimsWithPortalNames].sort((a, b) => 
      a.displayName.localeCompare(b.displayName, undefined, { sensitivity: 'base' })
    );
    
    const rows = sortedClaims.map((c) => [
      `"${c.displayName}"`,
      `"${c.childName}"`,
      c.ageInYears,
      c.careCategory,
      c.behavioralProfile,
      c.projectedHours.toFixed(2),
      c.projectedAttendanceDays,
      c.calculationDetails?.averageHoursPerDay?.toFixed(2) || '',
      c.isProrated ? 'Yes' : 'No',
      `"${c.notes?.join('; ') || ''}"`,
    ]);

    const csvContent = [headers, ...rows].map((row) => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${report.reportName.replace(/\s+/g, '_')}_${months[report.report.targetMonth - 1]}_${report.report.targetYear}_sorted.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => {
    if (!report) return;
    
    // Create a new window for printing
    const printWindow = window.open('', '_blank', 'width=800,height=600');
    if (!printWindow) return;

    // Check if we have approved name mappings
    const nameMappings = getApprovedNameMappings();
    const hasNameMappings = nameMappings.length > 0;

    // Transform claims to use portal names and sort alphabetically
    const claimsWithPortalNames = report.report.claims.map((c) => ({
      ...c,
      displayName: getPortalName(c.childName), // Use portal name if available
    }));

    // Sort alphabetically by display name (LastName, FirstName format)
    const sortedClaims = [...claimsWithPortalNames].sort((a, b) => 
      a.displayName.localeCompare(b.displayName, undefined, { sensitivity: 'base' })
    );

    const claimsRows = sortedClaims
      .map((c) => `
        <tr>
          <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: 500;">${c.displayName}</td>
          <td style="padding: 8px; border-bottom: 1px solid #eee;">${c.ageInYears}y ${c.ageInMonths % 12}m</td>
          <td style="padding: 8px; border-bottom: 1px solid #eee;">${c.careCategory === 'FullTime' ? 'Full-Time' : 'School-Age'}</td>
          <td style="padding: 8px; border-bottom: 1px solid #eee;">${c.behavioralProfile}</td>
          <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; font-weight: 600;">${c.projectedHours.toFixed(1)}</td>
          <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">${c.projectedAttendanceDays}</td>
          <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: center;">${c.isProrated ? 'Yes' : '-'}</td>
        </tr>
      `)
      .join('');
    
    const nameSyncNote = hasNameMappings 
      ? '<div style="background: #dcfce7; border: 1px solid #86efac; border-radius: 6px; padding: 8px 12px; margin-bottom: 16px; font-size: 11px; color: #166534;"><strong>✓ Portal Names Applied:</strong> Names transformed to Portal format from approved Name Sync mappings, sorted A-Z.</div>'
      : '';

    const printContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>${report.reportName} - Claim Report</title>
          <style>
            body {
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
              padding: 40px;
              color: #333;
              line-height: 1.5;
            }
            .header {
              border-bottom: 2px solid #333;
              padding-bottom: 20px;
              margin-bottom: 30px;
            }
            .header h1 {
              margin: 0 0 8px 0;
              font-size: 24px;
            }
            .header p {
              margin: 0;
              color: #666;
              font-size: 14px;
            }
            .stats {
              display: flex;
              gap: 40px;
              margin-bottom: 30px;
              flex-wrap: wrap;
            }
            .stat {
              text-align: center;
            }
            .stat-value {
              font-size: 28px;
              font-weight: bold;
              color: #333;
            }
            .stat-label {
              font-size: 12px;
              color: #666;
              text-transform: uppercase;
            }
            table {
              width: 100%;
              border-collapse: collapse;
              font-size: 12px;
            }
            th {
              background: #f5f5f5;
              padding: 10px 8px;
              text-align: left;
              font-weight: 600;
              border-bottom: 2px solid #ddd;
              text-transform: uppercase;
              font-size: 11px;
              color: #555;
            }
            th.right { text-align: right; }
            th.center { text-align: center; }
            .footer {
              margin-top: 30px;
              padding-top: 20px;
              border-top: 1px solid #ddd;
              font-size: 11px;
              color: #888;
              text-align: center;
            }
            @media print {
              body { padding: 20px; }
              .no-print { display: none; }
            }
          </style>
        </head>
        <body>
          <div class="header">
            <h1>${report.reportName}</h1>
            <p>${months[report.report.targetMonth - 1]} ${report.report.targetYear} • Created ${formatDate(report.created_at)}</p>
          </div>
          
          ${nameSyncNote}
          
          <div class="stats">
            <div class="stat">
              <div class="stat-value">${report.report.totalChildrenProcessed}</div>
              <div class="stat-label">Total Children</div>
            </div>
            <div class="stat">
              <div class="stat-value">${report.report.totalProjectedHours?.toFixed(1) || 0}</div>
              <div class="stat-label">Total Hours</div>
            </div>
            <div class="stat">
              <div class="stat-value">${report.report.averageHoursPerChild?.toFixed(1) || 0}</div>
              <div class="stat-label">Avg Hours/Child</div>
            </div>
            <div class="stat">
              <div class="stat-value">${report.report.fullTimeChildren || 0}</div>
              <div class="stat-label">Full-Time</div>
            </div>
            <div class="stat">
              <div class="stat-value">${report.report.schoolAgeChildren || 0}</div>
              <div class="stat-label">School-Age</div>
            </div>
            <div class="stat">
              <div class="stat-value">${report.report.proratedChildren || 0}</div>
              <div class="stat-label">Prorated</div>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Child Name</th>
                <th>Age</th>
                <th>Category</th>
                <th>Profile</th>
                <th class="right">Hours</th>
                <th class="right">Days</th>
                <th class="center">Prorated</th>
              </tr>
            </thead>
            <tbody>
              ${claimsRows}
            </tbody>
          </table>

          <div class="footer">
            Generated by CareSync • Printed on ${new Date().toLocaleDateString()}
          </div>
        </body>
      </html>
    `;

    printWindow.document.write(printContent);
    printWindow.document.close();
    
    // Wait for content to load then print
    printWindow.onload = () => {
      printWindow.focus();
      printWindow.print();
      printWindow.close();
    };
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 transition-opacity" onClick={onClose} />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden">
          {/* Header */}
          <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between z-10">
            <div>
              <h2 className="text-xl font-bold text-gray-900">
                {loading ? 'Loading...' : report?.reportName || 'Report Details'}
              </h2>
              {report && (
                <p className="text-sm text-gray-500 flex items-center mt-1">
                  <CalendarIcon className="h-4 w-4 mr-1" />
                  {months[report.report.targetMonth - 1]} {report.report.targetYear}
                  <span className="mx-2">•</span>
                  Created {formatDate(report.created_at)}
                </p>
              )}
            </div>
            <div className="flex items-center space-x-3">
              {report && (
                <>
                  <button
                    onClick={handlePrint}
                    className="btn btn-secondary flex items-center"
                  >
                    <PrinterIcon className="h-4 w-4 mr-2" />
                    Print
                  </button>
                  <button
                    onClick={downloadCSV}
                    className="btn btn-secondary flex items-center"
                  >
                    <DocumentArrowDownIcon className="h-4 w-4 mr-2" />
                    Export CSV
                  </button>
                  {onRegenerate && (
                    <button
                      onClick={() => onRegenerate(reportId)}
                      className="btn btn-primary flex items-center"
                    >
                      <ArrowPathIcon className="h-4 w-4 mr-2" />
                      Regenerate
                    </button>
                  )}
                </>
              )}
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <XMarkIcon className="h-5 w-5 text-gray-500" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="overflow-y-auto max-h-[calc(90vh-80px)] p-6">
            {loading && (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary-500 border-t-transparent mb-4"></div>
                <p className="text-gray-500">Loading report details...</p>
              </div>
            )}

            {error && (
              <div className="text-center py-16">
                <div className="bg-red-100 text-red-700 rounded-lg p-4 inline-block">
                  <p className="font-medium">Error loading report</p>
                  <p className="text-sm">{error.message}</p>
                </div>
              </div>
            )}

            {report && (
              <div className="space-y-6">
                {/* Summary Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                  <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-blue-500 rounded-lg">
                        <UserGroupIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-xs text-blue-600 font-medium">Total Children</p>
                        <p className="text-2xl font-bold text-blue-900">
                          {report.report.totalChildrenProcessed}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-purple-500 rounded-lg">
                        <ClockIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-xs text-purple-600 font-medium">Total Hours</p>
                        <p className="text-2xl font-bold text-purple-900">
                          {report.report.totalProjectedHours?.toFixed(1) || 0}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-4">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-green-500 rounded-lg">
                        <ChartBarIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-xs text-green-600 font-medium">Avg Hours/Child</p>
                        <p className="text-2xl font-bold text-green-900">
                          {report.report.averageHoursPerChild?.toFixed(1) || 0}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 rounded-xl p-4">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-indigo-500 rounded-lg">
                        <UserGroupIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-xs text-indigo-600 font-medium">Full-Time</p>
                        <p className="text-2xl font-bold text-indigo-900">
                          {report.report.fullTimeChildren || 0}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-teal-50 to-teal-100 rounded-xl p-4">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-teal-500 rounded-lg">
                        <UserGroupIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-xs text-teal-600 font-medium">School-Age</p>
                        <p className="text-2xl font-bold text-teal-900">
                          {report.report.schoolAgeChildren || 0}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl p-4">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-orange-500 rounded-lg">
                        <CalendarIcon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-xs text-orange-600 font-medium">Prorated</p>
                        <p className="text-2xl font-bold text-orange-900">
                          {report.report.proratedChildren || 0}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Filters */}
                <div className="bg-gray-50 rounded-xl p-4">
                  <div className="flex flex-wrap items-center gap-4">
                    <div className="flex-1 min-w-[200px]">
                      <div className="relative">
                        <MagnifyingGlassIcon className="h-5 w-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                        <input
                          type="text"
                          placeholder="Search by child name..."
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                          className="input pl-10 w-full"
                        />
                      </div>
                    </div>
                    <select
                      value={categoryFilter}
                      onChange={(e) => setCategoryFilter(e.target.value)}
                      className="input"
                    >
                      <option value="all">All Categories</option>
                      <option value="FullTime">Full-Time</option>
                      <option value="SchoolAge">School-Age</option>
                    </select>
                    <select
                      value={profileFilter}
                      onChange={(e) => setProfileFilter(e.target.value)}
                      className="input"
                    >
                      <option value="all">All Profiles</option>
                      <option value="consistent">Consistent</option>
                      <option value="variable">Variable</option>
                      <option value="oftenAbsent">Often Absent</option>
                    </select>
                    <span className="text-sm text-gray-500">
                      Showing {filteredClaims.length} of {report.report.claims.length} claims
                    </span>
                  </div>
                </div>

                {/* Claims Table */}
                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Child Name
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Age
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Category
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Profile
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Hours
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Days
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Avg/Day
                          </th>
                          <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                            Status
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {filteredClaims.map((claim, idx) => (
                          <tr key={idx} className="hover:bg-gray-50 transition-colors">
                            <td className="px-4 py-3">
                              <div className="font-medium text-gray-900">{claim.childName}</div>
                              {claim.enrollmentDate && (
                                <div className="text-xs text-gray-500">
                                  Enrolled: {new Date(claim.enrollmentDate).toLocaleDateString()}
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3 text-gray-600">
                              {claim.ageInYears}y {claim.ageInMonths % 12}m
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                                  claim.careCategory === 'FullTime'
                                    ? 'bg-blue-100 text-blue-700'
                                    : 'bg-teal-100 text-teal-700'
                                }`}
                              >
                                {claim.careCategory === 'FullTime' ? 'Full-Time' : 'School-Age'}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                                  claim.behavioralProfile === 'consistent'
                                    ? 'bg-emerald-100 text-emerald-700'
                                    : claim.behavioralProfile === 'variable'
                                    ? 'bg-amber-100 text-amber-700'
                                    : 'bg-red-100 text-red-700'
                                }`}
                              >
                                {claim.behavioralProfile === 'oftenAbsent'
                                  ? 'Often Absent'
                                  : claim.behavioralProfile.charAt(0).toUpperCase() +
                                    claim.behavioralProfile.slice(1)}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right font-semibold text-gray-900">
                              {claim.projectedHours.toFixed(1)}
                            </td>
                            <td className="px-4 py-3 text-right text-gray-600">
                              {claim.projectedAttendanceDays}
                            </td>
                            <td className="px-4 py-3 text-right text-gray-600">
                              {claim.calculationDetails?.averageHoursPerDay?.toFixed(1) || '-'}
                            </td>
                            <td className="px-4 py-3 text-center">
                              {claim.isProrated ? (
                                <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-orange-100 text-orange-700 font-medium">
                                  Prorated
                                </span>
                              ) : (
                                <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-gray-100 text-gray-600">
                                  Full Month
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {filteredClaims.length === 0 && (
                    <div className="text-center py-12 text-gray-500">
                      <MagnifyingGlassIcon className="h-8 w-8 mx-auto mb-2 text-gray-300" />
                      <p>No claims match your search criteria</p>
                    </div>
                  )}
                </div>

                {/* Description */}
                {report.description && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h4 className="text-sm font-medium text-gray-700 mb-2">Description</h4>
                    <p className="text-gray-600">{report.description}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReportDetailModal;
