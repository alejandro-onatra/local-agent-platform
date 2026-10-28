#!/usr/bin/env python3
"""Operate two synthetic, offline OpenHands instances; never migrate the current demo."""
import argparse,fcntl,hashlib,json,os,re,socket,stat,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
import urllib.error,urllib.request
import yaml
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/storage'))
import storage as store
BASE=Path('/var/lib/agent-platform/instances-pilot')
TEMPLATE=ROOT/'infra/openhands/instances/compose.yaml'
SOURCE_ENTRYPOINT='87f44fe42f523db1087023c0fbd34e7359db7066636aefedae963576991454b6'
PORTS={'probe-a':8101,'probe-b':8102}

class PilotError(ValueError):
    """Fixed public categories; never return exceptions, HTTP bodies or keys."""
    def __init__(self,code,details=None):
        super().__init__(code)
        self.details=details


def project(tenant):return 'agent-platform-'+tenant['id']

def paths(tenant):
    selected=store.entries(store.load_policy())
    state=next(e[4] for e in selected if e[0]['id']==tenant['id'] and e[1]=='state')
    workspace=next(e[4] for e in selected if e[0]['id']==tenant['id'] and e[1]=='workspace')
    return state,workspace,BASE/tenant['id']


def values(tenant,lock):
    state,workspace,control=paths(tenant)
    return {'PILOT_IMAGE':lock['image'],'PILOT_PROXY_IMAGE':lock['proxy']['image'],
            'PILOT_USER':f"{tenant['uid']}:{tenant['gid']}",'PILOT_UID':str(tenant['uid']),
            'PILOT_STATE':str(state),'PILOT_WORKSPACE':str(workspace),'PILOT_CONTROL':str(control),
            'PILOT_LAUNCHER':str(ROOT/'scripts/openhands/start-agent-server.py'),
            'PILOT_ENTRYPOINT':str(ROOT/'infra/openhands/instances/entrypoint.sh'),
            'PILOT_NGINX':str(ROOT/'infra/openhands/nginx.conf'),'PILOT_PORT':str(PORTS[tenant['id']])}


def render(tenant,lock,template=None):
    template=store.read_yaml(TEMPLATE) if template is None else template
    replacements=values(tenant,lock)
    def visit(value):
        if isinstance(value,dict):return {k:visit(v) for k,v in value.items()}
        if isinstance(value,list):return [visit(v) for v in value]
        if isinstance(value,str):
            def substitute(match):
                if match[1] not in replacements:raise PilotError('unknown_template_input')
                return replacements[match[1]]
            return re.sub(r'\$\{([A-Z_]+)\}',substitute,value)
        return value
    result=visit(template);validate_config(result,tenant,lock)
    return result


