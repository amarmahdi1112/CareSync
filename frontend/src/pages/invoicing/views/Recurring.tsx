// ============================================
// Recurring Invoices View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  ArrowPathIcon,
  PlusIcon,
  CalendarDaysIcon,
  PlayIcon,
  PauseIcon,
  PencilIcon,
  TrashIcon,
  ClockIcon,
  UserGroupIcon
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { RecurringSchedule, RecurringFrequency } from '../types';

// Components
import { StatCard, StatsGrid } from '../components/common/StatCard';
import { EmptyState, CenteredLoading } from '../components/common/EmptyState';
import { RecurringStatusBadge } from '../components/common/StatusBadge';
import { Modal, ModalButton } from '../components/common/Modal';
import { SimpleLineItemList } from '../components/forms/LineItemEditor';

// Utils & Constants
import { formatCurrencyIntl, formatDate, getOrdinalSuffix } from '../utils/formatters';
import { calculateScheduleAmount, calculateMonthlyRevenue } from '../utils/calculations';
import { FREQUENCY_LABELS, DAY_OF_WEEK_LABELS, DEFAULT_RECURRING_FORM } from '../constants';

const Recurring: React.FC = () => {
  const { addNotification } = useNotifications();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<RecurringSchedule | null>(null);
  const [formData, setFormData] = useState(DEFAULT_RECURRING_FORM);
  const [creating, setCreating] = useState(false);
  const [updating, setUpdating] = useState(false);

  const { data: scheduleRows = [], loading, refetch } = useApiQuery<Array<RecurringSchedule & { line_items?: RecurringSchedule['line_items'] | string }>>('/resources/recurring_invoices', { limit: 1000, sort: 'created_at', order: 'desc' });
  const schedules: RecurringSchedule[] = scheduleRows.map((schedule) => ({
    ...schedule,
    line_items: typeof schedule.line_items === 'string'
      ? (() => { try { return JSON.parse(schedule.line_items); } catch { return []; } })()
      : (schedule.line_items || []),
  }));

  const resetForm = () => {
    setFormData(DEFAULT_RECURRING_FORM);
    setEditingSchedule(null);
  };

  const handleOpenEdit = (schedule: RecurringSchedule) => {
    setEditingSchedule(schedule);
    setFormData({
      name: schedule.name,
      client_name: schedule.client_name || '',
      frequency: schedule.frequency,
      day_of_period: schedule.day_of_period || 1,
      start_date: schedule.start_date || '',
      end_date: schedule.end_date || '',
      due_days: schedule.due_days || 30,
      line_items: (schedule.line_items || []).map(item => ({
        description: item.description || '',
        item_type: item.item_type || 'service_flat',
        amount: item.amount || 0,
      })),
    });
    setShowCreateModal(true);
  };

  const getFrequencyDetails = (schedule: RecurringSchedule) => {
    const day = schedule.day_of_period;
    if (schedule.frequency === 'weekly' || schedule.frequency === 'bi_weekly') {
      return `Every ${DAY_OF_WEEK_LABELS[day] || 'day'}`;
    }
    if (['monthly', 'quarterly', 'yearly'].includes(schedule.frequency) && day) {
      return `On the ${getOrdinalSuffix(day)}`;
    }
    return FREQUENCY_LABELS[schedule.frequency] || schedule.frequency;
  };

  // Handlers
  const handleToggleStatus = async (id: string, currentStatus: string) => {
    try {
      await api.resources.update('recurring_invoices', id, { status: currentStatus === 'active' ? 'paused' : 'active' });
      await refetch();
      addNotification({ type: 'success', title: currentStatus === 'active' ? 'Schedule Paused' : 'Schedule Resumed', message: 'The schedule status was updated.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this recurring schedule?')) {
      try {
        await api.resources.remove('recurring_invoices', id);
        await refetch();
        addNotification({ type: 'success', title: 'Schedule Deleted', message: 'The recurring schedule has been removed.' });
      } catch (err) {
        addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
      }
    }
  };

  const handleCreateSchedule = async () => {
    if (!formData.name.trim()) {
      addNotification({ type: 'error', title: 'Name Required', message: 'Please enter a schedule name.' });
      return;
    }

    const lineItems = formData.line_items
      .filter(item => item.description && item.amount > 0)
      .map(item => ({
        item_type: item.item_type,
        description: item.description,
        amount: item.amount
      }));

    const input = {
      name: formData.name,
      client_name: formData.client_name || undefined,
      frequency: formData.frequency,
      day_of_period: formData.day_of_period,
      start_date: formData.start_date,
      end_date: formData.end_date || undefined,
      due_days: formData.due_days,
      line_items: lineItems.length > 0 ? JSON.stringify(lineItems) : undefined
    };

    try {
      if (editingSchedule) {
        setUpdating(true);
        await api.resources.update('recurring_invoices', editingSchedule.id, input);
      } else {
        setCreating(true);
        await api.resources.create('recurring_invoices', input);
      }
      await refetch();
      setShowCreateModal(false);
      resetForm();
      addNotification({ type: 'success', title: editingSchedule ? 'Schedule Updated' : 'Schedule Created', message: 'The recurring schedule has been saved.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
    } finally {
      setCreating(false);
      setUpdating(false);
    }
  };

  const handleGenerate = async (id: string) => {
    try {
      const invoice = await api.post<{ invoice_number?: string }>(`/invoicing/recurring/${id}/generate`, {});
      await refetch();
      addNotification({ type: 'success', title: 'Invoice Generated', message: `Invoice ${invoice.invoice_number || 'New'} has been created.` });
    } catch (err) {
      addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
    }
  };

  const handleLineItemChange = (index: number, field: 'description' | 'amount', value: string | number) => {
    setFormData(prev => ({
      ...prev,
      line_items: prev.line_items.map((item, i) => i === index ? { ...item, [field]: value } : item)
    }));
  };

  // Stats
  const activeCount = schedules.filter(s => s.status === 'active').length;
  const monthlyRevenue = schedules
    .filter(s => s.status === 'active')
    .reduce((sum, s) => sum + calculateMonthlyRevenue(s), 0);
  const totalGenerated = schedules.reduce((sum, s) => sum + s.invoices_generated, 0);

  if (loading) return <CenteredLoading />;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <StatsGrid columns={3}>
        <StatCard
          icon={<ArrowPathIcon className="w-6 h-6 text-primary-600" />}
          iconBg="bg-primary-100"
          label="Active Schedules"
          value={activeCount}
        />
        <StatCard
          icon={<CalendarDaysIcon className="w-6 h-6 text-green-600" />}
          iconBg="bg-green-100"
          label="Est. Monthly Revenue"
          value={formatCurrencyIntl(monthlyRevenue)}
          valueColor="text-green-600"
        />
        <StatCard
          icon={<ClockIcon className="w-6 h-6 text-purple-600" />}
          iconBg="bg-purple-100"
          label="Total Generated"
          value={totalGenerated}
          valueColor="text-purple-600"
        />
      </StatsGrid>

      {/* Schedule List */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="p-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Recurring Schedules</h2>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <PlusIcon className="w-4 h-4" />
            New Schedule
          </button>
        </div>

        {schedules.length === 0 ? (
          <EmptyState
            icon={<ArrowPathIcon className="w-12 h-12" />}
            title="No Recurring Invoices"
            description="Set up recurring schedules to automatically generate invoices."
            action={{
              label: 'Create First Schedule',
              onClick: () => setShowCreateModal(true),
              icon: <PlusIcon className="w-4 h-4" />,
            }}
          />
        ) : (
          <div className="divide-y divide-gray-100">
            {schedules.map((schedule) => (
              <ScheduleRow
                key={schedule.id}
                schedule={schedule}
                frequencyDetails={getFrequencyDetails(schedule)}
                onGenerate={() => void handleGenerate(schedule.id)}
                onToggleStatus={() => handleToggleStatus(schedule.id, schedule.status)}
                onEdit={() => handleOpenEdit(schedule)}
                onDelete={() => handleDelete(schedule.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => { setShowCreateModal(false); resetForm(); }}
        title={editingSchedule ? 'Edit Recurring Schedule' : 'Create Recurring Schedule'}
        maxWidth="2xl"
        footer={
          <>
            <ModalButton variant="secondary" onClick={() => { setShowCreateModal(false); resetForm(); }}>
              Cancel
            </ModalButton>
            <ModalButton onClick={handleCreateSchedule} loading={creating || updating}>
              {editingSchedule ? 'Update Schedule' : 'Create Schedule'}
            </ModalButton>
          </>
        }
      >
        <div className="space-y-6">
          {/* Name & Client */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Schedule Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                className="w-full input"
                placeholder="e.g., Monthly Daycare - Smith Family"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Client Name</label>
              <input
                type="text"
                value={formData.client_name}
                onChange={(e) => setFormData(prev => ({ ...prev, client_name: e.target.value }))}
                className="w-full input"
                placeholder="e.g., Smith Family"
              />
            </div>
          </div>

          {/* Frequency */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Frequency</label>
            <div className="grid grid-cols-5 gap-2">
              {(['weekly', 'bi_weekly', 'monthly', 'quarterly', 'yearly'] as RecurringFrequency[]).map((freq) => (
                <button
                  key={freq}
                  type="button"
                  onClick={() => setFormData(prev => ({ ...prev, frequency: freq }))}
                  className={`py-2 px-3 rounded-lg border-2 text-sm font-medium transition-all ${
                    formData.frequency === freq
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {FREQUENCY_LABELS[freq]}
                </button>
              ))}
            </div>
          </div>

          {/* Day Selection */}
          {(formData.frequency === 'weekly' || formData.frequency === 'bi_weekly') && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Day of Week</label>
              <select
                value={formData.day_of_period}
                onChange={(e) => setFormData(prev => ({ ...prev, day_of_period: parseInt(e.target.value) }))}
                className="w-full input"
              >
                {DAY_OF_WEEK_LABELS.map((day, idx) => (
                  <option key={idx} value={idx}>{day}</option>
                ))}
              </select>
            </div>
          )}

          {['monthly', 'quarterly', 'yearly'].includes(formData.frequency) && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Day of Month</label>
              <select
                value={formData.day_of_period}
                onChange={(e) => setFormData(prev => ({ ...prev, day_of_period: parseInt(e.target.value) }))}
                className="w-full input"
              >
                {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                  <option key={day} value={day}>{day}</option>
                ))}
              </select>
            </div>
          )}

          {/* Dates */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
              <input
                type="date"
                value={formData.start_date}
                onChange={(e) => setFormData(prev => ({ ...prev, start_date: e.target.value }))}
                className="w-full input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">End Date (optional)</label>
              <input
                type="date"
                value={formData.end_date}
                onChange={(e) => setFormData(prev => ({ ...prev, end_date: e.target.value }))}
                className="w-full input"
              />
            </div>
          </div>

          {/* Line Items */}
          <SimpleLineItemList
            items={formData.line_items}
            onChange={handleLineItemChange}
            onAdd={() => setFormData(prev => ({ ...prev, line_items: [...prev.line_items, { description: '', item_type: 'service_flat', amount: 0 }] }))}
            onRemove={(idx) => setFormData(prev => ({ ...prev, line_items: prev.line_items.filter((_, i) => i !== idx) }))}
          />

          {/* Total */}
          <div className="p-4 bg-gray-50 rounded-lg">
            <div className="flex justify-between items-center">
              <span className="font-medium text-gray-700">Total per Invoice</span>
              <span className="text-2xl font-bold text-gray-900">
                {formatCurrencyIntl(formData.line_items.reduce((sum, item) => sum + item.amount, 0))}
              </span>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

// -------------------- Schedule Row Component --------------------

interface ScheduleRowProps {
  schedule: RecurringSchedule;
  frequencyDetails: string;
  onGenerate: () => void;
  onToggleStatus: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

const ScheduleRow: React.FC<ScheduleRowProps> = ({
  schedule,
  frequencyDetails,
  onGenerate,
  onToggleStatus,
  onEdit,
  onDelete,
}) => {
  const amount = calculateScheduleAmount(schedule);
  const periodLabel = schedule.frequency === 'weekly' ? 'week' 
    : schedule.frequency === 'bi_weekly' ? '2 weeks' 
    : 'month';

  return (
    <div className="p-4 hover:bg-gray-50">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h3 className="font-medium text-gray-900">{schedule.name}</h3>
            <RecurringStatusBadge status={schedule.status} />
          </div>
          
          <div className="flex items-center gap-4 text-sm text-gray-500 mb-3">
            <span className="flex items-center gap-1">
              <UserGroupIcon className="w-4 h-4" />
              {schedule.client_name}
            </span>
            <span className="flex items-center gap-1">
              <ArrowPathIcon className="w-4 h-4" />
              {FREQUENCY_LABELS[schedule.frequency]} • {frequencyDetails}
            </span>
            <span className="flex items-center gap-1">
              <CalendarDaysIcon className="w-4 h-4" />
              Next: {schedule.next_invoice_date ? formatDate(schedule.next_invoice_date) : 'N/A'}
            </span>
          </div>

          <div className="flex items-center gap-4">
            <span className="text-lg font-bold text-gray-900">
              {formatCurrencyIntl(amount)}
              <span className="text-sm font-normal text-gray-500">/{periodLabel}</span>
            </span>
            <span className="text-sm text-gray-500">{schedule.invoices_generated} invoices generated</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button onClick={onGenerate} className="p-2 text-gray-400 hover:text-primary-600 rounded" title="Generate Now">
            <PlayIcon className="w-5 h-5" />
          </button>
          <button
            onClick={onToggleStatus}
            className={`p-2 rounded ${schedule.status === 'active' ? 'text-gray-400 hover:text-yellow-600' : 'text-gray-400 hover:text-green-600'}`}
            title={schedule.status === 'active' ? 'Pause' : 'Resume'}
          >
            {schedule.status === 'active' ? <PauseIcon className="w-5 h-5" /> : <PlayIcon className="w-5 h-5" />}
          </button>
          <button onClick={onEdit} className="p-2 text-gray-400 hover:text-blue-600 rounded" title="Edit">
            <PencilIcon className="w-5 h-5" />
          </button>
          <button onClick={onDelete} className="p-2 text-gray-400 hover:text-red-600 rounded" title="Delete">
            <TrashIcon className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Recurring;
