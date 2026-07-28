import React, { useEffect, useMemo, useState } from 'react';
import {
  AdjustmentsHorizontalIcon,
  ArrowLeftIcon,
  ArrowLongRightIcon,
  ArrowPathIcon,
  BoltIcon,
  CalendarDaysIcon,
  CheckBadgeIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  MagnifyingGlassIcon,
  PauseIcon,
  PlayIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';

type TimeBlock = {
  startTick: number;
  endTick: number;
};

type EngineEvent = {
  sequence: number;
  phase: string;
  action: string;
  childId?: string;
  childName?: string;
  fromDate?: string;
  toDate?: string;
  fromBlocks: TimeBlock[];
  toBlocks: TimeBlock[];
  durationTicks: number;
  reason?: string;
  beforeShortfallTicks?: number;
  afterShortfallTicks?: number;
  iteration?: number;
};

type EnginePhase = {
  key: string;
  label: string;
  description?: string;
  outcome?: string;
};

type EngineData = {
  version: string;
  phases: EnginePhase[];
  events: EngineEvent[];
  children: Array<{ id: string; name: string }>;
  dates: string[];
  capacity: number;
  requestedTicks: number;
  scheduledTicks: number;
  certified: boolean;
  source: 'telemetry' | 'audit';
};

type Assignment = {
  childId: string;
  childName: string;
  date: string;
  blocks: TimeBlock[];
};

type LooseRecord = Record<string, unknown>;

interface EngineRoomPhaseProps {
  activeBatchId: string | null;
  scheduleResult?: unknown;
  onContinueToReview: () => void;
  onBackToConfigure?: () => void;
}

const TICK_MINUTES = 5;
const PLAYBACK_DELAYS: Record<string, number> = {
  '0.5': 1500,
  '1': 800,
  '2': 400,
  '4': 180,
};

const PLAYBACK_TARGETS: Record<string, number> = {
  '0.5': 180_000,
  '1': 90_000,
  '2': 45_000,
  '4': 22_500,
};

const PHASE_META: Record<string, { label: string; description: string }> = {
  normalize: { label: 'Normalize', description: 'Convert every claim and time to exact five-minute ticks.' },
  candidates: { label: 'Build candidates', description: 'Enumerate only legal attendance windows for every child.' },
  feasibility: { label: 'Prove feasibility', description: 'Measure whether all requested time can fit before placement.' },
  construct: { label: 'Initial placement', description: 'Place the least-flexible claims first in deterministic order.' },
  repair: { label: 'Repair & balance', description: 'Move, resize, swap, add, or remove blocks to reduce shortfall.' },
  daycare_realism: {
    label: 'Daycare realism',
    description: 'Redistribute Daycare attendance into realistic days while conserving each child’s exact scheduled ticks.',
  },
  validate: { label: 'Validate', description: 'Check capacity, time windows, overlap, and exact claim totals.' },
  audit: { label: 'Independent audit', description: 'Recalculate the result independently before certification.' },
  assignments: { label: 'Assignments', description: 'Replay the final certified child and day placements.' },
  complete: { label: 'Complete', description: 'Seal the deterministic result and its independent certification.' },
};

function asNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asRecord(value: unknown): LooseRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as LooseRecord
    : {};
}

function timeToTick(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value !== 'string') return 0;
  const [hours, minutes] = value.split(':').map(Number);
  return Number.isFinite(hours) && Number.isFinite(minutes)
    ? Math.round((hours * 60 + minutes) / TICK_MINUTES)
    : 0;
}

function normalizeBlocks(value: unknown): TimeBlock[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((block) => {
    if (Array.isArray(block) && block.length >= 2) {
      const startTick = timeToTick(block[0]);
      const endTick = timeToTick(block[1]);
      return endTick > startTick ? [{ startTick, endTick }] : [];
    }
    if (!block || typeof block !== 'object') return [];
    const item = block as Record<string, unknown>;
    const startTick = timeToTick(item.startTick ?? item.start_tick ?? item.start);
    const endTick = timeToTick(item.endTick ?? item.end_tick ?? item.end);
    return endTick > startTick ? [{ startTick, endTick }] : [];
  });
}

function entryBlocks(entry: Record<string, unknown>): TimeBlock[] {
  const blocks = [
    [entry.start_time ?? entry.startTime1, entry.end_time ?? entry.endTime1],
    [entry.start_time_2 ?? entry.startTime2, entry.end_time_2 ?? entry.endTime2],
  ];
  return blocks.flatMap(([start, end]) => {
    if (!start || !end) return [];
    const startTick = timeToTick(start);
    const endTick = timeToTick(end);
    return endTick > startTick ? [{ startTick, endTick }] : [];
  });
}

function eventDuration(event: Partial<EngineEvent>): number {
  if (event.durationTicks) return event.durationTicks;
  return (event.toBlocks || []).reduce((total, block) => total + block.endTick - block.startTick, 0);
}

