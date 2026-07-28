# Legacy family and child import

Status: applied and reconciled on 2026-07-15

## Source and target

- The untouched original database remains `caresync` on PostgreSQL 5432.
- The import read from the safety clone on PostgreSQL 5433.
- Relevant source-table counts and content fingerprints matched between 5432 and 5433 before
  import.
- The target is the isolated Basic `caresync` database on PostgreSQL 5434.

## Imported records

| Record | Imported |
| --- | ---: |
| Families | 109 |
| Guardians | 199 |
| Emergency contacts | 4 |
| Children | 202 |
| Active enrollments created | 196 |

The existing Basic test family, child, and enrollment were preserved. There was no family-name
or child natural-key overlap with that test data.

## Mapping and safety rules

- Source identifiers are retained as stable import identities, making reruns idempotent.
- Family status, file number, notes, consents, guardian/contact facts, child identity, date of
  birth, health facts, active state, and original timestamps are preserved.
- Guardian primary/secondary roles are mapped directly. Legacy guardians have no explicit pickup
  authorization column, so imported guardian pickup authorization is `false` until verified.
- Emergency-contact pickup authorization is copied from its explicit legacy field.
- Inactive children receive no invented active enrollment.
- Active children receive a deterministic facility enrollment with no program or room placement.
  They enter the DOB room-placement review queue and require human approval.
- No source row is deleted or changed. No target row is overwritten on rerun.
- The aggregate import and the placement-review conversion are recorded in the target audit log
  without copying personal details into audit metadata.

## Import utility

The repeatable utility is `backend/scripts/import_legacy_childcare.py`. It is a dry run unless
`--apply` is supplied. Its verification step reconciles every imported source fact and every
deterministic active enrollment against the source fingerprint.
