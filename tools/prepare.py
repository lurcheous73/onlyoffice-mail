#!/usr/bin/env python3
"""Create fresh lab credentials and a private test CA. No Docker commands."""
import os
from pathlib import Path
import secrets
import subprocess

ROOT=Path(__file__).resolve().parents[1]
state=ROOT/'.state'
if state.exists(): raise SystemExit('State already exists; refusing to overwrite credentials or data')
os.umask(0o077)
state.mkdir()
for name in ('secrets','tls'):(state/name).mkdir()
for name in ('reader_db','auth_db','api_db','oo_db','api_token','filter_password'):
    (state/'secrets'/name).write_text(secrets.token_hex(32)+'\n')
    # API runs as uid 5000. Docker Compose file secrets are bind mounts.
    os.chmod(state/'secrets'/name,0o444)
def run(*args):
    subprocess.run(args,cwd=state/'tls',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
run('openssl','req','-x509','-newkey','rsa:3072','-nodes','-days','30','-subj','/CN=OO Mail Lab CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout','ca.key','-out','ca.crt')
run('openssl','req','-newkey','rsa:3072','-nodes','-subj','/CN=mail.lab.invalid','-keyout','server.key','-out','server.csr')
(state/'tls'/'server.ext').write_text('subjectAltName=DNS:mail.lab.invalid,DNS:mail\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n')
run('openssl','x509','-req','-in','server.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-days','30','-extfile','server.ext','-out','server.crt')
os.chmod(state/'tls'/'ca.crt',0o444)
os.chmod(state/'tls'/'server.crt',0o444)
print('Fresh synthetic lab prepared. Certificates expire in 30 days; use your own reviewed TLS material for production.')
