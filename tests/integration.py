#!/usr/bin/python3
"""End-to-end synthetic OO SQL/API and actual SMTP/IMAP tests.

No public SMTP recipient or production data is permitted. Run only through
the provided isolated test Compose profile. Keeps all dummy mail for review.
"""
import ctypes
import base64
import email
from email.message import EmailMessage
from email import policy
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import imaplib
import json
import os
import poplib
from pathlib import Path
import smtplib
import socket
import ssl
import sys
import time
import threading
import uuid
import requests
import dkim
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

sys.path.insert(0,'/opt/tests/api')
from common import connect,secret

results=[]
CONTEXT=ssl.create_default_context(cafile='/run/tls/ca.crt')
TOKEN=secret('api_token')
BASE='http://api:8081'
PASS='Synthetic-Only-Password!2026'
RUN=uuid.uuid4().hex[:8]
HOST='alpha.invalid'
ALICE='alice'+RUN+'@'+HOST
BOB='bob'+RUN+'@'+HOST

def check(name,fn):
    started=time.monotonic()
    try:
        fn()
        item={'test':name,'passed':True,'seconds':round(time.monotonic()-started,2)}
    except Exception as exc:
        item={'test':name,'passed':False,'error':type(exc).__name__+': '+str(exc)}
    results.append(item)
    print(json.dumps(item),flush=True)

def sql(query,params=()):
    with connect() as db,db.cursor() as c:
        c.execute(query,params)
        return c.fetchall()

def legacy_hash(password):
    lib=ctypes.CDLL('libcrypt.so.1');lib.crypt.restype=ctypes.c_char_p
    return lib.crypt(password.encode(),b'$1$ootest42$').decode()

def create_mailbox(username):
    local=username.split('@')[0]
    # Columns/REPLACE pattern taken from OO 12.8 MailboxDao.Save.
    sql('REPLACE INTO mailbox(username,name,password,maildir,local_part,domain,created,modified,enableimap,enableimapsecured,enablepop3,enablepop3secured,enabledeliver,enablelda) VALUES(%s,%s,%s,%s,%s,%s,NOW(),NOW(),1,1,1,1,1,1)',
        (username,local,legacy_hash(PASS),HOST+'/'+local[:1]+'/'+local[1:2]+'/'+local[2:3]+'/'+local+'-2026.11.06.00.00.00/',local,HOST))
    sql('REPLACE INTO alias(address,goto,domain,created,modified,active,islist) VALUES(%s,%s,%s,NOW(),NOW(),1,0)',(username,username,HOST))

def setup():
    sql('INSERT INTO domain(domain,description,created,modified,active) VALUES(%s,%s,NOW(),NOW(),1) ON DUPLICATE KEY UPDATE active=1',(HOST,'Synthetic OO compatibility domain'))
    create_mailbox(ALICE);create_mailbox(BOB)

def imap(user,password=PASS):
    c=imaplib.IMAP4_SSL('mail.lab.invalid',993,ssl_context=CONTEXT)
    c.login(user,password)
    return c

def api(path,method='GET',**kwargs):
    return requests.request(method,BASE+path,headers={'Auth-Token':TOKEN},timeout=15,**kwargs)

def test_version_auth():
    r=requests.get(BASE+'/api/v1/version',timeout=5)
    assert r.status_code==401,r.status_code
    r=requests.get(BASE+'/api/v1/version',params={'auth_token':TOKEN},timeout=5)
    assert r.status_code==200 and r.json()['global_vars']['value']=='2.0.0-dev'
    assert api('/api/v1/version.json').status_code==200

def test_sql_api():
    r=api('/api/v1/domains/'+HOST+'/mailboxes')
    assert r.status_code==200,r.text
    users={x['mailbox']['username'] for x in r.json()}
    assert {ALICE,BOB}<=users
    assert all('password' not in x['mailbox'] for x in r.json())

def test_all_oo_fields():
    contract=json.loads(Path('/opt/tests/oo-sql-contract.json').read_text())
    for table,expected in contract['tables'].items():
        actual={r['COLUMN_NAME'] for r in sql('SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',('onlyoffice_mailserver',table))}
        assert set(expected)<=actual,(table,sorted(set(expected)-actual))

