/**
 * Family Store
 * Manages family-related state and caching
 */

import { create } from 'zustand';
import type { AgeGroup } from '../types/family';

// Types
export interface FamilyListItem {
  id: string;
  name: string;
  status: 'active' | 'pending' | 'inactive';
  primaryGuardianName: string;
  primaryGuardianPhone: string;
  primaryGuardianEmail: string;
  childrenCount: number;
  children: {
    id: string;
    firstName: string;
    lastName: string;
    ageGroup: AgeGroup;
  }[];
  createdAt: string;
}

export interface ChildListItem {
  id: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  ageGroup: AgeGroup;
  familyName: string;
  familyId: string;
  status: 'active' | 'inactive';
  enrollmentDate: string;
}

interface FamilyFilters {
  searchTerm: string;
  statusFilter: string;
  ageGroupFilter: string;
}

interface FamilyState {
  // Cached data
  families: FamilyListItem[];
  children: ChildListItem[];
  
  // Loading states
  familiesLoading: boolean;
  childrenLoading: boolean;
  
  // Filters
  filters: FamilyFilters;
  
  // Actions
  setFamilies: (families: FamilyListItem[]) => void;
  setChildren: (children: ChildListItem[]) => void;
  setFamiliesLoading: (loading: boolean) => void;
  setChildrenLoading: (loading: boolean) => void;
  
  // Filter actions
  setSearchTerm: (term: string) => void;
  setStatusFilter: (status: string) => void;
  setAgeGroupFilter: (ageGroup: string) => void;
  clearFilters: () => void;
  
  // Computed getters
  getFilteredFamilies: () => FamilyListItem[];
  getFilteredChildren: () => ChildListItem[];
  
  // Stats
  getFamilyStats: () => {
    total: number;
    active: number;
    pending: number;
    inactive: number;
    totalChildren: number;
  };
  
  getChildrenStats: () => {
    total: number;
    infants: number;
    toddlers: number;
    preschool: number;
    schoolAge: number;
  };

  // Cache invalidation
  invalidateCache: () => void;
}

const initialFilters: FamilyFilters = {
  searchTerm: '',
  statusFilter: 'all',
  ageGroupFilter: 'all',
};

export const useFamilyStore = create<FamilyState>((set, get) => ({
  // State
  families: [],
  children: [],
  familiesLoading: false,
  childrenLoading: false,
  filters: initialFilters,

  // Setters
  setFamilies: (families) => set({ families }),
  setChildren: (children) => set({ children }),
  setFamiliesLoading: (loading) => set({ familiesLoading: loading }),
  setChildrenLoading: (loading) => set({ childrenLoading: loading }),

  // Filter actions
  setSearchTerm: (term) =>
    set((state) => ({ filters: { ...state.filters, searchTerm: term } })),
  setStatusFilter: (status) =>
    set((state) => ({ filters: { ...state.filters, statusFilter: status } })),
  setAgeGroupFilter: (ageGroup) =>
    set((state) => ({ filters: { ...state.filters, ageGroupFilter: ageGroup } })),
  clearFilters: () => set({ filters: initialFilters }),

  // Filtered data getters
  getFilteredFamilies: () => {
    const { families, filters } = get();
    return families.filter((family) => {
      const matchesSearch =
        filters.searchTerm === '' ||
        family.name.toLowerCase().includes(filters.searchTerm.toLowerCase()) ||
        family.primaryGuardianName.toLowerCase().includes(filters.searchTerm.toLowerCase()) ||
        family.primaryGuardianEmail.toLowerCase().includes(filters.searchTerm.toLowerCase());
      
      const matchesStatus =
        filters.statusFilter === 'all' || family.status === filters.statusFilter;
      
      return matchesSearch && matchesStatus;
    });
  },

  getFilteredChildren: () => {
    const { children, filters } = get();
    return children.filter((child) => {
      const matchesSearch =
        filters.searchTerm === '' ||
        child.firstName.toLowerCase().includes(filters.searchTerm.toLowerCase()) ||
        child.lastName.toLowerCase().includes(filters.searchTerm.toLowerCase()) ||
        child.familyName.toLowerCase().includes(filters.searchTerm.toLowerCase());
      
      const matchesAgeGroup =
        filters.ageGroupFilter === 'all' || child.ageGroup === filters.ageGroupFilter;
      
      return matchesSearch && matchesAgeGroup;
    });
  },

  // Stats
  getFamilyStats: () => {
    const { families } = get();
    return {
      total: families.length,
      active: families.filter((f) => f.status === 'active').length,
      pending: families.filter((f) => f.status === 'pending').length,
      inactive: families.filter((f) => f.status === 'inactive').length,
      totalChildren: families.reduce((acc, f) => acc + f.childrenCount, 0),
    };
  },

  getChildrenStats: () => {
    const { children } = get();
    const activeChildren = children.filter((c) => c.status === 'active');
    return {
      total: activeChildren.length,
      infants: activeChildren.filter((c) => c.ageGroup === 'Infant').length,
      toddlers: activeChildren.filter((c) => c.ageGroup === 'Toddler').length,
      preschool: activeChildren.filter((c) => c.ageGroup === 'Preschool').length,
      schoolAge: activeChildren.filter((c) => c.ageGroup === 'School-Age').length,
    };
  },

  // Cache invalidation
  invalidateCache: () => set({ families: [], children: [] }),
}));
