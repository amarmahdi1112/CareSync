// ============================================
// Data Privacy View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  ArrowDownTrayIcon,
  ShieldCheckIcon,
  DocumentTextIcon,
  TrashIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { useAuth } from '../../../context/AuthContext';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  SettingsSubsection,
  InfoBanner,
} from '../components';

// -------------------- Types --------------------

interface ExportOption {
  id: string;
  name: string;
  description: string;
  format: string;
  size?: string;
}

const exportOptions: ExportOption[] = [
  { id: 'families', name: 'Families & Children', description: 'All family records including guardians, children, and emergency contacts', format: 'CSV', size: '~2 MB' },
  { id: 'attendance', name: 'Attendance Records', description: 'Check-in/check-out history and attendance reports', format: 'CSV', size: '~5 MB' },
  { id: 'invoices', name: 'Invoices & Payments', description: 'All invoices, line items, and payment records', format: 'CSV', size: '~1 MB' },
  { id: 'all', name: 'Complete Data Export', description: 'All data in your account including settings and configurations', format: 'ZIP', size: '~10 MB' },
];

const Privacy: React.FC = () => {
  const { addNotification } = useNotifications();
  const { state } = useAuth();
  const organization = state.organization;

  const [exportingId, setExportingId] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  const handleExport = async (exportId: string) => {
    setExportingId(exportId);
    await new Promise((resolve) => setTimeout(resolve, 2000));
    setExportingId(null);
    addNotification({
      type: 'success',
      title: 'Export Started',
      message: "Your data export is being prepared. You will receive an email when it's ready to download.",
    });
  };

  const handleDeleteAccount = () => {
    if (deleteConfirmText !== organization?.name) {
      addNotification({
        type: 'error',
        title: 'Confirmation Required',
        message: 'Please type your organization name exactly to confirm deletion.',
      });
      return;
    }
    addNotification({
      type: 'info',
      title: 'Account Deletion',
      message: 'Account deletion requests must be submitted via email to support@caresync.com for verification.',
    });
    setShowDeleteModal(false);
    setDeleteConfirmText('');
  };

  return (
    <SettingsPageLayout title="Data & Privacy" description="Export your data, manage retention, and control your account.">
      {/* Data Export Section */}
      <SettingsSection title="Data Export" icon={DocumentTextIcon} description="Download copies of your data" className="mb-6">
        <div className="space-y-4">
          {exportOptions.map((option) => (
            <ExportOptionCard key={option.id} option={option} exporting={exportingId === option.id} onExport={() => handleExport(option.id)} />
          ))}
        </div>
      </SettingsSection>

      {/* Data Retention Section */}
      <SettingsSection title="Data Retention" icon={ClockIcon} className="mb-6">
        <div className="space-y-6">
          <RetentionPolicy title="Active Records" description="Family and child records are retained while your account is active." period="Indefinite" />
          <RetentionPolicy title="Attendance History" description="Attendance logs are stored for compliance and reporting purposes." period="7 years" />
          <RetentionPolicy title="Financial Records" description="Invoices and payment records are retained for tax and audit compliance." period="7 years" />
          <RetentionPolicy title="Deleted Records" description="When you delete records, they are moved to trash and permanently removed after." period="30 days" />
        </div>
      </SettingsSection>

      {/* Security Info */}
      <InfoBanner icon={ShieldCheckIcon} title="Data Security" className="mb-6">
        <ul className="space-y-1">
          <li>• All data is encrypted at rest and in transit</li>
          <li>• We never sell or share your data with third parties</li>
          <li>• Regular security audits and penetration testing</li>
          <li>• SOC 2 Type II compliance (in progress)</li>
        </ul>
      </InfoBanner>

      {/* Danger Zone */}
      <SettingsSection className="border-red-200">
        <SettingsSubsection title="Danger Zone" icon={ExclamationTriangleIcon}>
          <p className="text-sm text-gray-600 mb-4">
            Once you delete your account, there is no going back. Please be certain.
          </p>
          <button onClick={() => setShowDeleteModal(true)} className="btn bg-red-600 text-white hover:bg-red-700">
            <TrashIcon className="w-4 h-4" /> Delete Account
          </button>
        </SettingsSubsection>
      </SettingsSection>

      {/* Delete Modal */}
      {showDeleteModal && (
        <DeleteAccountModal
          organizationName={organization?.name || ''}
          confirmText={deleteConfirmText}
          setConfirmText={setDeleteConfirmText}
          onDelete={handleDeleteAccount}
          onClose={() => { setShowDeleteModal(false); setDeleteConfirmText(''); }}
        />
      )}
    </SettingsPageLayout>
  );
};

// -------------------- Sub-components --------------------

interface ExportOptionCardProps {
  option: ExportOption;
  exporting: boolean;
  onExport: () => void;
}

const ExportOptionCard: React.FC<ExportOptionCardProps> = ({ option, exporting, onExport }) => (
  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
    <div>
      <p className="font-medium text-gray-900">{option.name}</p>
      <p className="text-sm text-gray-500">{option.description}</p>
      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
        <span>Format: {option.format}</span>
        {option.size && <span>Est. size: {option.size}</span>}
      </div>
    </div>
    <button onClick={onExport} disabled={exporting} className="btn btn-secondary btn-sm">
      {exporting ? (
        <span className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          Exporting...
        </span>
      ) : (
        <>
          <ArrowDownTrayIcon className="w-4 h-4" /> Export
        </>
      )}
    </button>
  </div>
);

interface RetentionPolicyProps {
  title: string;
  description: string;
  period: string;
}

const RetentionPolicy: React.FC<RetentionPolicyProps> = ({ title, description, period }) => (
  <div className="flex items-start justify-between">
    <div>
      <p className="font-medium text-gray-900">{title}</p>
      <p className="text-sm text-gray-500">{description}</p>
    </div>
    <span className="px-3 py-1 bg-gray-100 text-gray-700 text-sm font-medium rounded-full">{period}</span>
  </div>
);

interface DeleteAccountModalProps {
  organizationName: string;
  confirmText: string;
  setConfirmText: (text: string) => void;
  onDelete: () => void;
  onClose: () => void;
}

const DeleteAccountModal: React.FC<DeleteAccountModalProps> = ({
  organizationName,
  confirmText,
  setConfirmText,
  onDelete,
  onClose,
}) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-red-600">Delete Account</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>

      <div className="mb-6">
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
          <p className="text-sm text-red-800">
            <strong>Warning:</strong> This action cannot be undone. This will permanently delete your organization and all associated data.
          </p>
        </div>

        <p className="text-sm text-gray-600 mb-4">
          Please type <strong>{organizationName}</strong> to confirm:
        </p>
        <input
          type="text"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          className="input"
          placeholder="Type organization name..."
        />
      </div>

      <div className="flex justify-end gap-3">
        <button onClick={onClose} className="btn btn-secondary">Cancel</button>
        <button
          onClick={onDelete}
          disabled={confirmText !== organizationName}
          className="btn bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Delete Account
        </button>
      </div>
    </div>
  </div>
);

export default Privacy;