def test_password_upgrade():
    assert sql('SELECT password FROM mailbox WHERE username=%s',(ALICE,))[0]['password'].startswith('$1$')
    with imap(ALICE) as c: assert c.noop()[0]=='OK'
    assert sql('SELECT password FROM mailbox WHERE username=%s',(ALICE,))[0]['password'].startswith('{ARGON2ID}$argon2id$')
    with imap(ALICE) as c: assert c.noop()[0]=='OK'

def test_wrong_and_disabled():
    try:
        with imap(ALICE,'wrong'):pass
    except imaplib.IMAP4.error:pass
    else:raise AssertionError('Wrong password accepted')
    sql('UPDATE mailbox SET active=0 WHERE username=%s',(BOB,))
    try:
        try:
            with imap(BOB):pass
        except imaplib.IMAP4.error:pass
        else:raise AssertionError('Disabled mailbox accepted')
    finally:sql('UPDATE mailbox SET active=1 WHERE username=%s',(BOB,))

def send(sender,recipient,tag,attachment=True,authenticated=True):
    m=EmailMessage();m['From']=sender;m['To']=recipient;m['Subject']='OO synthetic '+tag
    m['Message-ID']='<'+tag+'@alpha.invalid>'
    m.set_content('Synthetic preservation test: café, £, 日本語.\n')
    if attachment:m.add_attachment(b'attachment-test\x00\xff',maintype='application',subtype='octet-stream',filename='example.bin')
    port=587 if authenticated else 25
    with smtplib.SMTP('mail.lab.invalid',port,timeout=60) as s:
        s.ehlo();s.starttls(context=CONTEXT);s.ehlo()
        if authenticated:s.login(sender,PASS)
        s.send_message(m)

def find_message(user,tag):
    for _ in range(40):
        with imap(user) as c:
            c.select('INBOX')
            code,data=c.uid('search',None,'HEADER','Message-ID','<'+tag+'@alpha.invalid>')
            if code=='OK' and data[0]:
                uid=data[0].split()[-1]
                code,data=c.uid('fetch',uid,'(BODY.PEEK[])')
                message=email.message_from_bytes(data[0][1],policy=policy.default)
                message.raw_source=data[0][1]
                return uid,message
        time.sleep(1)
    raise AssertionError('Message not delivered: '+tag)

def test_authenticated_delivery():
    tag=RUN+'-outbound';send(ALICE,BOB,tag)
    uid,m=find_message(BOB,tag)
    assert str(m['Subject'])=='OO synthetic '+tag
    assert next(m.iter_attachments()).get_payload(decode=True)==b'attachment-test\x00\xff'
    assert '日本語' in m.get_body(preferencelist=('plain',)).get_content()

def test_inbound_delivery():
    tag=RUN+'-inbound';send('outside@sender.invalid',ALICE,tag,authenticated=False)
    find_message(ALICE,tag)

def test_alias_and_group():
    alias='support'+RUN+'@'+HOST
    sql('REPLACE INTO alias(address,goto,domain,created,modified,active,islist) VALUES(%s,%s,%s,NOW(),NOW(),1,0)',(alias,BOB,HOST))
    tag=RUN+'-alias';send(ALICE,alias,tag);find_message(BOB,tag)
    group='team'+RUN+'@'+HOST
    sql('REPLACE INTO alias(address,goto,domain,created,modified,active,islist) VALUES(%s,%s,%s,NOW(),NOW(),1,1)',(group,ALICE+','+BOB,HOST))
    tag=RUN+'-group';send(ALICE,group,tag)
    find_message(ALICE,tag);find_message(BOB,tag)

def test_relay_and_tls_enforcement():
    with smtplib.SMTP('mail.lab.invalid',25,timeout=10) as s:
        s.ehlo();s.mail('outside@sender.invalid');code,_=s.rcpt('nobody@external.invalid')
        assert code>=500,code
    with smtplib.SMTP('mail.lab.invalid',587,timeout=10) as s:
        s.ehlo();code,_=s.docmd('AUTH PLAIN','AHgAeA==')
        assert code>=500,code
    bad=ssl.create_default_context()
    try: imaplib.IMAP4_SSL('mail.lab.invalid',993,ssl_context=bad)
    except ssl.SSLCertVerificationError:pass
    else:raise AssertionError('Untrusted certificate accepted')

