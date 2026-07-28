import React, { useState } from 'react';
import {
  UserGroupIcon,
  ClockIcon,
  CalendarDaysIcon,
  ArrowRightIcon,
  ArrowPathIcon,
  PlusIcon,
  XMarkIcon,
  PlayIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../stores';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';
import type { OrganizationData } from './ClaimsPhase';
import { schedulerCareType } from '../utils/careType';
import {
  buildSchoolCalendarPatch,
  monthWeekdayDates,
  schoolCalendarReadyForGeneration,
  schoolOffDaysWithinOpenDays,
  schoolOffSelectionForMonth,
  type SchoolCalendarData,
} from '../utils/schoolCalendar';
import { prepareImportedClaimsForScheduling } from '../utils/importedClaimIdentity';

// ─── Types ──────────────────────────────────────────────────────────────────────

interface SchedulerConfig {
  capacity: number;
  operatingStartHour: number;
  operatingEndHour: number;
  schoolOffDays: string[];
  closedDays: string[];
  dailyCapacityMin: number;
  dailyCapacityMax: number;
}

interface ChildTimeOverride {
  childIdentifier: string;
  daysOfWeek: number[]; // 1=Mon..5=Fri; empty = all days
  startTime1?: string;
  endTime1?: string;
  startTime2?: string;
  endTime2?: string;
}

interface ChildAbsentDaysEntry {
  childIdentifier: string;
  dates: string[];
}

interface ClosureDay {
  date: string;
  name: string;
  kind: 'statutory' | 'optional' | 'custom';
}

interface ClosureCalendar {
  year: number;
  province: string;
  statutory: ClosureDay[];
  custom: ClosureDay[];
  includeOptionalHolidays: boolean;
}

interface SchedulePhaseProps {
  selectedSource: { type: 'generated' | 'imported'; batchId: string } | null;
  onScheduleGenerated: (batchId: string, result?: unknown) => void;
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const normalizeChildName = (value: string) => value
  .normalize('NFKD')
  .replace(/[^a-zA-Z0-9]+/g, ' ')
  .trim()
  .toLowerCase();

const conservativeHourBoundary = (value: string | undefined, kind: 'opening' | 'closing') => {
  if (!value) return Number.NaN;
  const [hourValue, minuteValue = '0'] = value.split(':');
  const hour = Number(hourValue);
  const minute = Number(minuteValue);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return Number.NaN;
  return kind === 'opening' && minute > 0 ? hour + 1 : hour;
};

// ─── Component ──────────────────────────────────────────────────────────────────

const SchedulePhase: React.FC<SchedulePhaseProps> = ({ selectedSource, onScheduleGenerated }) => {
  const { success, error } = useNotificationStore();

  // Config state
  const [config, setConfig] = useState<SchedulerConfig>({
    capacity: 50,
    operatingStartHour: 7,
    operatingEndHour: 18,
    schoolOffDays: [],
    closedDays: [],
    dailyCapacityMin: 100,
    dailyCapacityMax: 140,
  });

  const [childTimeOverrides, setChildTimeOverrides] = useState<ChildTimeOverride[]>([]);
  const [childAbsentDays, setChildAbsentDays] = useState<ChildAbsentDaysEntry[]>([]);
  const [generating, setGenerating] = useState(false);
  const [savingClosures, setSavingClosures] = useState(false);
  const [savingSchoolCalendar, setSavingSchoolCalendar] = useState(false);
  const [includeOptionalHolidays, setIncludeOptionalHolidays] = useState(false);

  const { data: reportRows } = useApiQuery<any[]>('/resources/generated_claim_reports', { limit: 5000 });
  const { data: importedRows } = useApiQuery<any[]>('/resources/imported_claims', { limit: 5000 });
  const { data: generatedRows } = useApiQuery<any[]>('/resources/generated_claims', {
    report_id: selectedSource?.type === 'generated' ? selectedSource.batchId : undefined,
    limit: 5000,
  });
  const { data: childrenRows } = useApiQuery<any[]>('/children', { limit: 1000 });
  const { data: organization } = useApiQuery<OrganizationData>('/organization');

  const reportsData = React.useMemo(() => (reportRows || []).map((row) => ({
      id: row.id,
      reportName: row.report_name,
      report: {
        targetMonth: row.target_month,
        targetYear: row.target_year,
        totalChildrenProcessed: row.total_children_processed,
        totalProjectedHours: Number(row.total_projected_hours),
      },
    })), [reportRows]);
  const batchesData = React.useMemo(() => {
    const batches = new Map<string, any>();
    for (const row of importedRows || []) {
      const current = batches.get(row.import_batch_id) || {
        batchId: row.import_batch_id,
        claimMonth: row.claim_month,
        claimYear: row.claim_year,
        totalClaims: 0,
        totalHours: 0,
      };
      current.totalClaims += 1;
      current.totalHours += Number(row.corrected_hours ?? row.hours_claimed ?? 0);
      batches.set(row.import_batch_id, current);
    }
    return [...batches.values()];
  }, [importedRows]);
  const selectedImportedRows = React.useMemo(
    () => (importedRows || []).filter(
      (row) => row.import_batch_id === selectedSource?.batchId,
    ),
    [importedRows, selectedSource],
  );
  const schedulingImportedRows = React.useMemo(
    () => prepareImportedClaimsForScheduling(selectedImportedRows, childrenRows || []),
    [selectedImportedRows, childrenRows],
  );
  const importedMatchSummary = React.useMemo(() => {
    if (selectedSource?.type !== 'imported') return null;
    const matched = schedulingImportedRows.rows.filter((row) => row.uses_real_child);
    const claimOnly = schedulingImportedRows.rows.filter((row) => !row.uses_real_child);
    return {
      matchedCount: matched.length,
      claimOnlyCount: claimOnly.length,
      claimOnlyNames: claimOnly.map((row) => row.corrected_child_name || row.child_name),
      importedRowCount: selectedImportedRows.length,
      participantCount: schedulingImportedRows.rows.length,
      mergedRowCount: schedulingImportedRows.mergedRowCount,
      identityConflictCount: schedulingImportedRows.identityConflictCount,
      identityConflictNames: schedulingImportedRows.identityConflictNames,
    };
  }, [selectedSource, schedulingImportedRows, selectedImportedRows.length]);
  const transientClaimBatch = React.useMemo(() => {
    if (!selectedSource || selectedSource.type !== 'generated') return null;
    const value = sessionStorage.getItem(`caresync:claim-batch:${selectedSource.batchId}`);
    return value ? JSON.parse(value) : null;
  }, [selectedSource]);

  // Build child list for dropdowns
  const claimChildren: { id: string; name: string; hours: number }[] = React.useMemo(() => {
    if (selectedSource?.type === 'imported') {
      return schedulingImportedRows.rows.map((c) => ({
        id: c.schedule_child_id,
        name: c.corrected_child_name || c.child_name,
        hours: Number(c.corrected_hours ?? c.hours_claimed),
      }));
    }
    const claims = transientClaimBatch?.raw?.claims || generatedRows || [];
    if (selectedSource?.type === 'generated') {
      return claims.map((c: any) => ({
        id: c.child_id,
        name: c.child_name,
        hours: Number(c.projected_hours),
      }));
    }
    return [];
  }, [selectedSource, schedulingImportedRows, transientClaimBatch, generatedRows]);

  // Get batch info for display
  const selectedReport = selectedSource?.type === 'generated'
    ? reportsData.find(r => r.id === selectedSource.batchId)
    : null;
  const selectedBatch = selectedSource?.type === 'imported'
    ? batchesData.find(b => b.batchId === selectedSource.batchId)
    : null;

  const batchInfo = React.useMemo(() => selectedReport ? {
      month: selectedReport.report.targetMonth,
      year: selectedReport.report.targetYear,
      totalChildren: selectedReport.report.totalChildrenProcessed,
      totalHours: selectedReport.report.totalProjectedHours,
      name: selectedReport.reportName,
    } : selectedBatch ? {
      month: selectedBatch.claimMonth,
      year: selectedBatch.claimYear,
      totalChildren: selectedBatch.totalClaims,
      totalHours: selectedBatch.totalHours,
      name: `${MONTHS[selectedBatch.claimMonth - 1]} ${selectedBatch.claimYear}`,
    } : null, [selectedReport, selectedBatch]);

  const schoolCalendarSelectionKey = batchInfo && selectedSource
    ? `${selectedSource.type}-${selectedSource.batchId}-${batchInfo.year}-${batchInfo.month}`
    : '';
  const schoolCalendarLoadKey = React.useRef('');
  const schoolCalendarTouchedKey = React.useRef('');
  React.useEffect(() => {
    schoolCalendarTouchedKey.current = '';
    schoolCalendarLoadKey.current = '';
    setConfig((current) => ({ ...current, schoolOffDays: [] }));
  }, [schoolCalendarSelectionKey]);

  const configLoadKey = React.useRef('');
  React.useEffect(() => {
    if (!organization || !batchInfo) return;
    const key = `${selectedSource?.type}-${selectedSource?.batchId}`;
    if (configLoadKey.current === key) return;
    configLoadKey.current = key;
    // The current engine schedules on whole-hour operating boundaries. Rounding
    // inward prevents a 07:30 organization from ever receiving a 07:00 entry.
    const opening = conservativeHourBoundary(organization.opening_time, 'opening');
    const closing = conservativeHourBoundary(organization.closing_time, 'closing');
    const validOperatingWindow = Number.isFinite(opening)
      && Number.isFinite(closing)
      && opening < closing;
    const dailyMaximum = Math.max(1, Math.min(140, batchInfo.totalChildren));
    setConfig(current => ({
      ...current,
      capacity: organization.licensed_capacity || current.capacity,
      operatingStartHour: validOperatingWindow ? opening : current.operatingStartHour,
      operatingEndHour: validOperatingWindow ? closing : current.operatingEndHour,
      dailyCapacityMin: Math.min(100, dailyMaximum),
      dailyCapacityMax: dailyMaximum,
    }));
  }, [organization, batchInfo, selectedSource]);

  const closureYear = batchInfo?.year || new Date().getFullYear();
  const { data: closureCalendar, refetch: refetchClosures } = useApiQuery<ClosureCalendar>(
    '/schedules/closures',
    { year: closureYear },
    Boolean(batchInfo),
  );
  const {
    data: schoolCalendar,
    loading: schoolCalendarLoading,
    error: schoolCalendarError,
    refetch: refetchSchoolCalendar,
  } = useApiQuery<SchoolCalendarData>(
    '/schedules/school-calendar',
    { year: closureYear },
    Boolean(batchInfo),
  );
  const schoolCalendarGenerationReady = schoolCalendarReadyForGeneration({
    calendar: schoolCalendar,
    requestedYear: batchInfo?.year,
    loading: schoolCalendarLoading,
    hasError: Boolean(schoolCalendarError),
  });
  React.useEffect(() => {
    if (
      !batchInfo
      || !schoolCalendar
      || schoolCalendar.year !== batchInfo.year
      || !schoolCalendarSelectionKey
    ) return;
    const signature = [
      ...schoolCalendar.effective.map((item) => `${item.date}:${item.kind}`),
      ...schoolCalendar.excludedAutomaticDays.map((value) => `excluded:${value}`),
    ].sort().join(',');
    const loadKey = `${schoolCalendarSelectionKey}-${signature}`;
    if (
      schoolCalendarLoadKey.current === loadKey
      || schoolCalendarTouchedKey.current === schoolCalendarSelectionKey
    ) return;
    schoolCalendarLoadKey.current = loadKey;
    setConfig((current) => ({
      ...current,
      schoolOffDays: schoolOffSelectionForMonth(
        schoolCalendar,
        batchInfo.year,
        batchInfo.month,
      ),
    }));
  }, [batchInfo, schoolCalendar, schoolCalendarSelectionKey]);
  const closureLoadKey = React.useRef('');
  React.useEffect(() => {
    if (!batchInfo || !closureCalendar) return;
    const allClosures = [...closureCalendar.statutory, ...closureCalendar.custom];
    const signature = allClosures.map((item) => item.date).sort().join(',');
    const key = `${batchInfo.year}-${batchInfo.month}-${signature}`;
    if (closureLoadKey.current === key) return;
    closureLoadKey.current = key;
    const monthPrefix = `${batchInfo.year}-${String(batchInfo.month).padStart(2, '0')}-`;
    setConfig((current) => ({
      ...current,
      closedDays: allClosures
        .map((item) => item.date)
        .filter((value) => value.startsWith(monthPrefix)),
    }));
    setIncludeOptionalHolidays(closureCalendar.includeOptionalHolidays);
  }, [batchInfo, closureCalendar]);

  const closureNames = React.useMemo(
    () => new Map(
      [...(closureCalendar?.statutory || []), ...(closureCalendar?.custom || [])]
        .map((item) => [item.date, item.name]),
    ),
    [closureCalendar],
  );

  const automaticSchoolOffDates = React.useMemo(
    () => new Set((schoolCalendar?.automatic || []).map((item) => item.date)),
    [schoolCalendar],
  );
  const customSchoolOffDates = React.useMemo(
    () => new Set((schoolCalendar?.custom || []).map((item) => item.date)),
    [schoolCalendar],
  );
  const schoolOffNames = React.useMemo(
    () => new Map(
      [...(schoolCalendar?.automatic || []), ...(schoolCalendar?.custom || [])]
        .map((item) => [item.date, item.name]),
    ),
    [schoolCalendar],
  );

  const updateSchoolOffDays = (days: string[]) => {
    schoolCalendarTouchedKey.current = schoolCalendarSelectionKey;
    setConfig((current) => ({ ...current, schoolOffDays: [...new Set(days)].sort() }));
  };

  const handleSaveSchoolCalendar = async () => {
    if (!batchInfo || !schoolCalendar) return;
    setSavingSchoolCalendar(true);
    try {
      await api.patch('/schedules/school-calendar', buildSchoolCalendarPatch(
        schoolCalendar,
        config.schoolOffDays,
        batchInfo.year,
        batchInfo.month,
      ));
      await refetchSchoolCalendar();
      success(
        'School Calendar Saved',
        'Automatic dates and your manual exceptions will load for future schedules.',
      );
    } catch (caught) {
      error('Save Failed', caught instanceof Error ? caught.message : 'Request failed');
    } finally {
      setSavingSchoolCalendar(false);
    }
  };

  const handleSaveClosures = async () => {
    if (!batchInfo) return;
    const statutoryDates = new Set((closureCalendar?.statutory || []).map((item) => item.date));
    const monthPrefix = `${batchInfo.year}-${String(batchInfo.month).padStart(2, '0')}-`;
    const otherMonths = (closureCalendar?.custom || []).filter(
      (item) => !item.date.startsWith(monthPrefix),
    );
    const currentMonth = config.closedDays
      .filter((value) => !statutoryDates.has(value))
      .map((value) => ({ date: value, name: 'Daycare closed', kind: 'custom' as const }));
    setSavingClosures(true);
    try {
      await api.patch('/schedules/closures', {
        year: batchInfo.year,
        includeOptionalHolidays,
        customDays: [...otherMonths, ...currentMonth],
      });
      await refetchClosures();
      success('Closure Calendar Saved', 'Holiday and daycare closure settings will load automatically next time.');
    } catch (caught) {
      error('Save Failed', caught instanceof Error ? caught.message : 'Request failed');
    } finally {
      setSavingClosures(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedSource) return;
    const overrides = childTimeOverrides.filter(o => o.startTime1 || o.endTime1 || o.startTime2 || o.endTime2);
    if (!batchInfo) return;
    if (!schoolCalendarGenerationReady) {
      error(
        'School Calendar Loading',
        'Wait for the school-off calendar to finish loading before generating this schedule.',
      );
      return;
    }
    const daysInMonth = new Date(batchInfo.year, batchInfo.month, 0).getDate();
    const closed = new Set(config.closedDays);
    const openDays = Array.from({ length: daysInMonth }, (_, index) => {
      const day = String(index + 1).padStart(2, '0');
      return `${batchInfo.year}-${String(batchInfo.month).padStart(2, '0')}-${day}`;
    }).filter((value) => {
      const weekDay = new Date(`${value}T12:00:00`).getDay();
      return weekDay >= 1 && weekDay <= 5 && !closed.has(value);
    });
    // A facility closure is never a schedulable school-off day. Keeping this
    // intersection at the request boundary also protects manual selections
    // made before a closure was added.
    // Derive untouched automatic dates directly from the resolved response as
    // well as hydrating the UI state. This closes the single-render window
    // between the request completing and the hydration effect running.
    const selectedSchoolOffDays = schoolCalendar && schoolCalendar.year === batchInfo.year
      && schoolCalendarTouchedKey.current !== schoolCalendarSelectionKey
      ? schoolOffSelectionForMonth(schoolCalendar, batchInfo.year, batchInfo.month)
      : config.schoolOffDays;
    const effectiveSchoolOffDays = schoolOffDaysWithinOpenDays(
      selectedSchoolOffDays,
      openDays,
    );
    const childById = new Map((childrenRows || []).map((child) => [child.id, child]));
    const childByName = new Map<string, any[]>();
    for (const child of childrenRows || []) {
      const shortName = `${child.first_name} ${child.last_name}`;
      const fullName = [child.first_name, child.middle_name, child.last_name].filter(Boolean).join(' ');
      for (const candidate of new Set([normalizeChildName(shortName), normalizeChildName(fullName)])) {
        childByName.set(candidate, [...(childByName.get(candidate) || []), child]);
      }
    }
    const sourceClaims = selectedSource.type === 'imported'
      ? schedulingImportedRows.rows.map((claim) => ({
          child_id: claim.schedule_child_id,
          child_name: claim.corrected_child_name || claim.child_name,
          projected_hours: Number(claim.corrected_hours ?? claim.hours_claimed),
          care_category: claim.care_category,
          source_claim_ids: claim.source_claim_ids,
          source_claim_names: claim.source_claim_names,
        }))
      : (transientClaimBatch?.raw?.claims || generatedRows || []);
    const absentByChild = new Map(childAbsentDays.map((entry) => [entry.childIdentifier, entry.dates]));
    const resolutionIssues: string[] = [];
    const claimOnlyChildren: string[] = [];
    const schedulerChildren = sourceClaims.flatMap((claim: any) => {
      const nameMatches = childByName.get(normalizeChildName(String(claim.child_name || ''))) || [];
      const child = childById.get(claim.child_id)
        || (selectedSource.type === 'generated' && nameMatches.length === 1 ? nameMatches[0] : null);
      const fallbackName = String(claim.child_name || claim.child_id || 'Unnamed child');
      if (!child) {
        const isClaimOnlyImport = selectedSource.type === 'imported'
          && String(claim.child_id).startsWith('imported-claim:');
        if (!isClaimOnlyImport) {
          resolutionIssues.push(`${fallbackName} (${nameMatches.length > 1 ? 'ambiguous name' : 'no child match'})`);
          return [];
        }
        const claimedHours = Number(claim.projected_hours);
        if (!Number.isFinite(claimedHours) || claimedHours < 0) {
          resolutionIssues.push(`${fallbackName} (invalid projected hours)`);
          return [];
        }
        if (claimedHours <= 0.1) return [];
        claimOnlyChildren.push(fallbackName);
        return [{
          id: claim.child_id,
          name: fallbackName,
          familyId: `imported-batch:${selectedSource.batchId}`,
          careType: schedulerCareType(claim.care_category),
          totalClaimedHours: claimedHours,
          enrollmentDate: null,
          preferences: { excludedDays: absentByChild.get(claim.child_name) || [] },
        }];
      }
      const claimedHours = Number(claim.projected_hours);
      if (!Number.isFinite(claimedHours) || claimedHours < 0) {
        resolutionIssues.push(`${fallbackName} (invalid projected hours)`);
        return [];
      }
      if (claimedHours <= 0.1) return [];
      return [{
        id: child.id,
        name: child ? `${child.first_name} ${child.last_name}` : fallbackName,
        familyId: child.family_id,
        // The claim category describes the program for this claim month; the
        // current child age group is only a fallback when that source is blank.
        careType: schedulerCareType(claim.care_category, child.age_group),
        totalClaimedHours: claimedHours,
        enrollmentDate: child.start_date,
        preferences: { excludedDays: absentByChild.get(child.id) || absentByChild.get(claim.child_name) || [] },
      }];
    });
    const duplicateIds = schedulerChildren
      .map((child: { id: string }) => child.id)
      .filter((id: string, index: number, values: string[]) => values.indexOf(id) !== index);
    if (duplicateIds.length) {
      resolutionIssues.push(`${new Set(duplicateIds).size} child record(s) appear more than once in the claim source`);
    }
    if (resolutionIssues.length) {
      error(
        'Resolve Child Matches First',
        `${resolutionIssues.slice(0, 4).join('; ')}${resolutionIssues.length > 4 ? `; and ${resolutionIssues.length - 4} more` : ''}. Use Name Sync before generating.`,
      );
      return;
    }
    if (!schedulerChildren.length) {
      error(
        'No Billable Hours',
        'The selected claim source has no children with positive projected hours.',
      );
      return;
    }
    setGenerating(true);
    try {
      const result = await api.post<any>('/schedules/generate', {
        openDays,
        capacity: config.capacity,
        operatingHours: { start: config.operatingStartHour, end: config.operatingEndHour },
        schoolOffDays: effectiveSchoolOffDays,
        dailyCapacityMin: config.dailyCapacityMin,
        dailyCapacityMax: config.dailyCapacityMax,
        childTimeOverrides: overrides,
        children: schedulerChildren,
        seed: `${selectedSource.type}-${selectedSource.batchId}`,
        persist: true,
        sourceClaimBatchId: selectedSource.batchId,
      });
      const namesById = Object.fromEntries(
        schedulerChildren.map((child: { id: string; name: string }) => [String(child.id), child.name]),
      );
      const enrichedResult = {
        ...result,
        child_names: namesById,
        generation_context: {
          operating_hours: {
            start: config.operatingStartHour,
            end: config.operatingEndHour,
          },
          room_capacity: config.capacity,
          daily_child_min: config.dailyCapacityMin,
          daily_child_max: config.dailyCapacityMax,
          closed_days: config.closedDays,
          school_off_days: effectiveSchoolOffDays,
          school_calendar: schoolCalendar ? {
            source: schoolCalendar.source,
            source_detail: schoolCalendar.sourceDetail,
            academic_year: schoolCalendar.academicYear,
            automatic_dates: effectiveSchoolOffDays.filter((value) =>
              automaticSchoolOffDates.has(value),
            ),
            manual_dates: effectiveSchoolOffDays.filter((value) =>
              !automaticSchoolOffDates.has(value),
            ),
          } : null,
          source_name: batchInfo.name,
          claim_only_imports: claimOnlyChildren,
          identity_split_imports: schedulingImportedRows.rows
            .filter((claim) => claim.identity_conflict)
            .map((claim) => ({
              sourceClaimId: claim.id,
              sourceName: claim.corrected_child_name || claim.child_name,
              ...claim.identity_conflict,
            })),
          merged_imported_claims: schedulingImportedRows.rows
            .filter((claim) => claim.source_claim_ids.length > 1)
            .map((claim) => ({
              childId: claim.schedule_child_id,
              sourceClaimIds: claim.source_claim_ids,
              sourceNames: claim.source_claim_names,
              totalHours: Number(claim.corrected_hours ?? claim.hours_claimed),
            })),
        },
        entries: (result.entries || []).map((entry: any, index: number) => ({
          ...entry,
          client_entry_id: entry.id || entry.client_entry_id || `${result.batch_id}-entry-${index}`,
          child_name: namesById[String(entry.child_id)] || entry.child_name,
          source_claim_batch_id: selectedSource.batchId,
        })),
      };
      try {
        sessionStorage.setItem(`caresync:schedule-batch:${result.batch_id}`, JSON.stringify(enrichedResult));
      } catch {
        // The in-memory handoff below keeps the workflow usable when the
        // browser's session quota is already full.
      }
      if (result.persisted === false) {
        success(
          'V3 Diagnostic Generated',
          `Scheduled ${result.stats.total_hours_scheduled.toFixed(1)} of ${result.stats.requested_hours.toFixed(1)} hours. Nothing was written to the database because certification needs review.`,
        );
      } else {
        success(
          'Schedule Generated & Saved',
          `Saved ${result.persisted_entries ?? result.stats.total_entries} entries for ${result.stats.children_scheduled} children${claimOnlyChildren.length ? `, including ${claimOnlyChildren.length} import-only child${claimOnlyChildren.length === 1 ? '' : 'ren'}` : ''}`,
        );
      }
      onScheduleGenerated(result.batch_id, enrichedResult);
    } catch (caught) {
      error('Generation Failed', caught instanceof Error ? caught.message : 'Request failed');
    } finally {
      setGenerating(false);
    }
  };

  // ─── No source selected ─────────────────────────────────────────────────────

  if (!selectedSource) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="p-4 bg-yellow-100 rounded-2xl mb-6">
          <CalendarDaysIcon className="h-12 w-12 text-yellow-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">No Claim Source Selected</h2>
        <p className="text-gray-500 max-w-md text-center">
          Go back to the <strong>Claims</strong> phase and generate or import claims first,
          then select them to continue here.
        </p>
      </div>
    );
  }

  // ─── Main Config UI ─────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      {/* Source summary */}
      {batchInfo && (
        <div className="p-4 bg-blue-50 rounded-xl border border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-blue-500 uppercase tracking-wider">Claim Source</p>
              <p className="font-semibold text-blue-900 text-lg">{batchInfo.name}</p>
              <p className="text-sm text-blue-600">
                {batchInfo.totalChildren} children • {batchInfo.totalHours.toFixed(1)} hours • {MONTHS[batchInfo.month - 1]} {batchInfo.year}
              </p>
            </div>
          </div>
        </div>
      )}

      {importedMatchSummary && (
        <div className="p-4 rounded-xl border bg-amber-50 border-amber-200">
          <p className="font-semibold text-amber-900">
            All {importedMatchSummary.importedRowCount} imported claim rows are ready
          </p>
          <p className="text-sm text-amber-700">
            {importedMatchSummary.claimOnlyCount > 0
              ? `${importedMatchSummary.matchedCount} real child records and ${importedMatchSummary.claimOnlyCount} import-only children will produce ${importedMatchSummary.participantCount} scheduler participants.`
              : 'All imported names are linked to child records.'}
          </p>
          {importedMatchSummary.mergedRowCount > 0 && (
            <p className="mt-1 text-xs font-medium text-amber-700">
              {importedMatchSummary.mergedRowCount} repeated claim row{importedMatchSummary.mergedRowCount === 1 ? ' was' : 's were'} merged into the same real children; their hours are added together without creating duplicate daily attendance.
            </p>
          )}
          {importedMatchSummary.identityConflictCount > 0 && (
            <p className="mt-2 rounded-lg border border-orange-300 bg-orange-100 p-2 text-xs font-medium text-orange-900">
              Identity safety split: {importedMatchSummary.identityConflictCount} repeated claim row{importedMatchSummary.identityConflictCount === 1 ? '' : 's'} had a birth date that contradicted the linked child while another row exactly matched. {importedMatchSummary.identityConflictNames.slice(0, 6).join(', ')}{importedMatchSummary.identityConflictNames.length > 6 ? `, and ${importedMatchSummary.identityConflictNames.length - 6} more` : ''} will be scheduled separately as import-only children; no claimed hours were removed.
            </p>
          )}
          {importedMatchSummary.claimOnlyNames.length > 0 && (
            <p className="mt-1 text-xs text-amber-600">
              Import-only: {importedMatchSummary.claimOnlyNames.slice(0, 6).join(', ')}
              {importedMatchSummary.claimOnlyNames.length > 6
                ? `, and ${importedMatchSummary.claimOnlyNames.length - 6} more`
                : ''}
            </p>
          )}
        </div>
      )}

      {/* Capacity & Hours */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Scheduler Configuration</h2>
        <p className="text-gray-500 text-sm mb-4">Configure capacity and operating hours</p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <label className="flex items-center text-sm font-medium text-gray-700">
              <UserGroupIcon className="h-5 w-5 mr-2 text-gray-400" />
              Slot Capacity
            </label>
            <input
              type="number"
              value={config.capacity}
              onChange={(e) => setConfig({ ...config, capacity: parseInt(e.target.value) || 0 })}
              className="input w-full"
              min={1}
              max={200}
            />
          </div>
          <div className="space-y-2">
            <label className="flex items-center text-sm font-medium text-gray-700">
              <ClockIcon className="h-5 w-5 mr-2 text-gray-400" />
              Opening Time
            </label>
            <select
              value={config.operatingStartHour}
              onChange={(e) => setConfig({ ...config, operatingStartHour: parseInt(e.target.value) })}
              className="input w-full"
            >
              {Array.from({ length: 12 }, (_, i) => i + 5).map((hour) => (
                <option key={hour} value={hour}>{hour}:00 {hour < 12 ? 'AM' : 'PM'}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label className="flex items-center text-sm font-medium text-gray-700">
              <ClockIcon className="h-5 w-5 mr-2 text-gray-400" />
              Closing Time
            </label>
            <select
              value={config.operatingEndHour}
              onChange={(e) => setConfig({ ...config, operatingEndHour: parseInt(e.target.value) })}
              className="input w-full"
            >
              {Array.from({ length: 12 }, (_, i) => i + 12).map((hour) => (
                <option key={hour} value={hour}>{hour > 12 ? hour - 12 : hour}:00 PM</option>
              ))}
            </select>
          </div>
        </div>
        {organization && (
          organization.opening_time !== `${String(config.operatingStartHour).padStart(2, '0')}:00`
          || organization.closing_time !== `${String(config.operatingEndHour).padStart(2, '0')}:00`
        ) && (
          <p className="mt-3 text-sm text-amber-700">
            Organization hours {organization.opening_time}–{organization.closing_time} were rounded inward to whole
            hours ({config.operatingStartHour}:00–{config.operatingEndHour}:00) so the scheduler never places care
            outside the licensed window.
          </p>
        )}
      </div>

      {/* Daily Attendance Range */}
      <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
        <label className="flex items-center text-sm font-medium text-blue-800 mb-3">
          <UserGroupIcon className="h-5 w-5 mr-2" />
          Daily Attendance Distribution Range
        </label>
        <p className="text-xs text-blue-600 mb-4">
          Set the target range for daily attendance. The scheduler will distribute children evenly within this range.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs font-medium text-blue-700">Minimum Children/Day</label>
            <input type="number" value={config.dailyCapacityMin} onChange={(e) => setConfig({ ...config, dailyCapacityMin: parseInt(e.target.value) || 0 })} className="input w-full" min={1} max={config.dailyCapacityMax} />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-blue-700">Maximum Children/Day</label>
            <input type="number" value={config.dailyCapacityMax} onChange={(e) => setConfig({ ...config, dailyCapacityMax: parseInt(e.target.value) || 0 })} className="input w-full" min={config.dailyCapacityMin} max={300} />
          </div>
        </div>
        <p className="text-xs text-blue-500 mt-2">
          Target range: {config.dailyCapacityMin} - {config.dailyCapacityMax} children per day
        </p>
      </div>

      {/* School Off Days */}
      {batchInfo && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center text-sm font-medium text-gray-700">
              <CalendarDaysIcon className="h-5 w-5 mr-2 text-gray-400" />
              School Off Days (for OSC children)
            </label>
            <div className="flex flex-wrap justify-end gap-2">
              {schoolCalendar?.hasOfficialDefaults && (
                <button
                  type="button"
                  onClick={() => updateSchoolOffDays(
                    schoolCalendar.automatic
                      .map((item) => item.date)
                      .filter((value) => value.startsWith(
                        `${batchInfo.year}-${String(batchInfo.month).padStart(2, '0')}-`,
                      )),
                  )}
                  className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                >
                  Use Official
                </button>
              )}
              <button
                type="button"
                onClick={() => updateSchoolOffDays(
                  monthWeekdayDates(batchInfo.year, batchInfo.month),
                )}
                className="text-xs px-2 py-1 bg-orange-100 text-orange-700 rounded hover:bg-orange-200"
              >
                Select All
              </button>
              <button type="button" onClick={() => updateSchoolOffDays([])} className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200">
                Clear All
              </button>
            </div>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Select days when school is closed. OSC children will be scheduled for full days on these dates.
          </p>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-orange-200 bg-orange-50 p-3">
            <div>
              {schoolCalendarLoading && !schoolCalendar ? (
                <p className="text-xs font-medium text-orange-800">Loading Edmonton school calendar…</p>
              ) : schoolCalendarError ? (
                <p className="text-xs font-medium text-red-700">
                  Automatic calendar unavailable. Manual dates still work.
                </p>
              ) : schoolCalendar ? (
                <>
                  <p className="text-xs font-semibold text-orange-900">
                    {schoolCalendar.hasOfficialDefaults
                      ? 'Built-in June school-off defaults loaded'
                      : 'Manual calendar'}
                    {' · '}{schoolCalendar.source}
                  </p>
                  <p className="mt-0.5 text-xs text-orange-700">
                    {schoolCalendar.sourceDetail}
                    {schoolCalendar.academicYear ? ` · Academic year ${schoolCalendar.academicYear}` : ''}
                  </p>
                </>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => void handleSaveSchoolCalendar()}
              disabled={!schoolCalendar || savingSchoolCalendar}
              className="text-xs px-3 py-1.5 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50"
            >
              {savingSchoolCalendar ? 'Saving…' : 'Save School Calendar'}
            </button>
          </div>
          <div className="grid grid-cols-7 gap-2 p-4 bg-gray-50 rounded-lg border max-h-64 overflow-y-auto">
            {(() => {
              const year = batchInfo.year;
              const month = batchInfo.month - 1;
              const daysInMonth = new Date(year, month + 1, 0).getDate();
              const days = [];
              for (let d = 1; d <= daysInMonth; d++) {
                const date = new Date(year, month, d);
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
                const dayOfWeek = date.getDay();
                const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                const isSelected = config.schoolOffDays.includes(dateStr);
                const isAutomatic = automaticSchoolOffDates.has(dateStr);
                const isCustom = customSchoolOffDates.has(dateStr);
                days.push(
                  <button key={dateStr} type="button" disabled={isWeekend}
                    onClick={() => {
                      if (isSelected) updateSchoolOffDays(config.schoolOffDays.filter(d => d !== dateStr));
                      else updateSchoolOffDays([...config.schoolOffDays, dateStr]);
                    }}
                    className={`p-2 text-xs rounded ${isWeekend ? 'bg-gray-200 text-gray-400 cursor-not-allowed' : isSelected ? 'bg-orange-500 text-white font-bold' : isAutomatic ? 'bg-orange-50 border border-orange-300 text-orange-800' : 'bg-white border hover:bg-gray-100'}`}
                    title={isWeekend ? 'Weekend' : schoolOffNames.get(dateStr) || (isSelected ? 'Manual school-off day' : 'Click to mark as school off')}
                  >
                    {d}{isAutomatic ? ' •' : isCustom ? ' +' : ''}
                  </button>
                );
              }
              return days;
            })()}
          </div>
          {config.schoolOffDays.length > 0 && (
            <p className="text-sm text-orange-600 mt-2">
              {config.schoolOffDays.length} school off day(s) selected ·{' '}
              {config.schoolOffDays.filter((value) => automaticSchoolOffDates.has(value)).length} automatic ·{' '}
              {config.schoolOffDays.filter((value) => !automaticSchoolOffDates.has(value)).length} manual
            </p>
          )}
        </div>
      )}

      {/* Closed Days */}
      {batchInfo && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center text-sm font-medium text-gray-700">
              <CalendarDaysIcon className="h-5 w-5 mr-2 text-gray-400" />
              Closed Days / Holidays
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  const year = batchInfo.year;
                  const month = batchInfo.month - 1;
                  const daysInMonth = new Date(year, month + 1, 0).getDate();
                  const allWeekdays: string[] = [];
                  for (let d = 1; d <= daysInMonth; d++) {
                    const date = new Date(year, month, d);
                    if (date.getDay() !== 0 && date.getDay() !== 6) {
                      allWeekdays.push(`${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`);
                    }
                  }
                  setConfig({ ...config, closedDays: allWeekdays });
                }}
                className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
              >
                Select All
              </button>
              <button type="button" onClick={() => setConfig({ ...config, closedDays: [] })} className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200">
                Clear All
              </button>
            </div>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Alberta statutory holidays are loaded automatically. Click any other weekday to add a
            daycare-specific closure; no children will be scheduled on marked days.
          </p>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3 p-3 bg-red-50 border border-red-100 rounded-lg">
            <label className="flex items-center gap-2 text-xs text-red-800">
              <input
                type="checkbox"
                checked={includeOptionalHolidays}
                onChange={(event) => setIncludeOptionalHolidays(event.target.checked)}
                className="rounded border-red-300 text-red-600 focus:ring-red-500"
              />
              Also include optional Alberta holidays (Easter Monday, Heritage Day, Truth and
              Reconciliation Day, Boxing Day)
            </label>
            <button
              type="button"
              onClick={() => void handleSaveClosures()}
              disabled={savingClosures}
              className="text-xs px-3 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
            >
              {savingClosures ? 'Saving…' : 'Save Closure Calendar'}
            </button>
          </div>
          <div className="grid grid-cols-7 gap-2 p-4 bg-gray-50 rounded-lg border max-h-64 overflow-y-auto">
            {(() => {
              const year = batchInfo.year;
              const month = batchInfo.month - 1;
              const daysInMonth = new Date(year, month + 1, 0).getDate();
              const days = [];
              for (let d = 1; d <= daysInMonth; d++) {
                const date = new Date(year, month, d);
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
                const dayOfWeek = date.getDay();
                const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                const isSelected = config.closedDays.includes(dateStr);
                days.push(
                  <button key={`closed-${dateStr}`} type="button" disabled={isWeekend}
                    onClick={() => {
                      if (isSelected) setConfig({ ...config, closedDays: config.closedDays.filter(d => d !== dateStr) });
                      else setConfig({ ...config, closedDays: [...config.closedDays, dateStr] });
                    }}
                    className={`p-2 text-xs rounded ${isWeekend ? 'bg-gray-200 text-gray-400 cursor-not-allowed' : isSelected ? 'bg-red-500 text-white font-bold' : 'bg-white border hover:bg-gray-100'}`}
                    title={isWeekend ? 'Weekend' : closureNames.get(dateStr) || (isSelected ? 'Daycare closed' : 'Click to mark as closed')}
                  >
                    {d}{closureNames.has(dateStr) ? ' •' : ''}
                  </button>
                );
              }
              return days;
            })()}
          </div>
          {config.closedDays.length > 0 && (
            <p className="text-sm text-red-600 mt-2">{config.closedDays.length} closed day(s) selected</p>
          )}
        </div>
      )}

      {/* Per-Child Time Constraints */}
      <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
        <div className="flex items-center justify-between mb-3">
          <label className="flex items-center text-sm font-medium text-purple-800">
            <ClockIcon className="h-5 w-5 mr-2" />
            Child Time Constraints
          </label>
          <button
            type="button"
            onClick={() => setChildTimeOverrides([...childTimeOverrides, { childIdentifier: '', daysOfWeek: [] }])}
            className="text-xs px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 flex items-center"
          >
            <PlusIcon className="h-3 w-3 mr-1" />
            Add Override
          </button>
        </div>
        <p className="text-xs text-purple-600 mb-3">
          Set specific morning and afternoon sign-in/out times for individual children.
        </p>

        {childTimeOverrides.length === 0 ? (
          <p className="text-xs text-purple-400 italic">No child-specific constraints. All children use default operating hours.</p>
        ) : (
          <div className="space-y-3">
            {childTimeOverrides.map((override, index) => (
              <div key={index} className="bg-white p-3 rounded border border-purple-100 space-y-2">
                <div className="flex items-center gap-2">
                  <select
                    value={override.childIdentifier}
                    onChange={(e) => { const u = [...childTimeOverrides]; u[index] = { ...u[index], childIdentifier: e.target.value }; setChildTimeOverrides(u); }}
                    className="input text-sm py-1 px-2 flex-1"
                  >
                    <option value="">Select child...</option>
                    {claimChildren.map((c) => (
                      <option key={c.id} value={c.name}>{c.name} ({c.hours.toFixed(1)}h)</option>
                    ))}
                  </select>
                  <button type="button" onClick={() => setChildTimeOverrides(childTimeOverrides.filter((_, i) => i !== index))}
                    className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded" title="Remove"
                  >
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                </div>
                {/* Day-of-week selector */}
                <div className="flex items-center gap-1">
                  <span className="text-xs text-gray-500 mr-1">Days:</span>
                  {[{d:1,l:'Mon'},{d:2,l:'Tue'},{d:3,l:'Wed'},{d:4,l:'Thu'},{d:5,l:'Fri'}].map(({d,l}) => {
                    const active = override.daysOfWeek.includes(d);
                    return (
                      <button key={d} type="button"
                        onClick={() => {
                          const u = [...childTimeOverrides];
                          u[index] = { ...u[index], daysOfWeek: active ? u[index].daysOfWeek.filter(x => x !== d) : [...u[index].daysOfWeek, d] };
                          setChildTimeOverrides(u);
                        }}
                        className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${active ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-500 hover:bg-purple-100'}`}
                      >{l}</button>
                    );
                  })}
                  <span className="text-xs text-gray-400 ml-2">{override.daysOfWeek.length === 0 ? '(all days)' : ''}</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-2 bg-yellow-50 rounded border border-yellow-100">
                    <p className="text-xs font-medium text-yellow-800 mb-1">Morning Session</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <label className="text-xs text-gray-500">Sign In</label>
                        <input type="time" value={override.startTime1 || ''}
                          onChange={(e) => { const u = [...childTimeOverrides]; u[index] = { ...u[index], startTime1: e.target.value }; setChildTimeOverrides(u); }}
                          className="input text-sm py-1 px-2 w-full"
                        />
                      </div>
                      <span className="text-gray-400 text-xs mt-4">→</span>
                      <div className="flex-1">
                        <label className="text-xs text-gray-500">Sign Out</label>
                        <input type="time" value={override.endTime1 || ''}
                          onChange={(e) => { const u = [...childTimeOverrides]; u[index] = { ...u[index], endTime1: e.target.value }; setChildTimeOverrides(u); }}
                          className="input text-sm py-1 px-2 w-full"
                        />
                      </div>
                    </div>
                  </div>
                  <div className="p-2 bg-blue-50 rounded border border-blue-100">
                    <p className="text-xs font-medium text-blue-800 mb-1">Afternoon Session</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <label className="text-xs text-gray-500">Sign In</label>
                        <input type="time" value={override.startTime2 || ''}
                          onChange={(e) => { const u = [...childTimeOverrides]; u[index] = { ...u[index], startTime2: e.target.value }; setChildTimeOverrides(u); }}
                          className="input text-sm py-1 px-2 w-full"
                        />
                      </div>
                      <span className="text-gray-400 text-xs mt-4">→</span>
                      <div className="flex-1">
                        <label className="text-xs text-gray-500">Sign Out</label>
                        <input type="time" value={override.endTime2 || ''}
                          onChange={(e) => { const u = [...childTimeOverrides]; u[index] = { ...u[index], endTime2: e.target.value }; setChildTimeOverrides(u); }}
                          className="input text-sm py-1 px-2 w-full"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-Child Absent Days */}
      {batchInfo && (
        <div className="p-4 bg-red-50 rounded-lg border border-red-200">
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center text-sm font-medium text-red-800">
              <CalendarDaysIcon className="h-5 w-5 mr-2" />
              Child Absent Days
            </label>
            <button
              type="button"
              onClick={() => setChildAbsentDays([...childAbsentDays, { childIdentifier: '', dates: [] }])}
              className="text-xs px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 flex items-center"
            >
              <PlusIcon className="h-3 w-3 mr-1" />
              Add Child
            </button>
          </div>
          <p className="text-xs text-red-600 mb-3">
            Mark specific days a child was absent. The scheduler will skip those dates for that child.
          </p>

          {childAbsentDays.length === 0 ? (
            <p className="text-xs text-red-400 italic">No child absences configured. All children will be scheduled on all open days.</p>
          ) : (
            <div className="space-y-3">
              {childAbsentDays.map((entry, index) => (
                <div key={index} className="bg-white p-3 rounded border border-red-100 space-y-2">
                  <div className="flex items-center gap-2">
                    <select
                      value={entry.childIdentifier}
                      onChange={(e) => {
                        const u = [...childAbsentDays];
                        u[index] = { ...u[index], childIdentifier: e.target.value };
                        setChildAbsentDays(u);
                      }}
                      className="input text-sm py-1 px-2 flex-1"
                    >
                      <option value="">Select child...</option>
                      {claimChildren.map((c) => (
                        <option key={c.id} value={c.name}>{c.name} ({c.hours.toFixed(1)}h)</option>
                      ))}
                    </select>
                    <span className="text-xs text-gray-500">{entry.dates.length} day(s)</span>
                    <button
                      type="button"
                      onClick={() => setChildAbsentDays(childAbsentDays.filter((_, i) => i !== index))}
                      className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded" title="Remove"
                    >
                      <XMarkIcon className="h-4 w-4" />
                    </button>
                  </div>
                  {/* Date grid */}
                  <div className="grid grid-cols-7 gap-1">
                    {(() => {
                      const year = batchInfo.year;
                      const month = batchInfo.month - 1;
                      const daysInMonth = new Date(year, month + 1, 0).getDate();
                      const days = [];
                      for (let d = 1; d <= daysInMonth; d++) {
                        const date = new Date(year, month, d);
                        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
                        const dayOfWeek = date.getDay();
                        const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                        const isClosed = config.closedDays.includes(dateStr);
                        const isAbsent = entry.dates.includes(dateStr);
                        days.push(
                          <button
                            key={dateStr}
                            type="button"
                            disabled={isWeekend || isClosed}
                            onClick={() => {
                              const u = [...childAbsentDays];
                              if (isAbsent) {
                                u[index] = { ...u[index], dates: u[index].dates.filter(dd => dd !== dateStr) };
                              } else {
                                u[index] = { ...u[index], dates: [...u[index].dates, dateStr] };
                              }
                              setChildAbsentDays(u);
                            }}
                            className={`p-1 text-xs rounded ${
                              isWeekend || isClosed
                                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                                : isAbsent
                                  ? 'bg-red-500 text-white font-bold'
                                  : 'bg-white border hover:bg-red-50'
                            }`}
                            title={isWeekend ? 'Weekend' : isClosed ? 'Facility closed' : isAbsent ? 'Absent' : 'Click to mark absent'}
                          >
                            {d}
                          </button>
                        );
                      }
                      return days;
                    })()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Config Summary */}
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h3 className="font-medium text-gray-900 mb-3">Configuration Summary</h3>
        <div className="grid grid-cols-4 gap-4 text-sm">
          <div className="p-3 bg-white rounded-lg border">
            <p className="text-gray-500">Capacity</p>
            <p className="font-bold text-gray-900 text-lg">{config.capacity}</p>
          </div>
          <div className="p-3 bg-white rounded-lg border">
            <p className="text-gray-500">Opens</p>
            <p className="font-bold text-gray-900 text-lg">{config.operatingStartHour}:00</p>
          </div>
          <div className="p-3 bg-white rounded-lg border">
            <p className="text-gray-500">Closes</p>
            <p className="font-bold text-gray-900 text-lg">{config.operatingEndHour}:00</p>
          </div>
          <div className="p-3 bg-white rounded-lg border">
            <p className="text-gray-500">Hours/Day</p>
            <p className="font-bold text-gray-900 text-lg">{config.operatingEndHour - config.operatingStartHour}h</p>
          </div>
        </div>
      </div>

      {/* Generate Button */}
      <div className="flex justify-end pt-4 border-t border-gray-200">
        <button
          onClick={handleGenerate}
          disabled={generating || !schoolCalendarGenerationReady}
          className="btn btn-primary px-8 py-3 text-lg flex items-center space-x-2"
        >
          {generating ? (
            <>
              <ArrowPathIcon className="h-5 w-5 animate-spin" />
              <span>Generating Schedule...</span>
            </>
          ) : !schoolCalendarGenerationReady ? (
            <>
              <ArrowPathIcon className="h-5 w-5 animate-spin" />
              <span>Loading School Calendar...</span>
            </>
          ) : (
            <>
              <PlayIcon className="h-5 w-5" />
              <span>Generate Schedule</span>
              <ArrowRightIcon className="h-4 w-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default SchedulePhase;
