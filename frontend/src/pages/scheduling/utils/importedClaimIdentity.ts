export interface ImportedClaimIdentityRow {
  id: string;
  child_name: string;
  hours_claimed: number | string;
  matched_child_id?: string | null;
  date_of_birth?: string | Date | null;
  corrected_child_name?: string | null;
  corrected_hours?: number | string | null;
  care_category?: string | null;
  manually_verified?: boolean | null;
  match_confidence?: number | string | null;
  [key: string]: unknown;
}

export interface ChildIdentityRow {
  id: string;
  date_of_birth?: string | Date | null;
}

export interface ClaimIdentityConflict {
  code: 'DATE_OF_BIRTH_MISMATCH';
  matchedChildId: string;
  claimDateOfBirth: string;
  childDateOfBirth: string;
}

export interface SchedulingImportedClaimRow extends ImportedClaimIdentityRow {
  schedule_child_id: string;
  uses_real_child: boolean;
  source_claim_ids: string[];
  source_claim_names: string[];
  identity_conflict?: ClaimIdentityConflict;
}

export interface SchedulingImportedClaims {
  rows: SchedulingImportedClaimRow[];
  mergedRowCount: number;
  identityConflictCount: number;
  identityConflictNames: string[];
}

/**
 * Convert a supported API/Date value to the identity-bearing calendar date.
 * Returning null deliberately means "unknown", not "equal" or "conflicting".
 */
function identityDate(value: string | Date | null | undefined): string | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value.toISOString().slice(0, 10);
  }
  if (typeof value !== 'string') return null;
  const match = value.trim().match(/^(\d{4}-\d{2}-\d{2})(?:$|T|\s)/);
  return match?.[1] ?? null;
}

export function importedClaimIdentityConflict(
  claim: ImportedClaimIdentityRow,
  child: ChildIdentityRow | undefined,
): ClaimIdentityConflict | undefined {
  if (!claim.matched_child_id || !child) return undefined;
  const claimDateOfBirth = identityDate(claim.date_of_birth);
  const childDateOfBirth = identityDate(child.date_of_birth);
  if (!claimDateOfBirth || !childDateOfBirth || claimDateOfBirth === childDateOfBirth) {
    return undefined;
  }
  return {
    code: 'DATE_OF_BIRTH_MISMATCH',
    matchedChildId: claim.matched_child_id,
    claimDateOfBirth,
    childDateOfBirth,
  };
}

function effectiveHours(row: ImportedClaimIdentityRow): number {
  return Number(row.corrected_hours ?? row.hours_claimed ?? 0);
}

function sourceName(row: ImportedClaimIdentityRow): string {
  return row.corrected_child_name || row.child_name;
}

/**
 * Merge repeated source rows only when they point to a DOB-consistent child.
 * A contradictory DOB is retained as a claim-only scheduling identity so two
 * distinct people can never be collapsed into one attendance record.
 */
export function prepareImportedClaimsForScheduling(
  claims: ImportedClaimIdentityRow[],
  children: ChildIdentityRow[],
): SchedulingImportedClaims {
  const childrenById = new Map(children.map((child) => [child.id, child]));
  const conflicts = new Map<string, ClaimIdentityConflict>();
  const sourceGroups = new Map<string, ImportedClaimIdentityRow[]>();
  const groups = new Map<string, ImportedClaimIdentityRow[]>();

  for (const row of claims) {
    if (!row.matched_child_id) continue;
    sourceGroups.set(
      row.matched_child_id,
      [...(sourceGroups.get(row.matched_child_id) || []), row],
    );
  }

  for (const [childId, rows] of sourceGroups) {
    const child = childrenById.get(childId);
    const childDateOfBirth = identityDate(child?.date_of_birth);
    // A lone DOB mismatch can be stale or imprecise source data. Split only a
    // duplicate mapping whose sibling positively anchors the database child.
    const hasExactIdentityAnchor = rows.length > 1 && Boolean(
      childDateOfBirth
      && rows.some((row) => identityDate(row.date_of_birth) === childDateOfBirth),
    );
    for (const row of rows) {
      const conflict = hasExactIdentityAnchor
        ? importedClaimIdentityConflict(row, child)
        : undefined;
      if (conflict) {
        conflicts.set(row.id, conflict);
        continue;
      }
      groups.set(childId, [...(groups.get(childId) || []), row]);
    }
  }

  const mergedByChildId = new Map<string, SchedulingImportedClaimRow>();
  let mergedRowCount = 0;
  for (const [childId, rows] of groups) {
    const ranked = [...rows].sort((left, right) => {
      const verificationDifference = Number(Boolean(right.manually_verified))
        - Number(Boolean(left.manually_verified));
      if (verificationDifference) return verificationDifference;
      const confidenceDifference = Number(right.match_confidence || 0)
        - Number(left.match_confidence || 0);
      if (confidenceDifference) return confidenceDifference;
      return effectiveHours(right) - effectiveHours(left);
    });
    const representative = ranked[0];
    if (!representative) continue;
    const careCategories = [...new Set(rows.map((row) => row.care_category).filter(Boolean))];
    mergedByChildId.set(childId, {
      ...representative,
      schedule_child_id: childId,
      uses_real_child: true,
      corrected_hours: rows.reduce((total, row) => total + effectiveHours(row), 0),
      care_category: careCategories.join(' '),
      source_claim_ids: rows.map((row) => row.id),
      source_claim_names: rows.map(sourceName),
    });
    mergedRowCount += Math.max(0, rows.length - 1);
  }

  const emittedRealChildren = new Set<string>();
  const preparedRows = claims.flatMap((row): SchedulingImportedClaimRow[] => {
    const conflict = conflicts.get(row.id);
    if (!row.matched_child_id || conflict) {
      return [{
        ...row,
        schedule_child_id: `imported-claim:${row.id}`,
        uses_real_child: false,
        source_claim_ids: [row.id],
        source_claim_names: [sourceName(row)],
        ...(conflict ? { identity_conflict: conflict } : {}),
      }];
    }
    if (emittedRealChildren.has(row.matched_child_id)) return [];
    emittedRealChildren.add(row.matched_child_id);
    const merged = mergedByChildId.get(row.matched_child_id);
    return merged ? [merged] : [];
  });

  return {
    rows: preparedRows,
    mergedRowCount,
    identityConflictCount: conflicts.size,
    identityConflictNames: claims
      .filter((row) => conflicts.has(row.id))
      .map(sourceName),
  };
}
