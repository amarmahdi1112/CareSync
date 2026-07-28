import React from 'react';
import { Link } from 'react-router-dom';
import { 
  UsersIcon, 
  UserPlusIcon,
  Cog6ToothIcon,
  CurrencyDollarIcon,
  BuildingOffice2Icon,
  ArrowTrendingUpIcon,
  CalendarDaysIcon,
  ClockIcon,
  CheckCircleIcon,
  ArrowRightIcon,
  BanknotesIcon,
  ExclamationCircleIcon
} from '@heroicons/react/24/outline';
import { useAuth } from '../context/AuthContext';
import { useApiQuery } from '../api/hooks';
import { formatTimeAgo, formatTimeString } from '../utils/dateUtils';
import { usePreferences } from '../hooks/usePreferences';

interface FamilyStats {
  families: number;
  active_families: number;
  active_children: number;
}

interface ActivityItem {
  id: string;
  activity_type: string;
  description: string;
  user_name?: string;
  created_at: string;
}

interface InvoiceSummary {
  balance_due: number | string;
}

const Dashboard: React.FC = () => {
  const { state } = useAuth();
  const { preferences } = usePreferences();
  const user = state.user;
  const organization = state.organization;

  const { data: statsData, loading: loadingFamilies } = useApiQuery<FamilyStats>('/families/stats');
  const { data: activityData } = useApiQuery<ActivityItem[]>('/resources/activity_logs', {
    limit: 5,
    sort: 'created_at',
    order: 'desc',
  });
  const { data: invoiceData } = useApiQuery<InvoiceSummary[]>('/resources/invoices', { limit: 1000 });

  // Recent activity
  const recentActivity = activityData || [];

  // Use accurate stats from familyStats query
  const totalFamilies = statsData?.families || 0;
  const totalChildren = statsData?.active_children || 0;
  const activeFamilies = statsData?.active_families || 0;
  const totalOutstanding = (invoiceData || []).reduce(
    (sum, invoice) => sum + Number(invoice.balance_due || 0),
    0,
  );

  // Get current date info
  const now = new Date();
  const greeting = now.getHours() < 12 ? 'Good morning' : now.getHours() < 17 ? 'Good afternoon' : 'Good evening';
  const dateStr = now.toLocaleDateString('en-US', { 
    weekday: 'long', 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric' 
  });

  return (
    <div className="space-y-6">
      {/* Welcome Header */}
      <div className="bg-gradient-to-r from-primary-600 to-primary-700 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">
              {greeting}, {user?.firstName || 'there'}!
            </h1>
            <p className="mt-1 text-primary-100">
              {dateStr}
            </p>
            {organization && (
              <div className="mt-3 flex items-center gap-2 text-primary-100">
                <BuildingOffice2Icon className="h-4 w-4" />
                <span>{organization.name}</span>
              </div>
            )}
          </div>
          <div className="hidden md:block">
            <div className="bg-white/10 rounded-lg p-4 backdrop-blur-sm">
              <p className="text-sm text-primary-100">Quick Tip</p>
              <p className="text-sm mt-1">Use the sidebar to navigate between sections</p>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Total Families */}
        <div className="bg-white overflow-hidden shadow-sm rounded-xl border border-gray-200 hover:shadow-md transition-shadow">
          <div className="p-5">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-blue-100 rounded-lg">
                <UsersIcon className="h-6 w-6 text-blue-600" />
              </div>
              {totalFamilies > 0 && (
                <span className="flex items-center text-xs text-green-600 font-medium">
                  <ArrowTrendingUpIcon className="h-3 w-3 mr-1" />
                  Active
                </span>
              )}
            </div>
            <div className="mt-4">
              <p className="text-2xl font-bold text-gray-900">
                {loadingFamilies ? '...' : totalFamilies}
              </p>
              <p className="text-sm text-gray-500">Total Families</p>
            </div>
          </div>
        </div>

        {/* Total Children */}
        <div className="bg-white overflow-hidden shadow-sm rounded-xl border border-gray-200 hover:shadow-md transition-shadow">
          <div className="p-5">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-purple-100 rounded-lg">
                <UserPlusIcon className="h-6 w-6 text-purple-600" />
              </div>
              {totalChildren > 0 && (
                <span className="flex items-center text-xs text-green-600 font-medium">
                  <ArrowTrendingUpIcon className="h-3 w-3 mr-1" />
                  Enrolled
                </span>
              )}
            </div>
            <div className="mt-4">
              <p className="text-2xl font-bold text-gray-900">
                {loadingFamilies ? '...' : totalChildren}
              </p>
              <p className="text-sm text-gray-500">Total Children</p>
            </div>
          </div>
        </div>

        {/* Active Families */}
        <div className="bg-white overflow-hidden shadow-sm rounded-xl border border-gray-200 hover:shadow-md transition-shadow">
          <div className="p-5">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-green-100 rounded-lg">
                <CheckCircleIcon className="h-6 w-6 text-green-600" />
              </div>
            </div>
            <div className="mt-4">
              <p className="text-2xl font-bold text-gray-900">
                {loadingFamilies ? '...' : activeFamilies}
              </p>
              <p className="text-sm text-gray-500">Active Families</p>
            </div>
          </div>
        </div>

        {/* Invoice Stats */}
        <Link to="/invoicing" className="bg-white overflow-hidden shadow-sm rounded-xl border border-gray-200 hover:shadow-md transition-shadow block">
          <div className="p-5">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-yellow-100 rounded-lg">
                <BanknotesIcon className="h-6 w-6 text-yellow-600" />
              </div>
              {totalOutstanding > 0 && (
                <span className="flex items-center text-xs text-orange-600 font-medium">
                  <ExclamationCircleIcon className="h-3 w-3 mr-1" />
                  Outstanding
                </span>
              )}
            </div>
            <div className="mt-4">
              <p className="text-2xl font-bold text-gray-900">
                ${totalOutstanding.toFixed(0)}
              </p>
              <p className="text-sm text-gray-500">Outstanding Balance</p>
            </div>
          </div>
        </Link>
      </div>

      {/* Bottom Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Quick Actions */}
        <div className="bg-white shadow-sm rounded-xl border border-gray-200">
          <div className="px-5 py-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Quick Actions</h3>
          </div>
          <div className="p-5 space-y-3">
            <Link 
              to="/families/create" 
              className="flex items-center p-3 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors"
            >
              <div className="p-2 bg-primary-100 rounded-lg mr-3">
                <UserPlusIcon className="w-5 h-5 text-primary-600" />
              </div>
              <div>
                <span className="text-sm font-medium text-gray-900">Register Family</span>
                <p className="text-xs text-gray-500">Add a new family</p>
              </div>
              <ArrowRightIcon className="w-4 h-4 text-gray-400 ml-auto" />
            </Link>

            <Link 
              to="/families" 
              className="flex items-center p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="p-2 bg-blue-100 rounded-lg mr-3">
                <UsersIcon className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <span className="text-sm font-medium text-gray-900">View Families</span>
                <p className="text-xs text-gray-500">Manage all families</p>
              </div>
              <ArrowRightIcon className="w-4 h-4 text-gray-400 ml-auto" />
            </Link>

            <Link 
              to="/invoicing" 
              className="flex items-center p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="p-2 bg-yellow-100 rounded-lg mr-3">
                <CurrencyDollarIcon className="w-5 h-5 text-yellow-600" />
              </div>
              <div>
                <span className="text-sm font-medium text-gray-900">Create Invoice</span>
                <p className="text-xs text-gray-500">Bill families</p>
              </div>
              <ArrowRightIcon className="w-4 h-4 text-gray-400 ml-auto" />
            </Link>

            <Link 
              to="/settings" 
              className="flex items-center p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="p-2 bg-gray-100 rounded-lg mr-3">
                <Cog6ToothIcon className="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <span className="text-sm font-medium text-gray-900">Settings</span>
                <p className="text-xs text-gray-500">Configure your account</p>
              </div>
              <ArrowRightIcon className="w-4 h-4 text-gray-400 ml-auto" />
            </Link>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="lg:col-span-2 bg-white shadow-sm rounded-xl border border-gray-200">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Recent Activity</h3>
            <Link to="/activity" className="text-sm text-primary-600 hover:text-primary-700">View all</Link>
          </div>
          <div className="p-5">
            {recentActivity.length > 0 ? (
              <div className="space-y-3 mb-6">
                {recentActivity.map((activity) => (
                  <div key={activity.id} className="flex items-start gap-3 text-sm">
                    <div className="w-2 h-2 mt-1.5 rounded-full bg-primary-500 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-gray-700 truncate">{activity.description}</p>
                      <p className="text-xs text-gray-400">{activity.user_name} • {formatTimeAgo(activity.created_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500 mb-6">No recent activity yet.</p>
            )}
            
            <h4 className="text-sm font-medium text-gray-700 mb-3">Getting Started</h4>
            <div className="space-y-4">
              {/* Step 1 */}
              <div className="flex items-start gap-4">
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  organization ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
                }`}>
                  {organization ? <CheckCircleIcon className="w-5 h-5" /> : '1'}
                </div>
                <div className="flex-1">
                  <p className={`font-medium ${organization ? 'text-green-600' : 'text-gray-900'}`}>
                    Set up your organization
                  </p>
                  <p className="text-sm text-gray-500">Configure your organization profile, logo, and business hours</p>
                  {!organization && (
                    <Link to="/settings/organization" className="text-sm text-primary-600 hover:text-primary-700 mt-1 inline-block">
                      Complete setup →
                    </Link>
                  )}
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex items-start gap-4">
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  totalFamilies > 0 ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
                }`}>
                  {totalFamilies > 0 ? <CheckCircleIcon className="w-5 h-5" /> : '2'}
                </div>
                <div className="flex-1">
                  <p className={`font-medium ${totalFamilies > 0 ? 'text-green-600' : 'text-gray-900'}`}>
                    Register your first family
                  </p>
                  <p className="text-sm text-gray-500">Add families and children to start managing enrollments</p>
                  {totalFamilies === 0 && (
                    <Link to="/families/create" className="text-sm text-primary-600 hover:text-primary-700 mt-1 inline-block">
                      Add a family →
                    </Link>
                  )}
                </div>
              </div>

              {/* Step 3 */}
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-gray-100 text-gray-400">
                  3
                </div>
                <div className="flex-1">
                  <p className="font-medium text-gray-900">Create your first invoice</p>
                  <p className="text-sm text-gray-500">Set up billing and send invoices to families</p>
                  <Link to="/invoicing" className="text-sm text-primary-600 hover:text-primary-700 mt-1 inline-block">
                    Go to invoicing →
                  </Link>
                </div>
              </div>

              {/* Step 4 */}
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-gray-100 text-gray-400">
                  4
                </div>
                <div className="flex-1">
                  <p className="font-medium text-gray-900">Invite your team</p>
                  <p className="text-sm text-gray-500">Add staff members and set their roles and permissions</p>
                  <Link to="/settings/users" className="text-sm text-primary-600 hover:text-primary-700 mt-1 inline-block">
                    Manage team →
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Organization Info Bar */}
      {organization && (
        <div className="bg-white shadow-sm rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-sm">
                <ClockIcon className="h-4 w-4 text-gray-400" />
                <span className="text-gray-600">Hours:</span>
                <span className="font-medium text-gray-900">
                  {formatTimeString(organization.opening_time, preferences.timeFormat)} - {formatTimeString(organization.closing_time, preferences.timeFormat)}
                </span>
              </div>
              <div className="h-4 w-px bg-gray-200" />
              <div className="flex items-center gap-2 text-sm">
                <CalendarDaysIcon className="h-4 w-4 text-gray-400" />
                <span className="text-gray-600">Type:</span>
                <span className="font-medium text-gray-900 capitalize">
                  {organization.organization_type?.replace('_', ' ') || '—'}
                </span>
              </div>
              <div className="h-4 w-px bg-gray-200" />
              <div className="flex items-center gap-2 text-sm">
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                  organization.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                }`}>
                  {organization.status || 'pending'}
                </span>
              </div>
            </div>
            <Link to="/settings/organization" className="text-sm text-primary-600 hover:text-primary-700 font-medium">
              Edit Organization →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
