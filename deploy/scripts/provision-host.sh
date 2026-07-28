#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

hostname=""
deploy_public_key_file=""
certificate_email="info@discoverersdaycare.com"

usage() {
  echo "Usage: sudo provision-host.sh --hostname HOST --deploy-public-key-file FILE [--certificate-email EMAIL]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostname)
      hostname="${2:-}"
      shift 2
      ;;
    --deploy-public-key-file)
      deploy_public_key_file="${2:-}"
      shift 2
      ;;
    --certificate-email)
      certificate_email="${2:-}"
      shift 2
      ;;
    *)
      usage
      exit 64
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]] ||
   [[ ! "$hostname" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{2,252}$ ]] ||
   [[ ! -s "$deploy_public_key_file" ]] ||
   [[ ! "$certificate_email" =~ ^[^[:space:]@]+@[^[:space:]@]+$ ]]; then
  usage
  exit 64
fi

deploy_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
server_ip="134.209.124.182"
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  ca-certificates \
  certbot \
  clamav \
  clamav-freshclam \
  curl \
  gnupg \
  libgl1 \
  libglib2.0-0 \
  libgomp1 \
  nginx \
  openssl \
  postgresql-common \
  python3-certbot-nginx \
  python3.12 \
  python3.12-venv

install -d -m 0755 /usr/share/postgresql-common/pgdg
if [[ ! -s /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc ]]; then
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
fi
distribution_codename="$(
  . /etc/os-release
  printf '%s' "$VERSION_CODENAME"
)"
printf 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
  "$distribution_codename" \
  > /etc/apt/sources.list.d/pgdg.list
apt-get update
apt-get install -y postgresql-17 postgresql-client-17

if ! swapon --noheadings --show=NAME | grep -qx '/swapfile'; then
  if [[ ! -e /swapfile ]]; then
    fallocate -l 4G /swapfile
    chmod 0600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
fi
if ! grep -qE '^/swapfile[[:space:]]' /etc/fstab; then
  printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
fi

if ! id -u caresync >/dev/null 2>&1; then
  useradd \
    --system \
    --user-group \
    --home-dir /var/lib/caresync \
    --create-home \
    --shell /usr/sbin/nologin \
    caresync
fi
if ! id -u caresync-deploy >/dev/null 2>&1; then
  useradd \
    --system \
    --user-group \
    --home-dir /var/lib/caresync-deploy \
    --create-home \
    --shell /bin/bash \
    caresync-deploy
fi

install -d -o root -g caresync -m 0755 /srv/caresync
install -d -o root -g caresync -m 0755 /srv/caresync/releases
install -d -o caresync -g caresync -m 0700 /var/lib/caresync/storage
install -d -o caresync -g caresync -m 0700 /var/lib/caresync/vault
install -d -o caresync -g caresync -m 0700 /var/lib/caresync/vault/family
install -d -o caresync -g caresync -m 0700 /var/lib/caresync/vault/staff
install -d -o caresync -g caresync -m 0700 /var/lib/caresync/ocr-home
install -d -o root -g root -m 0700 /var/backups/caresync
install -d -o root -g root -m 0755 /opt/caresync/ocr
install -d -o root -g root -m 0755 /var/cache/caresync/uv
install -d -o root -g caresync -m 0750 /etc/caresync
install -d -o root -g root -m 0700 /etc/caresync/secrets
install -d -o root -g root -m 0755 /usr/local/lib/caresync

if [[ ! -x /opt/caresync/uv/bin/uv ]]; then
  python3.12 -m venv /opt/caresync/uv
  /opt/caresync/uv/bin/python -m pip install \
    --disable-pip-version-check \
    "uv==0.9.27"
fi
ln -sfn /opt/caresync/uv/bin/uv /usr/local/bin/uv

new_hex_secret() {
  openssl rand -hex 32
}

new_urlsafe_secret() {
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n'
}

for secret_name in app-db-password transport-db-password jwt-secret; do
  secret_path="/etc/caresync/secrets/$secret_name"
  if [[ ! -s "$secret_path" ]]; then
    new_hex_secret > "$secret_path"
    chmod 0600 "$secret_path"
  fi
