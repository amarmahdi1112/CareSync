import type { RoomPlacementPlan } from './roomsApi';

export class PlacementCommandSequenceError<Result> extends Error {
  readonly completedResults: readonly Result[];

  constructor(
    completedResults: readonly Result[],
    public readonly failedIndex: number,
    public readonly total: number,
    public readonly cause: unknown,
  ) {
    super(cause instanceof Error ? cause.message : 'The placement command sequence stopped.');
    this.name = 'PlacementCommandSequenceError';
    this.completedResults = Object.freeze([...completedResults]);
  }
}

/**
 * The durable childcare lane permits one unresolved command. Clear placements
 * therefore commit one-by-one; a failure stops before the next plan is sent.
 */
export async function runPlacementCommandSequence<Result>(
  plans: readonly RoomPlacementPlan[],
  execute: (plan: RoomPlacementPlan) => Promise<Result>,
  onProgress: (completed: number, total: number) => void,
): Promise<readonly Result[]> {
  const results: Result[] = [];
  for (const [index, plan] of plans.entries()) {
    try {
      const result = await execute(plan);
      results.push(result);
      onProgress(results.length, plans.length);
    } catch (caught) {
      throw new PlacementCommandSequenceError(results, index, plans.length, caught);
    }
  }
  return results;
}
