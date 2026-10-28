"""Bounded Docker probes against synthetic pilot storage only; no active agent access."""
import json
import os
from pathlib import Path
import re
import sys
import uuid
import yaml

# Runs as the synthetic UID inside the pinned image, without an agent or LLM.
PROBE = r'''
import errno,json,os,sys,uuid
from pathlib import Path
role,capacity,foreign_host,expected_uid,canary = sys.argv[1:]
capacity=int(capacity);expected_uid=int(expected_uid)
own=Path('/projects' if role=='workspace' else '/state')
results={'uid_matches':os.getuid()==expected_uid}
results['own_canary_visible']=(own/canary).read_text()=='synthetic storage canary'
def denied(path):
    try:
        with open(path,'rb') as file: file.read(1)
        return False
    except (PermissionError,FileNotFoundError,NotADirectoryError): return True
results['foreign_host_path_denied']=denied(foreign_host)
results['foreign_uid_canary_denied']=denied(Path('/other')/canary)
scratch=own/('.quota-probe-'+uuid.uuid4().hex)
written=0;full=False;created=False
try:
    # Unbuffered writes: never allocate more than fixed capacity + one chunk.
    with scratch.open('xb',buffering=0) as file:
        created=True;chunk=b'\0'*(256*1024)
        while written<=capacity:
            try:
                count=file.write(chunk)
                if not count: break
                written+=count
            except OSError as exc:
                if exc.errno==errno.ENOSPC: full=True;break
                raise
        try: os.fsync(file.fileno())
        except OSError as exc:
            if exc.errno==errno.ENOSPC: full=True
            else: raise
finally:
    if created: scratch.unlink()
results['disk_full_denied']=full
results['temporary_file_removed']=not scratch.exists()
results['written_mib']=round(written/(1024**2),2)
print(json.dumps(results))
'''
CHECKS = ('uid_matches','own_canary_visible','foreign_host_path_denied',
          'foreign_uid_canary_denied','disk_full_denied','temporary_file_removed')


def valid_result(result):
    return (isinstance(result,dict) and set(result)==set(CHECKS)|{'written_mib'}
            and all(result.get(key) is True for key in CHECKS)
            and type(result['written_mib']) in (int,float)
            and 0 <= result['written_mib'] <= 129)


def docker_command(api, image, tenant, role, capacity, workspace, state, other, canary, name):
    return ['docker','--context','default','run','--rm','-i','--name',name,
            '--label','agent-platform.storage-probe=synthetic',
            '--network','none','--read-only','--user',f"{tenant['uid']}:{tenant['gid']}",
            '--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--security-opt','apparmor=docker-default','--memory','256m','--cpus','1',
            '--pids-limit','64','--log-driver','none',
            '--mount',f'type=bind,src={workspace},dst=/projects',
            '--mount',f'type=bind,src={state},dst=/state',
            # Diagnostic-only read-only negative mount: distinct UID must deny it.
            '--mount',f'type=bind,src={other},dst=/other,readonly',
            '--entrypoint','python',image,'-B','-',role,str(capacity),
            str(other/canary),str(tenant['uid']),canary]


def require_synthetic_only(api,selected):
    for entry in selected:
        target=entry[4]
        if any(child.name!='lost+found' for child in target.iterdir()):
            raise api.StorageError('pilot_contains_unexpected_data')


def accept(policy,engine,api):
    api.check(policy,engine)
    selected=api.entries(policy)
    require_synthetic_only(api,selected)
    lock=api.read_yaml(api.ROOT/'infra/openhands/versions.yaml')
    image=lock.get('image') if isinstance(lock,dict) else None
    if not isinstance(image,str) or not re.fullmatch(
            r'ghcr\.io/openhands/agent-canvas@sha256:[0-9a-f]{64}',image):
        raise api.StorageError('invalid_probe_image_lock')
    digests=json.loads(engine.run(['docker','--context','default','image','inspect',
                                  '--format','{{json .RepoDigests}}',image]))
    if image not in (digests or []):
        raise api.StorageError('probe_image_unavailable')
    canary='.storage-canary-'+uuid.uuid4().hex
    created=[];results=[]
    try:
        for tenant,role,size,backing,target in selected:
            path=target/canary
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            created.append(path)
            try:
                os.write(fd,b'synthetic storage canary')
                os.fchown(fd,tenant['uid'],tenant['gid']);os.fsync(fd)
            finally:
                os.close(fd)
        for tenant,role,size,backing,target in selected:
            workspace=next(e[4] for e in selected if e[0]['id']==tenant['id'] and e[1]=='workspace')
            state=next(e[4] for e in selected if e[0]['id']==tenant['id'] and e[1]=='state')
            other=next(e[4] for e in selected if e[0]['id']!=tenant['id'] and e[1]==role)
            name='agent-platform-storage-probe-'+uuid.uuid4().hex
            print(f'[storage] Accepting {tenant["id"]}/{role}.',file=sys.stderr,flush=True)
            try:
                command=docker_command(api,image,tenant,role,size,workspace,state,other,canary,name)
                result=json.loads(engine.run(command,input=PROBE.encode(),timeout=180))
            finally:
                # Fixed unique name belongs solely to this probe. Never remove services.
                try: engine.run(['docker','--context','default','rm','--force',name])
                except api.StorageError: pass
            if not valid_result(result):
                raise api.StorageError('live_storage_probe_failed')
            results.append({'tenant':tenant['id'],'role':role,'checks':result,'status':'passed'})
    finally:
        for path in created:
            path.unlink()
    # Check source/mount capacities again after real writes and cleanup.
    api.check(policy,engine)
    return {'status':'passed','pilot_probes':results,'household_readiness':'pending',
            'scope':'Synthetic filesystem limits and UID canaries only; no real tenant HTTP/WebSocket, app-state, egress or restart/restore acceptance'}
