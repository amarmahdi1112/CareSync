# CareSync Ultimate Product Constitution

> Living document. Created 2026-07-16 (America/Edmonton). This is the durable product memory, capability inventory, risk register, and long-range backlog for CareSync. It contains no secrets. It is not legal, clinical, accounting, employment, or regulatory advice. Before production, applicable decisions require review by Alberta childcare counsel, a privacy professional, an accountant, the operator's licensing officer, and qualified safety practitioners.

## Document protocol

This file is intentionally larger than a conventional roadmap. It is designed to survive context loss and repeated reassessment.

Registry snapshot after four research generations and the 2026-07-16 adversarial audit: **1,483 unique stable feature/control IDs**, **153 major/detailed headings**, **2,446 lines**, and **96 unique cited source URLs**, plus implemented-system evidence, delivery phases, failure analysis, correction history and prohibited features. Counts will change as the living document evolves.

Status labels:

- `IMPLEMENTED`: working code exists in the new Basic runtime and is covered by relevant tests.
- `DEFERRED-IMPLEMENTED`: working legacy/advanced code exists, but it is not integrated into the new Basic SaaS runtime.
- `PARTIAL`: some code/UI exists, but the full lifecycle, safety, or production boundary is incomplete.
- `P0`: safety, legality, privacy, correctness, or production-foundation work.
- `P1`: complete operational MVP work.
- `P2`: major business value or Alberta-specific differentiation.
- `P3`: scale, ecosystem, optimization, or advanced intelligence.
- `FUTURE`: deliberately speculative; requires evidence and governance before implementation.
- `AVOID`: should not be built without an exceptional, documented reason.

Priority is not legal authority. Each executable control must also be classified as `LAW/REGULATION`, `LEGAL_IMPLEMENTATION`, `AHJ_APPLICABILITY`, `LICENCE/PERMIT`, `AGREEMENT_RULE`, `GUIDANCE`, `RISK_CONTROL`, `PRODUCT_STANDARD`, `EVIDENCE_SUPPORT` or `FUTURE/HYPOTHESIS`, with source, applicability and effective date.

Every feature is incomplete until it has, where applicable: authorization, tenant isolation, state transitions, validation, audit, notifications, error recovery, concurrency behavior, retention, accessibility, observability, tests, documentation, migration, and rollback.

## Product thesis

CareSync is an Alberta-first, Canada-ready operating system for childcare. It should connect the full lifecycle:

```text
family inquiry -> waitlist -> enrolment -> daily care -> billing/funding -> transition/alumni
candidate -> applicant -> interview -> offer -> employee -> schedule/shift -> development/alumni
licence -> facility -> program -> room -> live occupancy/ratios -> evidence -> inspection/renewal
```

It is not the Government of Alberta, a licensing authority, a medical provider, a legal decision-maker, or an autonomous hiring/safeguarding system. It may prepare evidence, calculate, reconcile, simulate, explain, and recommend. Accountable humans remain in control of safety, legal, clinical, safeguarding, employment, funding, and external-submission decisions.

## Current system truth

### New Basic backend and platform

- `IMPLEMENTED` FastAPI application factory, configuration, health checks, CORS, PostgreSQL/SQLite test support, read-only safety switch.
- `IMPLEMENTED` Alembic revisions `0001` through `0018`.
- `IMPLEMENTED` normalized users, organizations, memberships, roles, facilities, programs, rooms, families, guardians, contacts, children, enrolments, attendance, care, medications, incidents, staffing, ATS, marketplace, credential vault, shifts, realtime, and audit models.
- `IMPLEMENTED` tenant-scoped API dependencies and PostgreSQL forced RLS.
- `IMPLEMENTED` owner, administrator, and educator permissions with room/facility scopes.
- `IMPLEMENTED` bcrypt password hashing, JWT auth-version revocation, opaque hashed one-time tokens, staff activation, password reset, login, registration, profile and password change.
- `PARTIAL` email, organization, and facility verification fields exist, but local launch policy auto-verifies them.
- `IMPLEMENTED` organization/facility onboarding, Daycare and OSC programs, unlimited logical room creation, capacity, room age intervals, settings.
- `IMPLEMENTED` family care networks, guardians, emergency contacts, consents, child records, profile photos, enrolment lifecycle.
- `IMPLEMENTED` room rosters, occupancy, unassigned queue, room movement, DOB/capacity placement recommendations, individual approval, atomic bulk approval.
- `IMPLEMENTED` attendance roster, check-in/out, absence, correction, history, event/audit evidence.
- `IMPLEMENTED` daily care: feed/bottle, diaper, toilet, sleep, mood, activity, correction, void, room daybook, safety cards.
- `IMPLEMENTED` written-authorization medication plans, activation/archive, administration/refusal/omission, correction/void, immutable facts.
- `IMPLEMENTED` incident draft, review, finalization, return, external-report marker, history.
- `IMPLEMENTED` staff invitations, activation, suspension, room assignments, role changes, resets.
- `IMPLEMENTED` location-free idempotent staff clock-in/out and server-side active-shift guard for staff attendance, care, medication-administration, and incident mutations.
- `IMPLEMENTED` transactional outbox, realtime tickets, cursor replay, heartbeats, reset, access revocation, candidate-filtered realtime.
- `IMPLEMENTED` ATS listings, applicants, interviews, offers, decisions, hiring/provisioning, credential review.
- `IMPLEMENTED` independent candidate marketplace registration/login, job search/application tracking, interview accept/decline/counter-proposal, offers, talent search.
- `IMPLEMENTED` certified-educator/student onboarding, profile completion, DOB/phone/photo, work history, certificate/resume upload, versioned credential vault.
- `IMPLEMENTED` server-side OpenCV/PaddleOCR pipeline with user confirmation and name-mismatch resolution.

Evidence roots: `backend/app/api/basic/`, `backend/app/basic/models.py`, `backend/alembic/versions/`, and `backend/tests/`.

### Admin portal

- `IMPLEMENTED` React 19, Vite, TypeScript, styled-components, Zustand, dark-ice design system, motion preferences and protected shell.
- `IMPLEMENTED` public landing, product, pricing, security, registration, login, reset, staff activation and resumable onboarding.
- `IMPLEMENTED` live Dashboard, Today, Families, Family Profile, Children, Child Profile, enrolments, Rooms, rosters, DOB placement, Attendance, Medication, Incidents, Staff, Jobs/Hiring and Settings.
- `IMPLEMENTED` permission-aware navigation, not-found/access-denied boundaries, loading/empty/error states across core modules.
- `PARTIAL` public pricing is presentational; no live SaaS subscription/entitlement engine.
- `PARTIAL` scheduling page is an animated visualization/demo, not the live V3 engine integration.
- `PARTIAL` claims, imports, invoicing, documents, activity/support and advanced AI remain placeholders or hidden/deferred modules.

Evidence root: `frontend-redesign/src/`.

### Staff and candidate mobile app

- `IMPLEMENTED` Expo SDK 57 / React Native app with secure session storage and separate candidate/staff navigation states.
- `IMPLEMENTED` candidate onboarding, marketplace, job/application status, interview decisions, offers, credential history and personal profile.
- `IMPLEMENTED` post-hire staff room roster, shift clock, attendance and care actions.
- `IMPLEMENTED` location-free shift clock, no redundant child attendance confirmation modal, UI locks without active shift, server enforcement.
- `IMPLEMENTED` realtime cursor/checkpoint handling.
- `PARTIAL` a secure offline care queue exists, but CareSync must not claim complete offline-first safety until every conflict, expiry, device revocation and reconciliation path is proven.
- `MISSING` production push notifications, app-store pipelines, mobile E2E automation, device management, family app.

Evidence root: `/Users/amarmuha/Documents/Codex/2026-07-13/hel/CareSync-Staff/`.

### Deferred advanced assets

- `DEFERRED-IMPLEMENTED` deterministic V3 five-minute scheduler, feasibility analysis, repairs, Daycare realism redistribution, independent auditing, certification and visualization events.
- `DEFERRED-IMPLEMENTED` claim simulation, claim import/rematch, reports, CSV imports, DeepSeek name matching and AI conversations.
- `DEFERRED-IMPLEMENTED` broad invoicing APIs including recurring/bulk invoices, credits, settings, tracking, analytics and email preparation.
- `DEFERRED-IMPLEMENTED` browser extension for KinderLogix attendance entry, durable mappings, AI recommendations, denied-pair memory, cleanup and stateful checkpoints.
- `HIGH-RISK` Basic and legacy/advanced routers are mutually exclusive. Existing advanced modules cannot simply be made visible; they need authentication, tenancy, schema and contract integration into the Basic modular runtime.

### Verification checkpoint

- Backend full suite on 2026-07-16: 275 passed, 7 optional disposable-PostgreSQL tests skipped.
- Admin portal checkpoint: 233 tests, typecheck and production build passed.
- Staff mobile checkpoint: 49 tests, typecheck and Android SDK 57 export passed.
- Browser extension historical checkpoint: 75 tests, typecheck and build passed.
- `MISSING`: full browser E2E, mobile Maestro/Detox E2E, visual regression, accessibility automation, cross-app lifecycle, load/soak/chaos, backup restore and production security evidence.

## Highest-priority structural risks

1. `P0` Unify Basic and advanced domains without weakening tenancy or duplicating identities.
2. `P0` Replace temporary auto-verification with real email, organization and facility control verification.
3. `P0` Add production sessions, refresh rotation, MFA/passkeys, device/session management, rate limiting and abuse defense.
4. `P0` Rotate every secret ever pasted into chat or stored insecurely; keep all provider keys server-side in a secret manager.
5. `P0` Build real deployment, Canadian-region storage, backups, restore drills, observability, alerting and incident response.
6. `P0` Add a durable job/worker system; synchronous 90-second OCR subprocesses are not a production architecture.
7. `P0` Consolidate overlapping ATS/hiring route families into one explicit state machine.
8. `P0` Build notifications; current invites/offers/status changes do not have a production email/SMS/push delivery platform.
9. `P0` Prove tenant isolation across files, exports, background jobs, search, analytics, AI and support tools—not only ordinary HTTP rows.
10. `P0` Create a parent/family identity and consent architecture before exposing family self-service.
11. `P0` Reconcile room physical capacity, licensed capacity, group size and ratio capacity as distinct values.
12. `P0` Implement actual live child/staff ratio evidence and emergency offline rosters.
13. `P0` Replace heuristic “compliance” claims with rule-source/version/effective-date evidence and human certification.
14. `P0` Establish financial ledgers, idempotency and reconciliation before real money movement.
15. `P0` Prevent scope explosion: ship complete vertical workflows, not disconnected pages.

## Non-negotiable design principles

- Safety over convenience, but do not add ritual friction that produces no safety value.
- Server authorization is the boundary; UI visibility is not authorization.
- Every tenant-owned record, job, file, event, export and model call carries tenant context.
- Records are corrected with history, not silently rewritten.
- Money uses an immutable double-entry subledger and compensating entries.
- Regulations, funding rules, rates, capacities and policies are effective-dated.
- Realtime means durable replay and reconciliation, not merely WebSocket animation.
- Offline claims require conflict rules, expiry, device revocation and truth-preserving UI.
- AI outputs are proposals with provenance, confidence, abstention, review and rollback.
- No automated external submission without a lawful interface and explicit human authorization.
- Accessibility target is WCAG 2.2 AA across web, mobile, kiosk, email, PDF and exports.
- Dark-ice animation remains optional; reduced motion and operational speed are mandatory.
- Never copy real child data into demos, logs, analytics samples or development fixtures.
- Every warning must provide a safe resolution path, owner and next step.

## Personas and operating modes

- Licence holder / legal representative
- Organization owner
- Regional or multi-site operator
- Facility director / administrator
- Privacy officer
- Finance and claims specialist
- Scheduler / workforce coordinator
- Program supervisor
- Educator / primary staff
- Substitute / casual staff
- Cook / nutrition lead
- Driver / transportation coordinator
- Volunteer / practicum student
- Parent / guardian
- Secondary household / payer
- Authorized pickup
- Caseworker / support professional
- Candidate educator
- Student educator
- Auditor / licensing evidence recipient
- CareSync support engineer with time-bound audited access

## Authoritative research baseline

- Alberta licensed facility programs: <https://www.alberta.ca/licensed-facility-based-programs>
- Alberta facility-based child-care licensing handbook: <https://open.alberta.ca/dataset/0d43ae19-ccc7-4b39-b226-27733354bab1>
- Alberta commercial-carrier education manual: <https://www.alberta.ca/education-manual-for-commercial-carriers>
- Alberta Early Learning and Child Care Regulation: <https://www.canlii.org/en/ab/laws/regu/alta-reg-143-2008/latest/alta-reg-143-2008.html>
- Alberta incident reporting: <https://www.alberta.ca/childcare-report-an-incident-concern-or-complaint>
- Alberta monthly claims: <https://www.alberta.ca/online-child-care-claims-system>
- Alberta affordability grant: <https://www.alberta.ca/affordability-grants-for-child-care-programs>
- Alberta subsidy: <https://www.alberta.ca/child-care-subsidy-program>
- Alberta grant funding: <https://www.alberta.ca/alberta-child-care-grant-funding-program>
- Alberta inclusion support: <https://www.alberta.ca/child-care-supports-for-inclusion>
- Alberta PIPA responsibilities: <https://www.alberta.ca/organization-responsibilities-for-protecting-personal-information>
- Alberta OIPC breach notification: <https://oipc.ab.ca/breach-notification/>
- AHS childcare health and safety guide: <https://www.albertahealthservices.ca/assets/wf/eph/wf-eh-health-safety-guidlines-child-care-facilities.pdf>
- W3C WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
- OWASP ASVS 5: <https://owasp.org/www-project-application-security-verification-standard/>
- OWASP API Security: <https://owasp.org/API-Security/>
- NIST SSDF: <https://csrc.nist.gov/pubs/sp/800/218/final>
- NIST digital identity: <https://pages.nist.gov/800-63-4/sp800-63b.html>
- Brightwheel features: <https://mybrightwheel.com/features/>
- Procare capabilities: <https://www.procaresoftware.com/capabilities/child-care-management-software/>
- Lillio features: <https://www.lillio.com/features>
- Kangarootime: <https://kangarootime.com/>

## Master feature registry — pass 1: foundation and parity

The following registry is intentionally exhaustive and may contain alternatives. Discovery validates need; prioritization selects the slice; implementation must still satisfy the completion rule above.

### SaaS organization and commercial platform

- [ ] `SAAS-001 P0` Real plans, price catalogue, effective dates, entitlements and limits.
- [ ] `SAAS-002 P0` Trial, activation, grace, past-due, cancellation, read-only and deletion states.
- [ ] `SAAS-003 P0` Hosted subscription checkout and signed deduplicated webhooks.
- [ ] `SAAS-004 P0` Canadian taxes, invoices, receipts, credits and refunds for CareSync subscription.
- [ ] `SAAS-005 P1` Transparent public pricing and plan comparison driven by catalogue data.
- [ ] `SAAS-006 P1` Capacity-band or per-location pricing; unlimited rooms/staff for safety and usability.
- [ ] `SAAS-007 P1` Annual plans, nonprofit discount, founders cohort and coupon governance.
- [ ] `SAAS-008 P1` Multi-facility organization hierarchy and regional administration.
- [ ] `SAAS-009 P1` Multiple organization memberships and deliberate organization switcher.
- [ ] `SAAS-010 P1` Branding, locale, terminology and policy configuration per tenant.
- [ ] `SAAS-011 P1` Sandbox/training tenant using fictional data.
- [ ] `SAAS-012 P1` Guided onboarding checklist and adoption/readiness score.
- [ ] `SAAS-013 P1` Data import centre with dry run, mapping, reconciliation and rollback.
- [ ] `SAAS-014 P1` Complete tenant export before cancellation.
- [ ] `SAAS-015 P1` Retention-aware deletion workflow and legal hold.
- [ ] `SAAS-016 P2` Usage metering for AI, media, SMS and unusually expensive work.
- [ ] `SAAS-017 P2` Customer-facing service health, incidents and maintenance communication.
- [ ] `SAAS-018 P2` Release notes, guided change education and feature discovery.
- [ ] `SAAS-019 P2` Support plans, response targets and escalation.
- [ ] `SAAS-020 P3` Multi-site/enterprise contracts, SSO, API, SLA and custom retention.

### Identity, access and account security

- [ ] `IAM-001 P0` Production transactional email verification.
- [ ] `IAM-002 P0` Organization/facility-control verification workflow distinct from email verification.
- [ ] `IAM-003 P0` Short-lived access tokens and rotated refresh sessions.
- [ ] `IAM-004 P0` Logout, list sessions, revoke one/all sessions and auth-version rotation.
- [ ] `IAM-005 P0` MFA for privileged roles; recovery codes and secure recovery.
- [ ] `IAM-006 P0` Passkeys/WebAuthn and phishing-resistant admin authentication.
- [ ] `IAM-007 P0` Login rate limits, credential-stuffing detection and bot protection.
- [ ] `IAM-008 P0` Secure invitation delivery, expiry, revocation and resend.
- [ ] `IAM-009 P0` Secure email-change confirmation to old and new addresses.
- [ ] `IAM-010 P0` Device/session history, new-device alerts and remote logout.
- [ ] `IAM-011 P0` Break-glass access with reason, expiry, approval and alerts.
- [ ] `IAM-012 P0` Support access consent, scope, time limit, banner and audit.
- [ ] `IAM-013 P1` Custom roles built from safe permission templates.
- [ ] `IAM-014 P1` Facility, room, child-relationship and workflow-state attributes in authorization.
- [ ] `IAM-015 P1` Delegated administration without owner-equivalent privilege.
- [ ] `IAM-016 P1` Administrator separation of duties for finance, HR and safeguarding.
- [ ] `IAM-017 P1` SSO via Google/Microsoft; enterprise SAML/OIDC later.
- [ ] `IAM-018 P1` Candidate-to-employee identity conversion without duplicate accounts.
- [ ] `IAM-019 P1` Parent/guardian portal identities with per-child/per-purpose permissions.
- [ ] `IAM-020 P2` Privacy-preserving auditor evidence-room identities.

### Privacy and records governance

- [ ] `PRIV-001 P0` Privacy officer and tenant privacy-management workspace.
- [ ] `PRIV-002 P0` Personal-information inventory and processing register.
- [ ] `PRIV-003 P0` Purpose, authority, consent version, actor, time, expiry and withdrawal history.
- [ ] `PRIV-004 P0` Separate operational, healthcare, medication, media, marketing, research, off-site and optional-service consents.
- [ ] `PRIV-005 P0` Record-class retention, destruction, anonymization and legal hold.
- [ ] `PRIV-006 P0` Access/correction request intake, identity proof, redaction, response and audit.
- [ ] `PRIV-007 P0` PIPA breach register, containment, RROSH assessment, notice and remediation.
- [ ] `PRIV-008 P0` Subprocessor register, country/purpose disclosure and vendor agreements.
- [ ] `PRIV-009 P0` Privacy impact assessment and material-change reassessment.
- [ ] `PRIV-010 P0` Sensitive field classifications and field-level access restrictions.
- [ ] `PRIV-011 P1` Family trust centre: access history, active consents, retention and exports.
- [ ] `PRIV-012 P1` Download/export watermarking and reason capture for sensitive data.
- [ ] `PRIV-013 P1` Child-media metadata stripping, audience controls and consent enforcement.
- [ ] `PRIV-014 P1` Third-party information redaction in subject-access exports.
- [ ] `PRIV-015 P1` Policy acknowledgement and mandatory staff privacy training.
- [ ] `PRIV-016 P2` Automated legal holds triggered by incidents, claims, complaints or investigations.
- [ ] `PRIV-017 P2` Data expiry map explaining why every sensitive field still exists.
- [ ] `PRIV-018 P3` Privacy-budgeted, minimum-cohort benchmarking.

### Platform security and secure delivery

- [ ] `SEC-001 P0` Secret manager; no default production JWT secret or client-side provider keys.
- [ ] `SEC-002 P0` TLS everywhere, encryption at rest and managed key rotation.
- [ ] `SEC-003 P0` Canadian-region application, object, backup and log hosting option.
- [ ] `SEC-004 P0` Tenant isolation tests across DB, API, cache, files, search, jobs, AI, analytics and notifications.
- [ ] `SEC-005 P0` Signed object URLs, malware scanning, quarantine and safe rendering.
- [ ] `SEC-006 P0` CSP and security headers, CORS review, CSRF strategy and upload limits.
- [ ] `SEC-007 P0` API resource/rate limits with emergency-workflow exceptions.
- [ ] `SEC-008 P0` Immutable security audit, alerting and suspicious-access detection.
- [ ] `SEC-009 P0` SAST, DAST, dependency, secret, container and IaC scanning.
- [ ] `SEC-010 P0` SBOM, vulnerability intake and patch SLAs.
- [ ] `SEC-011 P0` OWASP ASVS 5 verification and API Top 10 evidence.
- [ ] `SEC-012 P0` Independent penetration test and tenant-isolation assessment.
- [ ] `SEC-013 P0` Secure SDLC aligned with NIST SSDF.
- [ ] `SEC-014 P0` Production/test separation and synthetic fixtures.
- [ ] `SEC-015 P0` Incident-response plan, tabletop drills and customer notification tooling.
- [ ] `SEC-016 P0` Encrypted backups, point-in-time recovery and recurring restore drills.
- [ ] `SEC-017 P1` Mobile device expiry/revocation and minimum offline cached data.
- [ ] `SEC-018 P1` Signed webhooks with replay protection and idempotency.
- [ ] `SEC-019 P2` SOC 2 Type II readiness program.
- [ ] `SEC-020 P3` ISO 27001 information-security management program.

### Reliability, deployment and observability

- [ ] `OPS-001 P0` Reproducible container/deployment artifacts and environment validation.
- [ ] `OPS-002 P0` CI gates for tests, typecheck, lint, build, migrations and security scans.
- [ ] `OPS-003 P0` Safe migration expand/backfill/contract workflow and rollback plan.
- [ ] `OPS-004 P0` Structured privacy-safe logs with correlation/request IDs.
- [ ] `OPS-005 P0` Metrics, traces, dashboards and actionable alerts.
- [ ] `OPS-006 P0` Error monitoring with tenant-safe context and user-visible correlation ID.
- [ ] `OPS-007 P0` SLOs for API, realtime, jobs, email, payments and emergency read paths.
- [ ] `OPS-008 P0` Durable job queue for OCR, notifications, exports, reports and integrations.
- [ ] `OPS-009 P0` Object storage, retention, derivatives and lifecycle rules.
- [ ] `OPS-010 P0` Transactional outbox consumers with idempotency and dead-letter handling.
- [ ] `OPS-011 P1` LISTEN/NOTIFY or broker-backed realtime fan-out instead of per-connection polling.
- [ ] `OPS-012 P1` Feature flags, canary tenants and rapid rollback.
- [ ] `OPS-013 P1` Capacity/load/soak tests and noisy-neighbour controls.
- [ ] `OPS-014 P1` Chaos drills: DB failover, object outage, provider failure, network loss.
- [ ] `OPS-015 P1` Business continuity for full SaaS outage and printable fallbacks.
- [ ] `OPS-016 P2` Tenant-specific diagnostics and safe self-service repair tools.
- [ ] `OPS-017 P2` Public status page and incident postmortems.
- [ ] `OPS-018 P3` Data warehouse/analytics replica with governed lineage.

### Notifications and communications infrastructure

- [ ] `NOTIFY-001 P0` Transactional email delivery with domain authentication, bounce and complaint handling.
- [ ] `NOTIFY-002 P0` Mobile push delivery and device-token lifecycle.
- [ ] `NOTIFY-003 P0` SMS provider abstraction for urgent/opted-in use.
- [ ] `NOTIFY-004 P0` Template versioning, localization, approval and preview.
- [ ] `NOTIFY-005 P0` Operational versus commercial purpose separation and CASL consent evidence.
- [ ] `NOTIFY-006 P1` In-app notification centre with actionable state.
- [ ] `NOTIFY-007 P1` Delivery/read/acknowledgement evidence and escalation.
- [ ] `NOTIFY-008 P1` Severity, quiet hours, digests, preferences and emergency override.
- [ ] `NOTIFY-009 P1` Deduplication, batching and fatigue controls.
- [ ] `NOTIFY-010 P1` Custody/consent-aware recipient resolution.
- [ ] `NOTIFY-011 P2` Multilingual delivery with original text and translation label.
- [ ] `NOTIFY-012 P2` Communication SLA and unresolved urgent-message dashboard.

## Master feature registry — pass 2: regulated childcare operations

### Licensing, inspection and compliance

- [ ] `LIC-001 P0` Licence record with number, authority, facility/program scope, issue/expiry, capacity, conditions and immutable document versions.
- [ ] `LIC-002 P0` Renewal calendar with evidence checklist, accountable owner, escalation and submission receipt.
- [ ] `LIC-003 P0` Licence-condition rules that constrain rooms, ages, hours and capacity instead of acting as notes.
- [ ] `LIC-004 P0` Inspection workspace: request list, evidence bundle, annotations, findings, corrective actions and closure proof.
- [ ] `LIC-005 P0` Critical-incident decision support with human confirmation, deadlines, contacts and immutable submission evidence.
- [ ] `LIC-006 P0` Regulation/version registry: effective dates, applicability, source URL, reviewed interpretation and impacted controls.
- [ ] `LIC-007 P0` Required child/staff/facility record completeness matrix with expiry and retention.
- [ ] `LIC-008 P1` Policy library with version approval, distribution, acknowledgement and retraining triggers.
- [ ] `LIC-009 P1` Corrective/preventive action register with root cause, owner, due date, verification and recurrence signal.
- [ ] `LIC-010 P1` Inspection-ready export with source provenance and a manifest/hash for every artifact.
- [ ] `LIC-011 P1` Portable emergency-record packs available offline by room and trip.
- [ ] `LIC-012 P1` Licensing change impact simulator before capacity, program or room edits are committed.
- [ ] `LIC-013 P2` Compliance calendar covering licences, fire, health, insurance, training, checks, drills and equipment.
- [ ] `LIC-014 P2` Evidence freshness score that measures missing/stale proof without inventing compliance.
- [ ] `LIC-015 P2` Multi-jurisdiction rule packs; Alberta remains an explicit versioned pack.
- [ ] `LIC-016 FUTURE` Inspection replay: reconstruct what staff, occupancy, credentials and evidence looked like at any historical instant.

### Programs, rooms, ratios and capacity

- [x] `ROOM-001 IMPLEMENTED` Daycare and OSC programs, rooms, licensed capacity and age intervals.
- [x] `ROOM-002 IMPLEMENTED` Live roster, occupancy, unassigned queue and child movement.
- [x] `ROOM-003 IMPLEMENTED` DOB-based placement recommendation with explicit approval and ambiguity handling.
- [ ] `ROOM-004 P0` Effective-dated room capacity and age-band history; never rewrite historical compliance.
- [ ] `ROOM-005 P0` Alberta ratio/group-size engine by program, age mix, time slice and staff qualification.
- [ ] `ROOM-006 P0` Five-minute occupancy/ratio ledger with explainable numerator, denominator and exceptions.
- [ ] `ROOM-007 P0` Mixed-age calculation with authoritative rule citation and licensed-condition overrides.
- [ ] `ROOM-008 P0` Real-time under-ratio/over-capacity alerts with acknowledgement and resolution record.
- [ ] `ROOM-009 P1` Planned versus actual room census and safe overflow/merge workflow.
- [ ] `ROOM-010 P1` Transition queue for upcoming birthdays, school entry, program moves and guardian notice.
- [ ] `ROOM-011 P1` Room closure, temporary relocation and renovation lifecycle.
- [ ] `ROOM-012 P1` Staff-to-room assignment timeline, float coverage and break coverage.
- [ ] `ROOM-013 P1` Headcount reconciliation by educator, room, facility and emergency assembly zone.
- [ ] `ROOM-014 P2` Capacity forecast from enrolment, waitlist, age transitions, staffing and absences.
- [ ] `ROOM-015 P2` What-if simulator for opening/closing rooms, hiring, ratios and revenue.
- [ ] `ROOM-016 FUTURE` Capacity time machine: explain why a seat was or was not safely available on any date.

