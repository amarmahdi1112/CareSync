// ============================================
// Integrations Settings View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  KeyIcon,
  PlusIcon,
  TrashIcon,
  ClipboardDocumentIcon,
  EyeIcon,
  EyeSlashIcon,
  ArrowPathIcon,
  GlobeAltIcon,
  BoltIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  FormInput,
  SettingsEmptyState,
} from '../components';

// -------------------- Types --------------------

interface APIKey {
  id: string;
  name: string;
  key: string;
  createdAt: string;
  lastUsed: string | null;
  permissions: string[];
}

interface Webhook {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  lastTriggered: string | null;
  failureCount: number;
}

interface WebhookEvent {
  id: string;
  label: string;
  category: string;
}

// -------------------- Mock Data --------------------

const mockAPIKeys: APIKey[] = [
  { id: '1', name: 'Production API Key', key: 'cs_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx', createdAt: '2024-10-15', lastUsed: '2024-11-28', permissions: ['read:families', 'read:attendance', 'write:invoices'] },
  { id: '2', name: 'Development Key', key: 'cs_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxx', createdAt: '2024-11-01', lastUsed: null, permissions: ['read:families', 'read:attendance'] },
];

const mockWebhooks: Webhook[] = [
  { id: '1', url: 'https://api.example.com/webhooks/caresync', events: ['family.created', 'invoice.paid'], active: true, lastTriggered: '2024-11-28T14:30:00Z', failureCount: 0 },
];

const availableEvents: WebhookEvent[] = [
  { id: 'family.created', label: 'Family Created', category: 'Families' },
  { id: 'family.updated', label: 'Family Updated', category: 'Families' },
  { id: 'child.checkin', label: 'Child Check-in', category: 'Attendance' },
  { id: 'child.checkout', label: 'Child Check-out', category: 'Attendance' },
  { id: 'invoice.created', label: 'Invoice Created', category: 'Billing' },
  { id: 'invoice.paid', label: 'Invoice Paid', category: 'Billing' },
  { id: 'invoice.overdue', label: 'Invoice Overdue', category: 'Billing' },
];