def test_password_change():
    sql('UPDATE mailbox SET password=%s WHERE username=%s',(legacy_hash('Changed-Pass!2026'),BOB))
    try:
        with imap(BOB,'Changed-Pass!2026') as c:assert c.noop()[0]=='OK'
        assert sql('SELECT password FROM mailbox WHERE username=%s',(BOB,))[0]['password'].startswith('{ARGON2ID}')
    finally:sql('UPDATE mailbox SET password=%s WHERE username=%s',(legacy_hash(PASS),BOB))

def test_folder_flags_and_drafts():
    with imap(ALICE) as c:
        folder='Synthetic-'+RUN
        assert c.create(folder)[0]=='OK'
        m=EmailMessage();m['Subject']='Draft '+RUN;m.set_content('Keep this draft')
        assert c.append(folder,'(\\Draft)',None,m.as_bytes())[0]=='OK'
        c.select(folder)
        status,data=c.uid('search',None,'ALL');uid=data[0].split()[0]
        c.uid('store',uid,'+FLAGS','(\\Seen \\Flagged)')
        status,data=c.uid('fetch',uid,'(FLAGS)')
        assert b'\\Flagged' in data[0] and b'\\Draft' in data[0]
        assert c.subscribe(folder)[0]=='OK'

def test_cleanup_preserves_mail():
    local='retire'+RUN;username=local+'@'+HOST
    create_mailbox(username)
    tag=RUN+'-retire';send(ALICE,username,tag);find_message(username,tag)
    row=sql('SELECT storagenode,maildir FROM mailbox WHERE username=%s',(username,))[0]
    src=Path('/var/vmail')/row['storagenode']/row['maildir']
    files={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*') if p.is_file()}
    r=api('/api/v1/domains/'+HOST+'/mailboxes/'+local,'DELETE')
    assert r.status_code==200,r.text
    retained=Path('/var/vmail')/r.json()['retired']['retained_at']
    assert retained.is_dir() and not src.exists()
    assert files=={str(p.relative_to(retained)):hashlib.sha256(p.read_bytes()).hexdigest() for p in retained.rglob('*') if p.is_file()}
    assert sql('SELECT username FROM mailbox WHERE username=%s',(username,))
    # Mirrors OO's SQL deletion after the API's cleanup call, test rows only.
    sql('DELETE FROM mailbox WHERE username=%s',(username,));sql('DELETE FROM alias WHERE address=%s',(username,))

def test_training_ssrf_rejected():
    for url in ['http://169.254.169.254/latest/meta-data','http://database:3306/','http://oo-fixture:8080@database/x','file:///etc/passwd']:
        r=api('/api/v1/spam/training.json','POST',data={'url':url,'is_spam':'1'})
        assert r.status_code==400,(url,r.status_code)
    # A repeated training request must complete without forcing double learning.
    for attempt in range(2):
        r=api('/api/v1/spam/training.json','POST',data={'url':'http://oo-fixture:8080/dummy.eml','is_spam':'1'})
        assert r.status_code==201,r.text
        ident=r.json()['spam_training_queue']['id']
        for _ in range(25):
            state=api('/api/v1/spam/training/'+str(ident)).json()['spam_training_queue']['state']
            if state==2:break
            if state==3:raise AssertionError('Training worker failed, attempt '+str(attempt))
            time.sleep(1)
        else:raise AssertionError('Training was not completed')

def test_dkim():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()).decode()
    public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))
    selector='lab'+RUN
    sql('INSERT INTO dkim(domain_name,selector,private_key,public_key) VALUES(%s,%s,%s,%s)',(HOST,selector,private,public.decode()))
    time.sleep(4)
    tag=RUN+'-dkim';send(ALICE,BOB,tag)
    _,message=find_message(BOB,tag)
    assert message['DKIM-Signature'],'DKIM header missing'
    assert dkim.verify(message.raw_source,dnsfunc=lambda name,timeout=5:b'v=DKIM1; k=rsa; p='+public),'DKIM verification failed'

