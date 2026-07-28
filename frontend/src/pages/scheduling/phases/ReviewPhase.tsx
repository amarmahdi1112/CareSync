import React, { useState, useMemo, useCallback } from 'react';
import {
  UserIcon,
  CalendarDaysIcon,
  ClockIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
  LockClosedIcon,
  ArrowPathIcon,
  ArrowRightIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../stores';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// ─── Types ──────────────────────────────────────────────────────────────────────

interface ScheduledEntry {
  id: string;
  child_id: string;
  child_name?: string;
  date: string;
  startTime1?: string;
  endTime1?: string;
  startTime2?: string;
  endTime2?: string;
  is_locked?: boolean;
}

interface ChildInfo {
  id: string;
  first_name: string;
  last_name: string;
}

interface EditedEntry {
  entryId: string;
  startTime1?: string;
  endTime1?: string;
  startTime2?: string;
  endTime2?: string;
}

interface ReviewPhaseProps {
  activeBatchId: string | null;
  scheduleResult?: unknown;
  onContinueToExport?: () => void;
}

// ─── Helpers ────────────────────────────────────────────────────────────────────

function calculateHours(start?: string, end?: string): number {
  if (!start || !end) return 0;
  const [startH, startM] = start.split(':').map(Number);
  const [endH, endM] = end.split(':').map(Number);
  return ((endH * 60 + endM) - (startH * 60 + startM)) / 60;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return 'N/A';
  const date = new Date(dateStr.includes('T') ? dateStr : `${dateStr}T12:00:00`);
  if (isNaN(date.getTime())) return 'Invalid Date';
  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function getChildName(childId: string): string {
  return childId
    .replace('imported-', '')
    .replace(/^\d+-/, '')
    .replace(/-/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function validateTimeBlocks(
  start1: string,
  end1: string,
  start2: string,
  end2: string,
  openingHour = 0,
  closingHour = 24,
  alignmentMinutes?: number,
): string | null {
  const minutes = (value: string) => {
    if (!/^\d{2}:\d{2}$/.test(value)) return Number.NaN;
    const [hour, minute] = value.split(':').map(Number);
    return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59
      ? hour * 60 + minute
      : Number.NaN;
  };
  if (!start1 || !end1) return 'Session 1 needs both a start and end time.';
  if (Boolean(start2) !== Boolean(end2)) return 'Session 2 needs both a start and end time.';
  const firstStart = minutes(start1);
  const firstEnd = minutes(end1);
  if (!Number.isFinite(firstStart) || !Number.isFinite(firstEnd)) return 'Enter valid 24-hour times.';
  if (firstEnd <= firstStart) return 'Session 1 must end after it starts.';
  if (firstStart < openingHour * 60 || firstEnd > closingHour * 60) return 'Session 1 is outside operating hours.';
  if (start2 && end2) {
    const secondStart = minutes(start2);
    const secondEnd = minutes(end2);
    if (!Number.isFinite(secondStart) || !Number.isFinite(secondEnd)) return 'Enter valid Session 2 times.';
    if (secondEnd <= secondStart) return 'Session 2 must end after it starts.';
    if (secondStart < firstEnd) return 'Session 2 cannot overlap Session 1.';
    if (secondStart < openingHour * 60 || secondEnd > closingHour * 60) return 'Session 2 is outside operating hours.';
  }
  if (alignmentMinutes && [start1, end1, start2, end2]
    .filter(Boolean)
    .some(value => minutes(value) % alignmentMinutes !== 0)) {
    return `V3-certified schedules require every time to align to a ${alignmentMinutes}-minute boundary.`;
  }
  return null;
}

function refreshTransientStats(schedule: any) {
  const entryHours = (entry: any) => calculateHours(entry.start_time, entry.end_time)
    + calculateHours(entry.start_time_2, entry.end_time_2);
  const totalHours = (schedule.entries || []).reduce((sum: number, entry: any) => sum + entryHours(entry), 0);
  const children = new Set((schedule.entries || []).map((entry: any) => entry.child_id));
  schedule.stats = {
    ...(schedule.stats || {}),
    total_entries: schedule.entries?.length || 0,
    total_hours_scheduled: totalHours,
    children_scheduled: children.size,
    unscheduled_children: Math.max(0, Number(schedule.stats?.requested_children || 0) - children.size),
    hours_shortfall: Math.max(0, Number(schedule.stats?.requested_hours || 0) - totalHours),
    completion_percentage: schedule.stats?.requested_hours
      ? totalHours / Number(schedule.stats.requested_hours) * 100
      : 100,
  };
  schedule.manual_changes = true;
  if (!(schedule.warnings || []).some((warning: any) => warning.code === 'MANUAL_CHANGES')) {
    schedule.warnings = [...(schedule.warnings || []), {
      severity: 'warning',
      code: 'MANUAL_CHANGES',
      message: 'This schedule was manually changed after generation; review totals before export.',
    }];
  }
  if (String(schedule.algorithm_version || '').startsWith('3.')
    && !(schedule.warnings || []).some((warning: any) => warning.code === 'V3_CERTIFICATION_INVALIDATED')) {
    schedule.warnings = [...(schedule.warnings || []), {
      severity: 'critical',
      code: 'V3_CERTIFICATION_INVALIDATED',
      message: 'A manual change invalidated the independent V3 audit certification. Regenerate this schedule with V3 before export.',
    }];
  }
}

function validateTransientCapacity(entries: any[], context: any): string | null {
  const capacity = Number(context?.room_capacity || 0);
  const openingHour = Number(context?.operating_hours?.start ?? 0);
  if (!capacity) return null;
  const occupancy = new Map<string, number>();
  const minutes = (value: string) => {
    const [hour, minute] = value.split(':').map(Number);
    return hour * 60 + minute;
  };
  for (const entry of entries) {
    const blocks = [
      [entry.start_time, entry.end_time],
      [entry.start_time_2, entry.end_time_2],
    ].filter(([start, end]) => start && end) as string[][];
    for (const [start, end] of blocks) {
      const startSlot = Math.floor((minutes(start) - openingHour * 60) / 5);
      const endSlot = Math.ceil((minutes(end) - openingHour * 60) / 5);
      for (let slot = startSlot; slot < endSlot; slot += 1) {
        const key = `${entry.date}:${slot}`;
        const next = (occupancy.get(key) || 0) + 1;
        if (next > capacity) return `This edit would exceed room capacity on ${formatDate(entry.date)}.`;
        occupancy.set(key, next);
      }
    }
  }
  return null;
}

// ─── Component ──────────────────────────────────────────────────────────────────

type ViewMode = 'byChild' | 'byDay';

const ReviewPhase: React.FC<ReviewPhaseProps> = ({ activeBatchId, scheduleResult, onContinueToExport }) => {
  const { success, error } = useNotificationStore();

  const [viewMode, setViewMode] = useState<ViewMode>('byChild');
  const [expandedChildren, setExpandedChildren] = useState<Set<string>>(new Set());
  const [editingChildId, setEditingChildId] = useState<string | null>(null);
  const [editedEntries, setEditedEntries] = useState<Map<string, EditedEntry>>(new Map());
  const [savingEdits, setSavingEdits] = useState(false);
  const [deletingEntries, setDeletingEntries] = useState(false);
  const [revision, setRevision] = useState(0);
  const [safetyAcknowledged, setSafetyAcknowledged] = useState(false);

  const { data, loading, refetch } = useApiQuery<ScheduledEntry[]>('/resources/scheduled_attendance', {
    batch_id: activeBatchId || undefined,
    limit: 5000,
  });
  const { data: children = [] } = useApiQuery<ChildInfo[]>('/children', { limit: 1000 });
  const transientSchedule = useMemo(() => {
    if (scheduleResult && typeof scheduleResult === 'object') {
      return scheduleResult as ReturnType<typeof JSON.parse>;
    }
    if (!activeBatchId) return null;
    const value = sessionStorage.getItem(`caresync:schedule-batch:${activeBatchId}`);
    if (!value) return null;
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  }, [activeBatchId, scheduleResult, revision]);

  const entries: ScheduledEntry[] = useMemo(() => transientSchedule
    ? (transientSchedule.entries || []).map((entry: any, index: number) => ({
      id: entry.id || entry.client_entry_id || `transient-${index}`,
      child_id: entry.child_id,
      child_name: entry.child_name,
      date: entry.date,
      startTime1: entry.start_time,
      endTime1: entry.end_time,
      startTime2: entry.start_time_2,
      endTime2: entry.end_time_2,
      is_locked: Boolean(entry.is_locked),
    }))
    : (data || []), [transientSchedule, data]);

  const childNameById = useMemo(
    () => new Map(children.map(child => [child.id, `${child.first_name} ${child.last_name}`])),
    [children],
  );
  const resolveChildName = useCallback((entry: ScheduledEntry) => entry.child_name
    || transientSchedule?.child_names?.[entry.child_id]
    || childNameById.get(entry.child_id)
    || getChildName(entry.child_id), [transientSchedule, childNameById]);
  const scheduleWarnings = transientSchedule?.warnings || [];
  const scheduleStats = transientSchedule?.stats;
  const isV3Schedule = String(transientSchedule?.algorithm_version || '').startsWith('3.');
  const completionPercentage = Number(scheduleStats?.completion_percentage ?? 100);
  const hasV3IncompleteWarning = scheduleWarnings.some(
    (warning: any) => warning.code === 'V3_INCOMPLETE_NOT_PERSISTABLE',
  );
  const hasV3RealismFailureWarning = scheduleWarnings.some(
    (warning: any) => warning.code === 'V3_DAYCARE_REALISM_NOT_PERSISTABLE',
  );
  const v3CertificationInvalidated = isV3Schedule && scheduleWarnings.some(
    (warning: any) => warning.code === 'V3_CERTIFICATION_INVALIDATED',
  );
  const v3Incomplete = isV3Schedule
    && (completionPercentage < 100 || hasV3IncompleteWarning);
  const v3RealismFailed = isV3Schedule && hasV3RealismFailureWarning;
  const v3ExportBlocked = v3Incomplete || v3CertificationInvalidated || v3RealismFailed;
  const criticalWarnings = scheduleWarnings.filter((warning: any) => warning.severity === 'critical');
  const requiresSafetyReview = criticalWarnings.length > 0
    || (scheduleStats?.completion_percentage != null && scheduleStats.completion_percentage < 99.5);

  React.useEffect(() => setSafetyAcknowledged(false), [activeBatchId]);
  React.useEffect(() => {
    if (!transientSchedule || transientSchedule.persisted) return undefined;
    const warnBeforeClose = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener('beforeunload', warnBeforeClose);
    return () => window.removeEventListener('beforeunload', warnBeforeClose);
  }, [transientSchedule]);

  const handleDeleteEntry = async (entryId: string, childName: string) => {
    if (window.confirm(`Delete this day entry for ${childName}?`)) {
      setDeletingEntries(true);
      try {
        if (transientSchedule) {
          const index = transientSchedule.entries.findIndex(
            (entry: any, entryIndex: number) => (entry.id || entry.client_entry_id || `transient-${entryIndex}`) === entryId,
          );
          if (index < 0) throw new Error('The schedule entry no longer exists');
          if (transientSchedule.persisted) {
            await api.resources.remove('scheduled_attendance', entryId);
          }
          transientSchedule.entries.splice(index, 1);
          refreshTransientStats(transientSchedule);
          sessionStorage.setItem(`caresync:schedule-batch:${activeBatchId}`, JSON.stringify(transientSchedule));
          setRevision((value) => value + 1);
          setSafetyAcknowledged(false);
        } else {
          await api.resources.remove('scheduled_attendance', entryId);
          await refetch();
        }
        success('Deleted', 'Entry removed');
      } catch (caught) {
        error('Delete Failed', caught instanceof Error ? caught.message : 'Request failed');
      } finally {
        setDeletingEntries(false);
      }
    }
  };

  // Group by child
  const groupedByChild = useMemo(() => {
    const map = new Map<string, { id: string; name: string; entries: ScheduledEntry[]; totalHours: number }>();
    entries.forEach(entry => {
      if (!map.has(entry.child_id)) {
        map.set(entry.child_id, { id: entry.child_id, name: resolveChildName(entry), entries: [], totalHours: 0 });
      }
      const child = map.get(entry.child_id)!;
      child.entries.push(entry);
      child.totalHours += calculateHours(entry.startTime1, entry.endTime1) + calculateHours(entry.startTime2, entry.endTime2);
    });
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [entries, resolveChildName]);

  // Group by day
  const groupedByDay = useMemo(() => {
    const map = new Map<string, ScheduledEntry[]>();
    entries.forEach(entry => {
      if (!map.has(entry.date)) map.set(entry.date, []);
      map.get(entry.date)!.push(entry);
    });
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, dayEntries]) => ({
        date,
        entries: dayEntries,
        childCount: new Set(dayEntries.map(e => e.child_id)).size,
        totalHours: dayEntries.reduce((sum, e) => sum + calculateHours(e.startTime1, e.endTime1) + calculateHours(e.startTime2, e.endTime2), 0),
      }));
  }, [entries]);

  const toggleChild = (id: string) => {
    const next = new Set(expandedChildren);
    if (next.has(id)) next.delete(id); else next.add(id);
    setExpandedChildren(next);
  };

  const handleSaveEdits = async () => {
    const edits = Array.from(editedEntries.values());
    if (!edits.length) {
      setEditingChildId(null);
      return;
    }
    const openingHour = Number(transientSchedule?.generation_context?.operating_hours?.start ?? 0);
    const closingHour = Number(transientSchedule?.generation_context?.operating_hours?.end ?? 24);
    for (const edit of edits) {
      const validationError = validateTimeBlocks(
        edit.startTime1 || '',
        edit.endTime1 || '',
        edit.startTime2 || '',
        edit.endTime2 || '',
        openingHour,
        closingHour,
        isV3Schedule ? 5 : undefined,
      );
      if (validationError) {
        error('Invalid Attendance Times', validationError);
        return;
      }
    }
    if (transientSchedule) {
      const projectedEntries = transientSchedule.entries.map((entry: any) => ({ ...entry }));
      for (const edit of edits) {
        const index = projectedEntries.findIndex(
          (entry: any, entryIndex: number) => (entry.id || entry.client_entry_id || `transient-${entryIndex}`) === edit.entryId,
        );
        if (index < 0) {
          error('Edit Conflict', 'The schedule changed while you were editing. Reopen the child and try again.');
          return;
        }
        Object.assign(projectedEntries[index], {
          start_time: edit.startTime1 || null,
          end_time: edit.endTime1 || null,
          start_time_2: edit.startTime2 || null,
          end_time_2: edit.endTime2 || null,
        });
      }
      const capacityError = validateTransientCapacity(
        projectedEntries,
        transientSchedule.generation_context,
      );
      if (capacityError) {
        error('Capacity Conflict', capacityError);
        return;
      }
    }
    setSavingEdits(true);
    try {
      for (const edit of edits) {
        if (transientSchedule) {
          const index = transientSchedule.entries.findIndex(
            (entry: any, entryIndex: number) => (entry.id || entry.client_entry_id || `transient-${entryIndex}`) === edit.entryId,
          );
          if (index < 0) throw new Error('The schedule entry no longer exists');
          if (transientSchedule.persisted) {
            await api.resources.update('scheduled_attendance', edit.entryId, {
              startTime1: edit.startTime1 || null,
              endTime1: edit.endTime1 || null,
              startTime2: edit.startTime2 || null,
              endTime2: edit.endTime2 || null,
              is_locked: true,
            });
          }
          const target = transientSchedule.entries[index];
          target.start_time = edit.startTime1 || null;
          target.end_time = edit.endTime1 || null;
          target.start_time_2 = edit.startTime2 || null;
          target.end_time_2 = edit.endTime2 || null;
          target.hours = calculateHours(target.start_time, target.end_time)
            + calculateHours(target.start_time_2, target.end_time_2);
          target.is_locked = true;
        } else {
          await api.resources.update('scheduled_attendance', edit.entryId, {
            startTime1: edit.startTime1 || null,
            endTime1: edit.endTime1 || null,
            startTime2: edit.startTime2 || null,
            endTime2: edit.endTime2 || null,
            is_locked: true,
          });
        }
      }
      if (transientSchedule) {
        refreshTransientStats(transientSchedule);
        sessionStorage.setItem(`caresync:schedule-batch:${activeBatchId}`, JSON.stringify(transientSchedule));
        setRevision((value) => value + 1);
        setSafetyAcknowledged(false);
      } else {
        await refetch();
      }
      success('Saved', `Saved and locked ${edits.length} entries`);
    } catch {
      error('Error', 'Failed to save changes');
    }
    setSavingEdits(false);
    setEditingChildId(null);
    setEditedEntries(new Map());
  };

  // ─── Empty state ────────────────────────────────────────────────────────────

  if (!activeBatchId) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="p-4 bg-yellow-100 rounded-2xl mb-6">
          <CalendarDaysIcon className="h-12 w-12 text-yellow-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">No Schedule Selected</h2>
        <p className="text-gray-500 text-center max-w-md">
          Generate a schedule in the previous phase, or select one from the history panel on the left.
        </p>
      </div>
    );
  }

  if (loading && !transientSchedule) {
    return (
      <div className="flex items-center justify-center py-24">
        <ArrowPathIcon className="h-10 w-10 animate-spin text-gray-400" />
      </div>
    );
  }

  // ─── Main ───────────────────────────────────────────────────────────────────

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Review Schedule</h2>
          <p className="text-sm text-gray-500">
            {groupedByChild.length} children • {entries.length} entries
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* View mode toggle */}
          <div className="flex p-1 bg-gray-100 rounded-lg">
            <button
              onClick={() => setViewMode('byChild')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === 'byChild' ? 'bg-white text-primary-600 shadow-sm' : 'text-gray-600'}`}
            >
              By Child
            </button>
            <button
              onClick={() => setViewMode('byDay')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === 'byDay' ? 'bg-white text-primary-600 shadow-sm' : 'text-gray-600'}`}
            >
              By Day
            </button>
          </div>
          {onContinueToExport && (
            <button
              onClick={onContinueToExport}
              disabled={v3ExportBlocked
                || (requiresSafetyReview && !safetyAcknowledged)
                || editedEntries.size > 0}
              title={v3CertificationInvalidated
                ? 'Export blocked: manual changes invalidated the independent V3 audit. Regenerate the schedule.'
                : v3RealismFailed
                  ? 'Export blocked: Daycare realism could not be certified. Adjust the available dates or capacity, then regenerate.'
                : v3Incomplete
                  ? 'Export blocked: incomplete V3 schedules cannot be exported or overridden. Regenerate the schedule.'
                  : editedEntries.size > 0
                    ? 'Save or cancel attendance edits before export'
                    : requiresSafetyReview && !safetyAcknowledged
                      ? 'Review and acknowledge the schedule warnings first'
                      : undefined}
              className="btn btn-primary flex items-center space-x-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span>Continue to Export</span>
              <ArrowRightIcon className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {transientSchedule && (
        <div className={`mb-6 rounded-xl border p-4 ${v3ExportBlocked ? 'border-red-300 bg-red-50' : requiresSafetyReview ? 'border-amber-300 bg-amber-50' : 'border-emerald-200 bg-emerald-50'}`}>
          <div className="flex items-start gap-3">
            {v3ExportBlocked || requiresSafetyReview
              ? <ExclamationTriangleIcon className={`mt-0.5 h-6 w-6 shrink-0 ${v3ExportBlocked ? 'text-red-600' : 'text-amber-600'}`} />
              : <ShieldCheckIcon className="mt-0.5 h-6 w-6 shrink-0 text-emerald-600" />}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {transientSchedule.persisted ? 'Saved database schedule' : 'Unsaved browser draft'} • Engine {transientSchedule.algorithm_version || 'V2'}
                  </p>
                  <h3 className={`font-semibold ${v3ExportBlocked ? 'text-red-950' : requiresSafetyReview ? 'text-amber-950' : 'text-emerald-950'}`}>
                    {v3CertificationInvalidated
                      ? 'V3 certification invalidated — regeneration required'
                      : v3RealismFailed
                        ? 'Daycare realism could not be certified — export blocked'
                      : v3Incomplete
                        ? 'Incomplete V3 schedule — export blocked'
                        : requiresSafetyReview
                          ? 'Schedule requires review before export'
                          : 'Generation safety checks passed'}
                  </h3>
                  {scheduleStats && (
                    <p className={`mt-1 text-sm ${v3ExportBlocked ? 'text-red-800' : requiresSafetyReview ? 'text-amber-800' : 'text-emerald-800'}`}>
                      {Number(scheduleStats.completion_percentage ?? 100).toFixed(1)}% of requested hours scheduled
                      {' • '}{scheduleStats.children_scheduled}/{scheduleStats.requested_children ?? scheduleStats.children_scheduled} children
                      {' • '}{Number(scheduleStats.total_hours_scheduled ?? 0).toFixed(1)}/{Number(scheduleStats.requested_hours ?? scheduleStats.total_hours_scheduled ?? 0).toFixed(1)} hours
                    </p>
                  )}
                  {v3ExportBlocked && (
                    <p className="mt-2 text-sm font-medium text-red-800">
                      {v3CertificationInvalidated
                        ? 'Manual changes are outside the independent V3 audit. Warning acknowledgment cannot restore certification; regenerate before export.'
                        : v3RealismFailed
                          ? 'The exact raw allocation was preserved, but its Daycare hours could not be relocated within the realism limits. Nothing was saved; adjust dates or capacity and regenerate.'
                        : 'V3 must reach 100% completion and pass certification. Warning acknowledgment cannot override this export block.'}
                    </p>
                  )}
                </div>
                {requiresSafetyReview && !v3ExportBlocked && (
                  <button
                    type="button"
                    onClick={() => setSafetyAcknowledged(true)}
                    className={`rounded-lg px-3 py-2 text-xs font-semibold ${safetyAcknowledged ? 'bg-emerald-600 text-white' : 'bg-amber-600 text-white hover:bg-amber-700'}`}
                  >
                    {safetyAcknowledged ? 'Warnings acknowledged' : 'I reviewed these warnings'}
                  </button>
                )}
              </div>
              {scheduleWarnings.length > 0 && (
                <ul className={`mt-3 space-y-1 text-sm ${v3ExportBlocked ? 'text-red-900' : 'text-amber-900'}`}>
                  {scheduleWarnings.slice(0, 6).map((warning: any, index: number) => (
                    <li key={`${warning.code}-${index}`}>• {warning.message}</li>
                  ))}
                  {scheduleWarnings.length > 6 && <li>• {scheduleWarnings.length - 6} additional warnings are recorded in this batch.</li>}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── By Child View ─── */}
      {viewMode === 'byChild' && (
        <div className="space-y-3">
          <div className="flex gap-2 mb-4">
            <button onClick={() => setExpandedChildren(new Set(groupedByChild.map(c => c.id)))} className="btn btn-secondary text-xs">Expand All</button>
            <button onClick={() => setExpandedChildren(new Set())} className="btn btn-secondary text-xs">Collapse All</button>
          </div>

          {groupedByChild.map((child) => (
            <div key={child.id} className="border border-gray-200 rounded-lg overflow-hidden">
              <button
                onClick={() => toggleChild(child.id)}
                className="w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 flex items-center justify-between"
              >
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-primary-100 rounded-full">
                    <UserIcon className="h-5 w-5 text-primary-600" />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-gray-900">{child.name}</p>
                    <p className="text-sm text-gray-500">{child.entries.length} days • {child.totalHours.toFixed(1)}h</p>
                  </div>
                </div>
                {expandedChildren.has(child.id) ? (
                  <ChevronUpIcon className="h-5 w-5 text-gray-400" />
                ) : (
                  <ChevronDownIcon className="h-5 w-5 text-gray-400" />
                )}
              </button>

              {expandedChildren.has(child.id) && (
                <div className="p-4">
                  {/* Edit controls */}
                  <div className="flex justify-end mb-3">
                    {editingChildId === child.id ? (
                      <div className="flex gap-2">
                        <button
                          onClick={handleSaveEdits}
                          disabled={savingEdits}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                        >
                          <CheckIcon className="h-3 w-3" />
                          {savingEdits ? 'Saving...' : 'Save & Lock'}
                        </button>
                        <button onClick={() => { setEditingChildId(null); setEditedEntries(new Map()); }}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                        >
                          <XMarkIcon className="h-3 w-3" />
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setEditingChildId(child.id)}
                        disabled={child.entries.some(entry => entry.is_locked)}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500"
                      >
                        {child.entries.some(entry => entry.is_locked)
                          ? <LockClosedIcon className="h-3 w-3" />
                          : <PencilIcon className="h-3 w-3" />}
                        {child.entries.some(entry => entry.is_locked) ? 'Locked' : 'Edit Times'}
                      </button>
                    )}
                  </div>

                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="py-2 px-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                        <th className="py-2 px-3 text-left text-xs font-medium text-gray-500 uppercase">Session 1</th>
                        <th className="py-2 px-3 text-left text-xs font-medium text-gray-500 uppercase">Session 2</th>
                        <th className="py-2 px-3 text-right text-xs font-medium text-gray-500 uppercase">Hours</th>
                        <th className="py-2 px-3 text-center text-xs font-medium text-gray-500 uppercase w-10"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {child.entries.sort((a, b) => a.date.localeCompare(b.date)).map((entry) => {
                        const isEditing = editingChildId === child.id;
                        const edited = editedEntries.get(entry.id);
                        const s1 = edited?.startTime1 ?? entry.startTime1 ?? '';
                        const e1 = edited?.endTime1 ?? entry.endTime1 ?? '';
                        const s2 = edited?.startTime2 ?? entry.startTime2 ?? '';
                        const e2 = edited?.endTime2 ?? entry.endTime2 ?? '';

                        const handleChange = (field: keyof EditedEntry, value: string) => {
                          const current = editedEntries.get(entry.id) || {
                            entryId: entry.id, startTime1: entry.startTime1, endTime1: entry.endTime1,
                            startTime2: entry.startTime2, endTime2: entry.endTime2,
                          };
                          setEditedEntries(new Map(editedEntries.set(entry.id, { ...current, [field]: value })));
                        };

                        return (
                          <tr key={entry.id} className={`hover:bg-gray-50 ${entry.is_locked ? 'bg-yellow-50' : ''}`}>
                            <td className="py-2 px-3 font-medium text-gray-900">
                              {formatDate(entry.date)}
                              {entry.is_locked && <LockClosedIcon className="inline h-3 w-3 ml-1 text-yellow-600" />}
                            </td>
                            <td className="py-2 px-3 text-gray-600">
                              {isEditing ? (
                                <div className="flex gap-1 items-center">
                                  <input type="time" step={isV3Schedule ? 300 : 60} value={s1} onChange={(ev) => handleChange('startTime1', ev.target.value)} className="w-20 px-1 py-0.5 text-xs border rounded" />
                                  <span>-</span>
                                  <input type="time" step={isV3Schedule ? 300 : 60} value={e1} onChange={(ev) => handleChange('endTime1', ev.target.value)} className="w-20 px-1 py-0.5 text-xs border rounded" />
                                </div>
                              ) : s1 && e1 ? (
                                <span className="flex items-center"><ClockIcon className="h-4 w-4 mr-1 text-gray-400" />{s1} - {e1}</span>
                              ) : '-'}
                            </td>
                            <td className="py-2 px-3 text-gray-600">
                              {isEditing ? (
                                <div className="flex gap-1 items-center">
                                  <input type="time" step={isV3Schedule ? 300 : 60} value={s2} onChange={(ev) => handleChange('startTime2', ev.target.value)} className="w-20 px-1 py-0.5 text-xs border rounded" />
                                  <span>-</span>
                                  <input type="time" step={isV3Schedule ? 300 : 60} value={e2} onChange={(ev) => handleChange('endTime2', ev.target.value)} className="w-20 px-1 py-0.5 text-xs border rounded" />
                                </div>
                              ) : s2 && e2 ? (
                                <span className="flex items-center"><ClockIcon className="h-4 w-4 mr-1 text-gray-400" />{s2} - {e2}</span>
                              ) : '-'}
                            </td>
                            <td className="py-2 px-3 text-right font-medium text-gray-900">
                              {(calculateHours(s1, e1) + calculateHours(s2, e2)).toFixed(1)}h
                            </td>
                            <td className="py-2 px-2 text-center w-12">
                              <div className="flex items-center justify-center gap-1">
                                {entry.is_locked && <span title="Locked" className="text-yellow-600">🔒</span>}
                                <button
                                  onClick={() => handleDeleteEntry(entry.id, child.name)}
                                  disabled={deletingEntries || entry.is_locked}
                                  className="p-1.5 rounded-md bg-red-50 text-red-500 hover:bg-red-100 hover:text-red-700 transition-colors"
                                  title="Delete this day"
                                >
                                  <TrashIcon className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ─── By Day View ─── */}
      {viewMode === 'byDay' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {groupedByDay.map((day) => (
            <div key={day.date} className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-900">{formatDate(day.date)}</h3>
                <span className="text-xs px-2 py-1 bg-primary-50 text-primary-600 rounded-full font-medium">
                  {day.childCount} children
                </span>
              </div>
              <div className="text-sm text-gray-600 space-y-1">
                <p className="flex items-center gap-2">
                  <ClockIcon className="h-4 w-4 text-gray-400" />
                  {day.totalHours.toFixed(1)} total hours
                </p>
              </div>
              <div className="mt-3 pt-3 border-t border-gray-100">
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {day.entries.map(entry => (
                    <div key={entry.id} className="flex items-center justify-between text-xs">
                      <span className="text-gray-700 truncate">{resolveChildName(entry)}</span>
                      <span className="text-gray-500 shrink-0 ml-2">
                        {entry.startTime1 && entry.endTime1 ? `${entry.startTime1}-${entry.endTime1}` : '-'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ReviewPhase;
