// ============================================
// Line Item Editor Component
// ============================================

import React from 'react';
import { TrashIcon } from '@heroicons/react/24/outline';
import type { LineItem, LineItemType, Child } from '../../types';
import { LineItemTypeBadge } from '../common/StatusBadge';
import { calculateLineItemAmount } from '../../utils/calculations';
import { formatCurrency } from '../../utils/formatters';

// Helper to build full name with optional middle name
const getChildFullName = (child: Child): string => {
  const parts = [child.first_name];
  if (child.middle_name) parts.push(child.middle_name);
  parts.push(child.last_name);
  return parts.join(' ');
};

// -------------------- Single Line Item Editor --------------------

interface LineItemEditorProps {
  item: LineItem;
  onChange: (updates: Partial<LineItem>) => void;
  onRemove: () => void;
  canRemove: boolean;
  children?: Child[];
  currencySymbol?: string;
}

export const LineItemEditor: React.FC<LineItemEditorProps> = ({
  item,
  onChange,
  onRemove,
  canRemove,
  children = [],
  currencySymbol = '$',
}) => {
  const amount = calculateLineItemAmount(item);

  return (
    <div className="p-4 border border-gray-200 rounded-lg">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <LineItemTypeBadge type={item.item_type} />
        {canRemove && (
          <button
            onClick={onRemove}
            className="text-red-500 hover:text-red-700"
          >
            <TrashIcon className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Type-specific fields */}
      {item.item_type === 'daycare_subsidy' && (
        <DaycareSubsidyFields
          item={item}
          onChange={onChange}
          children={children}
          currencySymbol={currencySymbol}
          amount={amount}
        />
      )}

      {item.item_type === 'service_hourly' && (
        <ServiceHourlyFields
          item={item}
          onChange={onChange}
          currencySymbol={currencySymbol}
          amount={amount}
        />
      )}

      {item.item_type === 'service_flat' && (
        <ServiceFlatFields
          item={item}
          onChange={onChange}
          currencySymbol={currencySymbol}
        />
      )}

      {item.item_type === 'product' && (
        <ProductFields
          item={item}
          onChange={onChange}
          currencySymbol={currencySymbol}
          amount={amount}
        />
      )}
    </div>
  );
};

// -------------------- Daycare Subsidy Fields --------------------

interface DaycareSubsidyFieldsProps {
  item: LineItem;
  onChange: (updates: Partial<LineItem>) => void;
  children: Child[];
  currencySymbol: string;
  amount: number;
}

const DaycareSubsidyFields: React.FC<DaycareSubsidyFieldsProps> = ({
  item,
  onChange,
  children,
  currencySymbol,
  amount,
}) => {
  const handleChildSelect = (childId: string) => {
    const child = children.find(c => c.id === childId);
    const fullName = child ? getChildFullName(child) : '';
    onChange({
      child_id: childId,
      child_name: fullName,
      description: fullName ? `${fullName} - Childcare` : item.description,
    });
  };

  return (
    <>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Child</label>
          <select
            value={item.child_id || ''}
            onChange={(e) => handleChildSelect(e.target.value)}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
          >
            <option value="">Select child...</option>
            {children.map(child => (
              <option key={child.id} value={child.id}>
                {getChildFullName(child)} ({child.age_group})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Description</label>
          <input
            type="text"
            value={item.description}
            onChange={(e) => onChange({ description: e.target.value })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            placeholder="e.g., June Childcare"
          />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Full Rate</label>
          <input
            type="number"
            value={item.full_rate || ''}
            onChange={(e) => onChange({ full_rate: parseFloat(e.target.value) || 0 })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            step="0.01"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Subsidy</label>
          <input
            type="number"
            value={item.subsidy_amount || ''}
            onChange={(e) => onChange({ subsidy_amount: parseFloat(e.target.value) || 0 })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            step="0.01"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Amount</label>
          <div className="px-2 py-1.5 text-sm bg-gray-100 rounded font-medium">
            {formatCurrency(amount, currencySymbol)}
          </div>
        </div>
      </div>
    </>
  );
};

// -------------------- Service Hourly Fields --------------------

interface ServiceHourlyFieldsProps {
  item: LineItem;
  onChange: (updates: Partial<LineItem>) => void;
  currencySymbol: string;
  amount: number;
}

const ServiceHourlyFields: React.FC<ServiceHourlyFieldsProps> = ({
  item,
  onChange,
  currencySymbol,
  amount,
}) => {
  return (
    <>
      <div className="mb-3">
        <label className="block text-xs text-gray-500 mb-1">Description</label>
        <input
          type="text"
          value={item.description}
          onChange={(e) => onChange({ description: e.target.value })}
          className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
          placeholder="e.g., Support Worker Services"
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Hours</label>
          <input
            type="number"
            value={item.hours || ''}
            onChange={(e) => onChange({ hours: parseFloat(e.target.value) || 0 })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            step="0.5"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Rate/Hour</label>
          <input
            type="number"
            value={item.hourly_rate || ''}
            onChange={(e) => onChange({ hourly_rate: parseFloat(e.target.value) || 0 })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            step="0.01"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Amount</label>
          <div className="px-2 py-1.5 text-sm bg-gray-100 rounded font-medium">
            {formatCurrency(amount, currencySymbol)}
          </div>
        </div>
      </div>
    </>
  );
};

// -------------------- Service Flat Fields --------------------

interface ServiceFlatFieldsProps {
  item: LineItem;
  onChange: (updates: Partial<LineItem>) => void;
  currencySymbol: string;
}

const ServiceFlatFields: React.FC<ServiceFlatFieldsProps> = ({
  item,
  onChange,
}) => {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="block text-xs text-gray-500 mb-1">Description</label>
        <input
          type="text"
          value={item.description}
          onChange={(e) => onChange({ description: e.target.value })}
          className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
          placeholder="e.g., Registration Fee"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">Amount</label>
        <input
          type="number"
          value={item.amount || ''}
          onChange={(e) => onChange({ amount: parseFloat(e.target.value) || 0 })}
          className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
          step="0.01"
        />
      </div>
    </div>
  );
};

// -------------------- Product Fields --------------------

interface ProductFieldsProps {
  item: LineItem;
  onChange: (updates: Partial<LineItem>) => void;
  currencySymbol: string;
  amount: number;
}

const ProductFields: React.FC<ProductFieldsProps> = ({
  item,
  onChange,
  currencySymbol,
  amount,
}) => {
  return (
    <>
      <div className="mb-3">
        <label className="block text-xs text-gray-500 mb-1">Item Name</label>
        <input
          type="text"
          value={item.description}
          onChange={(e) => onChange({ description: e.target.value })}
          className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
          placeholder="e.g., Art Supplies"
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Quantity</label>
          <input
            type="number"
            value={item.quantity || ''}
            onChange={(e) => onChange({ quantity: parseFloat(e.target.value) || 0 })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            step="1"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Unit Price</label>
          <input
            type="number"
            value={item.unit_price || ''}
            onChange={(e) => onChange({ unit_price: parseFloat(e.target.value) || 0 })}
            className="w-full px-2 py-1.5 text-sm bg-white text-gray-900 border border-gray-200 rounded"
            step="0.01"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Amount</label>
          <div className="px-2 py-1.5 text-sm bg-gray-100 rounded font-medium">
            {formatCurrency(amount, currencySymbol)}
          </div>
        </div>
      </div>
    </>
  );
};

// -------------------- Add Line Item Buttons --------------------

interface AddLineItemButtonsProps {
  onAdd: (type: LineItemType) => void;
}

export const AddLineItemButtons: React.FC<AddLineItemButtonsProps> = ({ onAdd }) => {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onAdd('daycare_subsidy')}
        className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
      >
        + Daycare
      </button>
      <button
        onClick={() => onAdd('service_hourly')}
        className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200"
      >
        + Hourly
      </button>
      <button
        onClick={() => onAdd('service_flat')}
        className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded hover:bg-purple-200"
      >
        + Flat Rate
      </button>
      <button
        onClick={() => onAdd('product')}
        className="text-xs px-2 py-1 bg-orange-100 text-orange-700 rounded hover:bg-orange-200"
      >
        + Product
      </button>
    </div>
  );
};

// -------------------- Simple Line Item List (for templates/recurring) --------------------

interface SimpleLineItem {
  description: string;
  amount: number;
}

interface SimpleLineItemListProps {
  items: SimpleLineItem[];
  onChange: (index: number, field: 'description' | 'amount', value: string | number) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

export const SimpleLineItemList: React.FC<SimpleLineItemListProps> = ({
  items,
  onChange,
  onAdd,
  onRemove,
}) => {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">Line Items</label>
      <div className="space-y-2">
        {items.map((item, idx) => (
          <div key={idx} className="flex gap-2">
            <input
              type="text"
              value={item.description}
              onChange={(e) => onChange(idx, 'description', e.target.value)}
              placeholder="Description"
              className="flex-1 input"
            />
            <div className="relative w-32">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
              <input
                type="number"
                step="0.01"
                value={item.amount || ''}
                onChange={(e) => onChange(idx, 'amount', parseFloat(e.target.value) || 0)}
                placeholder="0.00"
                className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              />
            </div>
            {items.length > 1 && (
              <button
                type="button"
                onClick={() => onRemove(idx)}
                className="p-2 text-red-400 hover:text-red-600"
              >
                <TrashIcon className="w-5 h-5" />
              </button>
            )}
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={onAdd}
        className="mt-2 text-sm text-primary-600 hover:text-primary-700 font-medium"
      >
        + Add Line Item
      </button>
    </div>
  );
};
