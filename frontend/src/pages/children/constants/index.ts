// ============================================
// Children Module Constants
// ============================================

export const AGE_GROUP_OPTIONS = [
  { value: 'all', label: 'All Age Groups' },
  { value: 'Infant', label: 'Infant' },
  { value: 'Toddler', label: 'Toddler' },
  { value: 'Preschool', label: 'Preschool' },
  { value: 'School-Age', label: 'School-Age' },
];

export const STATUS_OPTIONS = [
  { value: 'all', label: 'All Status' },
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
];

export const AGE_GROUP_COLORS = {
  'Infant': { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200' },
  'Toddler': { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200' },
  'Preschool': { bg: 'bg-purple-100', text: 'text-purple-700', border: 'border-purple-200' },
  'School-Age': { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-200' },
} as const;
