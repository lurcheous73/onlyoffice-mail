#!/usr/bin/python3
import os
import grp
from pathlib import Path
import pwd
import re
password=Path('/run/secrets/filter_password').read_text().strip()
if not re.fullmatch('[0-9a-f]{64}',password):raise SystemExit('Invalid controller secret')
config=Path('/etc/rspamd/local.d/worker-controller.inc')
config.write_text('bind_socket="0.0.0.0:11334";\npassword="'+password+'";\nenable_password="'+password+'";\nsecure_ip="127.0.0.1";\n')
uid=pwd.getpwnam('rspamd').pw_uid;gid=grp.getgrnam('rspamd').gr_gid
os.chown(config,0,gid);os.chmod(config,0o640)
# The package's service UID differs from the earlier Debian lab image. Retain
# classifier data while giving the selected service identity its own volume.
root=Path('/var/lib/rspamd');root.mkdir(exist_ok=True)
for directory,dirs,files in os.walk(root,followlinks=False):
    for path in [Path(directory),*(Path(directory)/name for name in dirs+files)]:
        os.chown(path,uid,gid,follow_symlinks=False)
os.execvp('rspamd',['rspamd','-f','-u','rspamd','-g','rspamd'])