### Families, guardians, custody and relationships

- [x] `FAM-001 IMPLEMENTED` Family care network, guardians, emergency contacts, relationships and consents.
- [x] `FAM-002 IMPLEMENTED` Full family profile rather than a detail drawer.
- [ ] `FAM-003 P0` Household, guardian and payer separation; one child may belong to multiple households.
- [ ] `FAM-004 P0` Custody/access restriction model with effective dates, confidential evidence and need-to-know visibility.
- [ ] `FAM-005 P0` Authorized pickup identity, relationship, expiry, restrictions and pickup audit.
- [ ] `FAM-006 P0` Court-order conflict warning with mandatory human escalation; never automated legal interpretation.
- [ ] `FAM-007 P1` Family onboarding checklist, missing-item requests and e-signature.
- [ ] `FAM-008 P1` Preferred language, communication channel, accessibility and translation needs.
- [ ] `FAM-009 P1` Multiple payer splits, subsidies, sponsors and statement access boundaries.
- [ ] `FAM-010 P1` Sibling linking, shared contacts/documents and sibling-sensitive admissions.
- [ ] `FAM-011 P1` Family timeline covering inquiries, messages, consents, attendance, billing and changes.
- [ ] `FAM-012 P1` Self-service updates with staff approval for safety-sensitive fields.
- [ ] `FAM-013 P2` Family risk-free support flags (transport, language, accessibility) without stigmatizing scores.
- [ ] `FAM-014 P2` Alumni/export/closure workflow with retention, legal hold and verified deletion.
- [ ] `FAM-015 FUTURE` Consent compiler that converts a planned activity into the exact valid consent set and unresolved exceptions.

### Child master record, enrolment and transitions

- [x] `CHILD-001 IMPLEMENTED` Child profile, photo, DOB, enrolment and room placement.
- [ ] `CHILD-002 P0` Legal/preferred name, pronouns where appropriate, identifiers and duplicate-safe merge workflow.
- [ ] `CHILD-003 P0` Emergency, medical, allergy, dietary, accessibility and individual-support facts with source/effective dates.
- [ ] `CHILD-004 P0` Enrolment contract: program, schedule, start/end, funding, fees, custody and consent prerequisites.
- [ ] `CHILD-005 P0` Immutable enrolment/room/status history and future-effective changes.
- [ ] `CHILD-006 P1` Developmental profile, routines, comforts, culture, language and family goals.
- [ ] `CHILD-007 P1` Gradual-entry plan, transition notes and room handoff acknowledgement.
- [ ] `CHILD-008 P1` Withdrawal, suspension, extended absence and return workflow.
- [ ] `CHILD-009 P1` Document expiry and annual-record confirmation campaign.
- [ ] `CHILD-010 P1` Child data export/transfer packet with guardian approval and disclosure log.
- [ ] `CHILD-011 P2` Age-transition intelligence with candidate rooms, capacity impact and explainable recommendation.
- [ ] `CHILD-012 P2` Longitudinal care timeline with strict role/guardian visibility.
- [ ] `CHILD-013 FUTURE` Care graph connecting people, rooms, plans, consents and events for safer impact analysis.

### Admissions, inquiries and waitlist

- [ ] `ADM-001 P1` Public inquiry forms by facility/program with bot/abuse protection.
- [ ] `ADM-002 P1` Configurable admissions pipeline from inquiry through tour, offer, deposit and enrolment.
- [ ] `ADM-003 P1` Waitlist preferences: start date, days, age/program, sibling, subsidy and accessibility.
- [ ] `ADM-004 P1` Transparent waitlist priority policy with reason codes, overrides and audit.
- [ ] `ADM-005 P1` Tours, reminders, attendance, notes and follow-up sequences.
- [ ] `ADM-006 P1` Seat offers with expiry, acceptance, deposit and automatic next-candidate workflow.
- [ ] `ADM-007 P1` Capacity-aware availability calendar based on future transitions and staffing.
- [ ] `ADM-008 P1` Application/document portal with resumable progress and multilingual instructions.
- [ ] `ADM-009 P2` Conversion, time-to-seat, unmet-demand and neighbourhood demand analytics.
- [ ] `ADM-010 P2` Ethical recommendation assistance that never hides or silently deprioritizes applicants.

### Attendance, pickup and movement

- [x] `ATT-001 IMPLEMENTED` Child check-in/out, absence, correction, history and shift guard.
- [ ] `ATT-002 P0` Authorized-pickup verification and exception/escalation workflow.
- [ ] `ATT-003 P0` Missing-child/failed-headcount emergency workflow with immediate escalation.
- [ ] `ATT-004 P0` Attendance event correction/void with reason, actor and immutable original.
- [ ] `ATT-005 P0` Late pickup, no-show and custody-conflict workflows.
- [ ] `ATT-006 P1` Kiosk mode with privacy shielding, signed device identity and offline queue.
- [ ] `ATT-007 P1` Guardian QR/PIN/signature options governed per facility; no biometric requirement.
- [ ] `ATT-008 P1` Room-to-room and indoor/outdoor movement ledger.
- [ ] `ATT-009 P1` Expected-versus-present dashboard and absence reason workflow.
- [ ] `ATT-010 P1` OSC school departure/arrival, bus/walk route and handoff evidence.
- [ ] `ATT-011 P1` Trip roster, vehicle boarding, destination headcounts and return reconciliation.
- [ ] `ATT-012 P2` Attendance anomaly detection as an explainable prompt, never an automatic accusation.
- [ ] `ATT-013 P2` Reconciliation against claims, invoices, staffing and parent records.
- [ ] `ATT-014 FUTURE` Emergency mesh that preserves headcounts across offline staff devices during an outage.

### Daily care, learning and family experience

- [x] `CARE-001 IMPLEMENTED` Feed, bottle, diaper, toilet, sleep, mood, activity, correction and void.
- [ ] `CARE-002 P0` Care-entry policy by age/program with required facts, safe defaults and impossible-state validation.
- [ ] `CARE-003 P1` Individual routines and plans surfaced at the point of care.
- [ ] `CARE-004 P1` Batch entry that preserves individual confirmation and audit.
- [ ] `CARE-005 P1` Photos/videos/observations with consent, audience and retention checks before capture/share.
- [ ] `CARE-006 P1` End-of-day digest with staff review, correction and guardian delivery status.
- [ ] `CARE-007 P1` Room daybook handoff between shifts and unresolved-task acknowledgement.
- [ ] `CARE-008 P1` Supply reminders for diapers, food, clothing and medication.
- [ ] `CARE-009 P2` Pattern summaries for sleep, feeding and toileting, explicitly non-diagnostic.
- [ ] `CARE-010 P2` Family-provided routine updates with educator acknowledgement.
- [ ] `LEARN-001 P1` Curriculum/activity planning by room, age, framework and learning goal.
- [ ] `LEARN-002 P1` Observation-to-portfolio workflow with guardian visibility controls.
- [ ] `LEARN-003 P1` Activity material, allergy, risk, staffing and consent checklist.
- [ ] `LEARN-004 P2` Developmental milestone observations without diagnosis or automated labeling.
- [ ] `LEARN-005 P2` Inclusive-programming plans and specialist collaboration log.
- [ ] `LEARN-006 P2` Portfolio export for family and transition to school.

### Health, allergies, illness and medication

- [x] `MED-001 IMPLEMENTED` Medication plans, authorization, activation, administration/refusal/omission and corrections.
- [ ] `MED-002 P0` Medication rights validation: child, drug, dose, route, time, authorization and staff.
- [ ] `MED-003 P0` Controlled access, inventory/quantity, storage location, expiry and disposal witnesses where required.
- [ ] `MED-004 P0` PRN indication, minimum interval, maximum dose and guardian-contact rules.
- [ ] `MED-005 P0` Allergy/anaphylaxis plan visible offline and at every relevant care surface.
- [ ] `MED-006 P0` Medication error/adverse-reaction escalation linked to incident evidence.
- [ ] `HLTH-001 P0` Illness assessment facts, exclusion decision, guardian contact, pickup and return criteria.
- [ ] `HLTH-002 P0` Symptom/outbreak line list with privacy-scoped public-health reporting support.
- [ ] `HLTH-003 P0` Store immunization information supplied by the parent, and proof/exemption evidence only where separately lawfully required; never claim Alberta childcare licensing universally requires proof or complete status.
- [ ] `HLTH-004 P1` Injury/body-map documentation with careful provenance and no AI-invented facts.
- [ ] `HLTH-005 P1` Individual health/support plan versioning, acknowledgement and review.
- [ ] `HLTH-006 P1` Public-health advisory and facility closure communication workflow.
- [ ] `HLTH-007 P2` Outbreak early-warning based on aggregated symptoms with human review and privacy thresholds.
- [ ] `HLTH-008 P2` Health-form integrations only through consented, minimum-necessary exchange.
- [ ] `HLTH-009 AVOID` No diagnosis, treatment recommendation or autonomous medical triage.

### Incidents, safeguarding and emergency readiness

- [x] `INC-001 IMPLEMENTED` Incident draft, review, finalization, return, report marker and history.
- [ ] `INC-002 P0` Severity/type-specific forms, mandatory facts and deadline clock.
- [ ] `INC-003 P0` Immediate safety actions, people notified, medical response and current child disposition.
- [ ] `INC-004 P0` Tamper-evident attachments, statements and chronology with provenance.
- [ ] `INC-005 P0` Human-controlled external reporting package and submission receipt.
- [ ] `INC-006 P0` Safeguarding restricted workspace, conflict-aware access and anti-retaliation audit.
- [ ] `INC-007 P0` Allegation workflow that separates allegation, evidence, finding and employment action.
- [ ] `INC-008 P1` Root-cause/corrective-action review with recurrence and effectiveness check.
- [ ] `INC-009 P1` Guardian acknowledgement/signature without implying agreement.
- [ ] `EMERG-001 P0` Emergency plans by hazard, facility, room, role and accessibility need.
- [ ] `EMERG-002 P0` Drill scheduling, attendance, duration, issues and corrective actions.
- [ ] `EMERG-003 P0` Offline emergency contacts, medications, attendance and reunification data.
- [ ] `EMERG-004 P0` Evacuation/reunification workflow with guardian identity and chain of custody.
- [ ] `EMERG-005 P1` Emergency broadcast with acknowledgements, escalation and delivery fallback.
- [ ] `EMERG-006 P2` Scenario simulator and after-action review.
- [ ] `INC-010 AVOID` No AI-generated incident facts, credibility judgments or autonomous abuse conclusions.

### Nutrition, food safety, sanitation and environment

- [ ] `FOOD-001 P0` Menu planning with allergens, substitutions, age suitability and dietary restrictions.
- [ ] `FOOD-002 P0` Meal-service record linked to child attendance and actual consumption.
- [ ] `FOOD-003 P0` Kitchen temperature, sanitation, receiving, storage and corrective-action logs.
- [ ] `FOOD-004 P0` Allergy-safe meal roster and cross-contact controls at preparation/service.
- [ ] `FOOD-005 P1` Recipe, nutrition and Canada Food Guide support with qualified review.
- [ ] `FOOD-006 P1` Vendor, lot/recall and affected-meal tracing.
- [ ] `FOOD-007 P2` Allergy menu compiler that proves every planned child/menu combination has a safe path.
- [ ] `ENV-001 P0` Opening/closing safety checklist and accountable sign-off.
- [ ] `ENV-002 P0` Cleaning/sanitizing schedules, diapering/toileting logs and missed-task escalation.
- [ ] `ENV-003 P0` Indoor/outdoor temperature, air-quality and unsafe-condition actions.
- [ ] `ENV-004 P1` Pest, water, playground and equipment inspection records.
- [ ] `ENV-005 P1` Maintenance request, hazard isolation, contractor and completion evidence.

### Transportation and off-site activities

- [ ] `TRIP-001 P0` Trip plan with destination, route, risk assessment, consent, staffing and emergency contacts.
- [ ] `TRIP-002 P0` Boarding/deboarding/headcount at every transition and vehicle sweep verification.
- [ ] `TRIP-003 P0` Driver licence, insurance, vehicle inspection, seat/restraint and expiry evidence.
- [ ] `TRIP-004 P0` OSC school/route stop assignments and authorized handoffs.
- [ ] `TRIP-005 P1` Delay, missed pickup, route exception and guardian notification.
- [ ] `TRIP-006 P1` Offline trip pack and device-to-device reconciliation.
- [ ] `TRIP-007 P2` Route optimization constrained by safety, capacity and promised windows.
- [ ] `TRIP-008 FUTURE` Vehicle sweep proof using deliberate human actions; no surveillance biometrics.
- [ ] `TRIP-013 P0` Child-specific home-transport plan with guardian request/consent, approved origin and destination, approved receivers, schedule, accessibility/medical constraints and effective dates.
- [ ] `TRIP-014 P0` Dispatch binds each run to one approved driver, vehicle, route version, child manifest, restraints, shift and accountable dispatcher before any address is revealed.
- [ ] `TRIP-015 P0` Home addresses and route details use minimum-necessary, assignment-bound mobile access that expires after the run; no general staff directory, background tracking or durable route export.
- [ ] `TRIP-016 P0` Same-day exceptional home transport requires a recorded guardian request, authorized facility approval and a complete driver/vehicle/consent preflight; staff may not improvise a private ride from a phone call alone.
- [ ] `TRIP-017 P0` Home handoff closes only to an approved receiver with time and staff evidence. A missing or unapproved receiver keeps the child in program custody and opens the failed-handoff escalation plan.
- [ ] `TRIP-018 P0` Dispatch removes the transporting staff member from on-site ratio/capacity calculations for the exact trip interval and prevents conflicting room or shift assignments.

## Master feature registry — pass 3: business, workforce and ecosystem

### Parent/guardian app and communications

- [ ] `PARENT-001 P0` Separate guardian identity and policy boundary; never reuse admin accounts.
- [ ] `PARENT-002 P0` Child/family access derived from effective custody and consent, not a loose foreign key.
- [ ] `PARENT-003 P1` Home dashboard: attendance, care digest, messages, invoices, forms and alerts.
- [ ] `PARENT-004 P1` Check-in/out and pickup delegation controls with expiry.
- [ ] `PARENT-005 P1` Secure two-way messaging, room announcements and emergency acknowledgements.
- [ ] `PARENT-006 P1` Forms, consent, signatures, document upload and annual confirmation.
- [ ] `PARENT-007 P1` Billing, autopay, receipts, tax statements and payer split.
- [ ] `PARENT-008 P1` Absence/vacation, schedule-change and pickup-change requests.
- [ ] `PARENT-009 P1` Daily reports, photos, portfolios and translation preferences.
- [ ] `PARENT-010 P1` Notification preferences with mandatory safety-message carve-out.
- [ ] `PARENT-011 P2` Family trust centre: access log, consent history, exports, retention and privacy requests.
- [ ] `PARENT-012 P2` Community/resources directory with moderation and no ad profiling.
- [ ] `PARENT-013 P2` Web plus native applications with equivalent critical capabilities.
- [ ] `PARENT-014 FUTURE` Custody-safe communication graph resolving exactly who may receive each fact.

### Documents, forms and signatures

- [ ] `DOC-001 P0` Versioned document store with tenant, subject, classification, retention and malware scan.
- [ ] `DOC-002 P0` Immutable originals plus derived preview/OCR artifacts and checksums.
- [ ] `DOC-003 P0` Fine-grained download/share audit and time-limited URLs.
- [ ] `DOC-004 P1` Form builder with conditional logic, validation and accessibility.
- [ ] `DOC-005 P1` Template/version/effective-date management and mass assignment.
- [ ] `DOC-006 P1` E-signature intent, signer identity, document hash, timestamp and evidence certificate.
- [ ] `DOC-007 P1` Expiry reminders and replacement/version history.
- [ ] `DOC-008 P1` Bulk import with preview, validation, rollback and provenance.
- [ ] `DOC-009 P2` Data extraction with confidence, field evidence and mandatory human confirmation.
- [ ] `DOC-010 P2` Disclosure/export packages with manifest and redaction review.

### Billing, payments, accounting and commerce

- [ ] `BILL-001 P0` Effective-dated fee plans by program, schedule, age and funding arrangement.
- [ ] `BILL-002 P0` Contract-to-charge engine with explainable line-item provenance.
- [ ] `BILL-003 P0` Immutable invoices, credit notes, adjustments, refunds and write-offs.
- [ ] `BILL-004 P0` Canadian tax handling and accountant-reviewed configuration.
- [ ] `BILL-005 P0` Payment processor tokenization; CareSync never stores raw card data.
- [ ] `BILL-006 P0` Payment allocation, partials, overpayments, failures, chargebacks and reconciliation.
- [ ] `BILL-007 P1` Autopay, reminders, statements, receipts and year-end tax receipts.
- [ ] `BILL-008 P1` Deposit, registration, late-pickup and ad-hoc charges with approval.
- [ ] `BILL-009 P1` Sibling/employee/contract discounts with effective dates and audit.
- [ ] `BILL-010 P1` Multiple payer responsibilities and confidential balances.
- [ ] `BILL-011 P1` General-ledger mapping and QuickBooks/Xero export/integration.
- [ ] `BILL-012 P1` Bank/processor reconciliation dashboard and exception queue.
- [ ] `BILL-013 P2` Revenue recognition, occupancy, aged receivables and forecast analytics.
- [ ] `BILL-014 P2` Multi-site consolidated finance with facility-level books.
- [ ] `BILL-015 AVOID` No opaque fee optimization or discriminatory pricing.

### Alberta affordability, subsidy, grants and claims

- [ ] `CLAIM-001 P0` Versioned Alberta funding-program rules with effective dates and source citations.
- [ ] `CLAIM-002 P0` Child/family funding eligibility facts separated from calculated recommendations.
- [ ] `CLAIM-003 P0` Claim-period lock, authorized preparation, review, approval and submission receipt.
- [ ] `CLAIM-004 P0` Attendance/enrolment/fee-to-claim reconciliation and explainable exception queue.
- [ ] `CLAIM-005 P0` Amendment/reversal/recovery lifecycle without deleting prior submissions.
- [ ] `CLAIM-006 P0` Government credential isolation; never store credentials unless an approved integration requires it.
- [ ] `CLAIM-007 P1` Affordability grant, subsidy, wage top-up, professional-development and inclusion-support workspaces.
- [ ] `CLAIM-008 P1` Supporting-document checklist, expiry and evidence bundle per program.
- [ ] `CLAIM-009 P1` Forecast versus remittance reconciliation and receivable aging.
- [ ] `CLAIM-010 P1` Claim anomaly prompts with human review, rule citation and no unsupported accusation.
- [ ] `CLAIM-011 P2` Funding scenario simulator for enrolment, attendance, fees and staffing.
- [ ] `CLAIM-012 P2` Audit-ready claim compiler mapping each submitted value back to source facts.
- [ ] `CLAIM-013 P2` Inclusion-funding plan/budget/outcome evidence with sensitive-access controls.
- [ ] `CLAIM-014 FUTURE` Alberta funding digital twin that replays a historical rule version before any correction.

### Staff records, HR and professional readiness

- [x] `STAFF-001 IMPLEMENTED` Staff invitations, activation, suspension, roles and room assignments.
- [x] `STAFF-002 IMPLEMENTED` Mobile profile, work history, credentials and location-free shift clock.
- [ ] `STAFF-003 P0` Employee identity separated from user login and candidate profile.
- [ ] `STAFF-004 P0` Effective-dated employment, position, facility, classification, pay and status.
- [ ] `STAFF-005 P0` Certification, first aid, criminal/vulnerable-sector checks and renewal evidence.
- [ ] `STAFF-006 P0` Qualification/ratio eligibility computed for each actual time slice.
- [ ] `STAFF-007 P0` Confidential HR file boundary distinct from operational child access.
- [ ] `STAFF-008 P1` Orientation/onboarding checklist, policies, training and supervisor sign-off.
- [ ] `STAFF-009 P1` Availability, time off, leave, accommodation and restrictions.
- [ ] `STAFF-010 P1` Timesheet corrections, approvals, overtime/break rules and payroll export.
- [ ] `STAFF-011 P1` Competency/training matrix, expiry, courses and professional-development funding.
- [ ] `STAFF-012 P1` Performance goals, check-ins and discipline with restricted access/retention.
- [ ] `STAFF-013 P1` Injury/OHS, return-to-work and accommodation workflows.
- [ ] `STAFF-014 P1` Offboarding: access revocation, final shift, asset return, record retention and alumni state.
- [ ] `STAFF-015 P2` Substitute/floater pool with verified readiness for facility, room and shift.
- [ ] `STAFF-016 P2` Workload and burnout indicators using transparent aggregate signals, not covert surveillance.
- [ ] `STAFF-017 P2` Credential passport controlled by the worker with verified issuer evidence.
- [ ] `STAFF-018 AVOID` No permanent location tracking, keystroke monitoring, emotion recognition or hidden productivity scoring.
- [ ] `STAFF-029 P0` Confidential criminal-record and vulnerable-sector-check document lifecycle: candidate upload, legal-name/date-of-birth reconciliation, issue date and jurisdiction, authorized human review, renewal/recheck policy, restricted vault access and immutable decision history. OCR may assist extraction but never decide suitability.
- [ ] `STAFF-030 P0` Effective-dated transport qualification separate from the educator role; a person may be educator-only, driver-only or approved for both, and losing driving readiness must not silently suspend unrelated educator duties.

### Recruiting, candidate marketplace and ATS

- [x] `ATS-001 IMPLEMENTED` Public marketplace, applications, interviews, offers, decisions and provisioning.
- [x] `ATS-002 IMPLEMENTED` Credential OCR, history, name mismatch confirmation and educator/student paths.
- [ ] `ATS-003 P0` Consolidate overlapping ATS/hiring/candidate APIs into one canonical state machine.
- [ ] `ATS-004 P0` Candidate consent, visibility, profile publication and deletion controls.
- [ ] `ATS-005 P0` Job publication lifecycle, location, requirements, pay range and closing/archival.
- [ ] `ATS-006 P0` Application state ledger visible consistently to candidate and employer in realtime.
- [ ] `ATS-007 P0` Interview scheduling, accept/decline/counter, timezone, reminders and outcome.
- [ ] `ATS-008 P0` Offer versioning, expiry, conditions, signatures, withdrawal and acceptance.
- [ ] `ATS-009 P0` Hire/provision transaction that cannot create partial employee/account/assignment state.
- [ ] `ATS-010 P1` Candidate search by verified qualifications, city, availability and consented fields.
- [ ] `ATS-011 P1` Screening rubrics, structured notes and conflict-of-interest controls.
- [ ] `ATS-012 P1` Reference requests, responses and candidate visibility policy.
- [ ] `ATS-013 P1` Candidate document vault, upgraded certification and employer notification.
- [ ] `ATS-014 P1` Talent pools, saved candidates, re-engagement consent and expiry.
- [ ] `ATS-015 P1` Hiring analytics: source, conversion, time-to-hire and fairness monitoring.
- [ ] `ATS-016 P2` Province-wide substitute marketplace with credential/availability validation.
- [ ] `ATS-019 P0` Job listings declare educator, driver or combined responsibilities plus required licence, vehicle and availability evidence; a driving duty cannot be introduced after application without a new visible offer version and candidate acceptance.
- [ ] `ATS-020 P0` Candidate transport profile distinguishes willingness to drive, licence class, access to a personal vehicle and preferred radius from employer-verified driver/vehicle readiness. Candidate claims are never treated as approval.
- [ ] `ATS-017 P2` Explainable match recommendations; employer/candidate must choose.
- [ ] `ATS-018 AVOID` No autonomous rejection, inferred protected traits, personality scoring or face/voice analysis.

### Workforce scheduling, shifts and time

- [ ] `WSCHED-001 P0` Effective-dated staff availability, role, certification and room eligibility.
- [ ] `WSCHED-002 P0` Shift creation, publication, acknowledgement, modification and cancellation ledger.
- [ ] `WSCHED-003 P0` Ratio-aware schedule validation against forecast children and breaks.
- [ ] `WSCHED-004 P0` Clock-in/out, break, correction and manager approval with audit.
- [ ] `WSCHED-005 P0` Configurable location verification; current local mode may disable geofencing explicitly.
- [ ] `WSCHED-006 P1` Open shifts, qualified offers, bids, swaps and manager approval.
- [ ] `WSCHED-007 P1` Time-off and leave request workflow with coverage impact.
- [ ] `WSCHED-008 P1` Break planning and live coverage warnings.
- [ ] `WSCHED-009 P1` Overtime, minimum-rest and employment-standard rule checks.
- [ ] `WSCHED-010 P1` Payroll-period lock, exceptions and export.
- [ ] `WSCHED-011 P2` Demand forecast from enrolment/attendance while protecting staff fairness.
- [ ] `WSCHED-012 P2` Explainable schedule optimizer with hard safety constraints and human publication.
- [ ] `WSCHED-013 P2` Call-out recovery playbook and readiness-ranked substitute suggestions.
- [ ] `WSCHED-014 AVOID` No schedule optimization that silently sacrifices legal compliance, accommodations or equitable workload.

### Child attendance analyzer and V3 scheduler

- [x] `ANL-001 DEFERRED-IMPLEMENTED` Deterministic V3 construction, repair/balance, realism redistribution, validation and certification.
- [x] `ANL-002 DEFERRED-IMPLEMENTED` Interactive phase visualization and replay telemetry.
- [x] `ANL-003 DEFERRED-IMPLEMENTED` Holiday/closure handling, duplicate claims, unmatched children and daily CSV ZIP export.
- [ ] `ANL-004 P0` Integrate advanced scheduler behind explicit entitlement without replacing Basic APIs.
- [ ] `ANL-005 P0` Exact claim-hour conservation and per-child/day constraint certificate.
- [ ] `ANL-006 P0` Daycare realistic-duration redistribution with deterministic seeds and reproducibility.
- [ ] `ANL-007 P0` OSC school-day split windows and school-calendar provenance.
- [ ] `ANL-008 P0` Capacity/ratio/staff feasibility—not merely a soft unique-child target.
- [ ] `ANL-009 P0` Impossible-request proof explaining which constraints prevent 100%.
- [ ] `ANL-010 P1` Scenario comparison, saved assumptions and diffable outputs.
- [ ] `ANL-011 P1` Human review/approval and immutable published schedule version.
- [ ] `ANL-012 P1` Reconciliation against actual attendance and variance analysis.
- [ ] `ANL-013 P2` Multi-objective optimization for realism, fairness, stability and operational feasibility.
- [ ] `ANL-014 P2` Constraint-learning suggestions from reviewed exceptions without silently changing policy.
- [ ] `ANL-015 P2` Privacy-safe synthetic stress-test generator and benchmark corpus.

### Payroll, benefits and workforce finance

- [ ] `PAY-001 P1` Payroll provider export/integration with employee mapping and reconciliation.
- [ ] `PAY-002 P1` Wage, premium, overtime, vacation and statutory-holiday rule configuration.
- [ ] `PAY-003 P1` Wage enhancement/top-up calculation and evidence.
- [ ] `PAY-004 P1` Benefits eligibility/enrolment document tracking without storing unnecessary medical detail.
- [ ] `PAY-005 P1` T4/ROE workflow support through approved providers rather than home-grown tax filing.
- [ ] `PAY-006 P2` Labour cost versus ratio, occupancy, funding and revenue analytics.
- [ ] `PAY-007 P2` Forecast and scenario planning with transparent assumptions.

### Facilities, inventory, procurement and assets

- [ ] `FAC-001 P1` Facility, room, zone, door, playground, vehicle and equipment registry.
- [ ] `FAC-002 P1` Asset serial, inspection, warranty, maintenance, recall and retirement history.
- [ ] `FAC-003 P1` Inventory levels, par, consumption, reorder and stockout alerts.
- [ ] `FAC-004 P1` Purchase request, approval, vendor, order, receipt and invoice match.
- [ ] `FAC-005 P1` Keys/access devices and issued-device lifecycle.
- [ ] `FAC-006 P1` Contractor access, insurance and safeguarding boundaries.
- [ ] `FAC-007 P2` Energy/utility and sustainability metrics where operationally useful.
- [ ] `FAC-008 P2` Capital plan and lifecycle-cost forecast.

