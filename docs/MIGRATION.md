# Preservation, mapping and migration rehearsal

This package does not contact, stop, reconfigure or import from a live server. A real capture, service interruption, endpoint change, DNS change and final cutover each require the owner's confirmation. Do not attach original production volumes to this stack.

## Required recovery point

Keep a complete immutable platform backup, then prove a same-version restore on independent storage. Preserve the entire Workspace database and data root as well as backend mail. Workspace may retain messages from disabled or external accounts that do not exist on the local mail server.

Capture the two databases, CommunityServer data including `.private/machinekey`, Maildir, configuration, certificates, queues, container writable-layer customisations and externally mounted storage at one coordinated recovery point. A listed backup is not evidence of successful recovery. Non-transactional MyISAM tables require a coordinated freeze/snapshot or an equivalent tested method; `--single-transaction` alone does not cover them.

The portable verifier/unpacker from the companion Workspace project is included in `migration/backup_bundle.py`. It accepts the documented OO 12.8.0.1971/MySQL 8.4.0 baseline and verifies exact artifact hashes before unpacking into a fresh marked lab directory. See `migration/manifest.example.json`. It refuses overwrites, links and special archive entries. Original full backups remain necessary for ACLs, xattrs, hardlinks and other filesystem state. Sieve/certificate symlinks need a separately reviewed copy procedure; do not silently drop them.

## Source-to-target mapping

| Source state | Target and preservation rule | Required evidence |
| --- | --- | --- |
| Complete `onlyoffice` database | Same-version isolated Workspace clone, preserving every tenant/user/mailbox/message ID and relationship | All table counts, message counts by account/folder/removed state and dependency checks |
| CommunityServer data and encryption material | Complete independent data copy; original machine key retained privately | Every file hash; successful decryption and old-message/attachment access |
| Workspace cached external/disabled accounts | Preserve their original records and payloads; do not map them to invented local mailboxes | Separate cached-account reconciliation, including disabled records |
| Backend `domain` | Same domain identity, status, dates, quota metadata and supported transport semantics | Exact rows and inactive state; review unsupported non-default settings |
| Backend `mailbox` | Same username, flags, quota in MiB, legacy hash, `/var/vmail` root, storage node and dated maildir | Explicit account mapping, no normalisation collisions, path and hash-family validation |
| Backend `alias` | Same address, destination list, domain, active/islist state | Self-aliases, multi-recipient groups, loops, external destinations and catchalls reviewed |
| Backend `dkim` | Same domain, selector and keys, kept private | Sign and verify against the existing public key; no DNS changes during lab trial |
| Maildir and per-user Sieve tree | Exact copy into a fresh target mail volume; UID/GID adjusted only on the copy after recording the change | Bodies/attachments hash identically; filenames, flags, times, subscriptions, UIDVALIDITY and UIDs reconcile |
| `used_quota` and disposable indexes | Preserve originals for recovery; recalculate only the clone's derived usage/indexes after baseline comparison | No quota-unit conversion error; no change to mail content |
| API tokens and service logins | Newly generated scoped service credentials; private OO clone reconfigured to them | Expiry/revocation tests; never publish original keys |
| Remaining legacy backend tables | Retain the entire original database; individually classify policies, history and unsupported features | No unknown table silently discarded or claimed to have been translated |
| Mail delivery queue | Preserve original spool and recovery notes; keep it offline | Explicit queue IDs/disposition; no blind queue replay or duplicate delivery |
| Site-specific UI/config changes | Preserve privately and compare to pinned source | Approved features ported deliberately, licence/provenance reviewed |

This is the mapping contract. **A general automatic conversion of all legacy backend tables is not implemented.** Do not feed a MySQL 8 application dump or old database directory directly into MariaDB 11.8. First restore the original engine/version in the isolated recovery clone, export reviewed logical records, then load only into a new target schema with an explicit field map. Keep the whole source database recoverable. MySQL system tables/users, old definers and authentication plugins must not be imported into this candidate.

## Implemented logical import

`migration/backend_records.py` exports a frozen, network-isolated MySQL 8.4 **copy** through a SELECT-only `migration_reader` account at the fixed `legacy-copy` alias. It requires read-only and super-read-only modes with scheduled events disabled. It archives every base table's DDL, columns and typed rows in private SQLite, including binary values, decimals, zero dates and microsecond timestamps. Source SQL DDL is data; it is never executed on the target.

The `inventory` action produces a review policy. Each noncore table needs an explicit `archive_only` decision bound to its row count and digest; used unsupported feature tables are refused. The `plan` action checks identities, supported policies/hash families, exact copied file manifests and real mailbox directories. It refuses unknown columns, missing accounts or a populated target. The `apply` action requires the reviewed plan digest, writes the four core tables in one transaction, rejects conversion warnings and compares every imported row before commit. A private receipt records the outcome. A repeat import is refused. The other tables remain losslessly recoverable in the original database and archive; this does not implement their historical features.

