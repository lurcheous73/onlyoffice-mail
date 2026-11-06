#!/usr/bin/python3
"""OO MailServer v1 compatibility API. New implementation of observed contract.

Query tokens are accepted for OO compatibility; access logs never include URLs.
Cleanup retires directories on the same volume, retaining all content. No API
endpoint recursively deletes files. Database writes remain OO's existing SQL
contract and are deliberately not duplicated by the cleanup endpoint.
"""
import datetime
import functools
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid
from flask import Flask,abort,jsonify,request
from common import address,domain,connect,mailbox_path,secret

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=16384
ROOT=Path(os.environ.get('MAIL_ROOT','/var/vmail'))
PUBLIC_MAILBOX='username,name,local_part,storagebasedirectory,storagenode,maildir,quota,domain,created,modified,expired,active'

def normal(value):
    if isinstance(value,(datetime.date,datetime.datetime)):
        return value.isoformat()
    return value

def envelope(name,row):
    return {name:{k:normal(v) for k,v in row.items()}}

def authenticated(fn):
    @functools.wraps(fn)
    def wrapped(*args,**kwargs):
        token=request.headers.get('Auth-Token') or request.args.get('auth_token','')
        if not isinstance(token,str) or not 16<=len(token)<=255:
            abort(401)
        with connect() as db,db.cursor() as c:
            c.execute('SELECT access_token FROM api_keys WHERE active=1 AND (expires_at IS NULL OR expires_at>UTC_TIMESTAMP()) AND access_token=%s',(token,))
            row=c.fetchone()
            if not row or not hmac.compare_digest(row['access_token'],token): abort(401)
        return fn(*args,**kwargs)
    return wrapped

@app.errorhandler(ValueError)
def invalid(_): return jsonify(error='Invalid request or storage mapping'),400

@app.errorhandler(404)
def missing(_): return jsonify(error='Not found'),404

@app.errorhandler(401)
def unauthorized(_): return jsonify(error='Unauthorized. Invalid or expired token.'),401

@app.errorhandler(500)
def failed(_): return jsonify(error='Service unavailable'),500

@app.get('/health')
def health():
    with connect() as db,db.cursor() as c: c.execute('SELECT 1')
    return jsonify(status='ok')

@app.get('/api/v1/version')
@app.get('/api/v1/version.json')
@authenticated
def version():
    with connect() as db,db.cursor() as c:
        c.execute("SELECT value FROM global_vars WHERE variable='VERSION'")
        row=c.fetchone()
    return jsonify(global_vars={'value':row['value'] if row else '2.0.0-dev'})

@app.get('/api/v1/domains')
@authenticated
def domains():
    with connect() as db,db.cursor() as c:
        c.execute('SELECT domain,description,aliases,mailboxes,maxquota,quota,transport,backupmx,created,modified,active FROM domain ORDER BY domain')
        rows=c.fetchall()
    return jsonify([envelope('domain',r) for r in rows])

@app.route('/api/v1/domains/<host>',methods=['GET','DELETE'])
@authenticated
def domain_route(host):
    domain(host)
    with connect() as db,db.cursor() as c:
        c.execute('SELECT domain,description,aliases,mailboxes,maxquota,quota,transport,backupmx,created,modified,active FROM domain WHERE domain=%s',(host,))
        row=c.fetchone()
        if not row: abort(404)
        if request.method=='GET': return jsonify(envelope('domain',row))
        c.execute('SELECT username,storagebasedirectory,storagenode,maildir FROM mailbox WHERE domain=%s',(host,))
        rows=c.fetchall()
    # Preflight every mapping before making any filesystem change.
    for r in rows: mailbox_path(r,ROOT)
    receipts=[retire(r) for r in rows]
    return jsonify(retired=receipts,preserved=True)

@app.get('/api/v1/domains/<host>/mailboxes')
@authenticated
def mailboxes(host):
    domain(host)
    with connect() as db,db.cursor() as c:
        c.execute('SELECT domain FROM domain WHERE domain=%s',(host,))
        if not c.fetchone(): abort(404)
        c.execute('SELECT '+PUBLIC_MAILBOX+' FROM mailbox WHERE domain=%s ORDER BY username',(host,))
        rows=c.fetchall()
    return jsonify([envelope('mailbox',r) for r in rows])

