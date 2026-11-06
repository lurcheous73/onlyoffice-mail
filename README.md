# OO-compatible mail backend for Docker

An independent replacement candidate for the old ONLYOFFICE MailServer runtime, designed for a Debian 13 Docker host while retaining CommunityServer 12.8's mail integration. The Workspace interface remains in CommunityServer.

**Status: working isolated lab candidate; not approved for live mail.** Real CommunityServer 12.8 browser testing now covers domain/mailbox creation, password and alias changes, sending, receiving and exact attachment downloads. Synthetic legacy import, full candidate backup/restore and copied-database upgrades have passed. A complete restored Workspace trial, private-data reconciliation and remaining security findings are still release gates. See [qualification/README.md](qualification/README.md).

The current iRedMail 1.8.9 source is a reference for the maintained mail stack. This project implements an OO-compatible schema and configuration rather than running the iRedMail installer. Matching field names alone does not prove compatibility: protocol, administration, persistence and data-reconciliation tests are required.

## Components

| Service | Implementation |
| --- | --- |
| Mail delivery and submission | Postfix on Debian 13, TLS and authenticated submission |
| Mailbox access | Dovecot 2.4, Maildir, SQL user database and PAM password adapter |
| Compatibility database | MariaDB 11.8.9, OO legacy fields retained, InnoDB tables |
| Private OO API and worker | Python, Flask/Waitress; version, retirement, DKIM and spam-training integration |
| Filtering | Rspamd, Redis and upstream ClamAV 1.5.4; retryable failure if scanning is unavailable |
| Qualification | Synthetic SQL/API/protocol tests and recovery checks |

The MariaDB container uses its upstream Ubuntu-based image. Mail uses Debian 13 with native upstream Debian packages for Connector/C 3.4.10; no fallback library or dynamic-linker override is installed. API/worker, filter and Redis use pinned Alpine bases; antivirus uses Cisco's upstream Alpine-based image. The deployment host is Debian 13. Exact source commits and base-image digests are in [upstream.lock.json](upstream.lock.json); recorded package versions are in `qualification/`.

## Run a fresh synthetic lab

Use a dedicated disposable Linux VM with Docker Engine, Compose v2, Python 3 and OpenSSL. This build was exercised on Linux x86_64. The native client package and hashed Python wheel locks currently support x86_64 builds. Allow at least 4 GB RAM for the guest; 6 GB is preferable while building/scanning, plus 20 GB free disk. Mail and application backup space is additional.

From a fresh checkout:

```sh
python3 tools/prepare.py
docker compose -f compose.json build
docker compose -f compose.json --profile maintenance run --rm signature-update
docker compose -f compose.json up -d
sh tools/test.sh
```

The first command creates unique service credentials and a 30-day private test CA. It refuses to replace existing `.state`. Keep that directory private and outside source control. File secrets are read-only bind mounts; their parent directory is private. Compose file secrets are not an encrypted secret store.

The signature updater contacts ClamAV's database service using a separate maintenance network. It has the signature volume and no mail/database credentials. The runtime network is internal, publishes no ports and has no default route. The antivirus daemon refuses to start without a recent signature database. Repeat the explicit update job regularly when using a persistent lab; a scheduler is not installed by this package.

Tests use only newly created `.invalid` addresses, a synthetic password, and a local OO message fixture. They write dummy accounts, mail, DKIM keys and training records into this lab. `--use-aliases` in the test helper is required for the fixture hostname. Never run the test profile against imported private mail or a production override.

To stop the lab while keeping every volume:

```sh
docker compose -f compose.json stop
```

Restart with `up -d`. No cleanup, volume pruning or deletion is part of the runbook. To repeat from empty storage, use a new project name and fresh state in a separate checkout; keep previous attempts for comparison.

## Recovery checks

After a passing full suite, verify the saved message and IMAP UIDVALIDITY after restarting the lab:

```sh
docker compose -f compose.json restart
docker compose -f compose.json run --rm --use-aliases tests python3 persistence.py
```

The scanner-outage test is deliberately disruptive to this synthetic lab only:

```sh
docker compose -f compose.json stop clamav
docker compose -f compose.json run --rm --no-deps tests python3 scanner_failure.py
docker compose -f compose.json up -d clamav
```

Always restore the antivirus service after that test, including if the test fails. This verifies an SMTP temporary failure; it is not permission to interrupt live inbound mail.

## Integration and migration

Read [the compatibility contract](docs/COMPATIBILITY.md), [migration mapping and approval gates](docs/MIGRATION.md), and [security/update requirements](docs/SECURITY.md). The compatibility database is created only on a fresh marked volume. An unmarked existing mail database is refused. Secrets are established on initialisation; editing secret files does not rotate existing database accounts.

The [synthetic Workspace browser fixture](docs/WORKSPACE-TEST.md) requires a separate KVM VM with 8 GB RAM. It uses upstream legacy client images and fresh `.invalid` data. It is separate from a private recovery copy and must never be attached to live mail.

`compose.production.example.json` illustrates the reviewed network and certificate inputs a later deployment would need. It is **not a cutover script**. It must not be combined with a live project, original data volume or running OO client before backup recovery, migration reconciliation, security review and owner approval. Existing Workspace cached messages and attachments live separately from backend Maildir and must be preserved in full.

No production data, certificates, credentials, addresses or site-specific changes are included here. [NOTICE](NOTICE) describes source attribution and redistribution limits. The manual GitHub workflow runs a synthetic lab only; it does not publish or deploy images.
