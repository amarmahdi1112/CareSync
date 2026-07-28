export interface ProfileDistribution {
  consistent: number;
  variable: number;
  oftenAbsent: number;
}

export interface ClaimConfig {
  month: number;
  year: number;
  capacity: number;
  operatingHours: number;
  hourTiers: {
    fullTimeMonthlyTarget: number;
    schoolAgeFullDayTarget: number;
    schoolAgePartDayTarget: number;
  };
  schoolBreakPeriods: Array<{ start: string; end: string; name?: string }>;
  behavioralProfiles: {
    consistent: { probability: number; variance: number };
    variable: { probability: number; variance: number };
    oftenAbsent: { probability: number; variance: number };
  };
  fullTimeDistribution: ProfileDistribution;
  schoolAgeDistribution: ProfileDistribution;
}

export interface OrganizationData {
  id: string;
  name: string;
  licensed_capacity: number;
  opening_time: string;
  closing_time: string;
}