def retire(row):
    src=mailbox_path(row,ROOT)
    retired=ROOT/'.retired'
    if retired.is_symlink(): raise ValueError('Unsafe retired root')
    retired.mkdir(mode=0o700,exist_ok=True)
    identity=hashlib.sha256(row['username'].encode()).hexdigest()
    dest=retired/(identity+'-'+uuid.uuid4().hex)
    if not src.exists(): return {'mailbox':row['username'],'already_absent':True}
    # Same-filesystem atomic rename; no recursive removal and no symlink walk.
    src.rename(dest)
    receipt={'mailbox':row['username'],'source':str(src.relative_to(ROOT)),
             'retained_at':str(dest.relative_to(ROOT)),'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (retired/(dest.name+'.json')).write_text(json.dumps(receipt)+'\n')
    return receipt

@app.route('/api/v1/domains/<host>/mailboxes/<local>',methods=['GET','DELETE'])
@authenticated
def mailbox_route(host,local):
    username=address(local+'@'+host)
    with connect() as db,db.cursor() as c:
        c.execute('SELECT '+PUBLIC_MAILBOX+' FROM mailbox WHERE username=%s AND domain=%s',(username,host))
        row=c.fetchone()
    if not row: abort(404)
    if request.method=='GET': return jsonify(envelope('mailbox',row))
    return jsonify(retired=retire(row),preserved=True)

def validate_training_url(value):
    try: p=urlsplit(value)
    except (ValueError,TypeError): raise ValueError('Invalid training URL')
    origins=set(x for x in os.environ.get('TRAINING_ORIGINS','').split(',') if x)
    origin=p.scheme+'://'+p.netloc
    if origin not in origins or p.scheme not in ('http','https') or p.username or p.password or p.fragment:
        raise ValueError('Training origin is not approved')
    if not p.path.startswith('/') or len(value)>4096:
        raise ValueError('Invalid training path')
    return value

@app.post('/api/v1/spam/training')
@app.post('/api/v1/spam/training.json')
@authenticated
def training():
    values=request.get_json(silent=True) or request.form
    url=validate_training_url(values.get('url',''))
    is_spam=values.get('is_spam')
    if str(is_spam) not in ('0','1'): raise ValueError('Invalid training flag')
    with connect() as db,db.cursor() as c:
        c.execute('INSERT INTO api_sa_training_queue(url,is_spam,state) VALUES (%s,%s,0)',(url,int(is_spam)))
        task_id=c.lastrowid
    return jsonify(spam_training_queue={'id':task_id,'url':url,'is_spam':int(is_spam),'state':0}),201

@app.get('/api/v1/api_keys')
@authenticated
def keys():
    with connect() as db,db.cursor() as c:
        # Metadata only. Key material is never returned by a list operation.
        c.execute('SELECT id,active,expires_at,created_at,updated_at FROM api_keys')
        rows=c.fetchall()
    return jsonify([envelope('api_key',r) for r in rows])

def expiry(value):
    try:
        dt=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=datetime.timezone.utc)
        dt=dt.astimezone(datetime.timezone.utc)
    except (AttributeError,TypeError,ValueError): raise ValueError('Invalid expiry')
    if dt<=datetime.datetime.now(datetime.timezone.utc): raise ValueError('Expiry must be in the future')
    return dt.replace(tzinfo=None)

@app.post('/api/v1/api_keys')
@authenticated
def create_key():
    import secrets
    values=request.get_json(silent=True) or request.form
    expires=expiry(values.get('expires_at'))
    token=secrets.token_hex(32)
    with connect() as db,db.cursor() as c:
        c.execute('INSERT INTO api_keys(access_token,active,expires_at,created_at,updated_at) VALUES(%s,1,%s,UTC_TIMESTAMP(),UTC_TIMESTAMP())',(token,expires))
        ident=c.lastrowid
    return jsonify(api_key={'id':ident,'access_token':token,'active':True,'expires_at':expires.isoformat()}),201

@app.route('/api/v1/api_keys/<key>',methods=['GET','PUT','DELETE'])
@authenticated
def key_route(key):
    if not re.fullmatch('[0-9a-f]{16,64}',key):raise ValueError('Invalid token identifier')
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id,active,expires_at,created_at,updated_at FROM api_keys WHERE access_token=%s',(key,))
        row=c.fetchone()
        if not row:abort(404)
        if request.method=='DELETE':
            c.execute('UPDATE api_keys SET active=0,updated_at=UTC_TIMESTAMP() WHERE id=%s',(row['id'],))
            return jsonify(revoked=True)
        if request.method=='PUT':
            values=request.get_json(silent=True) or request.form
            active=values.get('active',row['active'])
            if str(active).lower() not in ('0','1','true','false'):raise ValueError('Invalid active flag')
            active=str(active).lower() in ('1','true')
            expires=expiry(values['expires_at']) if 'expires_at' in values else row['expires_at']
            c.execute('UPDATE api_keys SET active=%s,expires_at=%s,updated_at=UTC_TIMESTAMP() WHERE id=%s',(active,expires,row['id']))
            row.update(active=active,expires_at=expires)
    return jsonify(envelope('api_key',row))

@app.get('/api/v1/spam/training/<int:task_id>')
@authenticated
def training_state(task_id):
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id,is_spam,state,date_created FROM api_sa_training_queue WHERE id=%s',(task_id,))
        row=c.fetchone()
    if not row:abort(404)
    return jsonify(envelope('spam_training_queue',row))

if __name__=='__main__':
    from waitress import serve
    logging.getLogger('werkzeug').disabled=True
    logging.getLogger('waitress').setLevel(logging.ERROR)
    serve(app,host='0.0.0.0',port=8081,threads=4,channel_timeout=15,max_request_body_size=16384)
