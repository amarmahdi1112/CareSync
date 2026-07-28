import React, { useState, useEffect } from 'react';
import {
  Cog6ToothIcon,
  FolderIcon,
  DocumentArrowDownIcon,
  ArrowsRightLeftIcon,
  PlayIcon,
  PlusIcon,
  ArrowRightIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../../stores';
import ConfigurationPanel from '../../files/claim-generation/components/ConfigurationPanel';
import ResultsPanel from '../../files/claim-generation/components/ResultsPanel';
import SavedReportsPanel from '../../files/claim-generation/components/SavedReportsPanel';
import ReportDetailModal from '../../files/claim-generation/components/ReportDetailModal';
import NameSyncView from '../../files/claim-generation/name-sync/NameSyncView';
import PdfImportView from '../../files/claim-generation/components/PdfImportView';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// ─── Types ──────────────────────────────────────────────────────────────────────

export interface ProfileDistribution {
  consistent: number;
  variable: number;
  oftenAbsent: number;
}

export interface ClaimConfig {
  month: number;
  year: number;
  capacity: number;
  operatingHours: number;
  hourTiers: {
    fullTimeMonthlyTarget: number;
    schoolAgeFullDayTarget: number;
    schoolAgePartDayTarget: number;
  };
  schoolBreakPeriods: Array<{ start: string; end: string; name?: string }>;
  behavioralProfiles: {
    consistent: { probability: number; variance: number };
    variable: { probability: number; variance: number };
    oftenAbsent: { probability: number; variance: number };
  };
  fullTimeDistribution: ProfileDistribution;
  schoolAgeDistribution: ProfileDistribution;
}

export interface OrganizationData {
  id: string;
  name: string;
  licensed_capacity: number;
  opening_time: string;
  closing_time: string;
}

interface GenerationResult {
  id: string;
  reportName: string;
  totalChildren: number;
  totalProjectedHours: number;
  claims: Array<{
    childId: string;
    childName: string;
    careCategory: string;
    projectedHours: number;
    projectedAttendanceDays: number;
    behavioralProfile: string;
    isProrated: boolean;
  }>;
}

const calculateOperatingHours = (openTime: string, closeTime: string): number => {
  const [openHour, openMin] = openTime.split(':').map(Number);
  const [closeHour, closeMin] = closeTime.split(':').map(Number);
  return ((closeHour * 60 + closeMin) - (openHour * 60 + openMin)) / 60;
};

const getDefaultConfig = (org?: OrganizationData): ClaimConfig => ({
  month: new Date().getMonth() + 1,
  year: new Date().getFullYear(),
  capacity: org?.licensed_capacity || 50,
  operatingHours: org ? calculateOperatingHours(org.opening_time, org.closing_time) : 10,
  hourTiers: {
    fullTimeMonthlyTarget: 120,
    schoolAgeFullDayTarget: org ? calculateOperatingHours(org.opening_time, org.closing_time) : 9,
    schoolAgePartDayTarget: 4,
  },
  schoolBreakPeriods: [],
  behavioralProfiles: {
    consistent: { probability: 0.95, variance: 0.05 },
    variable: { probability: 0.80, variance: 0.15 },
    oftenAbsent: { probability: 0.60, variance: 0.25 },
  },
  fullTimeDistribution: { consistent: 40, variable: 35, oftenAbsent: 25 },
  schoolAgeDistribution: { consistent: 55, variable: 30, oftenAbsent: 15 },
});

// ─── Component ──────────────────────────────────────────────────────────────────

type SubTab = 'generate' | 'reports' | 'pdfImport' | 'nameSync';
type GenerateStep = 'configure' | 'generating' | 'results';

interface ClaimsPhaseProps {
  onClaimSelected: (sourceType: 'generated' | 'imported', batchId: string) => void;
  selectedSource: { type: 'generated' | 'imported'; batchId: string } | null;
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const ClaimsPhase: React.FC<ClaimsPhaseProps> = ({ onClaimSelected, selectedSource }) => {
  const { success, error: showError } = useNotificationStore();

  // Sub-tab state
  const [activeTab, setActiveTab] = useState<SubTab>('generate');

  // Generation flow state
  const [config, setConfig] = useState<ClaimConfig>(getDefaultConfig());
  const [reportName, setReportName] = useState(`Claims ${new Date().toLocaleDateString()}`);
  const [step, setStep] = useState<GenerateStep>('configure');
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [orgLoaded, setOrgLoaded] = useState(false);

  // Report modal
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [showReportModal, setShowReportModal] = useState(false);
  const [loading, setLoading] = useState(false);

  const { data: orgData } = useApiQuery<OrganizationData>('/organization');
  const { data: reportRows } = useApiQuery<any[]>('/resources/generated_claim_reports', {
    limit: 5000,
    sort: 'created_at',
    order: 'desc',
  });
  const { data: childrenData } = useApiQuery<any[]>('/children', { active_only: true, limit: 1000 });

  const reportsData = (reportRows || []).map((row) => ({
    id: row.id,
    reportName: row.report_name,
    created_at: row.created_at,
    report: {
      targetMonth: row.target_month,
      targetYear: row.target_year,
      totalChildrenProcessed: row.total_children_processed,
      totalProjectedHours: Number(row.total_projected_hours),
    },
  }));
  // Auto-populate config from org
  useEffect(() => {
    if (orgData && !orgLoaded) {
      setConfig(getDefaultConfig(orgData));
      setOrgLoaded(true);
    }
  }, [orgData, orgLoaded]);

  const handleGenerate = async () => {
    setStep('generating');
    setLoading(true);
    try {
      const raw = await api.post<any>('/claims/simulate', {
          month: config.month,
          year: config.year,
          capacity: config.capacity,
          operatingHours: config.operatingHours,
          hourTiers: config.hourTiers,
          schoolBreakPeriods: config.schoolBreakPeriods,
          behavioralProfiles: config.behavioralProfiles,
          fullTimeDistribution: config.fullTimeDistribution,
          schoolAgeDistribution: config.schoolAgeDistribution,
          seed: `${config.year}-${config.month}-${reportName}`,
          children: (childrenData || []).map((child) => ({
            id: child.id,
            name: `${child.first_name} ${child.last_name}`,
            birthDate: child.date_of_birth,
            familyId: child.family_id,
            enrollmentDate: child.start_date,
            ageGroup: child.age_group,
          })),
      });
      const flat: GenerationResult = {
        id: raw.batch_id,
        reportName,
        totalChildren: raw.stats.total_claims,
        totalProjectedHours: raw.stats.total_hours_projected,
        claims: (raw.claims || []).map((claim: any) => ({
          childId: claim.child_id,
          childName: claim.child_name,
          careCategory: claim.care_category,
          projectedHours: claim.projected_hours,
          projectedAttendanceDays: claim.projected_attendance_days,
          behavioralProfile: claim.behavioral_profile,
          isProrated: claim.is_prorated,
        })),
      };
      sessionStorage.setItem(`caresync:claim-batch:${raw.batch_id}`, JSON.stringify({ raw, config, reportName }));
      setResult(flat);
      setStep('results');
      success('Claims Generated', `Successfully generated ${flat.claims.length} claims`);
    } catch (caught) {
      showError('Generation Failed', caught instanceof Error ? caught.message : 'Failed to generate claims');
      setStep('configure');
    } finally {
      setLoading(false);
    }
  };

  // ─── Sub-tabs ───────────────────────────────────────────────────────────────

  const tabs: { key: SubTab; label: string; icon: React.ElementType }[] = [
    { key: 'generate', label: 'Generate Claims', icon: Cog6ToothIcon },
    { key: 'reports', label: 'Saved Reports', icon: FolderIcon },
    { key: 'pdfImport', label: 'Import from PDF', icon: DocumentArrowDownIcon },
    { key: 'nameSync', label: 'Name Sync', icon: ArrowsRightLeftIcon },
  ];

  return (
    <div className="h-full flex flex-col">
      {/* Sub-tab Navigation */}
      <div className="bg-white border-b border-gray-200 px-6">
        <nav className="flex space-x-6" aria-label="Claim tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors flex items-center space-x-2 ${
                activeTab === tab.key
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <tab.icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* ─── Generate Tab ─── */}
        {activeTab === 'generate' && (
          <>
            {/* Action Bar */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Generate Projected Claims</h2>
                <p className="text-sm text-gray-500">Configure and generate attendance claim projections</p>
              </div>
              {step === 'configure' && (
                <button onClick={handleGenerate} disabled={loading} className="btn btn-primary flex items-center space-x-2">
                  <PlayIcon className="h-5 w-5" />
                  <span>Generate Claims</span>
                </button>
              )}
            </div>

            {step === 'configure' && (
              <ConfigurationPanel
                config={config}
                setConfig={setConfig}
                reportName={reportName}
                setReportName={setReportName}
                organization={orgData}
              />
            )}

            {step === 'generating' && (
              <div className="flex flex-col items-center justify-center py-24">
                <div className="relative">
                  <div className="animate-spin rounded-full h-20 w-20 border-4 border-primary-200 border-t-primary-500" />
                  <ClockIcon className="h-8 w-8 text-primary-500 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2" />
                </div>
                <h2 className="text-xl font-semibold text-gray-900 mt-6 mb-2">Generating Claims...</h2>
                <p className="text-gray-500">
                  Processing {MONTHS[config.month - 1]} {config.year} attendance projections
                </p>
              </div>
            )}

            {step === 'results' && result && (
              <>
                <ResultsPanel
                  result={result}
                  config={config}
                  onNewGeneration={() => { setStep('configure'); setResult(null); }}
                  onViewSavedReports={() => setActiveTab('reports')}
                />
                {/* CTA: Continue to Schedule */}
                <div className="mt-6 p-4 bg-gradient-to-r from-primary-50 to-blue-50 rounded-xl border border-primary-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-primary-900">Ready to generate a schedule?</h3>
                      <p className="text-sm text-primary-600">
                        Use this claim report ({result.totalChildren} children, {result.totalProjectedHours.toFixed(0)}h) to build a daily schedule.
                      </p>
                    </div>
                    <button
                      onClick={() => onClaimSelected('generated', result.id)}
                      className="btn btn-primary flex items-center space-x-2 shrink-0"
                    >
                      <span>Continue to Schedule</span>
                      <ArrowRightIcon className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ─── Saved Reports Tab ─── */}
        {activeTab === 'reports' && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Saved Claim Reports</h2>
                <p className="text-sm text-gray-500">View and use previously generated claim reports</p>
              </div>
              <button onClick={() => { setActiveTab('generate'); setStep('configure'); }} className="btn btn-primary flex items-center space-x-2">
                <PlusIcon className="h-5 w-5" />
                <span>New Generation</span>
              </button>
            </div>

            <SavedReportsPanel onViewReport={(id) => { setSelectedReportId(id); setShowReportModal(true); }} />

            {/* Selectable report cards for continuing to schedule */}
            {reportsData.length > 0 && (
              <div className="mt-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
                <h3 className="font-medium text-gray-700 mb-3">Select a report to use for scheduling:</h3>
                <div className="grid gap-3">
                  {reportsData.map((report) => (
                    <button
                      key={report.id}
                      onClick={() => onClaimSelected('generated', report.id)}
                      className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                        selectedSource?.batchId === report.id
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 bg-white hover:border-primary-300'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-semibold text-gray-900">{report.reportName}</p>
                          <p className="text-sm text-gray-500">
                            {MONTHS[report.report.targetMonth - 1]} {report.report.targetYear} • {report.report.totalChildrenProcessed} children • {report.report.totalProjectedHours.toFixed(1)}h
                          </p>
                        </div>
                        <ArrowRightIcon className="h-5 w-5 text-gray-400" />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── PDF Import Tab ─── */}
        {activeTab === 'pdfImport' && (
          <div>
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-gray-900">Import Claims from PDF</h2>
              <p className="text-sm text-gray-500">Upload a government PDF and match claims to children</p>
            </div>
            <PdfImportView
              onUseForScheduling={(batchId) => onClaimSelected('imported', batchId)}
            />
          </div>
        )}

        {/* ─── Name Sync Tab ─── */}
        {activeTab === 'nameSync' && (
          <div>
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-gray-900">Name Sync</h2>
              <p className="text-sm text-gray-500">Match and reconcile child names between systems</p>
            </div>
            <NameSyncView claimsData={result?.claims} />
          </div>
        )}
      </div>

      {/* Report Detail Modal */}
      {selectedReportId && (
        <ReportDetailModal
          reportId={selectedReportId}
          isOpen={showReportModal}
          onClose={() => { setShowReportModal(false); setSelectedReportId(null); }}
          onRegenerate={() => {
            setShowReportModal(false);
            setSelectedReportId(null);
            setActiveTab('generate');
            setStep('configure');
            setResult(null);
          }}
        />
      )}
    </div>
  );
};

export default ClaimsPhase;