function prettify(value: string): string {
  return value
    .replace(/^v3_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function phaseKey(value: string): string {
  const normalized = value.toLowerCase().replace(/^v3_/, '');
  if (normalized.includes('daycare_realism')) return 'daycare_realism';
  if (normalized.includes('independent') || normalized.includes('audit')) return 'audit';
  if (normalized.includes('assignment')) return 'assignments';
  return Object.keys(PHASE_META).find(key => normalized.includes(key)) || normalized || 'construct';
}

function parseVisualization(schedule: LooseRecord): EngineData {
  const telemetry = asRecord(schedule.visualization);
  const childNames = asRecord(schedule.child_names);
  const stats = asRecord(schedule.stats);
  const generationContext = asRecord(schedule.generation_context);
  const certification = asRecord(telemetry.certification);
  const rawEntries: LooseRecord[] = Array.isArray(schedule.entries)
    ? schedule.entries.map(asRecord)
    : [];
  const entriesByChild = new Map<string, string>();
  rawEntries.forEach((entry) => {
    const id = String(entry.child_id ?? entry.childId ?? '');
    const name = String(entry.child_name ?? entry.childName ?? childNames[id] ?? id);
    if (id) entriesByChild.set(id, name);
  });

  const rawEvents: LooseRecord[] = Array.isArray(telemetry.events)
    ? telemetry.events.map(asRecord)
    : [];
  let events: EngineEvent[] = rawEvents.map((event, index) => {
    const childId = event.childId ?? event.child_id;
    const fromBlocks = normalizeBlocks(event.fromBlocks ?? event.from_blocks);
    const toBlocks = normalizeBlocks(event.toBlocks ?? event.to_blocks ?? event.blocks);
    return {
      sequence: asNumber(event.sequence, index + 1),
      phase: phaseKey(String(event.phase || 'construct')),
      action: String(event.operation ?? event.action ?? 'place'),
      childId: childId ? String(childId) : undefined,
      childName: String(event.childName ?? event.child_name ?? entriesByChild.get(String(childId)) ?? childId ?? ''),
      fromDate: (event.fromDate ?? event.from_date)
        ? String(event.fromDate ?? event.from_date)
        : undefined,
      toDate: (event.toDate ?? event.to_date ?? event.date)
        ? String(event.toDate ?? event.to_date ?? event.date)
        : undefined,
      fromBlocks,
      toBlocks,
      durationTicks: asNumber(event.durationTicks ?? event.duration_ticks),
      reason: event.reason ? String(event.reason) : undefined,
      beforeShortfallTicks: (event.beforeShortfallTicks ?? event.before_shortfall_ticks) === undefined
        ? undefined
        : asNumber(event.beforeShortfallTicks ?? event.before_shortfall_ticks),
      afterShortfallTicks: (event.afterShortfallTicks ?? event.after_shortfall_ticks) === undefined
        ? undefined
        : asNumber(event.afterShortfallTicks ?? event.after_shortfall_ticks),
      iteration: event.iteration === undefined ? undefined : asNumber(event.iteration),
    };
  });

  const auditTrail: LooseRecord[] = Array.isArray(schedule.audit_trail)
    ? schedule.audit_trail.map(asRecord)
    : [];
  if (!events.length) {
    const traceEvents: EngineEvent[] = auditTrail
      .filter(item => !String(item.action || '').includes('assignment_translated'))
      .map((item, index) => {
        const details = asRecord(item.details);
        return {
          sequence: index + 1,
          phase: phaseKey(String(item.action || 'validate')),
          action: String(item.action || 'checkpoint').replace(/^v3_/, ''),
          childId: item.child_id ? String(item.child_id) : undefined,
          childName: item.child_id ? (entriesByChild.get(String(item.child_id)) || String(item.child_id)) : undefined,
          fromDate: undefined,
          toDate: item.date ? String(item.date) : undefined,
          fromBlocks: [],
          toBlocks: normalizeBlocks(details.blocks),
          durationTicks: asNumber(details.durationTicks ?? details.duration_ticks),
          reason: item.reason ? String(item.reason) : undefined,
          beforeShortfallTicks: details.beforeShortfallTicks === undefined
            ? undefined
            : asNumber(details.beforeShortfallTicks),
          afterShortfallTicks: details.afterShortfallTicks === undefined
            ? undefined
            : asNumber(details.afterShortfallTicks),
        };
      });
    const placementEvents: EngineEvent[] = rawEntries.map((entry, index) => {
      const childId = String(entry.child_id ?? entry.childId ?? '');
      const blocks = entryBlocks(entry);
      return {
        sequence: traceEvents.length + index + 1,
        phase: 'assignments',
        action: 'place',
        childId,
        childName: String(entry.child_name ?? entry.childName ?? childNames[childId] ?? childId),
        toDate: String(entry.date ?? ''),
        fromBlocks: [],
        toBlocks: blocks,
        durationTicks: blocks.reduce((sum, block) => sum + block.endTick - block.startTick, 0),
        reason: 'Final V3 assignment from the saved schedule',
      };
    });
    events = [...traceEvents, ...placementEvents];
  }
  events = events.sort((left, right) => left.sequence - right.sequence)
    .map((event, index) => ({ ...event, sequence: index + 1, durationTicks: eventDuration(event) }));

  const rawChildren: LooseRecord[] = Array.isArray(telemetry.children)
    ? telemetry.children.map(asRecord)
    : [];
  const childrenMap = new Map<string, string>();
  rawChildren.forEach((child) => {
    const id = String(child.id ?? child.childId ?? child.child_id ?? '');
    if (id) childrenMap.set(id, String(child.name ?? child.childName ?? childNames[id] ?? id));
  });
  events.forEach(event => {
    if (event.childId) childrenMap.set(event.childId, event.childName || childrenMap.get(event.childId) || event.childId);
  });

  const phaseOrder: string[] = [];
  const configuredPhaseMap = new Map<string, EnginePhase>();
  if (Array.isArray(telemetry.phases)) {
    telemetry.phases.forEach((rawPhase: unknown) => {
        const phase = asRecord(rawPhase);
        const key = phaseKey(String(phase.key ?? phase.phase ?? phase.name ?? rawPhase));
        if (!phaseOrder.includes(key)) phaseOrder.push(key);
        const existing = configuredPhaseMap.get(key);
        configuredPhaseMap.set(key, {
          key,
          label: existing?.label ?? String(phase.label ?? PHASE_META[key]?.label ?? prettify(key)),
          description: existing?.description ?? String(phase.description ?? PHASE_META[key]?.description ?? ''),
          outcome: phase.action === undefined ? existing?.outcome : String(phase.action),
        });
      });
  }
  const configuredPhases = [...configuredPhaseMap.values()];
  events.forEach(event => {
    if (!phaseOrder.includes(event.phase)) phaseOrder.push(event.phase);
  });
  const phases = configuredPhases.length
    ? configuredPhases
    : phaseOrder.map(key => ({ key, label: PHASE_META[key]?.label || prettify(key), description: PHASE_META[key]?.description }));

  const dates = Array.from(new Set([
    ...(Array.isArray(telemetry.dates) ? telemetry.dates.map(String) : []),
    ...(Array.isArray(telemetry.dailyCapacityPeaks)
      ? telemetry.dailyCapacityPeaks.map(item => String(asRecord(item).date || '')).filter(Boolean)
      : []),
    ...events.flatMap(event => [event.fromDate, event.toDate]).filter(Boolean) as string[],
  ])).sort();
  const requestedTicks = asNumber(
    telemetry?.requestedTicks
      ?? telemetry?.requested_ticks
      ?? certification.requestedTicks
      ?? certification.requested_ticks,
    Math.round(asNumber(stats.requested_hours) * 12),
  );
  const scheduledTicks = asNumber(
    telemetry?.scheduledTicks
      ?? telemetry?.scheduled_ticks
      ?? certification.scheduledTicks
      ?? certification.scheduled_ticks,
    Math.round(asNumber(stats.total_hours_scheduled) * 12),
  );
  const certified = Boolean(
    telemetry?.certified
    ?? certification.certified
    ?? (certification.auditValid === undefined && certification.exactClaims === undefined
      ? undefined
      : certification.auditValid === true
        && certification.exactClaims === true
        && certification.feasible !== false
        && (!Array.isArray(certification.violationCodes) || certification.violationCodes.length === 0))
    ?? (String(schedule.algorithm_version || '').startsWith('3.')
      && asNumber(stats.constraint_violations) === 0
      && Math.abs(asNumber(stats.hours_shortfall)) < 0.001),
  );

  return {
    version: String(schedule.algorithm_version ?? `telemetry schema ${telemetry?.version ?? 1}`),
    phases,
    events,
    children: [...childrenMap].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name)),
    dates,
    capacity: asNumber(telemetry.capacity, asNumber(generationContext.room_capacity, 1)),
    requestedTicks,
    scheduledTicks,
    certified,
    source: rawEvents.length ? 'telemetry' : 'audit',
  };
}

