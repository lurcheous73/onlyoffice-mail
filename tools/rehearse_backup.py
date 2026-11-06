#!/usr/bin/env python3
"""Back up a STOPPED synthetic candidate and restore to new lab volumes.

Private archives include database credentials and signing keys. This is a
same-image candidate recovery rehearsal, not a legacy MySQL conversion tool.
It never stops services, removes volumes, overwrites files or contacts a host.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import tarfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'migration'))
from file_audit import capture,compare,unlinked


def run(*args):
    return subprocess.check_output(args,text=True).strip()


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def guard(hostname,project):
    if os.geteuid()!=0 or not hostname.endswith('-lab') or socket.gethostname()!=hostname:
        raise ValueError('Use root on the explicitly named dedicated -lab host')
    if not re.fullmatch(r'oo-mail-[a-z0-9-]+',project):raise ValueError('Dedicated oo-mail- lab project required')
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):raise ValueError('Remote Docker overrides refused')
    context=json.loads(run('docker','context','inspect'))[0]
    if context['Endpoints']['docker']['Host']!='unix:///var/run/docker.sock':raise ValueError('Local Docker socket required')


def volume_path(name):
    return unlinked(Path(json.loads(run('docker','volume','inspect',name))[0]['Mountpoint']))


def validate_tar(path):
    entries={}
    with tarfile.open(path) as archive:
        for member in archive:
            name=PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts:raise ValueError('Unsafe archive path')
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):raise ValueError('Special archive entry refused')
            if member.issym() or member.islnk():
                target=PurePosixPath(member.linkname)
                if target.is_absolute():raise ValueError('Absolute archive link refused')
                parts=[]
                for part in ((name.parent/target).parts if member.issym() else target.parts):
                    if part=='..':
                        if not parts:raise ValueError('Escaping archive link refused')
                        parts.pop()
                    elif part!='.':parts.append(part)
            if name in entries:raise ValueError('Duplicate archive member')
            entries[name]=member
        for name in entries:
            for parent in name.parents:
                if parent in entries and not entries[parent].isdir():raise ValueError('Non-directory archive parent')


def archive_tree(root,dest):
    with dest.open('xb') as out:
        subprocess.run(['tar','--numeric-owner','--acls','--xattrs','--sparse','--one-file-system','--format=posix','-C',str(root),'-cpf','-','.'],stdout=out,check=True)
    os.chmod(dest,0o600)
    validate_tar(dest)


def backup(checkout,project,destination):
    checkout=unlinked(checkout).resolve(strict=True);destination=unlinked(destination)
    if destination==checkout or checkout in destination.parents:raise ValueError('Backup must be outside checkout')
    config=json.loads(run('docker','compose','-f',str(checkout/'compose.json'),'-p',project,'config','--format','json'))
    ids=run('docker','ps','-aq','--filter','label=com.docker.compose.project='+project).splitlines()
    if not ids:raise ValueError('No stopped source project containers')
    containers=json.loads(run('docker','inspect',*ids));names={};actual_images={}
    for container in containers:
        if container['State']['Running']:raise ValueError('Source project must already be stopped')
        service=container['Config']['Labels']['com.docker.compose.service']
        if service not in config['services']:continue
        actual_images[service]=container['Image']
        if any(container['HostConfig'].get('PortBindings',{}).values()):raise ValueError('Published source ports refused')
        for network in container['NetworkSettings']['Networks']:
            if not json.loads(run('docker','network','inspect',network))[0]['Internal']:raise ValueError('Non-internal source network refused')
        for declaration in config['services'][service].get('volumes',[]):
            if declaration['type']!='volume':continue
            key=declaration['source']
            if key not in config['volumes']:
                key=next(k for k,v in config['volumes'].items() if v['name']==key)
            mount=next(m for m in container['Mounts'] if m['Destination']==declaration['target'])
            name=mount['Name']
            if key in names and names[key]!=name:raise ValueError('Inconsistent source mounts')
            names[key]=name
    if set(names)!=set(config['volumes']):raise ValueError('Unresolved runtime volumes')
    for name in names.values():
        if run('docker','ps','-q','--filter','volume='+name):raise ValueError('All volume users must already be stopped: '+name)
    destination.mkdir(mode=0o700)
    manifest={'format':1,'project':project,'volumes':{},'files':{},'images':{},'scope':'stopped synthetic candidate; same runtime images only'}
    for key,name in names.items():
        root=volume_path(name)
        before=destination/(key+'.sqlite');after=destination/(key+'-after.sqlite')
        summary=capture(root,before,skip_postfix_sockets=(key=='queue'),skip_rspamd_socket=(key=='filterdata'))
        archive=destination/(key+'.tar');archive_tree(root,archive)
        after_summary=capture(root,after,skip_postfix_sockets=(key=='queue'),skip_rspamd_socket=(key=='filterdata'))
        if summary['excluded_runtime_sockets']!=after_summary['excluded_runtime_sockets']:raise ValueError('Runtime socket set changed')
        if not compare(before,after)['matches']:raise ValueError('Source changed during backup: '+key)
        manifest['volumes'][key]={'source':name,'archive':archive.name,'tree':before.name,'summary':summary}
    selected=['compose.json','.state','api','db','mail','filter','antivirus','tests','tools','migration','docs/oo-sql-contract.json','.dockerignore','upstream.lock.json']
    config_tar=destination/'private-config.tar'
    with config_tar.open('xb') as out:
        subprocess.run(['tar','--numeric-owner','--acls','--xattrs','--format=posix','-C',str(checkout),'-cpf','-',*selected],stdout=out,check=True)
    os.chmod(config_tar,0o600);validate_tar(config_tar)
    for key,service in config['services'].items():
        if 'image' in service:
            manifest['images'][key]=actual_images.get(key) or json.loads(run('docker','image','inspect',service['image']))[0]['Id']
    for path in destination.iterdir():
        if path.is_file():manifest['files'][path.name]={'bytes':path.stat().st_size,'sha256':digest(path)}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return {'backed_up_volumes':len(names),'source_unchanged':True,'private_bundle':str(destination)}


def restore(bundle,project,destination):
    bundle=unlinked(bundle).resolve(strict=True);destination=unlinked(destination)
    manifest=json.loads((bundle/'manifest.json').read_text())
    if manifest['format']!=1 or project==manifest['project']:raise ValueError('New destination project required')
    if destination.exists() or destination.is_symlink():raise ValueError('Restore checkout already exists')
    for name,entry in manifest['files'].items():
        if Path(name).name!=name:raise ValueError('Unsafe bundle filename')
        path=bundle/name
        if path.is_symlink() or path.stat().st_size!=entry['bytes'] or digest(path)!=entry['sha256']:raise ValueError('Bundle hash mismatch')
        if name.endswith('.tar'):validate_tar(path)
    for entry in manifest['volumes'].values():
        for field in ('archive','tree'):
            if entry[field] not in manifest['files'] or Path(entry[field]).name!=entry[field]:raise ValueError('Unverified volume artifact')
    existing=set(run('docker','volume','ls','--format','{{.Name}}').splitlines())
    for key in manifest['volumes']:
        if not re.fullmatch('[a-z][a-z0-9_]*',key) or project+'_'+key in existing:raise ValueError('Existing/unsafe destination volume')
    for image in manifest['images'].values():run('docker','image','inspect',image)
    destination.mkdir(mode=0o700)
    subprocess.run(['tar','--same-owner','--same-permissions','--acls','--xattrs','-C',str(destination),'-xpf',str(bundle/'private-config.tar')],check=True)
    results={}
    for key,entry in manifest['volumes'].items():
        name=project+'_'+key
        run('docker','volume','create','--label','com.docker.compose.project='+project,'--label','com.docker.compose.volume='+key,name)
        root=volume_path(name)
        subprocess.run(['tar','--same-owner','--same-permissions','--acls','--xattrs','-C',str(root),'-xpf',str(bundle/entry['archive'])],check=True)
        audit=destination/(key+'-restored.sqlite');capture(root,audit)
        result=compare(bundle/entry['tree'],audit)
        if not result['matches']:raise ValueError('Restored tree differs: '+key)
        results[key]=result
    override={'services':{key:{'image':image,'pull_policy':'never'} for key,image in manifest['images'].items()}}
    (destination/'restored-images.json').write_text(json.dumps(override,indent=2)+'\n')
    receipt={'restored_volumes':len(results),'exact_metadata_and_bytes':True,'source_project':manifest['project'],'target_project':project,'comparison':results,'private_bundle_manifest_sha256':digest(bundle/'manifest.json')}
    (destination/'restore-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['backup','restore']);p.add_argument('--hostname',required=True)
    p.add_argument('--project',required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--checkout',type=Path);p.add_argument('--bundle',type=Path)
    a=p.parse_args();os.umask(0o077)
    try:
        guard(a.hostname,a.project)
        if a.action=='backup':result=backup(a.checkout,a.project,a.destination)
        else:result=restore(a.bundle,a.project,a.destination)
        print(json.dumps(result))
    except (ValueError,OSError,subprocess.CalledProcessError,KeyError,TypeError) as exc:p.exit(1,str(exc)+'\n')
