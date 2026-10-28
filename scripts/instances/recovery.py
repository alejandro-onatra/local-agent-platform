"""Restart and restore only generated synthetic records; never export native keys or full state."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid


def idle_guard(api,policy):
    sessions=api.health(policy)
    for index,tenant in enumerate(policy['tenants']):
        status,body=api.request(tenant,'/api/conversations/search?limit=100',sessions[index])
        if status!=200:raise api.PilotError('recovery_idle_inventory_unavailable')
        data=json.loads(body)
        if (not isinstance(data,dict) or not isinstance(data.get('items'),list)
            or len(data['items'])>=100 or data.get('next_page_id')
            or any(not isinstance(item,dict) or item.get('execution_status') not in {'idle','finished'} for item in data['items'])):
            raise api.PilotError('recovery_requires_idle_bounded_pilots')
    return sessions


def make_records(policy):
    return [{'tenant':tenant['id'],'conversation_id':str(uuid.uuid4()),
             'secret_name':'RECOVERY_'+uuid.uuid4().hex.upper(),
             'value':'synthetic-'+uuid.uuid4().hex,'marker':'.recovery-probe-'+uuid.uuid4().hex}
            for tenant in policy['tenants']]


def validate_manifest(data,policy):
    if (not isinstance(data,dict) or set(data)!={'schema_version','purpose','records'}
            or type(data['schema_version']) is not int or data['schema_version']!=1
            or data['purpose']!='synthetic_application_recovery' or not isinstance(data['records'],list)
            or len(data['records'])!=2):raise ValueError('invalid_synthetic_manifest')
    if {r.get('tenant') for r in data['records'] if isinstance(r,dict)}!={t['id'] for t in policy['tenants']}:
        raise ValueError('invalid_synthetic_manifest')
    for row in data['records']:
        if not isinstance(row,dict) or set(row)!={'tenant','conversation_id','secret_name','value','marker'}:
            raise ValueError('invalid_synthetic_manifest')
        if not isinstance(row['conversation_id'],str) or str(uuid.UUID(row['conversation_id']))!=row['conversation_id']:
            raise ValueError('invalid_synthetic_manifest')
        for field,pattern in [('secret_name',r'RECOVERY_[A-F0-9]{32}'),('value',r'synthetic-[a-f0-9]{32}'),('marker',r'\.recovery-probe-[a-f0-9]{32}')]:
            if not isinstance(row[field],str) or not re.fullmatch(pattern,row[field]):raise ValueError('invalid_synthetic_manifest')
    for field in ('conversation_id','secret_name','value','marker'):
        if len({row[field] for row in data['records']})!=2:raise ValueError('duplicate_synthetic_manifest_record')
    return data


def snapshot(api,policy,records):
    data=validate_manifest({'schema_version':1,'purpose':'synthetic_application_recovery','records':records},policy)
    raw=json.dumps(data,sort_keys=True).encode()
    if len(raw)>8192:raise api.PilotError('synthetic_manifest_oversized')
    api.store.safe_path(api.BASE)
    path=api.BASE/('recovery-'+uuid.uuid4().hex+'.json')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:os.write(fd,raw);os.fsync(fd)
    finally:os.close(fd)
    return path,hashlib.sha256(raw).hexdigest()


def read_snapshot(api,policy,path,expected,owner=0):
    api.store.safe_path(path.parent)
    # Inspect the opened descriptor before reading; FIFOs must never block here.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        meta=os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid!=owner or meta.st_nlink!=1
            or stat.S_IMODE(meta.st_mode)!=0o600 or not 0<meta.st_size<=8192):
            raise api.PilotError('unsafe_synthetic_manifest')
        raw=os.read(fd,8193)
    finally:os.close(fd)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),expected):raise api.PilotError('synthetic_manifest_changed')
    return validate_manifest(json.loads(raw),policy)['records']


def marker_paths(api,tenant,record):
    state,workspace,_=api.paths(tenant)
    return [base/record['marker'] for base in (state,workspace)]


def marker_matches(path,tenant,record):
    # Inspect the opened descriptor before reading; FIFOs must never block here.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        meta=os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid!=tenant['uid'] or meta.st_gid!=tenant['gid']
            or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)!=0o600 or meta.st_size>128):return False
        return os.read(fd,129)==record['value'].encode()
    finally:os.close(fd)


def create_markers(api,tenant,record,tracked):
    for path in marker_paths(api,tenant,record):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        tracked.append(path)
        try:os.write(fd,record['value'].encode());os.fchown(fd,tenant['uid'],tenant['gid']);os.fsync(fd)
        finally:os.close(fd)


def remove_markers(api,tenant,record,paths):
    for path in paths:
        if not path.exists() and not path.is_symlink():continue
        if path not in marker_paths(api,tenant,record) or not marker_matches(path,tenant,record):
            raise api.PilotError('synthetic_marker_changed')
        path.unlink()


def endpoints(record):
    return '/api/settings/secrets/'+record['secret_name'],'/api/conversations/'+record['conversation_id']


def create_application(api,tenant,key,record,owned):
    secret,conversation=endpoints(record)
    if api.request(tenant,secret,key)[0]!=404 or api.request(tenant,conversation,key)[0]!=404:
        raise api.PilotError('synthetic_recovery_collision')
    owned['secret']=True
    if api.request(tenant,'/api/settings/secrets',key,'PUT',{'name':record['secret_name'],'value':record['value'],'description':'Synthetic recovery canary'})[0]!=200:
        raise api.PilotError('synthetic_recovery_secret_create_failed')
    owned['conversation']=True
    if api.request(tenant,'/api/conversations',key,'POST',api.conversation_payload(record['conversation_id']))[0]!=201:
        raise api.PilotError('synthetic_recovery_conversation_create_failed')


def verify_records(api,policy,sessions,records):
    for index,tenant in enumerate(policy['tenants']):
        record=next(row for row in records if row['tenant']==tenant['id']);secret,conversation=endpoints(record)
        status,value=api.request(tenant,secret,sessions[index])
        if status!=200 or value!=record['value'].encode() or api.request(tenant,conversation,sessions[index])[0]!=200:
            raise api.PilotError('synthetic_recovery_own_records_mismatch')
        other=policy['tenants'][1-index]
        if api.request(other,secret,sessions[1-index])[0]!=404 or api.request(other,conversation,sessions[1-index])[0]!=404:
            raise api.PilotError('synthetic_recovery_cross_namespace_failure')
        if not all(marker_matches(path,tenant,record) for path in marker_paths(api,tenant,record)):
            raise api.PilotError('synthetic_recovery_filesystem_mismatch')


def wait_backend(api,tenant,credential,sleep=time.sleep):
    for attempt in range(45):
        try:
            status,body=api.request(tenant,'/api/settings',credential)
            if status==200 and isinstance(json.loads(body),dict) and 'agent_settings' in json.loads(body):return
            if status in (401,403):raise api.PilotError('native_key_changed_during_restart')
        except (OSError,ValueError,api.PilotError) as error:
            if isinstance(error,api.PilotError) and str(error)=='native_key_changed_during_restart':raise
        if attempt==44:raise api.PilotError('recovery_backend_restart_timeout')
        if attempt%5==0:print('[recovery] Waiting for '+tenant['id']+' authenticated backend.',file=__import__('sys').stderr,flush=True)
        sleep(2)


def restart_one(api,engine,tenant,credential):
    stopped=False
    try:
        stopped=True;api.compose(engine,tenant,'stop')
        api.compose(engine,tenant,'start')
        wait_backend(api,tenant,credential);stopped=False
    finally:
        if stopped:
            # Resume only this pilot if the bounded restart check failed; never switch state.
            try:api.compose(engine,tenant,'start')
            except api.store.StorageError:pass


def delete_application(api,tenant,key,record,owned):
    secret,conversation=endpoints(record)
    for name,path in [('conversation',conversation),('secret',secret)]:
        if owned[name]:
            if api.request(tenant,path,key,'DELETE')[0] not in (200,404):raise api.PilotError('synthetic_recovery_cleanup_failed')
            if api.request(tenant,path,key)[0]!=404:raise api.PilotError('synthetic_recovery_delete_not_confirmed')
            owned[name]=False


def recovery_check(api,policy,lock,engine):
    sessions=idle_guard(api,policy)
    native_keys=[(api.key(t,'api-key.txt'),api.key(t,'secret-key.txt')) for t in policy['tenants']]
    records=make_records(policy);owned=[];manifest=None;stage='create_canaries';failure=None;results=[]
    try:
        for index,tenant in enumerate(policy['tenants']):
            record=records[index];state={'tenant':tenant,'record':record,'secret':False,'conversation':False,'paths':[]}
            owned.append(state)
            create_markers(api,tenant,record,state['paths'])
            create_application(api,tenant,sessions[index],record,state)
        verify_records(api,policy,sessions,records)
        manifest,digest=snapshot(api,policy,records)
        stage='restart_pilots'
        for index,tenant in enumerate(policy['tenants']):
            print('[recovery] Restarting only '+tenant['id']+'; synthetic pilot must remain unused.',file=__import__('sys').stderr,flush=True)
            restart_one(api,engine,tenant,sessions[index])
            current=(api.key(tenant,'api-key.txt'),api.key(tenant,'secret-key.txt'))
            if not all(hmac.compare_digest(before,after) for before,after in zip(native_keys[index],current)):
                raise api.PilotError('native_keys_not_preserved')
            api.runtime(engine,tenant,lock)
        verify_records(api,policy,sessions,records)
        stage='validate_export'
        restored=read_snapshot(api,policy,manifest,digest)
        stage='remove_only_canaries'
        for index,state in enumerate(owned):
            delete_application(api,state['tenant'],sessions[index],state['record'],state)
            remove_markers(api,state['tenant'],state['record'],state['paths'])
        stage='import_only_canaries'
        for index,state in enumerate(owned):
            record=next(row for row in restored if row['tenant']==state['tenant']['id'])
            create_markers(api,state['tenant'],record,state['paths'])
            create_application(api,state['tenant'],sessions[index],record,state)
        verify_records(api,policy,sessions,restored)
        api.health(policy)
        results=[{'tenant':t['id'],'restart_persistence':'passed','native_keys_preserved':'passed',
                  'synthetic_api_import':'passed','synthetic_files_restored':'passed','cross_namespace_denied':'passed'} for t in policy['tenants']]
    except BaseException as error:failure=error
    cleanup_failed=False
    for index,state in enumerate(owned):
        try:
            delete_application(api,state['tenant'],sessions[index],state['record'],state)
            # Restoring reuses generated names; remove each name only once.
            remove_markers(api,state['tenant'],state['record'],list(dict.fromkeys(state['paths'])))
        except Exception:cleanup_failed=True
    if failure is not None or cleanup_failed:
        details={'failed_stage':stage if failure else 'cleanup','synthetic_cleanup':'pending' if cleanup_failed else 'completed'}
        if manifest is not None:details['synthetic_manifest_retained']=str(manifest)
        raise api.PilotError('synthetic_recovery_probe_failed',details) from None
    if manifest is not None:manifest.unlink()
    return {'status':'passed','instances':results,'synthetic_cleanup':'completed','synthetic_manifest_removed':True,
      'household_readiness':'pending','scope':'Synthetic record export/import and pilot process restart only; no native keys exported, full-state/SQLite backup, encrypted disaster recovery or host-reboot acceptance'}