function assignmentKey(childId: string, date: string): string {
  return `${childId}::${date}`;
}

function replayAssignments(events: EngineEvent[], cursor: number): Map<string, Assignment> {
  const assignments = new Map<string, Assignment>();
  events.slice(0, cursor + 1).forEach(event => {
    if (!event.childId) return;
    if (event.fromDate) assignments.delete(assignmentKey(event.childId, event.fromDate));
    const action = event.action.toLowerCase();
    if (action.includes('remove') && !event.toDate) return;
    if (event.toDate && event.toBlocks.length) {
      assignments.set(assignmentKey(event.childId, event.toDate), {
        childId: event.childId,
        childName: event.childName || event.childId,
        date: event.toDate,
        blocks: event.toBlocks,
      });
    }
  });
  return assignments;
}

function formatTick(tick: number): string {
  const minutes = tick * TICK_MINUTES;
  const hours = Math.floor(minutes / 60);
  const minute = minutes % 60;
  const suffix = hours >= 12 ? 'PM' : 'AM';
  const displayHour = hours % 12 || 12;
  return `${displayHour}:${String(minute).padStart(2, '0')} ${suffix}`;
}

function formatBlocks(blocks: TimeBlock[]): string {
  return blocks.length
    ? blocks.map(block => `${formatTick(block.startTick)}–${formatTick(block.endTick)}`).join(' · ')
    : 'None';
}

function formatDate(value?: string): string {
  if (!value) return 'No date';
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString('en-CA', { weekday: 'short', month: 'short', day: 'numeric' });
}

