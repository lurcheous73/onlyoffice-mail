#!/usr/bin/env python3
"""Prepare an empty client fixture on a dedicated KVM test VM only."""
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hostname',required=True);a=p.parse_args()
if os.geteuid()!=0 or socket.gethostname()!=a.hostname or not a.hostname.endswith('-lab'):
    p.exit(1,'Dedicated root-operated -lab host required\n')
if subprocess.check_output(['systemd-detect-virt'],text=True).strip()!='kvm':
    p.exit(1,'The privileged legacy client fixture requires a separate KVM VM\n')
root=Path(__file__).resolve().parents[1]/'.workspace-test'
if root.exists() or root.is_symlink():p.exit(1,'Existing fixture state retained; refusing overwrite\n')
os.umask(0o077);root.mkdir();(root/'secrets').mkdir()
for name in ('workspace_root','workspace_app','workspace_machinekey'):
    dest=root/'secrets'/name;dest.write_text(secrets.token_hex(32)+'\n');os.chmod(dest,0o444)
print('Fresh synthetic Workspace fixture prepared; no production credentials or data used.')
