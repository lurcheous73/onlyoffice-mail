import os
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

def initialize():
    sql=Path("/opt/oo-db/10-schema.sql").read_text()
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
    current.write_text("OO compatibility schema v2; fresh transactional deployment\n")

data=Path('/var/lib/mysql')
marker=data/'.oo-mail-schema-1'
current=data/'.oo-mail-schema-2'
initialized=(data/'mysql').exists()
if marker.is_symlink() or current.is_symlink() or data.is_symlink():
    raise SystemExit('Linked database paths are not supported')
if not (marker.exists() or current.exists()) and (initialized or any(data.iterdir())):
    raise SystemExit('Unmarked existing database: import into a fresh copy through the reviewed migration procedure')
upgrade=marker.exists() and not current.exists()
if upgrade and os.environ.get('OO_UPGRADE_RESTORED_COPY')!='yes':
    raise SystemExit('Schema v1 retained unchanged: restore a separate copy, then explicitly authorize its backed-up v2 upgrade')
# Only a fresh or explicitly marked lab volume reaches ownership maintenance.
subprocess.run(['chown','-hR','mysql:mysql',str(data)],check=True)
if not initialized:
    subprocess.run(['mariadb-install-db','--user=mysql','--datadir=/var/lib/mysql','--auth-root-authentication-method=socket'],check=True,stdout=subprocess.DEVNULL)
if not current.exists():
    proc=subprocess.Popen(['mariadbd','--user=mysql','--datadir=/var/lib/mysql','--skip-networking','--socket=/run/mysqld/mysqld.sock','--sql-mode=NO_ENGINE_SUBSTITUTION'])
    try:
        for _ in range(60):
            if subprocess.run(['mariadb-admin','ping','--silent'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
            time.sleep(1)
        else: raise RuntimeError('Database startup timed out')
        if upgrade:
            backups=data/'.oo-upgrades'
            if backups.is_symlink():raise RuntimeError('Linked upgrade backup directory')
            backups.mkdir(mode=0o700,exist_ok=True);os.chmod(backups,0o700)
            name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex
            backup=backups/(name+'-before-v2.sql')
            # No network listener or other application writer exists during this
            # offline step. Lock all tables because v1 includes MyISAM tables.
            fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as output:
                subprocess.run(['mariadb-dump','--lock-all-tables','--routines','--events','--triggers','--databases','onlyoffice_mailserver'],stdout=output,check=True)
                output.flush();os.fsync(output.fileno())
            sql='ALTER TABLE onlyoffice_mailserver.api_sa_training_history ENGINE=InnoDB;\nALTER TABLE onlyoffice_mailserver.api_sa_training_queue ENGINE=InnoDB;\n'
            subprocess.run(['mariadb'],input=sql,text=True,check=True)
            engines=subprocess.check_output(['mariadb','-N','-B','-e',"SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA='onlyoffice_mailserver' AND TABLE_NAME IN ('api_sa_training_history','api_sa_training_queue')"],text=True).splitlines()
            if engines!=['InnoDB','InnoDB']:raise RuntimeError('Training engine conversion incomplete')
            receipt={'schema_from':1,'schema_to':2,'backup':backup.name,'sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'capture':'offline --lock-all-tables; no network listener','retained_original_marker':True}
            (backups/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
            current.write_text('OO compatibility schema v2; transactional training tables; backed-up restored copy upgrade\n')
        else:
            initialize()
    finally:
        subprocess.run(['mariadb-admin','shutdown'],check=True)
        proc.wait(timeout=30)
os.execvp('mariadbd',['mariadbd','--user=mysql','--datadir=/var/lib/mysql','--bind-address=0.0.0.0','--sql-mode=NO_ENGINE_SUBSTITUTION','--skip-name-resolve','--max-connections=100','--max-allowed-packet=64M','--wsrep-on=OFF','--wsrep-provider=none','--wsrep-notify-cmd='])
