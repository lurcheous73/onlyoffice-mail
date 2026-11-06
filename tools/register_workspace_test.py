#!/usr/bin/env python3
"""Register the backend with an EMPTY synthetic Workspace fixture only."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess

from rehearse_backup import guard,run

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hostname',required=True);p.add_argument('--project',required=True);a=p.parse_args()
guard(a.hostname,a.project)
if run('systemd-detect-virt')!='kvm':p.exit(1,'Dedicated KVM client fixture required\n')
repo=Path(__file__).resolve().parents[1]
container=a.project+'-workspace-db-1'
info=json.loads(run('docker','inspect',container))[0]
if info['Config']['Labels'].get('com.docker.compose.service')!='workspace-db':p.exit(1,'Not the synthetic Workspace database\n')
def query(sql):
    command=['docker','exec','-i',container,'sh','-c','export MYSQL_PWD="$(cat /run/secrets/workspace_app)"; exec mysql -N -B -uonlyoffice_user onlyoffice']
    return subprocess.run(command,input=sql,text=True,check=True,capture_output=True).stdout.strip()
if query('SELECT COUNT(*) FROM mail_server_server;')!='0' or query('SELECT COUNT(*) FROM mail_mailbox;')!='0':p.exit(1,'Existing server or mailboxes retained; registration is fresh-fixture only\n')
def read(name):
    value=(repo/'.state/secrets'/name).read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('Invalid generated lab secret')
    return value
connection={'DbConnection':'Server=database;Database=onlyoffice_mailserver;User ID=oo_admin;Password='+read('oo_db')+';Pooling=True;Character Set=utf8;AutoEnlist=false;SSL Mode=None;Connection Timeout=30;Maximum Pool Size=100;',
            'Api':{'Protocol':'http','Server':'api','Port':'8081','Version':'v1','Token':read('api_token')}}
payload=json.dumps(connection,separators=(',',':')).encode().hex()
sql="""START TRANSACTION;
INSERT INTO mail_mailbox_server(id_provider,type,hostname,port,socket_type,username,authentication,is_user_data) VALUES(-1,'imap','mail.lab.invalid',143,'STARTTLS','%EMAILADDRESS%','',0);
SET @imap_id=LAST_INSERT_ID();
INSERT INTO mail_mailbox_server(id_provider,type,hostname,port,socket_type,username,authentication,is_user_data) VALUES(-1,'smtp','mail.lab.invalid',587,'STARTTLS','%EMAILADDRESS%','',0);
SET @smtp_id=LAST_INSERT_ID();
INSERT INTO mail_server_server(mx_record,connection_string,server_type,smtp_settings_id,imap_settings_id) VALUES('mail.lab.invalid',CONVERT(0x"""+payload+""" USING utf8mb4),2,@smtp_id,@imap_id);
SELECT LAST_INSERT_ID();
COMMIT;
"""
server_id=int(query(sql))
print(json.dumps({'registered_fresh_fixture':True,'server_id':server_id,'mail_hostname':'mail.lab.invalid','imap_starttls':143,'smtp_starttls':587,'private_api_port':8081,'backend_sql_role':'oo_admin'}))
