# Architecture

CareSync Private is a local-first modular monolith. It keeps one deployable FastAPI
backend while separating HTTP contracts, business services, company algorithms,
database access, and external integrations.

The React frontend will consume versioned REST endpoints under `/api/v1`. OpenAPI is
the source for its generated TypeScript client.

## Data safety rules

- SQLite filename: `caresync.db`
- PostgreSQL database name: `caresync`
- No automatic schema creation or destructive migration against the legacy database.
- Every schema migration is first exercised against a verified copy.
- IDs, relationships, dates, decimal values, and audit history are preserved.
- A backup and integrity report are required before any production data migration.
