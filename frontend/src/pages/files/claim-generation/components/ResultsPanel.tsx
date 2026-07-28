import React, { useState } from 'react';
import {
  DocumentArrowDownIcon,
  ArrowPathIcon,
  ChartBarIcon,
  UserGroupIcon,
  ClockIcon,
  CheckCircleIcon,
  MagnifyingGlassIcon,
  FolderIcon,
} from '@heroicons/react/24/outline';
import type { ClaimConfig } from '../types';

interface Claim {
  childId: string;
  childName: string;
  careCategory: string;
  projectedHours: number;
  projectedAttendanceDays: number;
  behavioralProfile: string;
  isProrated: boolean;
}

interface ResultsPanelProps {
  result: {
    id: string;
    reportName: string;
    totalChildren: number;
    totalProjectedHours: number;
    claims: Claim[];
  };
  config: ClaimConfig;
  onNewGeneration: () => void;
  onViewSavedReports?: () => void;
}

const ResultsPanel: React.FC<ResultsPanelProps> = ({ result, config, onNewGeneration, onViewSavedReports }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const filteredClaims = result.claims.filter(claim => {
    const matchesSearch = claim.childName.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = categoryFilter === 'all' || claim.careCategory === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const fullTimeCount = result.claims.filter(c => c.careCategory === 'FullTime').length;
  const schoolAgeCount = result.claims.filter(c => c.careCategory === 'SchoolAge').length;
  const proratedCount = result.claims.filter(c => c.isProrated).length;

  const downloadCSV = () => {
    const headers = ['Child Name', 'Care Category', 'Projected Hours', 'Attendance Days', 'Behavioral Profile', 'Prorated'];
    const rows = result.claims.map(c => [
      c.childName,
      c.careCategory,
      c.projectedHours.toFixed(2),
      c.projectedAttendanceDays,
      c.behavioralProfile,
      c.isProrated ? 'Yes' : 'No'
    ]);

    const csvContent = [headers, ...rows].map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `claims_${months[config.month - 1]}_${config.year}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Success Banner */}
      <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <CheckCircleIcon className="h-6 w-6 text-green-500" />
          <div>
            <h3 className="font-semibold text-green-800">Claims Generated Successfully</h3>
            <p className="text-sm text-green-600">
              Report ID: {result.id.slice(0, 8)}... | {months[config.month - 1]} {config.year}
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <button onClick={downloadCSV} className="btn btn-secondary">
            <DocumentArrowDownIcon className="h-5 w-5 mr-2" />
            Download CSV
          </button>
          {onViewSavedReports && (
            <button onClick={onViewSavedReports} className="btn btn-secondary">
              <FolderIcon className="h-5 w-5 mr-2" />
              View Saved Reports
            </button>
          )}
          <button onClick={onNewGeneration} className="btn btn-primary">
            <ArrowPathIcon className="h-5 w-5 mr-2" />
            New Generation
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <UserGroupIcon className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Total Children</p>
              <p className="text-2xl font-bold text-gray-900">{result.totalChildren}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-purple-100 rounded-lg">
              <ClockIcon className="h-5 w-5 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Total Hours</p>
              <p className="text-2xl font-bold text-gray-900">{result.totalProjectedHours.toFixed(1)}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-green-100 rounded-lg">
              <ChartBarIcon className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Full-Time / School-Age</p>
              <p className="text-2xl font-bold text-gray-900">{fullTimeCount} / {schoolAgeCount}</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-orange-100 rounded-lg">
              <ChartBarIcon className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Prorated</p>
              <p className="text-2xl font-bold text-gray-900">{proratedCount}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Claims Table */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Generated Claims</h3>
            <div className="flex items-center space-x-3">
              <div className="relative">
                <MagnifyingGlassIcon className="h-5 w-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search children..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="input pl-10 w-64"
                />
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
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Child Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Category</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Hours</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Days</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Profile</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Prorated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredClaims.map((claim, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{claim.childName}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      claim.careCategory === 'FullTime' 
                        ? 'bg-blue-100 text-blue-800' 
                        : 'bg-green-100 text-green-800'
                    }`}>
                      {claim.careCategory}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-900">{claim.projectedHours.toFixed(1)}</td>
                  <td className="px-4 py-3 text-right text-gray-900">{claim.projectedAttendanceDays}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      claim.behavioralProfile === 'consistent' ? 'bg-emerald-100 text-emerald-800' :
                      claim.behavioralProfile === 'variable' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                      {claim.behavioralProfile}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {claim.isProrated && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-orange-100 text-orange-800">
                        Yes
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredClaims.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No claims match your search criteria
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultsPanel;
