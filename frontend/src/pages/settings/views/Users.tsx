// ============================================
// User Management View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  UserPlusIcon,
  UserGroupIcon,
  XMarkIcon,
  NoSymbolIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  FormInput,
  FormSelect,
  SettingsLoadingSpinner,
  StatusBadge,
  SettingsEmptyState,
} from '../components';

// -------------------- Types --------------------

interface Role {
  id: number;
  name: string;
  description?: string;
}

interface TeamMember {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

interface InviteFormData {
  email: string;
  first_name: string;
  last_name: string;
  role_id: number;
}

const Users: React.FC = () => {
  const { addNotification } = useNotifications();
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteForm, setInviteForm] = useState<InviteFormData>({
    email: '',
    first_name: '',
    last_name: '',
    role_id: 0,
  });
  const [inviting, setInviting] = useState(false);

  // Queries
  const { data: teamMembers = [], loading: loadingUsers, refetch } = useApiQuery<TeamMember[]>('/auth/users');
  const { data: roles = [] } = useApiQuery<Role[]>('/auth/roles');

  const handleInvite = async () => {
    if (!inviteForm.email || !inviteForm.role_id) {
      addNotification({ type: 'error', title: 'Missing Fields', message: 'Email and role are required.' });
      return;
    }
    try {
      setInviting(true);
      await api.post('/auth/users', inviteForm);
      setShowInviteModal(false);
      setInviteForm({ email: '', first_name: '', last_name: '', role_id: 0 });
      await refetch();
      addNotification({ type: 'success', title: 'User Created', message: 'The team member account was created.' });
    } catch (error) {
      addNotification({ type: 'error', title: 'Invitation Failed', message: error instanceof Error ? error.message : 'Request failed' });
    } finally {
      setInviting(false);
    }
  };

  const handleDeactivate = async (userId: string, name: string) => {
    if (confirm(`Deactivate ${name}? They will no longer be able to access the system.`)) {
      try {
        await api.patch(`/auth/users/${userId}`, { is_active: false });
        await refetch();
        addNotification({ type: 'success', title: 'User Deactivated', message: 'The user has been deactivated.' });
      } catch (error) {
        addNotification({ type: 'error', title: 'Action Failed', message: error instanceof Error ? error.message : 'Request failed' });
      }
    }
  };

  const handleReactivate = async (userId: string) => {
    try {
      await api.patch(`/auth/users/${userId}`, { is_active: true });
      await refetch();
      addNotification({ type: 'success', title: 'User Reactivated', message: 'The user has been reactivated.' });
    } catch (error) {
      addNotification({ type: 'error', title: 'Action Failed', message: error instanceof Error ? error.message : 'Request failed' });
    }
  };

  const handleRoleChange = async (userId: string, roleId: number) => {
    try {
      await api.patch(`/auth/users/${userId}`, { role_id: roleId });
      await refetch();
      addNotification({ type: 'success', title: 'Role Updated', message: 'The user\'s role has been updated.' });
    } catch (error) {
      addNotification({ type: 'error', title: 'Action Failed', message: error instanceof Error ? error.message : 'Request failed' });
    }
  };

  if (loadingUsers) {
    return (
      <SettingsPageLayout title="User Management" description="Loading...">
        <SettingsLoadingSpinner />
      </SettingsPageLayout>
    );
  }

