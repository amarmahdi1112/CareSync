import React from 'react';
import {
  DocumentTextIcon,
  Cog6ToothIcon,
  BoltIcon,
  CalendarDaysIcon,
  ArrowDownTrayIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';

export type Phase = 'claims' | 'schedule' | 'engine' | 'review' | 'export';

interface PipelineNavProps {
  activePhase: Phase;
  onPhaseChange: (phase: Phase) => void;
  completedPhases: Set<Phase>;
  /** If a schedule batch is selected, phases 3-4 become available */
  hasActiveBatch: boolean;
  /** If a claim source is selected, phase 2 becomes available */
  hasClaimSource: boolean;
  /** Export is available only after this batch passed the review gate. */
  canExport: boolean;
}

const phases: { key: Phase; label: string; icon: React.ElementType; description: string }[] = [
  { key: 'claims', label: 'Claims', icon: DocumentTextIcon, description: 'Get hours per child' },
  { key: 'schedule', label: 'Generate', icon: Cog6ToothIcon, description: 'Configure & run engine' },
  { key: 'engine', label: 'Engine Room', icon: BoltIcon, description: 'Replay V3 decisions' },
  { key: 'review', label: 'Review & Edit', icon: CalendarDaysIcon, description: 'View daily attendance' },
  { key: 'export', label: 'Export', icon: ArrowDownTrayIcon, description: 'Timesheets & invoices' },
];

const PipelineNav: React.FC<PipelineNavProps> = ({
  activePhase,
  onPhaseChange,
  completedPhases,
  hasActiveBatch,
  hasClaimSource,
  canExport,
}) => {
  const isPhaseAccessible = (phase: Phase): boolean => {
    switch (phase) {
      case 'claims': return true;
      case 'schedule': return hasClaimSource || completedPhases.has('claims');
      case 'engine': return hasActiveBatch || completedPhases.has('schedule');
      case 'review': return hasActiveBatch || completedPhases.has('schedule');
      case 'export': return canExport && hasActiveBatch && completedPhases.has('review');
      default: return false;
    }
  };

  const activeIdx = phases.findIndex(p => p.key === activePhase);

  return (
    <div className="bg-white border-b border-gray-200">
      <div className="overflow-x-auto px-6 py-4">
        <div className="flex min-w-max items-center">
          {phases.map((phase, idx) => {
            const isActive = activePhase === phase.key;
            const isCompleted = completedPhases.has(phase.key);
            const isAccessible = isPhaseAccessible(phase.key);
            const isPast = idx < activeIdx;
            const Icon = phase.icon;

            return (
              <React.Fragment key={phase.key}>
                {idx > 0 && (
                  <div className={`flex-1 h-0.5 mx-3 transition-colors duration-300 ${
                    isPast || isCompleted ? 'bg-primary-500' : 'bg-gray-200'
                  }`} />
                )}
                <button
                  onClick={() => isAccessible && onPhaseChange(phase.key)}
                  disabled={!isAccessible}
                  className={`flex items-center space-x-3 px-4 py-2.5 rounded-xl transition-all duration-200 min-w-0 ${
                    isActive
                      ? 'bg-primary-50 border-2 border-primary-500 shadow-sm'
                      : isCompleted
                        ? 'bg-green-50 border-2 border-green-300 hover:border-green-400'
                        : isAccessible
                          ? 'bg-gray-50 border-2 border-gray-200 hover:border-gray-300 hover:bg-gray-100'
                          : 'bg-gray-50 border-2 border-gray-100 opacity-50 cursor-not-allowed'
                  }`}
                >
                  <div className={`flex items-center justify-center w-9 h-9 rounded-lg shrink-0 ${
                    isActive
                      ? 'bg-primary-500 text-white'
                      : isCompleted
                        ? 'bg-green-500 text-white'
                        : 'bg-gray-200 text-gray-500'
                  }`}>
                    {isCompleted && !isActive ? (
                      <CheckCircleIcon className="h-5 w-5" />
                    ) : (
                      <Icon className="h-5 w-5" />
                    )}
                  </div>
                  <div className="text-left min-w-0">
                    <p className={`text-sm font-semibold truncate ${
                      isActive ? 'text-primary-700' : isCompleted ? 'text-green-700' : 'text-gray-600'
                    }`}>
                      {phase.label}
                    </p>
                    <p className={`text-xs truncate ${
                      isActive ? 'text-primary-500' : 'text-gray-400'
                    }`}>
                      {phase.description}
                    </p>
                  </div>
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default PipelineNav;
