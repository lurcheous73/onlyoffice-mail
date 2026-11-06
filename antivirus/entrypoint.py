import os
from pathlib import Path
import pwd
import sys
import time

root=Path('/var/lib/clamav')
root.mkdir(exist_ok=True)
account=pwd.getpwnam('clamav')
uid,gid=account.pw_uid,account.pw_gid
os.chown(root,uid,gid)
for item in root.iterdir():
    if item.is_symlink():raise SystemExit('Linked antivirus database requires review')
    if item.is_file():os.chown(item,uid,gid)
if len(sys.argv)>1 and sys.argv[1]=='update':
    Path('/etc/clamav/freshclam.conf').write_text('DatabaseDirectory /var/lib/clamav\nDatabaseOwner clamav\nDatabaseMirror database.clamav.net\nForeground true\nConnectTimeout 15\nReceiveTimeout 120\nChecks 12\n')
    os.execvp('freshclam',['freshclam','--stdout'])
daily=[p for p in [root/'daily.cvd',root/'daily.cld'] if p.exists()]
if not daily or time.time()-max(p.stat().st_mtime for p in daily)>3*86400:
    raise SystemExit('No recent antivirus database. Run the explicit signature-update job before starting mail.')
Path('/etc/clamav/clamd.conf').write_text('''Foreground true
LogTime true
DatabaseDirectory /var/lib/clamav
TCPSocket 3310
TCPAddr 0.0.0.0
User clamav
MaxThreads 2
MaxQueue 20
MaxConnectionQueueLength 20
StreamMaxLength 27M
MaxScanSize 100M
MaxFileSize 27M
MaxRecursion 16
SelfCheck 300
''')
os.execvp('clamd',['clamd','--foreground=true'])