done
vault_key_path="/etc/caresync/secrets/staff-vault-key"
if [[ ! -s "$vault_key_path" ]]; then
  new_urlsafe_secret > "$vault_key_path"
  printf '\n' >> "$vault_key_path"
  chmod 0600 "$vault_key_path"
fi

app_password="$(tr -d '\n' < /etc/caresync/secrets/app-db-password)"
transport_password="$(tr -d '\n' < /etc/caresync/secrets/transport-db-password)"
jwt_secret="$(tr -d '\n' < /etc/caresync/secrets/jwt-secret)"
vault_key="$(tr -d '\n' < /etc/caresync/secrets/staff-vault-key)"

systemctl enable --now postgresql
runuser -u postgres -- psql --no-psqlrc --set=ON_ERROR_STOP=1 <<'SQL'
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app') THEN
    CREATE ROLE caresync_basic_app LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname='caresync_transport_evidence_ingest'
  ) THEN
    CREATE ROLE caresync_transport_evidence_ingest LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname='caresync_transport_command_owner'
  ) THEN
    CREATE ROLE caresync_transport_command_owner NOLOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
  END IF;
END
$roles$;
ALTER ROLE caresync_basic_app LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
ALTER ROLE caresync_basic_app RESET ALL;
ALTER ROLE caresync_basic_app SET search_path = public, pg_catalog;
ALTER ROLE caresync_transport_evidence_ingest LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
ALTER ROLE caresync_transport_evidence_ingest RESET ALL;
ALTER ROLE caresync_transport_evidence_ingest SET search_path = public, pg_catalog;
ALTER ROLE caresync_transport_command_owner NOLOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS;
ALTER ROLE caresync_transport_command_owner RESET ALL;
SQL
if ! runuser -u postgres -- psql --no-psqlrc --tuples-only --no-align \
  --command="SELECT 1 FROM pg_catalog.pg_database WHERE datname='caresync'" |
  grep -qx 1; then
  runuser -u postgres -- createdb --template=template0 --encoding=UTF8 caresync
fi
{
  printf "ALTER ROLE caresync_basic_app PASSWORD '%s';\n" "$app_password"
  printf "ALTER ROLE caresync_transport_evidence_ingest PASSWORD '%s';\n" \
    "$transport_password"
  printf "REVOKE ALL ON DATABASE caresync FROM PUBLIC;\n"
  printf "GRANT CONNECT ON DATABASE caresync TO caresync_basic_app;\n"
  printf "GRANT CONNECT ON DATABASE caresync TO caresync_transport_evidence_ingest;\n"
} | runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname=postgres \
    >/dev/null

environment_tmp="$(mktemp /etc/caresync/.backend.env.XXXXXXXX)"
cat > "$environment_tmp" <<ENV
APP_NAME=CareSync
APP_VERSION=production
ENVIRONMENT=production
HOST=127.0.0.1
PORT=8001
DATABASE_TYPE=postgres
DATABASE_PATH=/var/lib/caresync/storage/caresync.db
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_NAME=caresync
DATABASE_USER=caresync_basic_app
DATABASE_PASSWORD=$app_password
TRANSPORT_EVIDENCE_INGEST_PASSWORD=$transport_password
DATABASE_SSL=false
DATABASE_READ_ONLY=false
ENABLE_ADVANCED_ROUTES=false
BILLING_MODE=shadow
JWT_SECRET=$jwt_secret
JWT_EXPIRES_IN=7d
ALLOWED_ORIGINS=https://$hostname,https://www.$hostname
FAMILY_EVIDENCE_VAULT_PATH=/var/lib/caresync/vault/family
STAFF_SCREENING_VAULT_PATH=/var/lib/caresync/vault/staff
STAFF_SCREENING_VAULT_ENCRYPTION_KEY=$vault_key
STAFF_SCREENING_VAULT_KEY_ID=production-v1
FAMILY_EVIDENCE_SCANNER_PATH=/usr/bin/clamscan
FAMILY_EVIDENCE_SCANNER_TIMEOUT_SECONDS=60
FAMILY_EVIDENCE_SCANNER_MAX_DEFINITION_AGE_HOURS=168
CARESYNC_OCR_PYTHON=/opt/caresync/ocr/.venv/bin/python
SCHEDULER_ENGINE_VERSION=v3
PUSH_DELIVERY_ENABLED=false
PUSH_PROVIDER=disabled
CARESYNC_PUSH_WORKER_POLL_SECONDS=5
ENV
chown root:caresync "$environment_tmp"
chmod 0640 "$environment_tmp"
mv -f "$environment_tmp" /etc/caresync/backend.env

