// ============================================
// Invoice Templates View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  StarIcon,
  DocumentTextIcon,
  SparklesIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { InvoiceTemplate, TemplateLineItem, LineItemType } from '../types';

// Components
import { ContentCard, EmptyStateCard } from '../components/layout';
import { CenteredLoading } from '../components/common/EmptyState';
import { Modal, ModalButton } from '../components/common/Modal';
import { SimpleLineItemList } from '../components/forms/LineItemEditor';

// Utils
import { formatCurrencyIntl } from '../utils/formatters';
import { calculateLineItemAmount } from '../utils/calculations';
import { DEFAULT_TEMPLATE_FORM } from '../constants';

interface TemplatesProps {
  onUseTemplate: (template: InvoiceTemplate) => void;
}

const Templates: React.FC<TemplatesProps> = ({ onUseTemplate }) => {
  const { addNotification } = useNotifications();
  const [searchQuery, setSearchQuery] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<InvoiceTemplate | null>(null);
  const [newTemplate, setNewTemplate] = useState(DEFAULT_TEMPLATE_FORM);
  const [creating, setCreating] = useState(false);
  const [updatingTemplate, setUpdatingTemplate] = useState(false);

  const { data: templateRows = [], loading, refetch } = useApiQuery<Array<InvoiceTemplate & { line_items?: TemplateLineItem[] | string }>>('/resources/invoice_templates', { limit: 1000, sort: 'created_at', order: 'desc' });
  const templates: InvoiceTemplate[] = templateRows.map((template) => ({
    ...template,
    line_items: typeof template.line_items === 'string'
      ? (() => { try { return JSON.parse(template.line_items); } catch { return []; } })()
      : (template.line_items || []),
  }));

  // Helpers
  const calculateTemplateTotal = (template: InvoiceTemplate) => {
    return (template.line_items || []).reduce((sum, item) => sum + calculateLineItemAmount(item), 0);
  };

  const filteredTemplates = templates.filter(t => {
    return searchQuery === '' || 
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (t.description || '').toLowerCase().includes(searchQuery.toLowerCase());
  });

  const resetForm = () => {
    setNewTemplate(DEFAULT_TEMPLATE_FORM);
    setEditingTemplate(null);
  };

  const handleOpenEdit = (template: InvoiceTemplate) => {
    setEditingTemplate(template);
    setNewTemplate({
      name: template.name,
      description: template.description || '',
      due_days: template.due_days || 30,
      default_tax_rate: template.default_tax_rate || 0,
      line_items: (template.line_items || []).map(item => ({
        description: item.description || '',
        item_type: item.item_type || 'service_flat',
        amount: item.amount || 0,
      })),
      notes: template.notes || '',
      terms: template.terms || '',
    });
    setShowCreateModal(true);
  };

  const handleCreateTemplate = async () => {
    if (!newTemplate.name.trim()) {
      addNotification({ type: 'error', title: 'Name Required', message: 'Please enter a template name.' });
      return;
    }

    const lineItems = newTemplate.line_items
      .filter(item => item.description)
      .map(item => ({
        item_type: item.item_type,
        description: item.description,
        amount: item.amount || 0
      }));

    const input = {
      name: newTemplate.name,
      description: newTemplate.description || undefined,
      due_days: newTemplate.due_days,
      default_tax_rate: newTemplate.default_tax_rate,
      line_items: lineItems.length > 0 ? JSON.stringify(lineItems) : undefined,
      notes: newTemplate.notes || undefined,
      terms: newTemplate.terms || undefined
    };

    try {
      if (editingTemplate) {
        setUpdatingTemplate(true);
        await api.resources.update('invoice_templates', editingTemplate.id, input);
      } else {
        setCreating(true);
        await api.resources.create('invoice_templates', input);
      }
      await refetch();
      setShowCreateModal(false);
      resetForm();
      addNotification({ type: 'success', title: editingTemplate ? 'Template Updated' : 'Template Created', message: 'Your template has been saved.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
    } finally {
      setCreating(false);
      setUpdatingTemplate(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.resources.remove('invoice_templates', id);
      await refetch();
      addNotification({ type: 'success', title: 'Template Deleted', message: 'The template has been removed.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await Promise.all(templates.map((template) => api.resources.update('invoice_templates', template.id, { is_default: template.id === id })));
      await refetch();
      addNotification({ type: 'success', title: 'Default Updated', message: 'Default template has been changed.' });
    } catch (err) {
      addNotification({ type: 'error', title: 'Error', message: err instanceof Error ? err.message : 'Request failed' });
    }
  };

  const handleLineItemChange = (index: number, field: 'description' | 'amount', value: string | number) => {
    setNewTemplate(prev => ({
      ...prev,
      line_items: prev.line_items.map((item, i) => 
        i === index ? { ...item, [field]: value } : item
      )
    }));
  };

  const handleAddLineItem = () => {
    setNewTemplate(prev => ({
      ...prev,
      line_items: [...prev.line_items, { description: '', item_type: 'service_flat' as LineItemType, amount: 0 }]
    }));
  };

  const handleRemoveLineItem = (index: number) => {
    setNewTemplate(prev => ({
      ...prev,
      line_items: prev.line_items.filter((_, i) => i !== index)
    }));
  };

  if (loading) return <CenteredLoading />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Invoice Templates</h2>
          <p className="text-sm text-gray-500">Create invoices faster with reusable templates</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          <PlusIcon className="w-5 h-5" />
          New Template
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          placeholder="Search templates..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 max-w-xs input"
        />
        <span className="text-sm text-gray-500">
          {templates.length} template{templates.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Template Grid */}
      {filteredTemplates.length === 0 ? (
        <ContentCard>
          <EmptyStateCard
            icon={<DocumentTextIcon className="w-8 h-8 text-gray-400" />}
            title="No Templates Found"
            description={searchQuery ? 'Try adjusting your search.' : 'Create your first template to speed up invoicing.'}
            action={{
              label: 'Create Template',
              onClick: () => setShowCreateModal(true),
              icon: <PlusIcon className="w-5 h-5" />,
            }}
          />
        </ContentCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTemplates.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              total={calculateTemplateTotal(template)}
              onToggleDefault={() => void handleSetDefault(template.id)}
              onDelete={() => {
                if (confirm('Delete this template? This cannot be undone.')) {
                  void handleDelete(template.id);
                }
              }}
              onUse={() => {
                onUseTemplate(template);
                addNotification({ type: 'success', title: 'Template Applied', message: 'Create Invoice tab opened with template data.' });
              }}
              onEdit={() => handleOpenEdit(template)}
            />
          ))}
        </div>
      )}

      {/* Pro Tips */}
      <div className="bg-gradient-to-r from-primary-600 to-primary-700 rounded-xl p-6 text-white">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-white/10 rounded-lg">
            <SparklesIcon className="h-6 w-6" />
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-2">Pro Tip: Save Time with Templates</h3>
            <ul className="text-primary-100 text-sm space-y-1">
              <li>• Set your most-used template as default for quick access</li>
              <li>• Create templates for different services (daycare, tutoring, events)</li>
              <li>• Include standard notes and terms to save typing</li>
              <li>• Use templates with recurring invoices for maximum efficiency</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => { setShowCreateModal(false); resetForm(); }}
        title={editingTemplate ? 'Edit Template' : 'Create Template'}
        maxWidth="2xl"
        footer={
          <>
            <ModalButton variant="secondary" onClick={() => { setShowCreateModal(false); resetForm(); }}>
              Cancel
            </ModalButton>
            <ModalButton onClick={handleCreateTemplate} loading={creating || updatingTemplate}>
              {editingTemplate ? 'Update Template' : 'Save Template'}
            </ModalButton>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Template Name</label>
              <input
                type="text"
                value={newTemplate.name}
                onChange={(e) => setNewTemplate(prev => ({ ...prev, name: e.target.value }))}
                className="w-full input"
                placeholder="e.g., Monthly Daycare Fee"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <input
                type="text"
                value={newTemplate.description}
                onChange={(e) => setNewTemplate(prev => ({ ...prev, description: e.target.value }))}
                className="w-full input"
                placeholder="Short description of when to use this template"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Due Days</label>
              <input
                type="number"
                value={newTemplate.due_days}
                onChange={(e) => setNewTemplate(prev => ({ ...prev, due_days: parseInt(e.target.value) || 30 }))}
                className="w-full input"
              />
            </div>
          </div>

          <SimpleLineItemList
            items={newTemplate.line_items}
            onChange={handleLineItemChange}
            onAdd={handleAddLineItem}
            onRemove={handleRemoveLineItem}
          />

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Default Notes</label>
              <textarea
                value={newTemplate.notes}
                onChange={(e) => setNewTemplate(prev => ({ ...prev, notes: e.target.value }))}
                rows={3}
                className="w-full input"
                placeholder="Notes to include on invoices"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Default Terms</label>
              <textarea
                value={newTemplate.terms}
                onChange={(e) => setNewTemplate(prev => ({ ...prev, terms: e.target.value }))}
                rows={3}
                className="w-full input"
                placeholder="Terms & conditions"
              />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

// -------------------- Template Card Component --------------------

interface TemplateCardProps {
  template: InvoiceTemplate;
  total: number;
  onToggleDefault: () => void;
  onDelete: () => void;
  onUse: () => void;
  onEdit: () => void;
}

const TemplateCard: React.FC<TemplateCardProps> = ({
  template,
  total,
  onToggleDefault,
  onDelete,
  onUse,
  onEdit,
}) => {
  return (
    <div className={`bg-white rounded-xl border-2 overflow-hidden transition-all hover:shadow-lg ${
      template.is_default ? 'border-primary-500' : 'border-gray-200'
    }`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold text-gray-900">{template.name}</h3>
              {template.is_default && (
                <span className="px-2 py-0.5 bg-primary-100 text-primary-700 rounded-full text-xs font-medium">
                  Default
                </span>
              )}
            </div>
            <p className="text-sm text-gray-500 line-clamp-2">{template.description}</p>
          </div>
          <button
            onClick={onToggleDefault}
            className={`p-1 rounded ${template.is_default ? 'text-yellow-500' : 'text-gray-300 hover:text-yellow-400'}`}
            title={template.is_default ? 'Default template' : 'Set as default'}
          >
            {template.is_default ? <StarSolidIcon className="w-5 h-5" /> : <StarIcon className="w-5 h-5" />}
          </button>
        </div>
        
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
            Due in {template.due_days} days
          </span>
          {template.default_tax_rate > 0 && <span>Tax: {template.default_tax_rate}%</span>}
        </div>
      </div>

      {/* Line Items Preview */}
      <div className="p-4 bg-gray-50">
        <div className="space-y-2 mb-3">
          {(template.line_items || []).slice(0, 3).map((item: TemplateLineItem, idx: number) => (
            <div key={idx} className="flex items-center justify-between text-sm">
              <span className="text-gray-600 truncate">{item.description}</span>
              <span className="font-medium text-gray-900">{formatCurrencyIntl(item.amount || 0)}</span>
            </div>
          ))}
          {(template.line_items || []).length > 3 && (
            <p className="text-xs text-gray-400">+{(template.line_items || []).length - 3} more items</p>
          )}
        </div>
        
        <div className="flex items-center justify-between pt-2 border-t border-gray-200">
          <span className="text-sm font-medium text-gray-700">Template Total</span>
          <span className="text-lg font-bold text-primary-600">{formatCurrencyIntl(total)}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="p-3 bg-white border-t border-gray-100 flex items-center justify-between">
        <div className="flex gap-1">
          <button onClick={onEdit} className="p-2 text-gray-400 hover:text-blue-600 rounded" title="Edit">
            <PencilIcon className="w-4 h-4" />
          </button>
          <button onClick={onDelete} className="p-2 text-gray-400 hover:text-red-600 rounded" title="Delete">
            <TrashIcon className="w-4 h-4" />
          </button>
        </div>
        <button
          onClick={onUse}
          className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700"
        >
          Use Template
          <ArrowRightIcon className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default Templates;
