import React, { useState, useCallback } from 'react';
import PipelineNav, { type Phase } from './components/PipelineNav';
import HistoryPanel from './components/HistoryPanel';
import ClaimsPhase from './phases/ClaimsPhase';
import SchedulePhase from './phases/SchedulePhase';
import EngineRoomPhase from './phases/EngineRoomPhase';
import ReviewPhase from './phases/ReviewPhase';
import ExportPhase from './phases/ExportPhase';

interface ClaimSource {
  type: 'generated' | 'imported';
  batchId: string;
}

const SchedulingHub: React.FC = () => {
  // Pipeline state
  const [activePhase, setActivePhase] = useState<Phase>('claims');
  const [completedPhases, setCompletedPhases] = useState<Set<Phase>>(new Set());

  // Shared state between phases
  const [selectedSource, setSelectedSource] = useState<ClaimSource | null>(null);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [activeScheduleResult, setActiveScheduleResult] = useState<unknown>(null);
  const [approvedExportBatchId, setApprovedExportBatchId] = useState<string | null>(null);

  // History panel
  const [historyCollapsed, setHistoryCollapsed] = useState(false);

  const markPhaseCompleted = useCallback((phase: Phase) => {
    setCompletedPhases(prev => new Set([...prev, phase]));
  }, []);

  // Phase 1 → Phase 2 transition
  const handleClaimSelected = useCallback((sourceType: 'generated' | 'imported', batchId: string) => {
    setSelectedSource({ type: sourceType, batchId });
    markPhaseCompleted('claims');
    setActivePhase('schedule');
  }, [markPhaseCompleted]);

  // Generate → deterministic engine replay
  const handleScheduleGenerated = useCallback((batchId: string, result?: unknown) => {
    setActiveBatchId(batchId);
    setActiveScheduleResult(result ?? null);
    setApprovedExportBatchId(null);
    markPhaseCompleted('schedule');
    setActivePhase('engine');
  }, [markPhaseCompleted]);

  // History panel → Jump to review
  const handleSelectBatch = useCallback((batchId: string) => {
    setActiveBatchId(batchId);
    setActiveScheduleResult(null);
    setApprovedExportBatchId(null);
    setActivePhase('review');
  }, []);

  const handleContinueToExport = useCallback(() => {
    if (!activeBatchId) return;
    setApprovedExportBatchId(activeBatchId);
    markPhaseCompleted('review');
    setActivePhase('export');
  }, [activeBatchId, markPhaseCompleted]);

  const handleContinueToReview = useCallback(() => {
    markPhaseCompleted('engine');
    setActivePhase('review');
  }, [markPhaseCompleted]);

  // New schedule → Reset to phase 1
  const handleNewSchedule = useCallback(() => {
    setActivePhase('claims');
    setSelectedSource(null);
    setActiveBatchId(null);
    setActiveScheduleResult(null);
    setApprovedExportBatchId(null);
    setCompletedPhases(new Set());
  }, []);

  const renderActivePhase = () => {
    switch (activePhase) {
      case 'claims':
        return (
          <ClaimsPhase
            onClaimSelected={handleClaimSelected}
            selectedSource={selectedSource}
          />
        );
      case 'schedule':
        return (
          <SchedulePhase
            selectedSource={selectedSource}
            onScheduleGenerated={handleScheduleGenerated}
          />
        );
      case 'engine':
        return (
          <EngineRoomPhase
            activeBatchId={activeBatchId}
            scheduleResult={activeScheduleResult}
            onBackToConfigure={() => setActivePhase('schedule')}
            onContinueToReview={handleContinueToReview}
          />
        );
      case 'review':
        return (
          <ReviewPhase
            activeBatchId={activeBatchId}
            scheduleResult={activeScheduleResult}
            onContinueToExport={handleContinueToExport}
          />
        );
      case 'export':
        return (
          <ExportPhase
            activeBatchId={activeBatchId}
            reviewApproved={Boolean(activeBatchId && approvedExportBatchId === activeBatchId)}
            onReturnToReview={() => setActivePhase('review')}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-50 -m-6 -mt-4">
      {/* Page Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Scheduling</h1>
          <p className="text-sm text-gray-500">
            Generate claims, build schedules, review attendance, and export documents
          </p>
        </div>
      </div>

      {/* Pipeline Navigation */}
      <PipelineNav
        activePhase={activePhase}
        onPhaseChange={setActivePhase}
        completedPhases={completedPhases}
        hasActiveBatch={activeBatchId !== null}
        hasClaimSource={selectedSource !== null}
        canExport={Boolean(activeBatchId && approvedExportBatchId === activeBatchId)}
      />

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* History Sidebar */}
        <HistoryPanel
          collapsed={historyCollapsed}
          onToggleCollapse={() => setHistoryCollapsed(!historyCollapsed)}
          activeBatchId={activeBatchId}
          onSelectBatch={handleSelectBatch}
          onNewSchedule={handleNewSchedule}
        />

        {/* Phase Content */}
        <div className="flex-1 overflow-y-auto">
          {renderActivePhase()}
        </div>
      </div>
    </div>
  );
};

export default SchedulingHub;
