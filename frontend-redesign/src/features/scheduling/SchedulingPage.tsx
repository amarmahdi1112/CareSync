import { useEffect, useMemo, useReducer } from 'react';
import {
  ArrowPathIcon,
  ArrowRightIcon,
  BoltIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  CircleStackIcon,
  ClockIcon,
  CpuChipIcon,
  DocumentTextIcon,
  PauseIcon,
  PlayIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { SCHEDULER_PREVIEW_COPY } from '../../config/activeRuntimeCopy';
import {
  restoreSchedulerState,
  schedulerReducer,
  SCHEDULER_PHASE_COUNT,
} from './schedulerMachine';

type PhaseId = 'claims' | 'calendar' | 'construct' | 'reshape' | 'certify' | 'review';

const phases: Array<{ id: PhaseId; label: string; short: string; icon: typeof DocumentTextIcon }> = [
  { id: 'claims', label: 'Claim source', short: 'Lock exact hour targets', icon: DocumentTextIcon },
  { id: 'calendar', label: 'Calendar guard', short: 'Load closures and school days', icon: CalendarDaysIcon },
  { id: 'construct', label: 'Construct', short: 'Build deterministic placement', icon: CpuChipIcon },
  { id: 'reshape', label: 'Redistribute', short: 'Create realistic attendance days', icon: ArrowPathIcon },
  { id: 'certify', label: 'Audit preview', short: 'Show constraint-gate treatment', icon: ShieldCheckIcon },
  { id: 'review', label: 'Result preview', short: 'Show the review layout', icon: CheckCircleIcon },
];

if (phases.length !== SCHEDULER_PHASE_COUNT) throw new Error('Scheduler phase metadata is out of sync');

function restoreState() {
  return restoreSchedulerState(localStorage.getItem('caresync-redesign-scheduler-sim-v1'));
}

const reveal = keyframes`
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
`;

const orbit = keyframes`
  to { transform: rotate(360deg); }
`;

const blink = keyframes`
  0%, 100% { opacity: .45; }
  50% { opacity: 1; }
`;

const Page = styled.div`
  display: grid;
  gap: 20px;
  animation: ${reveal} 400ms ${({ theme }) => theme.motion.ease} both;
`;

const PageHeader = styled.header`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  h1 { margin: 9px 0 5px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2rem, 4vw, 3.7rem); font-weight: 520; letter-spacing: -.065em; line-height: 1; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .82rem; }
  @media (max-width: 760px) { align-items: flex-start; flex-direction: column; }
`;

const HeaderActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 9px;
  @media (max-width: 760px) { justify-content: flex-start; }
`;

const SafetyNotice = styled.div`
  position: sticky;
  top: 88px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 11px 13px;
  border: 1px solid rgba(255,202,114,.2);
  border-radius: 12px;
  color: ${({ theme }) => theme.color.textSoft};
  background: rgba(255,202,114,.055);
  backdrop-filter: blur(18px);
  font-size: .7rem;
  svg { width: 18px; color: ${({ theme }) => theme.color.amber}; }
  strong { color: ${({ theme }) => theme.color.amber}; }
`;

const PipelinePanel = styled(GlassPanel)`
  padding: 16px;
`;

const Pipeline = styled.div`
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
`;

const PhaseButton = styled.button<{ $active: boolean; $complete: boolean }>`
  position: relative;
  display: grid;
  min-width: 135px;
  min-height: 80px;
  grid-template-columns: 30px 1fr;
  align-items: center;
  gap: 9px;
  padding: 10px;
  overflow: hidden;
  border: 1px solid ${({ $active, $complete, theme }) => $active ? theme.color.borderStrong : $complete ? 'rgba(99,244,190,.21)' : theme.color.border};
  border-radius: 13px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ $active, $complete }) => $active ? 'linear-gradient(135deg, rgba(169,120,255,.17), rgba(83,230,255,.055))' : $complete ? 'rgba(99,244,190,.035)' : 'rgba(255,255,255,.018)'};
  cursor: pointer;
  text-align: left;
  transition: border-color 140ms ease, transform 140ms ease, background 140ms ease;
  &:hover { transform: translateY(-1px); border-color: ${({ theme }) => theme.color.borderStrong}; }
  &:disabled { cursor: not-allowed; opacity: .48; transform: none; }
  > svg { width: 21px; color: ${({ $active, $complete, theme }) => $complete ? theme.color.mint : $active ? theme.color.cyan : theme.color.textMuted}; }
  strong { display: block; font-size: .7rem; }
  small { display: block; margin-top: 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .56rem; line-height: 1.35; }
