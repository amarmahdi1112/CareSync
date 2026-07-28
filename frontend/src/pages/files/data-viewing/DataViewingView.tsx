import React, { useState, useMemo } from 'react';
import { 
  ChartBarIcon, 
  CalendarDaysIcon, 
  MagnifyingGlassIcon,
  AdjustmentsHorizontalIcon,
  EllipsisVerticalIcon
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';

interface DataRecord {
  id: number;
  childName: string;
  family: string;
  attendanceRate: number;
  lastActivity: Date;
  status: 'active' | 'inactive' | 'pending';
}

const DataViewingView: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');

  const stats = {
    totalRegistrations: 156,
    activeChildren: 134,
    pendingApprovals: 12,
    familyGroups: 89,
  };

  const records: DataRecord[] = useMemo(() => [
    {
      id: 1,
      childName: 'Emma Johnson',
      family: 'Johnson Family',
      attendanceRate: 92,
      lastActivity: new Date(2025, 0, 12),
      status: 'active',
    },
    {
      id: 2,
      childName: 'Liam Smith',
      family: 'Smith Family',
      attendanceRate: 87,
      lastActivity: new Date(2025, 0, 11),
      status: 'active',
    },
    {
      id: 3,
      childName: 'Olivia Brown',
      family: 'Brown Family',
      attendanceRate: 95,
      lastActivity: new Date(2025, 0, 10),
      status: 'active',
    },
    {
      id: 4,
      childName: 'Noah Davis',
      family: 'Davis Family',
      attendanceRate: 78,
      lastActivity: new Date(2025, 0, 9),
      status: 'pending',
    },
    {
      id: 5,
      childName: 'Ava Wilson',
      family: 'Wilson Family',
      attendanceRate: 0,
      lastActivity: new Date(2025, 0, 5),
      status: 'inactive',
    },
  ], []);

  const filteredRecords = useMemo(() => {
    if (!searchQuery) {
      return records;
    }
    const query = searchQuery.toLowerCase();
    return records.filter(record =>
      record.childName.toLowerCase().includes(query) ||
      record.family.toLowerCase().includes(query)
    );
  }, [searchQuery, records]);

  const totalRecords = filteredRecords.length;
  const startIndex = totalRecords > 0 ? 1 : 0;
  const endIndex = totalRecords;

  const formatDate = (date: Date) => {
    return format(date, 'MMM d, yyyy');
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800';
      case 'inactive':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-yellow-100 text-yellow-800';
    }
  };

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Data Viewing</h1>
            <p className="mt-2 text-sm text-gray-600">
              View and analyze your data with interactive charts and detailed reports.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <button className="btn btn-secondary">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="mr-2">
                <path d="M10.0002 17.9167C13.7321 17.9167 15.5981 17.9167 16.7575 16.7573C17.9168 15.5979 17.9168 13.7319 17.9168 10C17.9168 6.26804 17.9168 4.40207 16.7575 3.2427C15.5981 2.08334 13.7321 2.08334 10.0002 2.08334C6.26821 2.08334 4.40224 2.08334 3.24286 3.2427C2.0835 4.40208 2.0835 6.26805 2.0835 10C2.0835 13.7319 2.0835 15.5979 3.24286 16.7573C4.40223 17.9167 6.2682 17.9167 10.0002 17.9167Z" stroke="#6F6B6C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M12.5 7.5L7.5 12.4997M12.5 12.5L7.5 7.50033" stroke="#6F6B6C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Export Data
            </button>
            <button className="btn btn-primary">
              Generate Report
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="ml-2">
                <path d="M13.3332 10H6.6665M13.3332 10C13.3332 9.4165 11.6713 8.32627 11.2498 7.91666M13.3332 10C13.3332 10.5835 11.6713 11.6737 11.2498 12.0833" stroke="#F7F2FA" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2.0835 10C2.0835 6.26805 2.0835 4.40208 3.24286 3.2427C4.40224 2.08334 6.26821 2.08334 10.0002 2.08334C13.7321 2.08334 15.5981 2.08334 16.7575 3.2427C17.9168 4.40208 17.9168 6.26805 17.9168 10C17.9168 13.7319 17.9168 15.5979 16.7575 16.7573C15.5981 17.9167 13.7321 17.9167 10.0002 17.9167C6.26821 17.9167 4.40224 17.9167 3.24286 16.7573C2.0835 15.5979 2.0835 13.7319 2.0835 10Z" stroke="#F7F2FA" strokeWidth="1.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <select className="form-select">
              <option>All Data Types</option>
              <option>Attendance Records</option>
              <option>Registration Data</option>
              <option>Claims Data</option>
            </select>
            
            <div className="flex items-center space-x-2 px-4 py-2 border border-gray-300 rounded-lg bg-white">
              <CalendarDaysIcon className="h-5 w-5 text-gray-400" />
              <span className="text-sm text-gray-700">Last 30 days</span>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <button className="btn btn-secondary btn-sm">
              <MagnifyingGlassIcon className="h-5 w-5" />
            </button>
            <button className="btn btn-secondary btn-sm">
              <AdjustmentsHorizontalIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Data Visualization Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Attendance Trends Chart */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-lg font-medium text-gray-900">Attendance Trends</h3>
          </div>
          <div className="card-body">
            <div className="h-64 flex items-center justify-center border-2 border-dashed border-gray-200 rounded-lg">
              <div className="text-center">
                <ChartBarIcon className="mx-auto h-12 w-12 text-gray-400" />
                <p className="mt-2 text-sm text-gray-500">Interactive chart will be displayed here</p>
              </div>
            </div>
          </div>
        </div>

        {/* Registration Statistics */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-lg font-medium text-gray-900">Registration Statistics</h3>
          </div>
          <div className="card-body">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Total Registrations</span>
                <span className="text-lg font-bold text-gray-900">{stats.totalRegistrations}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Active Children</span>
                <span className="text-lg font-bold text-green-600">{stats.activeChildren}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Pending Approvals</span>
                <span className="text-lg font-bold text-yellow-600">{stats.pendingApprovals}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Family Groups</span>
                <span className="text-lg font-bold text-primary-500">{stats.familyGroups}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Data Table */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-medium text-gray-900">Data Records</h3>
            <div className="flex items-center space-x-2">
              <input
                type="text"
                placeholder="Search records..."
                className="form-input w-64"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </div>
        <div className="card-body">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Child Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Family
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Attendance Rate
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Activity
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="relative px-6 py-3">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredRecords.map((record) => (
                  <tr key={record.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {record.childName}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {record.family}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <div className="flex items-center">
                        <div className="w-16 bg-gray-200 rounded-full h-2 mr-2">
                          <div
                            className="bg-green-500 h-2 rounded-full"
                            style={{ width: `${record.attendanceRate}%` }}
                          ></div>
                        </div>
                        <span>{record.attendanceRate}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDate(record.lastActivity)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${getStatusClass(record.status)}`}>
                        {record.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button className="btn btn-secondary btn-xs mr-3">
                        View
                      </button>
                      <button className="btn btn-secondary btn-xs">
                        <EllipsisVerticalIcon className="h-5 w-5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="mt-6 flex items-center justify-between">
            <div className="text-sm text-gray-500">
              Showing {startIndex} to {endIndex} of {totalRecords} results
            </div>
            <div className="flex items-center space-x-2">
              <button className="btn btn-secondary btn-sm">Previous</button>
              <button className="btn btn-secondary btn-sm">Next</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DataViewingView;
