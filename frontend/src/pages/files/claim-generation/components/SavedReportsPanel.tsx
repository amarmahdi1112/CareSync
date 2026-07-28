import React, { useState } from 'react';
import {
  DocumentTextIcon,
  TrashIcon,
  EyeIcon,
  ArrowDownTrayIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  ClockIcon,
  UserGroupIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';
import { api } from '../../../../api/client';
import { useApiQuery } from '../../../../api/hooks';
import { useNotificationStore } from '../../../../stores';

interface SavedReport {
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
  };
}

interface SavedReportRow {
  id: string;
  report_name: string;
  created_at: string;
  created_by?: string;
  description?: string;
  target_month: number;
  target_year: number;
  total_children_processed: number;
  total_projected_hours: number;
}

interface SavedReportsPanelProps {
  onViewReport?: (reportId: string) => void;
}

const SavedReportsPanel: React.FC<SavedReportsPanelProps> = ({ onViewReport }) => {
  const { success, error: showError } = useNotificationStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [yearFilter, setYearFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'date' | 'name' | 'hours'>('date');
  
  const { data, loading, refetch } = useApiQuery<SavedReportRow[]>('/resources/generated_claim_reports', {
    limit: 1000,
    sort: 'created_at',
    order: 'desc',
  });

  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const handleDelete = async (id: string, name: string) => {
    if (window.confirm(`Are you sure you want to delete "${name}"?`)) {
      try {
        await api.resources.remove('generated_claim_reports', id);
        success('Report Deleted', 'The report has been deleted successfully');
        await refetch();
      } catch (caught) {
        showError('Delete Failed', caught instanceof Error ? caught.message : 'Request failed');
      }
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatRelativeDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    return formatDate(dateString);
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
        <div className="animate-spin rounded-full h-10 w-10 border-4 border-primary-500 border-t-transparent mx-auto"></div>
        <p className="mt-4 text-gray-500">Loading saved reports...</p>
      </div>
    );
  }

  const allReports: SavedReport[] = (data || []).map((row) => ({
    id: row.id,
    reportName: row.report_name,
    created_at: row.created_at,
    createdBy: row.created_by || 'System',
    description: row.description,
    report: {
      targetMonth: row.target_month,
      targetYear: row.target_year,
      totalChildrenProcessed: row.total_children_processed,
      totalProjectedHours: Number(row.total_projected_hours),
    },
  }));
  
  // Get unique years for filter
  const years = [...new Set(allReports.map(r => r.report.targetYear))].sort((a, b) => b - a);
  
  // Filter and sort reports
  const filteredReports = allReports
    .filter(report => {
      const matchesSearch = report.reportName.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesYear = yearFilter === 'all' || report.report.targetYear === parseInt(yearFilter);
      return matchesSearch && matchesYear;
    })
    .sort((a, b) => {
      if (sortBy === 'date') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (sortBy === 'name') {
        return a.reportName.localeCompare(b.reportName);
      }
      if (sortBy === 'hours') {
        return (b.report.totalProjectedHours || 0) - (a.report.totalProjectedHours || 0);
      }
      return 0;
    });

  // Calculate summary stats
  const totalReports = allReports.length;
  const totalHours = allReports.reduce((sum, r) => sum + (r.report.totalProjectedHours || 0), 0);
  const totalChildren = allReports.reduce((sum, r) => sum + (r.report.totalChildrenProcessed || 0), 0);

  if (allReports.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <DocumentTextIcon className="h-8 w-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">No Saved Reports</h3>
        <p className="text-gray-500 max-w-sm mx-auto">
          Generate your first claim report using the "Generate Claims" tab to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4 border border-blue-200">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-500 rounded-lg">
              <DocumentTextIcon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-sm text-blue-600 font-medium">Total Reports</p>
              <p className="text-2xl font-bold text-blue-900">{totalReports}</p>
            </div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4 border border-purple-200">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-purple-500 rounded-lg">
              <ClockIcon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-sm text-purple-600 font-medium">Total Hours Generated</p>
              <p className="text-2xl font-bold text-purple-900">{totalHours.toLocaleString()}</p>
            </div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-4 border border-green-200">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-green-500 rounded-lg">
              <UserGroupIcon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-sm text-green-600 font-medium">Total Children Processed</p>
              <p className="text-2xl font-bold text-green-900">{totalChildren.toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-[200px]">
            <div className="relative">
              <MagnifyingGlassIcon className="h-5 w-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search reports..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="input pl-10 w-full"
              />
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <FunnelIcon className="h-5 w-5 text-gray-400" />
            <select
              value={yearFilter}
              onChange={(e) => setYearFilter(e.target.value)}
              className="input"
            >
              <option value="all">All Years</option>
              {years.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center space-x-2">
            <ChartBarIcon className="h-5 w-5 text-gray-400" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'date' | 'name' | 'hours')}
              className="input"
            >
              <option value="date">Sort by Date</option>
              <option value="name">Sort by Name</option>
              <option value="hours">Sort by Hours</option>
            </select>
          </div>
          <span className="text-sm text-gray-500">
            {filteredReports.length} of {allReports.length} reports
          </span>
        </div>
      </div>

      {/* Reports List */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="divide-y divide-gray-100">
          {filteredReports.map((savedReport) => (
            <div
              key={savedReport.id}
              className="px-6 py-4 hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4 flex-1 min-w-0">
                  <div className="p-3 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl">
                    <DocumentTextIcon className="h-6 w-6 text-primary-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center space-x-2">
                      <h4 className="font-semibold text-gray-900 truncate">{savedReport.reportName}</h4>
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                        {months[savedReport.report.targetMonth - 1]} {savedReport.report.targetYear}
                      </span>
                    </div>
                    <div className="flex items-center space-x-4 mt-1.5">
                      <span className="text-sm text-gray-500 flex items-center">
                        <UserGroupIcon className="h-4 w-4 mr-1 text-gray-400" />
                        {savedReport.report.totalChildrenProcessed} children
                      </span>
                      <span className="text-sm text-gray-500 flex items-center">
                        <ClockIcon className="h-4 w-4 mr-1 text-gray-400" />
                        {savedReport.report.totalProjectedHours?.toFixed(1) || 0} hours
                      </span>
                      <span className="text-sm text-gray-400">
                        {formatRelativeDate(savedReport.created_at)}
                      </span>
                    </div>
                    {savedReport.description && (
                      <p className="text-sm text-gray-500 mt-1 truncate">{savedReport.description}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center space-x-1 ml-4">
                  {onViewReport && (
                    <button
                      onClick={() => onViewReport(savedReport.id)}
                      className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                      title="View Report Details"
                    >
                      <EyeIcon className="h-5 w-5" />
                    </button>
                  )}
                  <button
                    onClick={() => onViewReport?.(savedReport.id)}
                    className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="Download CSV"
                  >
                    <ArrowDownTrayIcon className="h-5 w-5" />
                  </button>
                  <button
                    onClick={() => handleDelete(savedReport.id, savedReport.reportName)}
                    className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="Delete Report"
                  >
                    <TrashIcon className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {filteredReports.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <MagnifyingGlassIcon className="h-8 w-8 mx-auto mb-2 text-gray-300" />
            <p>No reports match your search criteria</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SavedReportsPanel;
