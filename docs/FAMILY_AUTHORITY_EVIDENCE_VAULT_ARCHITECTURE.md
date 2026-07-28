# CareSync 0029A1 Family-Authority Evidence Vault

Last updated: 2026-07-22

## Status and boundary

This document records the bounded `0029A1_family_evidence_vault` implementation that follows the
verified, source-only `0029A_family_authority_kernel`, plus the exact way the source-only
`0029A2_authority_activation` revision may consume reviewed vault evidence. A1 is an additive
evidence-possession and review gate; review alone still creates no authority. A2 enables only the
explicit administrative activation lanes documented below. It does not enable educator release
context, verified checkout, software override, legal interpretation, or a retained-database
cutover.

The A/A1/A2 source implementation, portable/admin matrices and disposable restricted-role
PostgreSQL gates are verified. Later bounded synthetic scanner, signed-in operator and
four-artifact recovery-consistency receipts are also recorded, but none is a live-local release or
retained scanner-operational claim.

The retained local database remains at released revision `0028_childcare_command_spine` until a
separate backup-first release decision. Development migrations and destructive verification use
disposable databases only.

## Safety objective

The 0029A kernel can record an external or physical evidence fact, but it intentionally cannot
prove that CareSync possesses the referenced bytes. A client also cannot be trusted to choose an
object key or assert media type, size, hash, scan result, reviewer, or issuer validity.

0029A1 closes only that gap:

1. an authenticated owner or administrator uploads bytes through a tenant- and family-bound API;
2. the server generates the opaque object identity and private storage key;
3. the server measures the exact bytes, media type, size and SHA-256 digest;
4. the object remains unusable until an installed malware scanner returns a clean result;
5. a document evidence record pins that exact clean object version; and
6. a different active owner/administrator performs the human administrative review.

An administrative review means only that the reviewer observed the stored document and recorded
an assessment. It is not legal advice, court-order interpretation, identity assurance, government
verification, or a release decision.

## Deliberately bounded upload flow

The local MVP uses a direct authenticated multipart upload. The scoped HTTP route itself is the
tenant/family issuance boundary; there is no client-selected path and no public or presigned URL.
A later object-store deployment may split issuance and upload, but it must preserve the same
aggregate, exact-retry and object-version contract.

1. `POST /families/{family_id}/authority/evidence-objects` accepts
   `client_operation_id`, `evidence_kind`, and one `file`.
2. Authorization is rechecked before the operation slot, before persistence and at database
   commit through the existing API-managed tenant/actor context.
3. The server reads no more than the configured maximum plus one byte, rejects oversize content,
   and ignores the untrusted filename for storage and type decisions.
4. A strict signature allowlist recognizes only PDF, JPEG and PNG. The submitted MIME header is
   advisory and a mismatch is rejected. Active content, archives, office documents, SVG, HTML and
   unknown formats are rejected.
5. The server creates a random object ID and opaque relative key, writes through a same-directory
   `O_EXCL` temporary file, fsyncs it, and publishes the final name with a no-clobber hard-link
   operation before unlinking the temporary name and fsyncing the directory. Publication never
   replaces an existing final name. Directories/files are `0700`/`0600`, and storage is outside
   every mounted static or web root.
6. The server records immutable measured media type, byte size and lowercase SHA-256. It may retain
   a bounded, normalized display filename, but never uses it as a path. No public URL, absolute
   path, document bytes, filename, or custody content enters a command receipt, realtime event,
   push notification, URL query, or browser journal.
7. Upload commits version one in `quarantined`; it never claims the object is clean.
8. `POST /families/{family_id}/authority/evidence-objects/{object_id}/scan` asks the server to invoke
   a fixed-argument scanner adapter. The client cannot submit or override a verdict. Missing
   scanner, timeout, process failure, malformed output, skipped content, or unknown result rolls
   the scan transaction back, returns a typed service failure, and leaves the object quarantined.
   A new or exact retry may ask the server to scan again, but still accepts no verdict fields.
