#!/usr/bin/env bash
set -Eeuo pipefail

hostname="${1:-}"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "TLS activation must run as root." >&2
  exit 77
fi
if [[ -z "$hostname" && -s /etc/caresync/production-origin ]]; then
  hostname="$(sed -E 's#^https://##; s#/$##' /etc/caresync/production-origin)"
fi
if [[ ! "$hostname" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{2,252}$ ]]; then
  echo "Usage: sudo caresync-enable-tls [hostname]" >&2
  exit 64
fi

server_ip="$(tr -d '\n' < /etc/caresync/deploy-ip)"
email="$(tr -d '\n' < /etc/caresync/certificate-email)"
if ! getent ahostsv4 "$hostname" | awk '{print $1}' | grep -qx "$server_ip"; then
  echo "$hostname does not yet resolve to $server_ip." >&2
  exit 69
fi

domains=(-d "$hostname")
if getent ahostsv4 "www.$hostname" | awk '{print $1}' | grep -qx "$server_ip"; then
  domains+=(-d "www.$hostname")
fi

nginx -t
certbot --nginx \
  --non-interactive \
  --agree-tos \
  --email "$email" \
  --redirect \
  --keep-until-expiring \
  "${domains[@]}"
nginx -t
systemctl reload nginx
echo "TLS is active for $hostname."
