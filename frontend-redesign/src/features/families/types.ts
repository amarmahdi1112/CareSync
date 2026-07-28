export interface FamilyChildRecord {
  id: string;
  organization_id: string;
  family_id: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  date_of_birth: string;
  gender: string | null;
  age_group: string | null;
  is_active: boolean;
  profile_photo_url?: string | null;
  profile_photo_updated_at?: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  replayed: false;
}

export interface FamilyGuardianRecord {
  id: string;
  family_id: string;
  first_name: string;
  last_name: string;
  relationship: string | null;
  guardian_type: string;
  email: string;
  cell_phone: string;
  home_phone: string | null;
  work_phone: string | null;
  address: string | null;
  city: string | null;
  postal_code: string | null;
  authorized_pickup: boolean;
}

export interface FamilyEmergencyContactRecord {
  id: string;
  family_id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  cell_phone: string;
  home_phone: string | null;
  authorized_pickup: boolean;
}

export interface FamilySummaryRecord {
  id: string;
  organization_id: string;
  name: string;
  status: string;
  file_number: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  replayed: boolean;
  children: FamilyChildRecord[];
  guardians: FamilyGuardianRecord[];
}

export interface FamilyDetailRecord extends FamilySummaryRecord {
  photo_consent: boolean;
  field_trip_consent: boolean;
  emergency_medical_consent: boolean;
  additional_notes: string | null;
  emergency_contacts: FamilyEmergencyContactRecord[];
}

/** Privacy-minimized contact projection used only by the paged directory. */
export interface FamilyDirectoryPrimaryContact {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  cell_phone: string;
}

/** Server-bounded active-child preview. The directory returns at most four. */
export interface FamilyDirectoryChildPreview {
  id: string;
  first_name: string;
  last_name: string;
  age_group: string | null;
}

export interface FamilyDirectoryRecord {
  id: string;
  organization_id: string;
  name: string;
  file_number: string | null;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  primary_contact: FamilyDirectoryPrimaryContact | null;
  active_children: FamilyDirectoryChildPreview[];
  active_child_count: number;
}

export interface FamilyDirectoryPage {
  items: FamilyDirectoryRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface FamilyDirectoryQuery {
  search: string;
  status: string;
  limit: number;
  offset: number;
}

export interface GuardianInput {
  /** Existing server identity retained in edit drafts; never sent in write payloads. */
  record_id?: string | null;
  first_name: string;
  last_name: string;
  relationship: string;
  guardian_type: string;
  email: string;
  cell_phone: string;
  home_phone: string;
  work_phone: string;
  address: string;
  city: string;
  postal_code: string;
  authorized_pickup: boolean;
}

export interface EmergencyContactInput {
  client_id: string;
  /** Existing server identity retained in edit drafts; never sent in write payloads. */
  record_id?: string | null;
  first_name: string;
  last_name: string;
  relationship: string;
  cell_phone: string;
  home_phone: string;
  authorized_pickup: boolean;
}

export interface FamilyConsentsInput {
  photo_consent: boolean;
  field_trip_consent: boolean;
  emergency_medical_consent: boolean;
}

export interface FamilyRegistrationInput {
  name: string;
  file_number: string;
  status: string;
  include_primary_guardian: boolean;
  primary_guardian: GuardianInput;
  include_secondary_guardian: boolean;
  secondary_guardian: GuardianInput;
  emergency_contacts: EmergencyContactInput[];
  consents: FamilyConsentsInput;
  additional_notes: string;
}

export interface FamilyEditInput {
  name: string;
  status: string;
  file_number: string;
  consents: FamilyConsentsInput;
  additional_notes: string;
  /** Undefined means preserve the server section; null means explicitly remove it. */
  primary_guardian?: GuardianInput | null;
  /** Undefined means preserve the server section; null means explicitly remove it. */
  secondary_guardian?: GuardianInput | null;
  /** Undefined means preserve; null or an empty list explicitly removes all contacts. */
  emergency_contacts?: EmergencyContactInput[] | null;
}

export interface FamilyStatsRecord {
  families: number;
  active_families: number;
  children: number;
  active_children: number;
  pending_families: number;
  by_age_group: Record<string, number>;
}

export interface FamiliesSnapshot {
  directory: FamilyDirectoryPage;
  /** Optional aggregate metrics must never make a valid directory page unusable. */
  stats: FamilyStatsRecord | null;
}
