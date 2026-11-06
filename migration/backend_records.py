#!/usr/bin/env python3
"""Export a frozen MySQL COPY; plan/import core records into a fresh backend.

Every legacy table, column, DDL and row is retained in a private SQLite archive.
Only four reviewed compatibility tables become active. Other tables require an
explicit disposition tied to their row count/digest. No SQL DDL is replayed.
The complete Workspace database, cached mail, files and queues remain separate
recovery assets. This command cannot capture a coherent live production backup.
"""
import argparse
import base64
import datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'api'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import address,domain,mailbox_path,secret
from file_audit import compare,file_hash,readonly,unlinked

CORE=('domain','mailbox','alias','dkim')
FEATURE_TABLES={'alias_domain','sender_bcc_domain','recipient_bcc_domain','sender_bcc_user','recipient_bcc_user','share_folder','anyone_shares','domain_admins','admin'}


def identifier(value):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',value):raise ValueError('Unsupported SQL identifier')
    return '`'+value+'`'


def pack(value):
    if isinstance(value,bytes):return {'$bytes':base64.b64encode(value).decode()}
    if isinstance(value,datetime.datetime):return {'$datetime':value.isoformat(sep=' ')}
    if isinstance(value,datetime.date):return {'$date':value.isoformat()}
    if isinstance(value,datetime.timedelta):return {'$timedelta_us':value.days*86400000000+value.seconds*1000000+value.microseconds}
    if isinstance(value,Decimal):return {'$decimal':str(value)}
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,float) and math.isfinite(value):return value
    raise ValueError('Unsupported database scalar')


def unpack(value):
    if not isinstance(value,dict):return value
    if set(value)=={'$bytes'}:return base64.b64decode(value['$bytes'],validate=True)
    if set(value)=={'$datetime'}:return datetime.datetime.fromisoformat(value['$datetime'])
    if set(value)=={'$date'}:return datetime.date.fromisoformat(value['$date'])
    if set(value)=={'$timedelta_us'}:return datetime.timedelta(microseconds=value['$timedelta_us'])
    if set(value)=={'$decimal'}:return Decimal(value['$decimal'])
    raise ValueError('Unsupported scalar tag')