`;

const PhaseNumber = styled.span`
  position: absolute;
  top: 5px;
  right: 7px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .52rem;
  letter-spacing: .08em;
`;

const ProgressTrack = styled.div`
  height: 3px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255,255,255,.05);
`;

const ProgressFill = styled.div<{ $progress: number }>`
  width: ${({ $progress }) => $progress}%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, ${({ theme }) => theme.color.plasma}, ${({ theme }) => theme.color.cyan}, ${({ theme }) => theme.color.mint});
  box-shadow: 0 0 18px rgba(83,230,255,.5);
  transition: width 90ms linear;
`;

const WorkGrid = styled.div`
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  gap: 18px;
  @media (max-width: 980px) { grid-template-columns: 1fr; }
`;

const History = styled(GlassPanel)`
  padding: 16px;
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .95rem; font-weight: 560; }
  > p { margin: 4px 0 15px; color: ${({ theme }) => theme.color.textMuted}; font-size: .62rem; }
  @media (max-width: 980px) { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 15px; h2, > p { grid-column: 1; } }
`;

const BatchList = styled.div`
  display: grid;
  gap: 8px;
  @media (max-width: 980px) { display: flex; grid-column: 2; grid-row: 1 / span 2; overflow-x: auto; }
`;

const Batch = styled.div<{ $selected?: boolean }>`
  display: block;
  width: 100%;
  min-width: 170px;
  padding: 12px;
  border: 1px solid ${({ $selected, theme }) => $selected ? theme.color.borderStrong : theme.color.border};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ $selected }) => $selected ? 'rgba(169,120,255,.095)' : 'rgba(255,255,255,.018)'};
  text-align: left;
  strong { display: block; font-size: .75rem; }
  span { display: flex; align-items: center; gap: 5px; margin-top: 5px; color: ${({ theme }) => theme.color.textMuted}; font-size: .59rem; }
  svg { width: 12px; }
`;

const Engine = styled(GlassPanel)`
  padding: clamp(18px, 2.5vw, 30px);
  background:
    radial-gradient(circle at 72% 20%, rgba(83,230,255,.07), transparent 30%),
    radial-gradient(circle at 34% 105%, rgba(169,120,255,.12), transparent 38%),
    ${({ theme }) => theme.color.surface};
`;

const EngineHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
  h2 { margin: 9px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.4rem, 2.6vw, 2.25rem); font-weight: 520; letter-spacing: -.055em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; }
  @media (max-width: 680px) { flex-direction: column; }
`;

const EngineControls = styled.div`
  display: flex;
  gap: 8px;
`;

const TelemetryGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
  margin-bottom: 14px;
  @media (max-width: 680px) { grid-template-columns: repeat(2, 1fr); }
`;

const Telemetry = styled.div`
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  background: rgba(255,255,255,.018);
  span { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .55rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
  strong { display: block; margin-top: 5px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.05rem, 2vw, 1.55rem); font-weight: 550; letter-spacing: -.04em; }
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .55rem; }
`;

const VisualGrid = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, .7fr);
  gap: 14px;
  @media (max-width: 760px) { grid-template-columns: 1fr; }
`;

const Occupancy = styled.div`
  position: relative;
  min-height: 335px;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 16px;
  background:
    linear-gradient(rgba(164,180,255,.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(164,180,255,.045) 1px, transparent 1px),
    rgba(5,8,18,.56);
  background-size: 100% 25%, 12.5% 100%;
`;

