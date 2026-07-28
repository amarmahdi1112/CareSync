// ============================================
// Family Detail View - Completely Redesigned
// ============================================

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  PencilIcon,
  TrashIcon,
  PhoneIcon,
  EnvelopeIcon,
  MapPinIcon,
  PlayIcon,
  PauseIcon,
  PlusIcon,
  UserIcon,
  ShieldCheckIcon,
  DocumentTextIcon,
  ChevronRightIcon,
  EllipsisHorizontalIcon,
  CheckCircleIcon,
  XCircleIcon,
  CurrencyDollarIcon,
  BanknotesIcon,
} from '@heroicons/react/24/outline';
import { UserGroupIcon } from '@heroicons/react/24/solid';

// Reusable UI components
import { ConfirmModal, Modal } from '../../../components/ui';

// Family-specific components (existing - will be redesigned later)
import { 
  GuardiansList,
  EditGuardianModal,
  EditChildModal,
  EditEmergencyContactModal,
  AddEmergencyContactModal,
  AddGuardianModal,
} from '../../../components/families';

import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Stores
import { useNotificationStore } from '../../../stores';

// Local components
import {
  PageContainer,
  PageHeader,
  ContentCard,
  DetailSkeleton,
  EmptyState,
} from '../components/layout';
import { StatusBadge, AgeGroupBadge } from '../components/cards';
import type { AgeGroup, FamilyStatus } from '../types';

// -------------------- Types --------------------

interface GuardianData {
  id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  guardian_type: 'primary' | 'secondary';
  email: string;
  cell_phone: string;
  home_phone?: string;
  work_phone?: string;
  address?: string;
  city?: string;
  postal_code?: string;
}

interface ChildData {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  start_date: string;
  gender?: string;
  age_group?: string;
  is_active: boolean;
  health_care_number?: string;
  allergies?: string;
  medical_conditions?: string;
  medications?: string;
  immunization_up_to_date?: boolean;
  doctor_name?: string;
  doctor_phone?: string;
}

interface EmergencyContactData {
  id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  cell_phone: string;
  home_phone?: string;
  authorized_pickup: boolean;
}

interface FamilyData {
  id: string;
  name: string;
  status: FamilyStatus;
  additional_notes?: string;
  photo_consent: boolean;
  field_trip_consent: boolean;
  emergency_medical_consent: boolean;
  is_recurring_billing: boolean;
  recurring_funding_source_id?: string;
  file_number?: string;
  additional_fees: Array<{ description: string; amount: number }>;
  guardians: GuardianData[];
  children: ChildData[];
  emergency_contacts: EmergencyContactData[];
  created_at: string;
  updated_at: string;
}

interface FundingSource {
  id: string;
  name: string;
  funding_type: string;
  is_active: boolean;
}

// -------------------- Helper Components --------------------

const mapAgeGroup = (ageGroup?: string): AgeGroup => {
  if (!ageGroup) return 'Preschool';
  if (ageGroup === 'SchoolAge') return 'School-Age';
  return ageGroup as AgeGroup;
};

// Tab Navigation
type TabType = 'overview' | 'children' | 'guardians' | 'billing' | 'consents' | 'notes';

const tabs: { id: TabType; name: string; icon: React.ElementType }[] = [
  { id: 'overview', name: 'Overview', icon: UserGroupIcon },
  { id: 'children', name: 'Children', icon: UserIcon },
  { id: 'guardians', name: 'Guardians', icon: UserGroupIcon },
  { id: 'billing', name: 'Billing', icon: CurrencyDollarIcon },
  { id: 'consents', name: 'Consents', icon: ShieldCheckIcon },
  { id: 'notes', name: 'Notes', icon: DocumentTextIcon },
];