### Reporting, analytics and decision support

- [ ] `RPT-001 P0` Governed metric dictionary with owner, formula, grain, exclusions and effective version.
- [ ] `RPT-002 P0` Source-to-report lineage and reconciliation for compliance/finance metrics.
- [ ] `RPT-003 P1` Role-specific dashboards for owner, director, educator, finance and compliance.
- [ ] `RPT-004 P1` Attendance, occupancy, ratio, enrolment, waitlist and retention reporting.
- [ ] `RPT-005 P1` Revenue, receivable, funding, labour and unit-economics reporting.
- [ ] `RPT-006 P1` Health, incidents, medication, training and corrective-action reporting.
- [ ] `RPT-007 P1` Filtered export with privacy warning, watermark and audit.
- [ ] `RPT-008 P1` Scheduled report delivery with recipient authorization rechecked at send time.
- [ ] `RPT-009 P2` Cohort/trend/forecast analysis with uncertainty and assumptions.
- [ ] `RPT-010 P2` Benchmarking only with sufficient aggregation, consent and anti-reidentification controls.
- [ ] `RPT-011 P2` Natural-language query constrained to governed semantic metrics and cited source rows.
- [ ] `RPT-012 AVOID` No vanity score that collapses child safety, staff performance or family quality into an unexplained number.

### Integrations, API and data portability

- [ ] `INT-001 P0` Versioned public API with OAuth scopes, tenant boundaries, quotas and deprecation policy.
- [ ] `INT-002 P0` Signed, retryable, idempotent webhooks with replay protection.
- [ ] `INT-003 P0` Integration credential vault, rotation and least privilege.
- [ ] `INT-004 P0` Import/export canonical schemas, validation report, provenance and rollback.
- [ ] `INT-005 P1` Email/SMS/push, calendar, accounting, payments, payroll and identity providers.
- [ ] `INT-006 P1` Government export adapters isolated from core records and rule-versioned.
- [ ] `INT-007 P1` School calendar/closure feeds with source and manual override.
- [ ] `INT-008 P1` SFTP/batch integration runner with PGP, checksum and reconciliation.
- [ ] `INT-009 P1` Developer portal, sandbox, keys, logs and sample payloads.
- [ ] `INT-010 P2` Integration marketplace with security/privacy review and tenant consent.
- [ ] `INT-011 P2` Event-stream/data-warehouse export with governed contracts.
- [ ] `INT-012 P2` Standards-based health/education exchange only when lawful and necessary.

### Mobile, kiosk, offline and device fleet

- [ ] `MOB-001 P0` Offline-first mutation queue with stable IDs, ordering, retry and visible conflicts.
- [ ] `MOB-002 P0` Minimum offline emergency dataset and encrypted local storage.
- [ ] `MOB-003 P0` Remote session/device revocation and lost-device response.
- [ ] `MOB-004 P0` Background sync rules that respect battery, network and platform limits.
- [ ] `MOB-005 P1` Kiosk/device enrollment, facility binding and restricted mode.
- [ ] `MOB-006 P1` App update policy, forced security minimum and graceful schema compatibility.
- [ ] `MOB-007 P1` Camera/document capture, compression, crop, accessibility and safe temporary-file cleanup.
- [ ] `MOB-008 P1` Push deep links that reauthorize the destination at open time.
- [ ] `MOB-009 P1` Tablet/phone/responsive layouts and large-text support.
- [ ] `MOB-010 P1` Offline roster/headcount reconciliation across multiple devices.
- [ ] `MOB-011 P2` Managed-device posture and MDM hooks for enterprise tenants.
- [ ] `MOB-012 P2` Privacy-safe diagnostics bundle the user can inspect before sharing.

### UX, accessibility, localization and design system

- [ ] `UX-001 P0` WCAG 2.2 AA target across public, admin, guardian and staff surfaces.
- [ ] `UX-002 P0` Keyboard, focus, screen-reader, contrast, zoom/reflow and reduced-motion acceptance tests.
- [ ] `UX-003 P0` Plain-language errors with action, preserved input and correlation ID.
- [ ] `UX-004 P0` Dangerous actions show scope/consequence and support undo where safe.
- [ ] `UX-005 P1` Dark-ice design tokens shared across web/mobile without sacrificing readability.
- [ ] `UX-006 P1` Density modes, responsive typography and comfortable long-shift ergonomics.
- [ ] `UX-007 P1` Command palette, universal search and role-aware shortcuts.
- [ ] `UX-008 P1` Full-page profiles/workspaces for complex records; drawers only for short reversible tasks.
- [ ] `UX-009 P1` Guided empty states and progressive disclosure without hiding status.
- [ ] `UX-010 P1` English/French architecture, locale-aware dates/numbers/timezones and RTL readiness.
- [ ] `UX-011 P1` User-tested terminology: checked out, not absent, where state meaning differs.
- [ ] `UX-012 P2` Accessibility profiles and cognitive-load controls.
- [ ] `UX-013 P2` Motion system tied to state transitions, progress and spatial orientation—not decoration overload.
- [ ] `UX-014 P2` Design-system documentation, visual regression and component governance.

### AI, OCR, optimization and automation governance

- [x] `AI-001 PARTIAL` Server OCR pipeline with field evidence, user confirmation and credential history.
- [x] `AI-002 DEFERRED-IMPLEMENTED` Chunked DeepSeek name matching and review concepts in the extension.
- [ ] `AI-003 P0` Model/provider registry with purpose, version, region, data terms, owner and approved inputs.
- [ ] `AI-004 P0` Durable asynchronous inference jobs; eliminate request-blocking local subprocess assumptions.
- [ ] `AI-005 P0` Evaluation corpus for certificate name/level/number/date by image quality and document variant.
- [ ] `AI-006 P0` Confidence per field, evidence bounding region and explicit unresolved state.
- [ ] `AI-007 P0` Human approval for identity, credential, hiring, funding, incident and safeguarding outputs.
- [ ] `AI-008 P0` Prompt/model/output audit, redaction, retention and tenant-safe observability.
- [ ] `AI-009 P0` Prompt injection, malicious document and data-exfiltration defenses.
- [ ] `AI-010 P1` Hybrid OCR pipeline: quality assessment, orientation, crop, ensemble extraction and consistency validation.
- [ ] `AI-011 P1` Resume extraction into editable claims with source spans; never treat inference as verified history.
- [ ] `AI-012 P1` Entity matching with deterministic candidates first, AI ranking second and one-to-one constraints.
- [ ] `AI-013 P1` Automation ledger: trigger, inputs, policy, recommendation, human decision and outcome.
- [ ] `AI-014 P1` Tenant opt-in, feature flags, cost/rate budgets and provider fallback.
- [ ] `AI-015 P2` Policy-aware assistant that cites CareSync records and applicable rule/policy versions.
- [ ] `AI-016 P2` Draft communications, forms and summaries with visible provenance and approval.
- [ ] `AI-017 P2` Explainable anomaly triage for attendance, claims and billing.
- [ ] `AI-018 P2` Constraint solvers for rooms, workforce and attendance with proof/certification.
- [ ] `AI-019 P2` Feedback/evaluation loop that separates correction labels from production facts.
- [ ] `AI-020 FUTURE` Private per-tenant retrieval assistant with field-level authorization at query and citation time.
- [ ] `AI-021 AVOID` No facial recognition of children/families/staff.
- [ ] `AI-022 AVOID` No emotion recognition, lie detection or inferred mental/health state.
- [ ] `AI-023 AVOID` No autonomous hiring rejection, child risk ranking, diagnosis or regulatory submission.
- [ ] `AI-024 AVOID` No training on tenant data without explicit informed contract/consent and isolation.

### Customer support, success and internal operations

- [ ] `SUP-001 P0` Tenant-safe support access with approval, purpose, time limit and full audit.
- [ ] `SUP-002 P0` No raw production-data copying into tickets by default; redaction and secure attachments.
- [ ] `SUP-003 P1` Help centre, contextual guidance, release notes and admin academy.
- [ ] `SUP-004 P1` In-app ticket, severity, SLA, status and customer-visible history.
- [ ] `SUP-005 P1` Onboarding/migration project checklist and data-quality report.
- [ ] `SUP-006 P1` Health dashboard for configuration gaps, expiring evidence and failed integrations.
- [ ] `SUP-007 P1` Feature-request/feedback system linked to outcomes, not vote count alone.
- [ ] `SUP-008 P1` Tenant diagnostics/replay with privacy-preserving fixtures.
- [ ] `SUP-009 P2` Customer-success playbooks by lifecycle and risk, with human ownership.
- [ ] `SUP-010 P2` Community and certified implementation-partner program.

## Master feature registry — pass 4: original differentiators

- [ ] `NOVEL-001 P2` Compliance twin: continuously map live facts to versioned obligations and missing evidence.
- [ ] `NOVEL-002 P2` Safety debt ledger: unresolved temporary workarounds, expired controls and compounding exposure.
- [ ] `NOVEL-003 P2` Evidence room: one-click, time-bounded, manifest-backed inspection collaboration space.
- [ ] `NOVEL-004 P2` Operational digital twin: occupancy, ratios, staff, rooms, funding and forecast in one simulation model.
- [ ] `NOVEL-005 P2` No-dead-end exception handling: every failed workflow offers retry, repair, defer-with-owner or escalation.
- [ ] `NOVEL-006 P2` Readiness graph: prove which staff can safely cover which room/shift/facility at a particular instant.
- [ ] `NOVEL-007 P2` Lifecycle identity graph from candidate to employee without collapsing legally distinct records.
- [ ] `NOVEL-008 P2` Family trust centre exposing exactly what is stored, who accessed it and why.
- [ ] `NOVEL-009 P2` Migration ledger: every imported value retains source file, row, transformation, confidence and correction.
- [ ] `NOVEL-010 P2` Regulation impact map identifying forms, code, training, data and customers affected by a rule change.
- [ ] `NOVEL-011 P2` Ethical feature gate requiring purpose, lawful basis, harms, human control, evaluation and rollback.
- [ ] `NOVEL-012 P2` Facility quality cockpit of explainable measures—never a single punitive score.
- [ ] `NOVEL-013 P2` Substitute readiness network that matches only consented, currently verified workers.
- [ ] `NOVEL-014 P2` Child transition simulator across birthdays, rooms, siblings, staffing and licensing capacity.
- [ ] `NOVEL-015 P2` Grant compiler that assembles figures/evidence while preserving human submission authority.
- [ ] `NOVEL-016 P3` Privacy firewall that simulates intended data disclosure and blocks excess fields before sending.
- [ ] `NOVEL-017 P3` Policy-to-product compiler generating candidate controls/tests from approved policy changes for human engineering review.
- [ ] `NOVEL-018 P3` Resilience theatre: scheduled outage/emergency simulations scored against recovery evidence.
- [ ] `NOVEL-019 P3` Federated benchmarks that reveal operational opportunity without exporting identifiable tenant data.
- [ ] `NOVEL-020 FUTURE` Local-first emergency continuity allowing a facility to operate safely for an extended internet outage and reconcile cryptographically afterward.

## Pass 5: adversarial gap scan

The registry was reread as six failure scenarios rather than as a feature catalogue.

### If the internet, vendor or device fails

- [ ] `RES-001 P0` Define exactly which child-safety workflows remain possible offline and for how long.
- [ ] `RES-002 P0` Printable/exportable emergency packs with freshness timestamp and controlled disposal.
- [ ] `RES-003 P0` Provider circuit breakers and manual fallback for email, SMS, payments, OCR and storage.
- [ ] `RES-004 P0` Conflict-safe reconciliation drills with two devices editing the same child/event.
- [ ] `RES-005 P0` Restore drills prove database plus object store plus audit/outbox consistency.

### If a bad or compromised actor uses valid access

- [ ] `ABUSE-001 P0` High-risk action monitoring for bulk export, custody, permissions, deletion and support access.
- [ ] `ABUSE-002 P0` Two-person approval for destructive tenant-wide actions and external high-risk submissions.
- [ ] `ABUSE-003 P0` Break-glass access with reason, short expiry, notification and post-review.
- [ ] `ABUSE-004 P0` Insider-threat response that protects whistleblowers and preserves evidence.
- [ ] `ABUSE-005 P1` Honey records/tokens only where legally reviewed and unable to affect child operations.

### If data is wrong, duplicated or historically inconsistent

- [ ] `DATA-001 P0` Duplicate detection and supervised merge for people, families, children and organizations.
- [ ] `DATA-002 P0` Append-only correction pattern for regulated facts; original always recoverable.
- [ ] `DATA-003 P0` Effective-time and recorded-time support for history-sensitive domains.
- [ ] `DATA-004 P0` Quarantine state for questionable imports instead of silently activating records.
- [ ] `DATA-005 P0` Cross-module invariants continuously checked with repair playbooks.
- [ ] `DATA-006 P1` Data-quality dashboard with owner, severity, age and downstream impact.
- [ ] `DATA-007 P1` Safe merge/split/reparent operations with preview and rollback journal.

### If a tenant leaves, fails to pay or CareSync ceases operation

- [ ] `EXIT-001 P0` Complete machine-readable and human-readable tenant export.
- [ ] `EXIT-002 P0` Contractual retention/deletion schedule, grace period and legal-hold exception.
- [ ] `EXIT-003 P0` Safety-critical access is never abruptly disabled during a billing dispute.
- [ ] `EXIT-004 P0` Provider escrow/continuity plan for critical source, keys and runbooks at scale.
- [ ] `EXIT-005 P1` Verified deletion certificate and backup-expiry statement.

### If policy, regulation or product behavior changes

- [ ] `CHANGE-001 P0` Effective-dated configuration and migrations preserve old calculations.
- [ ] `CHANGE-002 P0` Release impact notes identify affected roles, workflows, data and required training.
- [ ] `CHANGE-003 P0` Tenant sandbox/canary and rollback for high-impact behavior.
- [ ] `CHANGE-004 P1` Policy acknowledgement only after material diff is understandable.
- [ ] `CHANGE-005 P1` Historical replay test fixtures for ratios, fees, funding and permissions.

### If someone challenges a decision

- [ ] `EXPLAIN-001 P0` Every automated calculation emits input, rule version, steps, exceptions and result.
- [ ] `EXPLAIN-002 P0` Every recommendation is distinguishable from a fact and records the human decision.
- [ ] `EXPLAIN-003 P0` Appeals/correction channel for candidate, family, staff and billing outcomes.
- [ ] `EXPLAIN-004 P1` Timeline reconstruction uses immutable evidence and clearly marks later corrections.
- [ ] `EXPLAIN-005 P1` Exportable decision record uses plain language and protects unrelated people.

## Architecture destination and consolidation plan

Use a modular monolith first: one deployable FastAPI system with explicit bounded contexts, PostgreSQL/RLS, transactional outbox, durable workers, object storage, search, realtime fan-out, notification service, feature flags/entitlements and OpenTelemetry. Split services only when measured scaling, isolation or ownership demands it.

Bounded contexts:

```text
Identity/Tenancy | Licensing/Compliance | People/Families/Children | Enrolment/Admissions
Rooms/Attendance/Care | Health/Safety | Billing/Funding | Workforce/Time
Talent/ATS | Communications/Documents | Reporting/Analyzer | Platform/Integrations
```

Immediate architectural corrections:

1. Mount Basic and advanced capabilities together; remove the current mutually exclusive router mode.
2. Choose one canonical hiring state machine and adapt/delete overlapping `ats`, `hiring`, `candidate_hiring` and marketplace mutations.
3. Move OCR, notifications, exports, imports, claims and reports to durable jobs.
4. Introduce object storage before accumulating more photos, credentials, incident evidence or forms.
5. Establish a single actor/authorization/audit vocabulary across admin, guardian, candidate, staff and service accounts.
6. Establish canonical lifecycle events via outbox; projections may differ, facts may not.
7. Keep the V3 analyzer isolated until its exact conservation, feasibility proof and certification pass production tests.

## Delivery sequence

### Phase 0 — production foundation and unification

- Router/runtime unification; canonical ATS; database and object backup/restore drills.
- Production identity, verification, MFA, sessions, rate limits and support-access controls.
- Durable jobs, object storage, notification delivery, observability, CI/CD and secrets management.
- Privacy program, retention/legal hold, audit export, breach response and tenant exit.
- Cross-app lifecycle E2E: register organization, enroll child, invite/hire staff, shift, attendance, care, incident.

### Phase 1 — operational childcare MVP

- Licensing/conditions, ratios/capacity, complete child/family/custody records and admissions.
- Guardian app/portal, messaging, forms/consents and document vault.
- Attendance/headcounts, health/allergy/medication, incidents, emergency and daily care.
- Staff compliance, workforce scheduling/time, billing/payments and operational reports.

### Phase 2 — Alberta advantage

- Claims/funding compiler, reconciliation and rule-versioned Alberta pack.
- Inspection evidence room, compliance twin, staffing/capacity simulation and V3 analyzer integration.
- Full ATS/substitute network, accounting/payroll integrations, advanced family trust centre.

### Phase 3 — scale and intelligence

- Multi-site enterprise governance, API/marketplace, warehouse/benchmarks and jurisdiction packs.
- Governed AI assistant, document intelligence, anomaly triage and explainable optimization.
- Resilience theatre, privacy firewall and other validated novel capabilities.

## Definition of done for every capability

A checkbox becoming “implemented” requires all applicable evidence below:

- Product: named user, problem, success metric, non-goals and exception paths.
- Domain: canonical state machine, invariants, effective dates and terminology.
- Safety/legal: rule/policy sources, accountable human, escalation and prohibited automation.
- Security/privacy: authorization matrix, tenant isolation, data class, consent/lawful purpose, retention and abuse cases.
- Backend: validation, idempotency, concurrency, transaction, audit/outbox and migration/rollback.
- UX: loading, empty, error, offline, conflict, accessibility, localization and destructive-action safety.
- Operations: logs, metrics, traces, alert, runbook, provider failure and recovery target.
- Quality: unit, integration, contract, permission/RLS, E2E, accessibility, performance and restore tests.
- Documentation: admin/user/support/release notes and evidence location.

## Test and assurance portfolio still required

- [ ] Unit/property tests for calculations, state machines and parsers.
- [ ] API/schema/consumer contract tests across web, mobile, workers and integrations.
- [ ] PostgreSQL RLS and authorization matrix tests for every role/resource/action.
- [ ] Browser E2E for owner/director/educator/guardian and candidate lifecycles.
- [ ] Mobile E2E on supported Android/iOS devices including offline/conflict/update.
- [ ] Visual regression and WCAG automated plus manual assistive-technology tests.
- [ ] Performance/load/soak tests for check-in peaks, notifications, realtime and reports.
- [ ] Chaos/provider-failure and disaster-recovery/restore tests.
- [ ] Migration/import rehearsals on anonymized production-scale fixtures.
- [ ] Security SAST, dependencies, secrets, IaC, container and periodic penetration tests.
- [ ] AI/OCR evaluation, drift, adversarial document and human-override tests.
- [ ] Regulatory scenario corpus reviewed by qualified Alberta operators/advisers.

## Commercial model hypotheses to validate

- Charge primarily per location/organization tier, not per room or staff; unlimited rooms avoids hostile setup UX.
- Candidate marketplace remains free to candidates.
- Never place safety, custody, core compliance, export or account recovery behind an upsell.
- Possible public starting hypotheses: Core CAD 129/location/month; Operations 229; Intelligence 349; enterprise custom. These are research hypotheses, not approved pricing.
- Usage-priced pass-through may apply to SMS, payment processing and exceptional AI volume with transparent caps.
- Offer a real trial/sandbox with synthetic data; avoid requiring production child data to evaluate the product.

## Research baseline and sources (checked 2026-07-16)

Authoritative sources outrank competitor behavior. Requirements must be rechecked for effective dates before implementation.

- Alberta Child Care Licensing Regulation: https://www.canlii.org/en/ab/laws/regu/alta-reg-143-2008/latest/alta-reg-143-2008.html
- Alberta licensed facility-based programs: https://www.alberta.ca/licensed-facility-based-programs
- Alberta online child care claims: https://www.alberta.ca/online-child-care-claims-system
- Alberta affordability grants: https://www.alberta.ca/affordability-grants-for-child-care-programs
- Alberta child care subsidy: https://www.alberta.ca/child-care-subsidy-program
- Alberta child care grant funding: https://www.alberta.ca/alberta-child-care-grant-funding-program
- Alberta supports for inclusion: https://www.alberta.ca/child-care-supports-for-inclusion
- Alberta Health Services child-care health/safety guidance: https://www.albertahealthservices.ca/assets/wf/eph/wf-eh-health-safety-guidlines-child-care-facilities.pdf
- Alberta OIPC breach notification: https://oipc.ab.ca/breach-notification/
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- NIST Secure Software Development Framework: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST Digital Identity Guidelines: https://pages.nist.gov/800-63-4/sp800-63b.html
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/
- OWASP API Security: https://owasp.org/API-Security/
- Competitor parity research: https://mybrightwheel.com/features/ ; https://www.procaresoftware.com/capabilities/child-care-management-software/ ; https://www.lillio.com/features ; https://kangarootime.com/

### Alberta rule-pack validation notes

The current Alberta regulation describes program-specific staff-to-child ratios and maximum group sizes. The research pass recorded the following implementation candidates for facility-based daycare: under 12 months 1:3/group 6; 12–under 19 months 1:4/group 8; 19 months–under 3 years 1:6/group 12; 3–under 4 years 1:8/group 16; 4 years and older 1:10/group 20. OSC was recorded as 1:15/group 30. Preschool variants differ. These values must be loaded from a versioned rule pack, cross-checked against the licence and current consolidated regulation, and approved by a qualified Alberta operator/licensing adviser before production. They must never be scattered as constants across UI code.

The rule pack also needs explicit, sourced entries for mixed-age calculation, staff qualification, first aid, criminal/vulnerable-sector checks, child and portable emergency records, arrival/departure evidence, serious/critical incident reporting, medication, illness/exclusion, nutrition, off-site activity, transportation, physical environment, emergency plans, retention and licence-specific conditions. Where law, licensing guidance, public-health guidance and facility policy differ, CareSync must preserve the source and apply the strictest lawfully applicable approved control rather than inventing one universal answer.

## Re-analysis log

### Pass A — implementation truth

Inspected backend, migrations, portal, mobile, browser extension and tests. Result: the rebuild already has a meaningful operational core; it is not yet one production SaaS because Basic and advanced runtimes are mutually exclusive and several modules overlap.

### Pass B — Alberta operator/regulatory lens

Mapped licensing, ratios, records, staff readiness, incidents, health, medication, nutrition, transport, claims, privacy, employment and emergency evidence. Result: compliance must be a versioned evidence system, not checkboxes or a claim of guaranteed compliance.

### Pass C — market/parity lens

Compared current official feature pages from Brightwheel, Procare, Lillio and Kangarootime. Result: messaging, parent access, billing, admissions, workforce, documents and reporting are table stakes; copying a competitor is insufficient.

### Pass D — architecture/failure lens

Re-read the registry under outage, malicious insider, wrong data, tenant exit, rule change and challenged-decision scenarios. Added resilience, abuse, data, exit, change and explanation controls.

### Pass E — differentiation/ethics lens

Added compliance/funding twins, evidence room, readiness graph, privacy firewall, migration ledger and no-dead-end recovery. Explicitly rejected facial/emotion recognition, autonomous rejection/diagnosis/safeguarding and covert surveillance.

### Pass F — execution lens

Converted the catalogue into four phases and a definition of done. Result: the next work is not another isolated screen; it is production foundation and lifecycle unification, followed by the operational MVP.

## Open product decisions requiring Amar/operator validation

1. Exact initial customer: single Alberta facility, multi-site operator, or both at launch.
2. Whether billing/funding or family communication is the first post-foundation vertical.
3. Guardian mobile app versus responsive PWA sequencing.
4. Approved payment, email, SMS, push, object-storage, payroll and accounting providers/data regions.
5. Pricing and which advanced analyzer capabilities are separate entitlements.
6. Retention schedules by record category and contractual/legal-hold policy.
7. What location evidence, if any, production staff clocking should use; current mode is explicitly location-free.
8. Which Alberta licensing officer/privacy/legal/accounting practitioners will validate rule packs.
9. Brand/domain/company ownership, support model and production incident contact.
10. Whether public candidate marketplace launches with the daycare SaaS or after operational stability.

## Maintenance protocol

- Keep this file in version control and never put credentials, API keys or identifiable child/family/staff data in it.
- Add every feature with a stable ID, status, priority, owner/dependency when planned, and evidence link when implemented.
- Re-run implementation truth, regulatory, operator, market, failure, privacy/ethics and execution passes at every major phase.
- A new idea belongs in `FUTURE` until its user, harm analysis, data need and success measure are known.
- “Ultimate” means unusually complete, safe, recoverable and humane—not maximal complexity. A feature may be rejected when it adds more cognitive, privacy or safety cost than durable value.

---

# Second-generation expansion — 2026-07-16

This expansion takes the first six passes as established context. It does not restate the original registry. It adds domains and lifecycle edges exposed by another independent operator, regulatory, technical, product and failure review.

## Round 2, pass G — governance, legal entity and organizational control

- [ ] `GOV-001 P0` Legal-entity registry with corporation/non-profit/society identity, business number, status and evidence.
- [ ] `GOV-002 P0` Licence holder, directors, officers, signing authorities and beneficial-control record with effective dates.
- [ ] `GOV-003 P0` Delegation-of-authority matrix for contracts, hiring, payments, claims, incidents and external submissions.
- [ ] `GOV-004 P0` Conflict-of-interest declarations, recusal and related-party transaction review.
- [ ] `GOV-005 P0` Insurance policies, coverage, endorsements, exclusions, claims contacts and expiry.
- [ ] `GOV-006 P0` Material legal notice, demand, investigation and litigation-hold intake.
- [ ] `GOV-007 P1` Board/committee meetings, resolutions, voting, minutes, packages and restricted records.
- [ ] `GOV-008 P1` Corporate filing, annual return, licence, lease and major-contract calendar.
- [ ] `GOV-009 P1` Enterprise policy approval hierarchy and local-facility exception process.
- [ ] `GOV-010 P1` Risk register with owner, likelihood, impact, controls, residual risk and review date.
- [ ] `GOV-011 P1` Vendor/partner due diligence, contract, data-processing terms, insurance and renewal.
- [ ] `GOV-012 P1` Donation, grant-restriction and charitable-receipt support for eligible non-profits.
- [ ] `GOV-013 P1` Franchise/affiliate model with brand standards but strict tenant/data boundaries.
- [ ] `GOV-014 P2` Acquisition/divestiture workspace for consented tenant transfer, data mapping and continuity.
- [ ] `GOV-015 P2` Executive attestation pack covering finance, privacy, safety and compliance evidence.
- [ ] `GOV-016 P2` Public transparency profile for operator-controlled licence/program facts and validated quality information.
- [ ] `GOV-017 P3` Multi-entity consolidation with intercompany allocations and separately accountable licences.
- [ ] `GOV-018 AVOID` Never infer legal authority from job title alone; authority must be explicit, scoped and effective-dated.

## Round 2, pass H — family day home agency and home educator operating model

This is a distinct Alberta operating model, not a room type. Licensed agencies recruit, approve, train and monitor contracted home educators; Alberta describes scheduled and unscheduled monitoring visits and separate standards.