def validate_config(config,tenant,lock):
    # Reviewable source guards; live inspect additionally checks the applied runtime.
    if set(config)!={'services','networks'} or config['networks']!={'backend':{'internal':True},'frontend':{}}:
        raise PilotError('network_or_topology_drift')
    services=config['services']
    if set(services)!={'openhands','ingress'}:raise PilotError('service_drift')
    allowed={'image','platform','user','init','entrypoint','command','restart','read_only','networks',
             'environment','volumes','tmpfs','mem_limit','cpus','pids_limit','cap_drop','security_opt',
             'logging','ports','depends_on'}
    v=values(tenant,lock);state,workspace,control=paths(tenant)
    agent_mounts=[(str(state),'/home/openhands',False),
        (str(state/'.openhands'),'/home/openhands/.openhands',False),
        (str(workspace),'/projects',False),(str(workspace),'/home/openhands/workspace',False),
        (str(control/'passwd'),'/etc/passwd',True),(str(control/'group'),'/etc/group',True),
        (v['PILOT_LAUNCHER'],'/usr/local/bin/openhands-agent-server',True),
        (v['PILOT_ENTRYPOINT'],'/opt/pilot/entrypoint.sh',True)]
    for name,service in services.items():
        if set(service)-allowed or service.get('platform')!='linux/amd64' or service.get('restart')!='no':
            raise PilotError('service_options_drift')
        if service.get('read_only') is not True or service.get('cap_drop')!=['ALL'] or set(service.get('security_opt',[]))!={'no-new-privileges:true','apparmor:docker-default'}:
            raise PilotError('process_controls_drift')
        if service.get('logging')!={'driver':'json-file','options':{'max-size':'2m','max-file':'2'}}:
            raise PilotError('logging_drift')
        expected_image=lock['image'] if name=='openhands' else lock['proxy']['image']
        if service.get('image')!=expected_image or not re.fullmatch(r'.+@sha256:[a-f0-9]{64}',expected_image):
            raise PilotError('image_drift')
        expected=agent_mounts if name=='openhands' else [(v['PILOT_NGINX'],'/etc/nginx/nginx.conf',True)]
        mounts=service.get('volumes',[])
        if len(mounts)!=len(expected):raise PilotError('mount_drift')
        for item,(source,target,readonly) in zip(mounts,expected):
            if set(item)-{'type','source','target','read_only','bind'} or item.get('type')!='bind' or item.get('source')!=source or item.get('target')!=target or item.get('read_only',False) is not readonly or item.get('bind')!={'create_host_path':False}:
                raise PilotError('mount_drift')
    agent=services['openhands'];ingress=services['ingress']
    expected_env={'HOME':'/home/openhands','USER':'openhands','LOGNAME':'openhands',
      'OH_WORKSPACE_PATH':'/projects','OH_MAX_CONCURRENT_RUNS':'1','OH_ENABLE_VSCODE':'false',
      'OH_ENABLE_BROWSER':'false','VITE_ENABLE_BROWSER_TOOLS':'false',
      'AGENT_CANVAS_ALLOW_LAN_SESSION_KEY':'false','OH_TELEMETRY_EXPORTER':'none',
      'OH_TELEMETRY_CONSENT':'denied','DO_NOT_TRACK':'1','VITE_DO_NOT_TRACK':'1',
      'LITELLM_LOCAL_MODEL_COST_MAP':'true','OPENHANDS_SUPPRESS_BANNER':'1','PYTHONDONTWRITEBYTECODE':'1'}
    uid=tenant['uid']
    expected_tmp=['/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777']+[
      f'/home/openhands/{folder}:rw,nosuid,nodev,noexec,size={size}m,mode=0700,uid={uid},gid={uid}'
      for folder,size in [('.cache',64),('.config',32),('.local',32)]]
    if (agent.get('user')!=v['PILOT_USER'] or agent.get('networks')!=['backend'] or agent.get('environment')!=expected_env
            or agent.get('entrypoint')!=['bash','/opt/pilot/entrypoint.sh'] or agent.get('init') is not True
            or agent.get('tmpfs')!=expected_tmp or 'ports' in agent or 'command' in agent or 'depends_on' in agent
            or (agent.get('mem_limit'),agent.get('cpus'),agent.get('pids_limit'))!=('2g',2,256)):
        raise PilotError('agent_controls_drift')
    if (ingress.get('user')!='101:101' or ingress.get('networks')!=['frontend','backend']
            or ingress.get('ports')!=[f"127.0.0.1:{PORTS[tenant['id']]}:8080"]
            or ingress.get('depends_on')!=['openhands'] or 'environment' in ingress or 'init' in ingress
            or ingress.get('entrypoint')!=['nginx'] or ingress.get('command')!=['-g','daemon off;']
            or ingress.get('tmpfs')!=['/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777']
            or (ingress.get('mem_limit'),ingress.get('cpus'),ingress.get('pids_limit'))!=('64m',0.5,64)):
        raise PilotError('ingress_controls_drift')


def conversation_payload(identifier):
    return {'conversation_id':identifier,'workspace':{'working_dir':'/projects'},
      'worktree':False,'initial_message':None,'max_iterations':1,
      'agent_settings':{'llm':{'model':'openai/qwen3:8b','api_key':'synthetic-local-only',
        'base_url':'http://127.0.0.1:9/v1','usage_id':'instance-probe:'+identifier}}}


