# CareSync production deployment

This directory defines the Linux production edge for CareSync. It is separate
from the macOS retained-database launcher: production runs an immutable release
under `/srv/caresync`, PostgreSQL 17, one unprivileged FastAPI service, Nginx,
and an optional push worker.

The initial production database is **fresh**. The deployment artifact contains
source and compiled frontend assets only. It does not contain or transfer the
local CareSync database, childcare records, vault contents, uploaded documents,
backups, API keys, or `.env` files.

## Runtime layout

| Path or listener | Purpose |
| --- | --- |
| `/srv/caresync/releases/<commit>/` | immutable release directories |
| `/srv/caresync/current` | atomic symlink to the active release |
| `/opt/caresync/ocr/.venv` | server-only OCR environment |
| `/etc/caresync/backend.env` | owner-private runtime secrets and configuration |
| `/etc/caresync/integrations.env` | optional owner-private provider credentials |
| `/etc/caresync/push-worker.enabled` | explicit push-worker activation marker |
| `/var/lib/caresync/storage` | non-public application state |
| `/var/lib/caresync/vault/family` | private family evidence |
| `/var/lib/caresync/vault/staff` | encrypted staff/transport evidence |
| `/var/lib/caresync/ocr-home` | OCR model/cache data |
| `127.0.0.1:8001` | FastAPI; never opened in UFW |
| Nginx `80/443` | public frontend, REST API, and WebSockets |

Create every state directory before the first service start and make it
`caresync:caresync` with no group/other access. The systemd unit makes the host
and release tree read-only and grants writes only to the paths above. Nginx
serves `/srv/caresync/current/frontend-redesign/dist`; no evidence directory is
ever mounted as static content.

The server needs a static `caresync` runtime account and a separate,
key-restricted `caresync-deploy` account. The deploy identity may install a
verified release and restart these two units through narrowly scoped `sudo`; it
must not receive a root login shell, database credentials, or permission to
read `/etc/caresync/backend.env`.

## Host prerequisites

- Ubuntu 24.04 with current security updates.
- PostgreSQL **17** from the PostgreSQL Apt repository. Keep PostgreSQL on
  loopback; do not open port 5432 in UFW.
- Nginx and Certbot's Nginx plugin.
- Python 3.12, pinned `uv`, `curl`, and standard archive/system utilities.
- ClamAV with fresh definitions before confidential uploads are advertised.
- Adequate RAM/swap for OCR model loading. The current 2 GiB host should have a
  bounded swap file and be observed during the first OCR proof.

CareSync preserves the database name `caresync`. Schema migration and request
traffic use different PostgreSQL identities:

- a migration owner creates/migrates the schema and applies grants;
- `caresync_basic_app` is the restricted API and push-worker identity;
- `caresync_transport_evidence_ingest` is the distinct evidence-ingest
  identity and must have a different password.

Never place the migration owner password in `backend.env`. Host provisioning
creates the empty database and terminal login identities but does not start
the application. The first verified release deployment migrates the database
to the pinned revision, applies
`backend/scripts/bootstrap_basic_runtime_role.sql`, and only then starts the
restricted API. Database migrations must finish before the `current` symlink
changes.

## Configuration

Copy `deploy/backend.env.production.example` to
`/etc/caresync/backend.env`, replace every `REPLACE_*` value, substitute the
public hostname, and set owner `root:caresync` with mode `0640`. Optional
DeepSeek, Gemini, and Expo credentials belong in
`/etc/caresync/integrations.env` with owner `root:root`, mode `0600`; the
allowlisted integration installer writes that file without exposing it to the
deploy identity.

Generate secrets on the server, not in a terminal transcript or GitHub log.
The JWT must contain at least 32 random bytes. The staff-vault key must be
URL-safe base64 encoding of exactly 32 random bytes. Back up that key through
approved offline custody: changing it without a keyring/rewrap procedure makes
existing encrypted evidence unreadable.

The intended production hostname is `caresync-app.com`. Point its `A` record at
the server before requesting the certificate and substitute it for
`__CARESYNC_HOST__` in both Nginx and `backend.env`. If permanent DNS is not
ready, a useful temporary hostname for this server is:

```text
caresync.134.209.124.182.sslip.io
```

Replace the placeholder in a copy under `/etc/nginx/sites-available/caresync`;
do not edit the template in a release. Enable the site, validate with
`nginx -t`, reload Nginx, and issue a certificate for the selected hostname:

```bash
certbot --nginx -d caresync-app.com \
  --redirect --non-interactive --agree-tos --email OPERATIONS_EMAIL
```

Replace `OPERATIONS_EMAIL` with a monitored address. Treat `sslip.io` as a
temporary DNS dependency; use an owned hostname before real family/staff data
or public launch. If `www.caresync-app.com` also resolves to the server, the
template and CORS configuration accept it and the TLS helper adds it to the
same certificate. The canonical deployment URL remains the apex origin. After
TLS is active, verify that the generated HTTPS server retains the proxy, upload
limit, cache, and security-header directives.

