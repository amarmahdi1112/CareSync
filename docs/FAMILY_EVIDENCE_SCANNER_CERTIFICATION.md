# Family evidence real-scanner certification

This is the bounded operator proof for CareSync's existing family-evidence
scanner adapter. It uses the production `scan_private_object` function and the
same inode-pinned private handle used by the family-authority API.

The harness is deliberately synthetic-only. It creates a private clean text
fixture and the standard harmless antivirus test signature in a temporary
mode-0700 directory, proves clean and rejected verdicts, then proves that a
missing scanner and a scanner that passes its version probe before failing in
the scan phase both fail closed. Temporary fixtures are removed before a
receipt is returned.

It does not import or initialize CareSync's database layer, open a network
socket, invoke Alembic, inspect a vault, or use child/family data. The receipt
does not contain fixture bytes, fixture paths, the scanner's absolute path, or
the detected signature. It is written outside the source tree as a mode-0600,
single-link, no-clobber JSON file. A passing receipt is scanner evidence only;
it is not authority to migrate, activate a facility, cut over 0029, or release
a child.

The certified local adapter is `clamscan`. It receives the pinned inode through
standard input and is always invoked with `--alert-exceeds-max=yes`; ClamAV
resource-limit exhaustion therefore cannot become a clean verdict. `clamdscan`
is deliberately unavailable until CareSync has an explicit way to attest the
daemon-side `AlertExceedsMax` policy. The receipt writer rejects incomplete or
expanded evidence shapes, and it stores only a normalized ClamAV
version/definition identity rather than raw scanner output.

## Exact invocation

From `backend/`, choose a new receipt name for every run:

```sh
receipt_root="$HOME/Library/Application Support/CareSync Basic/private-certification-receipts"
receipt="$receipt_root/family-evidence-scanner-$(date -u +%Y%m%dT%H%M%SZ).json"
install -d -m 700 "$receipt_root"

CARESYNC_RUN_REAL_SCANNER_CERTIFICATION=synthetic-only \
  .venv/bin/python -m scripts.family_evidence_scanner_certification \
  --synthetic-only \
  --scanner /opt/homebrew/opt/clamav/bin/clamscan \
  --receipt "$receipt"
```

The command refuses an absent `--synthetic-only` acknowledgement, an absent or
incorrect environment opt-in, a relative scanner or receipt path, a missing or
non-private mode-0700 receipt directory, a receipt inside the backend source
tree, and an existing receipt. ClamAV's reported definition timestamp must
satisfy the production freshness policy (168 hours by default).

Run the focused automated gate with the same explicit opt-in:

```sh
CARESYNC_RUN_REAL_SCANNER_CERTIFICATION=synthetic-only \
CARESYNC_REAL_SCANNER_PATH=/opt/homebrew/opt/clamav/bin/clamscan \
  .venv/bin/python -m pytest -q \
  tests/test_family_evidence_scanner_certification.py
```

Run lint without either opt-in because lint never executes the harness:

```sh
.venv/bin/python -m ruff check \
  scripts/family_evidence_scanner_certification.py \
  tests/test_family_evidence_scanner_certification.py
```

## Recorded local proof

The hardened 2026-07-22 synthetic-only run used `clamscan` 1.5.3 with definition
serial 28068 dated 2026-07-22. All four cases passed: clean, harmless
test-signature rejection, configured scanner unavailable, and post-version
scan-process failure. The current private receipt is:

`~/Library/Application Support/CareSync Basic/private-certification-receipts/family-evidence-scanner-20260722T084756Z-hardened.json`

It is an owned mode-0600 single-link file with SHA-256
`c6920e76f3839c2d6aa8ad9c4e9d3806cf85f19a2ebd43c737158854731da7d7`.
Focused Ruff passed; the real-inclusive scanner/certification boundary passed
17 focused tests and the staff-vault hardening boundary passed 17 tests.
`sigtool --verify` also verified `main-63`, `daily-28068` and `bytecode-339`
against their detached signatures, all signed by `ClamAV_datafiles_release`;
the updater's earlier certificate-store warning was not treated as proof. The
earlier receipts, including `20260722T082212Z` and `20260722T083907Z`, are
retained as historical evidence but superseded because they predate one or more
of scan-limit enforcement, strict receipt-shape validation, canonical token
validation and the post-version failure proof. This closes only the hardened synthetic
real-scanner adapter proof. Separate bounded synthetic signed-in authority-operation and
four-artifact recovery-consistency receipts have since passed; this scanner receipt does not prove
either one. Writer-frozen authoritative capture, physical-device acceptance and 0029
activation/cutover remain open.