def memory_available():
    data=Path('/proc/meminfo').read_text()
    match=re.search(r'^MemAvailable:\s+(\d+) kB$',data,re.MULTILINE)
    if not match or int(match[1])*1024 < 6*1024**3:
        raise PilotError('less_than_6_gib_available_memory')
    return round(int(match[1])/1024**2,2)


def image_metadata(engine,lock):
    for image in (lock['image'],lock['proxy']['image']):
        digests=json.loads(engine.run(['docker','--context','default','image','inspect','--format','{{json .RepoDigests}}',image]))
        if image not in (digests or []):raise PilotError('cached_pinned_image_required')
    launcher=(ROOT/'scripts/openhands/start-agent-server.py').read_text()
    program=launcher+'''\nassert runtime_ready()\nverify_usage_compatibility()\nimport json\nfrom pathlib import Path\nprint(json.dumps({'passwd':Path('/etc/passwd').read_text(),'group':Path('/etc/group').read_text(),'entrypoint':hashlib.sha256(Path('/opt/agent-canvas/entrypoint.sh').read_bytes()).hexdigest()}))\n'''
    # Avoid executing launcher's main(); only installed native compatibility checks.
    program="__name__='pilot_preflight'\n"+program
    program+='\nfrom openhands.sdk.conversation.request import StartConversationRequest\nStartConversationRequest.model_validate('+repr(conversation_payload(str(uuid.uuid4())))+')\n'
    name='agent-platform-instance-preflight-'+uuid.uuid4().hex
    try:
        data=json.loads(engine.run(['docker','--context','default','run','--rm','-i','--name',name,
          '--label','agent-platform.instance-preflight=synthetic','--network','none',
          '--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true',
          '--security-opt','apparmor=docker-default','--memory','512m','--cpus','1','--pids-limit','64',
          '--log-driver','none','--env','LITELLM_LOCAL_MODEL_COST_MAP=true','--entrypoint','python',
          lock['image'],'-B','-'],input=program.encode(),timeout=90))
    finally:
        try:engine.run(['docker','--context','default','rm','--force',name])
        except store.StorageError:pass
    if data.get('entrypoint')!=SOURCE_ENTRYPOINT:raise PilotError('native_entrypoint_mismatch')
    return data


def remap_accounts(text,tenant,kind):
    rows=[line.split(':') for line in text.splitlines()];count=0
    for row in rows:
        if len(row)!=(7 if kind=='passwd' else 4):raise PilotError('invalid_image_accounts')
        if row[0]=='openhands':
            count+=1;row[2]=str(tenant['uid'])
            if kind=='passwd':row[3]=str(tenant['gid']);row[5]='/home/openhands'
        elif row[2]==str(tenant['uid']):raise PilotError('image_identity_collision')
    if count!=1:raise PilotError('missing_image_identity')
    return '\n'.join(':'.join(row) for row in rows)+'\n'


def safe_child(parent,name,tenant,create=False):
    # Mounted roots are tenant-owned; never follow their linked child directories.
    target=parent/name
    if not target.exists() and not target.is_symlink() and create:
        target.mkdir(mode=0o700);os.chown(target,tenant['uid'],tenant['gid'])
    detail=target.lstat()
    if not stat.S_ISDIR(detail.st_mode) or detail.st_uid!=tenant['uid'] or detail.st_gid!=tenant['gid'] or stat.S_IMODE(detail.st_mode)!=0o700:
        raise PilotError('unsafe_state_child')
    return target


def protected_file(path,data,create=False):
    store.safe_path(path.parent)
    if not path.exists() and not path.is_symlink() and create:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        try:
            os.fchmod(fd,0o644);os.write(fd,data);os.fsync(fd)
        finally:os.close(fd)
    detail=path.lstat()
    if not stat.S_ISREG(detail.st_mode) or detail.st_uid!=0 or detail.st_nlink!=1 or stat.S_IMODE(detail.st_mode)!=0o644 or path.read_bytes()!=data:
        raise PilotError('control_file_drift')