The SPA shell is always `no-store`; Vite's content-hashed `/assets/` files are
cached immutably. `client_max_body_size 21m` permits the application's bounded
20 MiB evidence objects plus multipart overhead. All `/api/` traffic includes
WebSocket upgrade forwarding to `127.0.0.1:8001`.

## CI/CD contract

`.github/workflows/ci-cd.yml` runs CI for pull requests and pushes and must
complete backend lint/tests plus the production frontend build. CD runs only
for a verified commit on protected `main`.
`deploy/scripts/build-release.sh` creates a deterministic archive whose root
contains `release-manifest.json`, `backend/`, `frontend-redesign/dist`, and
`deploy/`. The workflow streams that archive to the restricted SSH command:

```text
deploy <40-character-git-revision> <64-character-artifact-sha256>
```

The server receiver verifies both identifiers and the manifest before it
creates a new release directory, runs the server-side preflight/migration,
switches `current` atomically, restarts the units, and gates success on:

```text
https://<host>/api/v1/health
https://<host>/
```

Use a GitHub `production` Environment and deployment concurrency so only one
production release can mutate the host at a time. The deployment workflow
expects:

| GitHub setting | Kind | Value |
| --- | --- | --- |
| `PRODUCTION_ORIGIN` | repository variable | `https://caresync-app.com` |
| `PROD_HOST` | production-environment variable | `134.209.124.182` |
| `PROD_USER` | production-environment variable | `caresync-deploy` |
| `PROD_SSH_PRIVATE_KEY` | environment secret | dedicated deploy private key |
| `PROD_KNOWN_HOSTS` | environment secret | pinned host-key line from a trusted channel |

SSH port 22 is deliberately fixed in the workflow and firewall.
`PRODUCTION_ORIGIN` must be repository-scoped because pull-request and `main`
verification build the frontend before the deploy job enters the protected
`production` Environment. The host/user variables and both SSH secrets remain
scoped to that Environment.
Do not use `ssh-keyscan` as trust-on-first-use inside every run. Pin the host
key once after verifying its fingerprint through the provider console.
Repository/fork pull requests must never receive deployment secrets or invoke
CD. Keep application secrets on the server: database passwords, JWT/vault
keys, Expo tokens, and AI-provider keys do not belong in GitHub.

The redesigned frontend is pinned to React Router DOM 7.18.2. The npm registry
currently reports an RSC-mode CSRF advisory against that line. CareSync is a
client-only Vite SPA and does not expose React Router RSC actions, so that
specific execution path is absent; keep the pin and migrate deliberately when
a compatible fixed 7.x release or the planned Router 8 upgrade is available.

## Push delivery

The push path is fail-closed. Its service and provider have three independent
gates:

1. `PUSH_DELIVERY_ENABLED=true`;
2. `PUSH_PROVIDER=expo` and a nonempty server-only
   `EXPO_PUSH_ACCESS_TOKEN`;
3. the operator-created `/etc/caresync/push-worker.enabled` marker.

Leave the unit disabled until a staging device proves token registration,
generic notification content, provider receipts, retry/dead-letter behavior,
and revocation. Then enable it explicitly:

```bash
install -o root -g root -m 0644 /dev/null /etc/caresync/push-worker.enabled
systemctl enable --now caresync-push-worker.service
```

Removing the marker and stopping/disabling the service pauses remote delivery
without deleting the transactional outbox.

## OCR

Certificate/resume OCR stays on the server. Provision a separate virtual
environment at `/opt/caresync/ocr/.venv` from
`backend/scripts/ocr-requirements.txt`; it pins OpenCV 5, PaddleOCR, and
PyMuPDF. Keep model downloads under `/var/lib/caresync/ocr-home`, which is the
only writable cache exposed to the API sandbox. Mobile apps upload bounded
documents and receive reviewed results; they do not bundle the model.

Before enabling real onboarding, run a synthetic certificate smoke test as the
`caresync` user, confirm both OCR model families are locally available, and
measure peak memory/time. The worker has a 90-second API timeout. Failed OCR
must remain a reviewable failure; it must not silently accept an identity or
certificate.

## Verification and rollback

After every activation, verify:

```bash
systemctl is-active caresync-api.service
curl --fail --silent --show-error http://127.0.0.1:8001/api/v1/health
curl --fail --silent --show-error https://<host>/api/v1/health
curl --fail --silent --show-error https://<host>/
journalctl -u caresync-api.service --since=-10m --no-pager
```

The deploy process retains previous release directories. An application-only
rollback atomically repoints `/srv/caresync/current` to the previous verified
release, restarts the API and enabled worker, and repeats both health checks.

A symlink rollback does **not** reverse a PostgreSQL migration. It is safe only
when the previous application is explicitly compatible with the current
schema. For an incompatible migration, stop writers and use the migration's
reviewed recovery procedure and a verified pre-migration database/vault backup.
Never improvise a downgrade or restore local development data into production.