9. A clean object may be downloaded only by an active owner/administrator through
   `GET /families/{family_id}/authority/evidence-objects/{object_id}/download`. The response is
   `private, no-store`, uses the server-derived media type, forces attachment disposition, applies
   `X-Content-Type-Options: nosniff`, and never exposes the storage key.

## Content and compatibility policy

The following evidence kinds require one exact current clean object:

- `identity_document`
- `custody_document`
- `court_order`
- `signed_consent`
- `signed_release_delegation`
- `other_document`

The following evidence kinds are non-file observations and forbid an object:

- `guardian_attestation`
- `staff_witness`

`document_observed` is valid only for an evidence record bound to a clean object. `reported` is
valid only for a non-file observation. A kind mismatch, cross-family object, terminal scan state,
expired object, already-bound object or changed object version fails without creating evidence.

Review alone does not activate any authority basis. A2 supplies this exact positive matrix and
rejects every unlisted combination:

| Administrative command lane | Authority basis or policy requirement | Required evidence |
| --- | --- | --- |
| release authorization | `guardian_record` | `guardian_attestation` plus current live-guardian provenance |
| release authorization | `reviewed_custody_evidence` | `custody_document` |
| release authorization | `reviewed_delegation_evidence` | `signed_release_delegation` plus original live-guardian provenance; no re-delegation |
| `deny` or `manager_review` rule | `guardian_record` | `guardian_attestation` plus one explicit current directing guardian |
| `deny` or `manager_review` rule | `reviewed_custody_evidence` | `custody_document` |
| consent signer authority | policy `guardian_record` | signer basis `guardian_record` + `guardian_attestation` + live-guardian provenance |
| consent signer authority | policy `legal_decision_maker` | signer basis `reviewed_custody_evidence` + `custody_document` |
| consent decision | either active signer lane | a separate `signed_consent` evidence/assessment tuple |

The consent decision and signer-authority evidence IDs must be distinct. The command activator must
differ from every evidence reviewer, each assessment must remain the current reviewed assessment,
and command windows cannot outlive evidence expiry. Invalidation or supersession follows both
consent evidence lanes and advances each affected child head once. `supervised_only`,
`named_recipient_only`, `specific_reviewed_authority` and `other_reviewed_authority` remain
non-activating.

The database and service matrix also enforce these negative rules:

- an identity document cannot establish custody, delegation, consent-signing authority or pickup
  authority;
- signed consent cannot imply pickup or custody authority;
- a staff witness cannot independently establish legal or custody authority;
- an attestation cannot silently replace a document required by policy; and
- `other_document` is never a catch-all authority grant.

## Persistence contract

### `family_authority_evidence_objects`

One measured-identity row represents the exact stored byte version. It contains:

- server-generated object ID;
- organization and family IDs;
- bounded evidence kind;
- exact object version, initially one;
- opaque private storage reference;
- server-derived media type, byte size and SHA-256;
- uploader user ID and exact upload operation ID; and
- finite server timestamps.

The measured identity, tenant/family binding, storage reference, object version, media facts,
uploader and upload provenance are immutable. The runtime role may move only `status`, once, from
`quarantined` to `clean` or `rejected`; database guards reject every other update. The runtime role
has no DELETE grant. Replacement uploads create new objects, and an object is single-use for
evidence attachment.

### `family_authority_evidence_object_assessments`

An append-only ordered stream records quarantine and scan outcomes. Each row binds organization,
family, object, version number, exact initiating actor/operation, decision, server time and the
bounded scanner metadata applicable to that decision.

The exact decisions in this slice are `quarantined`, `clean`, and `rejected`. `clean` and infected
rejection require a named scanner engine. An infected rejection may carry a bounded signature
label and reason code. Scanner infrastructure failures do not append a false domain verdict: the
transaction rolls back and the object remains quarantined. Diagnostic stdout, absolute paths and
document content are never persisted or returned.

