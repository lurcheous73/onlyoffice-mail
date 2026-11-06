# Development update — 6 November 2026

This update remains a laboratory candidate. It does not deploy, capture live
data, change inbound routing or approve a production cutover.

- Fix authenticated DKIM signing authority: reject forged MIME From addresses
  while retaining legitimate delegated aliases on both submission ports.
- Restore Inbox subscription expected by the real CommunityServer ImapSync
  service. Accept and validate OO's original noncanonical base64 RSA keys
  without changing SQL signing identities or public DNS.
- Update API/worker, Rspamd and Redis runtimes; use hash-locked Python wheels
  and native Debian 13 MariaDB client packages with verified provenance.
- Convert the remaining two MyISAM candidate training tables to InnoDB through
  an explicitly enabled, backed-up upgrade of a restored copy. Keep the source
  volume and locked SQL backup intact.
- Add full stopped-candidate backup/restore, typed all-table legacy export,
  explicit noncore-table review and transactional core import into an empty
  target. Keep cached Workspace history and platform data as separate recovery
  assets requiring their own complete reconciliation.
- Enforce expiry and delivery-only flags, and make persistent queue/database/
  Redis paths explicit. Add the missing approved Workspace route for training.
- Add an isolated real-client fixture and record actual browser send/receive,
  administration, signing and exact binary attachment evidence.

Final runs passed 27 integration cases on a fresh installation and a restored/
upgraded copy, plus 29 offline checks on macOS and Linux. Current six-image
scans report zero critical findings; 74 high package findings remain in the
mail image. The baseline scan reports are retained for comparison.

Private-data recovery, full restored-client parity (including browser training
and notifications), remaining security review, a current coordinated capture
and an approved rollback/cutover sheet remain release gates. See
[qualification/README.md](qualification/README.md).
