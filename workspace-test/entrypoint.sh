#!/bin/bash
set -eu
export MYSQL_SERVER_PASS="$(cat /run/secrets/workspace_app)"
export ONLYOFFICE_CORE_MACHINEKEY="$(cat /run/secrets/workspace_machinekey)"
cp /run/tls/lab-ca.crt /usr/local/share/ca-certificates/oo-synthetic-lab.crt
update-ca-certificates >/dev/null
if command -v cert-sync >/dev/null; then cert-sync /etc/ssl/certs/ca-certificates.crt >/dev/null; fi
exec /app/run-community-server.sh
