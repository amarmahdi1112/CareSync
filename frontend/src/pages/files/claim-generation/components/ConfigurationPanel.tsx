import React, { useState } from 'react';
import {
  CalendarDaysIcon,
  UserGroupIcon,
  ClockIcon,
  AcademicCapIcon,
  PlusIcon,
  TrashIcon,
  BuildingOffice2Icon,
  BookmarkIcon,
  FolderOpenIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import { api } from '../../../../api/client';
import { useApiQuery } from '../../../../api/hooks';
import { useNotificationStore } from '../../../../stores/notificationStore';
import type { ClaimConfig, OrganizationData } from '../types';

interface SavedConfiguration {
  id: string;
  name: string;
  description?: string;
  isDefault: boolean;
  capacity: number;
  operatingHours: number;
  hourTiers: {
    fullTimeMonthlyTarget: number;
    schoolAgeFullDayTarget: number;
    schoolAgePartDayTarget: number;
  };
  schoolBreakPeriods: Array<{ name: string; start: string; end: string }>;
  behavioralProfiles: {
    consistent: { probability: number; variance: number };
    variable: { probability: number; variance: number };
    oftenAbsent: { probability: number; variance: number };
  };
}

interface ConfigurationPanelProps {
  config: ClaimConfig;
  setConfig: React.Dispatch<React.SetStateAction<ClaimConfig>>;
  reportName: string;
  setReportName: React.Dispatch<React.SetStateAction<string>>;
  organization?: OrganizationData;
}

const ConfigurationPanel: React.FC<ConfigurationPanelProps> = ({
  config,
  setConfig,
  reportName,
  setReportName,
  organization,
}) => {
  const { success, error: showError } = useNotificationStore();
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [configName, setConfigName] = useState('');
  const [configDescription, setConfigDescription] = useState('');
  const [setAsDefault, setSetAsDefault] = useState(false);
  const [saving, setSaving] = useState(false);

  // Fetch saved configurations
  type ConfigurationRow = {
    id: string; name: string; description?: string; is_default: boolean; capacity: number;
    operating_hours: number; hour_tiers: SavedConfiguration['hourTiers'];
    school_break_periods: SavedConfiguration['schoolBreakPeriods'];
    behavioral_profiles: SavedConfiguration['behavioralProfiles'];
  };
  const { data: configurationRows = [], refetch: refetchConfigs } = useApiQuery<ConfigurationRow[]>('/resources/claim_generation_configurations', { limit: 1000, sort: 'created_at', order: 'desc' });
  const savedConfigs: SavedConfiguration[] = configurationRows.map((row) => ({
    id: row.id,
    name: row.name,
    description: row.description,
    isDefault: row.is_default,
    capacity: row.capacity,
    operatingHours: Number(row.operating_hours),
    hourTiers: row.hour_tiers,
    schoolBreakPeriods: row.school_break_periods || [],
    behavioralProfiles: row.behavioral_profiles,
  }));

  const handleSaveConfig = async () => {
    if (!configName.trim()) {
      showError('Name Required', 'Please enter a name for this configuration');
      return;
    }
    try {
      setSaving(true);
      await api.resources.create('claim_generation_configurations', {
        name: configName,
        description: configDescription || undefined,
        is_default: setAsDefault,
        capacity: config.capacity,
        operating_hours: config.operatingHours,
        hour_tiers: config.hourTiers,
        school_break_periods: config.schoolBreakPeriods,
        behavioral_profiles: config.behavioralProfiles,
      });
      success('Configuration Saved', 'Your configuration has been saved');
      setShowSaveModal(false);
      setConfigName('');
      setConfigDescription('');
      setSetAsDefault(false);
      await refetchConfigs();
    } catch (err) {
      showError('Save Failed', err instanceof Error ? err.message : 'Request failed');
    } finally {
      setSaving(false);
    }
  };

  const handleLoadConfig = (saved: SavedConfiguration) => {
    // Strip __typename from Apollo response objects
    setConfig(prev => ({
      ...prev,
      capacity: saved.capacity,
      operatingHours: saved.operatingHours,
      hourTiers: {
        fullTimeMonthlyTarget: saved.hourTiers.fullTimeMonthlyTarget,
        schoolAgeFullDayTarget: saved.hourTiers.schoolAgeFullDayTarget,
        schoolAgePartDayTarget: saved.hourTiers.schoolAgePartDayTarget,
      },
      schoolBreakPeriods: saved.schoolBreakPeriods.map(p => ({
        name: p.name,
        start: p.start,
        end: p.end,
      })),
      behavioralProfiles: {
        consistent: {
          probability: saved.behavioralProfiles.consistent.probability,
          variance: saved.behavioralProfiles.consistent.variance,
        },
        variable: {
          probability: saved.behavioralProfiles.variable.probability,
          variance: saved.behavioralProfiles.variable.variance,
        },
        oftenAbsent: {
          probability: saved.behavioralProfiles.oftenAbsent.probability,
          variance: saved.behavioralProfiles.oftenAbsent.variance,
        },
      },
    }));
    success('Configuration Loaded', `Loaded "${saved.name}"`);
  };
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const years = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i);

  const addSchoolBreak = () => {
    setConfig(prev => ({
      ...prev,
      schoolBreakPeriods: [
        ...prev.schoolBreakPeriods,
        { start: '', end: '', name: '' }
      ]
    }));
  };

  const removeSchoolBreak = (index: number) => {
    setConfig(prev => ({
      ...prev,
      schoolBreakPeriods: prev.schoolBreakPeriods.filter((_, i) => i !== index)
    }));
  };

  const updateSchoolBreak = (index: number, field: 'start' | 'end' | 'name', value: string) => {
    setConfig(prev => ({
      ...prev,
      schoolBreakPeriods: prev.schoolBreakPeriods.map((period, i) =>
        i === index ? { ...period, [field]: value } : period
      )
    }));
  };

  return (
    <div className="space-y-6">
      {/* Saved Configurations Bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center space-x-4 flex-1">
            <FolderOpenIcon className="h-5 w-5 text-gray-400" />
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Load Saved Configuration
              </label>
              <select
                className="input w-full max-w-xs"
                onChange={(e) => {
                  const selected = savedConfigs.find(c => c.id === e.target.value);
                  if (selected) handleLoadConfig(selected);
                }}
                defaultValue=""
              >
                <option value="" disabled>Select a saved configuration...</option>
                {savedConfigs.map(c => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.isDefault ? '⭐ (Default)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            onClick={() => setShowSaveModal(true)}
            className="btn btn-secondary flex items-center space-x-2"
          >
            <BookmarkIcon className="h-4 w-4" />
            <span>Save Current Config</span>
          </button>
        </div>
        {savedConfigs.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {savedConfigs.slice(0, 5).map(c => (
              <button
                key={c.id}
                onClick={() => handleLoadConfig(c)}
                className={`inline-flex items-center px-3 py-1.5 rounded-full text-sm transition-colors ${
                  c.isDefault
                    ? 'bg-primary-100 text-primary-700 hover:bg-primary-200'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {c.isDefault && <StarIconSolid className="h-3 w-3 mr-1 text-primary-500" />}
                {c.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Save Configuration Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Save Configuration</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Configuration Name *
                </label>
                <input
                  type="text"
                  value={configName}
                  onChange={(e) => setConfigName(e.target.value)}
                  className="input w-full"
                  placeholder="e.g., Winter Schedule"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description (optional)
                </label>
                <textarea
                  value={configDescription}
                  onChange={(e) => setConfigDescription(e.target.value)}
                  className="input w-full"
                  rows={2}
                  placeholder="Brief description of this configuration"
                />
              </div>
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={setAsDefault}
                  onChange={(e) => setSetAsDefault(e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Set as default configuration</span>
              </label>
            </div>
            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowSaveModal(false)}
                className="btn btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveConfig}
                disabled={saving}
                className="btn btn-primary"
              >
                {saving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Left Column - Basic Config */}
      <div className="space-y-6">
        {/* Report Name */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Report Details</h3>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Report Name
            </label>
            <input
              type="text"
              value={reportName}
              onChange={(e) => setReportName(e.target.value)}
              className="input w-full"
              placeholder="Enter report name"
            />
          </div>
        </div>

        {/* Time Period */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center space-x-2 mb-4">
            <CalendarDaysIcon className="h-5 w-5 text-primary-500" />
            <h3 className="text-lg font-semibold text-gray-900">Time Period</h3>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Month</label>
              <select
                value={config.month}
                onChange={(e) => setConfig(prev => ({ ...prev, month: parseInt(e.target.value) }))}
                className="input w-full"
              >
                {months.map((month, idx) => (
                  <option key={idx} value={idx + 1}>{month}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Year</label>
              <select
                value={config.year}
                onChange={(e) => setConfig(prev => ({ ...prev, year: parseInt(e.target.value) }))}
                className="input w-full"
              >
                {years.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Organization Info - From Settings */}
        {organization && (
          <div className="bg-gradient-to-r from-primary-50 to-blue-50 rounded-xl border border-primary-200 p-6">
            <div className="flex items-center space-x-2 mb-4">
              <BuildingOffice2Icon className="h-5 w-5 text-primary-600" />
              <h3 className="text-lg font-semibold text-gray-900">Organization Settings</h3>
              <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">Auto-loaded</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">
                  Licensed Capacity
                </label>
                <div className="flex items-center space-x-2">
                  <span className="text-2xl font-bold text-gray-900">{config.capacity}</span>
                  <span className="text-sm text-gray-500">children</span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">
                  Operating Hours
                </label>
                <div className="flex items-center space-x-2">
                  <span className="text-2xl font-bold text-gray-900">{config.operatingHours}</span>
                  <span className="text-sm text-gray-500">hrs/day</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {organization.opening_time} - {organization.closing_time}
                </p>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-4 flex items-center">
              <span className="mr-1">💡</span>
              These values come from your organization settings. Edit them in Settings → Organization.
            </p>
          </div>
        )}

        {/* Manual Capacity - Only show if no org data */}
        {!organization && (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center space-x-2 mb-4">
              <UserGroupIcon className="h-5 w-5 text-primary-500" />
              <h3 className="text-lg font-semibold text-gray-900">Capacity Settings</h3>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Licensed Capacity
                </label>
                <input
                  type="number"
                  value={config.capacity}
                  onChange={(e) => setConfig(prev => ({ ...prev, capacity: parseInt(e.target.value) || 0 }))}
                  className="input w-full"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Operating Hours/Day
                </label>
                <input
                  type="number"
                  value={config.operatingHours}
                  onChange={(e) => setConfig(prev => ({ ...prev, operatingHours: parseFloat(e.target.value) || 0 }))}
                  className="input w-full"
                  min={1}
                  max={24}
                  step={0.5}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Right Column - Advanced Config */}
      <div className="space-y-6">
        {/* Hour Tiers */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <ClockIcon className="h-5 w-5 text-primary-500" />
              <h3 className="text-lg font-semibold text-gray-900">Hour Targets</h3>
            </div>
            {organization && (
              <span className="text-xs text-gray-500">Some values auto-calculated</span>
            )}
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Full-Time Monthly Target (hours)
              </label>
              <input
                type="number"
                value={config.hourTiers.fullTimeMonthlyTarget}
                onChange={(e) => setConfig(prev => ({
                  ...prev,
                  hourTiers: { ...prev.hourTiers, fullTimeMonthlyTarget: parseFloat(e.target.value) || 0 }
                }))}
                className="input w-full"
              />
              <p className="text-xs text-gray-500 mt-1">Typical: 100-120 hours/month for full-time care</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  School-Age Full Day (hrs)
                  {organization && (
                    <span className="ml-2 text-xs text-primary-600 font-normal">= Operating hours</span>
                  )}
                </label>
                <input
                  type="number"
                  value={config.hourTiers.schoolAgeFullDayTarget}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    hourTiers: { ...prev.hourTiers, schoolAgeFullDayTarget: parseFloat(e.target.value) || 0 }
                  }))}
                  className="input w-full"
                  step={0.5}
                />
                <p className="text-xs text-gray-500 mt-1">During school breaks</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  School-Age Part Day (hrs)
                </label>
                <input
                  type="number"
                  value={config.hourTiers.schoolAgePartDayTarget}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    hourTiers: { ...prev.hourTiers, schoolAgePartDayTarget: parseFloat(e.target.value) || 0 }
                  }))}
                  className="input w-full"
                  step={0.5}
                />
                <p className="text-xs text-gray-500 mt-1">Before/after school</p>
              </div>
            </div>
          </div>
        </div>

        {/* School Breaks */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <AcademicCapIcon className="h-5 w-5 text-primary-500" />
              <h3 className="text-lg font-semibold text-gray-900">School Breaks</h3>
            </div>
            <button
              onClick={addSchoolBreak}
              className="btn btn-secondary text-sm py-1 px-3"
            >
              <PlusIcon className="h-4 w-4 mr-1" />
              Add Break
            </button>
          </div>
          
          {config.schoolBreakPeriods.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No school breaks configured. School-age children will use part-day hours.
            </p>
          ) : (
            <div className="space-y-3">
              {config.schoolBreakPeriods.map((period, idx) => (
                <div key={idx} className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg">
                  <input
                    type="text"
                    value={period.name || ''}
                    onChange={(e) => updateSchoolBreak(idx, 'name', e.target.value)}
                    placeholder="Break name"
                    className="input flex-1 text-sm"
                  />
                  <input
                    type="date"
                    value={period.start}
                    onChange={(e) => updateSchoolBreak(idx, 'start', e.target.value)}
                    className="input w-36 text-sm"
                  />
                  <span className="text-gray-400">to</span>
                  <input
                    type="date"
                    value={period.end}
                    onChange={(e) => updateSchoolBreak(idx, 'end', e.target.value)}
                    className="input w-36 text-sm"
                  />
                  <button
                    onClick={() => removeSchoolBreak(idx)}
                    className="p-2 text-red-500 hover:bg-red-50 rounded"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Profile Distribution */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Profile Distribution</h3>
          <p className="text-sm text-gray-500 mb-4">
            Set the percentage of children in each behavioral category. Must sum to 100%.
          </p>
          
          {/* Full-Time Distribution */}
          <div className="mb-4">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Full-Time Children</h4>
            <div className="grid grid-cols-3 gap-3">
              {(['consistent', 'variable', 'oftenAbsent'] as const).map((profile) => (
                <div key={`ft-${profile}`}>
                  <label className="block text-xs text-gray-500 mb-1 capitalize">
                    {profile === 'oftenAbsent' ? 'Often Absent' : profile}
                  </label>
                  <div className="flex items-center">
                    <input
                      type="number"
                      value={config.fullTimeDistribution[profile]}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        fullTimeDistribution: {
                          ...prev.fullTimeDistribution,
                          [profile]: parseInt(e.target.value) || 0
                        }
                      }))}
                      className="input w-full text-sm"
                      min={0}
                      max={100}
                      step={5}
                    />
                    <span className="ml-1 text-gray-400">%</span>
                  </div>
                </div>
              ))}
            </div>
            <p className={`text-xs mt-1 ${
              config.fullTimeDistribution.consistent + config.fullTimeDistribution.variable + config.fullTimeDistribution.oftenAbsent === 100
                ? 'text-green-600' : 'text-red-600'
            }`}>
              Total: {config.fullTimeDistribution.consistent + config.fullTimeDistribution.variable + config.fullTimeDistribution.oftenAbsent}%
            </p>
          </div>
          
          {/* School-Age Distribution */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-2">School-Age Children</h4>
            <div className="grid grid-cols-3 gap-3">
              {(['consistent', 'variable', 'oftenAbsent'] as const).map((profile) => (
                <div key={`sa-${profile}`}>
                  <label className="block text-xs text-gray-500 mb-1 capitalize">
                    {profile === 'oftenAbsent' ? 'Often Absent' : profile}
                  </label>
                  <div className="flex items-center">
                    <input
                      type="number"
                      value={config.schoolAgeDistribution[profile]}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        schoolAgeDistribution: {
                          ...prev.schoolAgeDistribution,
                          [profile]: parseInt(e.target.value) || 0
                        }
                      }))}
                      className="input w-full text-sm"
                      min={0}
                      max={100}
                      step={5}
                    />
                    <span className="ml-1 text-gray-400">%</span>
                  </div>
                </div>
              ))}
            </div>
            <p className={`text-xs mt-1 ${
              config.schoolAgeDistribution.consistent + config.schoolAgeDistribution.variable + config.schoolAgeDistribution.oftenAbsent === 100
                ? 'text-green-600' : 'text-red-600'
            }`}>
              Total: {config.schoolAgeDistribution.consistent + config.schoolAgeDistribution.variable + config.schoolAgeDistribution.oftenAbsent}%
            </p>
          </div>
        </div>

        {/* Behavioral Profiles */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Behavioral Profiles</h3>
          <p className="text-sm text-gray-500 mb-4">
            Configure attendance rate and variance for each profile type.
          </p>
          <div className="space-y-4">
            {(['consistent', 'variable', 'oftenAbsent'] as const).map((profile) => (
              <div key={profile} className="p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-700 capitalize">
                    {profile === 'oftenAbsent' ? 'Often Absent' : profile}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Attendance Rate</label>
                    <input
                      type="number"
                      value={config.behavioralProfiles[profile].probability * 100}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        behavioralProfiles: {
                          ...prev.behavioralProfiles,
                          [profile]: {
                            ...prev.behavioralProfiles[profile],
                            probability: (parseFloat(e.target.value) || 0) / 100
                          }
                        }
                      }))}
                      className="input w-full text-sm"
                      min={0}
                      max={100}
                      step={5}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Variance</label>
                    <input
                      type="number"
                      value={config.behavioralProfiles[profile].variance * 100}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        behavioralProfiles: {
                          ...prev.behavioralProfiles,
                          [profile]: {
                            ...prev.behavioralProfiles[profile],
                            variance: (parseFloat(e.target.value) || 0) / 100
                          }
                        }
                      }))}
                      className="input w-full text-sm"
                      min={0}
                      max={50}
                      step={5}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      </div>
    </div>
  );
};

export default ConfigurationPanel;
