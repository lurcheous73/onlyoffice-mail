# Recorded qualification — 6 November 2026

**Development candidate; production release gates remain open.** The current evidence is in [v2-workspace-20261106/](v2-workspace-20261106/). Root-level reports/results retain the earlier `cf9a543` baseline and its original findings; they are not the latest runtime. No production mail, credentials, private signing keys or copied Workspace history is included.

| Check | Recorded result |
| --- | --- |
| Final updated runtime on a full restored copy of the v1 candidate | 27/27 integration cases passed |
| Fresh installation with final images and independent empty data volumes | 27/27 passed |
| Restart of restored/upgraded candidate; message bytes and IMAP UIDVALIDITY | Passed |
| Antivirus outage produces retryable SMTP failure | Passed on preceding v2 runtime; no scanner-path change in subsequent Inbox/key-format fixes |
| Unexpected/unmarked data volume | Refused before ownership/content changes |
| Offline preservation/archive/key-format checks | 29/29 passed on macOS and Linux |
| Full stopped candidate backup/restore | Seven volumes reconciled exactly; restored runtime passed continuity check |
| Schema v1 copied-volume upgrade | Implicit upgrade refused; locked SQL backup verified; rows unchanged; all 19 tables InnoDB; source unchanged |
| Frozen MySQL 8.4 legacy import fixture | All 52 tables archived, including 18 MyISAM; 48 noncore tables explicitly retained; seven mailbox trees matched |
| Imported protocol state | Seven accounts, original message bytes, UID1/UIDVALIDITY, Seen, Archive and disabled state verified; active legacy hashes upgraded |
| Real fresh CommunityServer 12.8 browser | Domain/mailbox/password/sender/alias/group actions, draft, SMTP send, IMAP receive and exact attachment downloads passed |
| Actual OO-generated signing key | Group-delivered message signature verified against OO's original public key |
| Full restored private Workspace and complete data reconciliation | Pending |
| Browser spam-training/notification and complete feature parity | Pending; synthetic API training passes, but no browser-generated training task was observed |
| Complete source audit of the new migration/fixture code | Pending; completed baseline audit found one signing issue, now fixed/regression tested |
| Production cutover, DNS changes or real external delivery | Not performed |

The 27-case suite includes direct OO SQL/column patterns, private API authentication/version/retirement, password hash transition, SMTP 587/465/25, IMAP 993/STARTTLS, POP3S, default subscriptions, aliases/groups, binary attachments and Unicode, relay/sender restrictions, expiry and delivery-only flags, quotas, Sieve, DKIM PEM and actual OO-style RSA encoding, forged-From rejection, legitimate cross-domain aliases, spam/antivirus filtering, token revocation, repeated training, runtime isolation and restart evidence.

## Evidence and runtime versions

`v2-workspace-20261106/tests/` contains JSON records extracted from the synthetic run logs, including the real-client group-delivery/signature result. Full private backup bundles, SQLite row/file archives, SQL backups, credentials and failed import attempts remain outside this repository. Checksums of synthetic archives are evidence identifiers, not proof about any private recovery point.

| Component | Version exercised |
| --- | --- |
| Host/build guest | Debian 13 x86_64; Docker 26.1.5, Compose 2.26.1 |
| Mail runtime | Debian 13.7 packages; Postfix 3.10.13, Dovecot 2.4.1-4 |
| Database | MariaDB 11.8.9 upstream Ubuntu image |
| Native Debian Connector/C | 3.4.10 from hash-verified upstream Debian 13 packages |
| API/worker | Python 3.14, Alpine 3.23, hashed wheel dependencies |
| Filter | Rspamd 4.0.1, Alpine 3.24 |
| Redis | Upstream 8.4.6 Alpine |
| Antivirus | ClamAV 1.5.4 upstream Alpine image |
| Client trial | CommunityServer 12.8.0.1971, its Connector/NET 8.4, MySQL 8.4.0 and Elasticsearch 7.16.3 |
| Scanner | Trivy 0.76.2 |

The mail lab uses unprivileged service containers inside an outer LXC. The separate fresh Workspace browser fixture uses a dedicated KVM VM with 8 GB RAM; the legacy client container is privileged. See [WORKSPACE-TEST.md](../docs/WORKSPACE-TEST.md) for that boundary and reproduction procedure. No production mounts or published host mail ports were used.

`build.json` records six runtime image IDs and package versions, and `packages/` retains complete package inventories. Development images have not been published to an image registry. Every scanner report image ID was checked against the build record. The optional legacy Workspace fixture images are outside the six-image mail-runtime scan scope.

## Dependency release gate

Raw findings are retained without ignore rules. They are package findings, not a count of exploitable mail-service vulnerabilities.

| Image | High | Critical | Unique CVEs | Secret findings |
| --- | ---: | ---: | ---: | ---: |
| Database | 0 | 0 | 0 | 0 |
| Mail | 74 | 0 | 23 | 0 |
| API/worker | 0 | 0 | 0 | 0 |
| Filter | 0 | 0 | 0 | 0 |
| Redis | 0 | 0 | 0 | 0 |
| Antivirus | 0 | 0 | 0 | 0 |

The earlier baseline had 307 high and five critical package findings. The current scan has zero critical findings, with the mail-image high findings still open. `security-summary.json` binds the counts to report hashes/image IDs; `trivy-db-metadata.json` records the vulnerability database dates. No blanket not-affected classification was applied. The scan exits unsuccessfully while its release gate remains open. The supplied GitHub workflow has not been run on GitHub.

Promotion requires remaining security/source review, full actual-client parity, complete private-data/file reconciliation, same-version recovery, a current coordinated capture and a rollback plan preserving all trial writes. No test or script grants approval for a live change.