- [ ] `FDH-001 P1` Family day home agency licence, contract, territory, funded spaces and conditions.
- [ ] `FDH-002 P1` Contracted home educator identity distinct from employee and facility educator.
- [ ] `FDH-003 P1` Home approval lifecycle: application, checks, assessment, conditions, approval, suspension and closure.
- [ ] `FDH-004 P1` Home profile: household members, pets, smoking, water, sleeping, outdoor space, hazards and emergency exits.
- [ ] `FDH-005 P1` Home capacity including educator's own children and age composition at every time slice.
- [ ] `FDH-006 P1` Agency consultant/home visitor qualifications, caseload and conflict controls.
- [ ] `FDH-007 P1` Minimum monitoring-visit calendar with scheduled/unannounced classification and overdue escalation.
- [ ] `FDH-008 P1` Mobile home-visit checklist, evidence, findings, signatures and corrective actions.
- [ ] `FDH-009 P1` Ministry sample-inspection and agency evidence package.
- [ ] `FDH-010 P1` Educator contract, fee, payment, grant and remittance lifecycle.
- [ ] `FDH-011 P1` Backup-care provider, location, consent, capacity and handoff workflow.
- [ ] `FDH-012 P1` Substitute/caregiver authorization and home-specific readiness.
- [ ] `FDH-013 P1` Family placement/referral to homes with preference, capacity and human approval.
- [ ] `FDH-014 P1` Home closure, educator leave and emergency alternate-care communication.
- [ ] `FDH-015 P1` Home-specific attendance, claim, affordability and subsidy reconciliation.
- [ ] `FDH-016 P1` Agency consultant notes separated into operational, coaching, compliance and confidential categories.
- [ ] `FDH-017 P2` Caseload route planning constrained by due visits and unannounced-visit integrity.
- [ ] `FDH-018 P2` Home quality-improvement plan and educator mentorship evidence.
- [ ] `FDH-019 P2` Agency-wide risk/capacity dashboard without ranking educators through opaque scoring.
- [ ] `FDH-020 P3` Jurisdiction adapter for home-based models outside Alberta without corrupting Alberta semantics.

## Round 2, pass I — volunteers, practicum students, visitors and contractors

- [ ] `PEOPLE-001 P0` Person/engagement model distinguishing employee, contractor, volunteer, practicum student, visitor and guardian.
- [ ] `PEOPLE-002 P0` Screening, check, training and supervision requirements by engagement type.
- [ ] `PEOPLE-003 P0` Visitor sign-in/out, host, purpose, areas, badge and emergency headcount.
- [ ] `PEOPLE-004 P0` Restricted-person alert with confidential reason and safe front-desk response.
- [ ] `PEOPLE-005 P0` Contractor scope, safeguarding acknowledgement and escorted/unescorted access.
- [ ] `PEOPLE-006 P1` Practicum agreement linking institution, instructor, placement, hours, objectives and evaluation.
- [ ] `PEOPLE-007 P1` Student supervision plan; students never count toward ratios unless current law explicitly permits it.
- [ ] `PEOPLE-008 P1` Volunteer application, consent, orientation, schedule, supervisor and expiry.
- [ ] `PEOPLE-009 P1` Community presenter/activity-provider risk, insurance, consent and attendance.
- [ ] `PEOPLE-010 P1` Placement-hour verification and institution report with student approval.
- [ ] `PEOPLE-011 P1` External specialist visit with guardian consent and minimum-necessary child access.
- [ ] `PEOPLE-012 P1` Immediate access revocation and presence reconciliation when any engagement ends.
- [ ] `PEOPLE-013 P2` Placement pipeline for colleges and students, separate from paid-job ATS.
- [ ] `PEOPLE-014 P2` Skills-based volunteer opportunities with anti-exploitation controls.

## Round 2, pass J — complaints, concerns, appeals and enforcement

- [ ] `CASE-001 P0` Intake for family/staff/public complaint, licensing concern, privacy complaint and service issue.
- [ ] `CASE-002 P0` Anonymous/confidential reporting option with clear limitations and emergency direction.
- [ ] `CASE-003 P0` Triage that distinguishes immediate child safety, privacy breach, HR, billing and ordinary service recovery.
- [ ] `CASE-004 P0` Restricted case access, conflict-aware assignment and anti-retaliation safeguards.
- [ ] `CASE-005 P0` Evidence, chronology, communication and immutable decision record.
- [ ] `CASE-006 P0` Mandatory external escalation clock where applicable, with accountable human confirmation.
- [ ] `CASE-007 P1` Complainant acknowledgement, status, requests, outcome and appeal path without exposing third-party data.
- [ ] `CASE-008 P1` Corrective action, remedy, refund/credit and effectiveness review.
- [ ] `CASE-009 P1` Licence condition, probation, administrative penalty, closure/order and appeal lifecycle.
- [ ] `CASE-010 P1` Public-notice monitoring linked to operator response and continuity plan.
- [ ] `CASE-011 P1` Ombuds/privacy-regulator/law-enforcement request register with legal review.
- [ ] `CASE-012 P2` Thematic complaint analysis with small-cell privacy protection.
- [ ] `CASE-013 P2` Service-recovery playbooks and outcome measurement.
- [ ] `CASE-014 AVOID` No automated credibility scoring, retaliation-risk label or suppression of a report.

## Round 2, pass K — child guidance, inclusion and program quality

- [ ] `QUAL-001 P0` Approved child-guidance policy, staff acknowledgement and parent communication.
- [ ] `QUAL-002 P0` Prohibited-practice acknowledgement and immediate escalation when alleged/observed.
- [ ] `QUAL-003 P0` Individual support/accommodation plan with family, specialist, strategies, review and consent.
- [ ] `QUAL-004 P0` Inclusion support required-versus-funded gap without limiting admission automatically.
- [ ] `QUAL-005 P1` Observation-reflection-planning-learning-story cycle aligned to approved curriculum frameworks.
- [ ] `QUAL-006 P1` Educator reflective journal with explicit privacy and supervisor visibility boundaries.
- [ ] `QUAL-007 P1` Program plan version, goals, environment, routines, inclusion, family engagement and evaluation.
- [ ] `QUAL-008 P1` Environment/material audit for age suitability, inclusion, culture and accessibility.
- [ ] `QUAL-009 P1` Outdoor play, active play and screen-use policy evidence.
- [ ] `QUAL-010 P1` Child and family voice captured through age-appropriate, voluntary methods.
- [ ] `QUAL-011 P1` Mentorship/coaching plan separated from disciplinary HR records.
- [ ] `QUAL-012 P1` Referral/resource coordination with consent, purpose and disclosure record.
- [ ] `QUAL-013 P2` Quality-improvement experiments with baseline, intervention, outcome and unintended-effect review.
- [ ] `QUAL-014 P2` Curriculum resource library with provenance, cultural review and licensing.
- [ ] `QUAL-015 P2` Indigenous/community content governed through actual relationships, not tokenized generated content.
- [ ] `QUAL-016 AVOID` No child, educator or room leaderboard derived from observations.

## Round 2, pass L — insurance, claims and enterprise risk

- [ ] `RISK-001 P0` General liability, professional liability, cyber, property, vehicle and workers' coverage registry.
- [ ] `RISK-002 P0` Incident-to-insurer notice decision with deadline, policy and submission evidence.
- [ ] `RISK-003 P0` Claim file separated from care facts and protected by legal privilege configuration where valid.
- [ ] `RISK-004 P0` Certificate-of-insurance requests and additional-insured tracking for vendors/landlords.
- [ ] `RISK-005 P1` Property loss, business interruption and restoration-cost workflow.
- [ ] `RISK-006 P1` Cyber-insurance control/evidence questionnaire and renewal history.
- [ ] `RISK-007 P1` Risk acceptance requires authority, expiry and compensating controls.
- [ ] `RISK-008 P1` Near-miss and loss trend analysis linked to corrective action, not blame.
- [ ] `RISK-009 P1` Contract indemnity/insurance requirement register.
- [ ] `RISK-010 P2` Scenario-based financial exposure modeling with clearly stated assumptions.
- [ ] `RISK-011 P2` Renewal submission evidence pack assembled from verified controls.
- [ ] `RISK-012 AVOID` No claim-likelihood score used to deny a child, family or employee service.

## Round 2, pass M — calendars, events, community and internal knowledge

- [ ] `CAL-001 P1` Canonical organization/facility/program/room calendars with scoped visibility.
- [ ] `CAL-002 P1` Closures, holidays, school calendars, professional days and exceptional operating hours.
- [ ] `CAL-003 P1` Family events, RSVP, capacity, waitlist, consent, payment and reminders.
- [ ] `CAL-004 P1` Staff meetings/training with paid-time implications, attendance and minutes.
- [ ] `CAL-005 P1` Parent conferences with private scheduling, agenda, notes and follow-up.
- [ ] `CAL-006 P1` Field-trip/activity calendar linked to trip plans and consent readiness.
- [ ] `CAL-007 P1` External calendar subscriptions with revocable tokens and minimum details.
- [ ] `CAL-008 P1` Conflict detection across rooms, staff, vehicles, spaces and required participants.
- [ ] `CAL-009 P1` Newsletter/editor with audience, consent, translation, approval and delivery history.
- [ ] `CAL-010 P1` Staff intranet for policies, news, forms, resources and acknowledgement.
- [ ] `CAL-011 P1` Facility handover log for opening/closing staff and unresolved operational items.
- [ ] `CAL-012 P1` Community resource directory with owner, review date and eligibility notes.
- [ ] `CAL-013 P2` Volunteer/event coordination and post-event evaluation.
- [ ] `CAL-014 P2` Calendar impact preview when a closure changes billing, claims, staff and meals.
- [ ] `CAL-015 P2` Personalized agenda that remains explainable and never hides mandatory tasks.

## Round 2, pass N — SaaS revenue, trust and customer lifecycle

- [ ] `GTM-001 P0` Product catalogue, editions, entitlements, effective dates and safety-feature invariants.
- [ ] `GTM-002 P0` Quote, order form, contract, data-processing terms and activation state machine.
- [ ] `GTM-003 P0` Subscription ledger with plan, quantity, discounts, tax, renewal and cancellation.
- [ ] `GTM-004 P0` Processor-backed SaaS billing, webhook idempotency and reconciliation.
- [ ] `GTM-005 P0` Dunning/grace/read-only/export policy that never blocks immediate child safety.
- [ ] `GTM-006 P0` Trust centre: security, privacy, subprocessors, residency, uptime and incident history.
- [ ] `GTM-007 P1` Trial/sandbox containing only synthetic data with conversion/export controls.
- [ ] `GTM-008 P1` Sales CRM from lead through discovery, security review, quote, close and implementation.
- [ ] `GTM-009 P1` Customer implementation plan, readiness gates, migration acceptance and launch sign-off.
- [ ] `GTM-010 P1` Customer-success health from explicit service facts; no hidden manipulative score.
- [ ] `GTM-011 P1` Renewal, expansion, downgrade and cancellation workflow with reason/evidence.
- [ ] `GTM-012 P1` Support/SLA entitlement enforcement that preserves emergency pathways.
- [ ] `GTM-013 P1` Partner/referral/reseller attribution, commission and conflict controls.
- [ ] `GTM-014 P1` Procurement/security questionnaire evidence library with reviewed answers.
- [ ] `GTM-015 P2` Cohort retention, acquisition cost, lifetime value, support cost and gross-margin analytics.
- [ ] `GTM-016 P2` Feature adoption tied to customer outcomes, not dark-pattern engagement.
- [ ] `GTM-017 P2` Public roadmap/feedback communication without exposing security or contractual details.
- [ ] `GTM-018 P3` Regional/channel expansion gates based on support and regulatory readiness.

## Round 2, pass O — marketplace trust, liquidity and integrity

- [ ] `MARKET-001 P0` Candidate/employer authenticity and organization-affiliation verification.
- [ ] `MARKET-002 P0` Job scam, impersonation, credential tampering and abusive-message reporting.
- [ ] `MARKET-003 P0` Moderation case lifecycle with evidence, notice, appeal and proportionate action.
- [ ] `MARKET-004 P0` Candidate profile visibility modes, employer blocking and contact-information shielding.
- [ ] `MARKET-005 P0` Search/ranking explanation and explicit prohibition on protected-trait proxies.
- [ ] `MARKET-006 P1` Job freshness, duplicate detection, expiry and filled/closed outcomes.
- [ ] `MARKET-007 P1` Verified credential badges that state scope, issuer, method and freshness.
- [ ] `MARKET-008 P1` Employer/candidate response expectations and respectful status closure.
- [ ] `MARKET-009 P1` Interview no-show, offer withdrawal and dispute workflows without public shaming.
- [ ] `MARKET-010 P1` Candidate safety controls for interview address, contact and suspicious requests.
- [ ] `MARKET-011 P1` Supply/demand and time-to-fill metrics with privacy thresholds.
- [ ] `MARKET-012 P2` Substitute shift fulfilment, cancellation, backup and payment/contract boundaries.
- [ ] `MARKET-013 P2` Reputation limited to verified transactions and appealable factual dimensions.
- [ ] `MARKET-014 P2` Fair-exposure monitoring and cold-start support without paid concealment.
- [ ] `MARKET-015 AVOID` No sale of candidate data, pay-to-hide rejection status or addictive application mechanics.

## Round 2, pass P — domain architecture and proof-carrying workflows

- [ ] `ARCH-001 P0` Canonical domain glossary with one meaning for organization, facility, program, room, household, person and engagement.
- [ ] `ARCH-002 P0` Explicit state-machine catalogue with transition authorization and invalid-state tests.
- [ ] `ARCH-003 P0` Event catalogue with schema, producer, consumers, privacy class, ordering and compatibility.
- [ ] `ARCH-004 P0` Command/query ownership: exactly one context owns each mutation and source of truth.
- [ ] `ARCH-005 P0` Global actor envelope supporting user, service, support, guardian, candidate, device and system actions.
- [ ] `ARCH-006 P0` Resource identifiers that remain stable across imports, merges, projections and tenant moves.
- [ ] `ARCH-007 P0` Temporal model for effective time, recorded time, correction and supersession.
- [ ] `ARCH-008 P0` Money, attendance, shift, medication and incident facts use append-only/compensating semantics.
- [ ] `ARCH-009 P0` Transaction boundary map and saga compensation for cross-context workflows.
- [ ] `ARCH-010 P0` Outbox/inbox contract with idempotency key, dedupe horizon and poison-event policy.
- [ ] `ARCH-011 P0` File lifecycle contract from upload/quarantine/scan/classify/store/derive/share/retain/delete.
- [ ] `ARCH-012 P0` Authorization decision service/policy vocabulary shared by HTTP, workers, realtime, search and exports.
- [ ] `ARCH-013 P0` Entitlement checks separated from authorization and safety/legal retention access.
- [ ] `ARCH-014 P0` Configuration precedence: jurisdiction, licence, organization, facility, program and room.
- [ ] `ARCH-015 P0` Invariant registry with automated sentinel checks and accountable repair runbooks.
- [ ] `ARCH-016 P1` Workflow engine only for long-running human processes; core invariants stay in domain code.
- [ ] `ARCH-017 P1` Search index as disposable projection with authorization filters and source reconciliation.
- [ ] `ARCH-018 P1` Reporting semantic layer separated from transactional APIs and reconciled to source.
- [ ] `ARCH-019 P1` Data-contract CI that blocks breaking mobile/integration/event changes.
- [ ] `ARCH-020 P2` Architecture decision records with assumption, alternatives, consequences and revisit trigger.

## Round 2, pass Q — measurable non-functional requirements

- [ ] `NFR-001 P0` Availability SLO by criticality; emergency roster and attendance exceed marketing-page targets.
- [ ] `NFR-002 P0` Latency budgets for check-in, child roster, clock, medication and incident save.
- [ ] `NFR-003 P0` RPO/RTO per bounded context, including object evidence and audit/outbox consistency.
- [ ] `NFR-004 P0` Maximum acceptable realtime staleness and visible stale-state behavior.
- [ ] `NFR-005 P0` Peak-load model for morning check-in, afternoon checkout, payroll and month-end claims.
- [ ] `NFR-006 P0` Data-integrity SLO for lost, duplicated, reordered or orphaned regulated events.
- [ ] `NFR-007 P0` Notification delivery targets by emergency/urgent/routine severity and fallback.
- [ ] `NFR-008 P0` Offline survival target, cached-data freshness and reconciliation deadline.
- [ ] `NFR-009 P0` Accessibility release gate with automated and manual pass criteria.
- [ ] `NFR-010 P0` Supported browser/device/OS matrix and security-update policy.
- [ ] `NFR-011 P0` Backup restoration frequency and quarterly evidence standard.
- [ ] `NFR-012 P0` Vulnerability remediation targets by severity and exploitability.
- [ ] `NFR-013 P0` Privacy request, breach triage and deletion service targets.
- [ ] `NFR-014 P1` Capacity envelope and per-tenant noisy-neighbour budget.
- [ ] `NFR-015 P1` Object/media upload size, processing and preview-generation targets.
- [ ] `NFR-016 P1` Background-job completion/retry/dead-letter budgets by job class.
- [ ] `NFR-017 P1` Recovery usability: staff can identify system state and safe next action during degradation.
- [ ] `NFR-018 P1` Localization quality gate for truncation, dates, pluralization and translated critical content.
- [ ] `NFR-019 P1` Supportability gate: correlation, audit and diagnostics sufficient without database improvisation.
- [ ] `NFR-020 P2` Energy/cost efficiency budgets for storage, realtime polling, OCR and AI inference.

## Round 2, pass R — additional original differentiators

- [ ] `NOVEL-021 P2` Proof-carrying operation: high-risk actions return the facts, policy version and authorization proof that permitted them.
- [ ] `NOVEL-022 P2` Invariant sentinel: continuously detects impossible cross-module states before users encounter them.
- [ ] `NOVEL-023 P2` Evidence-decay forecast: predicts when expiring documents, staff readiness or stale consents will invalidate future operations.
- [ ] `NOVEL-024 P2` Operational consequence preview: shows which children, rooms, claims, invoices, shifts and messages an edit will affect.
- [ ] `NOVEL-025 P2` Reversible automation contract: every automation declares rollback/compensation and a human stop control.
- [ ] `NOVEL-026 P2` Trust-preserving correction: one correction propagates to projections while every historical statement remains reproducible.
- [ ] `NOVEL-027 P2` Minimum-necessary view compiler that assembles each role's screen from purpose-authorized facts.
- [ ] `NOVEL-028 P2` Rule conflict detector identifying contradictions between law, licence condition, facility policy and user configuration.
- [ ] `NOVEL-029 P2` Readiness certificate for tomorrow: capacity, ratios, staff, health plans, meals, transport and closures preflighted nightly.
- [ ] `NOVEL-030 P2` Human attention budget that limits low-value alerts and protects urgent-signal visibility.
- [ ] `NOVEL-031 P2` Cross-tenant mutual-aid exchange for emergency spaces, substitutes and supplies with explicit consent and privacy firewalls.
- [ ] `NOVEL-032 P2` Family burden map measuring repeated requests for the same verified information and eliminating them safely.
- [ ] `NOVEL-033 P2` Policy simulation using synthetic historical scenarios before activation.
- [ ] `NOVEL-034 P3` Privacy-preserving proof that a credential/control is valid without disclosing the underlying document broadly.
- [ ] `NOVEL-035 P3` Failure-aware interface that changes available actions based on confirmed provider/system degradation.
- [ ] `NOVEL-036 P3` Counterfactual audit: explain what would have happened under another approved rule version.
- [ ] `NOVEL-037 P3` Regulatory change radar that opens traceable product, policy, training and customer-impact work.
- [ ] `NOVEL-038 FUTURE` Inter-facility emergency capacity network with regulator-approved governance and no automatic child transfer.

## Round 2, pass S — Alberta rule-engine hard refinements

These are acceptance constraints for the Alberta jurisdiction pack. They refine earlier broad features and must be revalidated against the current consolidated law, licensing guidance, the facility's actual licence and qualified advice before release.

- [ ] `ABRULE-001 P0` Mandatory child-protection report path bypasses manager approval; it records support/evidence without delaying the reporter.
- [ ] `ABRULE-002 P0` `LEGAL_IMPLEMENTATION` Critical incidents use the current director-designated immediate phone channel and portal submission as soon as possible, no later than the currently instructed 24 hours; source/effective-date this rule rather than attributing the precise clock directly to static Regulation text.
- [ ] `ABRULE-003 P0` `LEGAL_IMPLEMENTATION` Other reportable incidents use the current director-designated portal workflow within the currently instructed two business days, with an effective-dated business calendar and source.
- [ ] `ABRULE-004 P0` Versioned incident classifier includes evacuation affecting safety, unexpected closure, intruder, serious illness/injury, medication error, unexpected absence and unauthorized removal.
- [ ] `ABRULE-005 P0` Versioned critical classifier includes criminal-nature allegations, serious emergency/hospital injury, death, missing child, police involvement and closure while children are in care.
- [ ] `ABRULE-006 P0` Incident timers use occurrence/discovery/report times, business calendar, facility timezone and proof of phone/portal submission.
- [ ] `ABRULE-007 P0` Family day home educator reports immediately to agency; agency external submission responsibility remains explicit.
- [ ] `ABRULE-008 P0` Program-plan/licence changes identify when prior Statutory Director/licensing approval is required; configuration cannot pre-empt approval.
- [ ] `ABRULE-009 P0` Ratio calculation covers ordinary and permitted rest-period ratios separately.
- [ ] `ABRULE-010 P0` Mixed-age calculation uses the applicable majority/youngest-child rule and records the actual age composition.
- [ ] `ABRULE-011 P0` Infant mixing is constrained by applicable ages, hours, exemptions and licence conditions.
- [ ] `ABRULE-012 P0` Minimum-adult-presence rule for seven or more children is independently evaluated from numeric ratio.
- [ ] `ABRULE-013 P0` Program-supervisor presence/designate rules and whether the supervisor may count in ratio are time-sliced.
- [ ] `ABRULE-014 P0` Staff certification composition is evaluated separately from staff-to-child numeric ratio.
- [ ] `ABRULE-015 P0` OSC, preschool, daycare and combined-program calculations remain distinct rule paths.
- [ ] `ABRULE-016 P0` Capacity distinguishes licensed spaces, maximum group size, ratio capacity, net indoor area, outdoor area and actual usable area.
- [ ] `ABRULE-017 P0` Outdoor-space calculation models age-specific area and percentage-of-licensed-capacity requirements where applicable.
- [ ] `ABRULE-018 P0` Staff, volunteers and relevant adult/minor supervision checks use role-specific current requirements and expiry.
- [ ] `ABRULE-019 P0` First-aid coverage is evaluated for actual present staff, excursions and transport—not merely document completeness.
- [ ] `ABRULE-020 P0` Posted licence, notices, emergency information and required parent information have location/freshness evidence.
- [ ] `ABRULE-021 P0` Unexpected closure workflow connects incident reporting, parent pickup, attendance reconciliation, billing/funding and reopening approval.
- [ ] `ABRULE-022 P0` Prohibited child-guidance practices generate immediate safety escalation and preserve the reporter's exact observations.
- [ ] `ABRULE-023 P0` Child disclosure notes preserve the child's own words and distinguish observation, report and inference.
- [ ] `ABRULE-024 P0` Reporting screens visibly direct immediate danger to emergency services and provide the current provincial intake path.
- [ ] `ABRULE-025 P1` Licence variance/exemption has request, authority, scope, conditions, expiry and downstream rule-engine impact.
- [ ] `ABRULE-026 P1` Administrative penalty/probation/order/public-notice state changes trigger operational and family continuity review.
- [ ] `ABRULE-027 P1` Affordability, subsidy, wage-top-up and inclusion rule packs model agreement status and non-transferability where applicable.
- [ ] `ABRULE-028 P1` Optional fees/discounts and parent charges are validated against the currently applicable funding agreement, not assumptions.
- [ ] `ABRULE-029 P1` Employment schedule validation models Alberta hours, break, rest, notice, reporting-pay and overtime rules with exceptions/versioning.
- [ ] `ABRULE-030 P1` Regulatory contact information and external form/link metadata are remotely updateable, approved and periodically verified.

New authoritative references checked for this refinement:

- Alberta incident/concern/complaint reporting: https://www.alberta.ca/childcare-report-an-incident-concern-or-complaint
- Alberta mandatory child-abuse reporting: https://www.alberta.ca/report-child-abuse
- Alberta child-care quality and child guidance: https://www.alberta.ca/deliver-high-quality-childcare
- Current consolidated Child Care Licensing Regulation: https://www.canlii.org/en/ab/laws/regu/alta-reg-143-2008/latest/alta-reg-143-2008.html
- Alberta family day home agencies: https://www.alberta.ca/licensed-family-day-home-agencies
- Alberta approved family day homes: https://www.alberta.ca/become-an-approved-family-day-home
- Alberta hours of work and rest: https://www.alberta.ca/hours-work-rest
- Alberta overtime: https://www.alberta.ca/overtime-hours-overtime-pay
- W3C Verifiable Credentials 2.0 overview: https://www.w3.org/TR/vc-overview/
- W3C Verifiable Credentials Data Model 2.0: https://www.w3.org/TR/vc-data-model-2.0/

## Round 2 risk additions

- `R2-RISK-001` Offline custody authority may remain stale after an urgent revocation; signed snapshots need short expiry and explicit emergency reconciliation.
- `R2-RISK-002` Accurate OCR can be mistaken for issuer verification; UI and data must separate extracted, user-confirmed, CareSync-reviewed and issuer-verified states.
- `R2-RISK-003` Marketplace design may change worker classification, agency, insurance or employer responsibilities.
- `R2-RISK-004` Metrics may cause staff to optimize recording rather than care; measure gaming and unintended behavior.
- `R2-RISK-005` Ownership transfer may violate licence/funding non-transferability, consent, contract or retention duties.
- `R2-RISK-006` Product experiments are inappropriate in safety, custody, accessibility, billing and regulated-decision workflows without exceptional review.
- `R2-RISK-007` A compromised rule-pack update can create systematic legal error; rule packs require signing, review, canary replay and rollback.
- `R2-RISK-008` DST, wrong device clocks and timezone changes can corrupt medication, shifts, attendance, incidents and claims.
- `R2-RISK-009` External-professional collaboration can expose unrelated records unless authorization is child-, purpose-, field- and time-scoped.
- `R2-RISK-010` Mutual-aid networks create custody, qualification, insurance, transport and responsibility boundaries that must be resolved before launch.

## Round 2, pass T — inspection-grade operational deltas

These additions translate the Alberta refinement into separately testable product records rather than leaving it only in `ABRULE-*` acceptance constraints.

### Licence and statutory record precision

- [ ] `LIC-017 P0` Versioned program-plan register with philosophy, services, staffing, procedures, spaces and approved amendments.
- [ ] `LIC-018 P1` Licence application workspace for location, program plan, municipal/health/fire approvals, information session, fee and inspection.
- [ ] `LIC-019 P1` Licence variance workflow with decision, conditions, effective date and impacted rule recalculation.
- [ ] `LIC-020 P1` Exemption register with exact requirement, authority, compensating plan, posting duty and automatic expiry.
- [ ] `LIC-021 P1` Appeal calendar/evidence for licence, certification and administrative-penalty decisions.
- [ ] `LIC-022 P0` Ownership/change-of-control workflow recognizing licences and funding agreements may not transfer.
- [ ] `LIC-023 P0` Enforcement lifecycle distinguishing allegation, non-compliance, warning, order, probation, suspension, cancellation and penalty.
- [ ] `LIC-024 P1` Reconciliation with Alberta lookup, public-notice and administrative-penalty sources.
- [ ] `LIC-025 P0` Posted-artifact evidence for licence, visit summary, safety plan, exemption, menu and emergency information.
- [ ] `LIC-026 P1` Regulatory snapshot storing publisher, title, consolidation/effective/retrieved dates, checksum, supersession and reviewer.
- [ ] `REC-001 P0` Exact statutory child-record completeness and on-premises/current availability view.
- [ ] `REC-002 P0` Exact administrative-record view for child/staff attendance, care hours, certification, first aid and checks.
- [ ] `REC-003 P0` Two-year minimum attendance retention rule with longer retention only under separately recorded authority.
- [ ] `REC-004 P0` Guardian reasonable-access workflow shielding other children, staff-confidential and custody-restricted information.
- [ ] `REC-005 P0` Licensing-inspection access during connectivity failure with later disclosure reconciliation.
- [ ] `REC-006 P0` Exact Alberta portable schema: child name and date of birth; parent name and telephone; alternate emergency-contact name and telephone; relevant health information supplied by the parent, including immunization/allergy information if any; and local emergency-response and poison-control numbers. Keep additional custody, medication and contact facts as separately classified safety controls.
- [ ] `REC-007 P1` Periodic drill proving regulated electronic records are available on premises during an outage.

