import { describe, expect, it } from 'vitest';
import { reconcileEditableDraft } from './settingsRealtime';

describe('settings realtime draft reconciliation', () => {
  it('loads the first canonical snapshot and replaces a clean draft on refresh', () => {
    const first = reconcileEditableDraft({ name: '' }, null, { name: 'North Centre' });
    expect(first).toEqual({ draft: { name: 'North Centre' }, baseline: { name: 'North Centre' }, dirty: false, remoteChangedWhileDirty: false });

    const refreshed = reconcileEditableDraft(first.draft, first.baseline, { name: 'North Campus' });
    expect(refreshed.draft).toEqual({ name: 'North Campus' });
    expect(refreshed.remoteChangedWhileDirty).toBe(false);
  });

  it('preserves a dirty draft during focus refresh without claiming a remote conflict', () => {
    const result = reconcileEditableDraft(
      { name: 'Local unsaved edit' },
      { name: 'Saved name' },
      { name: 'Saved name' },
    );
    expect(result.draft).toEqual({ name: 'Local unsaved edit' });
    expect(result.dirty).toBe(true);
    expect(result.remoteChangedWhileDirty).toBe(false);
  });

  it('preserves a dirty draft and reports when the canonical value also changed', () => {
    const result = reconcileEditableDraft(
      { name: 'Local unsaved edit' },
      { name: 'Old saved name' },
      { name: 'Remote saved edit' },
    );
    expect(result.draft).toEqual({ name: 'Local unsaved edit' });
    expect(result.baseline).toEqual({ name: 'Remote saved edit' });
    expect(result.remoteChangedWhileDirty).toBe(true);
  });

  it('becomes clean when the incoming canonical value matches the local edit', () => {
    const result = reconcileEditableDraft(
      { name: 'Same result' },
      { name: 'Old saved name' },
      { name: 'Same result' },
    );
    expect(result.draft).toEqual({ name: 'Same result' });
    expect(result.dirty).toBe(false);
    expect(result.remoteChangedWhileDirty).toBe(false);
  });
});
