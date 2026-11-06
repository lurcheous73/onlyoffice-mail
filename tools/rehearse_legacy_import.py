#!/usr/bin/env python3
"""Make and import a fresh 52-table SYNTHETIC MySQL8.4 fixture on a lab host.

Never opens a production address or accepts production input. Retains source,
archives, failed attempts and new target volumes. Requires prebuilt images.
"""
import argparse
import base64
import ctypes
from email.message import EmailMessage
from email import policy as email_policy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time

from rehearse_backup import archive_tree,capture,compare,guard,run,unlinked,volume_path

REPO=Path(__file__).resolve().parents[1]
MYSQL='sha256:05247af918647d8d063d2e880cc65c1546a7d616cde1e6c6f5dab1ca091f6cf8'


def sql_literal(value):
    if value is None:return 'NULL'
    if isinstance(value,int):return str(value)
    return "CONVERT(0x"+value.encode().hex()+" USING utf8mb4)"


def execute_sql(container,sql):
    command=['docker','exec','-i',container,'sh','-c','export MYSQL_PWD="$(cat /run/secrets/legacy_root)"; exec mysql -uroot -N -B --default-character-set=utf8mb4']
    return subprocess.run(command,input=sql,text=True,check=True,capture_output=True).stdout


def fixture(root,reader_password):
    source=root/'source-mail';source.mkdir(mode=0o700)
    schema=(REPO/'db/10-schema.sql').read_text()
    statements=[schema,'USE onlyoffice_mailserver;']
    records=[]
    lib=ctypes.CDLL('libcrypt.so.1');lib.crypt.restype=ctypes.c_char_p
    password=lib.crypt(b'Synthetic-Only-Password!2026',b'$1$ootest42$').decode()
    def insert(table,row):
        statements.append('INSERT INTO `'+table+'` ('+','.join('`'+k+'`' for k in row)+') VALUES ('+','.join(sql_literal(v) for v in row.values())+');')
    for host in ('legacy-a.invalid','legacy-b.invalid'):
        insert('domain',{'domain':host,'description':'Synthetic retained domain','created':'2020-01-02 03:04:05','modified':'2020-01-02 03:04:05','active':1})
        private=subprocess.check_output(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048'],stderr=subprocess.DEVNULL)
        public=base64.b64encode(subprocess.check_output(['openssl','pkey','-pubout','-outform','DER'],input=private,stderr=subprocess.DEVNULL)).decode()
        insert('dkim',{'domain_name':host,'selector':'preserved2020','private_key':private.decode(),'public_key':public})
    for index in range(7):
        host='legacy-a.invalid' if index<4 else 'legacy-b.invalid';local='legacy'+str(index);user=local+'@'+host
        maildir=host+'/l/e/g/'+local+'-2020.01.02.03.04.05/';home=source/'vmail1'/maildir;mail=home/'Maildir'
        for folder in ('','.Archive'):
            for part in ('cur','new','tmp'):(mail/folder/part).mkdir(mode=0o700,parents=True,exist_ok=True)
        message=EmailMessage();message['From']='source@'+host;message['To']=user;message['Subject']='Preserved legacy fixture '+str(index)
        message['Message-ID']='<legacy-'+str(index)+'@'+host+'>';message.set_content('Preserve café, 日本語, flags and original mailbox identity.\n')
        message.add_attachment(b'original-attachment\x00\xff'+bytes([index]),maintype='application',subtype='octet-stream',filename='preserved.bin')
        payload=message.as_bytes(policy=email_policy.SMTP);name='1577934245.M123P45.fixture'+str(index)
        (mail/'cur'/(name+':2,S')).write_bytes(payload)
        uidvalidity=13371337+index
        (mail/'dovecot-uidlist').write_text('3 V'+str(uidvalidity)+' N2 G'+hashlib.md5(user.encode()).hexdigest()+'\n1 :'+name+'\n')
        (mail/'subscriptions').write_text('Archive\n')
        (mail/'.Archive'/'cur'/(name+'-draft:2,DS')).write_bytes(b'Subject: Retained draft\r\n\r\nOriginal draft bytes\r\n')
        (home/'sieve').mkdir();(home/'sieve'/'retained.sieve').write_text('keep;\n');(home/'.dovecot.sieve').symlink_to('sieve/retained.sieve')
        active=int(index!=6)
        insert('mailbox',{'username':user,'name':'Synthetic café '+str(index),'password':password,'maildir':maildir,'local_part':local,'domain':host,'created':'2020-01-02 03:04:05','modified':'2020-01-02 03:04:05','quota':1024 if index==0 else 0,'active':active})
        insert('alias',{'address':user,'goto':user,'domain':host,'created':'2020-01-02 03:04:05','modified':'2020-01-02 03:04:05','active':active,'islist':0})
        records.append({'user':user,'active':active,'uidvalidity':uidvalidity,'sha256':hashlib.sha256(payload).hexdigest()})
    (source/'.legacy-fixture.json').write_text(json.dumps({'mailboxes':records},indent=2)+'\n')
    for directory,dirs,files in os.walk(source,followlinks=False):
        for path in [Path(directory),*(Path(directory)/x for x in dirs+files)]:os.chown(path,5000,5000,follow_symlinks=False)
    for index in range(33):
        engine='MyISAM' if index<18 else 'InnoDB'
        name='legacy_history_'+str(index)
        statements.append('CREATE TABLE '+name+' (id INT PRIMARY KEY,payload LONGBLOB,amount DECIMAL(20,6),recorded DATETIME(6),duration TIME(6),note TEXT) ENGINE='+engine+';')
        if index==0:statements.append("INSERT INTO "+name+" VALUES(1,0x00ff0d0a,123456789.123456,'2020-01-02 03:04:05.123456','-12:34:56.123456','Synthetic archived history');")
    if len(reader_password)!=64 or any(x not in '0123456789abcdef' for x in reader_password):raise ValueError('Invalid synthetic secret')
    statements+=["CREATE USER 'migration_reader'@'%' IDENTIFIED BY '"+reader_password+"';","GRANT SELECT ON onlyoffice_mailserver.* TO 'migration_reader'@'%';",'SET GLOBAL super_read_only=ON;']
    return source,'\n'.join(statements)


def main(a):
    guard(a.hostname,a.project);root=unlinked(a.destination);root.mkdir(mode=0o700)
    out=root/'export';out.mkdir(mode=0o700);os.chown(out,5000,5000)
    for name in ('legacy_root','legacy_copy'):
        path=root/name;path.write_text(secrets.token_hex(32)+'\n');os.chmod(path,0o444)
    source,sql=fixture(root,(root/'legacy_copy').read_text().strip())
    compose=['docker','compose','-f',str(REPO/'compose.json'),'-f',str(REPO/'compose.freshcheck.json'),'-p',a.project]
    run(*compose,'up','-d','--wait','database')
    source_name=a.project+'-source';network=a.project+'_private'
    run('docker','volume','create',a.project+'_legacy_mysql')
    run('docker','run','-d','--name',source_name,'--network',network,'--network-alias','legacy-copy','--memory','640m','-v',a.project+'_legacy_mysql:/var/lib/mysql','-v',str(root/'legacy_root')+':/run/secrets/legacy_root:ro','-e','MYSQL_ROOT_PASSWORD_FILE=/run/secrets/legacy_root',MYSQL,'--sql-mode=NO_ENGINE_SUBSTITUTION','--event-scheduler=OFF')
    for _ in range(90):
        try:
            if execute_sql(source_name,'SELECT @@skip_networking;').strip()=='0':break
            time.sleep(1)
        except subprocess.CalledProcessError:time.sleep(1)
    else:raise ValueError('Synthetic MySQL fixture failed to initialize')
    execute_sql(source_name,sql)
    target=a.project+'_maildata'
    # Compose creates declared empty volumes before starting the DB service.
    if target not in run('docker','volume','ls','--format','{{.Name}}').splitlines():
        run('docker','volume','create','--label','com.docker.compose.project='+a.project,'--label','com.docker.compose.volume=maildata',target)
    if any(volume_path(target).iterdir()):raise ValueError('Target mail volume is not empty')
    capture(source,out/'source-mail.sqlite');archive_tree(source,root/'source-mail.tar')
    copied=volume_path(target)
    subprocess.run(['tar','--same-owner','--same-permissions','--acls','--xattrs','-C',str(copied),'-xpf',str(root/'source-mail.tar')],check=True)
    capture(copied,out/'target-mail.sqlite')
    if not compare(out/'source-mail.sqlite',out/'target-mail.sqlite')['matches']:raise ValueError('Initial copied files differ')
    for name in ('source-mail.sqlite','target-mail.sqlite'):os.chown(out/name,5000,5000)
    command=['docker','run','--rm','--network',network,'-v',str(out)+':/migration','-v',str(root/'legacy_copy')+':/run/secrets/legacy_copy:ro','-v',str(REPO/'.state/secrets/oo_db')+':/run/secrets/oo_db:ro','-v',target+':/var/vmail:ro','oo-mailserver-migration:dev']
    def migrate(*args,expected=True):
        result=subprocess.run([*command,*args],capture_output=True,text=True)
        if expected and result.returncode:raise ValueError('Migration command failed: '+result.stderr[:500])
        if not expected and not result.returncode:raise ValueError('Unsafe migration request unexpectedly accepted')
        return result
    exported=json.loads(migrate('export','--archive','/migration/backend.sqlite').stdout)
    if exported['archived_tables']!=52:raise ValueError('Not every source table was archived')
    migrate('inventory','--archive','/migration/backend.sqlite','--output','/migration/policy.json')
    policy=json.loads((out/'policy.json').read_text())
    for decision in policy['retained_tables'].values():decision.update(disposition='archive_only',reason='Reviewed synthetic history or empty fixture table; full original rows remain in this archive.')
    (out/'policy.json').write_text(json.dumps(policy,indent=2)+'\n')
    bad=dict(policy,archive_sha256='0'*64);(out/'wrong-policy.json').write_text(json.dumps(bad));os.chown(out/'wrong-policy.json',5000,5000)
    common=['--source-mail-manifest','/migration/source-mail.sqlite','--target-mail-manifest','/migration/target-mail.sqlite']
    migrate('plan','--archive','/migration/backend.sqlite','--policy','/migration/wrong-policy.json',*common,expected=False)
    migrate('plan','--archive','/migration/backend.sqlite','--policy','/migration/policy.json',*common,'--output','/migration/plan.json')
    plan=json.loads((out/'plan.json').read_text())
    applied=json.loads(migrate('apply','--archive','/migration/backend.sqlite','--policy','/migration/policy.json',*common,'--reviewed-plan-sha256',plan['plan_sha256'],'--output','/migration/import-receipt.json').stdout)
    if applied['core_rows']!={'domain':2,'mailbox':7,'alias':7,'dkim':2}:raise ValueError('Core counts differ')
    migrate('apply','--archive','/migration/backend.sqlite','--policy','/migration/policy.json',*common,'--reviewed-plan-sha256',plan['plan_sha256'],'--output','/migration/second-receipt.json',expected=False)
    run('docker','stop',source_name)
    result={'test':'Frozen MySQL8.4 52-table logical export and reviewed MariaDB import','passed':True,'source_engine':exported['source_engine'],'archived_tables':52,'archived_noncore_tables':48,'source_myisam_tables':18,'core_rows':applied['core_rows'],'mail_tree_exact':True,'wrong_policy_rejected':True,'repeat_import_refused':True,'private_archive_sha256':exported['archive_sha256']}
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    run(*compose,'up','-d','--wait')
    protocol=subprocess.run([*compose,'run','--rm','tests','python3','legacy_import_protocol.py'],capture_output=True,text=True)
    (root/'protocol.log').write_text(protocol.stdout+'\n'+protocol.stderr)
    if protocol.returncode:raise ValueError('Imported mailbox protocol verification failed; inspect retained private protocol.log')
    print(protocol.stdout,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hostname',required=True);p.add_argument('--project',required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args();os.umask(0o077)
    try:main(a)
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as exc:p.exit(1,str(exc)+'\n')
