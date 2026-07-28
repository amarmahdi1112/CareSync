import type { ProgramType } from '../../models/programTypes';

export interface BasicOrganization {
  id: string;
  name: string;
  legal_name: string | null;
  status: string;
  email: string | null;
  phone: string | null;
  timezone: string;
  preferences: Record<string, unknown>;
}

export interface FacilityRecord {
  id: string;
  organization_id: string;
  name: string;
  license_number: string | null;
  status: 'draft' | 'active' | 'inactive';
  email: string | null;
  phone: string | null;
  street_address: string | null;
  city: string | null;
  province: string;
  postal_code: string | null;
  timezone: string;
  licensed_capacity: number;
  opening_time: string | null;
  closing_time: string | null;
}

export interface ProgramRecord {
  id: string;
  organization_id: string;
  facility_id: string;
  name: string;
  program_type: ProgramType | null;
  capacity: number;
  minimum_age_months: number | null;
  maximum_age_months: number | null;
  is_active: boolean;
}

export interface RoomRecord {
  id: string;
  organization_id: string;
  facility_id: string;
  program_id: string | null;
  name: string;
  capacity: number;
  age_group: string | null;
  is_active: boolean;
}

export interface OnboardingResponse {
  organization_id: string;
  status: 'draft' | 'in_progress' | 'complete';
  current_step: OnboardingStep | 'complete';
  completed_steps: OnboardingStep[];
  draft: Record<string, unknown>;
  completed_at: string | null;
  organization: BasicOrganization;
  facilities: FacilityRecord[];
}

export type OnboardingStep = 'organization' | 'facility' | 'rooms' | 'review';

export interface OrganizationDraft {
  name: string;
  legalName: string;
  email: string;
  phone: string;
  timezone: string;
}

export interface FacilityDraft {
  id: string | null;
  name: string;
  licenseNumber: string;
  email: string;
  phone: string;
  streetAddress: string;
  city: string;
  province: string;
  postalCode: string;
  timezone: string;
  licensedCapacity: string;
  openingTime: string;
  closingTime: string;
}

export interface ProgramDraft {
  id: string | null;
  name: string;
  capacity: string;
  minimumAgeMonths: string;
  maximumAgeMonths: string;
}

export interface RoomDraft {
  draftKey: string;
  id: string | null;
  programType: ProgramType | '';
  name: string;
  capacity: string;
  ageGroup: string;
}

export interface OnboardingDraft {
  organization: OrganizationDraft;
  facility: FacilityDraft;
  selectedProgramTypes: ProgramType[];
  programs: Record<ProgramType, ProgramDraft>;
  rooms: RoomDraft[];
  archivedRoomIds: string[];
}