Current state is derived from the highest assessment version under the aggregate lock. A clean or
rejected result is terminal in this bounded slice and history is never rewritten. Operational scan
failure telemetry remains separate from the immutable domain assessment stream.

### Binding to `family_authority_evidence`

The additive migration adds a nullable, unique, same-tenant/same-family `evidence_object_id` link.
When a document evidence record is created, the service locks the object and latest assessment,
requires current clean state, exact kind compatibility and no existing attachment, then copies the
server-measured storage tuple into the immutable evidence row in the same transaction. Non-file
evidence retains the null storage tuple and null object link.

Every evidence asset also stores immutable `recorded_by_user_id`, bound on insert to the current
command/receipt actor. PostgreSQL maker/checker enforcement reads this domain provenance directly;
it does not depend on one administrator being allowed to read another actor's private historical
receipt under forced RLS.

The copied tuple is an integrity projection, not a client claim. Database guards require it to
exactly match the pinned object row.

## Exact command and retry contract

The evidence-object target type is `authority_evidence_object`. The initial command vocabulary is:

- `family.authority.evidence_object.upload`
- `family.authority.evidence_object.scan`

Upload and scan requests use the 0028 operation ledger. Upload commits object/assessment version
one; a conclusive scan commits assessment version two. Same operation and canonical intent return
one immutable receipt and current projection. Reusing an operation with changed family, kind,
object, expected version, measured hash or byte count returns `409 operation_reused`. Replay never
changes the canonical object, reruns the scanner, or duplicates assessment history, audit, outbox
or realtime invalidation. Because multipart intent includes server measurements, an upload retry
is measured under a new private candidate object before receipt lookup; exact replay deletes that
duplicate candidate and returns the original object receipt.

The multipart request is read and measured before canonical intent is finalized. A typed
pre-commit database rejection removes the newly published file. A database commit/response
ambiguity deliberately retains the private bytes because commit status is not yet known.

`backend/scripts/family_evidence_vault_reconcile.py` is a report-only integrity tool. It derives
the canonical inventory from a verified database backup, traverses the vault descriptor-relative
without following symbolic links, and reports missing, mismatched, unsafe, unexpected and
indeterminate state. It never deletes or quarantines bytes, and `--purge` always fails closed.
Absence from one current-format backup is not deletion authority because that backup contract does
not record an authoritative `snapshotEstablishedAt` boundary and does not prove live-database
quiescence.

A future purge implementation remains unavailable until it proves all of these independent gates:

- two verified snapshots containing an authoritative `snapshotEstablishedAt` value;
- the same unexpected object is absent from both snapshots and unchanged for at least 30 days;
- writer and live-database quiescence is proven for the decisive inventory;
- an exact, reviewable purge-plan digest is confirmed before mutation; and
- every attempted deletion produces durable per-object receipts, including failures.

No age threshold, filename pattern, single-backup absence or scan rejection can bypass those
requirements. Rejected and invalid-document bytes remain canonical retained objects today.

## Maker/checker rule

Evidence capable of later supporting custody, release or consent must have separate maker and
checker actors. For document evidence, the human reviewer must differ from both the object uploader
and the evidence recorder. For non-file evidence, the reviewer must differ from the recorder. Both
actors must have active owner/administrator authority at their respective commits, and their exact
IDs and operation provenance remain immutable.

The maker may reject or abandon their own submission because rejection cannot activate authority.
The maker cannot produce a `reviewed` assessment. Loss of membership or role before commit rolls
the entire command back.

## Malware scanning

The adapter executes `clamscan` with a fixed executable path and fixed arguments, without a shell
and without user-controlled options. It streams the already pinned inode over standard input and
sets `--alert-exceeds-max=yes`, so ClamAV time/size/recursion/file-limit exhaustion cannot be
reported as clean. `clamdscan` fails closed until a separate contract can attest the daemon-side
`AlertExceedsMax` policy; the client cannot infer that policy. The adapter applies a bounded process
timeout and upload limit. A clean database/engine result with fresh definitions is required.
Scanner absence, unhealthy definitions, limit exhaustion or unattested daemon policy leaves the
object in a non-clean state; the application never uses a homemade signature check as a
malware-clean substitute.

