import React, { useState, useMemo } from 'react';
import JSZip from 'jszip';
import {
  ArrowDownTrayIcon,
  DocumentTextIcon,
  UserIcon,
  PrinterIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  TableCellsIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../stores';
import { useAuth } from '../../../context/AuthContext';
import { generateSingleChildTimesheetPDF, generateSingleChildTimesheetBlob } from '../../scheduler/utils/timesheetPdf';
import type { ChildAttendanceData } from '../../scheduler/utils/timesheetPdf';
import { generateFSCDInvoicePDF, generateFSCDInvoiceBlob } from '../../scheduler/utils/fscdInvoicePdf';
import type { FSCDEntry } from '../../scheduler/utils/fscdInvoicePdf';

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
  source_claim_batch_id?: string;
}

interface ChildInfo {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string;
  age_group: string;
  family_id: string;
  fscd_file_number?: string;
}

interface ExportPhaseProps {
  activeBatchId: string | null;
  reviewApproved: boolean;
  onReturnToReview: () => void;
}

// ─── Helpers ────────────────────────────────────────────────────────────────────

function calculateHours(start?: string, end?: string): number {
  if (!start || !end) return 0;
  const [startH, startM] = start.split(':').map(Number);
  const [endH, endM] = end.split(':').map(Number);
  return ((endH * 60 + endM) - (startH * 60 + startM)) / 60;
}

function getChildName(childId: string): string {
  return childId.replace('imported-', '').replace(/^\d+-/, '').replace(/-/g, ' ')
    .split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}

const isRealChildId = (id: string | null) =>
  id ? /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) : false;

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const csvValue = (value: string | number | null | undefined): string => {
  let normalized = value == null ? '' : String(value);
  if (/^[\t\r ]*[=+\-@]/.test(normalized)) normalized = `'${normalized}`;
  return `"${normalized.replace(/"/g, '""')}"`;
};

const csvDocument = (headers: string[], rows: Array<Array<string | number | null | undefined>>) =>
  [headers, ...rows].map((row) => row.map(csvValue).join(',')).join('\r\n') + '\r\n';

const normalizedDate = (value: string) => value.slice(0, 10);

// ─── Component ──────────────────────────────────────────────────────────────────

type ExportMode = 'timesheets' | 'dailyCsv' | 'fscd';

