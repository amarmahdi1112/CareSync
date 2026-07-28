import { describe, expect, it, vi } from 'vitest';
import { createExactChildcareCommand } from '../../api/childcareCommand';
import type { RoomPlacementPlan, RoomPlacementReview } from './roomsApi';
import { PlacementCommandSequenceError, runPlacementCommandSequence } from './placementCommandSequence';

function plan(index: number): RoomPlacementPlan {
  const review = {
    enrollment_id: `enrollment-${index}`,
    enrollment_version: index,
    effective_date: '2026-07-20',
  } as RoomPlacementReview;
  return {
    review,
    roomId: `room-${index}`,
    command: createExactChildcareCommand({ room_id: `room-${index}`, effective_date: review.effective_date }, index),
  };
}

describe('placement command sequence', () => {
  it('reports confirmed progress and never sends later plans after one unresolved command', async () => {
    const plans = [plan(1), plan(2), plan(3), plan(4)];
    const sent: string[] = [];
    const execute = vi.fn(async (current: RoomPlacementPlan) => {
      sent.push(current.review.enrollment_id);
      if (current === plans[2]) throw new Error('receipt unresolved');
      return current.review.enrollment_id;
    });
    const progress = vi.fn();

    const result = await runPlacementCommandSequence(plans, execute, progress).catch((caught) => caught);
    expect(result).toBeInstanceOf(PlacementCommandSequenceError);
    if (!(result instanceof PlacementCommandSequenceError)) throw new Error('Expected sequence failure.');
    expect(result.message).toBe('receipt unresolved');
    expect(result.completedResults).toEqual(['enrollment-1', 'enrollment-2']);
    expect(result.failedIndex).toBe(2);
    expect(result.total).toBe(4);
    expect(sent).toEqual(['enrollment-1', 'enrollment-2', 'enrollment-3']);
    expect(progress.mock.calls).toEqual([[1, 4], [2, 4]]);
    expect(execute).not.toHaveBeenCalledWith(plans[3]);
  });
});
