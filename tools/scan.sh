#!/bin/sh
# Scan local candidate images; retain findings and fail for high/critical
# vulnerabilities or secrets. Install Trivy from a verified upstream release.
set -eu
cd "$(dirname "$0")/.."
report_dir=${1:?Supply a NEW private report directory}
scanner_bin=${TRIVY_BIN:-trivy}
mkdir -m 700 "$report_dir"
status=0
for service in database mail api filter antivirus redis; do
    "$scanner_bin" image --scanners vuln,secret --severity HIGH,CRITICAL \
        --format json --exit-code 1 --output "$report_dir/$service.json" \
        "oo-mailserver-$service:dev" || status=1
done
exit "$status"