### Guidance, direct reporting and exact readiness

- [ ] `GUIDE-001 P0` Guidance-policy communication and version acknowledgement by staff, families and developmentally capable children.
- [ ] `GUIDE-002 P0` Explicit prohibited-practice control covering punishment, degradation, deprivation, restraint, confinement and isolation.
- [ ] `GUIDE-003 P0` Guidance event records observable antecedent, response and outcome without stigmatizing labels.
- [ ] `GUIDE-004 P0` Exceptional immediate-safety intervention is separated from ordinary guidance and reviewed as safeguarding.
- [ ] `GUIDE-005 P1` Scenario-based prohibited-practice competency and renewal.
- [ ] `SAFE-001 P0` Every worker has a direct statutory child-intervention reporting path that internal workflow cannot block.
- [ ] `SAFE-002 P0` Forthwith-report support with current emergency/intake contacts and confidential contemporaneous notes.
- [ ] `SAFE-003 P0` Preserve child's words verbatim; discourage leading questions and prohibit AI rewriting.
- [ ] `SAFE-004 P0` Exclude alleged persons and conflicted delegates from safeguarding access without identifying reporter.
- [ ] `SAFE-005 P0` Keep child-intervention, licensing, police and employment processes distinct and cross-referenced.
- [ ] `STAFF-019 P0` Role-specific criminal/vulnerable-sector-check timing, renewal and receipt deadlines.
- [ ] `STAFF-020 P0` Prevent unsupervised access and ratio eligibility before required checks are received.
- [ ] `STAFF-021 P0` Under-18 worker/volunteer direct-supervision and per-adult limits.
- [ ] `STAFF-022 P0` Dual first-aid coverage test: at least one on duty and required proportion of primary staff.
- [ ] `STAFF-023 P0` Supervisor duty/designation, absence and Level 3 eligibility ledger.
- [ ] `STAFF-024 P0` Level 1 certification deadline and supervised-access rules for uncertified staff.
- [ ] `STAFF-025 P0` Program/time-specific qualification composition alongside numeric ratio.
- [ ] `STAFF-026 P0` Certification lookup/status/conditions reconciliation immediately affects readiness.
- [ ] `STAFF-027 P1` Parent-volunteer preschool exception and automatic cessation.
- [ ] `STAFF-028 P1` Volunteer operational identity and readiness remains separate from employee status.

### Physical, health, food and trip precision

- [ ] `ROOM-017 P1` Preschool as a first-class Alberta program type, including its applicable duration semantics.
- [ ] `ROOM-018 P0` Approved net indoor play-space capacity by program and current square-metre rule.
- [ ] `ROOM-019 P0` Outdoor-space capacity by licensed percentage, age and approved usable area.
- [ ] `ROOM-020 P0` Outdoor occupancy, enclosure/gate evidence and approved exemption/OSC-location overlay.
- [ ] `ROOM-021 P0` Legally defined rest-period mode rather than a generic lower-ratio toggle.
- [ ] `ROOM-022 P0` Mixed-age majority/group-size calculation with ties and incomplete-age failure state.
- [ ] `ROOM-023 P0` Infant-mixing hours/threshold/exemption enforcement.
- [ ] `ROOM-024 P0` Minimum-adult staffing evaluated independently of child ratio.
- [ ] `ROOM-025 P0` Supervisor-counting eligibility by period, staffing and approved conditions.
- [ ] `ROOM-026 P0` “Actively supervising” state; presence, clock-in or assignment alone is insufficient.
- [ ] `ROOM-027 P1` Approved exemption/transport overlay with scope, time and rule trace.
- [ ] `MED-007 P0` Original-labelled-container and label-direction validation.
- [ ] `MED-008 P0` Emergency medication remains accessible to authorized responders/child but inaccessible to other children.
- [ ] `HLTH-010 P0` Illness exclusion records facts, pickup, separated supervision and authorized return evidence.
- [ ] `HLTH-011 P0` Sick-child supervision logic models age/disability direct-care requirements.
- [ ] `HLTH-012 P0` When a child becomes ill, immediately notify the parent, arrange removal as soon as possible, use the alternate emergency contact when required, provide necessary medical attention and apply required isolation/direct supervision; record actual timestamps without inventing a statutory minute limit.
- [ ] `INC-011 P0` Current Alberta reportable/critical incident taxonomy as a signed rule-pack artifact.
- [ ] `INC-012 P0` Separate effective-dated licensing phone/portal clocks using current director instructions, timezone and business calendar; never merge 911, Child Intervention, licensing, public health, police, OHS, WCB, privacy, insurer or internal-notification clocks.
- [ ] `INC-013 P0` Licensing-requested safety-plan approval and parent communication workflow.
- [ ] `INC-014 P0` Criminal-investigation preservation mode respects authority instructions and avoids witness contamination.
- [ ] `INC-015 P1` Public/visit-summary linkage with authorized redaction.
- [ ] `EMERG-007 P0` Posted emergency/poison/child-abuse contacts, evacuation procedures and external after-hours contact.
- [ ] `EMERG-008 P0` Staff/child evacuation-procedure communication and drill evidence.
- [ ] `ENV-006 P0` Smoke/vape-free control across every care location.
- [ ] `ENV-007 P0` Facility/trip first-aid kit inventory based on workers, hazard and medical distance.
- [ ] `ENV-008 P1` Applicability decision and evidence for public-health review/approval before opening or relevant construction, renovation or playground work where the authority and activity require it.
- [ ] `ENV-009 P1` Animal approval, health, food separation, supervised handling, hygiene and bite response.
- [ ] `ENV-010 P0` Sharps/biomedical-waste control.
- [ ] `ENV-011 P0` Sanitizer/disinfectant DIN, concentration, test, preparation, expiry and outbreak mode.
- [ ] `FOOD-008 P0` Posted menu version plus actual substitution/served history.
- [ ] `FOOD-009 P0` Infant bottle/food name-label verification and wrong-child prevention.
- [ ] `FOOD-010 P0` Developmentally safe seated/still feeding and no beverages during rest.
- [ ] `FOOD-011 P1` Parent-provided shared-food approval and allergen trace.
- [ ] `CARE-011 P1` Infant sleep equipment assignment, instructions, inspection and recall.
- [ ] `TRIP-009 P0` Off-site transport/contact/supervision disclosure and unretracted written consent.
- [ ] `TRIP-010 P0` Portable-record possession verified before departure and evacuation.
- [ ] `TRIP-011 P1` Home-to-program transportation separated from attendance/funding/billing time.
- [ ] `TRIP-012 P1` School-transport exemption scope cannot leak into unrelated staffing periods.

### Current Alberta funding mechanics

- [ ] `CLAIM-015 P0` `AGREEMENT_RULE` Versioned monthly preparation, submission, advance, payment and recovery calendar sourced to the signed/current funding pack.
- [ ] `CLAIM-016 P0` `AGREEMENT_RULE / PRODUCT_STANDARD` CCPN search-before-create and supervised duplicate identity resolution using the applicable portal/funding process.
- [ ] `CLAIM-017 P0` `AGREEMENT_RULE` Funding evidence matrix for registrations, attendance, timesheets, payroll and program-specific proof.
- [ ] `CLAIM-018 P0` `AGREEMENT_RULE` Current hour-band/parent-fee rule pack by program and eligibility; rates and formulas never live as timeless constants.
- [ ] `CLAIM-019 P0` `AGREEMENT_RULE` Optional-service consent, permitted fee, equal-access and reporting controls from the applicable signed agreement.
- [ ] `CLAIM-020 P1` `AGREEMENT_RULE / LEGAL_APPLICABILITY` Extended-hours/overnight supplemental-fee rules plus the separately sourced consecutive-care safety guard.
- [ ] `CLAIM-021 P0` `AGREEMENT_RULE / LEGAL_APPLICABILITY` Eligibility impact for entity, ownership, licence, program, profit status and funded-space limits.
- [ ] `CLAIM-022 P0` `AGREEMENT_RULE` Wage-top-up deadline/pass-through reconciliation to named educator and payroll evidence.
- [ ] `CLAIM-023 P1` `AGREEMENT_RULE` Claim-advance liability when actual entitlement is below the advance.

Additional authoritative source snapshots:

- Alberta facility licensing handbook, April 2025: https://open.alberta.ca/dataset/997f35bc-930d-44e5-b33b-a139087adc65/resource/2529eb5e-a49d-4056-a08f-792294fc29b3/download/jet-child-care-licensing-handbook-facility-based-programs-2025-04.pdf
- Child, Youth and Family Enhancement Act: https://www.canlii.org/en/ab/laws/stat/rsa-2000-c-c-12/latest/rsa-2000-c-c-12.html
- Alberta childcare lookup tools: https://www.alberta.ca/childcare-lookup-tools
- Alberta administrative penalties: https://www.alberta.ca/childcare-administrative-penalties
- Alberta childcare fees: https://www.alberta.ca/childcare-fees

## Round 2 convergence and implementation consequence

### Pass G — organizational reality

Added legal entity, board, delegated authority, insurance, ownership change, enterprise risk and public enforcement. A childcare SaaS cannot treat the tenant as merely a name and logo.

### Pass H — operating-model breadth

Added Alberta family day home agency/home educator, volunteer, practicum, contractor, visitor and authorized-professional models. These are structurally different relationships, not alternate staff roles.

### Pass I — customer and market operation

Added calendars/events/intranet, CareSync quote-to-cash/trust/procurement, and two-sided marketplace integrity/liquidity. A product can be operationally excellent yet commercially unshippable without these systems.

### Pass J — architecture and measurable quality

Added canonical states/events/actors, temporal semantics, invariant sentinels, file lifecycle, transaction/saga boundaries and concrete NFR budgets. “Reliable” is now something the program must measure and prove.

### Pass K — Alberta adversarial review

Rechecked the full registry against current Alberta operator guidance. Added direct child-protection reporting, exact incident clocks, guidance/prohibited practices, program-plan approval, ratio edge cases, physical-space rules, staff eligibility, statutory records, health/environment/food precision and current claim mechanics.

### Pass L — frontier review

Added proof-carrying operations, evidence-decay forecasting, rule-conflict detection, consequence preview, reversible automation, human attention budgets and privacy-preserving credential concepts. These remain later-stage until their simpler foundations exist.

### Revised immediate build gate

Before broad feature implementation resumes, convert the following into executable specifications and tests:

1. Canonical identity/actor/engagement and authorization model from the architecture and people registries.
2. Basic/advanced runtime and ATS state-machine consolidation.
3. Alberta signed/versioned rule-pack format plus regulatory source snapshot/review workflow.
4. Direct safeguarding and exact incident-reporting design.
5. Time-sliced room, ratio and staff-readiness model.
6. Statutory/offline emergency record schema and availability drill (`REC-*`).
7. Durable jobs, object lifecycle, notifications, observability and recovery proof.
8. One complete cross-app vertical slice exercised in production-like E2E before adding another domain.

The document still cannot guarantee that no future feature will ever be conceived. Its purpose is stronger: preserve an auditable method that repeatedly finds missing domains, distinguishes obligations from ideas, rejects harmful automation, and turns additions into stable implementable controls.

---

# Third-generation deep-research expansion — 2026-07-16

This cycle deliberately researched outside childcare-software feature lists. It uses adjacent legal, public-health, workforce, emergency, financial, evidence, security and international child-safety systems to expose requirements CareSync would otherwise discover only after a failure.

## Round 3 corrections to earlier assumptions

- Canadian-region hosting remains the preferred CareSync risk posture, but PIPA does not impose one universal private-sector localization rule. Foreign service providers require accountable policy, country/purpose disclosure and individual notice/contact pathways.
- WCAG 2.2 AA is a binding CareSync product and procurement standard once adopted; it is not described here as a universal Alberta private-sector statutory mandate.
- OCAP® is a First Nations data-governance framework led by participating Nations/communities. CareSync must never claim OCAP compliance merely because it stores an Indigenous identity field.
- Fire, building, occupancy and evacuation requirements are permit-, use-, municipality-, code-version- and authority-having-jurisdiction specific. School drill frequencies are not copied into daycare rules.
- Childcare licensing, Child Intervention, police, public health, privacy, OHS, WCB and insurer reporting are separate decisions and clocks.
- OCR confidence means extraction confidence, not credential authenticity or issuer verification.

## Round 3, pass U — privacy rights and accountable processing

- [ ] `PRIV-019 P0` Privacy officer identity, delegation, contact channel and coverage during absence.
- [ ] `PRIV-020 P0` Personal-information inventory mapping field, purpose, authority/consent, subject, source, system, processor and recipient.
- [ ] `PRIV-021 P0` Written access-request intake, identity assurance, 45-day clock/extension and response package.
- [ ] `PRIV-022 P0` Access redaction for another person, safety risk, confidential opinion and legally privileged material.
- [ ] `PRIV-023 P0` Correction workflow propagates accepted corrections to prior recipients where required.
- [ ] `PRIV-024 P0` Denied correction annotates the record with request and decision rather than erasing disagreement.
- [ ] `PRIV-025 P0` Foreign processor register with country, authorized purpose, safeguards, policy access and named question contact.
- [ ] `PRIV-026 P0` Provide the applicable PIPA section 13.1 notice before or at the required point for outside-Canada provider collection, or before direct/indirect transfer, and maintain country/purpose policies; this is not a universal Canadian localization mandate.
- [ ] `PRIV-027 P0` Breach decision tree for real risk of significant harm, OIPC notice, affected-person communication and evidence.
- [ ] `PRIV-028 P0` Privacy-breach register includes suspected/alleged events, containment, affected data, harms and rationale.
- [ ] `PRIV-029 P0` Processor contract enforces purpose limits, safeguards, subprocessor control, incident notice, return/deletion and audit.
- [ ] `PRIV-030 P0` Employee privacy/whistleblower anti-retaliation control for refusing or reporting PIPA violations.
- [ ] `PRIV-031 P0` `PRODUCT_STANDARD` Require a PIA for high-risk AI, biometrics, surveillance, matching and sensitive integrations. Submission is voluntary under PIPA but may be legally required for tenants/flows governed by Alberta public-body or health privacy law.
- [ ] `PRIV-032 P1` Privacy notice compiler renders audience/purpose-specific plain-language notices from the processing inventory.
- [ ] `PRIV-033 P1` Consent receipt captures statement/version, scope, channel, actor, timestamp, evidence, withdrawal and downstream effects.
- [ ] `PRIV-034 P1` Purpose-change assessment blocks incompatible reuse until new authority/consent and notice exist.
- [ ] `PRIV-035 P1` Data-subject request portal for guardian, candidate, employee and customer with identity/authority separation.
- [ ] `PRIV-036 P1` Privacy-preserving test/support data transformation with reidentification-risk review.
- [ ] `PRIV-037 P2` Machine-readable data-use ledger showing every processor and external disclosure affecting a subject.
- [ ] `PRIV-038 P2` Privacy budget for analytics/benchmarking, minimum cohorts and cumulative disclosure risk.

## Round 3, pass V — child media, devices and digital safeguarding

- [ ] `MEDIA-001 P0` Media policy separates care documentation, family sharing, curriculum, internal training, marketing and legal evidence.
- [ ] `MEDIA-002 P0` Per-child, per-purpose, per-audience consent checked at capture, composition, publication and later reuse.
- [ ] `MEDIA-003 P0` Service-managed device requirement for routine child images; personal-device capture is prohibited except documented emergency policy.
- [ ] `MEDIA-004 P0` Managed camera roll uploads directly to protected storage and avoids consumer cloud/photo-library synchronization.
- [ ] `MEDIA-005 P0` Device media cannot be exported to arbitrary apps, clipboard, personal backup or generative-AI services.
- [ ] `MEDIA-006 P0` Capture screen shows consent/restriction indicators without revealing confidential custody reasons.
- [ ] `MEDIA-007 P0` Multi-child photo audience is the intersection of every visible child's valid permissions.
- [ ] `MEDIA-008 P0` Withdrawn consent prevents future use and queues review/removal where promises or law require it.
- [ ] `MEDIA-009 P0` Original, derivative, crop, blur, caption, audience, download and deletion history remain linked.
- [ ] `MEDIA-010 P0` Strip EXIF/location/device identifiers from shared derivatives while preserving protected original evidence where justified.
- [ ] `MEDIA-011 P0` Media-access anomaly detection covers repeated viewing, bulk download, unusual hours and unrelated-room access.
- [ ] `MEDIA-012 P0` Lost/stolen managed-device response revokes keys and identifies unsynced/local media exposure.
- [ ] `MEDIA-013 P1` Parent event-photography policy and consent-aware guidance for images containing other children.
- [ ] `MEDIA-014 P1` External photographer/professional authorization, screening, purpose, device, transfer and destruction evidence.
- [ ] `MEDIA-015 P1` Watermark/audience marker deters redistribution but is never represented as technical prevention.
- [ ] `MEDIA-016 P1` Child-appropriate assent where developmentally meaningful, in addition to guardian authority.
- [ ] `MEDIA-017 P1` Media retention by purpose, with short default for unpublished captures and review for portfolios/evidence.
- [ ] `MEDIA-018 P2` Local/on-device redaction of unrelated children before external AI or processor use.
- [ ] `MEDIA-019 AVOID` No generated, face-swapped, age-progressed or synthetic media representing an identifiable child.
- [ ] `MEDIA-020 AVOID` No engagement optimization based on which child photos produce more parent activity.

## Round 3, pass W — fire, building, occupancy and premises approvals

- [ ] `FIRE-001 P0` Authority-having-jurisdiction record for fire, building, health, zoning and occupancy approvals.
- [ ] `FIRE-002 P0` Fire-safety plan version, approval, responsible persons, alternates and distribution.
- [ ] `FIRE-003 P0` Alarm, sprinkler, extinguisher, emergency lighting, suppression and inspection/test histories.
- [ ] `FIRE-004 P0` Evacuation route/muster map by room, mobility need, sleeping child and blocked-route alternative.
- [ ] `FIRE-005 P0` Drill frequency/rules derived from current applicable approval/code, not a generic constant.
- [ ] `FIRE-006 P0` Drill captures occupancy, staff, visitors, route, duration, missed person, equipment and corrective action.
- [ ] `FIRE-007 P0` Fire-system impairment permit/watch, temporary controls, notification and restoration.
- [ ] `FIRE-008 P0` Hot-work/contractor permit where applicable with isolation and post-work watch.
- [ ] `FIRE-009 P1` Fire inspection/order/finding and reinspection evidence.
- [ ] `FIRE-010 P1` Emergency responder premises pack: hazards, utilities, floor plan, children needing assistance and contacts.
- [ ] `FIRE-011 P1` Overnight/extended-care code and sleeping-occupancy overlay requiring explicit approval.
- [ ] `FIRE-012 P1` Alternate-site capacity and transport feasibility for prolonged evacuation.
- [ ] `FIRE-013 P2` Evacuation simulation tests route obstruction, staffing absence and accessibility constraints.
- [ ] `FIRE-014 AVOID` Never infer code compliance solely from a completed checklist.
- [ ] `BLDG-001 P0` Permit/occupancy registry with code edition, use classification, capacity, conditions and approved drawings.
- [ ] `BLDG-002 P0` Prevent CareSync activation of an affected space until applicable permits, inspections, occupancy approval, licensing update and authority conditions are recorded; CareSync itself does not claim statutory closure/reopening authority.
- [ ] `BLDG-003 P0` Net usable-area measurement, excluded spaces, measurer, drawing/version and approval evidence.
- [ ] `BLDG-004 P0` Accessibility route, door, washroom, change area and evacuation-assistance inventory.
- [ ] `BLDG-005 P0` Utility shutoff, electrical panel, gas, water, HVAC and hazardous-material locations.
- [ ] `BLDG-006 P1` Lease/landlord responsibility matrix for inspections, repairs, access and emergency systems.
- [ ] `BLDG-007 P1` Occupier/public hazard workflow for parking, snow/ice, entry, playground and deliveries.
- [ ] `BLDG-008 P1` Capital project phase gates from concept through permit, construction, commissioning and licence update.
- [ ] `BLDG-009 P1` Drawing revision control and field-verification record.
- [ ] `BLDG-010 P2` Space planning simulation against licences, ratios, accessibility, circulation and emergency egress.

## Round 3, pass X — environmental public health and workplace law

### Environmental public health

- [ ] `PUBH-001 P0` Applicable-rule profile for food, institutions, communicable disease, sanitation, housing and aquatic facilities.
- [ ] `PUBH-002 P0` Food-service applicability, permit, inspection and certified-handler coverage decision.
- [ ] `PUBH-003 P0` Drinking-water source, testing, advisory/boil-water, alternate supply, closure and reopening workflow.
- [ ] `PUBH-004 P0` Sewage/plumbing failure isolation, alternate facilities, reporting and reopening criteria.
- [ ] `PUBH-005 P0` Public-health authority/contact ledger distinct from symptom tracking and family messages.
- [ ] `PUBH-006 P0` Authority-directed outbreak cleaning plan with product, concentration, contact time, room and completion proof.
- [ ] `PUBH-007 P1` Inspection/order, corrective evidence, reinspection and public-record reconciliation.
- [ ] `PUBH-008 P1` Indoor-air hazard register for ventilation, combustion, carbon monoxide, mould, smoke and temperature.
- [ ] `PUBH-009 P1` Pest/pesticide treatment, child exclusion, SDS, ventilation and re-entry criteria.
- [ ] `PUBH-010 P1` Blood/body-fluid exposure response, PPE, cleanup, waste, follow-up and confidentiality.
- [ ] `PUBH-011 P1` Pool/wading/water-play approval and risk workflow distinct from ordinary trip consent.
- [ ] `PUBH-012 P1` Product-recall ingestion for food, cribs, toys, furniture and restraints with quarantine/disposition proof.

### Occupational health and WCB

- [ ] `OHS-001 P0` Formal worksite hazard assessment with worker participation, hierarchy of controls and review triggers.
- [ ] `OHS-002 P0` Worker emergency plan separate from child evacuation while coordinated with it.
- [ ] `OHS-003 P0` Named/trained rescue and evacuation roles with competence/drill evidence.
- [ ] `OHS-004 P0` Violence/harassment prevention plan, worker consultation, instruction, reporting, investigation, corrective action and three-year/triggered review; retain each investigation report for at least two years after the incident and make it available as required.
- [ ] `OHS-005 P0` Highly restricted domestic/sexual-violence spillover safety plan.
- [ ] `OHS-006 P0` Serious/potentially-serious worker incident classifier and OHS clock separate from licensing.
- [ ] `OHS-007 P0` Refusal-of-dangerous-work workflow preserving investigation, reassignment, pay/status and result.
- [ ] `OHS-008 P1` Joint committee/representative applicability, membership, meetings, recommendations and employer response.
- [ ] `OHS-009 P1` Working-alone assessment/check-in where a worker works alone and assistance is not readily available; opening, closing, transport, maintenance and administration are risk prompts, not automatic legal classification.
- [ ] `OHS-010 P1` Hazardous products within WHMIS scope use inventory, SDS, labels, training and inaccessible storage; ordinary consumer products are not automatically treated as WHMIS products.
- [ ] `OHS-011 P1` Ergonomic/manual-handling controls for lifting children, food, supplies and equipment.
- [ ] `OHS-012 P1` Young-worker orientation, hazards, permits/consent and prohibited tasks.
- [ ] `OHS-013 P1` Occupational exposure and respiratory program only after qualified necessity assessment.
- [ ] `OHS-014 P1` Link worker injury, child incident, hazard and insurance claim without merging confidential records.
- [ ] `WCB-001 P0` Classify WCB reportability first; for a reportable injury or illness, track the employer report within 72 hours after employer awareness rather than starting the clock for every first-aid-only event.
- [ ] `WCB-002 P0` Separate worker, employer, health-provider, OHS and childcare submissions/receipts.
- [ ] `WCB-003 P0` Modified/return-to-work plan uses functional restrictions, duration and accommodation—not diagnosis disclosure.
- [ ] `WCB-004 P1` Claim, wage-loss, absence, modified-duty and payroll reconciliation under restricted access.
- [ ] `WCB-005 P1` Account/premium/status calendar by employing legal entity/worksite.
- [ ] `WCB-006 P1` Occupational exposure record linkable to later claim without broad operational health disclosure.

### Employment standards and human rights

- [ ] `HRSTD-001 P0` Alberta rule pack for hours, breaks, rest, overtime, holidays, vacation, leaves, pay, deductions and termination.
- [ ] `HRSTD-002 P0` Required meeting/training time includes pay, minimum reporting pay and overtime consequences.
- [ ] `HRSTD-003 P0` Split-shift, call-back and performed on-call work calculations.
- [ ] `HRSTD-004 P0` Overtime banking agreement, employee copy, accrual, use, expiry and termination payout.
- [ ] `HRSTD-005 P0` General-holiday eligibility, pay, alternate day and facility calendar.
- [ ] `HRSTD-006 P0` Job-protected leave eligibility, notice, documentation, position protection and return.
- [ ] `HRSTD-007 P0` Final earnings calculation/deadline including wage, overtime bank, vacation and holiday amounts.
- [ ] `HRSTD-008 P1` Material schedule-change risk warning requiring human/legal review.
- [ ] `HRSTD-009 P1` Pay statement and employment record retention/export with calculation source and corrections.
- [ ] `HRSTD-010 P1` Collective agreement, averaging arrangement and variance overlays never weaken statutory minimums.
- [ ] `HRSTD-011 P1` Province rule boundary follows where work occurs, not headquarters.
- [ ] `HRSTD-012 P1` Employee/contractor/volunteer classification review; product labels never decide legal status.
- [ ] `HRIGHT-001 P0` Separate accommodation cases for employment/candidates, child/family service and public users.
- [ ] `HRIGHT-002 P0` Functional needs/restrictions without unnecessary diagnosis collection.
- [ ] `HRIGHT-003 P0` Interactive request, evidence, alternatives, consultation, decision, implementation and review.
- [ ] `HRIGHT-004 P0` Undue-hardship decision requires accountable human evidence and legal review, never a software score.
- [ ] `HRIGHT-005 P0` Admissions/waitlist criteria adverse-effect and protected-ground review.
- [ ] `HRIGHT-006 P0` `PRODUCT_STANDARD / RISK_CONTROL` Candidate forms default to no protected-ground questions. An exception requires documented lawful/job-related purpose, minimum collection, restricted access and human-rights/privacy review; BFOR is not generic collection permission.
- [ ] `HRIGHT-007 P0` Accommodate services connected to protected grounds, including disability and religious belief, to the point of undue hardship; treat language, culture and communication inclusion as product commitments unless linked to a protected ground, and service animals through disability accommodation.
- [ ] `HRIGHT-008 P0` Schedule accommodation protects sensitive reasons from ordinary schedulers.
- [ ] `HRIGHT-009 P1` Accommodation conflict view surfaces safety/ratio constraints while requiring alternatives.
- [ ] `HRIGHT-010 P1` Human-rights complaint confidentiality, anti-retaliation, remedy and policy correction.
- [ ] `HRIGHT-011 P1` Equity audit of admissions, fees, guidance, hiring, scheduling and termination with minimum necessary data.

## Round 3, pass Y — evidence, fleet, Indigenous governance and insurance

### Electronic evidence and signatures

- [ ] `EVID-001 P0` Record-integrity evidence contains system version, authorship, authoritative time, hash and correction chain.
- [ ] `EVID-002 P0` Preserve origin, destination, transmission time and readable original for electronic regulated records.
- [ ] `EVID-003 P0` Signature assurance policy by document class; checkbox acceptance is not universally sufficient.
- [ ] `EVID-004 P0` Signer authentication strength and reliable association to the exact document version.
- [ ] `EVID-005 P0` Finalized signed document cannot mutate unnoticed; amendments are linked new versions.
- [ ] `EVID-006 P1` Ordinary-course system evidence describes procedures, controls, backups and audits supporting integrity.
- [ ] `EVID-007 P1` Legal hold preserves native format, metadata, attachments, audit and rendering capability.
- [ ] `EVID-008 P1` Certified export/affidavit-support bundle without claiming automatic legal admissibility.
- [ ] `EVID-009 P1` Clock governance handles UTC, facility timezone, DST ambiguity, trusted source and device drift.

