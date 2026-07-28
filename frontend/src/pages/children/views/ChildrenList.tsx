// ============================================
// Children List View - Redesigned
// Uses same layout components as families module
// ============================================

/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlusIcon,
  UserIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import { UserIcon as UserSolidIcon } from '@heroicons/react/24/solid';

// Use same layout components as families module for consistency
import {
  PageContainer,
  PageHeader,
  StatsGrid,
  StatCard,
  SearchFilterBar,
  ContentCard,
  EmptyState,
  LoadingSkeleton,
} from '../../families/components/layout';

// Local Components
import { ChildCard, ChildRow } from '../components';

import { useApiQuery } from '../../../api/hooks';

// Stores
import { useUIStore, useFamilyStore } from '../../../stores';

// Local Imports
import type { ChildListItem } from '../types';
import { mapAgeGroup } from '../types';
import { AGE_GROUP_OPTIONS } from '../constants';

// -------------------- Main Component --------------------

const ChildrenList: React.FC = () => {
  const navigate = useNavigate();
  
  // Stores
  const { viewMode, setViewMode } = useUIStore();
  const { filters, setSearchTerm, setAgeGroupFilter } = useFamilyStore();
  
  const { data, loading, error, refetch } = useApiQuery<any[]>('/children', { limit: 1000 });
  const { data: statsData } = useApiQuery<any>('/families/stats');

  // Flatten children from all families
  const children: ChildListItem[] = (data || []).map((c: any) => ({
      id: c.id,
      firstName: c.first_name,
      lastName: c.last_name,
      dateOfBirth: c.date_of_birth,
      ageGroup: mapAgeGroup(c.age_group),
      familyName: c.family_name,
      familyId: c.family_id,
      status: c.is_active ? 'active' as const : 'inactive' as const,
      enrollmentDate: c.start_date,
    }));

  // Filter children
  const filteredChildren = children.filter((child) => {
    const matchesSearch = 
      child.firstName.toLowerCase().includes(filters.searchTerm.toLowerCase()) ||
      child.lastName.toLowerCase().includes(filters.searchTerm.toLowerCase()) ||
      child.familyName.toLowerCase().includes(filters.searchTerm.toLowerCase());
    const matchesAgeGroup = filters.ageGroupFilter === 'all' || child.ageGroup === filters.ageGroupFilter;
    return matchesSearch && matchesAgeGroup;
  });

  // Handlers
  const handleAddChild = () => navigate('/families/create?returnTo=/children');
  const handleChildClick = (childId: string) => navigate(`/children/${childId}`);

  // Render Content
  const renderContent = () => {
    if (loading) {
      return <LoadingSkeleton count={6} />;
    }

    if (error) {
      return (
        <ContentCard>
          <EmptyState
            icon={<UserSolidIcon className="w-8 h-8 text-red-400" />}
            title="Failed to load children"
            description="We couldn't fetch the children data. Please try again."
            action={{ label: 'Retry', onClick: () => refetch() }}
          />
        </ContentCard>
      );
    }

    if (children.length === 0) {
      return (
        <ContentCard>
          <EmptyState
            icon={<UserSolidIcon className="w-8 h-8 text-gray-400" />}
            title="No children registered"
            description="Start by registering a family. Children are added as part of a family registration."
            action={{
              label: 'Register Family',
              onClick: handleAddChild,
              icon: <PlusIcon className="w-5 h-5" />,
            }}
          />
        </ContentCard>
      );
    }

    if (filteredChildren.length === 0) {
      return (
        <ContentCard>
          <EmptyState
            icon={<UserSolidIcon className="w-8 h-8 text-gray-400" />}
            title="No matches found"
            description={`No children match your search "${filters.searchTerm}". Try a different search term.`}
            action={{ label: 'Clear Search', onClick: () => setSearchTerm('') }}
          />
        </ContentCard>
      );
    }

    if (viewMode === 'grid') {
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredChildren.map((child) => (
            <ChildCard 
              key={child.id} 
              child={child} 
              onClick={() => handleChildClick(child.id)}
            />
          ))}
        </div>
      );
    }

    return (
      <ContentCard noPadding>
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Child
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Age Group
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Family
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Enrolled
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredChildren.map((child) => (
              <ChildRow 
                key={child.id} 
                child={child}
                onClick={() => handleChildClick(child.id)}
              />
            ))}
          </tbody>
        </table>
      </ContentCard>
    );
  };

  // Use accurate stats from backend (falls back to calculated if not available)
  const activeChildrenLocal = children.filter(c => c.status === 'active');
  const activeChildrenCount = statsData?.active_children ?? activeChildrenLocal.length;
  const infantCount = statsData?.by_age_group?.Infant ?? activeChildrenLocal.filter(c => c.ageGroup === 'Infant').length;
  const toddlerCount = statsData?.by_age_group?.Toddler ?? activeChildrenLocal.filter(c => c.ageGroup === 'Toddler').length;
  const preschoolCount = statsData?.by_age_group?.Preschool ?? activeChildrenLocal.filter(c => c.ageGroup === 'Preschool').length;
  const schoolAgeCount = statsData?.by_age_group?.SchoolAge ?? statsData?.by_age_group?.['School-Age'] ?? activeChildrenLocal.filter(c => c.ageGroup === 'School-Age').length;

  return (
    <PageContainer>
      {/* Header */}
      <PageHeader
        title="Children"
        description="View and manage all enrolled children"
        icon={<UserSolidIcon className="w-6 h-6 text-white" />}
        actions={
          <button onClick={handleAddChild} className="btn btn-primary">
            <PlusIcon className="w-5 h-5" />
            Add Child
          </button>
        }
      />

      {/* Stats */}
      <StatsGrid columns={5}>
        <StatCard
          label="Active Children"
          value={activeChildrenCount}
          icon={<UsersIcon className="w-5 h-5" />}
          color="default"
        />
        <StatCard
          label="Infants"
          value={infantCount}
          icon={<UserIcon className="w-5 h-5" />}
          color="red"
        />
        <StatCard
          label="Toddlers"
          value={toddlerCount}
          icon={<UserIcon className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Preschool"
          value={preschoolCount}
          icon={<UserIcon className="w-5 h-5" />}
          color="purple"
        />
        <StatCard
          label="School-Age"
          value={schoolAgeCount}
          icon={<UserIcon className="w-5 h-5" />}
          color="green"
        />
      </StatsGrid>

      {/* Search & Filters */}
      <SearchFilterBar
        searchValue={filters.searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder="Search by name or family..."
        filters={[
          {
            value: filters.ageGroupFilter,
            onChange: setAgeGroupFilter,
            options: AGE_GROUP_OPTIONS,
          },
        ]}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
      />

      {/* Content */}
      {renderContent()}
    </PageContainer>
  );
};

export default ChildrenList;
