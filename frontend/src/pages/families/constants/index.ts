// ============================================
// Families Module - Constants
// ============================================

import type { FamilyStatus, AgeGroup, Relationship } from '../types';

// Status options
export const FAMILY_STATUS_OPTIONS: { value: FamilyStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All Status' },
  { value: 'active', label: 'Active' },
  { value: 'pending', label: 'Pending' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'archived', label: 'Archived' },
];

// Age group options
export const AGE_GROUP_OPTIONS: { value: AgeGroup | 'all'; label: string }[] = [
  { value: 'all', label: 'All Ages' },
  { value: 'Infant', label: 'Infant (0-19 mo)' },
  { value: 'Toddler', label: 'Toddler (20-36 mo)' },
  { value: 'Preschool', label: 'Preschool (3-5 yr)' },
  { value: 'School-Age', label: 'School-Age (6+ yr)' },
];

// Relationship options
export const RELATIONSHIP_OPTIONS: { value: Relationship; label: string }[] = [
  { value: 'Mother', label: 'Mother' },
  { value: 'Father', label: 'Father' },
  { value: 'Guardian', label: 'Guardian' },
  { value: 'Grandparent', label: 'Grandparent' },
  { value: 'Other', label: 'Other' },
];

// Status colors
export const STATUS_COLORS: Record<FamilyStatus, { bg: string; text: string; dot: string }> = {
  active: { bg: 'bg-green-50', text: 'text-green-700', dot: 'bg-green-500' },
  pending: { bg: 'bg-amber-50', text: 'text-amber-700', dot: 'bg-amber-500' },
  inactive: { bg: 'bg-gray-50', text: 'text-gray-600', dot: 'bg-gray-400' },
  archived: { bg: 'bg-red-50', text: 'text-red-700', dot: 'bg-red-500' },
};

// Age group colors
export const AGE_GROUP_COLORS: Record<AgeGroup, { bg: string; text: string }> = {
  'Infant': { bg: 'bg-pink-100', text: 'text-pink-700' },
  'Toddler': { bg: 'bg-purple-100', text: 'text-purple-700' },
  'Preschool': { bg: 'bg-blue-100', text: 'text-blue-700' },
  'School-Age': { bg: 'bg-teal-100', text: 'text-teal-700' },
};

// Default pagination
export const DEFAULT_PAGE_SIZE = 20;