ClamAV is one defensive layer, not proof that content is safe. After a clean malware result, PDF or
image structure validation runs in a separate Python isolated-mode subprocess with CPU, file-size,
descriptor, address-space and wall-clock bounds. The parser rejects encrypted or active PDFs,
embedded/action content, excessive PDF graph depth/size/pages, animated images, media mismatch and
excessive image pixels. This is resource/process isolation, not a claim of an OS container or
network sandbox. This phase does not run OCR or interpret document meaning.

The development host now has ClamAV. The hardened 2026-07-22 opt-in synthetic-only proof exercised
the production inode-pinned adapter with a clean fixture, the standard harmless antivirus test
signature, a missing scanner and a scanner that passes its version probe before failing during the
scan phase. The receipt writer accepts only the complete closed evidence shape, and scanner version
output is normalized before it crosses the receipt boundary. Its redacted private receipt and exact
command are recorded in `FAMILY_EVIDENCE_SCANNER_CERTIFICATION.md`. This receipt closes the
hardened local scanner-adapter proof only; it does not itself prove the separately recorded
signed-in or recovery-consistency gates and never authorizes live-local 0029 cutover.

## Authorization, privacy and storage

- All routes require an active owner or administrator in the exact organization.
- Both new tables use composite organization/family foreign keys, `ENABLE/FORCE ROW LEVEL
  SECURITY`, fail-closed tenant/actor policy and least grants.
- The runtime role receives only the exact inserts needed for immutable objects/assessments and
  SELECT required by admin projections. It receives no UPDATE or DELETE.
- Confidential object metadata is never exposed to educator, realtime, push or OS-notification
  payloads.
- The existing shared-runtime-role/GUC limitation remains disclosed; 0029A1 does not claim to solve
  arbitrary raw SQL through that credential.
- The private object root is excluded from static mounts and project source. Backup/restore treats
  database metadata and exact object bytes as one consistency set.

## Failure semantics

- structural request failure: `422`, with no operation or object;
- unsupported, empty or signature/MIME-mismatched content: `422`;
- upload too large: `413`;
- missing/cross-tenant resource: tenant-scoped `404`;
- stale object/evidence version: typed `409`;
- reused operation with changed intent: `409 operation_reused`;
- scanner unavailable/failure: scan transaction rolls back, object remains quarantined, and a
  typed non-sensitive `503` permits a later exact retry;
- infected content: terminal non-clean state and no attachment/review/download;
- maker/checker conflict: `409 maker_checker_required`;
- retained 0028 runtime: contained `503 family_authority_unavailable`.

## Release and test gates

Before this slice may be described as verified source:

- strict schema tests reject client keys, hashes, sizes, verdicts, extra fields and ambiguous
  evidence/object combinations;
- upload tests cover oversize input, MIME spoof, malformed signatures, traversal filenames,
  executable/archive/active content, exact hashing and restrictive permissions;
- scanner tests cover clean, infected, timeout, missing binary, nonzero error, output bounds and
  exact retry without re-scan;
- API tests cover tenant/family mismatch, role loss, object single-use, compatibility,
  maker/checker and private download headers;
- direct PostgreSQL tests cover immutable rows, assessment sequence, tuple equality, forced RLS,
  least grants and cross-tenant forgery;
- concurrency tests produce one winner for upload replay, scan transition, bind, review and
  terminal object transition;
- migration tests prove fresh `0028 -> 0029A -> 0029A1 -> 0029A2_authority_activation`, empty
  downgrade/upgrade, populated downgrade refusal and no change to legacy pickup/consent values;
- backup/restore proves exact database rows plus object inventory, byte length and SHA-256; and
- full backend/admin regression, lint, typecheck and build gates remain green.