if [[ ! -e /etc/caresync/integrations.env ]]; then
  install -o root -g root -m 0600 /dev/null /etc/caresync/integrations.env
fi
printf 'https://%s\n' "$hostname" > /etc/caresync/production-origin
chmod 0644 /etc/caresync/production-origin
printf '%s\n' "$server_ip" > /etc/caresync/deploy-ip
chmod 0644 /etc/caresync/deploy-ip
printf '%s\n' "$certificate_email" > /etc/caresync/certificate-email
chmod 0600 /etc/caresync/certificate-email

install -o root -g root -m 0755 \
  "$deploy_root/scripts/deploy-release.sh" \
  /usr/local/sbin/caresync-deploy-release
install -o root -g root -m 0755 \
  "$deploy_root/scripts/deploy-receive.sh" \
  /usr/local/sbin/caresync-deploy-receive
install -o root -g root -m 0755 \
  "$deploy_root/scripts/rollback-release.sh" \
  /usr/local/sbin/caresync-rollback-release
install -o root -g root -m 0755 \
  "$deploy_root/scripts/enable-tls.sh" \
  /usr/local/sbin/caresync-enable-tls
install -o root -g root -m 0755 \
  "$deploy_root/scripts/install-integration-env.py" \
  /usr/local/sbin/caresync-install-integration-env
install -o root -g root -m 0755 \
  "$deploy_root/scripts/validate-release-archive.py" \
  /usr/local/lib/caresync/validate-release-archive.py

install -o root -g root -m 0644 \
  "$deploy_root/systemd/caresync-api.service" \
  /etc/systemd/system/caresync-api.service
install -o root -g root -m 0644 \
  "$deploy_root/systemd/caresync-push-worker.service" \
  /etc/systemd/system/caresync-push-worker.service

sed \
  -e "s/__CARESYNC_HOST__/$hostname/g" \
  "$deploy_root/nginx/caresync.conf.template" \
  > /etc/nginx/sites-available/caresync.conf
chmod 0644 /etc/nginx/sites-available/caresync.conf
ln -sfn /etc/nginx/sites-available/caresync.conf \
  /etc/nginx/sites-enabled/caresync.conf

deploy_ssh="/var/lib/caresync-deploy/.ssh"
install -d -o caresync-deploy -g caresync-deploy -m 0700 "$deploy_ssh"
public_key="$(tr -d '\r\n' < "$deploy_public_key_file")"
if [[ ! "$public_key" =~ ^(ssh-ed25519|ecdsa-sha2-nistp256)[[:space:]][A-Za-z0-9+/=]+([[:space:]].*)?$ ]]; then
  echo "Deployment public key is unsupported." >&2
  exit 65
fi
printf 'restrict,command="/usr/local/sbin/caresync-deploy-receive" %s\n' "$public_key" \
  > "$deploy_ssh/authorized_keys"
chown caresync-deploy:caresync-deploy "$deploy_ssh/authorized_keys"
chmod 0600 "$deploy_ssh/authorized_keys"

cat > /etc/sudoers.d/caresync-deploy <<'SUDOERS'
caresync-deploy ALL=(root) NOPASSWD: /usr/local/sbin/caresync-deploy-release *
SUDOERS
chmod 0440 /etc/sudoers.d/caresync-deploy
visudo --check --file=/etc/sudoers.d/caresync-deploy

systemctl daemon-reload
systemctl enable caresync-api.service
systemctl disable caresync-push-worker.service 2>/dev/null || true
nginx -t
systemctl reload nginx

systemctl stop clamav-freshclam.service 2>/dev/null || true
freshclam || true
systemctl enable --now clamav-freshclam.service

if getent ahostsv4 "$hostname" | awk '{print $1}' | grep -qx "$server_ip"; then
  /usr/local/sbin/caresync-enable-tls "$hostname"
else
  echo "CareSync host provisioned. TLS is waiting for $hostname DNS to resolve to $server_ip."
fi
