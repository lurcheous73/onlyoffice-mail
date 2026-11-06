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
