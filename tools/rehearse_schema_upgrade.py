#!/usr/bin/env python3
"""Test a backed-up v1-to-v2 schema upgrade on a new synthetic volume only.

The stopped source volume is hashed, copied, and never started or modified.
All SQL runs on the independently created copy with Docker network disabled.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from rehearse_backup import archive_tree,capture,compare,guard,run,unlinked,volume_path


def wait(name):
    for _ in range(60):
        ready=subprocess.run(['docker','exec',name,'mariadb','-N','-B','-e','SELECT @@skip_networking'],capture_output=True,text=True)
        # The bootstrap socket is deliberately reachable during the offline
        # upgrade. Wait for the final server, after backup/ALTER/shutdown.
        if ready.returncode==0 and ready.stdout.strip()=='0':return
        time.sleep(1)
    raise ValueError('Copied database did not become ready')


def rows_digest(name):
    command=['docker','exec',name,'mariadb-dump','--skip-comments','--compact','--no-create-info','--skip-add-locks','--skip-disable-keys','--skip-extended-insert','--order-by-primary','onlyoffice_mailserver']
    return hashlib.sha256(subprocess.check_output(command)).hexdigest()


def start(name,image,volume,upgrade=False):
    command=['docker','run','-d','--name',name,'--network','none','-v',volume+':/var/lib/mysql']
    if upgrade:command+=['-e','OO_UPGRADE_RESTORED_COPY=yes']
    run(*command,image);wait(name)


def rehearse(source,project,destination,old_image,new_image):
    if not source.startswith('oo-mail-') or not source.endswith('_database'):raise ValueError('Synthetic source database volume required')
    if run('docker','ps','-q','--filter','volume='+source):raise ValueError('Source must already be stopped')
    root=volume_path(source)
    if not (root/'.oo-mail-schema-1').is_file() or (root/'.oo-mail-schema-2').exists():raise ValueError('Expected a v1 candidate source')
    target=project+'_database'
    if target in run('docker','volume','ls','--format','{{.Name}}').splitlines():raise ValueError('Destination volume exists')
    for image in (old_image,new_image):run('docker','image','inspect',image)
    destination=unlinked(destination);destination.mkdir(mode=0o700)
    capture(root,destination/'source-before.sqlite')
    archive_tree(root,destination/'source-v1.tar')
    run('docker','volume','create','--label','com.docker.compose.project='+project,'--label','com.docker.compose.volume=database',target)
    copied=volume_path(target)
    subprocess.run(['tar','--same-owner','--same-permissions','--acls','--xattrs','-C',str(copied),'-xpf',str(destination/'source-v1.tar')],check=True)
    before=project+'-before'
    start(before,old_image,target)
    try:original=rows_digest(before)
    finally:run('docker','stop',before)
    capture(copied,destination/'guard-before.sqlite')
    probe=subprocess.run(['docker','run','--rm','--network','none','-v',target+':/var/lib/mysql',new_image],capture_output=True,text=True)
    if probe.returncode==0 or 'Schema v1 retained unchanged' not in probe.stderr:raise ValueError('Implicit-upgrade refusal failed')
    capture(copied,destination/'guard-after.sqlite')
    if not compare(destination/'guard-before.sqlite',destination/'guard-after.sqlite')['matches']:raise ValueError('Refusal changed copied data')
    after=project+'-after'
    start(after,new_image,target,upgrade=True)
    try:
        if rows_digest(after)!=original:raise ValueError('Logical records changed during upgrade')
        engines=run('docker','exec',after,'mariadb','-N','-B','-e',"SELECT DISTINCT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA='onlyoffice_mailserver'").splitlines()
        if engines!=['InnoDB']:raise ValueError('Nontransactional table remains')
    finally:run('docker','stop',after)
    backups=list((copied/'.oo-upgrades').glob('*.json'))
    if len(backups)!=1:raise ValueError('Missing unique pre-upgrade receipt')
    receipt=json.loads(backups[0].read_text());backup=copied/'.oo-upgrades'/receipt['backup']
    if hashlib.sha256(backup.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('Upgrade backup digest differs')
    # A normal restart must accept v2 without repeating the schema mutation.
    restart=project+'-restart';start(restart,new_image,target)
    try:
        if rows_digest(restart)!=original:raise ValueError('Logical records changed after restart')
    finally:run('docker','stop',restart)
    if len(list((copied/'.oo-upgrades').glob('*.json')))!=1:raise ValueError('Restart repeated upgrade')
    capture(root,destination/'source-after.sqlite')
    if not compare(destination/'source-before.sqlite',destination/'source-after.sqlite')['matches']:raise ValueError('Original synthetic source changed')
    result={'test':'Schema v1 copy upgrade preserves records and original source','passed':True,'implicit_upgrade_refused_before_mutation':True,'pre_upgrade_locked_sql_backup_verified':True,'all_tables_innodb':True,'restart_idempotent':True,'logical_rows_sha256':original,'source_unchanged':True}
    (destination/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hostname',required=True);p.add_argument('--project',required=True)
    p.add_argument('--source-volume',required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--baseline-image',default='oo-mailserver-database:baseline-cf9a543');p.add_argument('--candidate-image',default='oo-mailserver-database:dev')
    a=p.parse_args();os.umask(0o077)
    try:
        guard(a.hostname,a.project)
        print(json.dumps(rehearse(a.source_volume,a.project,a.destination,a.baseline_image,a.candidate_image)))
    except (ValueError,OSError,subprocess.CalledProcessError,KeyError) as exc:p.exit(1,str(exc)+'\n')
