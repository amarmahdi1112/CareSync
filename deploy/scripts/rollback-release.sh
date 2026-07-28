#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

target_sha="${1:-}"
recovery_set="${2:-}"
if [[ "$(id -u)" -ne 0 ]] || [[ ! "$target_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: sudo caresync-rollback-release <git-sha> [recovery-set-directory]" >&2
  exit 64
fi

target="/srv/caresync/releases/$target_sha"
current="/srv/caresync/current"
if [[ ! -f "$target/release-manifest.json" ||
      ! -x "$target/backend/.venv/bin/uvicorn" ]]; then
  echo "The requested CareSync release is not installed." >&2
  exit 66
fi

exec 9>/run/lock/caresync-deploy.lock
flock -n 9 || {
  echo "Another CareSync deployment is active." >&2
  exit 75
}

systemctl stop caresync-push-worker.service caresync-api.service 2>/dev/null || true

if [[ -n "$recovery_set" ]]; then
  recovery_set="$(readlink -f "$recovery_set")"
  case "$recovery_set" in
    /var/backups/caresync/*) ;;
    *)
      echo "Recovery set must be inside /var/backups/caresync." >&2
      exit 64
      ;;
  esac
  (
    cd "$recovery_set"
    sha256sum --check SHA256SUMS
  )
  runuser -u postgres -- dropdb --if-exists --force caresync
  runuser -u postgres -- createdb --template=template0 --encoding=UTF8 caresync
  runuser -u postgres -- pg_restore \
    --exit-on-error \
    --no-owner \
    --role=postgres \
    --dbname=caresync \
    < "$recovery_set/database.dump"
  rm -rf /var/lib/caresync/vault/family /var/lib/caresync/vault/staff
  tar -C /var/lib/caresync/vault -xzf "$recovery_set/private-vaults.tar.gz"
  chown -R caresync:caresync /var/lib/caresync/vault
  chmod -R go-rwx /var/lib/caresync/vault
fi

runuser -u postgres -- psql \
  --no-psqlrc \
  --set=ON_ERROR_STOP=1 \
  --dbname=caresync \
  --file="$target/backend/scripts/bootstrap_basic_runtime_role.sql" \
  >/dev/null

app_password="$(tr -d '\n' < /etc/caresync/secrets/app-db-password)"
transport_password="$(tr -d '\n' < /etc/caresync/secrets/transport-db-password)"
{
  printf "ALTER ROLE caresync_basic_app PASSWORD '%s';\n" "$app_password"
  printf "ALTER ROLE caresync_transport_evidence_ingest PASSWORD '%s';\n" \
    "$transport_password"
} | runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname=caresync \
    >/dev/null

ln -sfn "$target" "$current.next"
mv -Tf "$current.next" "$current"
systemctl restart caresync-api.service
curl --fail --silent --show-error --retry 30 --retry-delay 2 \
  http://127.0.0.1:8001/api/v1/health >/dev/null
echo "CareSync rolled back to $target_sha."