### Vehicle fleet and transport compliance

- [ ] `FLEET-001 P0` Rule applicability derives from vehicle design, passenger capacity, use and jurisdiction.
- [ ] `FLEET-002 P0` Driver licence class/endorsement, restriction, abstract, expiry and vehicle authorization.
- [ ] `FLEET-003 P0` Registration, insurance, safety-fitness and inspection applicability with expiry lockout.
- [ ] `FLEET-004 P0` Pre/post-trip inspection, defect severity, repair and out-of-service state.
- [ ] `FLEET-005 P0` Child restraint assignment by age/size, vehicle and law plus installation/condition check.
- [ ] `FLEET-006 P0` Capacity includes every child, staff member, restraint and accessibility position.
- [ ] `FLEET-007 P0` Driver fitness, fatigue, impairment and medication escalation without diagnostic surveillance.
- [ ] `FLEET-008 P0` Weather, road, visibility and wildfire cancellation authority/risk assessment.
- [ ] `FLEET-009 P0` Collision/breakdown: accountability, alternate transport, notifications, reports and evidence.
- [ ] `FLEET-010 P0` Deliberate front-to-back human vehicle sweep with unresolved-child escalation and no biometrics.
- [ ] `FLEET-011 P1` Carrier safety program where applicable: restraints, defensive driving, fueling, speed and impairment.
- [ ] `FLEET-012 P1` Approved fueling/charging procedure when children are aboard or nearby.
- [ ] `FLEET-013 P1` Transport contractor due diligence and incident/data responsibility.
- [ ] `FLEET-014 P1` School-handoff exceptions for absent child, closure, route change or missing receiver.
- [ ] `FLEET-015 P1` Maintenance, recall, tire and odometer schedule with immobilization for safety defect.
- [ ] `FLEET-016 P0` Personal-vehicle readiness keeps driver licence, registration, ownership/permission, applicable automobile/business-use insurance, inspection, seating/restraint capacity and expiry evidence distinct.
- [ ] `FLEET-017 P0` Vehicle source is explicit—program-owned, staff personal, rental or contractor—and selects the correct approval, insurance, maintenance and responsibility workflow.
- [ ] `FLEET-018 P1` Mileage, approved expenses and trip-time compensation are derived from the completed dispatch record without exposing child route details to payroll exports.

### Indigenous collective data governance

- [ ] `INDIG-001 P0` Nation/community agreement before any OCAP®- or CARE-aligned claim.
- [ ] `INDIG-002 P0` Collective-data classification separated from an individual's identity field.
- [ ] `INDIG-003 P0` Community authority, purpose, access, possession, sharing, retention, return and destruction terms.
- [ ] `INDIG-004 P0` Block benchmarking, AI, research and product analytics absent applicable collective authority.
- [ ] `INDIG-005 P0` Community consent/engagement does not collapse into ordinary guardian consent.
- [ ] `INDIG-006 P1` Community-controlled access, export, audit and service-transition capability.
- [ ] `INDIG-007 P1` Cultural knowledge/media labels for audience, season, ceremony, role and community permissions.
- [ ] `INDIG-008 P1` First Nations, Inuit and Métis governance remain distinct; OCAP® is not universal shorthand.
- [ ] `INDIG-009 P1` Indigenous names/orthography and kinship structures without forced Western household schemas.
- [ ] `INDIG-010 P1` Community-agreement-level residency/possession and subprocessor approval.
- [ ] `INDIG-011 P1` Community benefit/harm review before aggregate research or release.
- [ ] `INDIG-012 AVOID` Never infer identity, Nation, status, culture or eligibility from name, location, relatives or documents.

### Insurance and claims governance

- [ ] `INS-001 P0` Policy register for liability, property, abuse/molestation, professional, cyber, interruption, crime, vehicle and D&O.
- [ ] `INS-002 P0` Limits, deductibles, exclusions, endorsements, insured entity/location and renewal evidence.
- [ ] `INS-003 P0` Policy-specific notice clock and privilege/confidentiality review from incident to insurer.
- [ ] `INS-004 P0` Certificate expiry lock for vehicles, landlords, contractors and high-risk providers.
- [ ] `INS-005 P1` Claim, adjuster, counsel, reserve, deductible, evidence request, authority and settlement lifecycle.
- [ ] `INS-006 P1` Business-interruption dependency map across closure, property, cyber, utility and supplier failures.
- [ ] `INS-007 P1` Annual coverage-gap review against enrolment, payroll, revenue, property, vehicle and cyber exposure.
- [ ] `INS-008 P1` Vendor coverage requirements derive from work risk and contract.
- [ ] `INS-009 P1` Minimum-necessary review before disclosing safeguarding, medical or legal records to insurer.
- [ ] `INS-010 P2` Loss-run/near-miss prevention analysis without punitive person risk scores.

### Source additions for passes U–Y

- Alberta PIPA responsibilities and foreign processors: https://www.alberta.ca/organization-responsibilities-for-protecting-personal-information
- Alberta PIPA access/correction: https://www.alberta.ca/accessing-your-personal-information.aspx
- Alberta OIPC privacy impact assessments: https://oipc.ab.ca/privacy-impact-assessments/
- Canadian Centre for Cyber Security baseline controls: https://www.cyber.gc.ca/en/guidance/baseline-cyber-security-controls-small-and-medium-organizations
- Alberta workplace violence/harassment: https://www.alberta.ca/workplace-harassment-violence
- Alberta OHS: https://www.alberta.ca/occupational-health-safety
- WCB employer injury process: https://www.wcb.ab.ca/claims/report-an-injury/for-employers.html
- Alberta Human Rights goods/services: https://albertahumanrights.ab.ca/issues-with-services/goods-and-services/
- Alberta Human Rights accommodation at work: https://albertahumanrights.ab.ca/issues-at-work/duty-to-accommodate-at-work/
- FNIGC OCAP®: https://fnigc.ca/ocap-training/
- ACECQA child-media model code: https://www.acecqa.gov.au/national-quality-framework/child-safety/national-model-code-taking-images-early-childhood-education-and-care
- UNICEF AI and children guidance: https://www.unicef.org/innocenti/reports/policy-guidance-ai-children

## Round 3, pass Z — adjacent-system capability transfer

### Pedagogy and family-owned learning continuity

- [ ] `PED-001 P1` Co-authored family aspirations/learning goals with educator response, review and visibility.
- [ ] `PED-002 P1` Observation → interpretation → curriculum → experience → implementation → reflection → next-step cycle.
- [ ] `PED-003 P1` Child-interest thread links observations/activities without permanent labeling.
- [ ] `PED-004 P1` Peer pedagogical review/moderation with original, revision and reviewer provenance.
- [ ] `PED-005 P1` Family home observation/language/culture contribution clearly marked family-reported.
- [ ] `PED-006 P1` Wider-family viewing/commenting never implies guardian, custody, billing or consent authority.
- [ ] `PED-007 P1` Guardian-retained child portfolio after withdrawal while provider retains only required records.
- [ ] `PED-008 P1` Selective portfolio transfer to provider/school under guardian disclosure approval.
- [ ] `PED-009 P2` Curriculum coverage/documentation-balance view without child or educator scoring.
- [ ] `PED-010 P2` Pedagogical leadership workspace for themes, coaching, practice changes and reflection.
- [ ] `PED-011 P2` Learning-story narration/child voice with transcript, accessibility and consent.
- [ ] `PED-012 AVOID` No automated development judgment, readiness ranking or invented observation.

### HRIS-grade position and workforce structure

- [ ] `HRX-001 P1` Position separate from employee: FTE, role, location, funding, pay band and qualifications.
- [ ] `HRX-002 P1` Position lifecycle: request, approved, open, frozen, filled, backfilled and eliminated.
- [ ] `HRX-003 P1` Requisition-position-hire linkage prevents duplicate/unbudgeted provisioning.
- [ ] `HRX-004 P1` Effective organization chart with reporting and temporary delegation.
- [ ] `HRX-005 P1` Compensation review/equity/approval/effective date/employee letter cycle.
- [ ] `HRX-006 P1` Employee-relations case boundary separate from coaching, safeguarding and support.
- [ ] `HRX-007 P1` Staff survey with minimum-cohort privacy and anti-retaliation.
- [ ] `HRX-008 P1` Worker-controlled career profile: verified skills, interests, desired hours and opportunities.
- [ ] `HRX-009 P2` Internal talent marketplace for mentorship, coverage, projects and advancement.
- [ ] `HRX-010 P2` Succession/coverage for supervisor, first-aid, cook, driver and administrative authority.
- [ ] `HRX-011 P2` Reconcile positions, hires, schedules, worked hours, funding and labour budget.
- [ ] `HRX-012 P2` Skills-gap plan links verified readiness to training without personality inference.
- [ ] `HRX-013 AVOID` No hidden flight-risk, loyalty, personality, productivity or promotion score.

### ERP-grade provider finance

- [ ] `ERP-001 P1` Vendor master with identity, remittance, tax, duplicate detection and change approval.
- [ ] `ERP-002 P1` Supplier invoice intake/OCR draft/coding/duplicate check/human approval.
- [ ] `ERP-003 P1` Purchase request → order → receipt → invoice three-way match.
- [ ] `ERP-004 P1` Payment proposal, segregation approval, bank/processor export and settlement.
- [ ] `ERP-005 P1` Expense/mileage reimbursement with policy, receipt, approval and payroll/AP handoff.
- [ ] `ERP-006 P1` Corporate-card matching, missing receipt and restricted-category review.
- [ ] `ERP-007 P1` Bank/processor reconciliation for family payments, grants, refunds and vendor disbursements.
- [ ] `ERP-008 P1` Approved budget/forecast by entity, facility, program and room.
- [ ] `ERP-009 P1` Month-end close, subledger reconciliation, lock, adjustment and controller sign-off.
- [ ] `ERP-010 P1` Fixed-asset capitalization, depreciation handoff, impairment, transfer and disposal.
- [ ] `ERP-011 P2` Restricted-fund accounting for grants/donations and eligible use.
- [ ] `ERP-012 P2` Cash forecast from receivables, funding, payroll, tax and vendors.
- [ ] `ERP-013 P2` Unit economics without using profitability to deny an individual child service.
- [ ] `ERP-014 AVOID` Do not build tax filing/general ERP before childcare subledgers and integrations stabilize.

### Field-service-grade work management

- [ ] `WORK-001 P1` Request includes asset/location, safety impact, photo, urgency and reporter.
- [ ] `WORK-002 P1` Triage determines isolation, internal work, contractor, inspection or capital project.
- [ ] `WORK-003 P1` Order tasks, skills, permits, parts, access window and estimated downtime.
- [ ] `WORK-004 P1` Dispatch qualified worker/contractor by schedule, access and equipment.
- [ ] `WORK-005 P1` Contractor accept/reject/expiry and reassignment.
- [ ] `WORK-006 P1` Safety isolation prevents hazardous room/asset/vehicle from appearing available.
- [ ] `WORK-007 P1` Parts reservation, issue, consumption, return and shortage.
- [ ] `WORK-008 P1` Mobile execution with before/after evidence, labour, parts and unexpected findings.
- [ ] `WORK-009 P1` Debrief, requester verification, reopen, warranty and service history.
- [ ] `WORK-010 P1` Preventive work from time, usage, inspection and manufacturer schedule.
- [ ] `WORK-011 P1` Recall locates affected assets/lots, isolates and proves remediation.
- [ ] `WORK-012 P2` Maintenance impact across capacity, ratios, enrolment, meals, transport and closure.
- [ ] `WORK-013 P2` Fix/recurrence analytics improve assets/vendors, not hidden worker ranking.

### EHR-inspired fact provenance and proxy access

- [ ] `PROV-001 P0` Fact provenance: source person/system/document, acquisition, transformation, author, verifier and version.
- [ ] `PROV-002 P0` Epistemic status: observed, child-stated, guardian/staff-reported, imported, calculated, inferred, reviewed, issuer-verified.
- [ ] `PROV-003 P0` Provenance, access audit and workflow history are separate concepts/stores.
- [ ] `PROV-004 P0` Purpose-of-use attached to sensitive access/disclosure and accounting reports.
- [ ] `PROV-005 P0` Proxy authority has source, scope, child, field/purpose, expiry and revocation.
- [ ] `PROV-006 P0` Source conflict preserves each assertion until human resolution.
- [ ] `PROV-007 P0` Security labels propagate through search, exports, notifications, analytics and AI.
- [ ] `PROV-008 P1` Medication authorization, receipt/inventory and administration are distinct linked facts.
- [ ] `PROV-009 P1` Reconciliation view for allergy, medication, contact and pickup changes/conflicts.
- [ ] `PROV-010 P1` Accounting-of-disclosure report for trust centre/privacy review.
- [ ] `PROV-011 P2` UI distinguishes original, extraction, correction and authoritative verification.
- [ ] `PROV-012 AVOID` Never flatten conflicting safety facts into one value without source/time/resolution.

Research transfer sources:

- Storypark capabilities: https://nz.storypark.com/feature/all-features
- Workday workforce planning: https://www.workday.com/en-us/products/human-capital-management/workforce-planning.html/
- UKG workforce management: https://www.ukg.com/products/ukg-pro-workforce-management
- ServiceNow field service: https://www.servicenow.com/products/field-service-management.html
- HL7 FHIR Provenance: https://fhir.hl7.org/fhir/provenance.html
- HL7 FHIR AuditEvent: https://www.hl7.org/fhir/R4/auditevent.html

## Round 3, pass AA — crisis, payments, marketplace and ecosystem depth

### Emergency command and reunification

- [ ] `CRISIS-001 P0` Explicit emergency activation/deactivation with type, severity, scope, initiator and time.
- [ ] `CRISIS-002 P0` Incident-command roles for command, operations, planning, logistics, communications and reunification.
- [ ] `CRISIS-003 P0` Role acceptance/handoff/vacancy; job title alone grants no emergency authority.
- [ ] `CRISIS-004 P0` Situation board separates verified fact, unresolved report, decision, task, resource and briefing.
- [ ] `CRISIS-005 P0` Person status unknown/safe/needs assistance/injured/missing/released with reporter/time/location.
- [ ] `CRISIS-006 P0` Alternate-site activation with capacity, access, route, staff, supplies and communications.
- [ ] `CRISIS-007 P0` Reunification stations: check-in, verification, child assembly, runner/handoff and exception desk.
- [ ] `CRISIS-008 P0` Privacy token prevents public queue from seeing child location/custody restriction.
- [ ] `CRISIS-009 P0` Do-not-release conflicts route to restricted desk without exposing ordinary queue.
- [ ] `CRISIS-010 P0` Responder liaison log for police, fire, EMS, licensing and municipality.
- [ ] `CRISIS-011 P0` Family update cadence, approved wording, delivery, response and rumour correction.
- [ ] `CRISIS-012 P0` Language/access/functional needs throughout evacuation, shelter and reunification.
- [ ] `CRISIS-013 P1` Drill injects degraded communication, missing people, blocked exits and alternate sites.
- [ ] `CRISIS-014 P1` Recovery: support, reopening criteria, preservation, after-action and correction.
- [ ] `CRISIS-015 P1` Independent emergency communication path avoids shared ordinary-app dependencies.
- [ ] `CRISIS-016 P2` Advisory ingestion retains source/confidence and requires human activation.
- [ ] `CRISIS-017 AVOID` No continuous location monitoring disguised as preparedness.

### Payment operations and revenue recovery

- [ ] `PAYMENT-001 P0` Payment mandate authorization, payer, scope, amount terms, revocation and evidence.
- [ ] `PAYMENT-002 P0` Method lifecycle: verification, active, expiring, replaced, failed and revoked.
- [ ] `PAYMENT-003 P0` Processor event/settlement ledger distinct from CareSync invoice/payment intent.
- [ ] `PAYMENT-004 P0` Payout reconciliation for fees, reserves, disputes, refunds, adjustments and negative balances.
- [ ] `PAYMENT-005 P0` Chargeback evidence deadline, package, submission and outcome.
- [ ] `PAYMENT-006 P1` Retry/dunning with quiet periods, preferences and hardship exception.
- [ ] `PAYMENT-007 P1` Family payment portal for method, mandate, autopay, receipt and failure resolution.
- [ ] `PAYMENT-008 P1` Hardship arrangement with authority/installments/missed plan and no stigma.
- [ ] `PAYMENT-009 P1` Cash/cheque batch, dual count, deposit and reconciliation.
- [ ] `PAYMENT-010 P1` Settlement forecast distinguishes invoice paid from funds available.
- [ ] `PAYMENT-011 P1` Processor migration preserves mandate only when portable; otherwise reconsent.
- [ ] `PAYMENT-012 P2` Recovery analytics distinguishes involuntary failure, hardship, dispute and delinquency.
- [ ] `PAYMENT-013 P2` SaaS deferred revenue by service period/modification.
- [ ] `PAYMENT-014 P2` Correctable usage meter for AI/SMS/media before customer invoice.
- [ ] `PAYMENT-015 AVOID` No automatic child service termination or humiliating failed-payment message.

### Marketplace mechanisms beyond moderation

- [ ] `MARKET-016 P0` Every verification badge defines check, actor, source, date and limits.
- [ ] `MARKET-017 P0` Background/reference consent, provider, status, expiry and minimized result.
- [ ] `MARKET-018 P0` Material adverse outcome has human review, notice and correction path.
- [ ] `MARKET-019 P1` Substitute contract, rate, cancellation, timesheet, dispute, invoice and payment.
- [ ] `MARKET-020 P1` Optional candidate interview safety check-in/trusted contact with narrow purpose.
- [ ] `MARKET-021 P1` Review eligibility requires verified engagement/application milestone and appeal.
- [ ] `MARKET-022 P1` Double-blind review publication window reduces retaliation.
- [ ] `MARKET-023 P1` Employer verification does not imply every interviewer/supervisor was vetted.
- [ ] `MARKET-024 P1` Fraud-ring investigation from account/payment/job behavior, never protected-trait inference.
- [ ] `MARKET-025 P1` Tax/invoice records for paid substitute work without deciding classification.
- [ ] `MARKET-026 P2` Availability commitment/expiry prevents stale matching.
- [ ] `MARKET-027 P2` Match feedback identifies requirement error rather than popularity.
- [ ] `MARKET-028 AVOID` No public star rating of educators, children, families or sensitive disputes.

### Ecosystem and trusted exchange

- [ ] `ECO-001 P1` Guardian-initiated provider transition with selective disclosure and receipt.
- [ ] `ECO-002 P1` Verified school/OSC contact, route, bell calendar and handoff directory.
- [ ] `ECO-003 P1` Specialist directory with credential source, area, referral requirements and review date.
- [ ] `ECO-004 P1` Approved supplier catalogue for food, safety, training, equipment and maintenance with tenant choice.
- [ ] `ECO-005 P1` Integration certification covering security, privacy, reconciliation, contract and support.
- [ ] `ECO-006 P1` Shared connector health: scope, last success, lag, error and affected workflow.
- [ ] `ECO-007 P2` College/ECE issuer integration for trusted credentials and status—not scraping.
- [ ] `ECO-008 P2` Tenant-controlled insurer/loss-control evidence exchange.
- [ ] `ECO-009 P2` Scoped accountant/payroll implementation partner network.
- [ ] `ECO-010 P2` Signed community rule contributions require authoritative review before activation.
- [ ] `ECO-011 P3` Family-consented inter-provider capacity referral without shared identifiable waitlist.
- [ ] `ECO-012 AVOID` No integration partner gets broad silent access by marketplace listing.

Sources:

- FEMA emergency operations/reunification guide: https://www.fema.gov/sites/default/files/2020-07/guide-developing-school-emergency-operations-plans.pdf
- Stripe customer management: https://docs.stripe.com/customer-management
- Stripe revenue recovery: https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Airbnb verification limitations: https://www.airbnb.com/help/article/450/what-is-verified-id

## Round 3, pass AB — architecture fault isolation and formal assurance

- [ ] `ARCH-021 P0` SaaS control plane is separated from childcare data plane; billing outage cannot break safety work.
- [ ] `ARCH-022 P0` Safety continuity plane serves minimal roster, release, allergy/medication and emergency facts independently.
- [ ] `ARCH-023 P0` Safety-plane sync has freshness, signature, revocation, expiry and reconciliation.
- [ ] `ARCH-024 P0` Emergency notification has independent provider/manual fallback.
- [ ] `ARCH-025 P0` Critical/offline paths enforce signed local policy bundles; remote authorization is not sole dependency.
- [ ] `ARCH-026 P0` Continuous access-change signal propagates suspension, custody/device/tenant revocation everywhere.
- [ ] `ARCH-027 P0` Every action declares fail-closed, cached-until-expiry, break-glass or manual fallback behavior.
- [ ] `ARCH-028 P0` No general superadmin; control-plane support authority and tenant-data access are separate.
- [ ] `ARCH-029 P0` Provenance model/store remains distinct from access audit and domain history.
- [ ] `ARCH-030 P0` Consumers receive purpose-specific minimized events, never universal child objects.
- [ ] `ARCH-031 P0` Security/purpose labels survive event transformations.
- [ ] `ARCH-032 P0` Critical event-completeness monitor compares expected producer/consumer acknowledgement.
- [ ] `ARCH-033 P1` Rebuildable projection reports source cursor, schema version and reconciliation.
- [ ] `ARCH-034 P2` Cell/deployment-stamp plan includes tenant placement, routing, rings and capacity.
- [ ] `ARCH-035 P2` Tenant migration between cells uses dual verification, cutover, rollback and audit.
- [ ] `ARCH-036 P2` Fault-isolation budget limits tenants affected by code, DB, queue, provider or deployment failure.
- [ ] `ARCH-037 P2` Dedicated isolation tier uses the same automated artifact, not manual fork.
- [ ] `ARCH-038 P2` Global control plane retains only routing/entitlement metadata, not complete child data.
- [ ] `ARCH-039 P0` Small safety kernel owns release, shift guard, medication rights, ratio/capacity and tenant invariants.
- [ ] `ARCH-040 P0` Property/model tests explore transitions, retry, concurrency and offline replay.
- [ ] `ARCH-041 P1` Machine-checkable invariants generate runtime sentinels and test oracles.
- [ ] `ARCH-042 P1` Rule sandbox is deterministic, bounded, signed and has no arbitrary network/code execution.
- [ ] `ARCH-043 P1` New rules/optimizers run shadow-mode before mutation authority.
- [ ] `ARCH-044 P1` Disaster drill separately proves control-plane loss, data-plane degradation and safety-plane continuity.

## Round 3, pass AC — standards conformance and product assurance

- [ ] `STD-001 P0` Versioned OWASP ASVS 5.0 control mapping with test/evidence for applicable requirements.
- [ ] `STD-002 P0` OWASP API/MASVS-aligned threat/control matrix for web, API, mobile and offline data.
- [ ] `STD-003 P0` NIST CSF 2.0 profile across Govern, Identify, Protect, Detect, Respond and Recover.
- [ ] `STD-004 P0` NIST SSDF practice/evidence integrated into engineering workflow.
- [ ] `STD-005 P0` Software supply-chain inventory, SBOM, provenance, signing and dependency response.
- [ ] `STD-006 P0` OAuth clients follow RFC 9700: authorization code/PKCE, exact redirects, rotation/replay defense and no implicit/password grant.
- [ ] `STD-007 P1` High-security partner APIs evaluate FAPI 2.0 sender-constrained/profile controls.
- [ ] `STD-008 P1` CloudEvents-compatible envelope considered for portable event metadata while domain schema stays CareSync-owned.
- [ ] `STD-009 P0` OpenTelemetry semantic conventions plus CareSync privacy-safe attribute allowlist.
- [ ] `STD-010 P0` Payment scope/attestation reviewed under current PCI DSS; tokenization does not eliminate all merchant responsibility.
- [ ] `STD-011 P1` Accessibility conformance covers WCAG 2.2 AA plus applicable mobile/software/document procurement criteria.
- [ ] `STD-012 P1` Accessibility conformance report cites tested versions/components and known defects.
- [ ] `STD-013 P1` NIST AI RMF Govern/Map/Measure/Manage evidence for every AI feature.
- [ ] `STD-014 P1` AI TEVV includes predeployment, ongoing, incident, bias, adversarial and retirement evidence.
- [ ] `STD-015 P1` Security controls have implementation, operation and effectiveness evidence—not policy alone.
- [ ] `STD-016 P2` SOC 2/ISO roadmaps reuse control evidence but never replace product/legal assurance.
- [ ] `STD-017 P2` Standard/source version updates open impact work instead of silently changing a badge.
- [ ] `STD-018 P2` Customer-facing conformance claims state scope, period, assessor and exclusions.

## Round 3, pass AD — AI lifecycle depth

- [ ] `AI-025 P0` AI use-case intake defines affected people, benefit, non-AI baseline, consequence and appeal.
- [ ] `AI-026 P0` Dataset register covers source, licence/authority, population, exclusions, quality and prohibited reuse.
- [ ] `AI-027 P0` Model card plus system card distinguish base model capability from CareSync workflow behavior.
- [ ] `AI-028 P0` Evaluation plan has field/segment thresholds, abstention, human baseline and failure severity.
- [ ] `AI-029 P0` Golden/adversarial sets are versioned, access controlled and separated from training.
- [ ] `AI-030 P0` Deployment decision records residual risk, accountable approver, rollback and monitoring.
- [ ] `AI-031 P0` Model/provider change is a production change with regression, privacy and contract review.
- [ ] `AI-032 P0` AI incident triage covers hallucination, bias, leakage, unsafe automation, prompt injection and provider compromise.
- [ ] `AI-033 P0` Child-impact assessment applies even where the child never directly uses the AI.
- [ ] `AI-034 P1` Output provenance retains model/version, prompt template, retrieved sources, tools and policy filters.
- [ ] `AI-035 P1` Cost/latency/provider failure never bypasses required human/safety control.
- [ ] `AI-036 P1` User correction feeds an evaluation queue, not automatic retraining.
- [ ] `AI-037 P1` Explainability is tested with intended users for comprehension, not merely emitted text.
- [ ] `AI-038 P1` Periodic drift review includes document formats, language, population and workflow changes.
- [ ] `AI-039 P2` AI retirement plan preserves reproducibility of historical decisions and removes provider data.
- [ ] `AI-040 AVOID` No child-facing AI companion, relational persona or persuasive chatbot in the operational product.

Standards sources:

- OWASP ASVS 5.0: https://owasp.org/www-project-application-security-verification-standard/
- NIST CSF 2.0: https://www.nist.gov/cyberframework
- NIST supply-chain guide: https://csrc.nist.gov/pubs/sp/1305/final
- OAuth security BCP RFC 9700: https://www.rfc-editor.org/info/rfc9700/
- FAPI 2.0: https://openid.net/specs/fapi-security-profile-2_0.html
- CloudEvents: https://cloudevents.io/
- OpenTelemetry semantics: https://opentelemetry.io/docs/specs/semconv/general/
- NIST AI RMF: https://www.nist.gov/itl/ai-risk-management-framework
- Accessibility ICT standard: https://accessible.canada.ca/standards-and-technical-guides/standards-and-technical-guides-database/can-asc-en-301-5492024-accessibility-requirements-ict-products-and-services-en-301-5492021-idt

## Round 3, pass AE — additional frontier concepts and prohibitions

