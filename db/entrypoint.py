import os
from pathlib import Path
import re
import subprocess
import time

data=Path('/var/lib/mysql')
marker=data/'.oo-mail-schema-1'
initialized=(data/'mysql').exists()
if marker.is_symlink() or data.is_symlink():
    raise SystemExit('Linked database paths are not supported')
if not marker.exists() and (initialized or any(data.iterdir())):
    raise SystemExit('Unmarked existing database: import into a fresh copy through the reviewed migration procedure')
# Only a fresh or explicitly marked lab volume reaches ownership maintenance.
subprocess.run(['chown','-hR','mysql:mysql',str(data)],check=True)
if not initialized:
    subprocess.run(['mariadb-install-db','--user=mysql','--datadir=/var/lib/mysql','--auth-root-authentication-method=socket'],check=True,stdout=subprocess.DEVNULL)
if not marker.exists():
    proc=subprocess.Popen(['mariadbd','--user=mysql','--skip-networking','--socket=/run/mysqld/mysqld.sock','--sql-mode=NO_ENGINE_SUBSTITUTION'])
    try:
        for _ in range(60):
            if subprocess.run(['mariadb-admin','ping','--silent'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
            time.sleep(1)
        else: raise RuntimeError('Database startup timed out')
        sql=Path('/opt/oo-db/10-schema.sql').read_text()
        roles={
          'mailreader':('reader_db','GRANT SELECT ON onlyoffice_mailserver.domain TO {who}; GRANT SELECT ON onlyoffice_mailserver.mailbox TO {who}; GRANT SELECT ON onlyoffice_mailserver.alias TO {who};'),
          'mailauth':('auth_db','GRANT SELECT ON onlyoffice_mailserver.domain TO {who}; GRANT SELECT ON onlyoffice_mailserver.mailbox TO {who}; GRANT UPDATE(password) ON onlyoffice_mailserver.mailbox TO {who};'),
          'mailapi':('api_db','GRANT SELECT ON onlyoffice_mailserver.domain TO {who}; GRANT SELECT ON onlyoffice_mailserver.mailbox TO {who}; GRANT SELECT,INSERT,UPDATE ON onlyoffice_mailserver.api_keys TO {who}; GRANT SELECT ON onlyoffice_mailserver.global_vars TO {who}; GRANT SELECT,INSERT,UPDATE ON onlyoffice_mailserver.api_sa_training_queue TO {who}; GRANT SELECT,INSERT,UPDATE ON onlyoffice_mailserver.api_sa_training_history TO {who}; GRANT SELECT ON onlyoffice_mailserver.dkim TO {who};'),
          'oo_admin':('oo_db','GRANT SELECT,INSERT,UPDATE,DELETE ON onlyoffice_mailserver.domain TO {who}; GRANT SELECT,INSERT,UPDATE,DELETE ON onlyoffice_mailserver.mailbox TO {who}; GRANT SELECT,INSERT,UPDATE,DELETE ON onlyoffice_mailserver.alias TO {who}; GRANT SELECT,INSERT,UPDATE,DELETE ON onlyoffice_mailserver.dkim TO {who};'),
        }
        for user,(filename,grants) in roles.items():
            password=(Path('/run/secrets')/filename).read_text().strip()
            if not re.fullmatch('[0-9a-f]{64}',password):raise ValueError('Invalid secret')
            who="'"+user+"'@'%'"
            sql+="\nCREATE USER "+who+" IDENTIFIED BY '"+password+"';\n"+grants.format(who=who)
        token=Path('/run/secrets/api_token').read_text().strip()
        if not re.fullmatch('[0-9a-f]{64}',token):raise ValueError('Invalid API token')
        sql+="\nINSERT INTO api_keys(id,access_token,active,expires_at,created_at,updated_at) VALUES(1,'"+token+"',1,'2099-01-01',UTC_TIMESTAMP(),UTC_TIMESTAMP());\n"
        subprocess.run(['mariadb','--default-character-set=utf8mb4'],input=sql,text=True,check=True)
        marker.write_text('OO compatibility schema v1; fresh deployment only\n')
    finally:
        subprocess.run(['mariadb-admin','shutdown'],check=True)
        proc.wait(timeout=30)
os.execvp('mariadbd',['mariadbd','--user=mysql','--bind-address=0.0.0.0','--sql-mode=NO_ENGINE_SUBSTITUTION','--skip-name-resolve','--max-connections=100','--max-allowed-packet=64M','--wsrep-on=OFF','--wsrep-provider=none','--wsrep-notify-cmd='])
