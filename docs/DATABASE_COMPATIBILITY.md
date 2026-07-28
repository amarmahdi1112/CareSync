# Database compatibility

A gzip-verified logical backup of the live PostgreSQL database was created before the
mutation layer was added. It contains all 40 tables and 42,098 rows. Backup payloads
remain under the ignored `backend/backups/` directory and are never committed.

## Preserved identities

- PostgreSQL database: `caresync`
- SQLite fallback file: `caresync.db`

The FastAPI settings reject any other names. The PostgreSQL connection is forced
read-only during migration, and the SQLite copy uses `PRAGMA query_only=ON`.

## PostgreSQL source

The legacy environment points to the live PostgreSQL `caresync` database. The
read-only inventory found 40 application tables. Aggregate parity anchors include:

| Table | Records at initial inventory |
|---|---:|
| organizations | 3 |
| users | 7 |
| families | 109 |
| children | 202 |
| guardians | 199 |
| generated_claims | 578 |
| invoices | 153 |

These counts are verification anchors, not migration targets; later checks must
account for legitimate records created while migration work continues.

## SQLite fallback

The working copy at `backend/storage/caresync.db` was created with SQLite's online
backup mechanism. It contains all 28 expected legacy SQLite tables, passes
`PRAGMA quick_check`, and has zero reported foreign-key violations.