// Child Card (Modern Design)
const ChildCard: React.FC<{
  child: ChildData;
  onClick: () => void;
  onEdit: () => void;
}> = ({ child, onClick, onEdit }) => {
  const age = calculateAge(child.date_of_birth);
  const ageGroup = mapAgeGroup(child.age_group);
  
  return (
    <div 
      onClick={onClick}
      className="group bg-white rounded-xl border border-gray-200 p-4 hover:shadow-lg hover:border-primary-300 hover:-translate-y-0.5 transition-all cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold ${
            child.is_active 
              ? 'bg-gradient-to-br from-primary-100 to-primary-200 text-primary-600' 
              : 'bg-gray-100 text-gray-400'
          }`}>
            {child.first_name[0]}{child.last_name[0]}
          </div>
          <div>
            <h4 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors">
              {child.first_name} {child.last_name}
            </h4>
            <div className="flex items-center gap-2 mt-1">
              <AgeGroupBadge ageGroup={ageGroup} />
              <span className="text-xs text-gray-500">{age}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {child.is_active ? (
            <span className="w-2 h-2 rounded-full bg-green-500" title="Active" />
          ) : (
            <span className="w-2 h-2 rounded-full bg-gray-300" title="Inactive" />
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-all"
          >
            <PencilIcon className="w-4 h-4" />
          </button>
          <ChevronRightIcon className="w-5 h-5 text-gray-300 group-hover:text-primary-500 transition-colors" />
        </div>
      </div>
      
      {/* Health Info */}
      {(child.allergies || child.medical_conditions) && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <div className="flex flex-wrap gap-2">
            {child.allergies && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-red-50 text-red-700">
                ⚠️ Allergies
              </span>
            )}
            {child.medical_conditions && (
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-amber-50 text-amber-700">
                🏥 Medical
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// Guardian Card (Modern Design)
const GuardianCard: React.FC<{
  guardian: GuardianData;
  isPrimary: boolean;
  onEdit: () => void;
}> = ({ guardian, isPrimary, onEdit }) => (
  <div className="group bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-primary-300 transition-all">
    <div className="flex items-start justify-between">
      <div className="flex items-center gap-3">
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold ${
          isPrimary 
            ? 'bg-gradient-to-br from-green-100 to-green-200 text-green-600' 
            : 'bg-gradient-to-br from-gray-100 to-gray-200 text-gray-600'
        }`}>
          {guardian.first_name[0]}{guardian.last_name[0]}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-gray-900">
              {guardian.first_name} {guardian.last_name}
            </h4>
            {isPrimary && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                Primary
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500">{guardian.relationship}</p>
        </div>
      </div>
      <button
        onClick={onEdit}
        className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-all"
      >
        <PencilIcon className="w-4 h-4" />
      </button>
    </div>
    
    <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
      <a href={`tel:${guardian.cell_phone}`} className="flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600">
        <PhoneIcon className="w-4 h-4 text-gray-400" />
        {guardian.cell_phone}
      </a>
      <a href={`mailto:${guardian.email}`} className="flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600 truncate">
        <EnvelopeIcon className="w-4 h-4 text-gray-400" />
        {guardian.email}
      </a>
    </div>
  </div>
);

// Emergency Contact Card (Modern Design)
const EmergencyContactCard: React.FC<{
  contact: EmergencyContactData;
  onEdit: () => void;
}> = ({ contact, onEdit }) => (
  <div className="group flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 rounded-xl transition-colors">
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
        <PhoneIcon className="w-5 h-5 text-red-600" />
      </div>
      <div>
        <div className="flex items-center gap-2">
          <p className="font-medium text-gray-900">{contact.first_name} {contact.last_name}</p>
          {contact.authorized_pickup && (
            <CheckCircleIcon className="w-4 h-4 text-green-500" title="Authorized for pickup" />
          )}
        </div>
        <p className="text-sm text-gray-500">{contact.relationship} • {contact.cell_phone}</p>
      </div>
    </div>
    <button
      onClick={onEdit}
      className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 rounded-lg transition-all"
    >
      <PencilIcon className="w-4 h-4" />
    </button>
  </div>
);

// Consent Item
const ConsentItem: React.FC<{ label: string; granted: boolean }> = ({ label, granted }) => (
  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
    <span className="text-gray-700">{label}</span>
    {granted ? (
      <span className="flex items-center gap-1.5 text-green-600 text-sm font-medium">
        <CheckCircleIcon className="w-5 h-5" />
        Granted
      </span>
    ) : (
      <span className="flex items-center gap-1.5 text-gray-400 text-sm font-medium">
        <XCircleIcon className="w-5 h-5" />
        Not Granted
      </span>
    )}
  </div>
);