def encode(row):
    return json.dumps({key:pack(value) for key,value in row.items()},sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def decode(payload):
    return {key:unpack(value) for key,value in json.loads(payload).items()}


def hash_rows(db,table):
    h=hashlib.sha256();count=0
    for (digest,) in db.execute('SELECT sha256 FROM records WHERE table_name=? ORDER BY sha256,ordinal',(table,)):
        h.update((digest+'\n').encode());count+=1
    return count,h.hexdigest()


def archive_open(path):
    path=unlinked(path).resolve(strict=True)
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON')
    meta=dict(db.execute('SELECT key,value FROM metadata'))
    if meta.get('format')!='1' or meta.get('complete')!='true':raise ValueError('Incomplete/unsupported record archive')
    if db.execute('SELECT COUNT(*) FROM records r LEFT JOIN tables t ON r.table_name=t.name WHERE t.name IS NULL').fetchone()[0]:raise ValueError('Unmapped orphan archive rows')
    for name,count,digest in db.execute('SELECT name,row_count,rows_sha256 FROM tables'):
        identifier(name)
        for payload,expected in db.execute('SELECT payload,sha256 FROM records WHERE table_name=?',(name,)):
            if len(payload)>32*1024*1024 or hashlib.sha256(payload.encode()).hexdigest()!=expected:raise ValueError('Archived row digest differs')
        if hash_rows(db,name)!=(count,digest):raise ValueError('Archived table digest differs')
    return db


def no_default_route():
    lines=Path('/proc/net/route').read_text().splitlines()[1:]
    if any(line.split()[1]=='00000000' for line in lines):raise ValueError('Run only on the dedicated internal migration network, without a default route')
    route6=Path('/proc/net/ipv6_route')
    if route6.exists():
        for line in route6.read_text().splitlines():
            fields=line.split()
            if fields[0]=='0'*32 and fields[1]=='00' and fields[-1]!='lo':raise ValueError('IPv6 default route refused')


def connection(source=False):
    no_default_route()
    import pymysql
    return pymysql.connect(host='legacy-copy' if source else 'database',user='migration_reader' if source else 'oo_admin',password=secret('legacy_copy' if source else 'oo_db'),database='onlyoffice_mailserver',charset='utf8mb4',autocommit=False,cursorclass=pymysql.cursors.DictCursor,connect_timeout=5,read_timeout=60,write_timeout=30)


def export_copy(destination):
    from pymysql.cursors import SSDictCursor
    destination=unlinked(destination)
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(descriptor)
    archive=sqlite3.connect(destination)
    archive.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE tables(name TEXT PRIMARY KEY,columns_json TEXT NOT NULL,ddl TEXT NOT NULL,engine TEXT,row_count INTEGER,rows_sha256 TEXT); CREATE TABLE records(table_name TEXT,ordinal INTEGER,payload TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(table_name,ordinal)); CREATE INDEX row_digests ON records(table_name,sha256);')
    archive.executemany('INSERT INTO metadata VALUES (?,?)',[('format','1'),('complete','false')]);archive.commit()
    try:
        with connection(source=True) as source,source.cursor() as c:
            c.execute('SELECT @@version AS version,@@read_only AS ro,@@super_read_only AS sro,@@event_scheduler AS events')
            info=c.fetchone()
            if not info['version'].startswith('8.4.') or not info['ro'] or not info['sro'] or info['events'] not in ('OFF','DISABLED'):raise ValueError('Expected a frozen MySQL8.4 recovery copy with events disabled')
            c.execute('SHOW GRANTS')
            for grant in c.fetchall():
                text=next(iter(grant.values()))
                if not (text.startswith('GRANT USAGE ') or text.startswith('GRANT SELECT ')):raise ValueError('Source account must have SELECT only')
            c.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            c.execute("SELECT TABLE_NAME,ENGINE,TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA='onlyoffice_mailserver' ORDER BY TABLE_NAME")
            tables=c.fetchall()
            for table in tables:
                name=table['TABLE_NAME'];identifier(name)
                if table['TABLE_TYPE']!='BASE TABLE':raise ValueError('Views require an explicit separate preservation review')
                c.execute("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='onlyoffice_mailserver' AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(name,))
                columns=c.fetchall()
                c.execute('SHOW CREATE TABLE '+identifier(name));ddl=list(c.fetchone().values())[1]
                archive.execute('INSERT INTO tables(name,columns_json,ddl,engine) VALUES (?,?,?,?)',(name,json.dumps(columns,default=str),ddl,table['ENGINE']))
                ordinal=0
                with source.cursor(SSDictCursor) as records_cursor:
                    records_cursor.execute('SELECT * FROM '+identifier(name))
                    while rows:=records_cursor.fetchmany(100):
                        for row in rows:
                            payload=encode(row)
                            if len(payload)>32*1024*1024:raise ValueError('Oversize source record requires review')
                            archive.execute('INSERT INTO records VALUES (?,?,?,?)',(name,ordinal,payload,hashlib.sha256(payload.encode()).hexdigest()));ordinal+=1
                count,digest=hash_rows(archive,name)
                archive.execute('UPDATE tables SET row_count=?,rows_sha256=? WHERE name=?',(count,digest,name));archive.commit()
            source.rollback()
            archive.execute('INSERT INTO metadata VALUES (?,?)',('source',json.dumps(info)))
            archive.execute("UPDATE metadata SET value='true' WHERE key='complete'");archive.commit()
        return {'archived_tables':len(tables),'source_read_only':True,'source_engine':info['version'],'archive_sha256':file_hash(destination,destination.lstat())}
    finally:archive.close()


def inventory(path):
    with archive_open(path) as db:
        return {name:{'row_count':count,'rows_sha256':digest,'disposition':'review_required','reason':''} for name,count,digest in db.execute('SELECT name,row_count,rows_sha256 FROM tables ORDER BY name') if name not in CORE}


def validate_core(table,row):
    empty=(None,'',0)
    policies={'domain':('disclaimer','settings'),'mailbox':('disclaimer','settings','allowedsenders','rejectedsenders','allowedrecipients','rejectedrecipients'),'alias':('moderators','accesspolicy')}
    for column in policies.get(table,()):
        if row.get(column) not in empty:raise ValueError('Unsupported non-default '+table+'.'+column)
    if table=='domain':
        domain(row['domain'])
        if row.get('backupmx',0)!=0 or row.get('transport','dovecot') not in ('','dovecot'):raise ValueError('Unsupported domain transport')
    if table=='mailbox':
        address(row['username']);domain(row['domain']);mailbox_path(row)
        if row['username']!=row['local_part']+'@'+row['domain']:raise ValueError('Mailbox identity mismatch')
        if row.get('transport','') not in ('','dovecot') or row.get('isadmin',0) or row.get('isglobaladmin',0):raise ValueError('Unsupported mailbox administration/transport')
        password=row['password'].removeprefix('{CRYPT}').removeprefix('{ARGON2ID}')
        if not password.startswith(('$1$','$5$','$6$','$2y$','$y$','$argon2id$')):raise ValueError('Unsupported legacy password family')
    if table=='alias':
        address(row['address']);domain(row['domain'])
        if not row.get('goto'):raise ValueError('Empty alias destination requires review')
        for value in row['goto'].split(','):address(value.strip())
    if table=='dkim':
        domain(row['domain_name'])
        if not re.fullmatch('[A-Za-z0-9_-]{1,63}',row['selector']):raise ValueError('Invalid DKIM selector')


def plan(path,policy,source_manifest,target_manifest,mail_root):
    comparison=compare(source_manifest,target_manifest)
    if not comparison['matches']:raise ValueError('Mailbox trees have not reconciled exactly')
    source_sha=file_hash(path,path.lstat())
    if policy.get('archive_sha256')!=source_sha:raise ValueError('Table review belongs to a different archive')
    with archive_open(path) as archive,connection() as target,target.cursor() as c:
        c.execute("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='onlyoffice_mailserver' ORDER BY TABLE_NAME,ORDINAL_POSITION")
        target_columns={}
        for row in c.fetchall():target_columns.setdefault(row['TABLE_NAME'],[]).append(row)
        result={'format':1,'archive_sha256':source_sha,'retained_tables':policy['retained_tables'],'core':{},'mail_tree':comparison,'source_mail_manifest_sha256':file_hash(source_manifest,source_manifest.lstat()),'target_mail_manifest_sha256':file_hash(target_manifest,target_manifest.lstat())}
        with readonly(target_manifest) as files:
            for table,count,digest,columns_json in archive.execute('SELECT name,row_count,rows_sha256,columns_json FROM tables'):
                if table not in CORE:
                    decision=policy['retained_tables'].get(table,{})
                    if decision.get('row_count')!=count or decision.get('rows_sha256')!=digest or decision.get('disposition')!='archive_only' or len(decision.get('reason',''))<20:raise ValueError('Every retained table needs an explicit matching review: '+table)
                    if table in FEATURE_TABLES and count:raise ValueError('Active unsupported legacy feature table: '+table)
                    continue
                fields=[x['COLUMN_NAME'] for x in json.loads(columns_json)]
                if set(fields)-{x['COLUMN_NAME'] for x in target_columns.get(table,[])}:raise ValueError('Unmapped source columns in '+table)
                c.execute('SELECT COUNT(*) AS n FROM '+identifier(table))
                if c.fetchone()['n']:raise ValueError('Target core tables must be empty')
                for (payload,) in archive.execute('SELECT payload FROM records WHERE table_name=? ORDER BY ordinal',(table,)):
                    row=decode(payload);validate_core(table,row)
                    if table=='mailbox':
                        home=mailbox_path(row,mail_root)
                        relative=home.relative_to(mail_root).as_posix()
                        if files.execute("SELECT kind FROM entries WHERE path=?",(relative,)).fetchone()!=('directory',) or not home.is_dir():raise ValueError('Missing copied mailbox home; never invent an empty mailbox')
                result['core'][table]={'columns':fields,'row_count':count,'rows_sha256':digest,'target_columns':target_columns[table]}
        if set(result['core'])!=set(CORE):raise ValueError('Missing core source table')
        if set(policy['retained_tables'])!=set(inventory(path)):raise ValueError('Unexpected table review entries')
        target.rollback()
        return result


def apply(path,policy,source_manifest,target_manifest,mail_root,expected,receipt):
    result=plan(path,policy,source_manifest,target_manifest,mail_root)
    digest=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    if digest!=expected:raise ValueError('Reviewed plan digest differs; run plan again')
    receipt=unlinked(receipt)
    fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(json.dumps({'state':'incomplete','plan_sha256':digest})+'\n')
    with archive_open(path) as archive,connection() as target,target.cursor() as c:
        try:
            for table in CORE:
                c.execute('SELECT * FROM '+identifier(table)+' FOR UPDATE')
                if c.fetchone():raise ValueError('Target acquired records since preflight')
            for table in CORE:
                fields=result['core'][table]['columns']
                statement='INSERT INTO '+identifier(table)+' ('+','.join(map(identifier,fields))+') VALUES ('+','.join(['%s']*len(fields))+')'
                for (payload,) in archive.execute('SELECT payload FROM records WHERE table_name=? ORDER BY ordinal',(table,)):
                    row=decode(payload);c.execute(statement,tuple(row[field] for field in fields))
                    c.execute('SHOW WARNINGS')
                    if c.fetchall():raise ValueError('Import conversion warning in '+table)
                c.execute('SELECT '+','.join(map(identifier,fields))+' FROM '+identifier(table))
                hashes=sorted(hashlib.sha256(encode(row).encode()).hexdigest() for row in c.fetchall())
                actual=hashlib.sha256(''.join(h+'\n' for h in hashes).encode()).hexdigest()
                if actual!=result['core'][table]['rows_sha256'] or len(hashes)!=result['core'][table]['row_count']:raise ValueError('Imported record mismatch in '+table)
            target.commit()
        except BaseException:target.rollback();raise
    result={'state':'committed','plan_sha256':digest,'archive_sha256':result['archive_sha256'],'core_rows':{t:result['core'][t]['row_count'] for t in CORE},'all_other_tables_retained_in_archive':True,'source_mail_manifest_sha256':result['source_mail_manifest_sha256'],'target_mail_manifest_sha256':result['target_mail_manifest_sha256']}
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['export','inventory','plan','apply'])
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--policy',type=Path);p.add_argument('--source-mail-manifest',type=Path);p.add_argument('--target-mail-manifest',type=Path);p.add_argument('--mail-root',type=Path,default=Path('/var/vmail'))
    p.add_argument('--reviewed-plan-sha256');a=p.parse_args();os.umask(0o077)
    try:
        if a.action=='export':result=export_copy(a.archive)
        elif a.action=='inventory':result={'archive_sha256':file_hash(a.archive,a.archive.lstat()),'retained_tables':inventory(a.archive)}
        else:
            policy=json.loads(unlinked(a.policy).read_text())
            if a.action=='apply':result=apply(a.archive,policy,a.source_mail_manifest,a.target_mail_manifest,a.mail_root,a.reviewed_plan_sha256,a.output)
            else:
                result=plan(a.archive,policy,a.source_mail_manifest,a.target_mail_manifest,a.mail_root)
                result['plan_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
        if a.action!='apply' and a.output:
            fd=os.open(unlinked(a.output),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as handle:json.dump(result,handle,indent=2,default=str);handle.write('\n')
        print(json.dumps({key:value for key,value in result.items() if key in ('archived_tables','source_read_only','source_engine','archive_sha256','plan_sha256','state','core_rows')}))
    except (ValueError,OSError,KeyError,TypeError,sqlite3.DatabaseError) as exc:p.exit(1,str(exc)+'\n')
