import type { LoginResponse } from '../../api/client';

export type MembershipStatus = 'active' | 'suspended';
export type InvitationStatus = 'pending' | 'accepted' | 'revoked' | 'expired';

export interface StaffRole {
  id: string;
  key: string;
  name: string;
  description: string | null;
  permissions: string[];
}

export interface StaffFacility {
  id: string;
  organization_id: string;
  name: string;
  timezone: string;
  status: string;
}

export interface StaffRoom {
  id: string;
  organization_id: string;
  facility_id: string;
  name: string;
  is_active: boolean;
}

export interface StaffMember {
  membership_id: string;
  organization_id: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: StaffRole;
  membership_status: MembershipStatus;
  assigned_facility_ids: string[];
  assigned_room_ids: string[];
  joined_at: string | null;
  created_at: string;
  updated_at: string;
  active_assignments: StaffAssignmentSummary[];
  credential: StaffCredentialSummary | null;
  current_shift: StaffShiftSummary | null;
  private_hr_fields_exposed: false;
}

export interface StaffAssignmentSummary { facility_id: string; facility_name: string; room_id: string | null; room_name: string | null; }
export interface StaffCredentialSummary { certification_type: string | null; certification_number: string | null; expiry_date: string | null; verification_status: 'unverified' | 'pending' | 'verified' | 'rejected'; ready: boolean; }
export interface StaffShiftSummary { id: string; facility_id: string; status: 'open' | 'closed'; clocked_in_at: string; clocked_out_at: string | null; }

export interface StaffInvitation {
  id: string;
  organization_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: StaffRole;
  status: InvitationStatus;
  assigned_facility_ids: string[];
  assigned_room_ids: string[];
  expires_at: string;
  created_at: string;
}

export interface StaffWorkspace {
  organization_id: string;
  roles: StaffRole[];
  facilities: StaffFacility[];
  rooms: StaffRoom[];
  members: StaffMember[];
  invitations: StaffInvitation[];
}

export interface StaffInviteInput {
  email: string;
  first_name: string;
  last_name: string;
  role_id: string;
  assigned_facility_ids: string[];
  assigned_room_ids: string[];
}

export interface OneTimeActivation {
  invitation: StaffInvitation;
  activation_url: string;
}

export interface OneTimePasswordReset {
  reset_url: string;
  expires_at: string;
}

export interface StaffActivationPreview {
  organization_name: string;
  email: string;
  first_name: string;
  last_name: string;
  role_name: string;
  expires_at: string;
  assigned_room_names: string[];
}

export interface PasswordResetPreview {
  organization_name: string;
  email: string;
  expires_at: string;
}

export type StaffActivationResult = LoginResponse;
