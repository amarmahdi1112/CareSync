import type {
  ExternalReportStatus,
  IncidentAssessment,
  IncidentRecord,
  IncidentSeverity,
  IncidentStatus,
} from './incidentApi';

export function incidentStatusLabel(status: IncidentStatus): string {
  if (status === 'draft') return 'Internal draft';
  if (status === 'under_review') return 'Under internal review';
  return 'Internally finalized';
}

export function incidentStatusTone(status: IncidentStatus): 'info' | 'warning' | 'success' {
  if (status === 'draft') return 'info';
  if (status === 'under_review') return 'warning';
  return 'success';
}

export function incidentSeverityLabel(severity: IncidentSeverity): string {
  const labels: Record<IncidentSeverity, string> = {
    minor: 'Minor — working selection',
    moderate: 'Moderate — working selection',
    serious: 'Serious — prompt review',
    critical: 'Critical — act immediately and review',
  };
  return labels[severity];
}

export function incidentAssessmentLabel(assessment: IncidentAssessment | null): string {
  if (assessment === 'not_reportable') return 'Internally assessed as not reportable';
  if (assessment === 'other_reportable') return 'Other reportable incident — external action tracked separately';
  if (assessment === 'critical') return 'Critical incident — external action tracked separately';
  return 'Reportability not yet internally assessed';
}

export function externalReportLabel(status: ExternalReportStatus): string {
  if (status === 'not_required') return 'No external report required — internal assessment';
  if (status === 'pending') return 'External report still needs human action';
  if (status === 'recorded') return 'External confirmation manually recorded';
  return 'External reporting not yet assessed';
}

export function reportingTimelineLabel(timeline: IncidentRecord['reporting_timeline']): string {
  if (timeline === 'as_soon_as_possible_no_later_than_24_hours') return 'Guidance marker: as soon as possible, no later than 24 hours — verify current Alberta steps';
  if (timeline === 'within_2_business_days') return 'Guidance marker: within 2 business days — verify current Alberta steps';
  if (timeline === 'not_reportable') return 'No external timeline — internal human assessment';
  return 'Timeline not assessed — human review required';
}

export function reportGuidance(incident: IncidentRecord): { urgent: boolean; heading: string; detail: string } {
  if (incident.severity === 'critical' || incident.reportability_assessment === 'critical') {
    return {
      urgent: true,
      heading: 'Critical working classification — act now and verify',
      detail: `Do not delay emergency response, parent contact, or Child Care Connect contact as applicable. ${reportingTimelineLabel(incident.reporting_timeline)}. Confirm the classification and current Alberta reporting steps with a responsible reviewer.`,
    };
  }
  if (incident.reportability_assessment === 'other_reportable') {
    return {
      urgent: false,
      heading: 'Other reportable assessment — human submission required',
      detail: `${reportingTimelineLabel(incident.reporting_timeline)}. Review current Alberta guidance and complete the external portal process within the applicable window. CareSync only tracks the confirmation you enter.`,
    };
  }
  return {
    urgent: false,
    heading: 'Working record — review required',
    detail: 'Severity and reportability are staff selections, not a legal determination. Confirm with Child Care Connect if the correct path is uncertain.',
  };
}

export function incidentCounts(incidents: readonly IncidentRecord[]) {
  return incidents.reduce((counts, incident) => {
    counts.total += 1;
    counts[incident.status] += 1;
    if (incident.external_report_status === 'pending') counts.externalPending += 1;
    return counts;
  }, { total: 0, draft: 0, under_review: 0, finalized: 0, externalPending: 0 });
}

export function incidentMatches(incident: IncidentRecord, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return `${incident.child_name || ''} ${incident.room_name} ${incident.category} ${incident.summary}`.toLowerCase().includes(normalized);
}

export function canEditIncident(incident: IncidentRecord): boolean {
  return incident.status === 'draft';
}

export function canRecordExternalReport(incident: IncidentRecord): boolean {
  return incident.status === 'finalized'
    && incident.external_report_status === 'pending'
    && (incident.reportability_assessment === 'critical' || incident.reportability_assessment === 'other_reportable');
}