function actionTone(action: string): string {
  const value = action.toLowerCase();
  if (value.includes('remove')) return 'bg-red-100 text-red-700';
  if (value.includes('swap') || value.includes('move')) return 'bg-violet-100 text-violet-700';
  if (value.includes('resize')) return 'bg-amber-100 text-amber-700';
  if (value.includes('audit') || value.includes('pass') || value.includes('certif')) return 'bg-emerald-100 text-emerald-700';
  return 'bg-sky-100 text-sky-700';
}

function realismOutcomeMeta(outcome?: string): {
  label: string;
  marker: string;
  buttonClass: string;
  markerClass: string;
  badgeClass: string;
} | null {
  if (!outcome) return null;
  const normalized = outcome.toLowerCase();
  if (normalized === 'applied') {
    return {
      label: 'Applied',
      marker: '✓',
      buttonClass: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
      markerClass: 'bg-emerald-500 text-slate-950',
      badgeClass: 'bg-emerald-400/15 text-emerald-200',
    };
  }
  if (normalized === 'rolled_back') {
    return {
      label: 'Rolled back',
      marker: '↩',
      buttonClass: 'border-rose-400/40 bg-rose-400/10 text-rose-200',
      markerClass: 'bg-rose-400 text-slate-950',
      badgeClass: 'bg-rose-400/15 text-rose-200',
    };
  }
  if (normalized === 'skipped') {
    return {
      label: 'Skipped',
      marker: '–',
      buttonClass: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
      markerClass: 'bg-amber-400 text-slate-950',
      badgeClass: 'bg-amber-400/15 text-amber-200',
    };
  }
  return {
    label: prettify(outcome),
    marker: '·',
    buttonClass: 'border-slate-600 bg-slate-800 text-slate-300',
    markerClass: 'bg-slate-600 text-white',
    badgeClass: 'bg-slate-700 text-slate-200',
  };
}

