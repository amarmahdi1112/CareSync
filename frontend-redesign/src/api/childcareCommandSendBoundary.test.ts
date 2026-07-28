import { describe, expect, it } from 'vitest';
import familyDrawerSource from '../features/families/FamilyDrawer.tsx?raw';
import childEditorSource from '../features/children/ChildEditor.tsx?raw';
import enrollmentEditorSource from '../features/children/EnrollmentEditor.tsx?raw';
import roomPlacementSource from '../features/rooms/RoomPlacementReviewDialog.tsx?raw';

const productionMutationSources = [
  familyDrawerSource,
  childEditorSource,
  enrollmentEditorSource,
  roomPlacementSource,
];

describe('0028 production command send boundaries', () => {
  it('binds all eleven family, child, enrollment, and placement sends to the journal callback id', () => {
    const boundSends = productionMutationSources.flatMap((source) => (
      source.match(/commandBoundToJournalOperation\((?:command|plan\.command), operationId\)/g) || []
    ));

    expect(boundSends).toHaveLength(11);
    expect(familyDrawerSource.match(/commandBoundToJournalOperation\(command, operationId\)/g)).toHaveLength(5);
    expect(childEditorSource.match(/commandBoundToJournalOperation\(command, operationId\)/g)).toHaveLength(2);
    expect(enrollmentEditorSource.match(/commandBoundToJournalOperation\(command, operationId\)/g)).toHaveLength(2);
    expect(roomPlacementSource.match(/commandBoundToJournalOperation\(plan\.command, operationId\)/g)).toHaveLength(2);
  });

  it('has no production recovery callback that discards the journal operation id', () => {
    expect(productionMutationSources.join('\n')).not.toMatch(
      /\},\s*\(\)\s*=>\s*(?:createFamily|updateFamily|replaceFamilyGuardian|replaceFamilyEmergencyContacts|archiveFamily|createChild|updateChild|createChildEnrollment|endChildEnrollment|approveRoomPlacement)\(/,
    );
  });

  it('binds enrollment action routes to their owning child and refetches canonical family state between staged commands', () => {
    expect(enrollmentEditorSource.match(/expectedActionOwnerId: child\.id/g)).toHaveLength(2);
    expect(roomPlacementSource.match(/expectedActionOwnerId: plan\.review\.child_id/g)).toHaveLength(2);
    expect(familyDrawerSource).toMatch(
      /purpose === 'edit'[\s\S]{0,180}?fetchFamilyDetail\(metadata\.expectedTargetId, organizationId, signal\)/,
    );
    expect(familyDrawerSource).toContain('fetchFamilyDetail(detail.id, organizationId, controller.signal)');
  });

  it('retires local pending UI only for the exact acknowledged terminal-absence operation', () => {
    for (const source of productionMutationSources) {
      expect(source).toContain('childcareFinalAbsenceAcknowledged(');
      expect(source).toContain('commandRecovery.lastFinalAbsenceAcknowledgedOperationId');
    }
  });

  it('keeps confirmed placement progress visible while the canonical queue refreshes', () => {
    expect(roomPlacementSource).toContain('sequenceError?.completedResults.length');
    expect(roomPlacementSource).toContain('saved before the sequence stopped');
    expect(roomPlacementSource.match(/setNotice\(""\)/g)).toHaveLength(3);
  });

  it('keeps production footer and confirmation mutations behind the lane-blocked lock', () => {
    for (const source of [familyDrawerSource, childEditorSource, enrollmentEditorSource]) {
      expect(source).toMatch(
        /const mutationLocked = childcareMutationControlDisabled\(\s*commandRecovery\.laneBlocked,/,
      );
    }
    expect(roomPlacementSource).toMatch(
      /const placementMutationLocked = childcareMutationControlDisabled\(\s*commandRecovery\.laneBlocked,/,
    );

    expect(familyDrawerSource.match(/type="submit"[\s\S]{0,180}?disabled=\{mutationLocked(?: \|\| Boolean\(pendingCareRemoval\))?\}/g)).toHaveLength(2);
    expect(familyDrawerSource).toContain('onClick={archive} disabled={mutationLocked}');
    expect(childEditorSource).toMatch(/type="submit"[\s\S]{0,100}?disabled=\{mutationLocked\}/);
    expect(enrollmentEditorSource).toContain('onClick={endEnrollment} disabled={mutationLocked}');
    expect(enrollmentEditorSource).toMatch(/type="submit"[\s\S]{0,140}?disabled=\{mutationLocked \|\| !selectedFacilityIsActive\}/);
    expect(roomPlacementSource).toContain('disabled={!clearPlan.length || placementMutationLocked}');
    expect(roomPlacementSource).toContain('!selected[review.enrollment_id] || placementMutationLocked');
  });
});
