#!/usr/bin/python3
import os
from pathlib import Path
import subprocess
from common import address,domain,secret

hostname=domain(os.environ.get('MAIL_HOSTNAME','mail.lab.invalid'))
password=secret('reader_db')
sql=Path('/etc/postfix/sql')
queries={
 'domains':"SELECT domain FROM domain WHERE domain='%s' AND active=1 AND backupmx=0",
 'mailboxes':"SELECT CONCAT(m.storagebasedirectory,'/',m.storagenode,'/',m.maildir,'Maildir/') FROM mailbox m JOIN domain d ON d.domain=m.domain WHERE m.username='%s' AND m.active=1 AND m.enabledeliver=1 AND m.enablelda=1 AND d.active=1",
 'aliases':"SELECT a.goto FROM alias a JOIN domain d ON d.domain=a.domain WHERE a.address='%s' AND a.active=1 AND d.active=1",
 'senders':"SELECT username FROM mailbox WHERE username='%s' AND active=1 UNION SELECT goto FROM alias WHERE address='%s' AND active=1",
}
for name,query in queries.items():
    p=sql/(name+'.cf')
    p.write_text('hosts = database\nuser = mailreader\npassword = '+password+'\ndbname = onlyoffice_mailserver\nquery = '+query+'\n')
    os.chmod(p,0o640)
    import grp
    os.chown(p,0,grp.getgrnam('postfix').gr_gid)
settings={
 'myhostname':hostname,'myorigin':'$myhostname','mydestination':'localhost',
 'inet_interfaces':'all','inet_protocols':'ipv4','mynetworks':'127.0.0.0/8',
 'compatibility_level':'3.10','maillog_file':'/dev/stdout',
 'virtual_mailbox_domains':'mysql:/etc/postfix/sql/domains.cf',
 'virtual_mailbox_maps':'mysql:/etc/postfix/sql/mailboxes.cf',
 'virtual_alias_maps':'mysql:/etc/postfix/sql/aliases.cf',
 'virtual_transport':'lmtp:inet:127.0.0.1:2424',
 'smtpd_relay_restrictions':'permit_sasl_authenticated,reject_unauth_destination',
 'smtpd_recipient_restrictions':'reject_non_fqdn_recipient,reject_unknown_recipient_domain,reject_unlisted_recipient',
 'smtpd_tls_cert_file':'/run/tls/server.crt','smtpd_tls_key_file':'/run/tls/server.key',
 'smtpd_tls_security_level':'may','smtpd_tls_auth_only':'yes',
 'smtpd_tls_mandatory_protocols':'>=TLSv1.2','smtpd_tls_protocols':'>=TLSv1.2',
 'smtp_tls_security_level':'may','smtp_tls_CAfile':'/etc/ssl/certs/ca-certificates.crt',
 'smtpd_sasl_type':'dovecot','smtpd_sasl_path':'private/auth','smtpd_sasl_auth_enable':'no',
 'smtpd_sasl_security_options':'noanonymous','smtpd_sender_login_maps':'mysql:/etc/postfix/sql/senders.cf',
 'smtpd_milters':'inet:filter:11332','non_smtpd_milters':'inet:filter:11332',
 'milter_protocol':'6','milter_default_action':'tempfail',
 'message_size_limit':'26214400','smtpd_client_connection_count_limit':'30',
 'smtpd_helo_required':'yes','disable_vrfy_command':'yes',
 'smtp_header_checks':'',
}
for key,value in settings.items():
    subprocess.run(['postconf','-e',key+' = '+value],check=True)
# Foreground services, no systemd/cgroup/host privilege required.
Path('/etc/postfix/master.cf').write_text('''smtp inet n - n - - smtpd
submission inet n - n - - smtpd
  -o syslog_name=postfix/submission
  -o smtpd_tls_security_level=encrypt
  -o smtpd_sasl_auth_enable=yes
  -o smtpd_sender_restrictions=reject_authenticated_sender_login_mismatch
  -o smtpd_relay_restrictions=permit_sasl_authenticated,reject
smtps inet n - n - - smtpd
  -o syslog_name=postfix/smtps
  -o smtpd_tls_wrappermode=yes
  -o smtpd_sasl_auth_enable=yes
  -o smtpd_sender_restrictions=reject_authenticated_sender_login_mismatch
  -o smtpd_relay_restrictions=permit_sasl_authenticated,reject
pickup unix n - n 60 1 pickup
cleanup unix n - n - 0 cleanup
qmgr unix n - n 300 1 qmgr
tlsmgr unix - - n 1000? 1 tlsmgr
rewrite unix - - n - - trivial-rewrite
bounce unix - - n - 0 bounce
defer unix - - n - 0 bounce
trace unix - - n - 0 bounce
verify unix - - n - 1 verify
flush unix n - n 1000? 0 flush
proxymap unix - - n - - proxymap
proxywrite unix - - n - 1 proxymap
smtp unix - - n - - smtp
relay unix - - n - - smtp
showq unix n - n - - showq
error unix - - n - - error
retry unix - - n - - error
discard unix - - n - - discard
local unix - n n - - local
virtual unix - n n - - virtual
lmtp unix - - n - - lmtp
anvil unix - - n - 1 anvil
scache unix - - n - 1 scache
postlog unix-dgram n - n - 1 postlogd
''')
postmaster=address(os.environ.get('POSTMASTER_ADDRESS','postmaster@'+hostname))
dovecot=Path('/opt/oo-mail/dovecot.conf').read_text().replace('READER_SECRET',password).replace('postmaster@lab.invalid',postmaster)
Path('/etc/dovecot/dovecot.conf').write_text(dovecot)
os.chmod('/etc/dovecot/dovecot.conf',0o600)
for protocol in ('imap','pop3','smtp','sieve'):
    Path('/etc/pam.d/oo-'+protocol).write_text('auth required pam_exec.so expose_authtok quiet /usr/bin/python3 /opt/oo-mail/pam_auth.py\naccount required pam_permit.so\n')
Path('/var/vmail/vmail1').mkdir(exist_ok=True)
os.chown('/var/vmail/vmail1',5000,5000)
Path('/var/vmail/.retired').mkdir(mode=0o700,exist_ok=True)
os.chown('/var/vmail/.retired',5000,5000)
subprocess.run(['postfix','check'],check=True)
subprocess.run(['doveconf','-n'],check=True,stdout=subprocess.DEVNULL)
os.execvp('supervisord',['supervisord','-n','-c','/opt/oo-mail/supervisord.conf'])
