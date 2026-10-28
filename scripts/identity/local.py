#!/usr/bin/env python3
"""Persistent localhost-only Authentik bootstrap, separate from disposable tests."""
import argparse
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
BASE=Path('/var/lib/agent-platform/identity-local')
PROJECT='agent-platform-identity-local'
URL='http://127.0.0.1:9000'
ADMIN_UID=0
DATA_UIDS={'database':70,'data':1000,'certs':1000}
SECRET_UIDS={'postgres-password':70,'authentik-password':1000,'authentik-secret':1000}
class LocalError(ValueError):pass


def native():
    spec=importlib.util.spec_from_file_location('local_identity_native',ROOT/'scripts/identity/native-check.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def bundle():
    helper=native();lock,_=helper.bundle()
    raw=(ROOT/'infra/identity/local-compose.yaml').read_text()
    if hashlib.sha256(raw.encode()).hexdigest()!=TEMPLATE_SHA256:raise LocalError('local_template_drift')
    template=helper.source_module().parse(raw)
    if set(template['services'])!={'database','server','worker'} or template['networks']!={'database':{'internal':True},'frontend':{}}:
        raise LocalError('local_topology_drift')
    for name,service in template['services'].items():
        if (service.get('read_only') is not True or service.get('cap_drop')!=['ALL']
            or service.get('security_opt')!=['no-new-privileges:true','apparmor:docker-default']):raise LocalError('local_process_drift')
        ports=service.get('ports',[])
        if ports!=(['127.0.0.1:9000:9000'] if name=='server' else []):raise LocalError('local_port_exposure')
    values={'POSTGRES_IMAGE':lock['postgres']['image'],'AUTHENTIK_IMAGE':lock['authentik']['image'],
            'PRIVATE_DIR':str(BASE/'secrets'),'STATE_DIR':str(BASE)}
    def substitute(match):
        if match[1] not in values:raise LocalError('unknown_local_template_input')
        return values[match[1]]
    rendered=re.sub(r'\$\{([A-Z_]+)\}',substitute,raw)
    return helper,lock,rendered,helper.source_module().parse(rendered)


def directory(path,uid,mode=0o700):
    meta=path.lstat()
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=uid or stat.S_IMODE(meta.st_mode)!=mode:
        raise LocalError('unsafe_identity_directory')


def ancestors(create=False):
    for path in reversed([BASE.parent,*BASE.parent.parents]):
        if not path.exists():
            if not create:raise LocalError('identity_environment_setup_required')
            path.mkdir(mode=0o700)
        meta=path.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=ADMIN_UID or meta.st_mode&0o022:
            raise LocalError('unsafe_identity_parent')


def read_file(path,uid,mode,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        meta=os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid!=uid or meta.st_nlink!=1
            or stat.S_IMODE(meta.st_mode)!=mode or not 0<meta.st_size<=limit):raise LocalError('unsafe_identity_file')
        return os.read(fd,limit+1)
    finally:os.close(fd)


def write_file(path,content,uid,mode):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:os.write(fd,content);os.fchown(fd,uid,uid);os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)


def manifest(lock,rendered):
    return {'schema_version':1,'purpose':'persistent_loopback_identity_bootstrap','project':PROJECT,
            'images':{name:lock[name]['image'] for name in ('authentik','postgres')},
            'compose_sha256':hashlib.sha256(rendered.encode()).hexdigest()}


def check_state(lock,rendered):
    ancestors();directory(BASE,ADMIN_UID)
    if not (BASE/'manifest.json').exists():raise LocalError('incomplete_identity_state_no_auto_repair')
    directory(BASE/'secrets',ADMIN_UID)
    try:
        source=native().source_module()
        current=source.parse(read_file(BASE/'manifest.json',ADMIN_UID,0o600,4096))
        if not isinstance(current,dict):raise LocalError('identity_state_version_drift')
        fingerprints=current.pop('secret_sha256',None)
        if not isinstance(fingerprints,dict) or set(fingerprints)!=set(SECRET_UIDS) or any(not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value) for value in fingerprints.values()):
            raise LocalError('identity_state_version_drift')
        if not source.same(current,manifest(lock,rendered)):raise LocalError('identity_state_version_drift')
        if read_file(BASE/'compose.yaml',ADMIN_UID,0o600,32768)!=rendered.encode():raise LocalError('identity_compose_drift')
        for name,uid in DATA_UIDS.items():directory(BASE/name,uid)
        contents={}
        for name,uid in SECRET_UIDS.items():
            raw=read_file(BASE/'secrets'/name,uid,0o400,96)
            if not re.fullmatch(rb'[a-f0-9]{'+str(96 if name=='authentik-secret' else 64).encode()+rb'}',raw):raise LocalError('invalid_identity_secret')
            contents[name]=raw
        if not hmac.compare_digest(contents['postgres-password'],contents['authentik-password']):raise LocalError('identity_password_copies_differ')
        if any(not hmac.compare_digest(fingerprints[name],hashlib.sha256(raw).hexdigest()) for name,raw in contents.items()):
            raise LocalError('identity_secret_integrity_drift')
    except FileNotFoundError:raise LocalError('incomplete_identity_state_no_auto_repair') from None