def controls(policy,lock,metadata,create=False):
    store.safe_path(BASE)
    if create:BASE.mkdir(mode=0o700,exist_ok=True)
    for tenant in policy['tenants']:
        state,workspace,control=paths(tenant)
        if create:control.mkdir(mode=0o700,exist_ok=True)
        for folder in ('.openhands','.cache','.config','.local','workspace'):
            safe_child(state,folder,tenant,create)
        for kind in ('passwd','group'):
            protected_file(control/kind,remap_accounts(metadata[kind],tenant,kind).encode(),create)
        document=yaml.safe_dump(render(tenant,lock),sort_keys=False).encode()
        protected_file(control/'compose.yaml',document,create)


def compose(engine,tenant,*args):
    return engine.run(['docker','--context','default','compose','--project-name',project(tenant),
      '--file',str(BASE/tenant['id']/'compose.yaml'),*args],timeout=180)


def selected(engine,tenant,service,required=True):
    output=engine.run(['docker','--context','default','ps','--all','--quiet',
        '--filter','label=com.docker.compose.project='+project(tenant),
        '--filter','label=com.docker.compose.service='+service]).decode().strip()
    if not output and not required:return None
    if not re.fullmatch(r'[a-f0-9]{12,64}',output):raise PilotError('instance_selection_failed')
    return output


INSPECT='''{"running":{{json .State.Running}},"apparmor":{{json .AppArmorProfile}},"image":{{json .Config.Image}},"user":{{json .Config.User}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}},"host":{{json .HostConfig}},"networks":{{json .NetworkSettings.Networks}}}'''
# HostConfig contains no application Env. Never print this internal response.
def security_options(options):
    """Normalize only recognized equivalent syntax; disabled/duplicate/extra opts fail."""
    if not isinstance(options,list):return None
    result={}
    for option in options:
        if not isinstance(option,str):return None
        normalized=option.replace(':','=',1)
        if normalized=='no-new-privileges':normalized+='=true'
        name,separator,value=normalized.partition('=')
        if not separator or name in result or name not in {'no-new-privileges','apparmor'}:
            return None
        result[name]=value
    return result


def process_checks(info,expected,tenant,service,running=True):
    host=info.get('host') or {};labels=info.get('labels') or {}
    options=security_options(host.get('SecurityOpt')) or {}
    return {
        'running':not running or info.get('running') is True,
        'pinned_image':info.get('image')==expected['image'],
        'user_identity':info.get('user')==expected['user'],
        'project_identity':labels.get('com.docker.compose.project')==project(tenant),
        'service_identity':labels.get('com.docker.compose.service')==service,
        'readonly_root':host.get('ReadonlyRootfs') is True,
        'capabilities_dropped':set(host.get('CapDrop') or [])=={'ALL'} and not host.get('CapAdd'),
        'no_new_privileges':options.get('no-new-privileges')=='true',
        'apparmor_profile':options.get('apparmor')=='docker-default' and info.get('apparmor')=='docker-default',
        'no_extra_security_options':security_options(host.get('SecurityOpt')) is not None,
        'no_privileged_devices':not host.get('Privileged') and not host.get('Devices') and not host.get('DeviceRequests'),
        # Accept only declared bridges; runtime() also checks the full attachment set.
        # Docker's shareable IPC owns its namespace; container:<id> joins another's.
        'private_namespaces':(
            host.get('NetworkMode') in {project(tenant)+'_'+name for name in expected['networks']}
            and host.get('PidMode')==''
            and host.get('IpcMode') in ('private','shareable')
            and host.get('UTSMode')==''),
        'memory_limit':host.get('Memory')==(2*1024**3 if service=='openhands' else 64*1024**2),
        'cpu_limit':host.get('NanoCpus')==(2_000_000_000 if service=='openhands' else 500_000_000),
        'pids_limit':host.get('PidsLimit')==(256 if service=='openhands' else 64),
        'log_rotation':host.get('LogConfig')=={'Type':'json-file','Config':{'max-file':'2','max-size':'2m'}},
    }