const ExportPhase: React.FC<ExportPhaseProps> = ({
  activeBatchId,
  reviewApproved,
  onReturnToReview,
}) => {
  const { success, error: showError } = useNotificationStore();
  const { state: authState } = useAuth();
  const organization = authState.organization;

  const [exportMode, setExportMode] = useState<ExportMode>('timesheets');
  const [selectedChildId, setSelectedChildId] = useState<string | null>(null);
  const [childSearchTerm, setChildSearchTerm] = useState('');
  const [batchDownloading, setBatchDownloading] = useState(false);
  const [dailyCsvDownloading, setDailyCsvDownloading] = useState(false);
  const [batchSelectedChildIds, setBatchSelectedChildIds] = useState<Set<string>>(new Set());

  // FSCD state
  const [fscdFileNumber, setFscdFileNumber] = useState('');
  const [selectedImportBatchId, setSelectedImportBatchId] = useState<string | null>(null);
  const [absentDays, setAbsentDays] = useState<Set<string>>(new Set());

  // Bulk FSCD state
  const [bulkSelectedBatchIds, setBulkSelectedBatchIds] = useState<Set<string>>(new Set());
  const [bulkExporting, setBulkExporting] = useState(false);

  const { data: scheduleRows, loading } = useApiQuery<ScheduledEntry[]>('/resources/scheduled_attendance', {
    batch_id: activeBatchId || undefined,
    limit: 5000,
  });
  const { data: childRows, refetch: refetchChildren } = useApiQuery<ChildInfo[]>('/children', { limit: 1000 });
  const { data: importedRows } = useApiQuery<any[]>('/resources/imported_claims', { limit: 5000 });
  const { data: allScheduleRows } = useApiQuery<any[]>('/resources/scheduled_attendance', { limit: 5000 });
  const childrenData = useMemo(() => ({ children: childRows || [] }), [childRows]);
  const importBatchesData = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const row of importedRows || []) {
      const current = grouped.get(row.import_batch_id) || {
        batchId: row.import_batch_id,
        claimMonth: row.claim_month,
        claimYear: row.claim_year,
        totalClaims: 0,
        importedAt: row.imported_at,
      };
      current.totalClaims += 1;
      grouped.set(row.import_batch_id, current);
    }
    return { getImportedClaimBatches: [...grouped.values()] };
  }, [importedRows]);

  const allScheduledBatches = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const entry of allScheduleRows || []) {
      const current = grouped.get(entry.batch_id) || {
        batch_id: entry.batch_id, entry_count: 0, earliest_date: entry.date,
        latest_date: entry.date, created_at: entry.created_at,
      };
      current.entry_count += 1;
      if (entry.date < current.earliest_date) current.earliest_date = entry.date;
      if (entry.date > current.latest_date) current.latest_date = entry.date;
      grouped.set(entry.batch_id, current);
    }
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const key = sessionStorage.key(index);
      if (!key?.startsWith('caresync:schedule-batch:')) continue;
      const stored = JSON.parse(sessionStorage.getItem(key) || '{}');
      const dates = (stored.entries || []).map((entry: any) => entry.date).sort();
      if (!dates.length) continue;
      const batchId = key.replace('caresync:schedule-batch:', '');
      grouped.set(batchId, { batch_id: batchId, entry_count: dates.length, earliest_date: dates[0], latest_date: dates[dates.length - 1], created_at: stored.generated_at });
    }
    return [...grouped.values()].sort((a, b) => a.earliest_date.localeCompare(b.earliest_date));
  }, [allScheduleRows, activeBatchId]);

  const updateChildFscdNumberMutation = async ({ variables }: { variables: { id: string; fscdFileNumber: string } }) => {
    await api.resources.update('children', variables.id, { fscd_file_number: variables.fscdFileNumber });
    await refetchChildren();
  };

  // Auto-select import batch
  React.useEffect(() => {
    if (importBatchesData?.getImportedClaimBatches?.length && !selectedImportBatchId) {
      const sorted = [...importBatchesData.getImportedClaimBatches].sort((a, b) => new Date(b.importedAt).getTime() - new Date(a.importedAt).getTime());
      setSelectedImportBatchId(sorted[0]?.batchId || null);
    }
  }, [importBatchesData, selectedImportBatchId]);

  // Sync FSCD file number and reset absent days when child changes
  React.useEffect(() => {
    if (selectedChildId && isRealChildId(selectedChildId) && childrenData?.children) {
      const child = childrenData.children.find(c => c.id === selectedChildId);
      setFscdFileNumber(child?.fscd_file_number || '');
    } else {
      setFscdFileNumber('');
    }
    setAbsentDays(new Set());
  }, [selectedChildId, childrenData]);

  const transientSchedule = useMemo(() => activeBatchId
    ? JSON.parse(sessionStorage.getItem(`caresync:schedule-batch:${activeBatchId}`) || 'null')
    : null, [activeBatchId]);
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
    }))
    : (scheduleRows || []), [transientSchedule, scheduleRows]);

  const loadBatchEntries = async (batchId: string): Promise<ScheduledEntry[]> => {
    const transient = JSON.parse(sessionStorage.getItem(`caresync:schedule-batch:${batchId}`) || 'null');
    if (transient) {
      return (transient.entries || []).map((entry: any, index: number) => ({
        id: entry.id || entry.client_entry_id || `transient-${index}`,
        child_id: entry.child_id,
        child_name: entry.child_name,
        date: entry.date,
        startTime1: entry.start_time,
        endTime1: entry.end_time,
        startTime2: entry.start_time_2,
        endTime2: entry.end_time_2,
      }));
    }
    const complete: ScheduledEntry[] = [];
    const pageSize = 5000;
    for (let offset = 0; ; offset += pageSize) {
      const page = await api.resources.list<ScheduledEntry>('scheduled_attendance', {
        batch_id: batchId,
        limit: pageSize,
        offset,
      });
      complete.push(...page);
      if (page.length < pageSize) return complete;
    }
  };

  // Group by child
  const groupedByChild = useMemo(() => {
    const map = new Map<string, { id: string; name: string; entries: ScheduledEntry[]; totalHours: number }>();
    entries.forEach(entry => {
      if (!map.has(entry.child_id)) {
        const dbChild = childrenData?.children.find(c => c.id === entry.child_id);
        const name = entry.child_name || transientSchedule?.child_names?.[entry.child_id]
          || (dbChild ? `${dbChild.first_name} ${dbChild.last_name}` : getChildName(entry.child_id));
        map.set(entry.child_id, { id: entry.child_id, name, entries: [], totalHours: 0 });
      }
      const child = map.get(entry.child_id)!;
      child.entries.push(entry);
      child.totalHours += calculateHours(entry.startTime1, entry.endTime1) + calculateHours(entry.startTime2, entry.endTime2);
    });
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [entries, childrenData, transientSchedule]);

  // Filter children
  const filteredChildren = groupedByChild.filter(c =>
    c.name.toLowerCase().includes(childSearchTerm.toLowerCase())
  );

  // ─── Empty state ────────────────────────────────────────────────────────────

  if (!activeBatchId) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <div className="p-4 bg-yellow-100 rounded-2xl mb-6">
          <ArrowDownTrayIcon className="h-12 w-12 text-yellow-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">No Schedule to Export</h2>
        <p className="text-gray-500 text-center max-w-md">
          Generate a schedule first, or select one from the history panel.
        </p>
      </div>
    );
  }

  if (!reviewApproved) {
    return (
      <div className="flex flex-col items-center justify-center px-6 py-24 text-center">
        <div className="mb-6 rounded-2xl bg-amber-100 p-4">
          <ExclamationTriangleIcon className="h-12 w-12 text-amber-700" />
        </div>
        <h2 className="mb-2 text-xl font-bold text-gray-900">Review required before export</h2>
        <p className="mb-6 max-w-lg text-gray-600">
          Return to Review, resolve or acknowledge the scheduler warnings, and finish any pending edits before
          producing projected documents.
        </p>
        <button type="button" onClick={onReturnToReview} className="btn btn-primary">
          Return to Review
        </button>
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

  // ─── Export handlers ────────────────────────────────────────────────────────

  const handleSingleTimesheetDownload = (childId: string) => {
    const child = groupedByChild.find(c => c.id === childId);
    if (!child) return;

    const childData: ChildAttendanceData = {
      name: child.name,
      dateOfBirth: '',
      entries: child.entries.map(e => ({
        date: e.date,
        startTime1: e.startTime1,
        endTime1: e.endTime1,
        startTime2: e.startTime2,
        endTime2: e.endTime2,
      })),
    };

    generateSingleChildTimesheetPDF(childData, child.name);
    success('Downloaded', `Timesheet for ${child.name} downloaded`);
  };

  const handleBatchDownload = async () => {
    if (batchSelectedChildIds.size === 0) return;
    setBatchDownloading(true);

    try {
      const zip = new JSZip();
      for (const childId of batchSelectedChildIds) {
        const child = groupedByChild.find(c => c.id === childId);
        if (!child) continue;

        const childData: ChildAttendanceData = {
          name: child.name,
          dateOfBirth: '',
          entries: child.entries.map(e => ({
            date: e.date,
            startTime1: e.startTime1,
            endTime1: e.endTime1,
            startTime2: e.startTime2,
            endTime2: e.endTime2,
          })),
        };

        const blob = await generateSingleChildTimesheetBlob(childData, child.name);
        zip.file(`DRAFT_PROJECTED_${child.name.replace(/\s+/g, '_')}_timesheet.pdf`, blob);
      }

      const zipBlob = await zip.generateAsync({ type: 'blob' });
      const url = URL.createObjectURL(zipBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'DRAFT_PROJECTED_timesheets_batch.zip';
      a.click();
      URL.revokeObjectURL(url);
      success('Downloaded', `${batchSelectedChildIds.size} timesheets downloaded as ZIP`);
    } catch {
      showError('Error', 'Failed to generate batch download');
    }
    setBatchDownloading(false);
  };

  const handleDailyCsvDownload = async () => {
    if (!activeBatchId) return;
    setDailyCsvDownloading(true);
    try {
      const batchEntries = await loadBatchEntries(activeBatchId);
      if (!batchEntries.length) {
        showError('Nothing to Export', 'This schedule has no attendance entries.');
        return;
      }
      const childNames = new Map(groupedByChild.map((child) => [child.id, child.name]));
      const databaseChildren = new Map(childrenData.children.map((child) => [child.id, child]));
      const byDate = new Map<string, ScheduledEntry[]>();
      for (const entry of batchEntries) {
        const date = normalizedDate(entry.date);
        byDate.set(date, [...(byDate.get(date) || []), entry]);
      }

      const zip = new JSZip();
      const folder = zip.folder('daily_attendance');
      if (!folder) throw new Error('Could not create the daily attendance folder');
      const manifestRows: Array<Array<string | number>> = [];
      const dates = [...byDate.keys()].sort();
      for (const date of dates) {
        const dayEntries = [...(byDate.get(date) || [])].sort((left, right) => {
          const leftName = left.child_name || childNames.get(left.child_id) || getChildName(left.child_id);
          const rightName = right.child_name || childNames.get(right.child_id) || getChildName(right.child_id);
          return leftName.localeCompare(rightName);
        });
        const uniqueChildren = new Set(dayEntries.map((entry) => entry.child_id));
        if (uniqueChildren.size !== dayEntries.length) {
          throw new Error(`${date} contains duplicate attendance rows for the same child. Return to Review before exporting.`);
        }
        const rows = dayEntries.map((entry) => {
          const child = databaseChildren.get(entry.child_id);
          const childName = entry.child_name
            || childNames.get(entry.child_id)
            || (child ? `${child.first_name} ${child.last_name}` : getChildName(entry.child_id));
          const totalHours = calculateHours(entry.startTime1, entry.endTime1)
            + calculateHours(entry.startTime2, entry.endTime2);
          return [
            date,
            entry.child_id,
            childName,
            child?.family_id || '',
            child ? 'DATABASE_CHILD' : 'IMPORT_ONLY_CHILD',
            child?.age_group || '',
            entry.startTime1 || '',
            entry.endTime1 || '',
            entry.startTime2 || '',
            entry.endTime2 || '',
            totalHours.toFixed(2),
            'PROJECTED_SCHEDULE',
            activeBatchId,
            entry.source_claim_batch_id || '',
            entry.id,
          ];
        });
        const totalHours = rows.reduce((sum, row) => sum + Number(row[10]), 0);
        const filename = `${date}.csv`;
        folder.file(filename, csvDocument([
          'attendance_date',
          'child_id',
          'child_name',
          'family_id',
          'child_record_type',
          'age_group',
          'session_1_start',
          'session_1_end',
          'session_2_start',
          'session_2_end',
          'total_hours',
          'record_status',
          'schedule_batch_id',
          'source_claim_batch_id',
          'schedule_entry_id',
        ], rows));
        manifestRows.push([date, `daily_attendance/${filename}`, uniqueChildren.size, totalHours.toFixed(2)]);
      }
      zip.file('manifest.csv', csvDocument(
        ['attendance_date', 'filename', 'child_count', 'total_hours'],
        manifestRows,
      ));
      zip.file(
        'README.txt',
        [
          'CareSync Daily Attendance Export',
          '',
          'Each file in daily_attendance/ contains every child scheduled for that date.',
          'There is one row per child per day, with up to two attendance sessions.',
          'record_status is PROJECTED_SCHEDULE because these rows come from the scheduler.',
          'IMPORT_ONLY_CHILD means the name came from the claim import and has no child record in this database.',
          '',
          `Schedule batch: ${activeBatchId}`,
          `Generated: ${new Date().toISOString()}`,
        ].join('\r\n'),
      );

      const firstMonth = dates[0].slice(0, 7);
      const multipleMonths = dates.some((date) => !date.startsWith(firstMonth));
      const zipBlob = await zip.generateAsync({
        type: 'blob',
        compression: 'DEFLATE',
        compressionOptions: { level: 6 },
      });
      const url = URL.createObjectURL(zipBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `CareSync_daily_attendance_${multipleMonths ? 'multi_month' : firstMonth}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      success('Daily CSV ZIP Downloaded', `${dates.length} daily CSV files exported for ${batchEntries.length} attendance entries.`);
    } catch (caught) {
      showError('CSV Export Failed', caught instanceof Error ? caught.message : 'Failed to create the daily CSV ZIP.');
    } finally {
      setDailyCsvDownloading(false);
    }
  };

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Export Documents</h2>
          <p className="text-sm text-gray-500">{groupedByChild.length} children available for export</p>
        </div>
        <div className="flex p-1 bg-gray-100 rounded-lg">
          <button
            onClick={() => setExportMode('timesheets')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${exportMode === 'timesheets' ? 'bg-white text-primary-600 shadow-sm' : 'text-gray-600'}`}
          >
            <PrinterIcon className="h-4 w-4 inline mr-1" />
            Timesheets
          </button>
          <button
            onClick={() => setExportMode('dailyCsv')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${exportMode === 'dailyCsv' ? 'bg-white text-primary-600 shadow-sm' : 'text-gray-600'}`}
          >
            <TableCellsIcon className="h-4 w-4 inline mr-1" />
            Daily CSV ZIP
          </button>
          <button
            onClick={() => setExportMode('fscd')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${exportMode === 'fscd' ? 'bg-white text-primary-600 shadow-sm' : 'text-gray-600'}`}
          >
            <DocumentTextIcon className="h-4 w-4 inline mr-1" />
            FSCD Drafts
          </button>
        </div>
      </div>

      <div className="mb-6 rounded-lg border-2 border-red-300 bg-red-50 p-4">
        <p className="font-semibold text-red-900">Projected draft exports only</p>
        <p className="mt-1 text-sm text-red-800">
          Scheduler rows are planned attendance, not proof that care or funded services occurred. Every PDF is
          watermarked and must be reconciled with actual attendance before it can support an official record.
        </p>
      </div>

      {/* ─── Timesheets Mode ─── */}
      {exportMode === 'timesheets' && (
        <div className="space-y-4">
          {/* Batch download bar */}
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200 flex items-center justify-between">
            <div>
              <p className="font-medium text-blue-900">Batch Download</p>
              <p className="text-sm text-blue-600">{batchSelectedChildIds.size} of {groupedByChild.length} children selected</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setBatchSelectedChildIds(new Set(groupedByChild.map(c => c.id)))} className="btn btn-secondary text-xs">Select All</button>
              <button onClick={() => setBatchSelectedChildIds(new Set())} className="btn btn-secondary text-xs">Clear</button>
              <button onClick={handleBatchDownload} disabled={batchSelectedChildIds.size === 0 || batchDownloading} className="btn btn-primary text-sm flex items-center gap-1">
                {batchDownloading ? <ArrowPathIcon className="h-4 w-4 animate-spin" /> : <ArrowDownTrayIcon className="h-4 w-4" />}
                Download ZIP
              </button>
            </div>
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Search children..."
            value={childSearchTerm}
            onChange={(e) => setChildSearchTerm(e.target.value)}
            className="input w-full"
          />

          {/* Child list */}
          <div className="grid gap-2">
            {filteredChildren.map((child) => (
              <div key={child.id} className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200 hover:shadow-sm">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={batchSelectedChildIds.has(child.id)}
                    onChange={(e) => {
                      const next = new Set(batchSelectedChildIds);
                      if (e.target.checked) next.add(child.id); else next.delete(child.id);
                      setBatchSelectedChildIds(next);
                    }}
                    className="w-4 h-4 rounded border-gray-300 text-primary-600"
                  />
                  <UserIcon className="h-5 w-5 text-gray-400" />
                  <div>
                    <p className="font-medium text-gray-900">{child.name}</p>
                    <p className="text-xs text-gray-500">{child.entries.length} days • {child.totalHours.toFixed(1)}h</p>
                  </div>
                </div>
                <button
                  onClick={() => handleSingleTimesheetDownload(child.id)}
                  className="btn btn-secondary text-xs flex items-center gap-1"
                >
                  <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                  PDF
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Daily CSV Mode ─── */}
      {exportMode === 'dailyCsv' && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-emerald-900">
                <TableCellsIcon className="h-6 w-6" />
                Combined Daily Attendance CSVs
              </h3>
              <p className="mt-2 max-w-2xl text-sm text-emerald-800">
                Downloads one ZIP containing a separate CSV for every scheduled date. Each daily file includes
                all children attending that day, their database/import identity, both time sessions, and total hours.
              </p>
              <p className="mt-2 text-xs text-emerald-700">
                The ZIP also includes manifest.csv for automated imports and README.txt with field notes.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void handleDailyCsvDownload()}
              disabled={dailyCsvDownloading || entries.length === 0}
              className="btn btn-primary flex shrink-0 items-center gap-2 px-6 py-3 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {dailyCsvDownloading
                ? <ArrowPathIcon className="h-5 w-5 animate-spin" />
                : <ArrowDownTrayIcon className="h-5 w-5" />}
              {dailyCsvDownloading ? 'Building Daily ZIP...' : 'Download Daily CSV ZIP'}
            </button>
          </div>
        </div>
      )}

      {/* ─── FSCD Mode ─── */}
      {exportMode === 'fscd' && (
        <div className="space-y-4">
          <div className="p-4 bg-amber-50 rounded-lg border border-amber-200">
            <p className="text-sm text-amber-800">
              Select a child to generate a projected FSCD draft. Stored signatures are deliberately excluded because
              a planned schedule cannot establish that services were delivered.
            </p>
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Search children..."
            value={childSearchTerm}
            onChange={(e) => setChildSearchTerm(e.target.value)}
            className="input w-full"
          />

          {/* Child list */}
          <div className="grid gap-2">
            {filteredChildren.map((child) => (
              <button
                key={child.id}
                onClick={() => setSelectedChildId(child.id)}
                className={`w-full text-left p-3 rounded-lg border-2 transition-all flex items-center justify-between ${selectedChildId === child.id ? 'border-primary-500 bg-primary-50' : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
              >
                <div className="flex items-center gap-3">
                  <UserIcon className="h-5 w-5 text-gray-400" />
                  <div>
                    <p className="font-medium text-gray-900">{child.name}</p>
                    <p className="text-xs text-gray-500">{child.entries.length} days • {child.totalHours.toFixed(1)}h</p>
                  </div>
                </div>
                {selectedChildId === child.id && (
                  <span className="text-xs px-2 py-1 bg-primary-100 text-primary-700 rounded-full">Selected</span>
                )}
              </button>
            ))}
          </div>

          {/* FSCD details for selected child */}
          {selectedChildId && (
            <div className="mt-6 p-6 bg-white rounded-xl border border-gray-200 space-y-4">
              <h3 className="font-semibold text-gray-900">
                FSCD Invoice: {groupedByChild.find(c => c.id === selectedChildId)?.name}
              </h3>

              {/* FSCD File Number */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700">FSCD File Number</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={fscdFileNumber}
                    onChange={(e) => setFscdFileNumber(e.target.value)}
                    onBlur={() => {
                      if (selectedChildId && isRealChildId(selectedChildId) && fscdFileNumber) {
                        updateChildFscdNumberMutation({ variables: { id: selectedChildId, fscdFileNumber } });
                      }
                    }}
                    placeholder="Enter FSCD file number"
                    className="input flex-1"
                  />
                  {isRealChildId(selectedChildId) && (
                    <button
                      onClick={() => {
                        if (selectedChildId) {
                          updateChildFscdNumberMutation({ variables: { id: selectedChildId, fscdFileNumber } });
                          success('Saved', 'FSCD file number saved to child record');
                        }
                      }}
                      className="btn btn-secondary text-sm"
                    >
                      Save
                    </button>
                  )}
                </div>
                {isRealChildId(selectedChildId) ? (
                  <p className="text-xs text-green-600">✓ Auto-saves when you click away — persists across all batches</p>
                ) : (
                  <p className="text-xs text-gray-400">Imported child — number will be used for this export only</p>
                )}
              </div>

              {/* Attendance Days — mark absences */}
              {(() => {
                const child = groupedByChild.find(c => c.id === selectedChildId);
                if (!child) return null;
                const sortedEntries = [...child.entries].sort((a, b) => a.date.localeCompare(b.date));
                const presentCount = sortedEntries.filter(e => !absentDays.has(e.date)).length;
                const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
                return (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium text-gray-700">Attendance Days</label>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setAbsentDays(new Set())}
                          className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200"
                        >
                          All Present
                        </button>
                        <button
                          type="button"
                          onClick={() => setAbsentDays(new Set(sortedEntries.map(e => e.date)))}
                          className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                        >
                          All Absent
                        </button>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500">
                      Uncheck days the child was absent — they will be excluded from the invoice.
                      <span className="ml-1 font-medium text-gray-700">{presentCount}/{sortedEntries.length} days included</span>
                    </p>
                    <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
                      {sortedEntries.map((entry) => {
                        const d = new Date(entry.date.includes('T') ? entry.date : `${entry.date}T12:00:00`);
                        const dayName = DAY_NAMES[d.getDay()];
                        const isAbsent = absentDays.has(entry.date);
                        const hrs = calculateHours(entry.startTime1, entry.endTime1) + calculateHours(entry.startTime2, entry.endTime2);
                        return (
                          <label
                            key={entry.date}
                            className={`flex items-center justify-between px-3 py-2 cursor-pointer transition-colors ${isAbsent ? 'bg-red-50 text-gray-400' : 'hover:bg-gray-50'
                              }`}
                          >
                            <div className="flex items-center gap-3">
                              <input
                                type="checkbox"
                                checked={!isAbsent}
                                onChange={() => {
                                  const next = new Set(absentDays);
                                  if (isAbsent) next.delete(entry.date); else next.add(entry.date);
                                  setAbsentDays(next);
                                }}
                                className="w-4 h-4 rounded border-gray-300 text-primary-600"
                              />
                              <span className={`text-sm font-medium ${isAbsent ? 'line-through text-gray-400' : 'text-gray-900'}`}>
                                {dayName}, {d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 text-xs">
                              <span className={isAbsent ? 'text-gray-400' : 'text-gray-500'}>
                                {entry.startTime1 || ''} - {entry.endTime1 || ''}
                                {entry.startTime2 && entry.endTime2 && (
                                  <>{' • '}{entry.startTime2} - {entry.endTime2}</>
                                )}
                              </span>
                              <span className={`font-medium ${isAbsent ? 'text-red-400' : 'text-gray-700'}`}>
                                {isAbsent ? 'ABSENT' : `${hrs.toFixed(1)}h`}
                              </span>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}

              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                Parent and director signatures cannot be attached in this projected-schedule export. Record actual
                attendance first, then use the verified invoicing workflow for an official claim.
              </div>

              {/* Generate FSCD button */}
              <button
                onClick={() => {
                  const child = groupedByChild.find(c => c.id === selectedChildId);
                  if (!child) return;
                  const childEntries = child.entries.filter(e => !absentDays.has(e.date));

                  // Get date range for the invoice month
                  const dates = childEntries.map(e => new Date(e.date.includes('T') ? e.date : `${e.date}T12:00:00`));
                  const targetMonth = dates.length > 0 ? dates[0].getMonth() : new Date().getMonth();
                  const targetYear = dates.length > 0 ? dates[0].getFullYear() : new Date().getFullYear();

                  const fscdEntries: FSCDEntry[] = childEntries.flatMap(e => {
                    const rows: FSCDEntry[] = [];
                    // Session 1 row
                    if (e.startTime1 && e.endTime1) {
                      rows.push({
                        date: e.date,
                        startTime: e.startTime1,
                        endTime: e.endTime1,
                        hours: calculateHours(e.startTime1, e.endTime1),
                      });
                    }
                    // Session 2 row (same date, separate line)
                    if (e.startTime2 && e.endTime2) {
                      rows.push({
                        date: e.date,
                        startTime: e.startTime2,
                        endTime: e.endTime2,
                        hours: calculateHours(e.startTime2, e.endTime2),
                      });
                    }
                    // Fallback: if somehow no sessions, still show the entry
                    if (rows.length === 0) {
                      rows.push({
                        date: e.date,
                        startTime: e.startTime1 || '',
                        endTime: e.endTime1 || '',
                        hours: 0,
                      });
                    }
                    return rows;
                  });

                  // Get business partner number from license
                  const licenseNumber = organization?.license_number || '';
                  const businessPartnerNumber = licenseNumber.replace(/^ELCCA\s*/i, '').trim();

                  generateFSCDInvoicePDF({
                    documentStatus: 'projected-draft',
                    // Provider Info
                    providerName: organization?.name || "Discoverers' Daycare",
                    providerPhone: organization?.phone || '',
                    providerEmail: organization?.email || '',
                    providerAddress: organization?.street_address || '',
                    providerCity: organization?.city || '',
                    providerPostalCode: organization?.postal_code || '',

                    // Invoice Info
                    invoiceMonth: MONTHS[targetMonth],
                    invoiceYear: targetYear,
                    invoiceNumber: `FSCD-${String(targetMonth + 1).padStart(2, '0')}-${targetYear}`,
                    fscdNumber: fscdFileNumber || '',
                    businessPartnerNumber,

                    // Child Info
                    childName: child.name,

                    // Entries
                    entries: fscdEntries,

                    // Rate
                    hourlyRate: 18.0,

                    // Service type
                    serviceType: '1:1 Aide',
                  });

                  success('Draft Generated', `Projected FSCD draft for ${child.name} downloaded`);
                }}
                className="btn btn-primary w-full flex items-center justify-center gap-2 py-3"
              >
                <DocumentTextIcon className="h-5 w-5" />
                Generate Projected FSCD Draft
              </button>

              {/* ─── Bulk FSCD Export ─── */}
              <div className="mt-6 pt-6 border-t border-gray-200 space-y-3">
                <h4 className="font-semibold text-gray-900 flex items-center gap-2">
                  <ArrowDownTrayIcon className="h-5 w-5 text-purple-600" />
                  Bulk Export — Multiple Months
                </h4>

                {(() => {
                  const allBatches = allScheduledBatches;
                  if (!allBatches.length) return <p className="text-xs text-gray-400">No batches found.</p>;

                  return (
                    <>
                      <div className="max-h-40 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
                        {allBatches.map((batch) => {
                          const earliest = new Date(batch.earliest_date.includes('T') ? batch.earliest_date : `${batch.earliest_date}T12:00:00`);
                          const label = earliest.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
                          const isSelected = bulkSelectedBatchIds.has(batch.batch_id);
                          return (
                            <label
                              key={batch.batch_id}
                              className={`flex items-center justify-between px-3 py-2 cursor-pointer transition-colors ${isSelected ? 'bg-purple-50' : 'hover:bg-gray-50'
                                }`}
                            >
                              <div className="flex items-center gap-3">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => {
                                    const next = new Set(bulkSelectedBatchIds);
                                    if (isSelected) next.delete(batch.batch_id); else next.add(batch.batch_id);
                                    setBulkSelectedBatchIds(next);
                                  }}
                                  className="w-4 h-4 rounded border-gray-300 text-purple-600"
                                />
                                <span className="text-sm font-medium text-gray-900">{label}</span>
                              </div>
                              <span className="text-xs text-gray-500">{batch.entry_count} entries</span>
                            </label>
                          );
                        })}
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setBulkSelectedBatchIds(new Set(allBatches.map(b => b.batch_id)))}
                          className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded hover:bg-purple-200"
                        >
                          Select All
                        </button>
                        <button
                          onClick={() => setBulkSelectedBatchIds(new Set())}
                          className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
                        >
                          Clear
                        </button>
                        <span className="text-xs text-gray-500 ml-auto">{bulkSelectedBatchIds.size} selected</span>
                      </div>

                      <button
                        onClick={async () => {
                          if (bulkSelectedBatchIds.size === 0 || !selectedChildId) return;
                          setBulkExporting(true);

                          try {
                            const zip = new JSZip();
                            const child = groupedByChild.find(c => c.id === selectedChildId);
                            const childDisplayName = child?.name || 'Unknown';

                            const licenseNumber = organization?.license_number || '';
                            const businessPartnerNumber = licenseNumber.replace(/^ELCCA\s*/i, '').trim();

                            for (const batchId of Array.from(bulkSelectedBatchIds)) {
                              // Fetch entries for this batch
                              const batchEntries = await loadBatchEntries(batchId);
                              // Match by ID or by name (child may have different IDs across batches)
                              const childEntries = batchEntries.filter(e => {
                                if (e.child_id === selectedChildId) return true;
                                // Check DB child name
                                const dbChild = childrenData?.children?.find(c => c.id === e.child_id);
                                if (dbChild) {
                                  const dbName = `${dbChild.first_name} ${dbChild.last_name}`.toLowerCase();
                                  if (dbName === childDisplayName.toLowerCase()) return true;
                                }
                                // Fallback: match by parsed name from child_id
                                const entryName = (e.child_name || getChildName(e.child_id)).toLowerCase();
                                return entryName === childDisplayName.toLowerCase();
                              });
                              console.log(`[Bulk FSCD] Batch ${batchId}: ${batchEntries.length} total entries, ${childEntries.length} matched for "${childDisplayName}"`);
                              if (childEntries.length === 0) continue;

                              const dates = childEntries.map(e => new Date(e.date.includes('T') ? e.date : `${e.date}T12:00:00`));
                              const targetMonth = dates[0].getMonth();
                              const targetYear = dates[0].getFullYear();

                              const fscdEntries: FSCDEntry[] = childEntries.flatMap(e => {
                                const rows: FSCDEntry[] = [];
                                if (e.startTime1 && e.endTime1) {
                                  rows.push({ date: e.date, startTime: e.startTime1, endTime: e.endTime1, hours: calculateHours(e.startTime1, e.endTime1) });
                                }
                                if (e.startTime2 && e.endTime2) {
                                  rows.push({ date: e.date, startTime: e.startTime2, endTime: e.endTime2, hours: calculateHours(e.startTime2, e.endTime2) });
                                }
                                if (rows.length === 0) {
                                  rows.push({ date: e.date, startTime: e.startTime1 || '', endTime: e.endTime1 || '', hours: 0 });
                                }
                                return rows;
                              });

                              const blob = generateFSCDInvoiceBlob({
                                documentStatus: 'projected-draft',
                                providerName: organization?.name || "Discoverers' Daycare",
                                providerPhone: organization?.phone || '',
                                providerEmail: organization?.email || '',
                                providerAddress: organization?.street_address || '',
                                providerCity: organization?.city || '',
                                providerPostalCode: organization?.postal_code || '',
                                invoiceMonth: MONTHS[targetMonth],
                                invoiceYear: targetYear,
                                invoiceNumber: `FSCD-${String(targetMonth + 1).padStart(2, '0')}-${targetYear}`,
                                fscdNumber: fscdFileNumber || '',
                                businessPartnerNumber,
                                childName: childDisplayName,
                                entries: fscdEntries,
                                hourlyRate: 18.0,
                                serviceType: '1:1 Aide',
                              });

                              const safeName = childDisplayName.replace(/[^a-zA-Z0-9]/g, '_');
                              zip.file(`DRAFT_PROJECTED_FSCD_${safeName}_${MONTHS[targetMonth]}_${targetYear}.pdf`, blob);
                            }

                            const zipBlob = await zip.generateAsync({ type: 'blob' });
                            const link = document.createElement('a');
                            link.href = URL.createObjectURL(zipBlob);
                            const safeName = childDisplayName.replace(/[^a-zA-Z0-9]/g, '_');
                            link.download = `DRAFT_PROJECTED_FSCD_${safeName}.zip`;
                            link.click();
                            URL.revokeObjectURL(link.href);

                            success('Drafts Downloaded', `${bulkSelectedBatchIds.size} projected FSCD drafts exported as ZIP`);
                          } catch (err: any) {
                            showError('Export Failed', err.message || 'Failed to generate bulk FSCD invoices');
                          }
                          setBulkExporting(false);
                        }}
                        disabled={bulkSelectedBatchIds.size === 0 || bulkExporting}
                        className="btn btn-primary w-full flex items-center justify-center gap-2 py-3 bg-purple-600 hover:bg-purple-700"
                      >
                        {bulkExporting ? (
                          <><ArrowPathIcon className="h-5 w-5 animate-spin" /> Generating...</>
                        ) : (
                          <><ArrowDownTrayIcon className="h-5 w-5" /> Download {bulkSelectedBatchIds.size} Drafts as ZIP</>
                        )}
                      </button>
                    </>
                  );
                })()}
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  );
};

export default ExportPhase;
