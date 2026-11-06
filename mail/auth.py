#!/usr/bin/python3
"""PAM password verification with transparent Argon2id upgrades.

OO 12.8 writes MD5-CRYPT. Accept only explicitly supported legacy formats,
verify them through libxcrypt, and replace after a successful login. Password
changes made concurrently are protected by a compare-and-swap update.
"""
import ctypes
import hmac
import ipaddress
from argon2 import PasswordHasher, exceptions
from common import address,connect,mailbox_path

HASHER=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=1)

def verify_password(stored, supplied):
    if not isinstance(supplied,str) or not 1<=len(supplied.encode())<=1024 or '\x00' in supplied:
        return False,False
    if stored.startswith('{ARGON2ID}'):
        stored=stored[10:]
    if stored.startswith('$argon2id$'):
        try:
            return HASHER.verify(stored,supplied), HASHER.check_needs_rehash(stored)
        except (exceptions.VerificationError,exceptions.InvalidHashError):
            return False,False
    if stored.startswith('{CRYPT}'):
        stored=stored[7:]
    if not stored.startswith(('$1$','$5$','$6$','$2y$','$y$')) or len(stored)>255:
        return False,False
    lib=ctypes.CDLL('libcrypt.so.1')
    lib.crypt.argtypes=[ctypes.c_char_p,ctypes.c_char_p]
    lib.crypt.restype=ctypes.c_char_p
    result=lib.crypt(supplied.encode(),stored.encode())
    return bool(result and hmac.compare_digest(result,stored.encode())),True

def authenticate(request):
    user=address(request.get('user','').lower())
    service=request.get('service','')
    flags={'imap':('enableimap','enableimapsecured'),
           'pop3':('enablepop3','enablepop3secured'),
           'smtp':('enablesmtp','enablesmtpsecured'),
           'sieve':('enablemanagesieve','enablemanagesievesecured')}
    if service not in flags:
        return {'ok':False}
    plain,tls=flags[service]
    with connect('mailauth','auth_db') as db,db.cursor() as c:
        c.execute('SELECT m.* FROM mailbox m JOIN domain d ON d.domain=m.domain '
                  'WHERE m.username=%s AND m.active=1 AND d.active=1 AND d.backupmx=0 '
                  'AND m.expired>UTC_TIMESTAMP() AND d.expired>UTC_TIMESTAMP() '
                  f'AND m.`{plain}`=1 AND m.`{tls}`=1',(user,))
        row=c.fetchone()
        if not row:
            # Spend comparable work on unknown users; never disclose existence.
            HASHER.hash('unknown-user-placeholder')
            return {'ok':False}
        mailbox_path(row)
        if row.get('allow_nets'):
            try:
                remote=ipaddress.ip_address(request.get('remote',''))
                nets=[ipaddress.ip_network(x.strip(),strict=False) for x in row['allow_nets'].replace(' ',',').split(',') if x.strip()]
                if not nets or not any(remote in net for net in nets):return {'ok':False}
            except ValueError:return {'ok':False}
        ok,upgrade=verify_password(row['password'],request.get('password',''))
        if not ok:
            return {'ok':False}
        if upgrade:
            strong='{ARGON2ID}'+HASHER.hash(request['password'])
            c.execute('UPDATE mailbox SET password=%s WHERE username=%s AND password=%s',
                      (strong,user,row['password']))
            if c.rowcount!=1:
                return {'ok':False}
        return {'ok':True,'user':user}