Run `python3 migration/backend_records.py --help` in the prepared migration image for the actions and required paths. Keep all archives, policies, plans and file manifests private. The source and target must have no default IPv4/IPv6 route. Mount the copied mail tree read-only while planning/importing. Never use this tool to freeze or capture live databases.

`tools/rehearse_legacy_import.py` demonstrates the procedure using a newly generated 52-table MySQL 8.4 fixture with 18 MyISAM tables, seven accounts, two domains and retained UID/Sieve state. This is synthetic evidence; it does not establish real-data completeness.

## Candidate recovery and schema upgrades

All 19 current candidate tables use InnoDB. Schema v1 accidentally retained two MyISAM training tables. A v1 volume is refused before ownership or contents change unless `OO_UPGRADE_RESTORED_COPY=yes` is explicitly set on an independent restored copy. The upgrade first retains a locked full SQL backup and SHA-256 receipt inside the copied volume, converts the two tables and then writes the v2 marker. Existing v1 markers and backup files remain. Never enable this flag on the original volume.

`tools/rehearse_schema_upgrade.py` proves the refusal, backed-up conversion, exact logical row preservation, restart idempotence and unchanged original source. `tools/rehearse_backup.py` backs up an already stopped synthetic candidate and restores seven volumes plus private configuration into new names. It records all file bytes, paths, safe links, ownership, modes and nanosecond modification times, pins the saved image IDs and refuses existing destinations. It does not stop a service or grant permission to operate on production. Private backup bundles contain credentials and signing keys.

The file verifier remains strict by default. The synthetic backup harness may explicitly record and exclude named Postfix Unix sockets and the historical Rspamd Unix socket; they contain no message payload. Unknown sockets and special entries are refused. Ordinary files with those names are still hashed. No queue message or Maildir file is excluded by these exceptions.

## Rehearsal order

1. Restore the complete original backup to an independent isolated machine. Remove inherited live networks, mounts, jobs and callbacks before booting it. Preserve the original backup and the failed attempts.
2. Establish the same-version baseline. Reconcile every database table and file manifest before intentional transformations. Use the verifier without `--apply` first. Do not start two aggregators against live mailboxes.
3. Export the legacy mail schema, row counts and account paths from that offline clone. Classify all tables and all non-default policies. Prepare the versioned field map; reject unsupported features rather than ignoring them.
4. Initialise a separate empty target volume with this candidate. Copy reviewed records and the complete mailbox tree into that independent volume, with daemons stopped. Original data stays read-only. Record every ownership/path change. Do not overwrite a previously attempted import.
5. Use `migration/file_audit.py` to hash stable offline trees before and after copying. It writes a new SQLite manifest outside the source tree, records regular files/directories/safe internal symlinks, and refuses special entries and escaping links. Run comparison before daemons can rewrite indexes. Treat manifests as private because paths can reveal addresses.
6. Repoint only the restored Workspace clone to the target private SQL/API/IMAP/SMTP endpoints. Disable external notifications, account polling and sending through host-level isolation. Import no original queue into an internet-connected test machine.
7. Exercise the actual OO browser: domain/mailbox/alias/group creation and changes, password changes, signing, training, inbox/sent/drafts, custom folders, flags, tags, contacts, signatures, rules, search, inline images, calendar invitations, CRM links and the oldest cached messages. Reconcile all counts and hashes; samples supplement full reconciliation.
8. Restart the entire candidate and restore it again from its own backup. Verify UID continuity, no duplicate downloads, all attachments, and a rollback rehearsal that preserves messages written during the trial.

Example offline file reconciliation:

```sh
python3 migration/file_audit.py capture /offline/source-mail /private/source-mail.sqlite
python3 migration/file_audit.py capture /offline/copied-mail /private/copied-mail.sqlite
python3 migration/file_audit.py compare /private/source-mail.sqlite /private/copied-mail.sqlite
```

Use `--ignore-ownership` only for a separately recorded, approved UID/GID translation on a copy. Modes, nanosecond modification times, symlink targets, paths and file bytes still must match. The file audit is not a database verifier and cannot turn a changing live tree into a coherent backup.

## Short switchover test and rollback

Prepare a change sheet with exact hosts, IP/port bindings, backup capture ID, independent storage, endpoint differences, inbound handling, service stop/start order, controlled sender/recipient addresses, maximum test duration and rollback triggers. Obtain approval for that concrete sheet before any live change.

Pausing inbound SMTP alone does not freeze OO polling, sent mail, drafts, database changes or a mail queue. Stopping the old mail container and bringing up an empty new one is not a preservation test. Use copied state, coordinate writers and final deltas, and keep the old container and volumes intact. Public senders may retry a temporary SMTP failure, but retry duration is sender-dependent; a short pause is not a guarantee that every sender will keep mail indefinitely.

Only one backend should accept live writes at a time. If the candidate accepts new messages or mailbox changes, collect and reconcile those writes before rollback; restarting the old container alone would strand them. Do not change MX records, delete/prune any source volume or remove backups as part of a test. Release only after security, actual OO compatibility, full data reconciliation and rollback all pass independently.
