// ============================================
// Organization Settings View (Refactored)
// ============================================

import React, { useState, useRef, useEffect } from 'react';
import {
  BuildingOffice2Icon,
  PhotoIcon,
  TrashIcon,
  ArrowUpTrayIcon,
  MapPinIcon,
  ClockIcon,
  PhoneIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../../context/AuthContext';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { config } from '../../../config';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';
import type { Organization as OrganizationType } from '../../../types';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  SettingsSubsection,
  SettingsTabs,
  SettingsLoadingSkeleton,
  StatusBadge,
} from '../components';

// -------------------- Types --------------------

interface OrganizationDetails {
  id: string;
  name: string;
  organization_type: string;
  status: string;
  primary_contact_name: string;
  email: string;
  phone: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
  license_number: string;
  licensed_capacity: number;
  opening_time: string;
  closing_time: string;
  age_groups_served: string[];
  logo_url?: string;
  website?: string;
  secondary_contact_name?: string;
  secondary_contact_phone?: string;
  secondary_contact_email?: string;
  business_number?: string;
  description?: string;
  programs_offered: string[];
  billing_email?: string;
  timezone?: string;
  subscription_plan: string;
  trial_ends_at?: string;
  email_verified: boolean;
  license_verified: boolean;
}

interface FormData {
  name: string;
  primary_contact_name: string;
  phone: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
  opening_time: string;
  closing_time: string;
  website: string;
  secondary_contact_name: string;
  secondary_contact_phone: string;
  secondary_contact_email: string;
  description: string;
  billing_email: string;
}

const DEFAULT_FORM: FormData = {
  name: '',
  primary_contact_name: '',
  phone: '',
  street_address: '',
  city: '',
  province: '',
  postal_code: '',
  country: '',
  opening_time: '',
  closing_time: '',
  website: '',
  secondary_contact_name: '',
  secondary_contact_phone: '',
  secondary_contact_email: '',
  description: '',
  billing_email: '',
};

type TabType = 'profile' | 'contact' | 'location' | 'operations';

const tabs = [
  { id: 'profile' as TabType, name: 'Profile', icon: BuildingOffice2Icon },
  { id: 'contact' as TabType, name: 'Contact', icon: PhoneIcon },
  { id: 'location' as TabType, name: 'Location', icon: MapPinIcon },
  { id: 'operations' as TabType, name: 'Operations', icon: ClockIcon },
];