const Integrations: React.FC = () => {
  const { addNotification } = useNotifications();
  const [apiKeys] = useState<APIKey[]>(mockAPIKeys);
  const [webhooks] = useState<Webhook[]>(mockWebhooks);
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [showCreateKeyModal, setShowCreateKeyModal] = useState(false);
  const [showCreateWebhookModal, setShowCreateWebhookModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newWebhookUrl, setNewWebhookUrl] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);

  const toggleKeyVisibility = (keyId: string) => {
    setVisibleKeys((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(keyId)) newSet.delete(keyId);
      else newSet.add(keyId);
      return newSet;
    });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    addNotification({ type: 'success', title: 'Copied', message: 'API key copied to clipboard.' });
  };

  const handleCreateKey = () => {
    if (!newKeyName.trim()) {
      addNotification({ type: 'error', title: 'Name Required', message: 'Please enter a name for your API key.' });
      return;
    }
    addNotification({ type: 'info', title: 'Coming Soon', message: 'API key creation will be available in a future update.' });
    setShowCreateKeyModal(false);
    setNewKeyName('');
  };

  const handleCreateWebhook = () => {
    if (!newWebhookUrl.trim() || selectedEvents.length === 0) {
      addNotification({ type: 'error', title: 'Missing Fields', message: 'Please enter a URL and select at least one event.' });
      return;
    }
    addNotification({ type: 'info', title: 'Coming Soon', message: 'Webhook configuration will be available in a future update.' });
    setShowCreateWebhookModal(false);
    setNewWebhookUrl('');
    setSelectedEvents([]);
  };

  const maskKey = (key: string) => key.substring(0, 8) + '••••••••••••••••••••';

  const showComingSoon = (feature: string) => {
    addNotification({ type: 'info', title: 'Coming Soon', message: `${feature} will be available soon.` });
  };

  return (
    <SettingsPageLayout
      title="Integrations"
      description="Connect CareSync with your other tools using API keys and webhooks."
      maxWidth="4xl"
      actions={<span className="px-2 py-0.5 rounded text-xs font-medium bg-primary-100 text-primary-800">Pro</span>}
    >
      {/* API Keys Section */}
      <SettingsSection
        title="API Keys"
        icon={KeyIcon}
        description="Use API keys to authenticate requests to the CareSync API."
        className="mb-6"
      >
        <div className="flex justify-end mb-4">
          <button onClick={() => setShowCreateKeyModal(true)} className="btn btn-primary btn-sm">
            <PlusIcon className="h-4 w-4" /> Create Key
          </button>
        </div>

        {apiKeys.length === 0 ? (
          <SettingsEmptyState
            icon={KeyIcon}
            title="No API keys yet"
            description="Create your first API key to get started"
            action={{ label: 'Create your first API key', onClick: () => setShowCreateKeyModal(true) }}
          />
        ) : (
          <div className="divide-y divide-gray-200 border-t border-gray-200">
            {apiKeys.map((apiKey) => (
              <APIKeyRow
                key={apiKey.id}
                apiKey={apiKey}
                isVisible={visibleKeys.has(apiKey.id)}
                onToggleVisibility={() => toggleKeyVisibility(apiKey.id)}
                onCopy={() => copyToClipboard(apiKey.key)}
                onRegenerate={() => showComingSoon('Key regeneration')}
                onDelete={() => showComingSoon('Key deletion')}
                maskKey={maskKey}
              />
            ))}
          </div>
        )}
      </SettingsSection>

      {/* Webhooks Section */}
      <SettingsSection
        title="Webhooks"
        icon={BoltIcon}
        description="Receive real-time notifications when events happen in CareSync."
        className="mb-6"
      >
        <div className="flex justify-end mb-4">
          <button onClick={() => setShowCreateWebhookModal(true)} className="btn btn-primary btn-sm">
            <PlusIcon className="h-4 w-4" /> Add Webhook
          </button>
        </div>

        {webhooks.length === 0 ? (
          <SettingsEmptyState
            icon={BoltIcon}
            title="No webhooks configured"
            description="Add your first webhook to receive notifications"
            action={{ label: 'Add your first webhook', onClick: () => setShowCreateWebhookModal(true) }}
          />
        ) : (
          <div className="divide-y divide-gray-200 border-t border-gray-200">
            {webhooks.map((webhook) => (
              <WebhookRow
                key={webhook.id}
                webhook={webhook}
                onEdit={() => showComingSoon('Webhook editing')}
                onDelete={() => showComingSoon('Webhook deletion')}
              />
            ))}
          </div>
        )}
      </SettingsSection>

      {/* API Documentation CTA */}
      <div className="bg-gradient-to-r from-gray-800 to-gray-900 rounded-xl p-6 text-white">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-white/10 rounded-lg">
            <KeyIcon className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold mb-2">API Documentation</h3>
            <p className="text-gray-300 text-sm mb-4">Learn how to integrate CareSync with your applications using our comprehensive API documentation.</p>
            <button onClick={() => showComingSoon('API documentation')} className="inline-flex items-center px-4 py-2 bg-white text-gray-900 font-medium rounded-lg hover:bg-gray-100 transition-colors text-sm">
              View Documentation
            </button>
          </div>
        </div>
      </div>

      {/* Create API Key Modal */}
      {showCreateKeyModal && (
        <Modal title="Create API Key" onClose={() => setShowCreateKeyModal(false)}>
          <FormInput label="Key Name" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} placeholder="e.g., Production API Key" hint="A descriptive name to identify this key." />
          <div className="flex justify-end gap-3 mt-6">
            <button onClick={() => setShowCreateKeyModal(false)} className="btn btn-secondary">Cancel</button>
            <button onClick={handleCreateKey} className="btn btn-primary">Create Key</button>
          </div>
        </Modal>
      )}

      {/* Create Webhook Modal */}
      {showCreateWebhookModal && (
        <Modal title="Add Webhook" onClose={() => setShowCreateWebhookModal(false)}>
          <FormInput label="Endpoint URL" type="url" value={newWebhookUrl} onChange={(e) => setNewWebhookUrl(e.target.value)} placeholder="https://api.example.com/webhooks" />
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">Events</label>
            <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-3 space-y-2">
              {availableEvents.map((event) => (
                <label key={event.id} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedEvents.includes(event.id)}
                    onChange={(e) => setSelectedEvents(e.target.checked ? [...selectedEvents, event.id] : selectedEvents.filter((id) => id !== event.id))}
                    className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                  />
                  <span className="text-sm text-gray-700">{event.label}</span>
                  <span className="text-xs text-gray-400">({event.category})</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button onClick={() => setShowCreateWebhookModal(false)} className="btn btn-secondary">Cancel</button>
            <button onClick={handleCreateWebhook} className="btn btn-primary">Add Webhook</button>
          </div>
        </Modal>
      )}
    </SettingsPageLayout>
  );
};

