#!/usr/bin/env bash
set -euo pipefail

# This is the forced command attached to the GitHub Actions deployment key.
# The key cannot request a shell, forwarding, SFTP, or any command other than
# this receiver. The release body arrives only on stdin.
original_command="${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$original_command" =~ ^deploy[[:space:]]([0-9a-f]{40})[[:space:]]([0-9a-f]{64})$ ]]; then
  echo "Rejected deployment command." >&2
  exit 64
fi

release_sha="${BASH_REMATCH[1]}"
archive_sha256="${BASH_REMATCH[2]}"
exec sudo -n /usr/local/sbin/caresync-deploy-release "$release_sha" "$archive_sha256"
