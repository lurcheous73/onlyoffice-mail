#!/usr/bin/python3
"""PAM adapter: receives the password on stdin, never argv or a log."""
import os
import sys
from auth import authenticate
try:
    raw=sys.stdin.buffer.read(1025).rstrip(b'\0')
    if not 1<=len(raw)<=1024:raise ValueError('Invalid password frame')
    result=authenticate({'user':os.environ.get('PAM_USER',''),
        'service':os.environ.get('PAM_SERVICE','').removeprefix('oo-'),
        'remote':os.environ.get('PAM_RHOST',''),
        'password':raw.decode('utf-8')})
    sys.exit(0 if result['ok'] else 1)
except Exception:
    sys.exit(1)