const ChartHeader = styled.div`
  position: absolute;
  top: 17px;
  left: 18px;
  z-index: 2;
  strong { display: block; font-size: .73rem; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .58rem; }
`;

const ScanLine = styled.div<{ $progress: number }>`
  position: absolute;
  top: 0;
  bottom: 0;
  left: ${({ $progress }) => Math.max(2, Math.min(98, $progress))}%;
  z-index: 3;
  width: 1px;
  background: ${({ theme }) => theme.color.cyan};
  box-shadow: 0 0 17px ${({ theme }) => theme.color.cyan};
  transition: left 90ms linear;
  &::before { position: absolute; top: 14px; left: -4px; width: 9px; height: 9px; content: ''; border-radius: 50%; background: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 14px ${({ theme }) => theme.color.cyan}; }
`;

const ChartSvg = styled.svg`
  position: absolute;
  inset: 50px 12px 18px;
  width: calc(100% - 24px);
  height: calc(100% - 68px);
  overflow: visible;
`;

const EngineCore = styled.div`
  position: relative;
  display: grid;
  min-height: 335px;
  place-items: center;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 16px;
  background: radial-gradient(circle, rgba(169,120,255,.14), rgba(83,230,255,.025) 42%, rgba(5,8,18,.55) 67%);
  &::before { position: absolute; width: 220px; height: 220px; content: ''; border: 1px dashed rgba(83,230,255,.25); border-radius: 50%; animation: ${orbit} 16s linear infinite; }
  &::after { position: absolute; width: 155px; height: 155px; content: ''; border: 1px solid rgba(169,120,255,.22); border-radius: 50%; animation: ${orbit} 9s linear reverse infinite; }
`;

const CoreCopy = styled.div`
  position: relative;
  z-index: 2;
  max-width: 190px;
  text-align: center;
  svg { width: 34px; margin: 0 auto 11px; color: ${({ theme }) => theme.color.plasmaBright}; animation: ${blink} 2.3s ease-in-out infinite; }
  strong { display: block; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; font-weight: 560; }
  span { display: block; margin-top: 5px; color: ${({ theme }) => theme.color.textMuted}; font-size: .61rem; line-height: 1.5; }
`;

const DecisionPanel = styled.div`
  display: grid;
  gap: 8px;
  margin-top: 14px;
`;

const PhaseAnnouncement = styled.p`
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
`;

const Decision = styled.div<{ $active?: boolean }>`
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid ${({ $active, theme }) => $active ? theme.color.borderStrong : theme.color.border};
  border-radius: 11px;
  background: ${({ $active }) => $active ? 'rgba(169,120,255,.075)' : 'rgba(255,255,255,.014)'};
  > span:first-child { display: grid; width: 22px; height: 22px; place-items: center; border-radius: 7px; color: ${({ $active, theme }) => $active ? theme.color.ink : theme.color.textMuted}; background: ${({ $active, theme }) => $active ? theme.color.cyan : 'rgba(255,255,255,.04)'}; font-size: .56rem; font-weight: 800; }
  strong { display: block; font-size: .67rem; }
  small { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .56rem; }
  > span:last-child { color: ${({ theme }) => theme.color.textMuted}; font-size: .55rem; text-transform: uppercase; }
`;

const Completion = styled.div`
  margin-top: 14px;
  padding: 14px;
  border: 1px solid rgba(99,244,190,.22);
  border-radius: 13px;
  color: ${({ theme }) => theme.color.mint};
  background: rgba(99,244,190,.045);
  font-size: .7rem;
`;

