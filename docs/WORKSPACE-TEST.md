# Fresh synthetic Workspace browser trial

This fixture tests the real CommunityServer 12.8 client against the candidate.
It is not a private-data restore or a production deployment. All mail addresses
use `.invalid`. The legacy client requires a privileged container and host
cgroups, so the preparation tools require a separate KVM VM named `*-lab`.
Do not run this profile on a production Docker host or an LXC sharing its host's
service manager. The mail backend containers themselves are not privileged.

Use Debian 13 x86_64, 8 GB RAM, four CPUs, a CPU model supporting x86-64-v2,
2 GB swap and at least 40 GB free disk. The pinned MySQL 8.4 client fixture
requires that CPU support. Lower client memory limits caused Mono processes
to be killed during the recorded trial. The profile limits Workspace to 4 GB
RAM/6 GB RAM-plus-swap and Elasticsearch to 1.5 GB/2 GB.

## Prepare a new fixture

In a fresh checkout on the dedicated VM, as root:

```sh
python3 tools/prepare.py
python3 tools/prepare_workspace_test.py --hostname "$(hostname)"
docker compose -p oo-mail-ui -f compose.json -f compose.workspace-test.json build
docker build -f workspace-test/Dockerfile.dns -t oo-mailserver-workspace-dns-fixture:dev .
docker compose -p oo-mail-ui -f compose.json -f compose.workspace-test.json --profile maintenance run --rm signature-update
docker compose -p oo-mail-ui -f compose.json -f compose.workspace-test.json up -d --wait
```

The helpers refuse existing `.state`/`.workspace-test` and create unique lab
credentials. Keep both directories private. The upstream Workspace, MySQL and
Elasticsearch fixture image digests are pinned in `compose.workspace-test.json`.
Building the fixture downloads those images; their binaries are not included in
this repository. They are legacy test dependencies and are not covered by the
six-image mail-runtime security summary.

The fixture patches two upstream bootstrap `mysqladmin shutdown` calls to target
the container's unused local database explicitly. Unqualified upstream calls
otherwise inherited the external database connection settings. It also disables
shell tracing and token echoes. An empty portal database is initialized through
a separate generated application login. No live credential or application data
is supplied. The real bundled Connector/NET 8.4 driver was tested against the
candidate MariaDB in both utf8 and utf8mb4 modes.

## Reach the portal inside the isolated VM

There are no published host ports or external SMTP routes. Run the browser
inside the VM. Add `workspace.lab.invalid` to that VM's `/etc/hosts`, using the
Workspace container's address on `oo-mail-ui_private`, obtained from
`docker inspect oo-mail-ui-workspace-1`. Refresh this mapping if it changes.
Open `http://workspace.lab.invalid/` and complete the empty-portal wizard with
a synthetic administrator and a fresh test password. Do not subscribe it to
external services. The recorded browser blocked every third-party origin.

Register the fresh backend metadata:

```sh
python3 tools/register_workspace_test.py --hostname "$(hostname)" --project oo-mail-ui
```

Registration refuses existing mail servers/mailboxes. It supplies the private
API, scoped SQL login, IMAP 143 STARTTLS and submission 587 STARTTLS. It avoids
the old combined mail/API-host port-25 bootstrap probe. Open Mail Server
administration and start the domain wizard with `webmail.invalid`.

The isolated client needs authoritative synthetic DNS for its domain checks.
After the wizard has allocated its `mail_server_dns` row, determine that row's
ID locally (IDs and public DNS fields only; never print connection strings).
Before completing the domain wizard, run:

```sh
python3 tools/prepare_workspace_test_dns.py --hostname "$(hostname)" --project oo-mail-ui --domain webmail.invalid --dns-id 1
```

Replace `1` with the actual allocated row ID. This helper reads only that row's
public MX/SPF/DKIM/ownership fields, creates a private DNS sidecar, probes its MX
answer and updates only the fixture container's resolver/hosts files. Original
fixture resolver files and failed attempts are retained. No public DNS is changed.
Re-run it after recreating service containers because their IPs can change.

## Browser checks and evidence limits

Create a domain and mailbox, change its password, edit its sender name, add an
alias and create a mail group. Compose a draft containing Unicode text and a
known binary attachment. Send through the alias/group, retrieve it through
Inbox, and download the sent/received attachments to compare their exact bytes.
Verify the delivered DKIM signature against OO's original public key. The
recorded trial passed these checks using the actual Workspace UI and daemons.

This trial found two backend omissions that are now regression tested:
Inbox must be auto-subscribed for OO ImapSync, and OO's base64/noncanonical RSA
key encoding must be normalized only in the published signing copy. No source
database key or public DNS record is rewritten to make these checks pass.

Full restored-history, cached external accounts, contacts, signatures, tags,
search, rules, CRM links, calendar integration and all administration flows
remain separate release checks. Browser spam-training and notification parity
also need explicit evidence; passing the synthetic API training test alone does
not prove those browser paths.

Stop with `docker compose -p oo-mail-ui -f compose.json -f compose.workspace-test.json stop`.
Keep volumes, private state, DNS sidecars and failed attempts. No cleanup or
volume-deletion command is included.
