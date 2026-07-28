export interface SchedulerState {
  phaseIndex: number;
  progress: number;
  iteration: number;
  running: boolean;
  completed: boolean;
}

export type SchedulerAction =
  | { type: 'start' }
  | { type: 'pause' }
  | { type: 'tick' }
  | { type: 'reset' }
  | { type: 'seek'; phaseIndex: number };

export const SCHEDULER_PHASE_COUNT = 6;

export const initialSchedulerState: SchedulerState = {
  phaseIndex: 0,
  progress: 0,
  iteration: 0,
  running: false,
  completed: false,
};

const clamp = (value: number, minimum: number, maximum: number) => Math.max(minimum, Math.min(maximum, value));

export function restoreSchedulerState(raw: string | null): SchedulerState {
  if (!raw) return initialSchedulerState;
  try {
    const parsed = JSON.parse(raw) as { version?: unknown; state?: Record<string, unknown> };
    if (parsed.version !== 1 || !parsed.state) return initialSchedulerState;
    const progress = typeof parsed.state.progress === 'number' && Number.isFinite(parsed.state.progress)
      ? clamp(parsed.state.progress, 0, 100)
      : 0;
    const completed = parsed.state.completed === true && progress === 100;
    const reachedPhase = Math.min(
      SCHEDULER_PHASE_COUNT - 1,
      Math.floor((progress / 100) * SCHEDULER_PHASE_COUNT),
    );
    const phaseIndex = completed
      ? SCHEDULER_PHASE_COUNT - 1
      : clamp(
          typeof parsed.state.phaseIndex === 'number' && Number.isFinite(parsed.state.phaseIndex)
            ? Math.floor(parsed.state.phaseIndex)
            : 0,
          0,
          reachedPhase,
        );
    return {
      phaseIndex,
      progress,
      iteration: typeof parsed.state.iteration === 'number' && Number.isFinite(parsed.state.iteration)
        ? Math.max(0, Math.floor(parsed.state.iteration))
        : 0,
      running: false,
      completed,
    };
  } catch {
    return initialSchedulerState;
  }
}

export function schedulerReducer(state: SchedulerState, action: SchedulerAction): SchedulerState {
  switch (action.type) {
    case 'start':
      return state.completed ? { ...initialSchedulerState, running: true } : { ...state, running: true };
    case 'pause':
      return { ...state, running: false };
    case 'reset':
      return initialSchedulerState;
    case 'seek': {
      const reachedPhase = state.completed
        ? SCHEDULER_PHASE_COUNT - 1
        : Math.min(SCHEDULER_PHASE_COUNT - 1, Math.floor((state.progress / 100) * SCHEDULER_PHASE_COUNT));
      const bounded = clamp(Math.floor(action.phaseIndex), 0, reachedPhase);
      return { ...state, phaseIndex: bounded, running: false };
    }
    case 'tick': {
      if (!state.running) return state;
      const nextProgress = Math.min(100, state.progress + 0.72);
      const nextPhase = Math.min(
        SCHEDULER_PHASE_COUNT - 1,
        Math.floor((nextProgress / 100) * SCHEDULER_PHASE_COUNT),
      );
      const finished = nextProgress >= 100;
      return {
        phaseIndex: finished ? SCHEDULER_PHASE_COUNT - 1 : nextPhase,
        progress: nextProgress,
        iteration: state.iteration + 1,
        running: !finished,
        completed: finished,
      };
    }
    default:
      return state;
  }
}