def test_spam_and_antivirus():
    patterns=[('GTUBE','XJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X'),
              ('EICAR','X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*')]
    for name,pattern in patterns:
        message=EmailMessage();message['From']=ALICE;message['To']=BOB;message['Subject']='Synthetic '+name
        message.set_content(pattern)
        with smtplib.SMTP('mail.lab.invalid',587,timeout=60) as s:
            s.ehlo();s.starttls(context=CONTEXT);s.ehlo();s.login(ALICE,PASS)
            try:s.send_message(message)
            except smtplib.SMTPDataError as exc:
                assert exc.smtp_code>=500,(name,exc.smtp_code)
            else:raise AssertionError(name+' test content was accepted')

def test_api_key_lifecycle():
    r=api('/api/v1/api_keys','POST',json={'expires_at':'2098-01-01T00:00:00Z'})
    assert r.status_code==201,r.text
    key=r.json()['api_key']['access_token']
    assert requests.get(BASE+'/api/v1/version',headers={'Auth-Token':key},timeout=5).status_code==200
    assert api('/api/v1/api_keys/'+key,'DELETE').status_code==200
    assert requests.get(BASE+'/api/v1/version',headers={'Auth-Token':key},timeout=5).status_code==401
    assert all('access_token' not in x['api_key'] for x in api('/api/v1/api_keys').json())

def test_starttls_and_pop3():
    with imaplib.IMAP4('mail.lab.invalid',143) as c:
        c.starttls(ssl_context=CONTEXT);c.login(ALICE,PASS)
        assert c.noop()[0]=='OK'
    c=poplib.POP3_SSL('mail.lab.invalid',995,context=CONTEXT,timeout=10)
    try:
        c.user(ALICE);c.pass_(PASS)
        assert c.stat()[0]>0
        c.rset()
    finally:c.quit()
    tag=RUN+'-smtps'
    m=EmailMessage();m['From']=ALICE;m['To']=BOB;m['Subject']='Secure SMTP test'
    m['Message-ID']='<'+tag+'@alpha.invalid>';m.set_content('Synthetic SMTP 465 delivery')
    with smtplib.SMTP_SSL('mail.lab.invalid',465,context=CONTEXT,timeout=30) as s:
        s.login(ALICE,PASS);s.send_message(m)
    find_message(BOB,tag)

def test_sender_ownership():
    m=EmailMessage();m['From']='not-owned@alpha.invalid';m['To']=BOB;m['Subject']='Spoof test';m.set_content('Must be rejected')
    with smtplib.SMTP('mail.lab.invalid',587,timeout=15) as s:
        s.ehlo();s.starttls(context=CONTEXT);s.ehlo();s.login(ALICE,PASS)
        try:s.send_message(m)
        except (smtplib.SMTPSenderRefused,smtplib.SMTPRecipientsRefused):pass
        else:raise AssertionError('Unowned sender accepted')

def test_quota():
    sql('UPDATE mailbox SET quota=1 WHERE username=%s',(BOB,))
    try:
        with imap(BOB) as c:
            code,data=c.append('INBOX',None,None,b'Subject: Quota test\r\n\r\n'+b'a'*(1200*1024))
            assert code=='NO',(code,data)
    finally:sql('UPDATE mailbox SET quota=0 WHERE username=%s',(BOB,))

def test_sieve():
    s=socket.create_connection(('mail.lab.invalid',4190),10);f=s.makefile('rb')
    def reply(stream):
        lines=[]
        while True:
            line=stream.readline()
            if not line:raise AssertionError('Sieve connection closed')
            lines.append(line)
            if line.startswith((b'OK',b'NO',b'BYE')):return b''.join(lines)
    assert b'OK' in reply(f)
    s.sendall(b'STARTTLS\r\n');assert reply(f).startswith(b'OK');f.close()
    s=CONTEXT.wrap_socket(s,server_hostname='mail.lab.invalid');f=s.makefile('rb')
    # RFC 5804: capabilities are sent again after TLS negotiation.
    assert b'OK' in reply(f)
    login=base64.b64encode(b'\0'+ALICE.encode()+b'\0'+PASS.encode())
    s.sendall(b'AUTHENTICATE "PLAIN" "'+login+b'"\r\n');assert reply(f).startswith(b'OK')
    folder='Sieve-'+RUN;tag=RUN+'-sieve'
    script=('require ["fileinto", "mailbox"]; if header :contains "Subject" "'+tag+'" { fileinto :create "'+folder+'"; stop; }').encode()
    s.sendall(b'PUTSCRIPT "synthetic" {'+str(len(script)).encode()+b'+}\r\n'+script+b'\r\n');assert reply(f).startswith(b'OK')
    s.sendall(b'SETACTIVE "synthetic"\r\n');assert reply(f).startswith(b'OK')
    s.sendall(b'LOGOUT\r\n');f.close();s.close()
    send(BOB,ALICE,tag)
    for _ in range(20):
        with imap(ALICE) as c:
            code,_=c.select(folder)
            if code=='OK':
                code,data=c.uid('search',None,'ALL')
                if code=='OK' and data[0]:return
        time.sleep(1)
    raise AssertionError('Sieve fileinto did not deliver to the custom folder')

