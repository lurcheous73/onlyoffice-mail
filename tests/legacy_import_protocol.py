"""Read only synthetic .invalid accounts installed by the migration rehearsal."""
import hashlib
import imaplib
import json
from pathlib import Path
import ssl
import sys

sys.path.insert(0,'/opt/tests/api')
from common import connect

ctx=ssl.create_default_context(cafile='/run/tls/ca.crt')
fixture=json.loads(Path('/var/vmail/.legacy-fixture.json').read_text())
for record in fixture['mailboxes']:
    user=record['user']
    assert user.endswith(('@legacy-a.invalid','@legacy-b.invalid'))
    client=imaplib.IMAP4_SSL('mail.lab.invalid',993,ssl_context=ctx)
    try:
        if not record['active']:
            try:client.login(user,'Synthetic-Only-Password!2026')
            except imaplib.IMAP4.error:continue
            raise AssertionError('Inactive imported mailbox accepted')
        client.login(user,'Synthetic-Only-Password!2026');client.select('INBOX')
        assert client.response('UIDVALIDITY')[1][0].decode()==str(record['uidvalidity'])
        status,data=client.uid('fetch','1','(BODY.PEEK[] FLAGS)')
        assert status=='OK' and data[0] and hashlib.sha256(data[0][1]).hexdigest()==record['sha256']
        assert b'\\Seen' in data[0][0]
        assert client.select('Archive')[0]=='OK'
        status,data=client.uid('search',None,'ALL');assert status=='OK' and data[0]
        with connect() as db,db.cursor() as c:
            c.execute('SELECT password FROM mailbox WHERE username=%s',(user,))
            assert c.fetchone()['password'].startswith('{ARGON2ID}$argon2id$')
    finally:
        try:client.logout()
        except Exception:pass
print(json.dumps({'test':'MySQL8.4 to MariaDB import preserves seven accounts, message bytes, UID1, UIDVALIDITY, Seen, Archive and disabled state; successful legacy logins upgrade hashes','passed':True,'mailboxes':len(fixture['mailboxes'])}))
