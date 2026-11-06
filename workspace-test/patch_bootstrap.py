"""Narrow fixes to the pinned legacy CLIENT test fixture's bootstrap."""
from pathlib import Path
import subprocess

p=Path('/app/run-community-server.sh');s=p.read_text()
if s.count('mysqladmin shutdown')!=2:raise SystemExit('Unexpected upstream shutdown calls; inspect before applying fixture patch')
# Upstream's generated global client files can point unqualified mysqladmin at
# the external database. Its local-service cleanup must target localhost only.
s=s.replace('mysqladmin shutdown','mysqladmin --defaults-file=/dev/null --host=127.0.0.1 --protocol=tcp shutdown')
s=s.replace('set -x','set +x')
s='\n'.join('        :' if 'echo "mysql mail server access token is' in line else line for line in s.split('\n'))
p.write_text(s)
subprocess.run(['bash','-n',str(p)],check=True)
