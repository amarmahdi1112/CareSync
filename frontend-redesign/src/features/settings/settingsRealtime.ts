export interface DraftReconciliation<T> {
  draft: T;
  baseline: T;
  dirty: boolean;
  remoteChangedWhileDirty: boolean;
}

export function draftsEqual<T extends object>(left: T, right: T): boolean {
  const keys = Object.keys(left) as Array<keyof T>;
  const rightKeys = Object.keys(right);
  return keys.length === rightKeys.length && keys.every((key) => left[key] === right[key]);
}

/**
 * Accepts a new canonical snapshot without destroying local edits. The baseline
 * always moves to the newest server value so an explicit reset loads that value.
 */
export function reconcileEditableDraft<T extends object>(
  current: T,
  previousBaseline: T | null,
  incoming: T,
): DraftReconciliation<T> {
  if (!previousBaseline) {
    return { draft: incoming, baseline: incoming, dirty: false, remoteChangedWhileDirty: false };
  }

  const wasDirty = !draftsEqual(current, previousBaseline);
  const differsFromIncoming = !draftsEqual(current, incoming);
  const remoteChanged = !draftsEqual(previousBaseline, incoming);
  const preserve = wasDirty && differsFromIncoming;

  return {
    draft: preserve ? current : incoming,
    baseline: incoming,
    dirty: preserve,
    remoteChangedWhileDirty: preserve && remoteChanged,
  };
}
