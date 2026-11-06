"""Shared validation and database access; Apache-2.0."""
import os
from pathlib import Path, PurePosixPath
import re
import pymysql

DOMAIN = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
LOCAL = re.compile(r"[a-z0-9][a-z0-9.!#$%&'*+\-=?^_`{|}~]{0,63}\Z")

def domain(value):
    if not isinstance(value,str) or not DOMAIN.fullmatch(value):
        raise ValueError('Invalid domain')
    return value

def address(value):
    if not isinstance(value,str) or value.count('@')!=1 or len(value)>254:
        raise ValueError('Invalid address')
    local,host=value.split('@')
    domain(host)
    if not LOCAL.fullmatch(local) or '..' in local or local.endswith('.'):
        raise ValueError('Invalid local part')
    return value

def secret(name):
    value=(Path(os.environ.get('SECRETS_DIR','/run/secrets'))/name).read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}',value):
        raise ValueError('Invalid service secret')
    return value

def connect(user=None, password_name=None):
    return pymysql.connect(host=os.environ.get('DB_HOST','database'),
        user=user or os.environ.get('DB_USER','mailapi'),
        password=secret(password_name or os.environ.get('DB_SECRET','api_db')),
        database='onlyoffice_mailserver',charset='utf8mb4',autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,connect_timeout=5,read_timeout=10,write_timeout=10)

def mailbox_path(row, root=Path('/var/vmail')):
    if row['storagebasedirectory'] != '/var/vmail':
        raise ValueError('Unsupported storage root; review migration mapping')
    parts=[]
    for key in ('storagenode','maildir'):
        raw=row[key]
        p=PurePosixPath(raw)
        if not raw or p.is_absolute() or '..' in p.parts or '\\' in raw or '\x00' in raw:
            raise ValueError('Unsafe mailbox path')
        parts.extend(p.parts)
    p=root.joinpath(*parts)
    if p==root or root.resolve() not in p.resolve().parents:
        raise ValueError('Mailbox path escapes storage')
    if any(x.is_symlink() for x in [p,*p.parents] if x!=root.parent):
        raise ValueError('Symlink in mailbox storage path')
    return p
