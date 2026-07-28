import React, { useState } from 'react';
import {
  ClockIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  UserCircleIcon,
  UserPlusIcon,
  DocumentTextIcon,
  CurrencyDollarIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  PencilSquareIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline';
import { useApiQuery } from '../api/hooks';
import { formatTimestampDetailed, getDateGroupLabel } from '../utils/dateUtils';

type ActivityType = string;

interface ActivityItem {
  id: string;
  activity_type: string;
  description: string;
  user_name?: string;
  user_email?: string;
  created_at: string | number;
  entity_type?: string;
  entity_id?: string;
  entity_name?: string;
  metadata?: Record<string, unknown>;
}

const activityTypeConfig: Record<ActivityType, { icon: React.ElementType; color: string; bgColor: string }> = {
  'user.login': { icon: ArrowRightOnRectangleIcon, color: 'text-green-600', bgColor: 'bg-green-100' },
  'user.logout': { icon: ArrowRightOnRectangleIcon, color: 'text-gray-600', bgColor: 'bg-gray-100' },
  'user.created': { icon: UserPlusIcon, color: 'text-blue-600', bgColor: 'bg-blue-100' },
  'user.password_changed': { icon: Cog6ToothIcon, color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
  'family.created': { icon: UserCircleIcon, color: 'text-purple-600', bgColor: 'bg-purple-100' },
  'family.updated': { icon: PencilSquareIcon, color: 'text-blue-600', bgColor: 'bg-blue-100' },
  'child.created': { icon: UserPlusIcon, color: 'text-pink-600', bgColor: 'bg-pink-100' },
  'invoice.created': { icon: DocumentTextIcon, color: 'text-orange-600', bgColor: 'bg-orange-100' },
  'invoice.paid': { icon: CurrencyDollarIcon, color: 'text-green-600', bgColor: 'bg-green-100' },
  'settings.updated': { icon: Cog6ToothIcon, color: 'text-gray-600', bgColor: 'bg-gray-100' },
};

const filterOptions = [
  { value: 'all', label: 'All Activities' },
  { value: 'user', label: 'User Actions' },
  { value: 'family', label: 'Family Changes' },
  { value: 'invoice', label: 'Billing' },
  { value: 'settings', label: 'Settings' },
];

const ActivityLog: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const { data, loading, refetch } = useApiQuery<ActivityItem[]>('/resources/activity_logs', {
    search: searchQuery || undefined,
    limit,
    offset,
    sort: 'created_at',
    order: 'desc',
  });

  const activities = (data || []).filter((activity) =>
    filterType === 'all' || activity.activity_type.startsWith(filterType),
  );
  const hasMore = (data?.length || 0) === limit;

  const filteredActivities = activities;

  const groupActivitiesByDate = (items: ActivityItem[]) => {
    const groups: Record<string, ActivityItem[]> = {};
    
    items.forEach(item => {
      const key = getDateGroupLabel(item.created_at);
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(item);
    });
    
    return groups;
  };

  const groupedActivities = groupActivitiesByDate(filteredActivities);

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      {/* Header */}
      <div className="mb-8">
        <h1 className="heading-lg text-gray-900 flex items-center gap-3">
          <ClockIcon className="h-8 w-8 text-gray-600" />
          Activity Log
        </h1>
        <p className="mt-2 body-md text-gray-600">
          Track all actions and changes made in your organization.
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search activities..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          {/* Filter */}
          <div className="flex items-center gap-2">
            <FunnelIcon className="h-5 w-5 text-gray-400" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            >
              {filterOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>

          {/* Refresh */}
          <button onClick={() => refetch()} className="btn btn-secondary">
            <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Activity List */}
      <div className="space-y-6">
        {loading && activities.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
            <p className="mt-4 text-gray-500">Loading activities...</p>
          </div>
        ) : Object.keys(groupedActivities).length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
            <ClockIcon className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">No activities found</p>
          </div>
        ) : (
          Object.entries(groupedActivities).map(([date, items]) => (
            <div key={date}>
              <h3 className="text-sm font-medium text-gray-500 mb-3">{date}</h3>
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                <div className="divide-y divide-gray-100">
                  {items.map((activity) => {
                    const typeKey = activity.activity_type.replace(/_/g, '.');
                    const config = activityTypeConfig[typeKey] || { icon: ClockIcon, color: 'text-gray-600', bgColor: 'bg-gray-100' };
                    const Icon = config.icon;
                    
                    return (
                      <div key={activity.id} className="p-4 hover:bg-gray-50 transition-colors">
                        <div className="flex items-start gap-4">
                          {/* Icon */}
                          <div className={`flex-shrink-0 p-2 rounded-lg ${config.bgColor}`}>
                            <Icon className={`h-5 w-5 ${config.color}`} />
                          </div>
                          
                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-gray-900">{activity.description}</p>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="text-xs text-gray-500">
                                by <span className="font-medium">{activity.user_name || 'System'}</span>
                              </span>
                              <span className="text-xs text-gray-400">•</span>
                              <span className="text-xs text-gray-400">{activity.user_email || ''}</span>
                            </div>
                          </div>
                          
                          {/* Timestamp */}
                          <div className="flex-shrink-0 text-xs text-gray-400">
                            {formatTimestampDetailed(activity.created_at)}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Load More */}
      {hasMore && (
        <div className="mt-6 text-center">
          <button 
            onClick={() => setOffset(prev => prev + limit)}
            className="btn btn-secondary"
          >
            Load More Activities
          </button>
        </div>
      )}

      {/* Info Banner */}
      <div className="mt-8 bg-blue-50 rounded-xl p-6 border border-blue-200">
        <div className="flex items-start gap-3">
          <ClockIcon className="h-6 w-6 text-blue-600 flex-shrink-0" />
          <div>
            <h3 className="font-medium text-blue-900">Activity Retention</h3>
            <p className="mt-1 text-sm text-blue-800">
              Activity logs are retained for 2 years. Older logs are automatically archived.
              For compliance reports or extended log access, contact support.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ActivityLog;
