import assert from 'node:assert/strict';
import test from 'node:test';

import {
  importedClaimIdentityConflict,
  prepareImportedClaimsForScheduling,
  type ImportedClaimIdentityRow,
} from '../src/pages/scheduling/utils/importedClaimIdentity.ts';

const matchingChild = {
  id: 'child-faxima',
  date_of_birth: '2014-11-06',
};

function claim(overrides: Partial<ImportedClaimIdentityRow>): ImportedClaimIdentityRow {
  return {
    id: 'claim-1',
    child_name: 'Fatima Mohamed',
    hours_claimed: 90,
    matched_child_id: matchingChild.id,
    date_of_birth: '2014-11-06',
    care_category: 'SchoolAge',
    ...overrides,
  };
}

test('detects an explicit DOB contradiction without treating unknown DOBs as conflicts', () => {
  assert.deepEqual(
    importedClaimIdentityConflict(
      claim({ id: 'claim-faxima', date_of_birth: '2013-11-06' }),
      matchingChild,
    ),
    {
      code: 'DATE_OF_BIRTH_MISMATCH',
      matchedChildId: matchingChild.id,
      claimDateOfBirth: '2013-11-06',
      childDateOfBirth: '2014-11-06',
    },
  );
  assert.equal(
    importedClaimIdentityConflict(claim({ date_of_birth: null }), matchingChild),
    undefined,
  );
});

test('keeps DOB-consistent aliases merged while splitting a contradictory source row', () => {
  const result = prepareImportedClaimsForScheduling(
    [
      claim({ id: 'claim-fatima', child_name: 'Fatima Mohamed', hours_claimed: 90 }),
      claim({
        id: 'claim-faxima',
        child_name: 'Faxima Mohamed',
        date_of_birth: '2013-11-06',
        hours_claimed: 73,
      }),
    ],
    [matchingChild],
  );

  assert.equal(result.rows.length, 2);
  assert.equal(result.mergedRowCount, 0);
  assert.equal(result.identityConflictCount, 1);
  assert.deepEqual(result.identityConflictNames, ['Faxima Mohamed']);
  assert.deepEqual(
    result.rows.map((row) => ({
      id: row.id,
      scheduleId: row.schedule_child_id,
      usesRealChild: row.uses_real_child,
      hours: Number(row.corrected_hours ?? row.hours_claimed),
    })),
    [
      {
        id: 'claim-fatima',
        scheduleId: matchingChild.id,
        usesRealChild: true,
        hours: 90,
      },
      {
        id: 'claim-faxima',
        scheduleId: 'imported-claim:claim-faxima',
        usesRealChild: false,
        hours: 73,
      },
    ],
  );
});

test('continues summing truly repeated rows for the same DOB-consistent child', () => {
  const result = prepareImportedClaimsForScheduling(
    [
      claim({ id: 'claim-a', hours_claimed: 40 }),
      claim({ id: 'claim-b', hours_claimed: 50, corrected_child_name: 'Faxima Mohamed' }),
    ],
    [matchingChild],
  );

  assert.equal(result.rows.length, 1);
  assert.equal(result.mergedRowCount, 1);
  assert.equal(result.identityConflictCount, 0);
  assert.equal(Number(result.rows[0]?.corrected_hours), 90);
  assert.deepEqual(result.rows[0]?.source_claim_ids, ['claim-a', 'claim-b']);
});

test('does not auto-split a unique stored match solely because its DOB differs', () => {
  const result = prepareImportedClaimsForScheduling(
    [claim({ id: 'unique-mismatch', date_of_birth: '2013-11-06' })],
    [matchingChild],
  );

  assert.equal(result.identityConflictCount, 0);
  assert.equal(result.rows.length, 1);
  assert.equal(result.rows[0]?.schedule_child_id, matchingChild.id);
  assert.equal(result.rows[0]?.uses_real_child, true);
});
