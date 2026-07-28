import { describe, expect, it } from 'vitest';
import {
  initialSchedulerState,
  restoreSchedulerState,
  schedulerReducer,
  SCHEDULER_PHASE_COUNT,
} from './schedulerMachine';

describe('scheduler preview state machine', () => {
  it('does not advance while paused', () => {
    expect(schedulerReducer(initialSchedulerState, { type: 'tick' })).toEqual(initialSchedulerState);
  });

  it('cannot seek into an unreached phase or manufacture certification', () => {
    const result = schedulerReducer(initialSchedulerState, { type: 'seek', phaseIndex: SCHEDULER_PHASE_COUNT - 1 });
    expect(result.phaseIndex).toBe(0);
    expect(result.progress).toBe(0);
    expect(result.completed).toBe(false);
  });

  it('finishes at exactly 100 percent and stops itself', () => {
    let state = schedulerReducer(initialSchedulerState, { type: 'start' });
    for (let index = 0; index < 1000 && !state.completed; index += 1) {
      state = schedulerReducer(state, { type: 'tick' });
    }
    expect(state.progress).toBe(100);
    expect(state.phaseIndex).toBe(SCHEDULER_PHASE_COUNT - 1);
    expect(state.running).toBe(false);
    expect(state.completed).toBe(true);
  });

  it('restores a versioned checkpoint but never resumes it automatically', () => {
    const state = restoreSchedulerState(JSON.stringify({
      version: 1,
      state: { phaseIndex: 3, progress: 54, iteration: 75, running: true, completed: false },
    }));
    expect(state).toMatchObject({ phaseIndex: 3, progress: 54, iteration: 75, running: false, completed: false });
  });

  it('rejects corrupt or unknown-version checkpoints', () => {
    expect(restoreSchedulerState('{nope')).toEqual(initialSchedulerState);
    expect(restoreSchedulerState(JSON.stringify({ version: 2, state: { progress: 100 } }))).toEqual(initialSchedulerState);
  });
});
