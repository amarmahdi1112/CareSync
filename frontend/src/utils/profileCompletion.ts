// ============================================
// Profile Completion Checker
// Determines what data is missing and where to redirect
// Shows ONLY the specific missing fields - not whole wizard
// ============================================

import type { Organization, User } from '../types';

export type ProfileIssue = 
  | 'setup_incomplete'         // Organization has missing required fields
  | 'profile_incomplete';      // User profile missing required fields

export interface ProfileStatus {
  isComplete: boolean;
  issues: ProfileIssue[];
  redirectTo: string | null;
  missingFieldsCount: number;
}

// Check if ALL required organization fields are complete
export const isOrganizationSetupComplete = (org: Organization | null): boolean => {
  if (!org) return false;
  
  const hasName = org.name && org.name !== 'My Organization';
  const hasLicense = org.license_number && org.license_number !== 'PENDING';
  const hasCapacity = !!org.licensed_capacity;
  const hasAddress = !!org.street_address;
  const hasCity = !!org.city;
  const hasProvince = !!org.province;
  const hasPostalCode = !!org.postal_code;
  const hasPhone = !!org.phone;
  const hasOpeningTime = !!org.opening_time;
  const hasClosingTime = !!org.closing_time;
  const hasAgeGroups = !!org.age_groups_served?.length;
  
  return !!(
    hasName && hasLicense && hasCapacity &&
    hasAddress && hasCity && hasProvince && hasPostalCode &&
    hasPhone && hasOpeningTime && hasClosingTime && hasAgeGroups
  );
};

// For backward compatibility - checks basic fields
export const isOnboardingComplete = (org: Organization | null): boolean => {
  return isOrganizationSetupComplete(org);
};

// Check if user profile is complete
export const isUserProfileComplete = (user: User | null): boolean => {
  if (!user) return false;
  
  const hasFirstName = !!user.firstName && user.firstName !== 'User';
  const hasLastName = !!user.lastName;
  
  return hasFirstName && hasLastName;
};

// Count missing organization fields
export const countMissingOrgFields = (org: Organization | null): number => {
  if (!org) return 11; // All fields missing
  
  let count = 0;
  if (!org.name || org.name === 'My Organization') count++;
  if (!org.license_number || org.license_number === 'PENDING') count++;
  if (!org.licensed_capacity) count++;
  if (!org.street_address) count++;
  if (!org.city) count++;
  if (!org.province) count++;
  if (!org.postal_code) count++;
  if (!org.phone) count++;
  if (!org.opening_time) count++;
  if (!org.closing_time) count++;
  if (!org.age_groups_served?.length) count++;
  
  return count;
};

// Get comprehensive profile status
export const getProfileStatus = (
  user: User | null, 
  org: Organization | null
): ProfileStatus => {
  const issues: ProfileIssue[] = [];
  let missingFieldsCount = 0;
  
  // Check organization setup
  const orgMissingCount = countMissingOrgFields(org);
  if (orgMissingCount > 0) {
    issues.push('setup_incomplete');
    missingFieldsCount += orgMissingCount;
  }
  
  // Check user profile
  if (!isUserProfileComplete(user)) {
    issues.push('profile_incomplete');
    missingFieldsCount += 2; // firstName, lastName
  }
  
  // Determine redirect - always go to /complete-setup for missing org fields
  // This shows ONLY the missing fields, not the whole wizard
  let redirectTo: string | null = null;
  
  if (issues.includes('setup_incomplete')) {
    redirectTo = '/complete-setup';
  } else if (issues.includes('profile_incomplete')) {
    redirectTo = '/complete-profile';
  }
  
  return {
    isComplete: issues.length === 0,
    issues,
    redirectTo,
    missingFieldsCount,
  };
};

// Get list of missing field names (for display)
export const getMissingFieldNames = (org: Organization | null): string[] => {
  if (!org) return ['All organization information'];
  
  const missing: string[] = [];
  
  if (!org.name || org.name === 'My Organization') missing.push('Organization Name');
  if (!org.license_number || org.license_number === 'PENDING') missing.push('License Number');
  if (!org.licensed_capacity) missing.push('Licensed Capacity');
  if (!org.street_address) missing.push('Street Address');
  if (!org.city) missing.push('City');
  if (!org.province) missing.push('Province');
  if (!org.postal_code) missing.push('Postal Code');
  if (!org.phone) missing.push('Phone Number');
  if (!org.opening_time) missing.push('Opening Time');
  if (!org.closing_time) missing.push('Closing Time');
  if (!org.age_groups_served?.length) missing.push('Age Groups');
  
  return missing;
};