def setup(lock,rendered):
    ancestors(create=True)
    if BASE.exists() or BASE.is_symlink():
        check_state(lock,rendered);return {'status':'prepared','existing_state_preserved':True}
    if shutil.disk_usage(BASE.parent).free<10*1024**3:raise LocalError('less_than_10_gib_storage_available')
    BASE.mkdir(mode=0o700);(BASE/'secrets').mkdir(mode=0o700)
    # Deliberately leave incomplete state for review if interrupted: never rotate silently.
    for name,uid in DATA_UIDS.items():
        path=BASE/name;path.mkdir(mode=0o700);os.chown(path,uid,uid)
    password=secrets.token_hex(32).encode();fingerprints={}
    for name,uid in SECRET_UIDS.items():
        value=secrets.token_hex(48).encode() if name=='authentik-secret' else password
        write_file(BASE/'secrets'/name,value,uid,0o400)
        fingerprints[name]=hashlib.sha256(value).hexdigest()
    write_file(BASE/'compose.yaml',rendered.encode(),ADMIN_UID,0o600)
    document=manifest(lock,rendered);document['secret_sha256']=fingerprints
    write_file(BASE/'manifest.json',json.dumps(document,sort_keys=True).encode(),ADMIN_UID,0o600)
    check_state(lock,rendered)
    return {'status':'prepared','existing_state_preserved':False}


INSPECT='''{"image":{{json .Config.Image}},"user":{{json .Config.User}},"labels":{{json .Config.Labels}},"state":{"Running":{{json .State.Running}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}"none"{{end}}},"command":{{json .Config.Cmd}},"entrypoint":{{json .Config.Entrypoint}},"host":{{json .HostConfig}},"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}},"apparmor":{{json .AppArmorProfile}}}'''

def runtime(engine,config,require_all=False,*,project=PROJECT,address='127.0.0.1',port=9000,internal_networks=('database',)):
    _,output=engine.run(['ps','--all','--quiet','--filter','label=com.docker.compose.project='+project])
    ids=output.decode().split()
    if len(ids)>3 or any(not re.fullmatch('[a-f0-9]{12,64}',cid) for cid in ids):raise LocalError('identity_selection_failed')
    results={}
    for cid in ids:
        _,raw=engine.run(['inspect','--format',INSPECT,cid]);info=json.loads(raw)
        labels=info.get('labels') or {};service=labels.get('com.docker.compose.service')
        if labels.get('com.docker.compose.project')!=project or service not in config['services'] or service in results:
            raise LocalError('foreign_identity_container')
        expected=config['services'][service];host=info.get('host') or {};state=info.get('state') or {}
        options={item.replace(':','=',1) for item in (host.get('SecurityOpt') or [])}
        mounts={(item['Source'],item['Destination'],item['RW']) for item in info['mounts'] if item['Type']=='bind'}
        wanted={(item['source'],item['target'],not item.get('read_only',False)) for item in expected['volumes']}
        networks={project+'_'+name for name in expected['networks']}
        sizes={'768m':768*1024**2,'1g':1024**3,'2g':2*1024**3}
        if (info.get('command')!=expected.get('command',['postgres'])
            or info.get('entrypoint')!=(['docker-entrypoint.sh'] if service=='database' else ['dumb-init','--','ak'])
            or info.get('image')!=expected['image'] or info.get('user')!=expected['user'] or host.get('ReadonlyRootfs') is not True
            or set(host.get('CapDrop') or [])!={'ALL'} or host.get('CapAdd') or host.get('Privileged') or host.get('Devices') or host.get('DeviceRequests')
            or options!={'no-new-privileges=true','apparmor=docker-default'} or info.get('apparmor')!='docker-default'
            or host.get('PidMode')!='' or host.get('IpcMode') not in ('private','shareable') or host.get('UTSMode')!=''
            or host.get('NetworkMode') not in networks or host.get('Memory')!=sizes[expected['mem_limit']]
            or host.get('NanoCpus')!=int(expected['cpus']*1_000_000_000) or host.get('PidsLimit')!=expected['pids_limit']
            or host.get('LogConfig')!={'Type':expected['logging']['driver'],'Config':expected['logging'].get('options',{})}
            or mounts!=wanted or any(item['Type'] not in ('bind','tmpfs') for item in info['mounts'])
            or (host.get('Tmpfs') or {})!=dict(item.split(':',1) for item in expected['tmpfs'])):
            raise LocalError('identity_runtime_restriction_drift')
        bindings=host.get('PortBindings') or {}
        wanted_ports={'9000/tcp':[{'HostIp':address,'HostPort':str(port)}]} if service=='server' else {}
        if bindings!=wanted_ports:raise LocalError('identity_runtime_port_exposure')
        if state.get('Running') is True and set(info['networks'])!=networks:raise LocalError('identity_runtime_network_drift')
        if state.get('Running') is True:
            for network in networks:
                _,raw=engine.run(['network','inspect','--format','{"driver":{{json .Driver}},"internal":{{json .Internal}}}',network])
                data=json.loads(raw)
                if data!={'driver':'bridge','internal':network in {project+'_'+item for item in internal_networks}}:raise LocalError('identity_network_policy_drift')
        health=state.get('health','none')
        results[service]={'running':state.get('Running') is True,'health':health if health in ('none','healthy','unhealthy','starting') else 'unknown'}
    if require_all and (set(results)!=set(config['services']) or any(not r['running'] or r['health']!='healthy' for r in results.values())):
        raise LocalError('identity_services_not_healthy')
    return results


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def http_ready(url=URL):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(url+'/-/health/ready/',timeout=5) as response:return response.status==200
    except (OSError,urllib.error.URLError):return False


