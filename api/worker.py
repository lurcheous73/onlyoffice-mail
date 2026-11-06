#!/usr/bin/python3
"""Restricted OO spam-training queue worker and DKIM publication.

Only preapproved OO HTTP origins can supply messages. Redirects are refused;
responses are size bounded. Rspamd and Redis stay on the private network.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from common import connect,domain,secret
from server import validate_training_url

MAX_BYTES=25*1024*1024

def publish_dkim():
    with connect() as db,db.cursor() as c:
        c.execute('SELECT domain_name,selector,private_key FROM dkim ORDER BY id')
        rows=c.fetchall()
    root=Path('/dkim')
    for row in rows:
        host=domain(row['domain_name'])
        selector=row['selector']
        if not re.fullmatch('[A-Za-z0-9_-]{1,63}',selector):raise ValueError('Invalid DKIM selector')
        key=row['private_key'].encode()
        if len(key)>16384:raise ValueError('Oversize DKIM key')
        load_pem_private_key(key,password=None)
        dest=root/(host+'.'+selector+'.key')
        if not dest.exists() or dest.read_bytes()!=key:
            temp=root/(host+'.'+selector+'.tmp')
            temp.write_bytes(key);os.chmod(temp,0o644);temp.replace(dest)
    # Rspamd reads only the active per-domain map; previous key files are kept
    # for recovery. The shared volume is not published outside the mail network.
    mapping={}
    for row in rows:
        mapping[domain(row['domain_name'])]={'selector':row['selector'],
            'path':'/dkim/'+row['domain_name']+'.'+row['selector']+'.key'}
    dest=root/'domains.json'
    data=json.dumps(mapping,sort_keys=True)
    if not dest.exists() or dest.read_text()!=data:
        temp=root/'domains.tmp';temp.write_text(data);os.chmod(temp,0o644);temp.replace(dest)

def train_once():
    stage='queue'
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id,url,is_spam FROM api_sa_training_queue WHERE state=0 ORDER BY id LIMIT 1')
        row=c.fetchone()
        if not row:return
        c.execute('UPDATE api_sa_training_queue SET state=1 WHERE id=%s AND state=0',(row['id'],))
        if c.rowcount!=1:return
    try:
        stage='fetch'
        url=validate_training_url(row['url'])
        with requests.get(url,timeout=(5,10),stream=True,allow_redirects=False) as r:
            if r.status_code!=200:raise ValueError('Message fetch failed')
            parts=[];size=0
            for chunk in r.iter_content(65536):
                size+=len(chunk)
                if size>MAX_BYTES:raise ValueError('Message too large')
                parts.append(chunk)
            message=b''.join(parts)
        if not message:raise ValueError('Empty message')
        endpoint='learnspam' if row['is_spam'] else 'learnham'
        stage='learn'
        r=requests.post('http://filter:11334/'+endpoint,data=message,
            headers={'Password':secret('filter_password')},timeout=20)
        if not r.ok:
            # Repeated OO training is idempotent. Rspamd returns HTTP 404 for
            # this specific successful prior classification; other errors fail.
            try:error=r.json().get('error','')
            except (ValueError,AttributeError):error=''
            label='spam' if row['is_spam'] else 'ham'
            duplicate=(r.status_code==404 and isinstance(error,str) and
                       error.endswith('has been already learned as '+label+', ignore it'))
            if not duplicate:r.raise_for_status()
        md5=hashlib.md5(message,usedforsecurity=False).hexdigest()
        with connect() as db,db.cursor() as c:
            c.execute('INSERT INTO api_sa_training_history(md5,is_spam,date_created,date_trained) VALUES(%s,%s,UTC_TIMESTAMP(),UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE is_spam=VALUES(is_spam),date_trained=UTC_TIMESTAMP()',(md5,row['is_spam']))
            c.execute('UPDATE api_sa_training_queue SET state=2 WHERE id=%s',(row['id'],))
    except Exception as exc:
        with connect() as db,db.cursor() as c:
            c.execute('UPDATE api_sa_training_queue SET state=3 WHERE id=%s',(row['id'],))
        print(json.dumps({'task':row['id'],'state':'failed; URL and content omitted','stage':stage,'error_type':type(exc).__name__,'http_status':getattr(getattr(exc,'response',None),'status_code',None)}),flush=True)

if __name__=='__main__':
    while True:
        try:publish_dkim();train_once()
        except Exception as exc:print(json.dumps({'worker_error':type(exc).__name__}),flush=True)
        time.sleep(2)
