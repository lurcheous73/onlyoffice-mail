#!/usr/bin/env python3
"""Record local image IDs and package lists without mounting mail or secrets.

Runs short inspection commands in the selected candidate images, network off.
Writes a new directory only. Does not inspect production containers or volumes.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def record(destination):
    destination.mkdir(mode=0o700)
    images = {}
    for service in ('database', 'mail', 'api', 'filter', 'antivirus', 'redis'):
        name = 'oo-mailserver-' + service + ':dev'
        info = json.loads(run('docker', 'image', 'inspect', name))[0]
        images[service] = {key: info.get(key) for key in ('Id', 'RepoDigests', 'Created', 'Architecture', 'Os')}
        images[service]['tag'] = name
        if service in ('antivirus', 'api', 'filter', 'redis'):
            command = ['apk', 'info', '-v']
        else:
            command = ['dpkg-query', '-W', '-f', '${binary:Package}\t${Version}\n']
        packages = run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', command[0], name, *command[1:])
        (destination / (service + '-packages.txt')).write_text(packages + '\n')
    versions = {}
    for component, service, command in (
        ('postfix', 'mail', ['postconf', '-h', 'mail_version']),
        ('dovecot', 'mail', ['dovecot', '--version']),
        ('mariadb', 'database', ['mariadbd', '--version']),
        ('rspamd', 'filter', ['rspamd', '--version']),
        ('clamav', 'antivirus', ['clamd', '--version']),
        ('redis', 'redis', ['redis-server', '--version']),
    ):
        versions[component] = run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', command[0],
                                  images[service]['tag'], *command[1:])
    versions['loaded_connector_provenance'] = json.loads(run('docker', 'run', '--rm', '--network', 'none',
        '--entrypoint', 'cat', images['mail']['tag'], '/opt/oo-client/provenance.json'))
    result = {'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'images': images, 'components': versions,
              'scope': 'build metadata only; no mail data or credentials mounted'}
    (destination / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'recorded_images': len(images), 'destination': str(destination)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_directory', type=Path)
    args = parser.parse_args()
    record(args.new_directory)