- [ ] `NOVEL-039 P2` Care-record epistemology visibly distinguishes observed, reported, imported, calculated, inferred and verified.
- [ ] `NOVEL-040 P2` Temporal truth lens reconstructs what applied and what CareSync knew then, including later correction.
- [ ] `NOVEL-041 P2` Safety-kernel certificate proves minimal invariants passed for release, medication and capacity.
- [ ] `NOVEL-042 P2` Trust receipt shows data used, change, approval and correction route after sensitive operation.
- [ ] `NOVEL-043 P2` Pedagogical continuity thread transfers selected aspirations/evidence without whole record.
- [ ] `NOVEL-044 P2` Care-plan compiler turns approved plan into contextual tasks without generating clinical facts.
- [ ] `NOVEL-045 P2` Reunification privacy token coordinates handoff without exposing assembly location/restriction.
- [ ] `NOVEL-046 P2` Operational twin shadow mode measures optimizer disagreement before authority.
- [ ] `NOVEL-047 P2` Evidence topology reveals many controls depending on one fragile source/person/integration.
- [ ] `NOVEL-048 P2` Decision consistency review surfaces unexplained variation without forcing unlike cases equal.
- [ ] `NOVEL-049 P3` Facility edge node provides encrypted, revocable, reconcilable emergency safety replica.
- [ ] `NOVEL-050 P3` Synthetic childcare conformance suites for ratios, custody, funding, credentials and attendance.
- [ ] `NOVEL-051 P3` Selective-disclosure shared-control credential proves a property without broad document release.
- [ ] `NOVEL-052 FUTURE` Pre-governed community resilience fabric across providers/responders/families.
- [ ] `NOVEL-053 AVOID` No immutable public ledger containing identifiable child/family/worker/custody/incident facts.

### Explicit anti-features discovered in round 3

- [ ] `ANTI-001 AVOID` No unlimited-forever child media promise; purpose, consent, retention and cost still govern.
- [ ] `ANTI-002 AVOID` No recording streaks/badges that pressure educators to document instead of care.
- [ ] `ANTI-003 AVOID` No parent group chat exposing phone, custody or child affiliation by default.
- [ ] `ANTI-004 AVOID` No AI polishing that silently changes child words, incident observation or authorship.
- [ ] `ANTI-005 AVOID` No public facility score built from incomparable or weakly sourced metrics.
- [ ] `ANTI-006 AVOID` No service denial, discipline or exclusion from anomaly detection alone.
- [ ] `ANTI-007 AVOID` No single notification provider presented as emergency readiness.
- [ ] `ANTI-008 AVOID` No ordinary SaaS entitlement call on current emergency-information path.
- [ ] `ANTI-009 AVOID` No advertising profiles from family payments, candidate behavior or staff schedules.
- [ ] `ANTI-010 AVOID` “Verified” never means safe, suitable or currently authorized without stated scope.
- [ ] `ANTI-011 AVOID` No home-grown payroll tax filing or medical engine just to claim all-in-one.
- [ ] `ANTI-012 AVOID` No raw child-record data lake reserved for hypothetical future AI.
- [ ] `ANTI-013 AVOID` No broad event topic carrying complete child/family objects.
- [ ] `ANTI-014 AVOID` No benchmark where small cohorts permit reidentification.
- [ ] `ANTI-015 AVOID` No edge/offline cache without expiry, remote revocation and controlled destruction.

### Commercial refinements

- [ ] `GTM-019 P1` Separate SaaS, processing, marketplace and services revenue in contracts/accounting.
- [ ] `GTM-020 P1` Revenue recognition for prepaid subscriptions and implementation service periods.
- [ ] `GTM-021 P1` Involuntary churn recovery differs from deliberate cancellation and preserves safety access.
- [ ] `GTM-022 P1` Subscription/payment self-service with governed effective dates.
- [ ] `GTM-023 P1` Downgrade compatibility keeps exported records readable and safety history available.
- [ ] `GTM-024 P2` Pricing experiments only on new offers, never silent active safety entitlements.
- [ ] `GTM-025 P2` Marketplace launch gate includes verification, density, response, support, disputes and legal readiness.
- [ ] `GTM-026 P2` Integration partner model defines certification, support, revenue and exit portability.
- [ ] `GTM-027 P2` Migration guarantee states source quality, reconciliation acceptance and customer duties.
- [ ] `GTM-028 P2` Residency/isolation premium funds real stamp/key/operations cost.
- [ ] `GTM-029 P2` Gross-margin controls optional AI/media/SMS without rationing safety/accessibility.
- [ ] `GTM-030 AVOID` Never monetize candidate data, child/family insights, regulator evidence or emergency access.

# Fourth-generation adversarial expansion — 2026-07-16

This cycle does not treat a long feature count as proof of completeness. It reopens the product at the boundaries where childcare, privacy, facilities, finance, evidence, employment and public authorities meet. A proposed control should carry an authority classification before implementation:

- `LAW/REGULATION`: directly traceable to an applicable enacted rule, with jurisdiction, section, effective date and legal review.
- `LICENCE/PERMIT`: imposed by the facility's actual licence, permit, approval, occupancy classification or authority having jurisdiction.
- `AGREEMENT`: imposed by a funding, insurance, processor, landlord, customer or other contract; it must not be presented as universal law.
- `GUIDANCE`: authoritative or professional guidance that informs reasonable practice but is not itself legislation.
- `PRODUCT STANDARD`: CareSync's chosen safety, accessibility, reliability or trust bar; describe it honestly as a product commitment.
- `FUTURE/HYPOTHESIS`: a design candidate that requires operator discovery, evidence and governance before build.

Where these layers conflict, CareSync must not silently choose one. It must identify the source, surface the conflict and route an accountable decision.

## Round 4, pass AF — premises security, access control and surveillance

- [ ] `PHYS-001 P0` Facility security profile separates life safety, child-release safety, property protection, privacy and business continuity objectives.
- [ ] `PHYS-002 P0` Door/zone register identifies public, family, staff-only, child-care, medication, records, kitchen, utility and restricted areas.
- [ ] `PHYS-003 P0` Physical credential lifecycle covers issuance, identity proofing, zone/time scope, activation, loss, replacement, suspension, return and destruction.
- [ ] `PHYS-004 P0` Key, fob, badge, PIN and mobile credential inventory has accountable custodian and periodic reconciliation.
- [ ] `PHYS-005 P0` Staff termination, suspension, role change and lost-device events revoke physical and digital access together.
- [ ] `PHYS-006 P0` Emergency egress and responder access can never be defeated by ordinary access-control policy.
- [ ] `PHYS-007 P0` Door-held-open, forced-entry, repeated-denial and controller-offline events have severity, response and evidence rules.
- [ ] `PHYS-008 P0` Visitor/contractor workflow records sponsor, purpose, permitted zones, arrival, badge, supervision requirement and departure without becoming a child attendance system.
- [ ] `PHYS-009 P0` Pickup authorization remains a family/custody decision; possession of a building credential never authorizes child release.
- [ ] `PHYS-010 P0` Video-surveillance assessment documents the specific reasonable purpose, less-intrusive alternatives, affected people, camera field and approval before activation.
- [ ] `PHYS-011 P0` Camera map excludes spaces with a high expectation of privacy and minimizes capture of neighbouring property, screens, documents and audio.
- [ ] `PHYS-012 P0` Audio recording, biometric identification, emotion inference and facial recognition are separately prohibited unless a new lawful, necessary and independently reviewed case is established.
- [ ] `PHYS-013 P0` Surveillance notice identifies purpose, accountable contact and access-request route; hidden signage or generic “security” language is insufficient.
- [ ] `PHYS-014 P0` Footage access is case-bound, least-privilege, time-limited and logged with viewer, purpose, search window, clips and disclosures.
- [ ] `PHYS-015 P0` Routine footage auto-expires under a documented schedule; incident clips are preserved through an explicit evidence/legal-hold action.
- [ ] `PHYS-016 P0` Footage export supports redaction, integrity verification, chain of custody, secure transfer and disclosure accounting.
- [ ] `PHYS-017 P0` Camera/vendor health monitoring detects blind cameras, time drift, storage failure, unauthorized configuration and exposed remote access.
- [ ] `PHYS-018 P1` Security inspection tests doors, alarms, panic/duress devices, lighting, sight lines, visitor controls, camera coverage and manual fallback.
- [ ] `PHYS-019 P1` Shared-building responsibility matrix assigns landlord, operator and vendor duties for keys, cameras, alarms, common areas, incidents and evidence.
- [ ] `PHYS-020 AVOID` No parent-facing continuous live classroom webcam, staff surveillance score or casual footage browsing as an engagement feature.

Authority note: Alberta OIPC guidance treats even unrecorded identifiable video as personal-information collection, recommends testing less-invasive alternatives, limiting viewing range, giving notice, restricting access and destroying recordings when no longer required. These controls are a mixture of PIPA-informed privacy obligations and CareSync product safety standards—not a claim that one statute prescribes every camera configuration.

## Round 4, pass AG — inclusive care as an operational lifecycle

- [ ] `INCL-001 P0` Inclusion intake begins with the child's strengths, participation barriers, family priorities and requested supports—not a diagnostic label.
- [ ] `INCL-002 P0` Record who requested support, the authority/consent for specialist involvement, permissible information sharing and withdrawal effects.
- [ ] `INCL-003 P0` Functional support needs are separated from clinical documents and exposed only to roles that need them for safe care.
- [ ] `INCL-004 P0` Individual inclusion plan links goals, observable strategies, environment changes, communication supports, responsible people and review date.
- [ ] `INCL-005 P0` Child/family voice and assent-appropriate preferences are recorded without making a child responsible for the accommodation decision.
- [ ] `INCL-006 P0` Safety-critical accommodations propagate to attendance, room placement, transport, meals, medication, emergency and off-site workflows.
- [ ] `INCL-007 P0` Admission, waitlist, withdrawal and exclusion decisions require reason, alternatives considered, accommodation analysis, approver and review/complaint route.
- [ ] `INCL-008 P0` Capacity/ratio constraints are documented as constraints to solve, not an automatic denial based on disability or support need.
- [ ] `INCL-009 P0` Behaviour-support records distinguish observation, trigger/context, strategy, outcome and family/specialist report; they do not label the child.
- [ ] `INCL-010 P0` Restrictive, humiliating, punitive, exclusionary or unapproved intervention patterns trigger safeguarding review.
- [ ] `INCL-011 P1` Alberta Inclusive Child Care intake workspace tracks application, agency, consultation, short-term support window, milestones, funding and closeout.
- [ ] `INCL-012 P1` Consultant access is scoped to named children/program evidence, expires automatically and never creates standing tenant access.
- [ ] `INCL-013 P1` Educator coaching/training plan connects strategies to shift/room readiness without exposing unnecessary child details.
- [ ] `INCL-014 P1` Additional-support staffing records funding source, approved purpose, hours, staff, actual delivery, variance and evidence.
- [ ] `INCL-015 P1` Assistive/adaptive equipment record covers ownership, fit, instruction, cleaning, maintenance, availability, failure and return.
- [ ] `INCL-016 P1` Communication passport supports language, AAC, sensory and transition preferences with family-controlled portability.
- [ ] `INCL-017 P1` Inclusion review measures participation, belonging, access and plan usefulness—not compliance by the child.
- [ ] `INCL-018 P1` Transition/closure plan preserves sustainable educator capability when time-limited external support ends.
- [ ] `INCL-019 P2` Barrier register aggregates environmental/process barriers with small-cohort privacy protection and tracks remediation.
- [ ] `INCL-020 AVOID` No disability-risk score, predicted “burden,” automated exclusion recommendation or ranking of children by cost/complexity.

Authority note: Alberta's current Inclusive Child Care Program describes consultation, training and short-term intensive supports for up to six months. Human-rights duties and the terms of a particular support agreement are separate sources and must remain separate rule/evidence layers.

## Round 4, pass AH — capital expansion, renovation and grant delivery

- [ ] `CAPEX-001 P0` Project charter identifies legal entity, site, lease/ownership authority, licensed programs, proposed spaces, accessibility outcome and accountable sponsor.
- [ ] `CAPEX-002 P0` Eligibility snapshot captures the program guide, intake window, entity/program type, geography, funding cap and evidence used at the time.
- [ ] `CAPEX-003 P0` Grant availability is effective-dated; a closed historical intake can inform a template but must never be offered as currently open.
- [ ] `CAPEX-004 P0` Funding sources and eligible-cost rules prevent double funding and unsupported cost allocation.
- [ ] `CAPEX-005 P0` Concept gate reconciles demand, operating sustainability, staffing, ratios, licence path, zoning, building/fire/public-health requirements and insurer/landlord approval.
- [ ] `CAPEX-006 P0` Design requirements trace each licensed, accessible, safety and funder commitment to drawings/specifications and an owner.
- [ ] `CAPEX-007 P0` Permit/approval register has authority, submission version, conditions, expiry, inspection and closure evidence.
- [ ] `CAPEX-008 P0` Construction cannot make a room/site available until occupancy, fire/building, public-health, licensing and operator commissioning gates applicable to that project pass.
- [ ] `CAPEX-009 P0` Work-in-occupied-facility plan controls separation, dust/noise, hazardous materials, exits, deliveries, contractor access and child/staff exposure.
- [ ] `CAPEX-010 P1` Procurement records solicitation/quote, conflict declaration, evaluation, approval, contract, insurance and change orders.
- [ ] `CAPEX-011 P1` Budget ledger distinguishes committed, invoiced, paid, eligible, claimed, reimbursed, retained and forecast cost.
- [ ] `CAPEX-012 P1` Scope/schedule/budget variance requires impact analysis and approval under both internal authority and funding agreement.
- [ ] `CAPEX-013 P1` Grant instalment/draw workflow links milestone, evidence package, submission, questions, receipt, payment and reconciliation.
- [ ] `CAPEX-014 P1` Commissioning covers systems, accessibility features, equipment, training, warranties, deficiencies, spares and operations handoff.
- [ ] `CAPEX-015 P1` Final report proves delivered scope, costs, procurement, outcomes, photos where appropriate, asset location and unresolved obligations.
- [ ] `CAPEX-016 P1` Post-project obligations track asset retention/use, reporting, audit, signage/recognition, insurance and repayment exposure.
- [ ] `CAPEX-017 P2` Benefits realization compares funded spaces/accessibility outcomes with actual licensed and occupied use without pressuring unsafe enrolment.
- [ ] `CAPEX-018 AVOID` No automated grant eligibility promise, permit approval prediction or spend recommendation based only on an old program guide.

Current-context note: Alberta lists Inclusive Spaces, Building Blocks and Space Creation as programs whose intakes are closed or historical as of this research date. The reusable product is the governed project/agreement engine; funding rules must remain versioned program packs.

## Round 4, pass AI — distinct program and service models

- [ ] `PROGRAM-001 P0` Program type is a legal/operational rule context, not a cosmetic label on a room.
- [ ] `PROGRAM-002 P0` Daycare, preschool, out-of-school care, family day home agency/home and legacy group family childcare remain distinct models.
- [ ] `PROGRAM-003 P0` One facility may hold multiple program contexts; enrolment, attendance, staff qualification, ratios, funding and reporting resolve against the correct one.
- [ ] `PROGRAM-004 P0` Program licence/approval stores authority, identifier, conditions, approved ages, capacity, hours, overnight/extended authorization and effective history.
- [ ] `PROGRAM-005 P0` Mixed-use rooms require a time-bounded allocation to a program; CareSync never assumes one room has one rule all day.
- [ ] `PROGRAM-006 P0` Daycare duration semantics, preschool duration semantics and OSC school-day/non-school-day semantics are separately validated from an effective rule pack.
- [ ] `PROGRAM-007 P0` OSC calendar connects each child's school, grade, bell times, transportation/handoff, PD days, closures and breaks.
- [ ] `PROGRAM-008 P0` Kindergarten daytime care and before/after-school care are not inferred from age alone.
- [ ] `PROGRAM-009 P0` Extended-hours/overnight care requires actual licensing approval, staffing/rest/sleep plan, emergency readiness and applicable building/fire classification.
- [ ] `PROGRAM-010 P0` Consecutive-care guard evaluates continuous time across midnight, transfers and linked bookings; a date change does not reset it.
- [ ] `PROGRAM-011 P0` Overnight sleep/wake checks, bedding, supervision, privacy, medication and emergency evacuation become explicit operational workflows.
- [ ] `PROGRAM-012 P1` Drop-in/casual care is an enrolment/booking modality only where compatible with the licensed program, capacity, records and funding rules.
- [ ] `PROGRAM-013 P1` Seasonal/summer service uses an effective calendar and enrolment term; it does not create an invented licence category.
- [ ] `PROGRAM-014 P1` Split-day and alternating preschool sessions support session rosters, turnaround, cleaning and under-four-hour validation where applicable.
- [ ] `PROGRAM-015 P1` School closure converts affected OSC children to a reviewed non-school-day care plan instead of copying ordinary bell-time attendance.
- [ ] `PROGRAM-016 P1` Program conversion, addition, suspension and closure have licence/funding/family/staff/data migration gates.
- [ ] `PROGRAM-017 P2` Demand/capacity scenarios compare program mixes while preserving room, staffing, funding and permit constraints.
- [ ] `PROGRAM-018 AVOID` No generic “custom program” switch that bypasses Alberta program definitions or silently inherits daycare rules.

Research note: Alberta currently describes daycare as care for kindergarten age and younger for four or more consecutive hours, preschool as care from 19 months to kindergarten age for less than four hours per child, and OSC as school-linked care for kindergarten through age 12 with limited special-needs extension. Those descriptions must be verified against the current regulation/licence before becoming executable rules.

## Round 4, pass AJ — Canadian tax receipts and financial record evidence

- [ ] `TAXREC-001 P0` Tax receipt is a distinct issued document derived from settled/recognized payment facts; an invoice, statement or processor authorization is not a receipt.
- [ ] `TAXREC-002 P0` Receipt identifies the payer/recipient, child, service period, amount actually received, provider legal identity/address and issue/signature evidence required for that provider type.
- [ ] `TAXREC-003 P0` Issue separate child-level receipt evidence where required even when one household paid a combined invoice.
- [ ] `TAXREC-004 P0` Provider-identity rule distinguishes organization from individual provider; an individual's SIN is highly restricted and never placed in general tenant exports or logs.
- [ ] `TAXREC-005 P0` Payer split, refund, credit, chargeback, subsidy/grant and third-party payment are reconciled before receiptable family amount is certified.
- [ ] `TAXREC-006 P0` Corrected/cancelled/reissued receipt preserves original identifier, reason, actor, approval, replacement link and delivery history.
- [ ] `TAXREC-007 P0` Duplicate download is visibly the same receipt/version, not a newly issued financial fact.
- [ ] `TAXREC-008 P0` Year-end lock prevents silent mutation while allowing governed late adjustments and reissuance.
- [ ] `TAXREC-009 P0` Electronic financial records remain readable/exportable with source transactions, audit trail and business-system documentation for the applicable retention period.
- [ ] `TAXREC-010 P0` Retention rule is effective-dated by record/entity type; the general CRA six-year rule is not used to shorten longer childcare, legal-hold or agreement requirements.
- [ ] `TAXREC-011 P1` Family portal offers annual package, child/payer breakdown, correction request and delivery status.
- [ ] `TAXREC-012 P1` Operator reconciliation proves totals across receipts, family ledger, bank/processor settlements and general ledger.
- [ ] `TAXREC-013 P1` CRA/auditor export is scoped, reproducible and accompanied by schema/system documentation without exposing unrelated child records.
- [ ] `TAXREC-014 AVOID` CareSync does not determine whether a family's expense is deductible, choose the claimant or provide personalized tax advice.

## Round 4, pass AK — legal demand, preservation and disclosure operations

- [ ] `LEGAL-001 P0` Central intake for subpoena, warrant, court/tribunal order, law-enforcement request, regulator demand, litigation notice and emergency request.
- [ ] `LEGAL-002 P0` Request record captures issuer identity, jurisdiction, authority cited, service method/time, scope, deadline, secrecy term and authenticity verification.
- [ ] `LEGAL-003 P0` Trained privacy/legal reviewer determines whether disclosure is required, permitted, prohibited or needs clarification; frontline staff cannot improvise.
- [ ] `LEGAL-004 P0` Preservation notice immediately protects potentially responsive records without granting the requester access.
- [ ] `LEGAL-005 P0` Legal hold defines custodians, systems, date range, data classes, preservation method, acknowledgement, refresh and release authority.
- [ ] `LEGAL-006 P0` Collection is reproducible and preserves native content, metadata, relationships, versions, deleted-state evidence and integrity checks where applicable.
- [ ] `LEGAL-007 P0` Review workspace separates responsive, non-responsive, privileged, restricted, duplicate and redaction-required material.
- [ ] `LEGAL-008 P0` Production is minimized to lawful scope; third-party child/family/staff information is redacted or withheld when not authorized.
- [ ] `LEGAL-009 P0` Disclosure approval records legal basis, reviewer, exact production set, exceptions, delivery method and recipient receipt.
- [ ] `LEGAL-010 P0` Secure production package has manifest, sequence identifiers, integrity hashes, encryption and separate key exchange.
- [ ] `LEGAL-011 P0` Non-disclosure/secrecy terms suppress ordinary subject notification only when validly applicable and expire/review on schedule.
- [ ] `LEGAL-012 P0` Emergency life/health/safety disclosure records circumstances, necessity, recipient, fields disclosed, follow-up and retrospective review.
- [ ] `LEGAL-013 P0` Disclosure accounting feeds privacy access reports where lawful without revealing protected investigations.
- [ ] `LEGAL-014 P1` Deadline workflow supports clarification, objection, narrowing, extension, counsel instruction and completion evidence.
- [ ] `LEGAL-015 P1` Hold conflict prevents ordinary retention deletion, tenant purge, key destruction and backup expiry for preserved material.
- [ ] `LEGAL-016 P1` Hold release resumes normal retention prospectively and records what remained preserved and why.
- [ ] `LEGAL-017 P2` Aggregate transparency reporting counts request types and outcomes only where lawful and non-identifying.
- [ ] `LEGAL-018 AVOID` No bulk “police portal,” silent voluntary disclosure, keyword dragnet or automated legal-conclusion engine.

Authority note: Alberta PIPA permits particular disclosures without consent, including compliance with a qualifying subpoena, warrant or order and assistance to a Canadian law-enforcement investigation. Permission is not a command to disclose everything requested; the product must preserve verification, reasonableness, minimization and accountable human review.

## Round 4, pass AL — voice, interpretation and channel continuity

- [ ] `VOICE-001 P0` Communication case has purpose, participants, child/family context, urgency, confidentiality level, owner and next action independent of channel.
- [ ] `VOICE-002 P0` Inbound caller verification is proportionate to action; caller ID alone never authorizes pickup, record change or disclosure.
- [ ] `VOICE-003 P0` Staff use an approved callback path for high-risk requests and record the verified directory source.
- [ ] `VOICE-004 P0` Call recording/transcription is off by default and requires separately reviewed notice, authority, purpose, access and retention.
- [ ] `VOICE-005 P0` Interpreter workflow records language, accessibility needs, interpreter identity/provider, confidentiality and whether interpretation—not consent—was provided.
- [ ] `VOICE-006 P0` A child or unauthorized family member is never used as interpreter for a safety, consent, custody, health or legal conversation.
- [ ] `VOICE-007 P0` Emergency communication has multi-provider/manual fallback, paper/contact export and delivery reconciliation.
- [ ] `VOICE-008 P1` Channel preference, quiet hours, emergency override, language and accessibility format are effective-dated per relationship/person.
- [ ] `VOICE-009 P1` Failed email/SMS/push/voice delivery opens a fallback task according to message severity instead of merely logging a bounce.
- [ ] `VOICE-010 P1` Shared family threads visibly show participants and prevent accidental disclosure across separated households.
- [ ] `VOICE-011 P1` Approved templates are versioned by purpose/language, but staff can add truthful context without AI rewriting facts.
- [ ] `VOICE-012 P1` Conversation summary identifies author/source and links to originals; it is not silently merged into the child's authoritative record.
- [ ] `VOICE-013 P1` Abuse, harassment, threats and repeated-contact controls preserve urgent access while protecting workers and families.
- [ ] `VOICE-014 P1` Number/domain reputation, SPF/DKIM/DMARC and anti-spoofing monitoring protect trusted outbound identity.
- [ ] `VOICE-015 P2` Human-reviewed translation glossary protects names, medication terms, custody language and emergency instructions.
- [ ] `VOICE-016 AVOID` No cloned educator/parent/child voice, deceptive AI caller, emotion detection or automated negotiation in sensitive care conversations.

## Round 4, pass AM — research and data partnerships

- [ ] `RESEARCH-001 P0` Research intake states question, public/participant benefit, affected population, necessity, sponsor, methods, outputs and accountable investigator.
- [ ] `RESEARCH-002 P0` Classify activity as operations, quality improvement, product analytics, research or model development; labels cannot be chosen to evade governance.
- [ ] `RESEARCH-003 P0` Authority/consent assessment covers every data source, linkage, secondary use, child impact and withdrawal limitation.
- [ ] `RESEARCH-004 P0` Child-impact, privacy, security, equity and Indigenous/community-governance review occurs before data access.
- [ ] `RESEARCH-005 P0` Data-management plan specifies fields, provenance, transformations, access, location, retention, publication and destruction.
- [ ] `RESEARCH-006 P0` De-identification risk is tested against small cohorts, rare events, dates, geography, linkage and recipient knowledge; removing names is insufficient.
- [ ] `RESEARCH-007 P0` Secure analysis environment supports approved code, query/output review, no raw download, monitoring and expiry for high-risk data.
- [ ] `RESEARCH-008 P0` Data-sharing agreement covers purpose, roles, onward use, security, incidents, audit, publication, IP, commercialization, return/destruction and termination.
- [ ] `RESEARCH-009 P0` Research access is project-scoped, named, time-limited and technically separated from support/production administration.
- [ ] `RESEARCH-010 P0` Data/model lineage allows every result to be traced to approved snapshots and transformations.
- [ ] `RESEARCH-011 P0` Output disclosure control blocks identifiable rows, small cells, memorized text/images and prohibited subgroup inference.
- [ ] `RESEARCH-012 P0` Participant/community correction, complaint and harm-response route survives project closure.
- [ ] `RESEARCH-013 P1` Publication review checks accuracy, reidentification, stigmatizing framing, commitments and acknowledgement without suppressing valid adverse findings.
- [ ] `RESEARCH-014 P1` Reproducibility package preserves code, metadata, environment and non-identifying evidence without retaining unauthorized personal data.
- [ ] `RESEARCH-015 P1` Project closeout verifies deliverables, access revocation, data return/destruction, residual copies and future-use decision.
- [ ] `RESEARCH-016 P2` Privacy-preserving multi-tenant benchmarking requires minimum cohorts, tenant opt-in, purpose limits and contestable methodology.
- [ ] `RESEARCH-017 P2` Synthetic data is evaluated for fidelity, leakage and harmful representation and is never advertised as risk-free.
- [ ] `RESEARCH-018 AVOID` No raw child record lake, broad university/partner feed, silent model training or “anonymous” dataset release without a defensible risk assessment.

### Round 4 source additions for passes AF–AM

- Alberta OIPC video surveillance in the private sector: https://oipc.ab.ca/resource/video-surveillance/
- Alberta PIPA disclosure grounds: https://www.alberta.ca/disclosing-personal-information
- Alberta program types: https://www.alberta.ca/understand-albertas-childcare-system-for-programs-and-providers
- Alberta licensed facility-based programs: https://www.alberta.ca/licensed-facility-based-programs
- Alberta Affordability Grant and extended/overnight context: https://www.alberta.ca/affordability-grant
- Alberta overnight childcare building/fire interpretation: https://open.alberta.ca/dataset/aa64d44e-6f21-474b-a86f-47bf24e40665/resource/2deb6c6e-7070-4bd4-b663-4bc9eb9289cb/download/ma-standata-joint-interpretation-19-bci-024-19-fci-019.pdf
- Alberta Inclusive Child Care Program: https://www.alberta.ca/inclusive-child-care-program
- Alberta Inclusive Spaces Program Grant: https://www.alberta.ca/inclusive-spaces-program-grant
- Alberta Building Blocks Capital Grant Program: https://www.alberta.ca/building-blocks-capital-grant-program
- Alberta Space Creation Grant: https://www.alberta.ca/child-care-space-creation-grant
- CRA child-care expense receipt requirement: https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/deductions-credits-expenses/line-21400-child-care-expenses/how-claim.html
- CRA daycare receipt fields for individual/home providers: https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/daycare-your-home/issuing-receipts.html
- CRA electronic record keeping: https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/ic05-1/electronic-record-keeping.html
- Canada Evidence Act electronic-document integrity: https://laws-lois.justice.gc.ca/eng/acts/C-5/section-31.2.html

