// ============================================
// Status Badge Components
// ============================================

import React from 'react';
import {
  PencilIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  XMarkIcon,
  PauseIcon,
} from '@heroicons/react/24/outline';
import type { InvoiceStatus, CreditNoteStatus, RecurringStatus } from '../../types';
import { INVOICE_STATUS_CONFIG, CREDIT_STATUS_CONFIG } from '../../constants';

// -------------------- Invoice Status Badge --------------------

interface InvoiceStatusBadgeProps {
  status: InvoiceStatus;
}

const InvoiceStatusIcons: Record<InvoiceStatus, React.ReactNode> = {
  draft: <PencilIcon className="w-3 h-3" />,
  sent: <ClockIcon className="w-3 h-3" />,
  paid: <CheckCircleIcon className="w-3 h-3" />,
  overdue: <ExclamationCircleIcon className="w-3 h-3" />,
  cancelled: null,
};

export const InvoiceStatusBadge: React.FC<InvoiceStatusBadgeProps> = ({ status }) => {
  const config = INVOICE_STATUS_CONFIG[status] || INVOICE_STATUS_CONFIG.draft;
  const icon = InvoiceStatusIcons[status];

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      {icon}
      {config.label}
    </span>
  );
};

// -------------------- Credit Note Status Badge --------------------

interface CreditStatusBadgeProps {
  status: CreditNoteStatus;
}

const CreditStatusIcons: Record<CreditNoteStatus, React.FC<{ className?: string }>> = {
  draft: ClockIcon,
  issued: ClockIcon,
  partially_applied: CheckCircleIcon,
  fully_applied: CheckCircleIcon,
  void: XMarkIcon,
};

export const CreditStatusBadge: React.FC<CreditStatusBadgeProps> = ({ status }) => {
  const config = CREDIT_STATUS_CONFIG[status] || CREDIT_STATUS_CONFIG.draft;
  const Icon = CreditStatusIcons[status] || ClockIcon;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      <Icon className="w-3 h-3" />
      {config.label}
    </span>
  );
};

// -------------------- Recurring Status Badge --------------------

interface RecurringStatusBadgeProps {
  status: RecurringStatus;
}

export const RecurringStatusBadge: React.FC<RecurringStatusBadgeProps> = ({ status }) => {
  const configs: Record<RecurringStatus, { bg: string; text: string; icon: React.ReactNode; label: string }> = {
    active: {
      bg: 'bg-green-100',
      text: 'text-green-700',
      icon: <CheckCircleIcon className="w-3 h-3" />,
      label: 'Active',
    },
    paused: {
      bg: 'bg-yellow-100',
      text: 'text-yellow-700',
      icon: <PauseIcon className="w-3 h-3" />,
      label: 'Paused',
    },
    cancelled: {
      bg: 'bg-gray-100',
      text: 'text-gray-500',
      icon: <XMarkIcon className="w-3 h-3" />,
      label: 'Cancelled',
    },
    completed: {
      bg: 'bg-gray-100',
      text: 'text-gray-700',
      icon: <CheckCircleIcon className="w-3 h-3" />,
      label: 'Completed',
    },
  };

  const config = configs[status] || configs.active;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      {config.icon}
      {config.label}
    </span>
  );
};

// -------------------- Line Item Type Badge --------------------

interface LineItemTypeBadgeProps {
  type: string;
}

export const LineItemTypeBadge: React.FC<LineItemTypeBadgeProps> = ({ type }) => {
  const configs: Record<string, { bg: string; text: string; label: string }> = {
    daycare_subsidy: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Daycare (Subsidy)' },
    service_hourly: { bg: 'bg-green-100', text: 'text-green-700', label: 'Service (Hourly)' },
    service_flat: { bg: 'bg-purple-100', text: 'text-purple-700', label: 'Service (Flat)' },
    product: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Product' },
  };

  const config = configs[type] || configs.service_flat;

  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
};

// -------------------- Generic Badge --------------------

interface GenericBadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
}

export const GenericBadge: React.FC<GenericBadgeProps> = ({ children, variant = 'default' }) => {
  const variants = {
    default: 'bg-gray-100 text-gray-700',
    primary: 'bg-primary-100 text-primary-700',
    success: 'bg-green-100 text-green-700',
    warning: 'bg-yellow-100 text-yellow-700',
    danger: 'bg-red-100 text-red-700',
  };

  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${variants[variant]}`}>
      {children}
    </span>
  );
};
