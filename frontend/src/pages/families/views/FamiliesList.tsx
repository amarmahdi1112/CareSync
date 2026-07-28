// ============================================
// Families List View - Redesigned
// ============================================

/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlusIcon,
  ArrowUpTrayIcon,
  UserGroupIcon,
  UsersIcon,
  ClockIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { UserGroupIcon as UserGroupSolidIcon } from '@heroicons/react/24/solid';

import { useApiQuery } from '../../../api/hooks';

// Zustand stores
import { useUIStore, useFamilyStore } from '../../../stores';

// Types
import type { FamilyListItem, AgeGroup } from '../types';

// Constants
import { FAMILY_STATUS_OPTIONS } from '../constants';

// Components
import {
  PageContainer,
  PageHeader,
  StatsGrid,
  StatCard,
  SearchFilterBar,
  ContentCard,
  EmptyState,
  LoadingSkeleton,
} from '../components/layout';
import { FamilyCard, FamilyRow } from '../components/cards';

// Map age group from GraphQL
const mapAgeGroup = (ageGroup?: string): AgeGroup => {
  if (!ageGroup) return 'Preschool';
  if (ageGroup === 'SchoolAge') return 'School-Age';
  return ageGroup as AgeGroup;
};

const FamiliesList: React.FC = () => {
  const navigate = useNavigate();
  
  // Zustand stores
  const { viewMode, setViewMode } = useUIStore();
  const { filters, setSearchTerm, setStatusFilter } = useFamilyStore();
  
  const { data, loading, error, refetch } = useApiQuery<any[]>('/families', {
    limit: 500,
    status: filters.statusFilter !== 'all' ? filters.statusFilter : undefined,
  });
  const { data: stats } = useApiQuery<any>('/families/stats');

  // Map GraphQL data to UI format
  const families: FamilyListItem[] = (data || []).map((f: any) => {
    const primaryGuardian = f.guardians?.find((g: any) => g.guardian_type === 'primary');
    return {
      id: f.id,
      name: f.name,
      status: f.status,
      childCount: f.children?.filter((c: any) => c.is_active)?.length || 0,
      children: (f.children || []).map((c: any) => ({
        id: c.id,
        firstName: c.first_name,
        lastName: c.last_name,
        ageGroup: mapAgeGroup(c.age_group),
        isActive: c.is_active,
      })),
      primaryContact: primaryGuardian ? {
        name: `${primaryGuardian.first_name} ${primaryGuardian.last_name}`,
        phone: primaryGuardian.cell_phone,
        email: primaryGuardian.email,
      } : { name: 'No primary contact', phone: '', email: '' },
      createdAt: f.created_at,
    };
  });

  // Filter families by search term
  const filteredFamilies = families.filter((family) => {
    if (!filters.searchTerm) return true;
    const search = filters.searchTerm.toLowerCase();
    return family.name.toLowerCase().includes(search) ||
      family.primaryContact.name.toLowerCase().includes(search) ||
      family.children.some(c => 
        c.firstName.toLowerCase().includes(search) ||
        c.lastName.toLowerCase().includes(search)
      );
  });

  // Calculate stats
  const allFamilies = data || [];
  const totalFamilies = stats?.families ?? allFamilies.length;
  const activeFamilies = stats?.active_families ?? allFamilies.filter((f: any) => f.status === 'active').length;
  const pendingFamilies = stats?.pending_families ?? allFamilies.filter((f: any) => f.status === 'pending').length;
  const totalChildren = stats?.active_children ?? allFamilies.reduce((acc: number, f: any) => acc + (f.children?.filter((c: any) => c.is_active)?.length || 0), 0);

  // Handlers
  const handleCreateFamily = () => navigate('/families/create');
  const handleFamilyClick = (familyId: string) => navigate(`/families/${familyId}`);

  // Render content
  const renderContent = () => {
    if (loading) {
      return <LoadingSkeleton count={6} />;
    }

    if (error) {
      return (
        <ContentCard>
          <EmptyState
            icon={<UserGroupSolidIcon className="w-8 h-8 text-red-400" />}
            title="Failed to load families"
            description="We couldn't fetch the family data. Please try again."
            action={{ label: 'Retry', onClick: () => refetch() }}
          />
        </ContentCard>
      );
    }

    if (families.length === 0) {
      return (
        <ContentCard>
          <EmptyState
            icon={<UserGroupSolidIcon className="w-8 h-8 text-gray-400" />}
            title="No families yet"
            description="Get started by registering your first family. You can add guardians and children once the family is created."
            action={{
              label: 'Add First Family',
              onClick: handleCreateFamily,
              icon: <PlusIcon className="w-5 h-5" />,
            }}
          />
        </ContentCard>
      );
    }

    if (filteredFamilies.length === 0) {
      return (
        <ContentCard>
          <EmptyState
            icon={<UserGroupIcon className="w-8 h-8 text-gray-400" />}
            title="No results found"
            description={`No families match "${filters.searchTerm}". Try a different search term.`}
            action={{ label: 'Clear search', onClick: () => setSearchTerm('') }}
          />
        </ContentCard>
      );
    }

    if (viewMode === 'grid') {
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredFamilies.map((family) => (
            <FamilyCard
              key={family.id}
              family={family}
              onClick={() => handleFamilyClick(family.id)}
            />
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {filteredFamilies.map((family) => (
          <FamilyRow
            key={family.id}
            family={family}
            onClick={() => handleFamilyClick(family.id)}
          />
        ))}
      </div>
    );
  };

  return (
    <PageContainer>
      {/* Header */}
      <PageHeader
        title="Families"
        description="Manage family registrations and child enrollments"
        icon={<UserGroupIcon className="w-6 h-6 text-white" />}
        actions={
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/families/import')}
              className="btn btn-secondary"
            >
              <ArrowUpTrayIcon className="w-5 h-5" />
              Import
            </button>
            <button
              onClick={handleCreateFamily}
              className="btn btn-primary"
            >
              <PlusIcon className="w-5 h-5" />
              Add Family
            </button>
          </div>
        }
      />

      {/* Stats */}
      <StatsGrid columns={4}>
        <StatCard
          icon={<UserGroupIcon className="w-5 h-5" />}
          label="Total Families"
          value={totalFamilies}
          color="blue"
        />
        <StatCard
          icon={<CheckCircleIcon className="w-5 h-5" />}
          label="Active"
          value={activeFamilies}
          color="green"
        />
        <StatCard
          icon={<ClockIcon className="w-5 h-5" />}
          label="Pending"
          value={pendingFamilies}
          color="yellow"
        />
        <StatCard
          icon={<UsersIcon className="w-5 h-5" />}
          label="Total Children"
          value={totalChildren}
          color="purple"
        />
      </StatsGrid>

      {/* Search & Filters */}
      <SearchFilterBar
        searchValue={filters.searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder="Search families, guardians, or children..."
        filters={[
          {
            value: filters.statusFilter,
            onChange: setStatusFilter,
            options: FAMILY_STATUS_OPTIONS,
          },
        ]}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
      />

      {/* Content */}
      <div className="min-h-[400px]">
        {renderContent()}
      </div>
    </PageContainer>
  );
};

export default FamiliesList;
