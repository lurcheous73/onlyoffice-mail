#!/usr/bin/python3
import os
from pathlib import Path
import re
password=Path('/run/secrets/filter_password').read_text().strip()
if not re.fullmatch('[0-9a-f]{64}',password):raise SystemExit('Invalid controller secret')
Path('/etc/rspamd/local.d/worker-controller.inc').write_text('bind_socket="0.0.0.0:11334";\npassword="'+password+'";\nenable_password="'+password+'";\nsecure_ip="127.0.0.1";\n')
os.execvp('rspamd',['rspamd','-f','-u','_rspamd','-g','_rspamd'])
