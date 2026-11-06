#!/usr/bin/env python3
"""Supply authoritative .invalid DNS inside a fresh synthetic Workspace VM.

No public DNS or production resolver is changed. Original fixture resolver and
hosts files are retained. Re-run in a new fixture after container recreation.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from rehearse_backup import guard,run

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hostname',required=True);p.add_argument('--project',required=True);p.add_argument('--domain',required=True);p.add_argument('--dns-id',type=int,required=True);a=p.parse_args()
guard(a.hostname,a.project)
if run('systemd-detect-virt')!='kvm':p.exit(1,'Dedicated KVM fixture required\n')
if not re.fullmatch(r'[a-z0-9-]+\.invalid',a.domain) or a.dns_id<1:p.exit(1,'Synthetic .invalid domain and positive DNS id required\n')
repo=Path(__file__).resolve().parents[1];attempt=uuid.uuid4().hex[:8];state=repo/'.workspace-test'/('dns-'+attempt)
network=a.project+'_private'
if not json.loads(run('docker','network','inspect',network))[0]['Internal']:p.exit(1,'Internal test network required\n')
ips={}
for service in ('workspace','workspace-db','workspace-search','mail','api','database'):
    d=json.loads(run('docker','inspect',a.project+'-'+service+'-1'))[0]
    if not d['State']['Running']:p.exit(1,'Start the synthetic '+service+' service before preparing DNS\n')
    ips[service]=str(ipaddress.IPv4Address(d['NetworkSettings']['Networks'][network]['IPAddress']))
state.mkdir(mode=0o700)
query="SELECT JSON_OBJECT('mx',mx,'spf',spf,'selector',dkim_selector,'public_key',dkim_public_key,'domain_check',domain_check) FROM mail_server_dns WHERE id="+str(a.dns_id)+';'
command=['docker','exec','-i',a.project+'-workspace-db-1','sh','-c','export MYSQL_PWD="$(cat /run/secrets/workspace_app)"; exec mysql -N -B --raw -uonlyoffice_user onlyoffice']
record=json.loads(subprocess.run(command,input=query,text=True,check=True,capture_output=True).stdout)
if record['mx']!='mail.lab.invalid' or not re.fullmatch('[A-Za-z0-9_-]+',record['selector']):p.exit(1,'Unexpected fixture DNS metadata\n')
def txt(value):
    if any(c in value for c in ('\r','\n','\0')):raise ValueError('Invalid TXT content')
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
lines=['no-resolv','no-hosts','bind-interfaces','port=53','user=nobody','group=nobody','local-ttl=30']
aliases={'workspace':['workspace.lab.invalid','onlyoffice-community-server'],'workspace-search':['onlyoffice-elasticsearch'],'mail':['mail.lab.invalid','onlyoffice-mail-server']}
for service,ip in ips.items():lines.append('host-record='+','.join([service,*aliases.get(service,[]),ip]))
lines+=['host-record='+a.domain+','+ips['mail'],'mx-host='+a.domain+',mail.lab.invalid,0',
        'txt-record='+a.domain+','+txt(record['spf']),'txt-record='+a.domain+','+txt(record['domain_check']),
        'txt-record='+record['selector']+'._domainkey.'+a.domain+','+','.join(txt(record['public_key'][i:i+255]) for i in range(0,len(record['public_key']),255))]
config=state/'dnsmasq.conf';config.write_text('\n'.join(lines)+'\n')
name=a.project+'-workspace-dns-'+attempt
run('docker','run','-d','--name',name,'--network',network,'--memory','64m','--read-only','--tmpfs','/run:size=1m,mode=0755','-v',str(config)+':/etc/dnsmasq.conf:ro','oo-mailserver-workspace-dns-fixture:dev')
d=json.loads(run('docker','inspect',name))[0];ip=str(ipaddress.IPv4Address(d['NetworkSettings']['Networks'][network]['IPAddress']))
for _ in range(20):
    probe=subprocess.run(['docker','exec',name,'nslookup','-type=MX',a.domain,'127.0.0.1'],capture_output=True,text=True)
    if probe.returncode==0 and record['mx'] in probe.stdout:break
    time.sleep(.25)
else:p.exit(1,'Private DNS fixture did not answer its MX readiness probe; attempt retained\n')
workspace=a.project+'-workspace-1'
for name in ('resolv.conf','hosts'):
    original=subprocess.check_output(['docker','exec',workspace,'cat','/etc/'+name])
    (state/(name+'.before')).write_bytes(original)
resolver='nameserver '+ip+'\noptions ndots:0\n'
subprocess.run(['docker','exec','-i',workspace,'sh','-c','cat > /etc/resolv.conf'],input=resolver,text=True,check=True)
hosts='\n'.join(value+' '+service+' '+' '.join(aliases.get(service,[])) for service,value in ips.items())+'\n'
subprocess.run(['docker','exec','-i',workspace,'sh','-c','cat >> /etc/hosts'],input=hosts,text=True,check=True)
(state/'receipt.json').write_text(json.dumps({'synthetic_domain':a.domain,'dns_record_id':a.dns_id,'dns_container':name,'dns_ip':ip,'public_dns_changed':False,'original_fixture_resolver_retained':True},indent=2)+'\n')
print(json.dumps({'synthetic_domain':a.domain,'private_dns_ready':True,'public_dns_changed':False}))