def operate(mode,engine,lock,rendered,config):
    check_state(lock,rendered)
    compose=['compose','--project-name',PROJECT,'--file',str(BASE/'compose.yaml')]
    observed=runtime(engine,config)
    if mode=='down':
        engine.run([*compose,'down','--timeout','15'],timeout=90)
        return {'status':'stopped','persistent_state_preserved':True}
    if mode=='status':return {'status':'collected','services':observed}
    if mode=='up':
        memory=re.search(r'^MemAvailable:\s+(\d+) kB$',Path('/proc/meminfo').read_text(),re.M)
        if not memory or int(memory[1])<6*1024**2:raise LocalError('less_than_6_gib_available')
        if 'server' not in observed:
            with socket.socket() as listener:
                try:listener.bind(('127.0.0.1',9000))
                except OSError:raise LocalError('identity_loopback_port_in_use') from None
        for name in ('postgres','authentik'):
            print('[identity-local] Checking pinned '+name+' image.',file=sys.stderr,flush=True)
            engine.run(['pull','--platform','linux/amd64',lock[name]['image']],timeout=1200)
        engine.run([*compose,'config','--quiet'])
        print('[identity-local] Starting database, server and worker on localhost only.',file=sys.stderr,flush=True)
        engine.run([*compose,'up','-d','--pull','never','--wait','--wait-timeout','300'],timeout=330)
    observed=runtime(engine,config,require_all=True)
    if not http_ready():raise LocalError('identity_http_not_ready')
    return {'status':'passed','services':observed,'ui_url':URL,'admin_setup':'manual_native_ui',
            'blueprint_application':'not_performed_by_this_task','browser_mfa_acceptance':'pending'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','setup','up','check','status','down']);args=parser.parse_args()
    try:
        helper,lock,rendered,config=bundle()
        if args.mode=='plan':
            report={'status':'prepared','ui_url':URL,'private_state':str(BASE),'services':list(config['services']),
                    'scope':'Persistent loopback bootstrap only; no blueprint application, family accounts, CA or LAN exposure'}
        else:
            if os.geteuid()!=0:raise LocalError('host_admin_required')
            ancestors(create=args.mode=='setup')
            # Serialize setup/up/down without making unrelated storage operations wait.
            fd=os.open(BASE.parent/'identity-local.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
            try:
                meta=os.fstat(fd)
                if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=0 or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)!=0o600:raise LocalError('unsafe_identity_lock')
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise LocalError('identity_operation_in_progress') from None
                report=setup(lock,rendered) if args.mode=='setup' else operate(args.mode,helper.Engine(),lock,rendered,config)
            finally:os.close(fd)
    except LocalError as exc:report={'status':'failed','error':str(exc)}
    except Exception as exc:
        allowed={'docker_command_timeout','docker_command_failed','oversized_native_output'}
        report={'status':'failed','error':str(exc) if str(exc) in allowed else 'identity_local_operation_failed_details_withheld'}
    report['household_readiness']='pending'
    report['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('infra/identity/local-compose.yaml','scripts/identity/local.py','infra/identity/versions.yaml')}
    print(json.dumps(report,indent=2));return int(report['status']=='failed')

TEMPLATE_SHA256='cfacf2ece3d10b5037ca190dc44b9949f34485aa385caa6de47b0f12addac8c1'
if __name__=='__main__':raise SystemExit(main())