export default function SchedulingPage() {
  const [state, dispatch] = useReducer(schedulerReducer, undefined, restoreState);
  const current = phases[state.phaseIndex];

  useEffect(() => {
    localStorage.setItem('caresync-redesign-scheduler-sim-v1', JSON.stringify({ version: 1, state }));
  }, [state]);

  useEffect(() => {
    if (!state.running) return;
    const timer = window.setInterval(() => dispatch({ type: 'tick' }), 80);
    return () => window.clearInterval(timer);
  }, [state.running]);

  const telemetry = useMemo(() => ({
    events: state.iteration,
    sampleEntities: Math.round(150 * Math.min(1, state.progress / 44)),
    audit: 'NOT RUN',
  }), [state.progress, state.completed]);

  return (
    <Page>
      <PageHeader>
        <div>
          <Eyebrow><BoltIcon width={14} /> V3 scheduler · redesign laboratory</Eyebrow>
          <h1>Engine room.</h1>
          <p>Preview the intended construction, redistribution, and audit story without contacting the scheduler.</p>
        </div>
        <HeaderActions>
          <StatusChip $tone={state.running ? 'info' : 'warning'}>{state.completed ? 'Demo animation complete' : state.running ? 'Demo animation moving' : 'Demo checkpoint saved'}</StatusChip>
          <ActionButton $variant="quiet" onClick={() => dispatch({ type: 'reset' })}><ArrowPathIcon /> Reset</ActionButton>
          <ActionButton $variant="primary" onClick={() => dispatch({ type: state.running ? 'pause' : 'start' })}>
            {state.running ? <PauseIcon /> : <PlayIcon />}{state.running ? 'Pause demo' : state.completed ? 'Replay demo' : 'Run UI demo'}
          </ActionButton>
        </HeaderActions>
      </PageHeader>

      <SafetyNotice><ShieldCheckIcon /><span><strong>SAMPLE UI · NO SERVER RUN:</strong> {SCHEDULER_PREVIEW_COPY}</span></SafetyNotice>

      <PipelinePanel $accent="plasma">
        <Pipeline aria-label="Scheduler phases">
          {phases.map((phase, index) => {
            const Icon = phase.icon;
            const reachedPhase = state.completed
              ? phases.length - 1
              : Math.min(phases.length - 1, Math.floor((state.progress / 100) * phases.length));
            return (
              <PhaseButton key={phase.id} disabled={index > reachedPhase} $active={index === state.phaseIndex} $complete={index < reachedPhase || state.completed} onClick={() => dispatch({ type: 'seek', phaseIndex: index })}>
                <PhaseNumber>0{index + 1}</PhaseNumber>
                <Icon aria-hidden="true" />
                <span><strong>{phase.label}</strong><small>{phase.short}</small></span>
              </PhaseButton>
            );
          })}
        </Pipeline>
        <ProgressTrack role="progressbar" aria-label="Interface demo progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(state.progress)}><ProgressFill $progress={state.progress} /></ProgressTrack>
      </PipelinePanel>

      <WorkGrid>
        <History $accent="cyan">
          <h2>Schedule history</h2>
          <p>Static layout samples only. No schedule history was requested.</p>
          <BatchList>
            <Batch $selected><strong>Sample run A</strong><span><CalendarDaysIcon /> Interface fixture only</span></Batch>
            <Batch><strong>Historical layout</strong><span><ClockIcon /> No server data loaded</span></Batch>
            <Batch><strong>Future workflow</strong><span><SparklesIcon /> Migration not connected</span></Batch>
          </BatchList>
        </History>

        <Engine $accent="plasma">
          <EngineHeader>
            <div>
              <Eyebrow><CpuChipIcon width={14} /> Active phase · 0{state.phaseIndex + 1}</Eyebrow>
              <h2>{current.label}</h2>
              <p>{current.short}. The checkpoint survives a page refresh.</p>
            </div>
            <StatusChip $tone={state.running ? 'info' : state.completed ? 'warning' : 'neutral'}>{state.running ? `Demo event ${state.iteration}` : state.completed ? 'Animation finished' : 'Standing by'}</StatusChip>
          </EngineHeader>

          <TelemetryGrid>
            <Telemetry><span>Animation</span><strong>{state.progress.toFixed(1)}%</strong><small>interface motion only</small></Telemetry>
            <Telemetry><span>UI events</span><strong>{telemetry.events}</strong><small>sample state transitions</small></Telemetry>
            <Telemetry><span>Sample entities</span><strong>{telemetry.sampleEntities}/150</strong><small>fabricated visualization data</small></Telemetry>
            <Telemetry><span>Server audit</span><strong>{telemetry.audit}</strong><small>no V3 request was made</small></Telemetry>
          </TelemetryGrid>

          <VisualGrid>
            <Occupancy aria-label="Preview room occupancy chart">
              <ChartHeader><strong>Sample occupancy shape · interface only</strong><span>Decorative fixture; not calculated from children or capacity</span></ChartHeader>
              <ScanLine $progress={state.progress} />
              <ChartSvg viewBox="0 0 800 260" preserveAspectRatio="none" role="img" aria-label="Sample animated curve with no server data">
                <defs>
                  <linearGradient id="schedule-area" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#a978ff" stopOpacity=".42" />
                    <stop offset="1" stopColor="#53e6ff" stopOpacity=".02" />
                  </linearGradient>
                  <linearGradient id="schedule-line" x1="0" y1="0" x2="1" y2="0">
                    <stop stopColor="#a978ff" /><stop offset=".52" stopColor="#53e6ff" /><stop offset="1" stopColor="#63f4be" />
                  </linearGradient>
                </defs>
                <path d="M0 230 L58 228 L88 92 L160 88 L190 150 L310 144 L380 152 L510 146 L575 82 L680 94 L708 226 L800 230 L800 260 L0 260 Z" fill="url(#schedule-area)" />
                <path d="M0 230 L58 228 L88 92 L160 88 L190 150 L310 144 L380 152 L510 146 L575 82 L680 94 L708 226 L800 230" fill="none" stroke="url(#schedule-line)" strokeWidth="4" vectorEffect="non-scaling-stroke" />
                <path d="M0 48 H800" stroke="#ff7d90" strokeWidth="1.5" strokeDasharray="7 7" vectorEffect="non-scaling-stroke" />
                <text x="10" y="38" fill="#ff7d90" fontSize="12">sample guide</text>
              </ChartSvg>
            </Occupancy>

            <EngineCore>
              <CoreCopy>
                <CircleStackIcon aria-hidden="true" />
                <strong>{current.label}</strong>
                <span>{state.running ? 'Animating the next interface state without contacting the scheduler.' : state.completed ? 'The interface story finished; no schedule or audit was performed.' : 'Press run to preview how the redesigned V3 story could unfold.'}</span>
              </CoreCopy>
            </EngineCore>
          </VisualGrid>

          <PhaseAnnouncement aria-live="polite">Interface demo phase: {current.label}</PhaseAnnouncement>
          <DecisionPanel>
            <Decision $active={state.phaseIndex === 2}><span>01</span><div><strong>Preview least-flexible placement story</strong><small>{telemetry.events} sample UI events rendered</small></div><span>{state.phaseIndex > 2 ? 'shown' : state.phaseIndex === 2 ? 'showing' : 'queued'}</span></Decision>
            <Decision $active={state.phaseIndex === 3}><span>02</span><div><strong>Preview the redistribution story</strong><small>Sample motion only; no child hours are loaded</small></div><span>{state.phaseIndex > 3 ? 'shown' : state.phaseIndex === 3 ? 'showing' : 'queued'}</span></Decision>
            <Decision $active={state.phaseIndex === 4}><span>03</span><div><strong>Preview the audit explanation layout</strong><small>Real certification appears only from a typed server result</small></div><span>{state.phaseIndex > 4 ? 'shown' : state.phaseIndex === 4 ? 'showing' : 'queued'}</span></Decision>
          </DecisionPanel>
          {state.completed && <Completion><strong>UI demo animation complete.</strong> No server request, schedule calculation, constraint audit, certification, persistence, or export occurred.</Completion>}
        </Engine>
      </WorkGrid>
    </Page>
  );
}