// -------------------- Sub-components --------------------

interface ModalProps {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}

const Modal: React.FC<ModalProps> = ({ title, children, onClose }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>
      {children}
    </div>
  </div>
);

interface APIKeyRowProps {
  apiKey: APIKey;
  isVisible: boolean;
  onToggleVisibility: () => void;
  onCopy: () => void;
  onRegenerate: () => void;
  onDelete: () => void;
  maskKey: (key: string) => string;
}

const APIKeyRow: React.FC<APIKeyRowProps> = ({ apiKey, isVisible, onToggleVisibility, onCopy, onRegenerate, onDelete, maskKey }) => (
  <div className="p-4">
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <div className="flex items-center gap-3 mb-2">
          <p className="font-medium text-gray-900">{apiKey.name}</p>
          <span className="text-xs text-gray-400">Created {apiKey.createdAt}</span>
        </div>
        <div className="flex items-center gap-2 mb-3">
          <code className="px-3 py-1.5 bg-gray-100 rounded font-mono text-sm text-gray-700">
            {isVisible ? apiKey.key : maskKey(apiKey.key)}
          </code>
          <button onClick={onToggleVisibility} className="p-1.5 text-gray-400 hover:text-gray-600 rounded" title={isVisible ? 'Hide' : 'Show'}>
            {isVisible ? <EyeSlashIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
          </button>
          <button onClick={onCopy} className="p-1.5 text-gray-400 hover:text-gray-600 rounded" title="Copy">
            <ClipboardDocumentIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>Last used: {apiKey.lastUsed || 'Never'}</span>
          <span>Permissions: {apiKey.permissions.length}</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={onRegenerate} className="p-2 text-gray-400 hover:text-gray-600 rounded" title="Regenerate">
          <ArrowPathIcon className="h-4 w-4" />
        </button>
        <button onClick={onDelete} className="p-2 text-red-400 hover:text-red-600 rounded" title="Delete">
          <TrashIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
);

interface WebhookRowProps {
  webhook: Webhook;
  onEdit: () => void;
  onDelete: () => void;
}

const WebhookRow: React.FC<WebhookRowProps> = ({ webhook, onEdit, onDelete }) => (
  <div className="p-4">
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <div className="flex items-center gap-3 mb-2">
          <GlobeAltIcon className="h-5 w-5 text-gray-400" />
          <code className="text-sm text-gray-700 break-all">{webhook.url}</code>
          {webhook.active ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
              <CheckCircleIcon className="h-3 w-3" /> Active
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
              <XCircleIcon className="h-3 w-3" /> Inactive
            </span>
          )}
          {webhook.failureCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
              <ExclamationTriangleIcon className="h-3 w-3" /> {webhook.failureCount} failures
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2 mb-2">
          {webhook.events.map((event) => (
            <span key={event} className="px-2 py-0.5 bg-gray-100 rounded text-xs text-gray-600">{event}</span>
          ))}
        </div>
        <div className="text-xs text-gray-500">Last triggered: {webhook.lastTriggered ? new Date(webhook.lastTriggered).toLocaleString() : 'Never'}</div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={onEdit} className="text-sm text-primary-600 hover:text-primary-700">Edit</button>
        <button onClick={onDelete} className="p-2 text-red-400 hover:text-red-600 rounded">
          <TrashIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
);

export default Integrations;
