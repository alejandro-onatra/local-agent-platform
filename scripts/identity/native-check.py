#!/usr/bin/env python3
"""Plan or run a unique disposable native identity check; never reuse an IdP DB."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import yaml

ROOT=Path(__file__).resolve().parents[2]
LOCK=ROOT/'infra/identity/versions.yaml'
TEMPLATE=ROOT/'infra/identity/native-compose.yaml'
PREFIX='agent-platform-identity-check-'
class CheckError(ValueError):
    def __init__(self,code,cleanup='not_started',issues=None):
        super().__init__(code);self.cleanup=cleanup;self.issues=issues


def source_module():
    spec=importlib.util.spec_from_file_location('native_identity_source',ROOT/'scripts/identity/check-source.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def bundle():
    source=source_module();source.validate(source.parse(source.BLUEPRINT.read_bytes()))
    lock=yaml.load(LOCK.read_text(),Loader=source.Loader)
    if set(lock)!={'resolved_at','platform','authentik','postgres'} or lock['platform']!='linux/amd64':raise CheckError('invalid_lock')
    for name,repo,version in [('authentik','ghcr.io/goauthentik/server','2026.8.4'),('postgres','postgres','18.6')]:
        item=lock[name]
        if (item['version']!=version or not re.fullmatch(re.escape(repo)+r'@sha256:[a-f0-9]{64}',item['image'])
            or not re.fullmatch(r'sha256:[a-f0-9]{64}',item['amd64_manifest'])
            or type(item['compressed_bytes']) is not int or not 0<item['compressed_bytes']<1024**3):raise CheckError('invalid_lock')
    raw=TEMPLATE.read_text()
    # Security-sensitive source structure is validated before interpolation.
    template=yaml.load(raw,Loader=source.Loader)
    if set(template)!={'services','networks'} or template['networks']!={'validation':{'internal':True}}:raise CheckError('invalid_topology')
    services=template['services']
    if set(services)!={'database','checker'}:raise CheckError('invalid_services')
    for name,service in services.items():
        expected_user='70:70' if name=='database' else '1000:1000'
        if (service.get('user')!=expected_user or service.get('platform')!='linux/amd64'
            or service.get('read_only') is not True or service.get('restart')!='no'
            or service.get('networks')!=['validation'] or service.get('cap_drop')!=['ALL']
            or service.get('security_opt')!=['no-new-privileges:true','apparmor:docker-default']
            or service.get('logging')!={'driver':'none'}):raise CheckError('unsafe_service')
        allowed={'image','platform','user','entrypoint','read_only','restart','cap_drop','security_opt','networks','environment','volumes','tmpfs','mem_limit','cpus','pids_limit','shm_size','logging','healthcheck'}
        if set(service)-allowed:raise CheckError('unexpected_service_option')
        expected_limits=('768m',1,128) if name=='database' else ('2g',2,256)
        if (service.get('mem_limit'),service.get('cpus'),service.get('pids_limit'))!=expected_limits:raise CheckError('unbounded_service')
        volumes=service.get('volumes',[])
        sources=['${PRIVATE_DIR}/postgres-password'] if name=='database' else ['${PRIVATE_DIR}/authentik-password','${PRIVATE_DIR}/authentik-secret','${PUBLIC_DIR}/household-blueprint.yaml','${PUBLIC_DIR}/native_validate.py']
        targets=['/run/secrets/db-password'] if name=='database' else ['/run/secrets/db-password','/run/secrets/authentik-secret','/candidate/household-blueprint.yaml','/candidate/native_validate.py']
        expected=[dict(type='bind',source=s,target=t,read_only=True,bind={'create_host_path':False}) for s,t in zip(sources,targets)]
        if volumes!=expected:raise CheckError('unsafe_mount')
    # A reviewed template hash prevents unexamined commands/env/tmpfs changes.
    # Updating the public hash requires review, not an operator-supplied override.
    if hashlib.sha256(raw.encode()).hexdigest()!=TEMPLATE_SHA256:raise CheckError('template_drift')
    return lock,raw


def render(raw,lock,private,public):
    values={'POSTGRES_IMAGE':lock['postgres']['image'],'AUTHENTIK_IMAGE':lock['authentik']['image'],
            'PRIVATE_DIR':str(private),'PUBLIC_DIR':str(public)}
    def replace(match):
        if match[1] not in values:raise CheckError('unknown_template_input')
        return values[match[1]]
    return re.sub(r'\$\{([A-Z_]+)\}',replace,raw)


class Engine:
    def __init__(self):self.env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','DOCKER_CONFIG':'/nonexistent'}
    def run(self,args,timeout=120,check=True):
        # Never stream raw Docker/native logs. Temporary output is discarded.
        with tempfile.TemporaryFile() as output:
            process=subprocess.Popen(['docker','--context','default',*args],stdout=output,stderr=output,env=self.env,start_new_session=True)
            try:
                deadline=time.monotonic()+timeout
                while process.poll() is None:
                    if time.monotonic()>=deadline:raise CheckError('docker_command_timeout')
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:print('[identity] Docker operation still running.',file=sys.stderr,flush=True)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
            output.seek(0);data=output.read(4*1024*1024+1)
            if len(data)>4*1024*1024:raise CheckError('oversized_native_output')
        if check and process.returncode:raise CheckError('docker_command_failed')
        return process.returncode,data


def write_private(path,content,uid):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    try:os.write(fd,content);os.fchown(fd,uid,uid);os.fchmod(fd,0o400)
    finally:os.close(fd)


def native_result(data,code):
    lines=[line for line in data.splitlines() if line.startswith(b'IDENTITY_NATIVE_RESULT=')]
    if len(lines)!=1:raise CheckError('missing_native_result')
    try:result=json.loads(lines[0].split(b'=',1)[1])
    except (ValueError,UnicodeError):raise CheckError('invalid_native_result') from None
    stages={'django_setup','migrations','fresh_tenant','native_fields','native_validation','native_import','native_readback','idempotency','completed'}
    if (not isinstance(result,dict) or not {'status','stage'} <= set(result) <= {'status','stage','entry','diagnostic','issues'} or result['status'] not in ('passed','failed')
        or result['stage'] not in stages):raise CheckError('invalid_native_result')
    if 'diagnostic' in result:
        allowed={'module_missing','import_error','permission_denied','file_missing','assertion_failed',
                 'os_error','configuration_error','registry_not_ready','database_unavailable','database_schema_error','blueprint_rejected','other'}
        if result['status']!='failed' or result['diagnostic'] not in allowed:raise CheckError('invalid_native_result')
    if 'entry' in result:
        source=source_module();known={row['id'] for row in source.parse(source.BLUEPRINT.read_bytes())['entries']}
        if result['status']!='failed' or result['entry'] not in known:raise CheckError('invalid_native_result')
    if 'issues' in result:
        if result['status']!='failed' or 'entry' not in result or not isinstance(result['issues'],list) or not 0<len(result['issues'])<=8:
            raise CheckError('invalid_native_result')
        row=next(row for row in source.parse(source.BLUEPRINT.read_bytes())['entries'] if row['id']==result['entry'])
        fields=set(row['attrs'])|set(row['identifiers'])|{'non_field_errors'}
        codes={'required','invalid','invalid_choice','null','blank','unique','does_not_exist',
               'incorrect_type','max_length','min_length','max_value','min_value'}
        for issue in result['issues']:
            if not isinstance(issue,dict) or set(issue)!={'field','code'} or not isinstance(issue['field'],str) or not isinstance(issue['code'],str) or issue['field'] not in fields or issue['code'] not in codes:
                raise CheckError('invalid_native_result')
    if code!=0 or result!={'status':'passed','stage':'completed'}:
        raise CheckError('native_failed_'+result['stage']+('_entry_'+result['entry'] if 'entry' in result else '')+('_'+result['diagnostic'] if 'diagnostic' in result else ''),issues=result.get('issues'))
    return result


def execute(engine,lock,raw):
    if os.geteuid()!=0:raise CheckError('host_admin_required')
    memory=re.search(r'^MemAvailable:\s+(\d+) kB$',Path('/proc/meminfo').read_text(),re.M)
    if not memory or int(memory[1])<4*1024**2:raise CheckError('less_than_4_gib_available')
    engine.run(['info','--format','{{.ServerVersion}}'])
    for name in ('postgres','authentik'):
        print('[identity] Ensuring pinned '+name+' image is cached.',file=sys.stderr,flush=True)
        engine.run(['pull','--platform','linux/amd64',lock[name]['image']],timeout=1200)
    project=PREFIX+uuid.uuid4().hex
    folder=Path(tempfile.mkdtemp(prefix=project+'-',dir='/var/tmp'));folder.chmod(0o700)
    private=folder/'private';private.mkdir(mode=0o700)
    public=folder/'public';public.mkdir(mode=0o755)
    config=folder/'compose.yaml';checker=project+'-checker'
    started=False;cleanup=[];error=None
    compose=['compose','--project-name',project,'--file',str(config)]
    try:
        password=secrets.token_hex(32).encode()
        write_private(private/'postgres-password',password,70)
        write_private(private/'authentik-password',password,1000)
        write_private(private/'authentik-secret',secrets.token_hex(48).encode(),1000)
        for source,target in [(ROOT/'infra/identity/household-blueprint.yaml','household-blueprint.yaml'),(ROOT/'scripts/identity/native_validate.py','native_validate.py')]:
            (public/target).write_bytes(source.read_bytes());(public/target).chmod(0o444)
        config.write_text(render(raw,lock,private,public));config.chmod(0o600)
        engine.run([*compose,'config','--quiet'])
        if engine.run(['ps','--all','--quiet','--filter','label=com.docker.compose.project='+project])[1].strip():raise CheckError('project_collision')
        started=True
        print('[identity] Starting private temporary PostgreSQL; no ports are published.',file=sys.stderr,flush=True)
        engine.run([*compose,'up','-d','--pull','never','--wait','--wait-timeout','90','database'],timeout=120)
        print('[identity] Running native migrations, import, readback and repeat import.',file=sys.stderr,flush=True)
        code,output=engine.run([*compose,'run','--rm','--no-deps','--pull','never','--name',checker,'checker'],timeout=600,check=False)
        native_result(output,code)
    except BaseException as exc:error=exc
    finally:
        if started:
            try:
                _,found=engine.run(['ps','--all','--quiet','--filter','label=com.docker.compose.project='+project,'--filter','name=^/'+checker+'$'])
                if found.strip():
                    if not re.fullmatch(rb'[a-f0-9]{12,64}',found.strip()):raise CheckError('cleanup_selection_failed')
                    engine.run(['rm','--force',checker],timeout=60)
            except Exception:cleanup.append('failed')
            try:engine.run([*compose,'down','--timeout','10','--volumes'],timeout=60)
            except Exception:cleanup.append('failed')
        if not cleanup:shutil.rmtree(folder)
    if cleanup:raise CheckError('cleanup_failed_'+project,cleanup='pending')
    if error:
        if isinstance(error,CheckError):error.cleanup='completed'
        raise error
    return {'status':'passed','native_authentik_validation':'passed','native_import_readback':'passed',
            'repeat_import':'passed','cleanup':'completed','browser_mfa_acceptance':'pending',
            'gateway_authorization_acceptance':'pending','household_readiness':'pending'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','run']);args=parser.parse_args()
    try:
        lock,raw=bundle()
        if args.mode=='plan':
            result={'status':'prepared','scope':'Disposable native validation only; no ports, real accounts, CA or persistent identity services',
                    'images':{k:lock[k]['image'] for k in ('authentik','postgres')},
                    'download_compressed_mib':round(sum(lock[k]['compressed_bytes'] for k in ('authentik','postgres'))/1024**2,1),
                    'native_authentik_validation':'pending','household_readiness':'pending'}
        else:result=execute(Engine(),lock,raw)
    except CheckError as exc:
        result={'status':'failed','error':str(exc),'cleanup':exc.cleanup,'household_readiness':'pending'}
        if exc.issues:result['native_issues']=exc.issues
    except Exception:result={'status':'failed','error':'native_probe_failed_details_withheld','household_readiness':'pending'}
    sources=['infra/identity/versions.yaml','infra/identity/native-compose.yaml','infra/identity/household-blueprint.yaml','scripts/identity/native_validate.py','scripts/identity/native-check.py']
    result['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    print(json.dumps(result,indent=2));return int(result['status']=='failed')

# REVIEWED_TEMPLATE_HASH
TEMPLATE_SHA256='a942128b36fcf09335c5c7d98278ccad14a752f8fa57e705a1864dc6cb0923ec'
if __name__=='__main__':raise SystemExit(main())