def record_persistence():
    _,message=find_message(BOB,RUN+'-outbound')
    with imap(BOB) as c:
        c.select('INBOX');uidvalidity=c.response('UIDVALIDITY')[1][0].decode()
    p=Path('/var/vmail/.qualification');p.mkdir(exist_ok=True)
    receipt={'user':BOB,'tag':RUN+'-outbound','sha256':hashlib.sha256(message.raw_source).hexdigest(),'uidvalidity':uidvalidity}
    (p/'persistence.json').write_text(json.dumps(receipt))

class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/dummy.eml':self.send_error(404);return
        message=('From: test@alpha.invalid\r\nTo: test@alpha.invalid\r\nSubject: Synthetic training sample '+RUN+'\r\nMIME-Version: 1.0\r\nContent-Type: text/plain\r\n\r\n'+
          'This synthetic example contains enough ordinary words for the mail classifier training mechanism. Meeting agenda project discussion notes office delivery library research document report account message information calendar appointment security update testing migration storage backup recovery verification attachment folder client server connection protocol transport privacy community maintenance compatibility function administration. '+RUN).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(message)));self.end_headers();self.wfile.write(message)
    def log_message(self,*args):pass

def test_network_boundary():
    # Network must have no non-local route. No probe is sent to production.
    routes=Path('/proc/net/route').read_text().splitlines()[1:]
    assert not any(line.split()[1]=='00000000' for line in routes),'Unexpected default route'

if __name__=='__main__':
    server=HTTPServer(('0.0.0.0',8080),FixtureHandler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    check('OO SQL account creation and alias records',setup)
    for name,fn in [
      ('Private API authentication/version response',test_version_auth),
      ('OO mailbox SQL and API field compatibility',test_sql_api),
      ('All fields referenced by OO source tables exist',test_all_oo_fields),
      ('Legacy password login upgrades to Argon2id',test_password_upgrade),
      ('Wrong passwords and disabled accounts rejected',test_wrong_and_disabled),
      ('Authenticated SMTP to IMAP with binary attachment',test_authenticated_delivery),
      ('Inbound SMTP to local mailbox',test_inbound_delivery),
      ('Alias and group multi-recipient delivery',test_alias_and_group),
      ('Open relay blocked and TLS enforced',test_relay_and_tls_enforcement),
      ('OO SQL password change remains compatible',test_password_change),
      ('Custom folder, draft, subscription and flags',test_folder_flags_and_drafts),
      ('OO cleanup API retains byte-identical messages',test_cleanup_preserves_mail),
      ('Spam training origin validation and SSRF prevention',test_training_ssrf_rejected),
      ('OO DKIM records produce verifiable outgoing signatures',test_dkim),
      ('GTUBE spam and EICAR antivirus rejection',test_spam_and_antivirus),
      ('API token creation and revocation',test_api_key_lifecycle),
      ('IMAP STARTTLS, POP3S and SMTP 465 delivery',test_starttls_and_pop3),
      ('Authenticated sender ownership enforcement',test_sender_ownership),
      ('Mailbox quota enforcement',test_quota),
      ('ManageSieve TLS authentication and filter delivery',test_sieve),
      ('Runtime has no default outbound route',test_network_boundary),
      ('Record message hash and UID state for restart trial',record_persistence),
    ]:check(name,fn)
    print(json.dumps({'summary':{'passed':sum(x['passed'] for x in results),'total':len(results)},'tests':results}),flush=True)
    raise SystemExit(0 if all(x['passed'] for x in results) else 1)