def diagnose(policy,lock,engine):
    """Read current process declarations only, including stopped pilot containers."""
    results=[]
    for tenant in policy['tenants']:
        config=render(tenant,lock)
        for service,expected in config['services'].items():
            cid=selected(engine,tenant,service,required=False)
            if cid is None:
                results.append({'tenant':tenant['id'],'service':service,'state':'missing'})
                continue
            info=json.loads(engine.run(['docker','--context','default','inspect','--format',INSPECT,cid]))
            checks=process_checks(info,expected,tenant,service,running=False)
            # State is reported separately; a stopped diagnostic never marks running passed.
            checks.pop('running')
            results.append({'tenant':tenant['id'],'service':service,
              'state':'running' if info.get('running') is True else 'not_running',
              'process_checks':{name:'passed' if ok else 'failed' for name,ok in checks.items()},
              'failed_checks':[name for name,ok in checks.items() if not ok]})
    return {'status':'collected','instances':results,'household_readiness':'pending',
      'scope':'Read-only current process declarations; no startup, mounts, keys, logs or isolation acceptance'}


def runtime(engine,tenant,lock,required=True,running=True):
    config=render(tenant,lock)
    records={}
    for service,expected in config['services'].items():
        cid=selected(engine,tenant,service,required)
        if cid is None:continue
        info=json.loads(engine.run(['docker','--context','default','inspect','--format',INSPECT,cid]))
        host=info['host'];labels=info['labels'];networks=info['networks']
        checks=process_checks(info,expected,tenant,service,running)
        failed=[name for name,ok in checks.items() if not ok]
        if failed:
            raise PilotError('runtime_process_drift',{'tenant':tenant['id'],'service':service,'failed_checks':failed})
        expected_mounts={(m['source'],m['target'],not m.get('read_only',False)) for m in expected['volumes']}
        actual_mounts={(m['Source'],m['Destination'],m['RW']) for m in info['mounts'] if m['Type']=='bind'}
        tmpfs=host.get('Tmpfs') or {}
        expected_tmpfs=dict(item.split(':',1) for item in expected['tmpfs'])
        if actual_mounts!=expected_mounts or any(m['Type'] not in ('bind','tmpfs') for m in info['mounts']) or tmpfs!=expected_tmpfs:
            raise PilotError('runtime_mount_drift')
        wanted={project(tenant)+'_'+name for name in expected['networks']}
        if running and set(networks)!=wanted:raise PilotError('runtime_network_drift')
        bindings=host.get('PortBindings') or {}
        if service=='openhands' and bindings:raise PilotError('agent_port_exposure')
        if service=='ingress' and bindings!={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':str(PORTS[tenant['id']])}]}:
            raise PilotError('ingress_port_exposure')
        for name in (wanted if running else set(networks)):
            data=json.loads(engine.run(['docker','--context','default','network','inspect',name]))[0]
            if data.get('Internal') is not name.endswith('_backend') or data.get('Driver')!='bridge':
                raise PilotError('runtime_network_drift')
        records[service]=cid
    return records


def key(tenant,filename):
    state,_,_=paths(tenant)
    if filename not in ('api-key.txt','secret-key.txt'):raise PilotError('invalid_key_filename')
    descriptors=[]
    try:
        fd=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);descriptors.append(fd)
        for name in ('.openhands','agent-canvas'):
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);descriptors.append(fd)
            detail=os.fstat(fd)
            if detail.st_uid!=tenant['uid'] or detail.st_gid!=tenant['gid'] or stat.S_IMODE(detail.st_mode)!=0o700:
                raise PilotError('unsafe_key_directory')
        # O_NOFOLLOW alone does not prevent a FIFO from blocking before fstat.
        fd=os.open(filename,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd);descriptors.append(fd)
        detail=os.fstat(fd)
        if not stat.S_ISREG(detail.st_mode) or detail.st_uid!=tenant['uid'] or detail.st_nlink!=1 or stat.S_IMODE(detail.st_mode)!=0o600 or detail.st_size>128:
            raise PilotError('unsafe_native_key_file')
        content=os.read(fd,129).decode().strip()
        if not re.fullmatch(r'[a-f0-9]{64}',content):raise PilotError('invalid_native_key')
        return content
    finally:
        for fd in reversed(descriptors):os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def request(tenant,path,credential=None,method='GET',body=None):
    if not path.startswith('/api/') or '..' in path:raise PilotError('invalid_probe_route')
    url=f"http://127.0.0.1:{PORTS[tenant['id']]}"+path
    headers={'Content-Type':'application/json'}
    if credential:headers['X-Session-API-Key']=credential
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    req=urllib.request.Request(url,headers=headers,method=method,
          data=None if body is None else json.dumps(body).encode())
    try:
        with opener.open(req,timeout=4) as response:
            data=response.read(1024*1024+1)
            if len(data)>1024*1024:raise PilotError('oversized_probe_response')
            return response.status,data
    except urllib.error.HTTPError as error:
        code=error.code;error.close();return code,b''
    except (OSError,urllib.error.URLError):raise PilotError('instance_http_unavailable') from None


