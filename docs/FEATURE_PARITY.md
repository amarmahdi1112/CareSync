# Feature parity

Status values are `not started`, `in progress`, `verified`, `released local`, or
`retired with reason`.

| Area | Status | Verification |
|---|---|---|
| FastAPI foundation and health checks | verified | Automated API and DB-name tests |
| Legacy SQLite integrity and schema fingerprint | verified | Read-only verification script |
| Live PostgreSQL schema mapping (40 tables) | verified | Generated mappings and metadata coverage test |
| Authentication and role permissions | in progress | Login, current-user, roles, permissions, and legacy JWT tests |
| Organizations and users | in progress | Current-organization REST profile/preferences plus scoped reads; user writes pending |
| Families, guardians, and emergency contacts | verified | Rich organization-scoped REST reads and guarded CRUD; active edit modals use REST |
| Children and funding | verified | Organization-scoped child/funding REST reads, configuration, and guarded updates |
| Pricing and provider settings | in progress | Legacy compatibility configuration exists; 0033 has synthetic effective-dated rate versions and no payment provider |
| CSV and document import | verified | CSV detection/mapping/direct import and claim PDF import use REST |
| Relationship and sibling detection | verified | Active family relationship and sibling workflows use REST |
| Attendance and scheduling | verified | Default deterministic V3 with independent five-minute certification, exact-claim persistence/export guards, canonical names, and automatic multi-year closures; V2 is deprecated rollback-only |
| Claim import and generation | verified | Organization-scoped PDF name/DOB matching, safe re-match, reports, profile distributions, and database-backed imports |
| Audit and violation reporting | in progress | Claim decision audit and explanations verified |
| Billing and finance (`0033`/`0036`/`0037`) | released local | Append-only CAD ledger, exact recovery, historical payer/rate/agreement facts, immutable payment/allocation/credit facts and coherent `/billing` workspace are retained; 0037 scopes ordinary agreements to enrollment while preserving the legacy-null fallback, and private/manual commands still require the absent 0036 owner activation |
| Enrollment-to-billing readiness | released local | Admissions, Billing, Family and Child consume one strict projection; family invoices remain settlement authority, child views are attribution-only, and the live queue truthfully shows 0 setup-ready of 197 active child records |
| Billing readiness batch planner (`0040`) | verified | Deterministic privacy-bounded setup waves and no-write preview are live in the retained API; Apply reuses canonical account/payer/rate/agreement commands, retained head stays 0039, and signed-in setup browser acceptance remains pending |
| Live room presence and operational safety board (`0041`) | verified | Server-confirmed room-presence intervals, exact-retry move/end, child-operation room gate, operational configured-target board, append-only exception episodes, strict admin/staff contracts and realtime invalidation passed the complete disposable source evidence; retained 5434 remains at 0039 and signed-in/physical-device acceptance is pending |
| Billing policy recertification (`0042`) | verified | Exact whole-catalog A/B preflight, transactional recreation of the 36 frozen 0033 policies, tamper/mixed-profile rejection and PostgreSQL 17 A-to-B dump/restore runtime certification passed; this is a source integrity repair with no new billing authority and no retained cutover |
| Candidate marketplace and employer ATS | released local | Canonical `/marketplace`, `/ats` and `/ats/marketplace` routes share one lifecycle/repository boundary; legacy hiring prefixes and unused client adapters are retired |
| Public job catalog replay (`0038`) | released local | Forced-RLS public-safe projection plus durable replay invalidates opened, updated and closed listings for unaffiliated candidates without publishing draft, tenant, candidate, application or free-text data |
| Invoice record, PDF, delivery and payment processing | in progress | Canonical synthetic/private-manual invoice preview plus browser print/save-PDF is implemented; external delivery, tax receipt, processor request and money movement remain absent |
| Signatures and letterheads | in progress | Scoped signature reads and guarded creation include binary image data; letterhead REST conversion pending |
| AI-assisted workflows | verified | Child insight/chat compatibility remains; invoice AI is not part of 0033; a bounded local extension name-matching companion adapter is released, while live third-party portal/provider acceptance remains separate |
| Frontend REST conversion and corrections | verified | Apollo/GraphQL removed; production build, lint, and authenticated browser integration verified |

The retained local database advanced exactly from
`0038_public_job_catalog_outbox` to `0039_admissions_decision_spine` on
2026-07-23 after an exact 16,445-row / 135-table disposable restore and the
guarded evidence recovery gates. The migration preserved 110 families, 203
children and 197 enrollments and retained 141 public tables plus one view.
Neither the per-facility
release activation nor the per-organization manual-billing activation was
created. Revision 0036 remains the manual-billing protocol schema; 0037 remains
the immutable agreement-scope repair; 0038 remains the public-catalog replay.
Final acceptance recorded 1,997 backend tests passed with 105 skips and seven
warnings, 841 administrator tests, 272 staff-app tests, 78 extension tests and
two independent green PostgreSQL 17 admissions runs.

The preceding cutovers remain historical evidence. Product slice
`0040_billing_readiness_batch_planner` is verified in source and through
retained live read-only API acceptance. Source then advanced through verified
`0041_live_room_presence` and `0042_billing_policy_recert`; the checked-in
launcher is pinned to 0042, while the retained PostgreSQL 17 database on port
5434 remains exactly at 0039. The populated disposable clone preserved all
16,508 rows across 140 pre-0041 business tables with count digest
`19376c0797dc5bf0613695b11448a3e16516c37751f694622773d55b8f8d62bd`
and row digest
`ab12ea50137809a4cc5e9a049d7f7b0f3fcfa37739f2690a024e2b54fe0fb846`.
Neither 0041 nor 0042 is a retained cutover. Signed-in administrator and
physical Android acceptance for 0041 remain pending.