  return (
    <SettingsPageLayout
      title="User Management"
      description="Invite team members and manage their access."
      actions={
        <button onClick={() => setShowInviteModal(true)} className="btn btn-primary">
          <UserPlusIcon className="w-4 h-4" /> Invite User
        </button>
      }
    >
      <SettingsSection>
        {/* Team Stats */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <UserGroupIcon className="h-5 w-5" />
            <span>{teamMembers.length} team member{teamMembers.length !== 1 ? 's' : ''}</span>
          </div>
        </div>

        {/* Team Members List */}
        {teamMembers.length === 0 ? (
          <SettingsEmptyState
            icon={UserGroupIcon}
            title="No team members yet"
            description="Invite your first team member to get started"
            action={{ label: 'Invite User', onClick: () => setShowInviteModal(true) }}
          />
        ) : (
          <div className="space-y-3">
            {teamMembers.map((member) => (
              <TeamMemberRow
                key={member.id}
                member={member}
                roles={roles}
                onDeactivate={handleDeactivate}
                onReactivate={handleReactivate}
                onRoleChange={handleRoleChange}
              />
            ))}
          </div>
        )}
      </SettingsSection>

      {/* Invite Modal */}
      {showInviteModal && (
        <InviteModal
          form={inviteForm}
          setForm={setInviteForm}
          roles={roles}
          inviting={inviting}
          onInvite={handleInvite}
          onClose={() => setShowInviteModal(false)}
        />
      )}
    </SettingsPageLayout>
  );
};

// -------------------- Team Member Row --------------------

interface TeamMemberRowProps {
  member: TeamMember;
  roles: Role[];
  onDeactivate: (userId: string, name: string) => void;
  onReactivate: (userId: string) => void;
  onRoleChange: (userId: string, roleId: number) => void;
}

const TeamMemberRow: React.FC<TeamMemberRowProps> = ({
  member,
  roles,
  onDeactivate,
  onReactivate,
  onRoleChange,
}) => {
  const name = `${member.first_name} ${member.last_name}`.trim() || member.email;

  return (
    <div className={`flex items-center justify-between p-4 rounded-lg border ${member.is_active ? 'bg-white border-gray-200' : 'bg-gray-50 border-gray-200'}`}>
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center">
          <span className="text-primary-700 font-medium">
            {member.first_name?.[0] || member.email[0].toUpperCase()}
          </span>
        </div>
        <div>
          <p className="font-medium text-gray-900">{name}</p>
          <p className="text-sm text-gray-500">{member.email}</p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <select
          value={member.role.id}
          onChange={(e) => onRoleChange(member.id, parseInt(e.target.value))}
          disabled={!member.is_active}
          className="input input-sm w-32"
        >
          {roles.map((role) => (
            <option key={role.id} value={role.id}>{role.name}</option>
          ))}
        </select>
        <StatusBadge status={member.is_active ? 'active' : 'inactive'} />
        {member.is_active ? (
          <button onClick={() => onDeactivate(member.id, name)} className="btn btn-ghost btn-sm text-red-600" title="Deactivate">
            <NoSymbolIcon className="w-4 h-4" />
          </button>
        ) : (
          <button onClick={() => onReactivate(member.id)} className="btn btn-ghost btn-sm text-green-600" title="Reactivate">
            <ArrowPathIcon className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};

// -------------------- Invite Modal --------------------

interface InviteModalProps {
  form: InviteFormData;
  setForm: React.Dispatch<React.SetStateAction<InviteFormData>>;
  roles: Role[];
  inviting: boolean;
  onInvite: () => void;
  onClose: () => void;
}

const InviteModal: React.FC<InviteModalProps> = ({
  form,
  setForm,
  roles,
  inviting,
  onInvite,
  onClose,
}) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold">Invite Team Member</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-4">
        <FormInput
          label="Email Address"
          type="email"
          value={form.email}
          onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          placeholder="colleague@company.com"
          required
        />
        <div className="grid grid-cols-2 gap-4">
          <FormInput
            label="First Name"
            value={form.first_name}
            onChange={(e) => setForm((p) => ({ ...p, first_name: e.target.value }))}
            placeholder="John"
          />
          <FormInput
            label="Last Name"
            value={form.last_name}
            onChange={(e) => setForm((p) => ({ ...p, last_name: e.target.value }))}
            placeholder="Doe"
          />
        </div>
        <FormSelect
          label="Role"
          value={form.role_id}
          onChange={(e) => setForm((p) => ({ ...p, role_id: parseInt(e.target.value) }))}
          options={[{ value: '0', label: 'Select a role...' }, ...roles.map((r) => ({ value: r.id.toString(), label: r.name }))]}
          required
        />
      </div>

      <div className="flex justify-end gap-3 mt-6 pt-6 border-t border-gray-200">
        <button onClick={onClose} className="btn btn-secondary">Cancel</button>
        <button onClick={onInvite} disabled={inviting} className="btn btn-primary">
          {inviting ? 'Sending...' : 'Send Invite'}
        </button>
      </div>
    </div>
  </div>
);

export default Users;