def health(policy):
    sessions=[];encryption=[]
    for tenant in policy['tenants']:
        sessions.append(key(tenant,'api-key.txt'));encryption.append(key(tenant,'secret-key.txt'))
        status,body=request(tenant,'/api/settings',sessions[-1])
        if status!=200:raise PilotError('authenticated_backend_unavailable')
        try:settings=json.loads(body)
        except (ValueError,UnicodeError):raise PilotError('unexpected_settings_response') from None
        if not isinstance(settings,dict) or 'agent_settings' not in settings:
            raise PilotError('unexpected_settings_response')
    if len(set(sessions))!=2 or len(set(encryption))!=2 or set(sessions)&set(encryption):
        raise PilotError('native_keys_not_distinct')
    return sessions


def acceptance(policy,lock,engine):
    store.check(policy,engine)
    for tenant in policy['tenants']:runtime(engine,tenant,lock)
    sessions=health(policy);results=[];created=[];secrets_created=[];conversations_created=[]
    marker='.instance-canary-'+uuid.uuid4().hex
    try:
        for tenant in policy['tenants']:
            state,workspace,_=paths(tenant)
            for base in (state,workspace):
                p=base/marker;fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                created.append(p)
                try:os.write(fd,b'synthetic instance canary');os.fchown(fd,tenant['uid'],tenant['gid'])
                finally:os.close(fd)
        for index,tenant in enumerate(policy['tenants']):
            own_key=sessions[index];other=policy['tenants'][1-index]
            if request(tenant,'/api/settings')[0] not in (401,403) or request(tenant,'/api/settings',sessions[1-index])[0] not in (401,403):
                raise PilotError('cross_or_anonymous_key_accepted')
            cid=selected(engine,tenant,'openhands')
            foreign=paths(other)[0]/marker
            args=['docker','--context','default','exec','-i',cid,'python','-B','-',str(tenant['uid']),marker,str(foreign)]
            checks=json.loads(engine.run(args,input=(ROOT/'scripts/instances/probe.py').read_bytes()))
            if set(checks)!={'uid_matches','own_state_visible','own_workspace_visible','foreign_host_path_denied'} or any(v is not True for v in checks.values()):
                raise PilotError('instance_filesystem_probe_failed')
            name='INSTANCE_PROBE_'+uuid.uuid4().hex.upper();value='synthetic-'+uuid.uuid4().hex
            path='/api/settings/secrets/'+name
            if request(tenant,path,own_key)[0]!=404 or request(other,path,sessions[1-index])[0]!=404:
                raise PilotError('synthetic_secret_collision')
            secrets_created.append((tenant,own_key,path))
            if request(tenant,'/api/settings/secrets',own_key,'PUT',{'name':name,'value':value,'description':'Synthetic instance isolation probe'})[0]!=200:
                raise PilotError('synthetic_secret_write_failed')
            status,data=request(tenant,path,own_key)
            if status!=200 or data!=value.encode() or request(other,path,sessions[1-index])[0]!=404:
                raise PilotError('synthetic_secret_namespace_not_isolated')
            if request(tenant,path,own_key,'DELETE')[0]!=200 or request(tenant,path,own_key)[0]!=404:
                raise PilotError('synthetic_secret_cleanup_failed')
            secrets_created.remove((tenant,own_key,path))
            identifier=str(uuid.uuid4());conversation_path='/api/conversations/'+identifier
            if request(tenant,conversation_path,own_key)[0]!=404 or request(other,conversation_path,sessions[1-index])[0]!=404:
                raise PilotError('synthetic_conversation_collision')
            conversations_created.append((tenant,own_key,conversation_path))
            if request(tenant,'/api/conversations',own_key,'POST',conversation_payload(identifier))[0]!=201:
                raise PilotError('synthetic_idle_conversation_create_failed')
            if request(tenant,conversation_path,own_key)[0]!=200 or request(other,conversation_path,sessions[1-index])[0]!=404:
                raise PilotError('conversation_namespace_not_isolated')
            if request(tenant,conversation_path,own_key,'DELETE')[0]!=200 or request(tenant,conversation_path,own_key)[0]!=404:
                raise PilotError('synthetic_conversation_cleanup_failed')
            conversations_created.remove((tenant,own_key,conversation_path))
            results.append({'tenant':tenant['id'],'filesystem':'passed','own_authentication':'passed',
              'anonymous_rejected':'passed','foreign_key_rejected':'passed','secret_namespace':'passed','idle_conversation_namespace':'passed'})
    finally:
        for tenant,credential,path in conversations_created:
            try:request(tenant,path,credential,'DELETE')
            except PilotError:pass
        for tenant,credential,path in secrets_created:
            try:request(tenant,path,credential,'DELETE')
            except PilotError:pass
        for p in created:p.unlink()
    return {'status':'passed','instances':results,'household_readiness':'pending',
      'scope':'Synthetic own-state, native key and HTTP secret-store isolation; WebSocket, restart/restore, inference and household login acceptance pending'}