const CapacityTimeline: React.FC<{
  assignments: Map<string, Assignment>;
  date: string;
  capacity: number;
  activeEvent?: EngineEvent;
}> = ({ assignments, date, capacity, activeEvent }) => {
  const occupancy = useMemo(() => {
    const values = Array.from({ length: 288 }, () => 0);
    assignments.forEach(assignment => {
      if (assignment.date !== date) return;
      assignment.blocks.forEach(block => {
        for (let tick = Math.max(0, block.startTick); tick < Math.min(288, block.endTick); tick += 1) values[tick] += 1;
      });
    });
    return values;
  }, [assignments, date]);
  const activeTicks = occupancy
    .map((value, tick) => ({ value, tick }))
    .filter(point => point.value > 0);
  const startTick = activeTicks.length ? Math.max(0, activeTicks[0].tick - 12) : 84;
  const endTick = activeTicks.length ? Math.min(288, activeTicks[activeTicks.length - 1].tick + 13) : 216;
  const width = 960;
  const height = 230;
  const padding = { left: 48, right: 18, top: 18, bottom: 34 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const safeCapacity = Math.max(1, capacity);
  const x = (tick: number) => padding.left + (tick - startTick) / Math.max(1, endTick - startTick) * plotWidth;
  const y = (value: number) => padding.top + plotHeight - Math.min(value, safeCapacity) / safeCapacity * plotHeight;
  const points = Array.from({ length: endTick - startTick + 1 }, (_, index) => {
    const tick = startTick + index;
    return `${x(tick)},${y(occupancy[tick] || 0)}`;
  }).join(' ');
  const areaPoints = `${x(startTick)},${y(0)} ${points} ${x(endTick)},${y(0)}`;
  const peak = Math.max(0, ...occupancy);
  const tickLabels = Array.from({ length: Math.floor((endTick - startTick) / 24) + 1 }, (_, index) => startTick + index * 24);
  const activeBlock = activeEvent?.toDate === date ? activeEvent.toBlocks[0] : undefined;

  return (
    <div className="min-w-0">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-900">Room occupancy · {formatDate(date)}</p>
          <p className="text-xs text-slate-500">Every point is one five-minute capacity check</p>
        </div>
        <p className="text-sm font-semibold text-slate-700">Peak {peak} / {capacity}</p>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Occupancy for ${formatDate(date)} peaks at ${peak} of ${capacity}`}
      >
        <defs>
          <linearGradient id="v3-capacity-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#8967A4" stopOpacity="0.42" />
            <stop offset="100%" stopColor="#8967A4" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        {[0, Math.round(safeCapacity / 2), safeCapacity].map(value => (
          <g key={value}>
            <line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} stroke="#cbd5e1" strokeWidth="1" />
            <text x={padding.left - 10} y={y(value) + 4} textAnchor="end" className="fill-slate-500 text-[11px]">{value}</text>
          </g>
        ))}
        {activeBlock && (
          <rect
            x={x(activeBlock.startTick)}
            y={padding.top}
            width={Math.max(2, x(activeBlock.endTick) - x(activeBlock.startTick))}
            height={plotHeight}
            fill="#f59e0b"
            opacity="0.12"
          />
        )}
        <polygon points={areaPoints} fill="url(#v3-capacity-area)" className="transition-all duration-300 motion-reduce:transition-none" />
        <polyline points={points} fill="none" stroke="#8967A4" strokeWidth="3" strokeLinejoin="round" className="transition-all duration-300 motion-reduce:transition-none" />
        <line x1={padding.left} x2={width - padding.right} y1={y(safeCapacity)} y2={y(safeCapacity)} stroke="#ef4444" strokeWidth="2" strokeDasharray="8 6" />
        {tickLabels.map(tick => (
          <text key={tick} x={x(tick)} y={height - 8} textAnchor="middle" className="fill-slate-500 text-[11px]">
            {formatTick(tick).replace(':00', '')}
          </text>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-full bg-primary-500" /> Occupancy</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 border-t-2 border-dashed border-red-500" /> Licensed ceiling</span>
        {activeBlock && <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-full bg-amber-300" /> Active change</span>}
      </div>
    </div>
  );
};

const EngineRoomPhase: React.FC<EngineRoomPhaseProps> = ({
  activeBatchId,
  scheduleResult,
  onContinueToReview,
  onBackToConfigure,
}) => {
  const [schedule, setSchedule] = useState<LooseRecord | null>(null);
  const [cursor, setCursor] = useState(-1);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState('1');
  const [selectedDate, setSelectedDate] = useState('');
  const [childSearch, setChildSearch] = useState('');

  useEffect(() => {
    if (scheduleResult) {
      setSchedule(asRecord(scheduleResult));
      return;
    }
    if (!activeBatchId) {
      setSchedule(null);
      return;
    }
    const raw = sessionStorage.getItem(`caresync:schedule-batch:${activeBatchId}`);
    try {
      setSchedule(raw ? asRecord(JSON.parse(raw)) : null);
    } catch {
      setSchedule(null);
    }
  }, [activeBatchId, scheduleResult]);

  const data = useMemo(() => schedule ? parseVisualization(schedule) : null, [schedule]);
  const lastIndex = Math.max(-1, (data?.events.length || 0) - 1);

  useEffect(() => {
    if (!data) return;
    setCursor(data.events.length ? 0 : -1);
    setSelectedDate(data.dates[0] || '');
    setPlaying(data.events.length > 1);
  }, [data]);

  useEffect(() => {
    if (!playing || !data?.events.length) return undefined;
    // Small runs stay slow enough to study event-by-event. Real monthly runs
    // are adaptively paced so thousands of committed placements still finish.
    const delay = Math.min(
      PLAYBACK_DELAYS[speed],
      Math.max(20, PLAYBACK_TARGETS[speed] / data.events.length),
    );
    const timer = window.setInterval(() => {
      setCursor(current => {
        if (current >= data.events.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, delay);
    return () => window.clearInterval(timer);
  }, [playing, speed, data]);

  const assignments = useMemo(
    () => replayAssignments(data?.events || [], cursor),
    [data, cursor],
  );
  const activeEvent = cursor >= 0 ? data?.events[cursor] : undefined;
  useEffect(() => {
    const eventDate = activeEvent?.toDate || activeEvent?.fromDate;
    if (eventDate) setSelectedDate(eventDate);
  }, [activeEvent]);

  const scheduledNow = useMemo(() => {
    let total = 0;
    assignments.forEach(assignment => assignment.blocks.forEach(block => { total += block.endTick - block.startTick; }));
    return total;
  }, [assignments]);
  const visibleEvents = useMemo(() => {
    const query = childSearch.trim().toLowerCase();
    return (data?.events || []).filter(event => {
      const matchesChild = !query || `${event.childName || ''} ${event.childId || ''}`.toLowerCase().includes(query);
      const matchesDate = !selectedDate || event.fromDate === selectedDate || event.toDate === selectedDate || (!event.fromDate && !event.toDate);
      return matchesChild && matchesDate;
    });
  }, [data, childSearch, selectedDate]);
  const currentPhase = activeEvent?.phase || data?.phases[0]?.key;
  const completed = cursor >= lastIndex && lastIndex >= 0;
  const displayedPhase = completed && data?.phases.some(phase => phase.key === 'complete')
    ? 'complete'
    : currentPhase;
  const displayedPhaseIndex = data?.phases.findIndex(phase => phase.key === displayedPhase) ?? -1;
  const exactCompletion = data?.requestedTicks
    ? Math.min(100, scheduledNow / data.requestedTicks * 100)
    : completed ? 100 : 0;
  const phaseEventIndexes = useMemo(() => {
    const indexes = new Map<string, number>();
    data?.events.forEach((event, index) => {
      if (!indexes.has(event.phase)) indexes.set(event.phase, index);
    });
    return indexes;
  }, [data]);
  const daycareRealismPhase = data?.phases.find(phase => phase.key === 'daycare_realism');
  const daycareRealismOutcome = realismOutcomeMeta(daycareRealismPhase?.outcome);

  if (!activeBatchId || !schedule || !data) {
    return (
      <div className="flex min-h-[32rem] flex-col items-center justify-center px-6 text-center">
        <div className="mb-5 rounded-2xl bg-slate-100 p-4"><BoltIcon className="h-10 w-10 text-slate-500" /></div>
        <h2 className="text-xl font-bold text-slate-900">No engine replay is loaded</h2>
        <p className="mt-2 max-w-md text-sm text-slate-500">Generate a V3 schedule first. Its deterministic trace will appear here automatically.</p>
        {onBackToConfigure && <button type="button" className="btn btn-primary mt-6" onClick={onBackToConfigure}>Return to Generate</button>}
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-950 px-4 py-5 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-violet-400/30 bg-violet-400/10 px-2.5 py-1 text-xs font-semibold text-violet-200">
                <SparklesIcon className="h-4 w-4" /> V3 ENGINE ROOM
              </span>
              <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-400">{data.version}</span>
              <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-400">
                {data.source === 'telemetry' ? 'Full decision telemetry' : 'Certified audit replay'}
              </span>
            </div>
            <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Watch the scheduler think</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-400">
              Follow each deterministic placement and repair while room capacity is rechecked every five minutes.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {onBackToConfigure && (
              <button type="button" className="btn border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800" onClick={onBackToConfigure}>
                <ArrowLeftIcon className="h-4 w-4" /> Configure
              </button>
            )}
            <button type="button" className="btn btn-primary" onClick={onContinueToReview}>
              Review schedule <ArrowLongRightIcon className="h-4 w-4" />
            </button>
          </div>
        </header>

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Replay metrics">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Progress</p>
            <p className="mt-1 text-2xl font-bold text-white">{Math.max(0, cursor + 1)}<span className="text-sm font-normal text-slate-500"> / {data.events.length}</span></p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Placed now</p>
            <p className="mt-1 text-2xl font-bold text-white">{(scheduledNow / 12).toLocaleString(undefined, { maximumFractionDigits: 1 })}<span className="text-sm font-normal text-slate-500"> hours</span></p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Exact target</p>
            <p className="mt-1 text-2xl font-bold text-white">{exactCompletion.toFixed(1)}<span className="text-sm font-normal text-slate-500">%</span></p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Certification</p>
            <p className={`mt-1 flex items-center gap-2 text-lg font-bold ${completed && data.certified ? 'text-emerald-300' : 'text-amber-300'}`}>
              {completed && data.certified ? <><CheckBadgeIcon className="h-6 w-6" /> Passed</> : <><ArrowPathIcon className={`h-5 w-5 ${playing ? 'animate-spin motion-reduce:animate-none' : ''}`} /> {completed ? 'Review' : 'Pending'}</>}
            </p>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-3 sm:p-4" aria-label="Playback controls">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Previous event"
                className="rounded-lg border border-slate-700 p-2 text-slate-300 transition hover:bg-slate-800 disabled:opacity-40"
                disabled={cursor <= 0}
                onClick={() => { setPlaying(false); setCursor(value => Math.max(0, value - 1)); }}
              ><ChevronLeftIcon className="h-5 w-5" /></button>
              <button
                type="button"
                className="inline-flex min-w-28 items-center justify-center gap-2 rounded-lg bg-violet-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-violet-400"
                onClick={() => {
                  if (completed) setCursor(0);
                  setPlaying(value => completed ? true : !value);
                }}
              >
                {playing ? <><PauseIcon className="h-5 w-5" /> Pause</> : completed ? <><ArrowPathIcon className="h-5 w-5" /> Replay</> : <><PlayIcon className="h-5 w-5" /> Play</>}
              </button>
              <button
                type="button"
                aria-label="Next event"
                className="rounded-lg border border-slate-700 p-2 text-slate-300 transition hover:bg-slate-800 disabled:opacity-40"
                disabled={cursor >= lastIndex}
                onClick={() => { setPlaying(false); setCursor(value => Math.min(lastIndex, value + 1)); }}
              ><ChevronRightIcon className="h-5 w-5" /></button>
            </div>
            <label className="flex min-w-0 flex-1 items-center gap-3 text-xs font-medium text-slate-400">
              <span className="sr-only">Replay position</span>
              <input
                type="range"
                min={0}
                max={Math.max(0, lastIndex)}
                value={Math.max(0, cursor)}
                onChange={event => { setPlaying(false); setCursor(Number(event.target.value)); }}
                className="h-2 min-w-0 flex-1 cursor-pointer accent-violet-500"
              />
              <span className="w-20 text-right tabular-nums">Step {Math.max(0, cursor + 1)}</span>
            </label>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-400">
              Speed
              <select className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" value={speed} onChange={event => setSpeed(event.target.value)}>
                {Object.keys(PLAYBACK_DELAYS).map(value => <option key={value} value={value}>{value}×</option>)}
              </select>
            </label>
          </div>
        </section>

        <nav className="overflow-x-auto pb-1" aria-label="V3 scheduling phases">
          <ol className="flex min-w-max items-center gap-2">
            {data.phases.map((phase, index) => {
              const eventIndex = phaseEventIndexes.get(phase.key) ?? -1;
              const active = displayedPhase === phase.key;
              const passed = displayedPhaseIndex > index;
              const realismOutcome = phase.key === 'daycare_realism'
                ? realismOutcomeMeta(phase.outcome)
                : null;
              const phaseButtonClass = realismOutcome
                ? realismOutcome.buttonClass
                : active
                  ? 'border-violet-400 bg-violet-400/15 text-white'
                  : passed
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                    : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800';
              const markerClass = realismOutcome
                ? realismOutcome.markerClass
                : active
                  ? 'bg-violet-500 text-white'
                  : passed
                    ? 'bg-emerald-500 text-slate-950'
                    : 'bg-slate-800';
              return (
                <React.Fragment key={`${phase.key}-${index}`}>
                  {index > 0 && <li aria-hidden="true" className={`h-px w-8 ${passed || active ? 'bg-violet-400' : 'bg-slate-700'}`} />}
                  <li>
                    <button
                      type="button"
                      disabled={eventIndex < 0}
                      aria-current={active ? 'step' : undefined}
                      onClick={() => { setPlaying(false); setCursor(eventIndex); }}
                      aria-label={`${phase.label}${realismOutcome ? `, backend trace outcome ${realismOutcome.label}` : ''}`}
                      className={`group flex items-center gap-2 rounded-xl border px-3 py-2 text-left transition ${phaseButtonClass}`}
                    >
                      <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${markerClass}`}>
                        {realismOutcome?.marker ?? (passed ? '✓' : index + 1)}
                      </span>
                      <span>
                        <span className="flex items-center gap-2 text-xs font-semibold">
                          {phase.label}
                          {realismOutcome && (
                            <span className={`rounded-full px-1.5 py-0.5 text-[9px] uppercase tracking-wide ${realismOutcome.badgeClass}`}>
                              {realismOutcome.label}
                            </span>
                          )}
                        </span>
                        <span className="block max-w-44 truncate text-[10px] opacity-70">{phase.description}</span>
                      </span>
                    </button>
                  </li>
                </React.Fragment>
              );
            })}
          </ol>
        </nav>

        {daycareRealismPhase && daycareRealismOutcome && (
          <section
            className={`flex flex-col gap-2 rounded-2xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${daycareRealismOutcome.buttonClass}`}
            aria-label={`Daycare realism backend trace outcome: ${daycareRealismOutcome.label}`}
          >
            <div className="flex min-w-0 items-center gap-3">
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-bold ${daycareRealismOutcome.markerClass}`}>
                {daycareRealismOutcome.marker}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold">Daycare realism · {daycareRealismOutcome.label}</p>
                <p className="text-xs opacity-80">{daycareRealismPhase.description}</p>
              </div>
            </div>
            <span className="shrink-0 text-[10px] uppercase tracking-wider opacity-70">Reported by V3 phase trace</span>
          </section>
        )}

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
          <main className="min-w-0 space-y-5">
            <section className="rounded-2xl border border-slate-800 bg-white p-4 text-slate-900 shadow-2xl shadow-black/20 sm:p-6">
              {selectedDate ? (
                <CapacityTimeline assignments={assignments} date={selectedDate} capacity={data.capacity} activeEvent={activeEvent} />
              ) : (
                <div className="py-16 text-center text-sm text-slate-500">No dated assignment is selected yet.</div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 sm:p-5">
              <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h3 className="font-bold text-white">Month pressure map</h3>
                  <p className="text-xs text-slate-500">Select a day to inspect its five-minute occupancy</p>
                </div>
                <label className="text-xs font-medium text-slate-400">
                  Day
                  <select className="ml-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200" value={selectedDate} onChange={event => setSelectedDate(event.target.value)}>
                    {data.dates.map(date => <option key={date} value={date}>{formatDate(date)}</option>)}
                  </select>
                </label>
              </div>
              <div className="grid grid-cols-4 gap-2 sm:grid-cols-7 lg:grid-cols-11">
                {data.dates.map(date => {
                  const dateAssignments = [...assignments.values()].filter(item => item.date === date);
                  const active = date === selectedDate;
                  const touched = date === activeEvent?.fromDate || date === activeEvent?.toDate;
                  return (
                    <button
                      type="button"
                      key={date}
                      onClick={() => setSelectedDate(date)}
                      aria-pressed={active}
                      aria-label={`${formatDate(date)}, ${dateAssignments.length} children placed`}
                      className={`relative min-h-16 rounded-xl border p-2 text-left transition ${active ? 'border-violet-400 bg-violet-400/20' : 'border-slate-700 bg-slate-950 hover:border-slate-600'} ${touched ? 'ring-2 ring-amber-400/50' : ''}`}
                    >
                      <span className="block text-xs text-slate-500">{new Date(`${date}T12:00:00`).toLocaleDateString('en-CA', { weekday: 'short' })}</span>
                      <span className="block text-sm font-bold text-white">{date.slice(-2)}</span>
                      <span className="mt-1 block text-[10px] text-slate-400">{dateAssignments.length} children</span>
                    </button>
                  );
                })}
              </div>
            </section>
          </main>

          <aside className="min-w-0 space-y-5">
            <section className="rounded-2xl border border-violet-400/30 bg-gradient-to-br from-violet-500/15 to-slate-900 p-5" aria-live="polite">
              <div className="mb-4 flex items-center justify-between gap-3">
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${actionTone(activeEvent?.action || 'checkpoint')}`}>{prettify(activeEvent?.action || 'Waiting')}</span>
                <span className="text-xs tabular-nums text-slate-500">
                  #{Math.max(0, cursor + 1)}{activeEvent?.iteration !== undefined ? ` · iteration ${activeEvent.iteration}` : ''}
                </span>
              </div>
              <h3 className="text-lg font-bold text-white">{activeEvent?.childName || PHASE_META[currentPhase || '']?.label || 'Engine checkpoint'}</h3>
              <p className="mt-1 text-sm text-slate-400">{activeEvent?.reason || PHASE_META[currentPhase || '']?.description || 'The engine recorded this deterministic decision.'}</p>
              {(activeEvent?.fromDate || activeEvent?.toDate) && (
                <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-xl border border-slate-700 bg-slate-950/60 p-3">
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Before</p>
                    <p className="truncate text-xs font-semibold text-slate-200">{formatDate(activeEvent.fromDate)}</p>
                    <p className="mt-1 text-[10px] text-slate-500">{formatBlocks(activeEvent.fromBlocks)}</p>
                  </div>
                  <ArrowLongRightIcon className="h-5 w-5 text-violet-400" />
                  <div className="min-w-0 text-right">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">After</p>
                    <p className="truncate text-xs font-semibold text-white">{formatDate(activeEvent.toDate)}</p>
                    <p className="mt-1 text-[10px] text-violet-300">{formatBlocks(activeEvent.toBlocks)}</p>
                  </div>
                </div>
              )}
              {(activeEvent?.beforeShortfallTicks !== undefined || activeEvent?.afterShortfallTicks !== undefined) && (
                <div className="mt-4 flex items-center justify-between text-xs">
                  <span className="text-slate-500">Claim shortfall</span>
                  <span className="font-semibold text-slate-200">
                    {((activeEvent.beforeShortfallTicks || 0) / 12).toFixed(1)}h → {((activeEvent.afterShortfallTicks || 0) / 12).toFixed(1)}h
                  </span>
                </div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <h3 className="font-bold text-white">Decision feed</h3>
                  <p className="text-xs text-slate-500">{visibleEvents.length} matching events</p>
                </div>
                <AdjustmentsHorizontalIcon className="h-5 w-5 text-slate-500" />
              </div>
              <label className="relative block">
                <span className="sr-only">Search children in decision feed</span>
                <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  type="search"
                  value={childSearch}
                  onChange={event => setChildSearch(event.target.value)}
                  placeholder="Search child…"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-9 pr-3 text-sm text-white placeholder:text-slate-600 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400/30"
                />
              </label>
              <div className="mt-3 max-h-[30rem] space-y-1 overflow-y-auto pr-1">
                {visibleEvents.slice(Math.max(0, visibleEvents.findIndex(event => event.sequence >= Math.max(1, cursor - 4)))).slice(0, 30).map(event => {
                  const selected = event.sequence - 1 === cursor;
                  return (
                    <button
                      type="button"
                      key={`${event.sequence}-${event.action}`}
                      onClick={() => { setPlaying(false); setCursor(event.sequence - 1); }}
                      className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition ${selected ? 'bg-violet-500/20 ring-1 ring-violet-400/50' : 'hover:bg-slate-800'}`}
                    >
                      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${selected ? 'bg-violet-400' : 'bg-slate-600'}`} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate text-xs font-semibold text-slate-200">{event.childName || prettify(event.phase)}</span>
                          <span className="shrink-0 text-[10px] text-slate-600">#{event.sequence}</span>
                        </span>
                        <span className="mt-0.5 block truncate text-[10px] text-slate-500">{prettify(event.action)}{event.toDate ? ` · ${formatDate(event.toDate)}` : ''}</span>
                      </span>
                    </button>
                  );
                })}
                {!visibleEvents.length && <p className="py-8 text-center text-xs text-slate-500">No decisions match these filters.</p>}
              </div>
            </section>

            {completed && (
              <section className={`rounded-2xl border p-5 ${data.certified ? 'border-emerald-400/30 bg-emerald-400/10' : 'border-amber-400/30 bg-amber-400/10'}`}>
                <div className="flex items-start gap-3">
                  {data.certified ? <ShieldCheckIcon className="h-8 w-8 shrink-0 text-emerald-300" /> : <ClockIcon className="h-8 w-8 shrink-0 text-amber-300" />}
                  <div>
                    <h3 className="font-bold text-white">{data.certified ? 'Independently certified' : 'Review is required'}</h3>
                    <p className="mt-1 text-xs text-slate-300">
                      {data.certified
                        ? `${(data.scheduledTicks / 12).toLocaleString(undefined, { maximumFractionDigits: 1 })} hours reconcile exactly with the normalized claims and no hard constraint was violated.`
                        : 'The replay is complete, but this result does not carry a passing V3 certification.'}
                    </p>
                  </div>
                </div>
              </section>
            )}
          </aside>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 py-4 text-xs text-slate-500">
          <span className="inline-flex items-center gap-2"><CalendarDaysIcon className="h-4 w-4" /> {data.dates.length} open days</span>
          <span className="inline-flex items-center gap-2"><UserGroupIcon className="h-4 w-4" /> Capacity {data.capacity}</span>
          <span className="inline-flex items-center gap-2"><BoltIcon className="h-4 w-4" /> Deterministic replay—same input, same decisions</span>
        </footer>
      </div>
    </div>
  );
};

export default EngineRoomPhase;
