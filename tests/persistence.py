import hashlib
import imaplib
import json
from pathlib import Path
import ssl
state=json.loads(Path('/var/vmail/.qualification/persistence.json').read_text())
ctx=ssl.create_default_context(cafile='/run/tls/ca.crt')
with imaplib.IMAP4_SSL('mail.lab.invalid',993,ssl_context=ctx) as c:
    c.login(state['user'],'Synthetic-Only-Password!2026')
    c.select('INBOX')
    assert c.response('UIDVALIDITY')[1][0].decode()==state['uidvalidity'],'UIDVALIDITY changed'
    code,data=c.uid('search',None,'HEADER','Message-ID','<'+state['tag']+'@alpha.invalid>')
    assert code=='OK' and data[0],'Stored message missing after restart'
    uid=data[0].split()[-1]
    code,data=c.uid('fetch',uid,'(BODY.PEEK[])')
    assert hashlib.sha256(data[0][1]).hexdigest()==state['sha256'],'Message bytes changed after restart'
print(json.dumps({'test':'Restart preserves mail bytes and UIDVALIDITY','passed':True}))