### Round 4 correction and seam controls

- [ ] `PRIV-039 P0` Tenant privacy-law profile distinguishes private-sector PIPA, public-body privacy law, federal PIPEDA applicability and any actual HIA role; sensitive child health facts do not by themselves make every daycare an HIA custodian.
- [ ] `PRIV-040 P0` Statutory PIPA breach-notification analysis starts after classifying an actual breach; suspected/alleged events still trigger containment and investigation but are not mislabeled as statutory notice triggers.
- [ ] `REC-008 P0` Retention is record-class specific. Never turn the Alberta attendance-record minimum into one universal retention period for every child, family, health, incident, finance or staff record.
- [ ] `PHYS-021 P0` Lockdown, hold-and-secure, shelter-in-place and evacuation remain separate emergency modes with distinct triggers, communications, headcounts, door behavior and release authority.
- [ ] `INCL-021 P0` Additional-support worker assignment explicitly states whether that worker is ratio-eligible for the exact program/room/time; funding a one-to-one support role never silently increases licensed capacity.
- [ ] `CAPEX-019 P1` Funded-space commitment tracks opening and operating milestones, maintained net-new spaces, affordability/use obligations, site/control changes, closure and repayment/clawback exposure from the signed agreement.
- [ ] `PROGRAM-019 P1` Drop-in fees and funding eligibility use the current Alberta funding rule pack; current public guidance says drop-in fees are not reduced by government funding, but this must remain effective-dated.
- [ ] `PROGRAM-020 P0` Temporary relocation, off-site operation or material change in hours/program enters licensing, municipal, fire/building and public-health applicability review instead of inheriting the original premises approval.
- [ ] `TAXREC-015 P0` Supply-level GST/HST classifier distinguishes generally exempt qualifying child-care services from taxable meals, supplies, instruction, placement or other separately supplied items, with accountant/ruling review for ambiguity.
- [ ] `LEGAL-019 P0` Distinguish an informal/voluntary preservation or disclosure request from a compulsory demand, order or production instrument; neither the word “police” nor a request alone resolves lawful authority.
- [ ] `LEGAL-020 P0` Mandatory child-safety and immediate emergency reporting remain independent of legal-demand review and are never delayed while waiting for subpoena, warrant, counsel or internal investigation.

Classification corrections applying across existing controls:

- `FIRE-*` and `BLDG-*` requirements are `AHJ_APPLICABILITY` unless a cited code, permit, order or approval makes the exact obligation applicable; landlord/operator responsibility may also be contractual.
- `PUBH-*`, sanitation and food controls combine legal applicability, public-health direction and risk guidance. The AHS childcare guide is authoritative guidance, not one undifferentiated statute.
- `EVID-*` are product evidence controls and must not promise automatic admissibility or regulator acceptance.
- `INDIG-*` are community governance, agreement and product controls; OCAP is not a universal statute triggered by an identity field.
- `FLEET-*` resolve by vehicle class, use, jurisdiction, operator and licence rather than one universal childcare transport rule.
- `WCAG 2.2 AA` remains CareSync's product standard unless a customer, procurement or governing rule makes it independently mandatory.
- Insurance, lease, grant/funding and most claim-pack details are agreement-driven unless a separate law, licence or authority requirement is identified.
- Canadian-region hosting is a strong CareSync risk posture, not a blanket PIPA data-localization claim.

Additional correction sources:

- Alberta childcare incident reporting: https://www.alberta.ca/childcare-report-an-incident-concern-or-complaint
- Alberta report child abuse: https://www.alberta.ca/report-child-abuse
- Alberta Early Learning and Child Care Regulation: https://kings-printer.alberta.ca/documents/Regs/2008_143.pdf
- Alberta OIPC privacy-impact assessments: https://oipc.ab.ca/privacy-impact-assessments/
- Alberta serious workplace incidents: https://www.alberta.ca/report-serious-injuries-incident
- Alberta workplace violence and harassment: https://www.alberta.ca/workplace-harassment-violence
- WCB Alberta injury reporting: https://www.wcb.ab.ca/claims/report-an-injury/
- Alberta Human Rights protected grounds: https://albertahumanrights.ab.ca/what-are-human-rights/about-human-rights/protected-grounds/
- Alberta fire codes: https://www.alberta.ca/fire-codes-and-standards
- Alberta building codes: https://www.alberta.ca/building-codes-and-standards
- AHS environmental public health: https://www.albertahealthservices.ca/eph/Page8302.aspx
- CRA GST/HST child-care services: https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/21-1/child-care-services.html
- Criminal Code voluntary preservation/disclosure request distinction: https://laws-lois.justice.gc.ca/eng/acts/C-46/section-487.0195.html

## Round 4, pass AN — lifecycle completion and humane offboarding

- [ ] `LIFE-001 P0` Child exit coordinator for graduation, withdrawal, transfer, non-start, removal and program closure covers effective date, final attendance, room release, funding close, invoice/deposit/refund, portal transition, export, retention and notices.
- [ ] `LIFE-002 P0` Exit blocker prevents silent closure while an incident, safeguarding case, medication discrepancy, disputed pickup, legal hold, refundable balance or required external report remains open; controlled partial exit assigns every exception.
- [ ] `LIFE-003 P0` Last-child household closure reconciles each payer, credit/refund, tax document, consent, scheduled payment, open case and message before the family portal becomes restricted archive access.
- [ ] `LIFE-004 P0` Guardian-authority lifecycle covers invite, proof failure, acceptance, decline, dormancy, dispute, revocation, death, duplicate/merge and reinvite; ending future authority never deletes historic signatures, payments or disclosures.
- [ ] `LIFE-005 P1` Re-enrolment reuses stable identity/history but requires fresh authority, consent, medical, custody, fee, funding and eligibility review instead of reviving stale facts.
- [ ] `LIFE-006 P0` Staff separation distinguishes resignation, termination, layoff, leave, abandonment, death and legal/credential disqualification and sequences time/pay handoff, safety cases, assets, credentials, sessions, retention and rehire state.
- [ ] `LIFE-007 P0` Departing-worker transfer inventory covers room responsibility, medication delegation, child plans, incidents, approvals, inboxes, conversations, scheduled reports, vendor work and secrets before access disappears.
- [ ] `LIFE-008 P1` Candidate lifecycle separates withdrawing one application, declining an offer, pausing marketplace visibility, deleting a candidate profile and leaving employment; one action cannot erase another relationship.
- [ ] `LIFE-009 P1` Transfer handoff supports receiver acknowledgement, partial rejection, missing-item request, correction and disclosure reconciliation; “export sent” is not completion.
- [ ] `LIFE-010 P0` Facility cessation distinguishes planned closure, emergency suspension, licence cancellation/revocation, insolvency and sale and coordinates family/staff notice, child placement help, deposits, government closeout, records custody and reopening criteria.
- [ ] `LIFE-011 P0` Ceased-organization state assigns an accountable records custodian and durable family/staff request channel even when no active administrator or subscription remains.
- [ ] `LIFE-012 P0` Death/bereavement handling for a child, guardian or worker suppresses insensitive automation, preserves required records, closes unsafe access and routes support, benefit, insurer and authority tasks with restricted visibility.
- [ ] `LIFE-013 P1` Vendor/integration termination freezes new work, reconciles unfinished orders/disputes, rotates credentials, returns assets/data, obtains destruction evidence and assigns replacement ownership.
- [ ] `LIFE-014 P1` Abandoned onboarding/no-start expires incomplete invites, releases reserved capacity, handles deposits/documents and permits later restart without duplicate people.
- [ ] `LIFE-015 P1` Closure/reactivation proof records reason, approver, unresolved exceptions, retention basis and the exact prerequisites that must be revalidated.

## Round 4, pass AO — workflow exception recovery

- [ ] `RECOV-001 P0` Stuck-work registry detects transition timeouts and shows object, last successful step, retry safety, owner, deadline, downstream impact and safe fallback.
- [ ] `RECOV-002 P1` Draft lifecycle supports autosave, ownership, expiry warning, reassignment, resume and deliberate abandonment without presenting a draft as submitted.
- [ ] `RECOV-003 P0` External “outcome unknown” state reconciles payment, email, government submission, signature or provisioning status before retrying a possibly successful operation.
- [ ] `RECOV-004 P0` Saga repair workbench shows completed/failed steps, invariant impact, allowable compensation, evidence and dual approval for exceptional manual intervention.
- [ ] `RECOV-005 P0` Bulk action uses preview, stable scope snapshot, resumable execution, per-item outcome, exception export and compensating journal; partial success never appears fully successful.
- [ ] `RECOV-006 P0` Finalized-record correction creates a linked amendment, reversal or replacement and deterministically recalculates affected downstream artifacts without rewriting history.
- [ ] `RECOV-007 P0` Owner loss through termination, leave, role removal or deleted account automatically reassigns open obligations and escalates safety/time-critical items.
- [ ] `RECOV-008 P1` Cross-client consistency indicator shows source version, local pending changes, last confirmed server state and explicit conflict resolution when mobile/admin/offline views disagree.

## Round 4, pass AP — communication lifecycle refinements

- [ ] `VOICE-017 P0` Audience authority is re-evaluated on each new message, attachment and download after custody, consent, employment or relationship changes; historic access and future participation are separate.
- [ ] `VOICE-018 P1` Communication commitments record who promised what, due date, completion evidence and escalation so consequential phone/SMS promises cannot disappear into notes.
- [ ] `VOICE-019 P1` Expiring number proxy/masked calling protects candidates, substitutes, families and staff while retaining abuse-report and lawful-audit paths.
- [ ] `VOICE-020 P1` Voicemail queue protects audio, permits governed transcription with confidence/source, assigns callback deadline and expires content; extracted text never becomes an authoritative care instruction automatically.
- [ ] `VOICE-021 P1` Interpreter lifecycle covers language/dialect/sign language, modality, urgency, request, qualification, conflict, assignment, attendance, completion, cancellation and payment.
- [ ] `VOICE-022 P1` Three-party interpreted call/video preserves attribution among original speaker, interpreter and staff rather than flattening every statement into one author.
- [ ] `VOICE-023 P1` TTY, IP relay and video relay are supported contact modes and are not rejected as suspicious or inferior merely because the number/operator differs.
- [ ] `VOICE-024 P0` Source-content change invalidates linked translation, easy-read, audio and alternate-format versions until reviewed and republished.
- [ ] `VOICE-025 P0` Wrong-recipient response supports containment, revocable-link shutdown, breach triage, deletion request/attestation where appropriate and corrected resend.
- [ ] `VOICE-026 P1` Contact-point lifecycle records unverified, verified, bounced, wrong number, unavailable, do-not-use and emergency-only states with a correction route.
- [ ] `VOICE-027 P0` Shared mailbox/queue delegation and offboarding transfer prevent unresolved family, regulator or safety messages from being stranded in a worker account.
- [ ] `VOICE-028 P1` Communication export/legal hold preserves participants, delivery evidence, attachments, edits, translations and access history without broadening ordinary visibility.
- [ ] `VOICE-029 P1` Emergency voice tree retries approved contacts and alternate channels but never treats a voicemail pickup event as proof that instructions were understood.

## Round 4, pass AQ — research ethics refinements

- [ ] `RESEARCH-019 P0` Non-coercion makes research participation unrelated to care availability, fees, employment, candidate ranking or regulator treatment and provides a retaliation-reporting route.
- [ ] `RESEARCH-020 P0` Research authority supports free, informed and ongoing consent, authorized-third-party authority, child assent/dissent, changing decision capacity and documented REB-approved exceptions where applicable.
- [ ] `RESEARCH-021 P1` Withdrawal records future collection/use restrictions and clearly explains what can and cannot be removed after valid aggregation, analysis or publication.
- [ ] `RESEARCH-022 P0` Protocol deviation, privacy incident, adverse event and unexpected child/community harm trigger containment, required notice, suspension and independent/REB review as applicable.
- [ ] `RESEARCH-023 P1` Sponsor/customer publication review is limited to confidentiality, consent, security and contract checks; it cannot suppress valid unfavourable findings.
- [ ] `RESEARCH-024 P1` Results/benefit return gives participants and affected communities understandable findings and limitations without exposing others.
- [ ] `RESEARCH-025 P0` Derived model, embedding and feature disposition is governed separately from raw-data destruction; deleting the source cannot leave an unrestricted learned artifact.

Research ethics sources:

- TCPS 2 scope and research/quality-improvement distinction: https://ethics.gc.ca/eng/tcps2-eptc2_2022_chapter2-chapitre2.html
- TCPS 2 free, informed and ongoing consent: https://ethics.gc.ca/eng/tcps2-eptc2_2022_chapter3-chapitre3.html
- TCPS 2 privacy, secondary use and data linkage: https://ethics.gc.ca/eng/tcps2-eptc2_2022_chapter5-chapitre5.html
- CRTC message relay services: https://crtc.gc.ca/eng/phone/acces/mrsrt.htm

## Round 4, pass AR — procurement and supplier-marketplace integrity

- [ ] `PROC-001 P1` Procurement intake captures business need, child/worker safety, accessibility, privacy/security, budget, alternatives, lifecycle cost, urgency and approving authority.
- [ ] `PROC-002 P1` Sourcing plan defines quote/RFx method, invited/open suppliers, timetable, mandatory criteria, evaluation method and exception rationale.
- [ ] `PROC-003 P1` Supplier Q&A/addenda give eligible bidders the same approved clarification and preserve the exact version each bidder answered.
- [ ] `PROC-004 P1` Time-sealed bid receipt prevents evaluator access before close and records late, withdrawn, replaced and non-compliant submissions.
- [ ] `PROC-005 P0` Evaluator/sponsor conflict declaration, recusal, ethical wall and related-party review occur before bid access and remain active throughout the procurement.
- [ ] `PROC-006 P1` Evaluation retains individual score/evidence, consensus changes and approval; AI may organize evidence but cannot score or award autonomously.
- [ ] `PROC-007 P1` Award workflow supports notice, unsuccessful-supplier debrief/challenge where policy requires, contract signature and purchase-order activation.
- [ ] `PROC-008 P0` Supplier onboarding verifies identity, appropriate ownership/control, tax/remittance, insurance, safeguarding, accessibility, privacy/security and permitted subcontractors according to risk.
- [ ] `PROC-009 P0` Vendor banking/remittance changes require independent trusted-channel verification, maker-checker approval and cooling-off/alert controls.
- [ ] `PROC-010 P1` Catalogue versions preserve price, unit, availability, expiry and approved substitution; substitution cannot silently change allergen, safety or accessibility properties.
- [ ] `PROC-011 P1` Supplier performance uses contract facts—delivery, defect, SLA, recall, privacy/safety incident and corrective action—with supplier response and appeal.
- [ ] `PROC-012 P1` Return, warranty, service credit, refund, invoice dispute and rejected-delivery workflows reconcile inventory and accounting.
- [ ] `PROC-013 P0` Emergency procurement permits bounded fast-track purchasing but requires stated emergency, ceiling, expiry, conflict check and after-action review.
- [ ] `PROC-014 P1` Local, diverse and Indigenous supplier attributes are voluntary/self-attested or verified through an approved source and never inferred from names or location.
- [ ] `PROC-015 P0` Sponsored placement, commissions and marketplace fees are visibly labelled; payment cannot hide safer, compliant or better-fitting options.
- [ ] `PROC-016 P1` Supplier reviews require a verified transaction, factual dimensions, moderation and appeal; competitors cannot anonymously review one another.
- [ ] `PROC-017 P1` Contract-obligation calendar tracks renewal, price change, certificate, data return, subprocessor/subcontractor change and exit assistance.
- [ ] `PROC-018 AVOID` No open general-purpose marketplace before curated onboarding, transaction disputes, recall tracing, due process and integrity controls work.

## Round 4, pass AS — accessibility beyond a web conformance badge

- [ ] `A11Y-001 P1` Portable accessibility preference profile applies across web, mobile, kiosk, documents, email and notifications, with a safe per-device override.
- [ ] `A11Y-002 P0` Accessible authentication/recovery permits password managers and copy/paste and avoids inaccessible CAPTCHA, memory puzzles and forced code transcription.
- [ ] `A11Y-003 P0` Assistive-technology test matrix includes screen readers, switch access, voice control, keyboard, one-handed use, large text, zoom/reflow and major mobile accessibility services.
- [ ] `A11Y-004 P0` Status never depends only on colour, animation, sound, position or gesture; every critical state has durable text and semantics.
- [ ] `A11Y-005 P1` PDFs, statements, forms, emails and exports have semantic headings, reading order, labels, document language, alternatives and tagged tables—not merely accessible source screens.
- [ ] `A11Y-006 P1` Photo/video/audio workflows support alt text, captions, transcripts and consent-aware accessible alternatives.
- [ ] `A11Y-007 P0` Long/critical forms autosave, resume, warn before timeout and restore focus/error context without losing entered data.
- [ ] `A11Y-008 P1` Authorized helper-supported completion records helper identity, participant intent and authorship without granting unnecessary guardian authority.
- [ ] `A11Y-009 P1` Kiosk acceptance covers seated reach, target size, glare, privacy, timeout extension, audio alternatives and staff-assisted fallback.
- [ ] `A11Y-010 P0` Emergency/evacuation/reunification preserves accessible communication, mobility/sensory assistance, relay/interpreter routes and non-digital fallback.
- [ ] `A11Y-011 P0` Accessibility defect severity comes from the blocked real-world task, workaround, affected versions, deadline and notification—not cosmetic priority.
- [ ] `A11Y-012 P0` Source-content change invalidates translations, easy-read, audio and alternate-format derivatives until review.
- [ ] `A11Y-013 P1` Sensory/neurodiversity mode supports reduced motion/transparency, predictable layout, lower stimulation and optional simplified task view.
- [ ] `A11Y-014 P0` No drag-only, hover-only, voice-only, device-motion-only or narrowly timed action; equivalent controls are required.
- [ ] `A11Y-015 P0` Personalization cannot hide medication, custody, pickup, emergency, ratio or other mandatory safety state.
- [ ] `A11Y-016 P1` Inclusive research includes people with disabilities and caregivers in realistic, compensated end-to-end failure/recovery testing.
- [ ] `A11Y-017 P1` Navigation preserves orientation through clear titles, hierarchy/back behavior, progress, current facility/child context and deep-link recovery.
- [ ] `A11Y-018 P1` Standards watch tracks the draft CAN-ASC-2.9 Accessible Childcare Centres through publication, then performs legal/applicability and product-gap review; draft text is not treated as current Alberta law or frozen implementation specification.

Accessibility research classification: these are CareSync product standards unless a particular customer, procurement or governing rule independently makes them mandatory.

## Round 4, pass AT — agentic AI and automation containment

- [ ] `AGENT-001 P0` Agent registry declares owner, purpose, tools, data classes, tenants, environments, action limits and prohibited operations.
- [ ] `AGENT-002 P0` Delegated authority is cryptographically/scopingly bounded, never exceeds the initiating human's current permissions and ends on revocation/expiry.
- [ ] `AGENT-003 P0` Agents default to read-only; mutation requires an approved workflow, visible diff/preview and risk-appropriate human confirmation.
- [ ] `AGENT-004 P0` High-risk operations separate proposer, reviewer and executor; an agent cannot approve its own recommendation.
- [ ] `AGENT-005 P0` Per-run budgets cap records, money, messages, external submissions, duration, tools, retries, tokens and cost.
- [ ] `AGENT-006 P0` Durable checkpoint, pause, cancel and resume stop a run cleanly and show exactly what completed before interruption.
- [ ] `AGENT-007 P0` Action ledger records agent identity, human delegator, task, sources, tool request/result, policy decision, approval and actual side effect.
- [ ] `AGENT-008 P0` Email, websites, files, OCR text, API/tool output and peer-agent messages are untrusted data and cannot redefine authority or system instructions.
- [ ] `AGENT-009 P0` Tool-boundary DLP authorizes each field and destination, blocks cross-tenant/context exfiltration and records denied egress.
- [ ] `AGENT-010 P0` Secret broker performs scoped operations without placing credentials, API keys or raw tokens in model context, logs or memory.
- [ ] `AGENT-011 P0` Each mutating tool has idempotency and reconcile-before-retry semantics; the agent cannot guess whether an unknown outcome failed.
- [ ] `AGENT-012 P0` Irreversible operations are unavailable to agents; reversible operations require a tested compensation path and evidence rollback completed.
- [ ] `AGENT-013 P0` Memory registry exposes source, scope, sensitivity, retention, confidence and edit/delete controls; no hidden long-term memory.
- [ ] `AGENT-014 P0` Memory/retrieval is isolated by tenant, user, role, purpose and child/family authority and reauthorized at use time.
- [ ] `AGENT-015 P0` Agent/service identity remains distinguishable from a human in audit, communications and signatures; no impersonation.
- [ ] `AGENT-016 P0` Agent-to-agent delegation carries explicit capability tokens and treats peer output as untrusted evidence, never authority.
- [ ] `AGENT-017 P1` Shadow/simulation mode compares proposed actions with human outcomes before mutation authority.
- [ ] `AGENT-018 P0` Kill switches exist per run, agent, tool, tenant and platform and safely handle in-flight work.
- [ ] `AGENT-019 P0` Loop/repetition detector stops recursive planning, message storms and cost amplification while preserving a human-readable checkpoint.
- [ ] `AGENT-020 P0` External portal/browser/RPA automation is disabled unless the interface is lawful, approved, scoped and observable, with explicit live authorization for consequential submission.
- [ ] `AGENT-021 P0` Uncertainty, conflicting sources, ambiguous policy or repeated failure hands a complete evidence bundle to a named human rather than improvising.
- [ ] `AGENT-022 P0` Agent-generated policy, code, SQL, rule packs or configuration cannot approve/deploy itself; normal secure-delivery gates remain mandatory.
- [ ] `AGENT-023 AVOID` No autonomous offer/rejection, discipline, child release, custody interpretation, medication action, incident conclusion, regulator submission or irreversible financial act.

Transfer sources:

- W3C WCAG 2.2 accessible authentication: https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html
- W3C cognitive accessibility guidance: https://www.w3.org/WAI/cognitive/
- Accessibility Standards Canada service delivery: https://accessible.canada.ca/standards-and-technical-guides/standards-and-technical-guides-database/summary-can-asc-5212026-accessible-service-delivery
- Accessibility Standards Canada procurement guidance: https://accessible.canada.ca/standards-and-technical-guides/standards-and-technical-guides-database/procurement-accessible-goods/4-introduction
- Accessibility Standards Canada draft childcare-centre standard overview: https://accessible.canada.ca/creating-accessibility-standards/overview-draft-standard-can-asc-29-accessible-childcare-centres
- Government of Canada supplier integrity: https://www.canada.ca/en/public-services-procurement/services/standards-oversight/supplier-integrity-compliance/about.html
- NIST agent-hijacking research: https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations
- OWASP Excessive Agency: https://genai.owasp.org/llmrisk/llm062025-excessive-agency/

## Round 4 adversarial test corpus

These are not feature slogans. Each becomes an executable cross-app test, tabletop exercise or operational drill before the affected capability is called production-ready:

- Staff access is revoked before their medication/case handoff, leaving a child workflow ownerless.
- A departing worker changes forwarding, contact or shared-queue ownership to retain information after departure.
- A revoked guardian loses server access but still sees cached/offline child facts.
- Removing a guardian erases or invalidates historic signatures, payments or disclosure evidence.
- A child transfer closes while an incident, legal hold or medication discrepancy remains open.
- Facility closure releases a deposit but leaves autopay and scheduled messages active.
- Organization insolvency removes the only administrator and nobody can answer record requests.
- An asset/share sale silently transfers family data, licences or grant assumptions without applicability review.
- Bereavement triggers attendance, birthday, invoice, pickup or credential reminders.
- Candidate profile deletion also deletes or corrupts an active employee identity.
- An external payment/submission succeeds but times out; retry duplicates the consequence.
- A room move updates 97 children, fails for three and presents the whole batch as complete.
- A draft incident looks submitted because its owner left employment.
- A guardian change occurs between message composition and send, exposing an attachment to the wrong household.
- An abusive contact cycles through proxy numbers/interpreter calls to bypass a safety block.
- A caller impersonates a guardian and requests pickup, banking, contact or health changes.
- A staff paraphrase converts an allegation or telephone report into a verified fact.
- Voicemail OCR/transcription converts uncertain speech into a medication instruction.
- A résumé, email, supplier PDF, image OCR result or website prompt-injects an agent.
- An interpreter is related/conflicted, unqualified for the modality or retains a personal copy.
- A source policy changes but its translation/easy-read/audio version remains active.
- Relay-service users are rejected by fraud logic because the apparent number/operator differs.
- A research partner links a name-removed small cohort to public records.
- Ordinary operational consent is silently reused to train a commercial model.
- Research withdrawal is promised after results are irreversibly aggregated.
- A sponsor pressures CareSync to suppress an unfavourable finding.
- Embeddings/model artifacts remain unrestricted after the source dataset is destroyed.
- A vendor employee who wrote requirements later evaluates or wins the procurement.
- A fraudster changes supplier bank details immediately before payment.
- Emergency procurement becomes a permanent bypass with no expiry/review.
- Paid marketplace placement hides the safer or compliant supplier.
- A substituted food/equipment product changes an allergen, safety or accessibility property.
- Accessibility personalization hides a mandatory custody, medication or emergency warning.
- A long form times out while the user relies on assistive technology.
- Login blocks paste/password managers or requires an inaccessible puzzle.
- Emergency instructions exist only as sound, colour or animation.
- A generated PDF looks correct visually but has an unusable reading order.
- An agent retries a non-idempotent payment, invitation or government submission.
- Hostile external content causes an agent to leak another tenant's facts.
- Agent memory carries one family/tenant's data into another context.
- An agent proposes, approves and executes its own high-risk recommendation.
- An agent receives the human's broad role instead of a narrowly delegated capability.
- A loop sends hundreds of messages or repeatedly mutates one record.
- Revocation stops new agent calls but leaves in-flight tools mutating state.
- An agent claims completion when only a draft/proposal exists.
- A secret reaches model context and is copied into logs, memory or an explanation.
- Agent-generated policy/rule/code deploys without legal, operator and secure-delivery review.

## Round 4 convergence assessment

The fourth cycle produced material new domains and corrected earlier overclaims; it therefore did **not** converge at the start. After facility security, inclusion, capital projects, program variants, tax evidence, legal demands, lifecycle/offboarding, recovery, communications, research, procurement, accessibility and agentic automation were decomposed, repeated passes began returning refinements rather than new top-level systems.

That is a useful boundary, not a claim of final completeness. Reopen research whenever any of these occur:

- Alberta statute, regulation, director instruction, funding agreement or official program page changes.
- CareSync enters another province, country, program model, health role or public-body procurement.
- A new payment, payroll, insurance, transport, camera, biometric, AI, research or government integration is proposed.
- A real incident, complaint, accessibility barrier, failed restore, audit finding or near miss reveals a missing control.
- A customer type or workflow cannot be represented without a generic bypass/custom-field escape hatch.

The next product-management move is not to implement 1,000 controls at once. It is to select a small end-to-end vertical slice, map every applicable P0 control, prove it across backend/admin/mobile/offline/evidence, and only then widen the surface.

The accepted bounded architecture following the schema-less `0040` billing
planner is
[`0041_live_room_presence_and_safety_board`](LIVE_ROOM_PRESENCE_SAFETY_BOARD_ARCHITECTURE.md).
It records factual staff room presence and compares confirmed live facts only
with configured operational targets. It does not implement or certify Alberta
ratios, qualifications, group size, licensed capacity or supervision.
