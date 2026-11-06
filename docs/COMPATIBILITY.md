# CommunityServer integration contract

Baseline: CommunityServer commit `fe1fa7babd093969e939ba6ff45a9fee1299dc93` and the old Docker-MailServer commit in `upstream.lock.json`. The source review covers OO 12.8; other OO releases need their own contract comparison and tests.

## Direct SQL is part of the interface

CommunityServer's `ASC.Mail.Server` engine and DAOs write directly to `domain`, `mailbox`, `alias` and `dkim`. Creating a new mailbox involves an OO-generated storage path, a password hash and a self-alias. Alias groups use comma-separated destinations. OO changes mailbox passwords through SQL as well as invoking the private HTTP API.

The required column names were extracted into [oo-sql-contract.json](oo-sql-contract.json). Tests check every referenced column and reproduce the relevant `REPLACE`/`UPDATE` patterns. Table names, identifiers, quota units and path semantics are retained. All compatibility tables use InnoDB in this candidate.

OO's database login is `oo_admin`, restricted to the four integration tables. Separate mail-reader, password-adapter and API logins have narrower grants. No remote database root account is created. The database accepts connections only through Docker networks unless an operator changes the supplied configuration.

This schema is not interchangeable with the current iRedMail `vmail` schema. Do not point OO at a stock iRedMail database or run a current iRedMail schema upgrade over this compatibility database.

## Password handling

OO 12.8 writes MD5-CRYPT hashes. The PAM adapter verifies supported legacy hashes with libxcrypt and upgrades a successful login to Argon2id, using a compare-and-swap SQL update to avoid overwriting a concurrent password change. Invalid passwords and inactive accounts are rejected. TLS is required for mailbox authentication and submission.

The adapter accepts existing Argon2id and the explicitly listed CRYPT families in `mail/auth.py`. Other hash families require a reviewed mapping before import. Legacy hashes remain until a successful login; this is a transition, not immediate removal of every weak stored hash. An OO password change still writes its legacy format, which upgrades again at the next successful login. A later optional OO patch could change that writer without changing the mail interface.

## Private HTTP API

The API listens on port 8081 inside Docker. OO's `auth_token` query parameter and the `Auth-Token` header are accepted. Query credentials are retained for compatibility; do not expose the API publicly or enable URL access logging at a proxy.

| Route | Candidate behaviour |
| --- | --- |
| `GET /api/v1/version[.json]` | `global_vars.value` version response |
| `GET /api/v1/domains`, domain/mailbox lookup routes | Legacy envelope names; mailbox password fields excluded |
| `DELETE /api/v1/domains/<domain>` | Validate mailbox paths, then retire their data directories |
| `DELETE /api/v1/domains/<domain>/mailboxes/<local>` | Atomically move the mailbox directory into `.retired` on the same volume |
| `POST /api/v1/spam/training[.json]` | Queue an allowed OO message URL; bounded fetch and actual Rspamd learning |
| API-key routes | Creation, metadata lookup/update, revocation; list does not reveal tokens |
| Training task lookup | Extension for observing queued/completed/failed tasks |

OO performs its normal SQL removal after the cleanup call. The API does not duplicate that SQL deletion. Retired mail is retained with a receipt; no automatic purge is implemented. Domain retirement is prevalidated but is not a single atomic operation across all directories. It still requires OO's normal administrative coordination.

The worker reads OO's DKIM SQL records and publishes a per-domain signing map. Synthetic signatures are cryptographically verified in tests. Public DNS records and external reputation are not tested by this internal lab.

## Mail protocols and deliberate limits

Submission uses 587 with STARTTLS or 465 with implicit TLS, with authenticated sender ownership checks. IMAP supports 993 and 143 with required TLS. POP3 uses 995; ManageSieve uses 4190 with TLS. Port 25 accepts valid local recipients and rejects unauthenticated relay. LMTP remains inside the mail container.

The preserved data path is `/var/vmail/<storagenode>/<maildir>/Maildir`. Active Sieve scripts, subscriptions, Dovecot UID state, Maildir flags and timestamps belong to the copied mailbox tree. Do not rebuild empty mailboxes and repopulate only message bodies if UID continuity is required.

The current test suite covers OO's SQL/API contract and real protocol clients. **It has not run an actual restored OO browser session.** OO-specific folders/tags, contacts, signatures, cached-only messages, CRM links and all UI administration flows require that separate trial.

Advanced historical iRedMail features such as backup-MX transports, domain aliases, BCC policies, administrator sharing and Amavis policy tables are not fully implemented merely because some legacy columns/tables remain. Inventory their use and reject unsupported non-default settings during a migration review. IPv6, multi-architecture builds, high availability and a public administration interface are outside this candidate's tested scope.
