# Security and maintenance status

This candidate is restricted to an isolated lab. No clean security sign-off or production-readiness claim is made. Review the recorded reports in `qualification/` before selecting an update. A newer version label and a successful mail test are separate from a vulnerability assessment.

## Implemented controls

- Digest-pinned Debian 13, upstream MariaDB 11.8.9 and Cisco ClamAV 1.5.4 bases; OS packages upgraded during build; actual versions and image IDs recorded after qualification.
- Current Postfix/Dovecot runtime replaces the old CentOS-based mail image. No systemd, privileged mail container, Docker socket or host filesystem mount is needed.
- Required TLS for password-bearing protocols; certificate validation in tests; authenticated submission, sender ownership and unauthenticated relay rejection.
- Scoped database roles; root socket administration only; private API/database/filter network; credentials excluded from access logs and source archives.
- Transitional legacy password verification followed by Argon2id upgrade. Existing weak hashes and OO's legacy password writer remain documented transition limits.
- Retain-on-removal API semantics; validated mailbox paths; no recursive mailbox deletion or automatic retention expiry.
- Exact-origin allowlist, no redirects and bounded payloads for OO spam-training fetches. Allowed OO origins and their DNS resolution must remain controlled.
- Actual DKIM verification, GTUBE rejection, EICAR rejection and retryable SMTP failure when the scanner is unavailable.
- Antivirus signatures updated through a separate explicit maintenance job; startup refuses stale/missing signatures. Configure and monitor a recurring updater before any live use.
- Runtime Compose network without a default route or published ports. The lab boundary must also be enforced outside Docker when restoring private data.

## Dependency findings as of 6 November 2026

Trivy 0.76.2 was downloaded from the official release and verified against its published checksum. High/critical raw reports are retained without ignore rules. Counts are package findings and can include multiple entries for the same CVE. A zero count is limited to the scanner database and the image actually scanned.

The initial Debian MariaDB server/connector packages were behind upstream corrective releases. The database now uses the pinned upstream 11.8.9 image, with Galera disabled. Its unused upstream Go-based `gosu` helper was removed from the runtime image; the replacement entrypoint does not call it. The recorded final database scan has zero high/critical findings.

The upstream ClamAV 1.5.4 image also has zero high/critical findings in the recorded final scan. An unused build-time Debian snakeoil TLS key was excluded from the mail image; real TLS material is mounted at runtime. All six final runtime reports have zero high/critical secret findings. These results are limited to the recorded images, scanner version and vulnerability database date.

The mail image loads upstream Connector/C 3.4.10 from that same pinned image via `/opt/oo-client`. `provenance.json` and the runtime version were checked. Debian's older connector package metadata and fallback library remain installed, so the mail image still reports MariaDB-related findings. This is a documented provenance/packaging issue to resolve, not an ignored finding or a clean image claim. All Python database connections use utf8mb4; the [Debian advisory for CVE-2026-44172](https://security-tracker.debian.org/tracker/CVE-2026-44172) describes a Big5-specific escaping issue fixed in later Connector/C releases. [MariaDB's corrective-release notice](https://mariadb.org/mariadb-community-server-corrective-releases/) covers the separate Galera issues addressed by the newer server baseline.

Other images still contain high/critical findings. The initial Debian antivirus packages reported known parser vulnerabilities; they were replaced with [Cisco's upstream ClamAV 1.5.4](https://github.com/Cisco-Talos/clamav/releases/tag/clamav-1.5.4), which includes newer parsing fixes. The remaining Debian filter image is flagged for libxml2 CVE-2026-6653. [Debian's tracker](https://security-tracker.debian.org/tracker/CVE-2026-6653) lists the current trixie package as vulnerable and classifies it as a minor issue without a DSA; Trivy's severity is critical. Reachability through the linked archive/XML libraries has not been established. Keep the finding open and obtain a reviewed fix or an evidence-backed disposition before release; do not silently suppress the severity difference. Additional base-package findings are retained in the raw reports and need review too.

## Repeatable update process

1. Start from the recorded source and image digests. Review upstream advisories and compatibility changes. Update `upstream.lock.json` and all relevant `FROM` references together. Recheck architecture and connector provenance.
2. Build in a new isolated project and record the actual package list, resulting image IDs and build date. Apt repositories move even when a base digest is pinned; byte-for-byte reproducibility requires a separately maintained snapshot repository.
3. Refresh signatures, run the full synthetic suite, restart/persistence test and scanner-outage test. Run offline migration-tool tests. Compare contracts when changing OO or Dovecot versions.
4. Scan every runtime image with a current vulnerability database. After installing a verified Trivy release, run `TRIVY_BIN=/path/to/trivy sh tools/scan.sh /private/new-report-directory`. It retains all reports and exits unsuccessfully for high/critical findings or secrets. Review actual runtime/package provenance. An unresolved actionable finding is a release gate; scanner silence alone is not a code/configuration audit.
5. Repeat the complete copied-data and actual OO UI rehearsal before a new deployment. Back up volumes and encryption material; never perform a database major-version upgrade in place on the only copy.
6. Prepare an operator-reviewed release and rollback sheet. Obtain site approval for live endpoint/service changes. Publish source/binaries only after licence obligations and private-data exclusion have been reviewed.

The production override is a design example, not a hardened final site configuration. It requires valid certificates, controlled OO networks/origins, real secret management, restart/monitoring policy, periodic signature refresh, backups, capacity controls and site-specific delivery/DNS checks before live operation. It exposes no API or SQL host port, but an attached OO network must still be trusted and restricted.
