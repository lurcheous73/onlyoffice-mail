# Security and maintenance status

This candidate is restricted to an isolated lab. No clean security sign-off or production-readiness claim is made. Review the recorded reports in `qualification/` before selecting an update. A newer version label and a successful mail test are separate from a vulnerability assessment.

## Implemented controls

- Digest-pinned Debian 13/Alpine, upstream MariaDB 11.8.9 and Cisco ClamAV 1.5.4 bases; OS packages upgraded during build; actual versions and image IDs recorded after qualification.
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

The mail runtime now installs hash-verified MariaDB 11.8.9 Debian 13 packages, loading Connector/C 3.4.10 natively. The copied Ubuntu library, fallback connector package and dynamic-linker override were removed. Package metadata and the loaded version now agree. API/worker uses Python 3.14 on Alpine with exact wheel hashes and no runtime pip. Filtering uses Rspamd 4.0.1 on Alpine; Redis uses upstream 8.4.6 Alpine. The database remains upstream MariaDB 11.8.9 and antivirus remains upstream ClamAV 1.5.4.

The updated six-image scan reports **zero critical findings**. Database, API/worker, filter, Redis and antivirus each report zero high findings. The Debian mail image still reports **74 high package findings across 23 CVEs**. All six report zero secret findings. No ignore rules or vulnerability suppressions were applied. The former baseline had 307 high and five critical package findings; its original reports remain available for comparison. See the exact image IDs, package lists, scanner database metadata and raw reports in `qualification/`.

The remaining mail findings involve Debian base/runtime libraries and utilities, including Python, expat, sqlite, zlib, ncurses, util-linux and Perl archive handling. They need individual fix/reachability review. A scanner finding is not automatically exploitable through SMTP, and an unused daemon does not automatically clear its library package. No blanket not-affected classification has been applied. These findings remain a release gate.

## Source review and compatibility corrections

A completed standard Codex Security source audit covered immutable baseline `cf9a5438c08cc2967a437fc07e7ed99bb1bde298`. It identified one high-confidence, high-severity signing-authorization issue: Rspamd's custom signing callback bypassed the normal MIME/envelope mismatch checks. The update explicitly requires a single matching MIME/envelope address, with independent authenticated sender ownership enforced by Postfix. Actual tests reject forged From headers and verify legitimate delegated-alias signatures on both 587 and 465. The historical audit is not a complete source audit of the newly added migration and fixture code.

The same update corrects the two MyISAM training tables and explicit persistent runtime paths, validates expiry/delivery-only flags, and adds full synthetic backup/restore and reviewed legacy-import rehearsals. The real client trial also identified and fixed missing Inbox subscription and OO's noncanonical RSA key encoding. These functional fixes supplement the package scan; they do not establish private-data preservation or production approval.

## Repeatable update process

1. Start from the recorded source and image digests. Review upstream advisories and compatibility changes. Update `upstream.lock.json` and all relevant `FROM` references together. Recheck architecture and connector provenance.
2. Build in a new isolated project and record the actual package list, resulting image IDs and build date. Apt repositories move even when a base digest is pinned; byte-for-byte reproducibility requires a separately maintained snapshot repository.
3. Refresh signatures, run the full synthetic suite, restart/persistence test and scanner-outage test. Run offline migration-tool tests. Compare contracts when changing OO or Dovecot versions.
4. Scan every runtime image with a current vulnerability database. After installing a verified Trivy release, run `TRIVY_BIN=/path/to/trivy sh tools/scan.sh /private/new-report-directory`. It retains all reports and exits unsuccessfully for high/critical findings or secrets. Review actual runtime/package provenance. An unresolved actionable finding is a release gate; scanner silence alone is not a code/configuration audit.
5. Repeat the complete copied-data and actual OO UI rehearsal before a new deployment. Back up volumes and encryption material; never perform a database major-version upgrade in place on the only copy.
6. Prepare an operator-reviewed release and rollback sheet. Obtain site approval for live endpoint/service changes. Publish source/binaries only after licence obligations and private-data exclusion have been reviewed.

The production override is a design example, not a hardened final site configuration. It requires valid certificates, controlled OO networks/origins, real secret management, restart/monitoring policy, periodic signature refresh, backups, capacity controls and site-specific delivery/DNS checks before live operation. It exposes no API or SQL host port, but an attached OO network must still be trusted and restricted.