// Quick Stat
const QuickStat: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="flex items-center justify-between py-2">
    <span className="text-sm text-gray-500">{label}</span>
    <span className="text-sm font-semibold text-gray-900">{value}</span>
  </div>
);

// Calculate age helper
const calculateAge = (dob: string): string => {
  const birth = new Date(dob);
  const now = new Date();
  const years = now.getFullYear() - birth.getFullYear();
  const months = now.getMonth() - birth.getMonth();
  
  if (years < 1) {
    const totalMonths = years * 12 + months;
    return `${totalMonths} mo`;
  }
  return `${years} yr${months > 0 ? ` ${months} mo` : ''}`;
};

// Actions Dropdown
const ActionsMenu: React.FC<{
  isActive: boolean;
  onEdit: () => void;
  onDeactivate: () => void;
  onActivate: () => void;
  onDelete: () => void;
}> = ({ isActive, onEdit, onDeactivate, onActivate, onDelete }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <EllipsisHorizontalIcon className="w-5 h-5" />
      </button>
      
      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-48 bg-white rounded-xl shadow-lg border border-gray-200 py-2 z-20">
            <button
              onClick={() => { setIsOpen(false); onEdit(); }}
              className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
            >
              <PencilIcon className="w-4 h-4" />
              Edit Name
            </button>
            <div className="border-t border-gray-100 my-1" />
            {isActive ? (
              <button
                onClick={() => { setIsOpen(false); onDeactivate(); }}
                className="w-full px-4 py-2 text-left text-sm text-amber-600 hover:bg-amber-50 flex items-center gap-2"
              >
                <PauseIcon className="w-4 h-4" />
                Deactivate
              </button>
            ) : (
              <button
                onClick={() => { setIsOpen(false); onActivate(); }}
                className="w-full px-4 py-2 text-left text-sm text-green-600 hover:bg-green-50 flex items-center gap-2"
              >
                <PlayIcon className="w-4 h-4" />
                Activate
              </button>
            )}
            <button
              onClick={() => { setIsOpen(false); onDelete(); }}
              className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
            >
              <TrashIcon className="w-4 h-4" />
              Delete Family
            </button>
          </div>
        </>
      )}
    </div>
  );
};

// -------------------- Main Component --------------------

const FamilyDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDeactivateModal, setShowDeactivateModal] = useState(false);
  const [showEditNameModal, setShowEditNameModal] = useState(false);
  const [editingName, setEditingName] = useState('');
  
  // Edit modal states
  const [editingGuardian, setEditingGuardian] = useState<GuardianData | null>(null);
  const [editingChild, setEditingChild] = useState<ChildData | null>(null);
  const [editingContact, setEditingContact] = useState<EmergencyContactData | null>(null);
  const [showAddContactModal, setShowAddContactModal] = useState(false);
  const [showAddGuardianModal, setShowAddGuardianModal] = useState(false);

  // Billing state
  const [billingEnabled, setBillingEnabled] = useState(false);
  const [selectedFundingSource, setSelectedFundingSource] = useState<string>('');
  const [fileNumber, setFileNumber] = useState('');

  const { success, error: showError } = useNotificationStore();

  const { data: family, loading, error, refetch } = useApiQuery<FamilyData>(`/families/${id || 'missing'}`);
  const { data: fundingData } = useApiQuery<FundingSource[]>('/resources/funding_sources', {
    is_active: true,
    limit: 1000,
  });
  const fundingSources = fundingData || [];
  const [updating, setUpdating] = useState(false);
  const [savingBilling, setSavingBilling] = useState(false);
  const [savingFees, setSavingFees] = useState(false);

  const updateBilling = async ({ variables }: { variables: {
    id: string;
    isRecurringBilling: boolean;
    recurringFundingSourceId: string | null;
    fileNumber: string | null;
  } }) => {
    setSavingBilling(true);
    try {
      await api.resources.update('families', variables.id, {
        is_recurring_billing: variables.isRecurringBilling,
        recurring_funding_source_id: variables.recurringFundingSourceId,
        file_number: variables.fileNumber,
      });
      success('Billing Updated', 'Billing settings saved.');
      await refetch();
    } catch (caught) {
      showError('Billing Update Failed', caught instanceof Error ? caught.message : 'Request failed');
    } finally {
      setSavingBilling(false);
    }
  };

  const updateAdditionalFees = async ({ variables }: {
    variables: { id: string; fees: Array<{ description: string; amount: number }> };
  }) => {
    setSavingFees(true);
    try {
      await api.resources.update('families', variables.id, { additional_fees: variables.fees });
      success('Fees Updated', 'Additional fees saved.');
      await refetch();
    } catch (caught) {
      showError('Fee Update Failed', caught instanceof Error ? caught.message : 'Request failed');
    } finally {
      setSavingFees(false);
    }
  };

  const toggleChildInvoice = async ({ variables }: {
    variables: { id: string; needInvoice: boolean };
  }) => {
    try {
      await api.resources.update('children', variables.id, { need_invoice: variables.needInvoice });
      await refetch();
    } catch (caught) {
      showError('Toggle Failed', caught instanceof Error ? caught.message : 'Request failed');
    }
  };

  // Additional fees state
  const [localFees, setLocalFees] = useState<Array<{ description: string; amount: number }>>([]);
  const [newFeeDesc, setNewFeeDesc] = useState('');
  const [newFeeAmount, setNewFeeAmount] = useState('');

  // Sync billing state when family data loads
  useEffect(() => {
    if (family) {
      setBillingEnabled(family.is_recurring_billing);
      setSelectedFundingSource(family.recurring_funding_source_id || '');
      setFileNumber(family.file_number || '');
      setLocalFees(family.additional_fees || []);
    }
  }, [family]);

  // Handlers
  const handleBack = () => navigate('/families');
  const handleEditName = () => {
    if (family) {
      setEditingName(family.name);
      setShowEditNameModal(true);
    }
  };
  const handleSaveName = () => {
    if (!editingName.trim()) return;
    if (!id) return;
    setUpdating(true);
    api.resources.update('families', id, { name: editingName.trim() })
      .then(() => {
        success('Family Updated', 'Family name has been updated.');
        setShowEditNameModal(false);
        return refetch();
      })
      .catch((caught: Error) => showError('Update Failed', caught.message))
      .finally(() => setUpdating(false));
  };
  const handleDelete = async () => {
    if (!id) return;
    try {
      await api.resources.remove('families', id);
      navigate('/families');
    } catch (caught) {
      showError('Delete Failed', caught instanceof Error ? caught.message : 'Request failed');
    } finally {
      setShowDeleteModal(false);
    }
  };
  const handleDeactivate = async () => {
    if (!id) return;
    try {
      await api.resources.update('families', id, { status: 'inactive' });
      setShowDeactivateModal(false);
      await refetch();
    } catch (caught) {
      showError('Deactivate Failed', caught instanceof Error ? caught.message : 'Request failed');
    }
  };
  const handleActivate = async () => {
    if (!id) return;
    try {
      await api.resources.update('families', id, { status: 'active' });
      await refetch();
    } catch (caught) {
      showError('Activate Failed', caught instanceof Error ? caught.message : 'Request failed');
    }
  };
  const handleAddChild = () => navigate(`/families/${id}/add-child`);
  const handleChildClick = (childId: string) => navigate(`/children/${childId}`);

  // Loading
  if (loading) {
    return (
      <PageContainer>
        <DetailSkeleton />
      </PageContainer>
    );
  }

  // Error
  if (error || !family) {
    return (
      <PageContainer>
        <ContentCard>
          <EmptyState
            icon={<UserGroupIcon className="w-8 h-8 text-gray-400" />}
            title="Family not found"
            description="We couldn't find this family. It may have been deleted."
            action={{ label: 'Back to Families', onClick: handleBack }}
          />
        </ContentCard>
      </PageContainer>
    );
  }

  const primaryGuardian = family.guardians.find(g => g.guardian_type === 'primary');
  const address = primaryGuardian?.address 
    ? `${primaryGuardian.address}${primaryGuardian.city ? `, ${primaryGuardian.city}` : ''}${primaryGuardian.postal_code ? ` ${primaryGuardian.postal_code}` : ''}`
    : null;

  const mappedGuardians = family.guardians.map((g) => ({
    id: g.id,
    firstName: g.first_name,
    lastName: g.last_name,
    relationship: (g.relationship || 'Other') as 'Mother' | 'Father' | 'Guardian' | 'Grandparent' | 'Other',
    phone: g.cell_phone,
    email: g.email,
    isPrimary: g.guardian_type === 'primary',
  }));

  return (
    <PageContainer>
      {/* Header */}
      <PageHeader
        title={family.name}
        description={`Member since ${new Date(family.created_at).toLocaleDateString()}`}
        icon={<UserGroupIcon className="w-6 h-6 text-white" />}
        backLink="/families"
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={family.status} />
            <ActionsMenu
              isActive={family.status === 'active'}
              onEdit={handleEditName}
              onDeactivate={() => setShowDeactivateModal(true)}
              onActivate={handleActivate}
              onDelete={() => setShowDeleteModal(true)}
            />
          </div>
        }
      />

      {/* Tabs */}
      <div className="mb-6">
        <nav className="flex space-x-6 overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const count = tab.id === 'children' ? family.children.length 
              : tab.id === 'guardians' ? family.guardians.length 
              : undefined;
            
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors flex items-center gap-2 ${
                  isActive 
                    ? 'border-primary-500 text-primary-600' 
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.name}
                {count !== undefined && (
                  <span className={`px-1.5 py-0.5 rounded-full text-xs ${
                    isActive ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <>
              {/* Children Section */}
              <ContentCard
                title="Children"
                description={`${family.children.length} enrolled`}
                actions={
                  <button onClick={handleAddChild} className="btn btn-primary btn-sm">
                    <PlusIcon className="w-4 h-4" /> Add Child
                  </button>
                }
              >
                {family.children.length === 0 ? (
                  <EmptyState
                    icon={<UserIcon className="w-6 h-6 text-gray-400" />}
                    title="No children"
                    description="Add your first child to this family"
                    action={{ label: 'Add Child', onClick: handleAddChild, icon: <PlusIcon className="w-4 h-4" /> }}
                  />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {family.children.map((child) => (
                      <ChildCard
                        key={child.id}
                        child={child}
                        onClick={() => handleChildClick(child.id)}
                        onEdit={() => setEditingChild(child)}
                      />
                    ))}
                  </div>
                )}
              </ContentCard>

              {/* Guardians Section */}
              <ContentCard
                title="Guardians"
                description={`${family.guardians.length} registered`}
                actions={
                  <button onClick={() => setShowAddGuardianModal(true)} className="btn btn-secondary btn-sm">
                    <PlusIcon className="w-4 h-4" /> Add
                  </button>
                }
              >
                {family.guardians.length === 0 ? (
                  <EmptyState
                    icon={<UserGroupIcon className="w-6 h-6 text-gray-400" />}
                    title="No guardians"
                    description="Add a guardian to this family"
                    action={{ label: 'Add Guardian', onClick: () => setShowAddGuardianModal(true) }}
                  />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {family.guardians.map((guardian) => (
                      <GuardianCard
                        key={guardian.id}
                        guardian={guardian}
                        isPrimary={guardian.guardian_type === 'primary'}
                        onEdit={() => setEditingGuardian(guardian)}
                      />
                    ))}
                  </div>
                )}
              </ContentCard>
            </>
          )}

          {/* Children Tab */}
          {activeTab === 'children' && (
            <ContentCard
              title="All Children"
              actions={
                <button onClick={handleAddChild} className="btn btn-primary btn-sm">
                  <PlusIcon className="w-4 h-4" /> Add Child
                </button>
              }
            >
              <div className="space-y-3">
                {family.children.map((child: any) => {
                  const age = child.date_of_birth ? (() => {
                    const dob = new Date(child.date_of_birth);
                    const now = new Date();
                    const y = now.getFullYear() - dob.getFullYear();
                    const m = now.getMonth() - dob.getMonth();
                    return m < 0 ? `${y - 1}y` : `${y}y`;
                  })() : '';

                  return (
                    <div key={child.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg group hover:bg-gray-100 transition-colors">
                      <div className="flex items-center gap-3 flex-1 cursor-pointer" onClick={() => handleChildClick(child.id)}>
                        <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
                          <UserIcon className="w-5 h-5 text-primary-600" />
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">
                            {child.first_name} {child.last_name}
                          </p>
                          <div className="flex items-center gap-2 text-xs text-gray-500">
                            {age && <span>{age} old</span>}
                            {child.age_group && (
                              <span className="px-2 py-0.5 bg-primary-50 text-primary-700 rounded-full text-xs font-medium">
                                {child.age_group}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Needs Invoice Toggle */}
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-medium ${child.need_invoice ? 'text-green-700' : 'text-gray-400'}`}>
                            {child.need_invoice ? '💰 Invoice' : 'No Invoice'}
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleChildInvoice({
                                variables: { id: child.id, needInvoice: !child.need_invoice },
                              });
                            }}
                            className={`relative inline-flex h-6 w-10 items-center rounded-full transition-colors ${
                              child.need_invoice ? 'bg-green-500' : 'bg-gray-300'
                            }`}
                          >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                              child.need_invoice ? 'translate-x-5' : 'translate-x-1'
                            }`} />
                          </button>
                        </div>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingChild(child);
                          }}
                          className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-primary-600 rounded transition-all"
                        >
                          <PencilIcon className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
                {family.children.length === 0 && (
                  <p className="text-gray-400 text-sm italic text-center py-4">No children added yet</p>
                )}
              </div>
              <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-100 text-xs text-blue-700">
                💡 Toggle "Invoice" ON for children that should be included when generating invoices for this family.
              </div>
            </ContentCard>
          )}

          {/* Guardians Tab */}
          {activeTab === 'guardians' && (
            <ContentCard
              title="All Guardians"
              actions={
                <button onClick={() => setShowAddGuardianModal(true)} className="btn btn-primary btn-sm">
                  <PlusIcon className="w-4 h-4" /> Add Guardian
                </button>
              }
            >
              <GuardiansList
                guardians={mappedGuardians}
                onAddGuardian={() => setShowAddGuardianModal(true)}
                onEditGuardian={(g) => {
                  const guardian = family.guardians.find(gu => gu.id === g.id);
                  if (guardian) setEditingGuardian(guardian);
                }}
                variant="detailed"
              />
            </ContentCard>
          )}

          {/* Billing Tab */}
          {activeTab === 'billing' && (
            <div className="space-y-6">
              <ContentCard title="Billing & Invoicing Settings">
                <div className="space-y-6">
                  {/* Toggle: Needs Invoice */}
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                    <div>
                      <h4 className="font-medium text-gray-900">Needs Invoice</h4>
                      <p className="text-sm text-gray-500">Enable to include this family in bulk invoicing</p>
                    </div>
                    <button
                      onClick={() => {
                        const newVal = !billingEnabled;
                        setBillingEnabled(newVal);
                        updateBilling({
                          variables: {
                            id: family.id,
                            isRecurringBilling: newVal,
                            recurringFundingSourceId: selectedFundingSource || null,
                            fileNumber: fileNumber || null,
                          },
                        });
                      }}
                      className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                        billingEnabled ? 'bg-green-500' : 'bg-gray-300'
                      }`}
                    >
                      <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition-transform ${
                        billingEnabled ? 'translate-x-6' : 'translate-x-1'
                      }`} />
                    </button>
                  </div>

                  {billingEnabled && (
                    <>
                      {/* Funding Source */}
                      <div className="space-y-2">
                        <label className="block text-sm font-medium text-gray-700">Funding Source</label>
                        <select
                          value={selectedFundingSource}
                          onChange={(e) => setSelectedFundingSource(e.target.value)}
                          className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent bg-white"
                        >
                          <option value="">-- Select Funding Source --</option>
                          {fundingSources.map((fs) => (
                            <option key={fs.id} value={fs.id}>{fs.name}</option>
                          ))}
                        </select>
                      </div>

                      {/* File Number */}
                      <div className="space-y-2">
                        <label className="block text-sm font-medium text-gray-700">File Number (for Income Support)</label>
                        <input
                          type="text"
                          value={fileNumber}
                          onChange={(e) => setFileNumber(e.target.value)}
                          placeholder="e.g. 1741315"
                          className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                        />
                      </div>

                      {/* Save Button */}
                      <div className="flex justify-end">
                        <button
                          onClick={() => {
                            updateBilling({
                              variables: {
                                id: family.id,
                                isRecurringBilling: billingEnabled,
                                recurringFundingSourceId: selectedFundingSource || null,
                                fileNumber: fileNumber || null,
                              },
                            });
                          }}
                          disabled={savingBilling}
                          className="btn btn-primary"
                        >
                          <BanknotesIcon className="w-4 h-4" />
                          {savingBilling ? 'Saving...' : 'Save Billing Settings'}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </ContentCard>

              {/* Additional Fees */}
              {billingEnabled && (
                <ContentCard title="Additional Fees">
                  <p className="text-sm text-gray-500 mb-4">Extra monthly charges for this family (registration, supplies, etc.)</p>

                  {/* Existing fees list */}
                  {localFees.length > 0 && (
                    <div className="space-y-2 mb-4">
                      {localFees.map((fee, index) => (
                        <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                          <span className="text-sm font-medium text-gray-800">{fee.description}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-sm font-mono font-semibold text-gray-700">${fee.amount.toFixed(2)}</span>
                            <button
                              onClick={() => {
                                const updated = localFees.filter((_, i) => i !== index);
                                setLocalFees(updated);
                                updateAdditionalFees({ variables: { id: family!.id, fees: updated } });
                              }}
                              className="text-red-400 hover:text-red-600 transition-colors"
                            >
                              <TrashIcon className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      ))}
                      <div className="flex justify-end pt-1">
                        <span className="text-sm font-semibold text-gray-700">
                          Total: <span className="font-mono">${localFees.reduce((s, f) => s + f.amount, 0).toFixed(2)}</span>
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Add new fee */}
                  <div className="flex items-end gap-3">
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                      <input
                        type="text"
                        value={newFeeDesc}
                        onChange={(e) => setNewFeeDesc(e.target.value)}
                        placeholder="e.g. Registration Fee"
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      />
                    </div>
                    <div className="w-28">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Amount</label>
                      <div className="relative">
                        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                        <input
                          type="number"
                          step="0.01"
                          value={newFeeAmount}
                          onChange={(e) => setNewFeeAmount(e.target.value)}
                          placeholder="0.00"
                          className="w-full pl-6 pr-2 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                        />
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        if (!newFeeDesc.trim() || !newFeeAmount) return;
                        const amount = parseFloat(newFeeAmount);
                        if (isNaN(amount) || amount <= 0) return;
                        const updated = [...localFees, { description: newFeeDesc.trim(), amount }];
                        setLocalFees(updated);
                        setNewFeeDesc('');
                        setNewFeeAmount('');
                        updateAdditionalFees({ variables: { id: family!.id, fees: updated } });
                      }}
                      disabled={savingFees}
                      className="px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
                    >
                      <PlusIcon className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Pricing settings link */}
                  <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-100 text-xs text-blue-700">
                    💡 Standard rates & parent portions are in <a href="/setup/pricing" className="text-primary-600 underline font-medium">Pricing Settings</a>
                  </div>
                </ContentCard>
              )}
            </div>
          )}

          {/* Consents Tab */}
          {activeTab === 'consents' && (
            <ContentCard title="Parental Consents">
              <div className="space-y-3">
                <ConsentItem label="Photo & Video Consent" granted={family.photo_consent} />
                <ConsentItem label="Field Trip Consent" granted={family.field_trip_consent} />
                <ConsentItem label="Emergency Medical Consent" granted={family.emergency_medical_consent} />
              </div>
            </ContentCard>
          )}

          {/* Notes Tab */}
          {activeTab === 'notes' && (
            <ContentCard
              title="Family Notes"
              actions={
                <button className="text-sm text-primary-600 hover:text-primary-700 font-medium">
                  Edit Notes
                </button>
              }
            >
              {family.additional_notes ? (
                <p className="text-gray-600 whitespace-pre-wrap">{family.additional_notes}</p>
              ) : (
                <p className="text-gray-400 italic">No notes added yet.</p>
              )}
            </ContentCard>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Contact Info */}
          <ContentCard title="Contact Information">
            <div className="space-y-4">
              {address && (
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                    <MapPinIcon className="w-4 h-4 text-gray-500" />
                  </div>
                  <p className="text-sm text-gray-600">{address}</p>
                </div>
              )}
              {primaryGuardian && (
                <>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                      <PhoneIcon className="w-4 h-4 text-gray-500" />
                    </div>
                    <a href={`tel:${primaryGuardian.cell_phone}`} className="text-sm text-gray-600 hover:text-primary-600">
                      {primaryGuardian.cell_phone}
                    </a>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                      <EnvelopeIcon className="w-4 h-4 text-gray-500" />
                    </div>
                    <a href={`mailto:${primaryGuardian.email}`} className="text-sm text-gray-600 hover:text-primary-600 truncate">
                      {primaryGuardian.email}
                    </a>
                  </div>
                </>
              )}
            </div>
          </ContentCard>

          {/* Emergency Contacts */}
          <ContentCard
            title="Emergency Contacts"
            actions={
              <button onClick={() => setShowAddContactModal(true)} className="text-sm text-primary-600 hover:text-primary-700 font-medium">
                + Add
              </button>
            }
          >
            {family.emergency_contacts.length > 0 ? (
              <div className="space-y-2">
                {family.emergency_contacts.map((contact) => (
                  <EmergencyContactCard
                    key={contact.id}
                    contact={contact}
                    onEdit={() => setEditingContact(contact)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 italic">No emergency contacts added.</p>
            )}
          </ContentCard>

          {/* Quick Stats */}
          <ContentCard title="Quick Stats">
            <div className="divide-y divide-gray-100">
              <QuickStat label="Total Children" value={family.children.length} />
              <QuickStat label="Active Children" value={family.children.filter(c => c.is_active).length} />
              <QuickStat label="Guardians" value={family.guardians.length} />
              <QuickStat label="Emergency Contacts" value={family.emergency_contacts.length} />
              <QuickStat label="Member Since" value={new Date(family.created_at).toLocaleDateString()} />
            </div>
          </ContentCard>
        </div>
      </div>

      {/* Modals */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteModal(false)}
        title="Delete Family"
        message={`Are you sure you want to delete ${family.name}? This will remove all associated children and records.`}
        confirmLabel="Delete"
        variant="danger"
        icon={<TrashIcon className="w-8 h-8 text-red-600" />}
      />

      <ConfirmModal
        isOpen={showDeactivateModal}
        onConfirm={handleDeactivate}
        onCancel={() => setShowDeactivateModal(false)}
        title="Deactivate Family"
        message={`Are you sure you want to deactivate ${family.name}? This will also deactivate all children.`}
        confirmLabel="Deactivate"
        variant="warning"
        icon={<PauseIcon className="w-8 h-8 text-amber-600" />}
      />

      <Modal
        isOpen={showEditNameModal}
        onClose={() => setShowEditNameModal(false)}
        title="Edit Family Name"
        size="sm"
      >
        <div className="space-y-4">
          <input
            type="text"
            value={editingName}
            onChange={(e) => setEditingName(e.target.value)}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            placeholder="Family name"
            autoFocus
          />
          <div className="flex justify-end gap-3">
            <button onClick={() => setShowEditNameModal(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button onClick={handleSaveName} disabled={updating || !editingName.trim()} className="btn btn-primary">
              {updating ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Edit Modals (using existing components) */}
      <EditGuardianModal
        isOpen={!!editingGuardian}
        onClose={() => setEditingGuardian(null)}
        guardian={editingGuardian}
        onSuccess={() => refetch()}
      />
      <EditChildModal
        isOpen={!!editingChild}
        onClose={() => setEditingChild(null)}
        child={editingChild}
        onSuccess={() => refetch()}
      />
      <EditEmergencyContactModal
        isOpen={!!editingContact}
        onClose={() => setEditingContact(null)}
        contact={editingContact}
        onSuccess={() => refetch()}
      />
      <AddEmergencyContactModal
        isOpen={showAddContactModal}
        onClose={() => setShowAddContactModal(false)}
        familyId={id || ''}
        onSuccess={() => refetch()}
      />
      <AddGuardianModal
        isOpen={showAddGuardianModal}
        onClose={() => setShowAddGuardianModal(false)}
        familyId={id || ''}
        onSuccess={() => refetch()}
        suggestedAddress={primaryGuardian ? {
          address: primaryGuardian.address,
          city: primaryGuardian.city,
          postalCode: primaryGuardian.postal_code,
        } : undefined}
      />
    </PageContainer>
  );
};

export default FamilyDetail;
