"""Full identity restore rehearsal: bounded RAM state, separate loopback origin."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import socket
import stat
import re

ROOT=Path(__file__).resolve().parents[2]
BASE=Path('/var/lib/agent-platform/identity-rehearsal')
STATE=BASE/'state'
CONTROL=BASE/'control'
PROJECT='agent-platform-identity-rehearsal'
ADDRESS='127.0.0.2'
PORT=19000
SCOPE='Isolated snapshot rehearsal; aggregate login/TOTP evidence does not correlate a specific account/session or certify all encrypted fields, egress or household gateway access'
URL='http://127.0.0.2:19000'
SIZE=768*1024**2
PROFILE={'schema_version':1,'purpose':'isolated_identity_restore_rehearsal',
         'project':PROJECT,'listen':{'address':ADDRESS,'port':PORT},
         'state_tmpfs_mib':768,'networks_internal':['database','frontend'],
         'logging':'none','reuse_live_state':False}
class RehearsalError(ValueError):pass


def configuration(local):
    helper,lock,_,_=local.bundle();source=helper.source_module()
    profile=source.parse((ROOT/'infra/identity/rehearsal-profile.yaml').read_bytes())
    if not source.same(profile,PROFILE):raise RehearsalError('rehearsal_profile_drift')
    # Derive only from the reviewed immutable base; no restored Compose is executed.
    raw=(ROOT/'infra/identity/local-compose.yaml').read_text()
    raw=raw.replace('127.0.0.1:9000:9000',f'{ADDRESS}:{PORT}:9000')
    values={'POSTGRES_IMAGE':lock['postgres']['image'],'AUTHENTIK_IMAGE':lock['authentik']['image'],
            'PRIVATE_DIR':str(STATE/'secrets'),'STATE_DIR':str(STATE)}
    raw=re.sub(r'\$\{([A-Z_]+)\}',lambda match:values[match[1]],raw)
    config=source.parse(raw)
    config['networks']['frontend']={'internal':True}
    for name,service in config['services'].items():
        service['logging']={'driver':'none'}
        if name!='database':service['environment']['AUTHENTIK_COOKIE_DOMAIN']=''
    config['services']['server']['volumes'].append({'type':'bind',
        'source':str(CONTROL/'rehearsal_probe.py'),'target':'/candidate/rehearsal_probe.py',
        'read_only':True,'bind':{'create_host_path':False}})
    import yaml
    rendered=yaml.safe_dump(config,sort_keys=False)
    return lock,config,rendered


def inspect_mount(engine):
    code,data=engine.run(['findmnt','--json','--mountpoint',str(STATE),'--output','TARGET,FSTYPE,OPTIONS,SOURCE'],check=False)
    if code:return None
    records=json.loads(data).get('filesystems',[])
    if len(records)!=1:raise RehearsalError('rehearsal_mount_selection_failed')
    mount=records[0];options=set(mount.get('options','').split(','))
    if (mount.get('target')!=str(STATE) or mount.get('fstype')!='tmpfs'
            or mount.get('source')!='identity-rehearsal' or not {'rw','nosuid','nodev','noexec'}<=options):
        raise RehearsalError('rehearsal_foreign_or_unsafe_mount')
    meta=STATE.lstat();capacity=os.statvfs(STATE)
    if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=0 or stat.S_IMODE(meta.st_mode)!=0o700
            or not 0<capacity.f_blocks*capacity.f_frsize<=SIZE):
        raise RehearsalError('rehearsal_mount_identity_or_capacity')
    return mount


def runtime(local,engine,config,required=False):
    return local.runtime(engine,config,require_all=required,project=PROJECT,
                         address=ADDRESS,port=PORT,internal_networks=('database','frontend'))


def control(local,rendered):
    local.ancestors();local.directory(BASE,0);local.directory(CONTROL,0)
    document=local.native().source_module().parse(local.read_file(CONTROL/'record.json',0,0o600,4096))
    expected={'schema_version':1,'project':PROJECT,'compose_sha256':hashlib.sha256(rendered.encode()).hexdigest()}
    if (not isinstance(document,dict) or set(document)!={*expected,'probe_sha256'}
            or not local.native().source_module().same({k:document[k] for k in expected},expected)
            or not isinstance(document['probe_sha256'],str)):
        raise RehearsalError('rehearsal_control_identity_drift')
    if local.read_file(CONTROL/'compose.yaml',0,0o600,32768)!=rendered.encode():
        raise RehearsalError('rehearsal_compose_drift')
    probe=local.read_file(CONTROL/'rehearsal_probe.py',0,0o644,16384)
    if hashlib.sha256(probe).hexdigest()!=document['probe_sha256']:
        raise RehearsalError('rehearsal_probe_drift')


def compose(engine,*args,timeout=120,check=True):
    return engine.run(['compose','--project-name',PROJECT,'--file',str(CONTROL/'compose.yaml'),*args],timeout=timeout,check=check)


def native_probe(engine,phase):
    code,raw=compose(engine,'exec','-T','server','python','/candidate/rehearsal_probe.py',phase,check=False)
    lines=[line.split(b'=',1)[1] for line in raw.splitlines() if line.startswith(b'IDENTITY_REHEARSAL_RESULT=')]
    if code or len(lines)!=1:raise RehearsalError('rehearsal_native_probe_failed')
    result=json.loads(lines[0])
    if (not isinstance(result,dict) or set(result)!={'status','secret_loaded','signing_roundtrip','host_only_cookie',
         'active_users_present','confirmed_totp_present','totp_material_readable','login_events','totp_max_step'}
            or result['status']!='passed'
            or any(result[key] is not True for key in ('secret_loaded','signing_roundtrip','host_only_cookie',
                'active_users_present','confirmed_totp_present','totp_material_readable'))
            or type(result['login_events']) is not int or result['login_events']<0
            or type(result['totp_max_step']) is not int or result['totp_max_step']< -1):
        raise RehearsalError('rehearsal_native_probe_failed')
    return result


def check(engine,local,accept=False):
    _,config,rendered=configuration(local);control(local,rendered)
    if not inspect_mount(engine):raise RehearsalError('rehearsal_ram_mount_missing')
    runtime(local,engine,config,required=True)
    if not local.http_ready(URL):raise RehearsalError('rehearsal_http_not_ready')
    baseline=local.native().source_module().parse(local.read_file(CONTROL/'baseline.json',0,0o600,4096))
    if (not isinstance(baseline,dict) or set(baseline)!={'login_events','totp_max_step'}
            or any(type(baseline[k]) is not int for k in baseline)
            or baseline['login_events']<0 or baseline['totp_max_step']< -1):
        raise RehearsalError('rehearsal_baseline_invalid')
    current=native_probe(engine,'check')
    evidence={'new_login_event':current['login_events']>baseline['login_events'],
              'totp_step_advanced':current['totp_max_step']>baseline['totp_max_step']}
    if accept and not all(evidence.values()):raise RehearsalError('rehearsal_browser_evidence_pending')
    return {'status':'passed','ui_url':URL,'native_startup':'passed','restored_secret_signing':'passed',
            'restored_totp_readback':'passed','browser_evidence':evidence,
            'browser_acceptance':'aggregate_evidence_passed' if accept else 'pending_owner_confirmation',
            'household_readiness':'pending','scope':SCOPE}


def stop(engine,local):
    _,config,rendered=configuration(local)
    if not BASE.exists():
        _,found=engine.run(['ps','--all','--quiet','--filter','label=com.docker.compose.project='+PROJECT])
        if found.strip():raise RehearsalError('rehearsal_controls_missing_with_containers')
        return {'status':'absent','household_readiness':'pending'}
    control(local,rendered)
    # Validate ownership/restrictions even when the RAM mount disappeared on reboot.
    runtime(local,engine,config)
    mount=inspect_mount(engine)
    if mount is None:
        local.directory(STATE,0)
        if any(STATE.iterdir()):raise RehearsalError('rehearsal_nonempty_unmounted_state')
    compose(engine,'down','--timeout','15',timeout=90)
    _,found=engine.run(['ps','--all','--quiet','--filter','label=com.docker.compose.project='+PROJECT])
    if found.strip():raise RehearsalError('rehearsal_containers_remain')
    if mount:engine.run(['umount',str(STATE)],timeout=30)
    STATE.rmdir()
    for name in ('compose.yaml','rehearsal_probe.py','record.json','baseline.json'):
        path=CONTROL/name
        if path.exists():path.unlink()
    CONTROL.rmdir();BASE.rmdir()
    return {'status':'stopped','temporary_state_removed':True,'household_readiness':'pending'}


def write_payload(local,values):
    for name,uid in [('database',70),('data',1000),('certs',1000),('secrets',0)]:
        folder=STATE/name;folder.mkdir(mode=0o700);os.chown(folder,uid,uid)
    for name,uid in [('postgres-password',70),('authentik-password',1000),('authentik-secret',1000)]:
        local.write_file(STATE/'secrets'/name,values['secrets/'+name],uid,0o400)
    # unpack() already rejected links, traversal, duplicates and unknown roots.
    for name,data in values.items():
        if not name.startswith(('data/','certs/')):continue
        path=STATE/name;parent=path.parent
        chain=[]
        while parent not in (STATE/'data',STATE/'certs'):
            chain.append(parent);parent=parent.parent
        for folder in reversed(chain):
            if not folder.exists():folder.mkdir(mode=0o700);os.chown(folder,1000,1000)
        local.write_file(path,data,1000,0o600)


def require_resources():
    memory=re.search(r'^MemAvailable:\s+(\d+) kB$',Path('/proc/meminfo').read_text(),re.M)
    if not memory or int(memory[1])<6*1024**2:raise RehearsalError('rehearsal_less_than_6_gib_available')
    with socket.socket() as listener:
        try:listener.bind((ADDRESS,PORT))
        except OSError:raise RehearsalError('rehearsal_loopback_port_busy') from None


def start(engine,backup,local,lock,plaintext):
    values,meta=backup.unpack(plaintext,lock)
    _,config,rendered=configuration(local)
    local.ancestors()
    if BASE.exists() or BASE.is_symlink():raise RehearsalError('rehearsal_exists_run_check_or_down')
    _,existing=engine.run(['ps','--all','--quiet','--filter','label=com.docker.compose.project='+PROJECT])
    if existing.strip():raise RehearsalError('rehearsal_project_collision')
    require_resources()
    BASE.mkdir(mode=0o700);CONTROL.mkdir(mode=0o700);STATE.mkdir(mode=0o700)
    probe=(ROOT/'scripts/identity/rehearsal_probe.py').read_bytes()
    local.write_file(CONTROL/'compose.yaml',rendered.encode(),0,0o600)
    local.write_file(CONTROL/'rehearsal_probe.py',probe,0,0o644)
    record={'schema_version':1,'project':PROJECT,'compose_sha256':hashlib.sha256(rendered.encode()).hexdigest(),
            'probe_sha256':hashlib.sha256(probe).hexdigest()}
    local.write_file(CONTROL/'record.json',json.dumps(record).encode(),0,0o600)
    try:
        engine.run(['mount','-t','tmpfs','-o','size=768m,mode=0700,nodev,nosuid,noexec','identity-rehearsal',str(STATE)])
        if not inspect_mount(engine):raise RehearsalError('rehearsal_ram_mount_missing')
        write_payload(local,values)
        compose(engine,'config','--quiet')
        print('[identity-rehearsal] Starting separate PostgreSQL and restoring the snapshot.',flush=True,file=sys.stderr)
        compose(engine,'up','-d','--pull','never','--wait','--wait-timeout','90','database',timeout=120)
        runtime(local,engine,config)
        with backup.memory_file() as dump,backup.memory_file() as sink:
            dump.write(values['database.dump']);dump.seek(0)
            backup.stream_command(['docker','--context','default','compose','--project-name',PROJECT,'--file',str(CONTROL/'compose.yaml'),
                'exec','-T','database','pg_restore','-U','identity_local','-d','identity_local','--no-owner','--exit-on-error','--single-transaction'],dump,sink,timeout=300)
        if backup.table_inventory(engine,['compose','--project-name',PROJECT,'--file',str(CONTROL/'compose.yaml'),'exec','-T','database'])!=meta['public_tables']:
            raise RehearsalError('rehearsal_restored_inventory_mismatch')
        print('[identity-rehearsal] Starting restored server/worker; the current instance remains separate.',flush=True,file=sys.stderr)
        compose(engine,'up','-d','--pull','never','--wait','--wait-timeout','300','server','worker',timeout=330)
        runtime(local,engine,config,required=True)
        if not local.http_ready(URL):raise RehearsalError('rehearsal_http_not_ready')
        native=native_probe(engine,'baseline')
        baseline={key:native[key] for key in ('login_events','totp_max_step')}
        local.write_file(CONTROL/'baseline.json',json.dumps(baseline).encode(),0,0o600)
        return check(engine,local)
    except BaseException:
        # Preserve state if its ownership/runtime cannot be verified for cleanup.
        try:stop(engine,local)
        except Exception:raise RehearsalError('rehearsal_failed_cleanup_needs_review') from None
        raise


def validate_report(report):
    expected={'status','ui_url','native_startup','restored_secret_signing','restored_totp_readback',
              'browser_evidence','browser_acceptance','household_readiness','scope'}
    if (not isinstance(report,dict) or set(report)!=expected or report['status']!='passed' or report['ui_url']!=URL
            or any(report[key]!='passed' for key in ('native_startup','restored_secret_signing','restored_totp_readback'))
            or report['household_readiness']!='pending' or report['browser_acceptance']!='pending_owner_confirmation'
            or not isinstance(report['browser_evidence'],dict) or set(report['browser_evidence'])!={'new_login_event','totp_step_advanced'}
            or any(type(value) is not bool for value in report['browser_evidence'].values())
            or report['scope']!=SCOPE):
        raise RehearsalError('rehearsal_invalid_helper_report')
    return report


def plan(local):
    configuration(local)
    return {'status':'prepared','ui_url':URL,'state_tmpfs_mib':768,'services':['database','server','worker'],
            'published_on_lan':False,'live_data_reused':False,'household_readiness':'pending',
            'scope':'Prepared isolated application restore; no mount, decryption, account or service changes'}