def operate(mode,policy,lock,engine):
    for tenant in policy['tenants']:render(tenant,lock)
    store.check(policy,engine)  # Required mounts verified before any start or mutation.
    available=memory_available() if mode in ('up','plan') else None
    print('[instances] Checking cached images and locked native modules.',file=sys.stderr,flush=True)
    metadata=image_metadata(engine,lock)
    if mode=='plan':
        for tenant in policy['tenants']:
            render(tenant,lock);remap_accounts(metadata['passwd'],tenant,'passwd');remap_accounts(metadata['group'],tenant,'group')
        return {'status':'planned','instances':[{'tenant':t['id'],'uid':t['uid'],'url':f"http://127.0.0.1:{PORTS[t['id']]}/canvas"} for t in policy['tenants']],
          'available_memory_gib':available,'deployment':'pending','household_readiness':'pending','scope':'Cached-image/native compatibility and mounted storage checked; no state/control writes or instance starts'}
    if mode=='up':
        # Collision check before starting either project; existing own ports validated later.
        for tenant in policy['tenants']:
            for service in ('openhands','ingress'):
                cid=selected(engine,tenant,service,required=False)
                if cid:raise PilotError('existing_pilot_use_check_or_down_before_up')
            with socket.socket() as listener:
                try:listener.bind(('127.0.0.1',PORTS[tenant['id']]))
                except OSError:raise PilotError('pilot_port_in_use') from None
        controls(policy,lock,metadata,create=True)
        started=[]
        try:
            for tenant in policy['tenants']:
                compose(engine,tenant,'config','--quiet')
                print('[instances] Starting '+tenant['id']+'; native startup may take a minute.',file=sys.stderr,flush=True)
                started.append(tenant)
                compose(engine,tenant,'up','-d','--pull','never')
            for attempt in range(45):
                try:health(policy);break
                except (PilotError,FileNotFoundError):
                    if attempt==44:raise PilotError('instance_startup_timeout') from None
                    if attempt%5==0:print('[instances] Waiting for both authenticated backends.',file=sys.stderr,flush=True)
                    time.sleep(2)
            for tenant in policy['tenants']:runtime(engine,tenant,lock)
        except BaseException as error:
            recovery={}
            for tenant in started:
                try:
                    compose(engine,tenant,'stop')
                    recovery[tenant['id']]='stop_completed'
                except store.StorageError:
                    recovery[tenant['id']]='stop_failed'
            if isinstance(error,(PilotError,store.StorageError)):
                error.recovery=recovery
            raise
        return {'status':'started','instances':2,'live_isolation':'pending','household_readiness':'pending'}
    controls(policy,lock,metadata,create=False)
    if mode=='down':
        # Inspect before stopping, and never delete data/volumes or unrelated projects.
        for tenant in policy['tenants']:runtime(engine,tenant,lock,required=False,running=False)
        for tenant in policy['tenants']:compose(engine,tenant,'down')
        return {'status':'stopped','state_preserved':True,'household_readiness':'pending'}
    for tenant in policy['tenants']:runtime(engine,tenant,lock)
    if mode=='accept':return acceptance(policy,lock,engine)
    if mode in ('network-check','websocket-check','recovery-check'):
        import isolation,recovery
        functions={'network-check':isolation.network_check,'websocket-check':isolation.websocket_check,
                   'recovery-check':recovery.recovery_check}
        return functions[mode](sys.modules[__name__],policy,lock,engine)
    health(policy)
    return {'status':'passed','instances':2,'live_isolation':'pending','household_readiness':'pending',
      'scope':'Applied runtime and authenticated API health; cross-key/state probes use accept'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['config','plan','up','check','accept','down','diagnose','network-check','websocket-check','recovery-check']);args=parser.parse_args()
    os.umask(0o077)
    try:
        policy=store.load_policy();lock=store.read_yaml(ROOT/'infra/openhands/versions.yaml')
        if args.mode=='config':
            for tenant in policy['tenants']:render(tenant,lock)
            report={'status':'passed','scope':'Source configuration only; no Docker or storage mutation'}
        else:
            if os.geteuid()!=0:raise PilotError('host_admin_required')
            if args.mode=='diagnose':
                report=diagnose(policy,lock,store.Engine())
                report.update(time_utc=datetime.now(timezone.utc).isoformat(),checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
                print(json.dumps(report,indent=2));return 0
            store.safe_path(BASE.parent)
            if not BASE.parent.is_dir():raise PilotError('storage_setup_required')
            # Same host storage lock prevents concurrent unmount during the operation.
            fd=os.open(BASE.parent/'storage-pilot.lock',os.O_WRONLY|os.O_NOFOLLOW)
            try:
                detail=os.fstat(fd)
                if detail.st_uid!=0 or detail.st_nlink!=1 or stat.S_IMODE(detail.st_mode)!=0o600:raise PilotError('unsafe_storage_lock')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                report=operate(args.mode,policy,lock,store.Engine())
            finally:os.close(fd)
    except (PilotError,store.StorageError) as error:
        report={'status':'failed','error':str(error),'household_readiness':'pending'}
        if isinstance(error,PilotError) and error.details:report.update(error.details)
        if getattr(error,'recovery',None):report['recovery']=error.recovery
    except Exception:
        report={'status':'failed','error':'instance_operation_failed_details_withheld','household_readiness':'pending'}
    report.update(time_utc=datetime.now(timezone.utc).isoformat(),checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.mode in ('network-check','websocket-check','recovery-check'):
        sources=['scripts/instances/instances.py','scripts/instances/isolation.py',
                 'scripts/instances/recovery.py','scripts/instances/network_probe.py',
                 'scripts/instances/websocket_probe.py','infra/openhands/instances/compose.yaml']
        report['probe_sources_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    print(json.dumps(report,indent=2));return int(report['status']=='failed')

if __name__=='__main__':raise SystemExit(main())