const Organization: React.FC = () => {
  const { state, setOrganization } = useAuth();
  const organization = state.organization;
  const { addNotification } = useNotifications();
  const [activeTab, setActiveTab] = useState<TabType>('profile');
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<FormData>(DEFAULT_FORM);

  // Logo state
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [updating, setUpdating] = useState(false);

  // Queries
  const { data: currentOrganization, loading: loadingOrg, refetch } = useApiQuery<OrganizationDetails>('/organization');
  const orgDetails = currentOrganization || (organization as OrganizationDetails | undefined);

  // Populate form when data loads
  useEffect(() => {
    if (orgDetails) {
      setFormData({
        name: orgDetails.name || '',
        primary_contact_name: orgDetails.primary_contact_name || '',
        phone: orgDetails.phone || '',
        street_address: orgDetails.street_address || '',
        city: orgDetails.city || '',
        province: orgDetails.province || '',
        postal_code: orgDetails.postal_code || '',
        country: orgDetails.country || '',
        opening_time: orgDetails.opening_time || '',
        closing_time: orgDetails.closing_time || '',
        website: orgDetails.website || '',
        secondary_contact_name: orgDetails.secondary_contact_name || '',
        secondary_contact_phone: orgDetails.secondary_contact_phone || '',
        secondary_contact_email: orgDetails.secondary_contact_email || '',
        description: orgDetails.description || '',
        billing_email: orgDetails.billing_email || '',
      });
    }
  }, [orgDetails]);

  // Handlers
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSave = async () => {
    if (!orgDetails?.id) return;
    try {
      setUpdating(true);
      const updated = await api.patch<OrganizationType>('/organization', formData);
      setOrganization(updated);
      setIsEditing(false);
      await refetch();
      addNotification({ type: 'success', title: 'Organization Updated', message: 'Your organization profile has been updated successfully.' });
    } catch (error) {
      addNotification({ type: 'error', title: 'Update Failed', message: error instanceof Error ? error.message : 'Request failed' });
    } finally {
      setUpdating(false);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    if (orgDetails) {
      setFormData({
        name: orgDetails.name || '',
        primary_contact_name: orgDetails.primary_contact_name || '',
        phone: orgDetails.phone || '',
        street_address: orgDetails.street_address || '',
        city: orgDetails.city || '',
        province: orgDetails.province || '',
        postal_code: orgDetails.postal_code || '',
        country: orgDetails.country || '',
        opening_time: orgDetails.opening_time || '',
        closing_time: orgDetails.closing_time || '',
        website: orgDetails.website || '',
        secondary_contact_name: orgDetails.secondary_contact_name || '',
        secondary_contact_phone: orgDetails.secondary_contact_phone || '',
        secondary_contact_email: orgDetails.secondary_contact_email || '',
        description: orgDetails.description || '',
        billing_email: orgDetails.billing_email || '',
      });
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'];
    if (!allowedTypes.includes(file.type)) {
      addNotification({ type: 'error', title: 'Invalid File Type', message: 'Please upload a JPG, PNG, GIF, WebP, or SVG image.' });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      addNotification({ type: 'error', title: 'File Too Large', message: 'Please upload an image smaller than 5MB.' });
      return;
    }

    setSelectedFile(file);
    const reader = new FileReader();
    reader.onloadend = () => setPreviewUrl(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    try {
      setUploading(true);
      const updated = await api.upload<OrganizationType>('/organization/logo', selectedFile);
      setOrganization(updated);
      setPreviewUrl(null);
      setSelectedFile(null);
      await refetch();
      addNotification({ type: 'success', title: 'Logo Updated', message: 'Your organization logo has been updated successfully.' });
    } catch (error) {
      addNotification({ type: 'error', title: 'Upload Failed', message: error instanceof Error ? error.message : 'Request failed' });
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async () => {
    if (!organization?.logo_url) return;
    if (window.confirm('Are you sure you want to remove your organization logo?')) {
      try {
        setRemoving(true);
        await api.delete('/organization/logo');
        const updated = await api.get<OrganizationType>('/organization');
        setOrganization(updated);
        await refetch();
        addNotification({ type: 'success', title: 'Logo Removed', message: 'Your organization logo has been removed.' });
      } catch (error) {
        addNotification({ type: 'error', title: 'Remove Failed', message: error instanceof Error ? error.message : 'Request failed' });
      } finally {
        setRemoving(false);
      }
    }
  };

  const cancelPreview = () => {
    setPreviewUrl(null);
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const currentLogoUrl = organization?.logo_url ? config.getUploadUrl(organization.logo_url) : null;

  if (loadingOrg) {
    return (
      <SettingsPageLayout title="Organization Settings" description="Loading...">
        <SettingsLoadingSkeleton />
      </SettingsPageLayout>
    );
  }

  return (
    <SettingsPageLayout
      title="Organization Settings"
      description="Manage your organization's profile, contact info, and operations."
      actions={
        !isEditing ? (
          <button onClick={() => setIsEditing(true)} className="btn btn-primary">Edit Profile</button>
        ) : (
          <div className="flex gap-3">
            <button onClick={handleCancel} disabled={updating} className="btn btn-secondary">Cancel</button>
            <button onClick={handleSave} disabled={updating} className="btn btn-primary">{updating ? 'Saving...' : 'Save Changes'}</button>
          </div>
        )
      }
    >
      <SettingsTabs tabs={tabs} activeTab={activeTab} onTabChange={(id) => setActiveTab(id as TabType)} />

      <SettingsSection>
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <ProfileTab
            orgDetails={orgDetails}
            formData={formData}
            isEditing={isEditing}
            onChange={handleInputChange}
            currentLogoUrl={currentLogoUrl}
            previewUrl={previewUrl}
            fileInputRef={fileInputRef}
            onFileSelect={handleFileSelect}
            onUpload={handleUpload}
            onRemove={handleRemove}
            onCancelPreview={cancelPreview}
            uploading={uploading}
            removing={removing}
          />
        )}

        {/* Contact Tab */}
        {activeTab === 'contact' && (
          <ContactTab orgDetails={orgDetails} formData={formData} isEditing={isEditing} onChange={handleInputChange} />
        )}

        {/* Location Tab */}
        {activeTab === 'location' && (
          <LocationTab orgDetails={orgDetails} formData={formData} isEditing={isEditing} onChange={handleInputChange} />
        )}

        {/* Operations Tab */}
        {activeTab === 'operations' && (
          <OperationsTab orgDetails={orgDetails} formData={formData} isEditing={isEditing} onChange={handleInputChange} />
        )}
      </SettingsSection>
    </SettingsPageLayout>
  );
};

// -------------------- Profile Tab --------------------

interface ProfileTabProps {
  orgDetails?: OrganizationDetails;
  formData: FormData;
  isEditing: boolean;
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  currentLogoUrl: string | null;
  previewUrl: string | null;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onUpload: () => void;
  onRemove: () => void;
  onCancelPreview: () => void;
  uploading: boolean;
  removing: boolean;
}

const ProfileTab: React.FC<ProfileTabProps> = ({
  orgDetails,
  formData,
  isEditing,
  onChange,
  currentLogoUrl,
  previewUrl,
  fileInputRef,
  onFileSelect,
  onUpload,
  onRemove,
  onCancelPreview,
  uploading,
  removing,
}) => (
  <div>
    <h3 className="text-lg font-semibold text-gray-900 mb-6">Organization Profile</h3>

    {/* Logo Section */}
    <div className="mb-8">
      <label className="block text-sm font-medium text-gray-700 mb-4">Organization Logo</label>
      <div className="flex items-start gap-6">
        <div className="flex-shrink-0">
          <div className="w-24 h-24 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center overflow-hidden bg-gray-50">
            {previewUrl ? (
              <img src={previewUrl} alt="Preview" className="w-full h-full object-contain" />
            ) : currentLogoUrl ? (
              <img src={currentLogoUrl} alt="Logo" className="w-full h-full object-contain" />
            ) : (
              <PhotoIcon className="h-10 w-10 text-gray-400" />
            )}
          </div>
        </div>
        <div className="flex-1">
          <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/gif,image/webp,image/svg+xml" onChange={onFileSelect} className="hidden" />
          {!previewUrl ? (
            <div className="flex items-center gap-3">
              <button onClick={() => fileInputRef.current?.click()} className="btn btn-secondary btn-sm">
                <ArrowUpTrayIcon className="h-4 w-4" /> Upload
              </button>
              {currentLogoUrl && (
                <button onClick={onRemove} disabled={removing} className="btn btn-ghost btn-sm text-red-600">
                  <TrashIcon className="h-4 w-4" /> {removing ? 'Removing...' : 'Remove'}
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <button onClick={onUpload} disabled={uploading} className="btn btn-primary btn-sm">{uploading ? 'Uploading...' : 'Save Logo'}</button>
              <button onClick={onCancelPreview} disabled={uploading} className="btn btn-secondary btn-sm">Cancel</button>
            </div>
          )}
          <p className="mt-2 text-xs text-gray-500">JPG, PNG, GIF, WebP, or SVG. Max 5MB.</p>
        </div>
      </div>
    </div>

    {/* Basic Info */}
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <EditableField label="Organization Name" name="name" value={formData.name} displayValue={orgDetails?.name} isEditing={isEditing} onChange={onChange} />
      <DisplayField label="Organization Type" value={orgDetails?.organization_type?.replace('_', ' ')} capitalize />
      <div className="md:col-span-2">
        <EditableTextarea label="Description" name="description" value={formData.description} displayValue={orgDetails?.description || 'No description'} isEditing={isEditing} onChange={onChange} placeholder="Brief description of your organization..." />
      </div>
      <EditableField label="Website" name="website" value={formData.website} displayValue={orgDetails?.website} isEditing={isEditing} onChange={onChange} type="url" placeholder="https://example.com" />
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
        <StatusBadge status={orgDetails?.status === 'active' ? 'active' : 'pending'} label={orgDetails?.status || 'Unknown'} />
      </div>
    </div>

    {/* License Info */}
    <SettingsSubsection title="License Information" className="mt-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <DisplayField label="License Number" value={orgDetails?.license_number} />
        <DisplayField label="Licensed Capacity" value={orgDetails?.licensed_capacity ? `${orgDetails.licensed_capacity} children` : undefined} />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">License Verified</label>
          <StatusBadge status={orgDetails?.license_verified ? 'active' : 'pending'} label={orgDetails?.license_verified ? 'Verified' : 'Pending'} />
        </div>
      </div>
    </SettingsSubsection>
  </div>
);

// -------------------- Contact Tab --------------------

interface TabProps {
  orgDetails?: OrganizationDetails;
  formData: FormData;
  isEditing: boolean;
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
}

const ContactTab: React.FC<TabProps> = ({ orgDetails, formData, isEditing, onChange }) => (
  <div>
    <h3 className="text-lg font-semibold text-gray-900 mb-6">Contact Information</h3>

    <div className="mb-8">
      <h4 className="text-md font-medium text-gray-900 mb-4 flex items-center gap-2">
        <UserGroupIcon className="h-5 w-5 text-gray-500" /> Primary Contact
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <EditableField label="Contact Name" name="primary_contact_name" value={formData.primary_contact_name} displayValue={orgDetails?.primary_contact_name} isEditing={isEditing} onChange={onChange} />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <p className="text-gray-900 py-2">{orgDetails?.email || '-'}</p>
          <p className="text-xs text-gray-500">Email cannot be changed</p>
        </div>
        <EditableField label="Phone" name="phone" value={formData.phone} displayValue={orgDetails?.phone} isEditing={isEditing} onChange={onChange} type="tel" />
        <EditableField label="Billing Email" name="billing_email" value={formData.billing_email} displayValue={orgDetails?.billing_email} isEditing={isEditing} onChange={onChange} type="email" placeholder="billing@example.com" />
      </div>
    </div>

    <SettingsSubsection title="Secondary Contact (Optional)">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <EditableField label="Name" name="secondary_contact_name" value={formData.secondary_contact_name} displayValue={orgDetails?.secondary_contact_name} isEditing={isEditing} onChange={onChange} />
        <EditableField label="Phone" name="secondary_contact_phone" value={formData.secondary_contact_phone} displayValue={orgDetails?.secondary_contact_phone} isEditing={isEditing} onChange={onChange} type="tel" />
        <EditableField label="Email" name="secondary_contact_email" value={formData.secondary_contact_email} displayValue={orgDetails?.secondary_contact_email} isEditing={isEditing} onChange={onChange} type="email" />
      </div>
    </SettingsSubsection>
  </div>
);

// -------------------- Location Tab --------------------

const LocationTab: React.FC<TabProps> = ({ orgDetails, formData, isEditing, onChange }) => (
  <div>
    <h3 className="text-lg font-semibold text-gray-900 mb-6">Location</h3>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div className="md:col-span-2">
        <EditableField label="Street Address" name="street_address" value={formData.street_address} displayValue={orgDetails?.street_address} isEditing={isEditing} onChange={onChange} />
      </div>
      <EditableField label="City" name="city" value={formData.city} displayValue={orgDetails?.city} isEditing={isEditing} onChange={onChange} />
      <EditableField label="Province/State" name="province" value={formData.province} displayValue={orgDetails?.province} isEditing={isEditing} onChange={onChange} />
      <EditableField label="Postal Code" name="postal_code" value={formData.postal_code} displayValue={orgDetails?.postal_code} isEditing={isEditing} onChange={onChange} />
      <EditableField label="Country" name="country" value={formData.country} displayValue={orgDetails?.country} isEditing={isEditing} onChange={onChange} />
    </div>
  </div>
);

// -------------------- Operations Tab --------------------

const OperationsTab: React.FC<TabProps> = ({ orgDetails, formData, isEditing, onChange }) => (
  <div>
    <h3 className="text-lg font-semibold text-gray-900 mb-6">Operations</h3>

    <div className="mb-8">
      <h4 className="text-md font-medium text-gray-900 mb-4 flex items-center gap-2">
        <ClockIcon className="h-5 w-5 text-gray-500" /> Operating Hours
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <EditableField label="Opening Time" name="opening_time" value={formData.opening_time} displayValue={orgDetails?.opening_time} isEditing={isEditing} onChange={onChange} type="time" />
        <EditableField label="Closing Time" name="closing_time" value={formData.closing_time} displayValue={orgDetails?.closing_time} isEditing={isEditing} onChange={onChange} type="time" />
      </div>
    </div>

    <SettingsSubsection title="Age Groups Served">
      <div className="flex flex-wrap gap-2">
        {orgDetails?.age_groups_served?.length ? (
          orgDetails.age_groups_served.map((group, idx) => (
            <span key={idx} className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-primary-100 text-primary-800">{group}</span>
          ))
        ) : (
          <p className="text-gray-500">No age groups specified</p>
        )}
      </div>
    </SettingsSubsection>

    <SettingsSubsection title="Programs Offered" className="pt-6">
      <div className="flex flex-wrap gap-2">
        {orgDetails?.programs_offered?.length ? (
          orgDetails.programs_offered.map((program, idx) => (
            <span key={idx} className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-gray-100 text-gray-800">{program}</span>
          ))
        ) : (
          <p className="text-gray-500">No programs specified</p>
        )}
      </div>
    </SettingsSubsection>

    <SettingsSubsection title="Subscription" className="pt-6 mt-8">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Current Plan</label>
          <span className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-primary-100 text-primary-800 font-medium capitalize">
            {orgDetails?.subscription_plan || 'Free'}
          </span>
        </div>
        {orgDetails?.trial_ends_at && (
          <DisplayField label="Trial Ends" value={new Date(orgDetails.trial_ends_at).toLocaleDateString()} />
        )}
      </div>
    </SettingsSubsection>
  </div>
);

// -------------------- Helper Components --------------------

interface EditableFieldProps {
  label: string;
  name: string;
  value: string;
  displayValue?: string;
  isEditing: boolean;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  placeholder?: string;
}

const EditableField: React.FC<EditableFieldProps> = ({ label, name, value, displayValue, isEditing, onChange, type = 'text', placeholder }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    {isEditing ? (
      <input type={type} name={name} value={value} onChange={onChange} className="input" placeholder={placeholder} />
    ) : (
      <p className="text-gray-900 py-2">{displayValue || '-'}</p>
    )}
  </div>
);

interface EditableTextareaProps {
  label: string;
  name: string;
  value: string;
  displayValue?: string;
  isEditing: boolean;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  rows?: number;
}

const EditableTextarea: React.FC<EditableTextareaProps> = ({ label, name, value, displayValue, isEditing, onChange, placeholder, rows = 3 }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    {isEditing ? (
      <textarea name={name} value={value} onChange={onChange} rows={rows} className="input" placeholder={placeholder} />
    ) : (
      <p className="text-gray-900 py-2">{displayValue || '-'}</p>
    )}
  </div>
);

interface DisplayFieldProps {
  label: string;
  value?: string | number;
  capitalize?: boolean;
}

const DisplayField: React.FC<DisplayFieldProps> = ({ label, value, capitalize }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    <p className={`text-gray-900 py-2 ${capitalize ? 'capitalize' : ''}`}>{value || '-'}</p>
  </div>
);

export default Organization;
