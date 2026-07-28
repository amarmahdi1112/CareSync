// ============================================
// Client & Funding Source Selector Components
// ============================================

import React, { useState, useRef, useEffect } from 'react';
import { XMarkIcon, ChevronDownIcon, CheckIcon, UserGroupIcon } from '@heroicons/react/24/outline';
import type { Family, FundingSource, Child } from '../../types';

// Helper to build full name with optional middle name
const getChildFullName = (child: Child): string => {
  const parts = [child.first_name];
  if (child.middle_name) parts.push(child.middle_name);
  parts.push(child.last_name);
  return parts.join(' ');
};

// -------------------- Client Selector (Single) --------------------

interface ClientSelectorProps {
  families: Family[];
  selectedFamilyId: string;
  onSelect: (familyId: string) => void;
  label?: string;
}

export const ClientSelector: React.FC<ClientSelectorProps> = ({
  families,
  selectedFamilyId,
  onSelect,
  label = 'Bill To',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getFamilyDisplayName = (family: Family) => {
    const guardian = family.guardians?.[0];
    return guardian ? `${guardian.first_name} ${guardian.last_name}` : family.name;
  };

  const getChildrenNames = (family: Family) => {
    return family.children?.map(c => getChildFullName(c).toLowerCase()) || [];
  };

  // Search by guardian name OR children names
  const filteredFamilies = families.filter(family => {
    const searchLower = search.toLowerCase();
    const guardianName = getFamilyDisplayName(family).toLowerCase();
    const childrenNames = getChildrenNames(family);
    
    return guardianName.includes(searchLower) || 
           childrenNames.some(name => name.includes(searchLower));
  });

  const selectedFamily = families.find(f => f.id === selectedFamilyId);

  return (
    <div ref={dropdownRef} className="relative">
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      
      {/* Selected display / trigger */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="min-h-[42px] w-full px-3 py-2 bg-white border border-gray-300 rounded-lg cursor-pointer flex items-center justify-between gap-2 hover:border-gray-400 transition-colors"
      >
        <div className="flex-1">
          {selectedFamily ? (
            <div>
              <span className="text-gray-900">{getFamilyDisplayName(selectedFamily)}</span>
              <span className="text-gray-500 text-sm ml-2">
                ({selectedFamily.children?.map(c => getChildFullName(c)).join(', ') || 'No children'})
              </span>
            </div>
          ) : (
            <span className="text-gray-400">Select a client...</span>
          )}
        </div>
        <ChevronDownIcon className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-72 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-gray-100">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by family or child name..."
              className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              onClick={(e) => e.stopPropagation()}
              autoFocus
            />
          </div>
          
          {/* Family list */}
          <div className="overflow-y-auto max-h-56">
            {/* Clear selection option */}
            {selectedFamilyId && (
              <div
                onClick={() => {
                  onSelect('');
                  setIsOpen(false);
                  setSearch('');
                }}
                className="px-4 py-2 cursor-pointer text-gray-500 hover:bg-gray-50 border-b border-gray-100 text-sm"
              >
                Clear selection
              </div>
            )}
            
            {filteredFamilies.length === 0 ? (
              <div className="px-4 py-3 text-sm text-gray-500 text-center">
                No families found
              </div>
            ) : (
              filteredFamilies.map(family => {
                const isSelected = family.id === selectedFamilyId;
                const childNames = family.children?.map(c => getChildFullName(c)).join(', ') || 'No children';
                return (
                  <div
                    key={family.id}
                    onClick={() => {
                      onSelect(family.id);
                      setIsOpen(false);
                      setSearch('');
                    }}
                    className={`px-4 py-2.5 cursor-pointer hover:bg-gray-50 ${isSelected ? 'bg-primary-50' : ''}`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {getFamilyDisplayName(family)}
                        </p>
                        <p className="text-xs text-gray-500">
                          Children: {childNames}
                        </p>
                      </div>
                      {isSelected && <CheckIcon className="w-4 h-4 text-primary-600" />}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// -------------------- Multi Client Selector --------------------

interface MultiClientSelectorProps {
  families: Family[];
  selectedFamilyIds: string[];
  onSelect: (familyIds: string[]) => void;
  label?: string;
}

export const MultiClientSelector: React.FC<MultiClientSelectorProps> = ({
  families,
  selectedFamilyIds,
  onSelect,
  label = 'Bill To',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleFamily = (familyId: string) => {
    if (selectedFamilyIds.includes(familyId)) {
      onSelect(selectedFamilyIds.filter(id => id !== familyId));
    } else {
      onSelect([...selectedFamilyIds, familyId]);
    }
  };

  const removeFamily = (familyId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(selectedFamilyIds.filter(id => id !== familyId));
  };

  const getFamilyDisplayName = (family: Family) => {
    const guardian = family.guardians?.[0];
    return guardian ? `${guardian.first_name} ${guardian.last_name}` : family.name;
  };

  const getChildrenNames = (family: Family) => {
    return family.children?.map(c => getChildFullName(c).toLowerCase()) || [];
  };

  // Search by guardian name OR children names
  const filteredFamilies = families.filter(family => {
    const searchLower = search.toLowerCase();
    const guardianName = getFamilyDisplayName(family).toLowerCase();
    const childrenNames = getChildrenNames(family);
    
    return guardianName.includes(searchLower) || 
           childrenNames.some(name => name.includes(searchLower));
  });

  const selectedFamilies = families.filter(f => selectedFamilyIds.includes(f.id));

  return (
    <div ref={dropdownRef} className="relative">
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {selectedFamilyIds.length > 1 && (
          <span className="ml-2 text-xs text-primary-600 font-normal">
            ({selectedFamilyIds.length} families selected)
          </span>
        )}
      </label>
      
      {/* Selected items display / trigger */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="min-h-[42px] w-full px-3 py-2 bg-white border border-gray-300 rounded-lg cursor-pointer flex items-center justify-between gap-2 hover:border-gray-400 transition-colors"
      >
        <div className="flex-1 flex flex-wrap gap-1.5">
          {selectedFamilies.length === 0 ? (
            <span className="text-gray-400">Select families to bill...</span>
          ) : (
            selectedFamilies.map(family => (
              <span
                key={family.id}
                className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-50 text-primary-700 rounded-md text-sm"
              >
                {getFamilyDisplayName(family)}
                <button
                  onClick={(e) => removeFamily(family.id, e)}
                  className="hover:bg-primary-100 rounded p-0.5"
                >
                  <XMarkIcon className="w-3.5 h-3.5" />
                </button>
              </span>
            ))
          )}
        </div>
        <ChevronDownIcon className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-gray-100">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by family or child name..."
              className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
          
          {/* Family list */}
          <div className="overflow-y-auto max-h-48">
            {filteredFamilies.length === 0 ? (
              <div className="px-4 py-3 text-sm text-gray-500 text-center">
                No families found
              </div>
            ) : (
              filteredFamilies.map(family => {
                const isSelected = selectedFamilyIds.includes(family.id);
                return (
                  <div
                    key={family.id}
                    onClick={() => toggleFamily(family.id)}
                    className={`px-4 py-2.5 cursor-pointer flex items-center justify-between hover:bg-gray-50 ${
                      isSelected ? 'bg-primary-50' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-5 h-5 border-2 rounded flex items-center justify-center ${
                        isSelected ? 'border-primary-500 bg-primary-500' : 'border-gray-300'
                      }`}>
                        {isSelected && <CheckIcon className="w-3.5 h-3.5 text-white" />}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {getFamilyDisplayName(family)}
                        </p>
                        <p className="text-xs text-gray-500">
                          {family.children?.map(c => getChildFullName(c)).join(', ') || 'No children'}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Quick actions */}
          {families.length > 2 && (
            <div className="p-2 border-t border-gray-100 flex gap-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(families.map(f => f.id));
                }}
                className="flex-1 px-2 py-1.5 text-xs text-primary-600 hover:bg-primary-50 rounded"
              >
                Select All
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect([]);
                }}
                className="flex-1 px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded"
              >
                Clear All
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// -------------------- Selected Clients Summary --------------------

interface SelectedClientsSummaryProps {
  families: Family[];
  selectedFamilyIds: string[];
}

export const SelectedClientsSummary: React.FC<SelectedClientsSummaryProps> = ({
  families,
  selectedFamilyIds,
}) => {
  const selectedFamilies = families.filter(f => selectedFamilyIds.includes(f.id));
  const totalChildren = selectedFamilies.reduce((sum, f) => sum + (f.children?.length || 0), 0);
  
  if (selectedFamilies.length === 0) return null;

  return (
    <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
      <div className="flex items-center gap-2 mb-2">
        <UserGroupIcon className="w-5 h-5 text-blue-600" />
        <span className="text-sm font-medium text-blue-900">
          {selectedFamilies.length} {selectedFamilies.length === 1 ? 'Family' : 'Families'} • {totalChildren} {totalChildren === 1 ? 'Child' : 'Children'}
        </span>
      </div>
      <div className="space-y-1">
        {selectedFamilies.map(family => {
          const guardian = family.guardians?.[0];
          const name = guardian ? `${guardian.first_name} ${guardian.last_name}` : family.name;
          const childNames = family.children?.map(c => getChildFullName(c)).join(', ') || 'No children';
          return (
            <div key={family.id} className="text-xs text-blue-800">
              <span className="font-medium">{name}:</span> {childNames}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// -------------------- Client Info Display --------------------

interface ClientInfoDisplayProps {
  clientName: string;
  fileNumber: string;
  clientAddress: string;
  onNameChange: (value: string) => void;
  onFileNumberChange: (value: string) => void;
  onAddressChange: (value: string) => void;
}

export const ClientInfoDisplay: React.FC<ClientInfoDisplayProps> = ({
  clientName,
  fileNumber,
  clientAddress,
  onNameChange,
  onFileNumberChange,
  onAddressChange,
}) => {
  return (
    <div className="grid grid-cols-2 gap-4 p-3 bg-gray-50 rounded-lg">
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
        <input
          type="text"
          value={clientName}
          onChange={(e) => onNameChange(e.target.value)}
          className="w-full px-2 py-1 text-sm bg-white text-gray-900 border border-gray-200 rounded"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">File Number (FSCD)</label>
        <input
          type="text"
          value={fileNumber}
          onChange={(e) => onFileNumberChange(e.target.value)}
          placeholder="e.g., FSCD-12345"
          className="w-full px-2 py-1 text-sm bg-white text-gray-900 border border-gray-200 rounded"
        />
      </div>
      <div className="col-span-2">
        <label className="block text-xs font-medium text-gray-500 mb-1">Address</label>
        <input
          type="text"
          value={clientAddress}
          onChange={(e) => onAddressChange(e.target.value)}
          className="w-full px-2 py-1 text-sm bg-white text-gray-900 border border-gray-200 rounded"
        />
      </div>
    </div>
  );
};

// -------------------- Funding Source Selector --------------------

interface FundingSourceSelectorProps {
  fundingSources: FundingSource[];
  selectedId: string;
  onSelect: (id: string) => void;
  label?: string;
  required?: boolean;
}

export const FundingSourceSelector: React.FC<FundingSourceSelectorProps> = ({
  fundingSources,
  selectedId,
  onSelect,
  label = 'Send Invoice To',
  required = true,
}) => {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <select
        value={selectedId}
        onChange={(e) => onSelect(e.target.value)}
        className="input"
      >
        <option value="">Select funding agency...</option>
        {fundingSources.map((source) => (
          <option key={source.id} value={source.id}>
            {source.name} {source.contact_email ? `(${source.contact_email})` : ''}
          </option>
        ))}
      </select>
      {fundingSources.length === 0 && (
        <p className="text-xs text-amber-600 mt-1">
          No funding sources configured. Go to Settings → Invoicing to add FSCD, Alberta Support, etc.
        </p>
      )}
    </div>
  );
};

// -------------------- Date Range Picker --------------------

interface DateRangePickerProps {
  startDate: string;
  endDate: string;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
  startLabel?: string;
  endLabel?: string;
  optional?: boolean;
}

export const DateRangePicker: React.FC<DateRangePickerProps> = ({
  startDate,
  endDate,
  onStartChange,
  onEndChange,
  startLabel = 'Start Date',
  endLabel = 'End Date',
  optional = false,
}) => {
  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {startLabel} {optional && <span className="text-gray-400">(optional)</span>}
        </label>
        <input
          type="date"
          value={startDate}
          onChange={(e) => onStartChange(e.target.value)}
          className="input"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {endLabel} {optional && <span className="text-gray-400">(optional)</span>}
        </label>
        <input
          type="date"
          value={endDate}
          onChange={(e) => onEndChange(e.target.value)}
          className="input"
        />
      </div>
    </div>
  );
};

// -------------------- Discount & Tax Fields --------------------

interface DiscountTaxFieldsProps {
  discountType: 'amount' | 'percentage';
  discountValue: number;
  taxRate: number;
  taxName?: string;
  onDiscountTypeChange: (type: 'amount' | 'percentage') => void;
  onDiscountValueChange: (value: number) => void;
  onTaxRateChange: (value: number) => void;
}

export const DiscountTaxFields: React.FC<DiscountTaxFieldsProps> = ({
  discountType,
  discountValue,
  taxRate,
  taxName,
  onDiscountTypeChange,
  onDiscountValueChange,
  onTaxRateChange,
}) => {
  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Discount</label>
        <div className="flex gap-2">
          <select
            value={discountType}
            onChange={(e) => onDiscountTypeChange(e.target.value as 'amount' | 'percentage')}
            className="px-2 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg text-sm"
          >
            <option value="amount">$</option>
            <option value="percentage">%</option>
          </select>
          <input
            type="number"
            value={discountValue || ''}
            onChange={(e) => onDiscountValueChange(parseFloat(e.target.value) || 0)}
            className="flex-1 px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg"
            step="0.01"
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Tax Rate (%) {taxName && `- ${taxName}`}
        </label>
        <input
          type="number"
          value={taxRate || ''}
          onChange={(e) => onTaxRateChange(parseFloat(e.target.value) || 0)}
          className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg"
          step="0.01"
        />
      </div>
    </div>
  );
};

// -------------------- Notes & Terms Fields --------------------

interface NotesTermsFieldsProps {
  notes: string;
  terms: string;
  onNotesChange: (value: string) => void;
  onTermsChange: (value: string) => void;
}

export const NotesTermsFields: React.FC<NotesTermsFieldsProps> = ({
  notes,
  terms,
  onNotesChange,
  onTermsChange,
}) => {
  return (
    <>
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
        <textarea
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          rows={2}
          className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg"
          placeholder="Payment instructions, bank details, etc."
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Terms & Conditions</label>
        <textarea
          value={terms}
          onChange={(e) => onTermsChange(e.target.value)}
          rows={2}
          className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg"
          placeholder="Payment due within 30 days..."
        />
      </div>
    </>
  );
};
