"""Build-time native Debian client upgrade with pinned package digests.

No mail data, service credentials or Docker socket is available during build.
The packaged library replaces the distribution version; no fallback copy or
dynamic-linker override is installed.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

lock=json.loads(Path('/opt/oo-mail/mariadb-client.lock.json').read_text())
if subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()!='amd64':
    raise SystemExit('This client package lock supports Debian 13 amd64 only')
with tempfile.TemporaryDirectory(prefix='oo-client-build-') as folder:
    packages=[]
    for entry in lock['packages']:
        dest=Path(folder)/(entry['name']+'.deb')
        with urllib.request.urlopen(entry['url'],timeout=60) as response:
            payload=response.read(8*1024*1024+1)
        if len(payload)>8*1024*1024 or hashlib.sha256(payload).hexdigest()!=entry['sha256']:
            raise SystemExit('Native MariaDB package checksum mismatch')
        dest.write_bytes(payload)
        packages.append(str(dest))
    subprocess.run(['dpkg','--force-confnew','--install',*packages],check=True)
subprocess.run(['ldconfig'],check=True)
library=ctypes.CDLL('libmariadb.so.3')
library.mysql_get_client_info.restype=ctypes.c_char_p
version=library.mysql_get_client_info().decode()
if version!='3.4.10':raise SystemExit('Unexpected MariaDB Connector/C runtime version')
for entry in lock['packages']:
    actual=subprocess.check_output(['dpkg-query','-W','-f','${Version}',entry['name']],text=True)
    if actual!=entry['version']:raise SystemExit('Unexpected MariaDB package version')
root=Path('/opt/oo-client');root.mkdir(exist_ok=True)
(root/'provenance.json').write_text(json.dumps(dict(lock,connector_version=version),indent=2)+'\n')
