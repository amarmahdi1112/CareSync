import React from 'react';
import {
  CalendarDaysIcon,
  TrashIcon,
  PlusIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../stores';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

interface ScheduledBatch {
  batch_id: string;
  entry_count: number;
  earliest_date: string;
  latest_date: string;
  created_at: string;
}

interface HistoryPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  activeBatchId: string | null;
  onSelectBatch: (batchId: string) => void;
  onNewSchedule: () => void;
}

const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function formatBatchDateRange(earliest: string, latest: string): string {
  if (!earliest || !latest) return 'Unknown';
  const start = new Date(earliest.includes('T') ? earliest : `${earliest}T12:00:00`);
  if (isNaN(start.getTime())) return 'Invalid';
  const month = MONTHS_SHORT[start.getMonth()];
  return `${month} ${start.getFullYear()}`;
}

function formatCreatedDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

const HistoryPanel: React.FC<HistoryPanelProps> = ({
  collapsed,
  onToggleCollapse,
  activeBatchId,
  onSelectBatch,
  onNewSchedule,
}) => {
  const { success, error } = useNotificationStore();

  const { data, refetch } = useApiQuery<any[]>('/resources/scheduled_attendance', {
    limit: 5000,
    sort: 'created_at',
    order: 'desc',
  });
  const batches = React.useMemo(() => {
    const grouped = new Map<string, ScheduledBatch>();
    for (const entry of data || []) {
      const current = grouped.get(entry.batch_id) || {
        batch_id: entry.batch_id,
        entry_count: 0,
        earliest_date: entry.date,
        latest_date: entry.date,
        created_at: entry.created_at,
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
      const entries = stored.entries || [];
      if (!entries.length) continue;
      const batchId = key.replace('caresync:schedule-batch:', '');
      const dates = entries.map((entry: any) => entry.date).sort();
      grouped.set(batchId, {
        batch_id: batchId,
        entry_count: entries.length,
        earliest_date: dates[0],
        latest_date: dates[dates.length - 1],
        created_at: stored.generated_at || new Date().toISOString(),
      });
    }
    return [...grouped.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [data, activeBatchId]);

  const deleteBatch = async (batchId: string) => {
    try {
      const storageKey = `caresync:schedule-batch:${batchId}`;
      const stored = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      const hasDatabaseRows = Boolean(stored?.persisted)
        || (data || []).some((entry) => entry.batch_id === batchId);
      if (hasDatabaseRows) {
        await api.delete(`/schedules/${encodeURIComponent(batchId)}`, { confirm: true });
      }
      sessionStorage.removeItem(storageKey);
      await refetch();
      success('Deleted', 'Schedule batch deleted');
    } catch (caught) {
      error('Delete Failed', caught instanceof Error ? caught.message : 'Request failed');
    }
  };

  if (collapsed) {
    return (
      <div className="w-12 bg-gray-50 border-r border-gray-200 flex flex-col items-center py-4 shrink-0">
        <button
          onClick={onToggleCollapse}
          className="p-2 hover:bg-gray-200 rounded-lg transition-colors mb-4"
          title="Expand history"
        >
          <ChevronRightIcon className="h-4 w-4 text-gray-500" />
        </button>
        <div className="flex flex-col items-center gap-2 mt-2">
          {batches.slice(0, 5).map((batch) => (
            <button
              key={batch.batch_id}
              onClick={() => onSelectBatch(batch.batch_id)}
              className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold transition-colors ${
                activeBatchId === batch.batch_id
                  ? 'bg-primary-500 text-white'
                  : 'bg-white border border-gray-200 text-gray-500 hover:border-primary-300'
              }`}
              title={formatBatchDateRange(batch.earliest_date, batch.latest_date)}
            >
              {batch.entry_count}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col shrink-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Schedule History</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={onNewSchedule}
            className="p-1.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
            title="New schedule"
          >
            <PlusIcon className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
            title="Collapse"
          >
            <ChevronLeftIcon className="h-3.5 w-3.5 text-gray-500" />
          </button>
        </div>
      </div>

      {/* Batch List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {batches.length === 0 ? (
          <div className="text-center py-8">
            <CalendarDaysIcon className="h-8 w-8 text-gray-300 mx-auto mb-2" />
            <p className="text-xs text-gray-400">No schedules yet</p>
          </div>
        ) : (
          batches.map((batch) => (
            <button
              key={batch.batch_id}
              onClick={() => onSelectBatch(batch.batch_id)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                activeBatchId === batch.batch_id
                  ? 'border-primary-500 bg-primary-50 shadow-sm'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-semibold ${
                  activeBatchId === batch.batch_id ? 'text-primary-700' : 'text-gray-800'
                }`}>
                  {formatBatchDateRange(batch.earliest_date, batch.latest_date)}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm('Delete this schedule batch?')) {
                      void deleteBatch(batch.batch_id);
                    }
                  }}
                  className="p-1 text-gray-300 hover:text-red-500 rounded transition-colors"
                >
                  <TrashIcon className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-400">
                <span className="flex items-center gap-1">
                  <CalendarDaysIcon className="h-3 w-3" />
                  {batch.entry_count} entries
                </span>
                <span className="flex items-center gap-1">
                  <ClockIcon className="h-3 w-3" />
                  {formatCreatedDate(batch.created_at)}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default HistoryPanel;
