# Recorded lab qualification — 6 November 2026

**Working development candidate; production release gates remain open.** Evidence here contains synthetic tests and build metadata. It contains no production mail, account credentials, private site configuration or copied Workspace data.

| Check | Result |
| --- | --- |
| Existing synthetic mail lab, final runtime images | 23/23 integration cases passed |
| Fresh installation with final images and empty independent data volumes | 23/23 integration cases passed |
| Restart, message SHA-256 and IMAP UIDVALIDITY | Passed |
| Antivirus outage, retryable SMTP response | Passed |
| Unexpected existing database volume rejected before content/ownership changes | Passed |
| Offline backup/file preservation tests | 19/19 passed on macOS and Linux |
| Actual restored ONLYOFFICE browser trial | Pending |
| Complete private-data migration and reconciliation | Pending |
| Reviewed vulnerability/configuration/code assessment | Pending |
| Approved production cutover or live external delivery | Not performed |

The final fresh suite includes OO column/SQL patterns, API authentication/version/retirement, weak-hash login upgrade, disabled/wrong-password rejection, SMTP 587 and 465, local inbound SMTP 25, IMAP 993/STARTTLS, POP3S, aliases/groups, attachments/UTF-8, relay and sender restrictions, quotas, ManageSieve delivery, verified DKIM, spam/antivirus rejection, token revocation, repeated training and network isolation. SMTP destinations are synthetic `.invalid` addresses inside the lab. This does not demonstrate public DNS, sender reputation or real external delivery.

`results.json` records the two full runs, recovery tests and data-volume refusal. `offline-tests.txt` records the independent preservation tests. These are test evidence, not proof that any real backup is complete or restorable.

## Versions actually exercised

| Component | Recorded version |
| --- | --- |
| Mail/API/filter base | Debian 13.7 packages, digest-pinned Debian 13 base |
| Postfix | 3.10.13 |
| Dovecot | 2.4.1-4 |
| MariaDB | 11.8.9, upstream Ubuntu 24.04 image |
| Loaded MariaDB Connector/C | 3.4.10 |
| Rspamd | 3.12.1 |
| ClamAV | 1.5.4, upstream Alpine-based image |
| Redis | 8.0.2 |
| Vulnerability scanner | Trivy 0.76.2 |

`build.json` contains the six runtime image IDs, build times, architecture and component output. `packages/` contains complete installed package lists. Local image IDs are recorded because these development images were not pushed to a registry and have no registry digest. The scanner report image IDs were checked against this build record before export.

Runtime qualification used a dedicated Debian 13 x86_64 guest with Docker 26.1.5 and Compose 2.26.1. The outer build guest was an LXC; individual mail-service containers were not privileged. No production volumes or published host mail ports were used. `tools/record_build.py` can record a new set of local candidate image IDs, versions and package lists without mounting mail or credentials.

## Dependency scan release gate

These are raw package findings, not counts of exploitable service vulnerabilities. No ignore rules were applied, and no high/critical secret findings remain in these images.

| Runtime image | High findings | Critical findings | Unique CVEs |
| --- | ---: | ---: | ---: |
| Database | 0 | 0 | 0 |
| Antivirus | 0 | 0 | 0 |
| Mail | 96 | 4 | 36 |
| API/worker | 78 | 0 | 27 |
| Filter | 83 | 1 | 30 |
| Redis | 50 | 0 | 14 |

`scans/` retains the full reports; `security-summary.json` contains counts and their SHA-256 values. `trivy-db-metadata.json` records the scanner database dates. Review [SECURITY.md](../docs/SECURITY.md) for the patched connector/provenance issue, the remaining libxml2 finding and update procedure. The scan exits unsuccessfully by design until the release gate is resolved. The GitHub workflow has been supplied but has not been run on GitHub.

Production promotion requires independently clearing dependency/code/configuration review, actual OO client/administration parity, complete copied-data reconciliation, backup recovery and rollback preservation. No script in this package grants approval for a live change.