The source backup/restore gate is implemented by
`backend/scripts/family_evidence_vault_bundle.py`. It cryptographically binds a separate private
archive to an already verified logical DB backup and its manifest, derives the inventory only from
that DB snapshot, verifies every required object before archive creation, and restores only into a
new disposable vault root. Every persisted object row requires exact bytes, including terminal
`rejected/invalid_document` and `rejected/malware_detected` objects, including the A2
`signed_release_delegation` document kind. Rejection prevents use and
download; it is not an implicit purge lifecycle. Traversal, symbolic links, unexpected archive
members, non-private modes, clobbering, inventory substitution and measurement mismatch fail
closed. The full operator procedure is in `CUTOVER_BACKUP_RESTORE_RUNBOOK.md`.

The 2026-07-22 synthetic exact-0029D joint recovery-consistency run exercised that contract with
one fixed four-artifact set. A caller-created scratch cluster restored 90 tables / 61 rows, the new
vault restored one evidence object, and the post-restore reconciler reported no missing,
mismatched, unexpected, unsafe, indeterminate or unclassified object. The private joint receipt is
`/Users/amarmuha/Library/Application Support/CareSync Basic/private-certification-receipts/family-authority-joint-recovery-20260722T172958Z.json`;
SHA-256 `da15e913738106a86b0d9682f040818755ac35560780b1f7a6b2c57aed4d8d1a`.
It proves artifact recovery consistency only. It explicitly leaves source-writer quiescence,
authoritative completeness/same-snapshot capture, unexpected source-vault exclusion, schema
authenticity and every migration/release/cutover/purge authority false. Rejected bytes and orphan
candidates remain non-purgeable, and retained port 5434 remains exact released 0028.

The A2 closeout on 2026-07-18 recorded 170/170 passing focused authority regression tests. The
maintained A/A1/A2 Python surface passed Ruff and bytecode compilation. The administrator client
passed TypeScript, 81 test files / 501 tests, and a production build transforming 834 modules; the
only build diagnostic was the existing oversized-chunk advisory. These counts are overlapping,
not additive. Disposable restricted-role PostgreSQL 17 separately passed 3/3 A2 gates: fresh
upgrade to exact revision `0029A2_authority_activation` and runtime identity, forced RLS/exact
least grants, positive activation commits, database rejection of invalid evidence kinds and
same-actor maker/checker, and populated downgrade refusal. Protected ports 5432/5433/5434 were not
contacted. None of this is operational ClamAV or retained cutover evidence.

No migration or source verification authorizes a retained 5434 cutover. The retained database
remains at released `0028_childcare_command_spine`; a separate operator, scanner-readiness and
backup-first release decision is required.

## Explicitly carried beyond A2

A2 closes only administrator-authored authority activation. Source-verified
`0029B_release_context` now supplies the minimum-necessary, expiring educator read projection. It
closes deterministic composition for the A2-activatable `deny`/`manager_review` vocabulary,
canonical restriction digesting, current actor/shift/room-scope evaluation and an in-memory
expiring staff context. It deliberately commits none of those facts as checkout evidence.
`0029C` must supply atomic verified checkout. The following remain blocked rather than guessed:

- unambiguous `named_recipient_only` semantics;
- supervisor identity/evidence for `supervised_only`;
- a satisfiable immutable approval object for `manager_review`;
- secondary identity-check representation;
- release-specific readiness distinct from a generic authority revision;
- immutable actor membership, permission, shift and room-scope snapshots;
- closure of every legacy attendance-checkout bypass; and
- atomic checkout plus immutable release snapshot and response-loss reconciliation.

Software override remains deferred beyond normal verified release. Until 0029C closes the legacy
bypass, CareSync attendance checkout is attendance evidence only and must not be marketed as
verified child release.

## Engineering references

- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- ClamAV scanning documentation: https://docs.clamav.net/manual/Usage/Scanning.html
- ClamAV daemon protocol: https://docs.clamav.net/manual/Usage/ClamdProtocol.html
