"""Separate named-user instances, bounded filesystems and native identity bootstrap."""
import argparse,fcntl,hashlib,hmac,importlib.util,ipaddress,json,os,re,ssl,stat,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
BASE=Path('/var/lib/agent-platform/household')
STORE=BASE/'storage'
POLICY={'schema_version':1,'purpose':'household_user_instances','host_reserve_gib':20,
        'volumes_mib':{'workspace':2048,'state':512},'tenants':[
        {'id':'alejandro','uid':200101,'gid':200101,'https_port':8444},
        {'id':'kimberly','uid':200102,'gid':200102,'https_port':8445}]}
class HouseholdError(ValueError):pass

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def helpers():
    gateway=module('household_gateway','scripts/gateway/gateway.py')
    pilot=module('household_pilot','scripts/instances/instances.py')
    return gateway,pilot,pilot.store

def source():
    gateway,pilot,store=helpers();check=gateway.source()
    if not check.same(store.read_yaml(ROOT/'config/household/users.yaml'),POLICY):raise HouseholdError('household_policy_drift')
    return gateway,pilot,store

def blueprint(address):
    ipaddress.IPv4Address(address)
    text=(ROOT/'infra/identity/household-blueprint.yaml').read_text().split('- id: outpost\n')[0]
    text=text.replace('household-','family-').replace('probe-a','alejandro').replace('probe-b','kimberly')
    for name,port in [('alejandro',8444),('kimberly',8445)]:
        text=text.replace('https://'+name+'.home.arpa',f'https://{address}:{port}')
    text=text.replace('domain: login.home.arpa','domain: '+address+':8443').replace('default: true','default: false')
    # Approved side-panel design: keep authentication stages native and place content on the right.
    text=text.replace('    designation:', '    layout: content_right\n    designation:')
    # TOTP works on IP origins; passkey enrollment requires a suitable DNS RP ID.
    text=re.sub(r'- id: webauthn\n.*?(?=- id: )','',text,flags=re.S)
    text=text.replace('    - webauthn\n','').replace("    - !KeyOf 'webauthn'\n",'')
    css=(ROOT/'infra/identity/household-light.css').read_text()
    text=text.replace('    branding_title: Local Agent Platform\n',
        '    branding_title: Local Agent Platform\n    branding_custom_css: |\n'+''.join('      '+line+'\n' for line in css.splitlines()))
    template=(ROOT/'infra/identity/invitation-blueprint.yaml').read_text()
    expression=(ROOT/'scripts/household/invitation-policy.expression').read_text()
    for tenant in POLICY['tenants']:
        block=template.replace('__EXPRESSION__','\n'.join('      '+line for line in expression.splitlines()))
        text+='\n'+block.replace('__USER__',tenant['id']).replace(
            '__APPLICATION_URL__',f"https://{address}:{tenant['https_port']}/canvas")
    return text

def storage_policy():
    return {**POLICY,'tenants':[{k:v for k,v in t.items() if k!='https_port'} for t in POLICY['tenants']]}

def paths(tenant):
    return STORE/'mounts'/tenant['id']/'state',STORE/'mounts'/tenant['id']/'workspace',BASE/'control'/tenant['id']

def render(tenant,lock):
    gateway,pilot,store=helpers();state,workspace,control=paths(tenant)
    values={'PILOT_IMAGE':lock['image'],'PILOT_PROXY_IMAGE':lock['proxy']['image'],
       'PILOT_USER':f"{tenant['uid']}:{tenant['gid']}",'PILOT_UID':str(tenant['uid']),
       'PILOT_STATE':str(state),'PILOT_WORKSPACE':str(workspace),'PILOT_CONTROL':str(control),
       'PILOT_LAUNCHER':str(ROOT/'scripts/openhands/start-agent-server.py'),
       'PILOT_ENTRYPOINT':str(ROOT/'infra/openhands/instances/entrypoint.sh'),
       'PILOT_NGINX':str(ROOT/'infra/openhands/nginx.conf'),'PILOT_PORT':'0'}
    text=(ROOT/'infra/openhands/instances/compose.yaml').read_text()
    config=store.read_yaml(ROOT/'infra/openhands/instances/compose.yaml')
    def visit(value):
        if isinstance(value,dict):return {k:visit(v) for k,v in value.items()}
        if isinstance(value,list):return [visit(v) for v in value]
        if isinstance(value,str):return re.sub(r'\$\{([A-Z_]+)\}',lambda m:values[m[1]],value)
        return value
    config=visit(config);agent=config['services']['openhands'];ingress=config['services']['ingress']
    agent['environment']['AGENT_CANVAS_ALLOW_LAN_SESSION_KEY']='true'
    ingress.pop('ports')
    relay={k:v for k,v in ingress.items() if k not in ('networks','depends_on','volumes')}
    relay['networks']=['backend','models']
    relay['volumes']=[{'type':'bind','source':str(control/'model-nginx.conf'),'target':'/etc/nginx/nginx.conf',
                       'read_only':True,'bind':{'create_host_path':False}}]
    config['services']['model-relay']=relay
    config['networks']['models']={'external':True,'name':'agent-platform-local_default'}
    return config

def model_config():
    return '''worker_processes 1;
pid /tmp/nginx.pid;
error_log /dev/stderr error;
events { worker_connections 64; }
http {
 access_log off;
 client_body_temp_path /tmp/body;
 proxy_temp_path /tmp/proxy;
 fastcgi_temp_path /tmp/fastcgi;
 uwsgi_temp_path /tmp/uwsgi;
 scgi_temp_path /tmp/scgi;
 server {
  listen 8080;
  client_max_body_size 8m;
  location = /v1/models { limit_except GET { deny all; } proxy_pass http://ollama:11434; }
  location = /v1/chat/completions { limit_except POST { deny all; } proxy_pass http://ollama:11434; proxy_buffering off; proxy_read_timeout 180s; }
  location / { return 404; }
 }
}
'''

LEGACY_MODEL_CONFIG_SHA256='5c7903aff9fac9ee0a8005c55107c81298d27b3e4de9d4d46e71a9ea3b852b94'

def prepare_model_control(path,pilot,create=False):
    """Migrate only the reviewed old public relay config; reject arbitrary drift."""
    data=model_config().encode()
    if path.exists() and not path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o644:
            raise HouseholdError('unsafe_model_relay_control')
        old=path.read_bytes()
        if old!=data and hashlib.sha256(old).hexdigest()==LEGACY_MODEL_CONFIG_SHA256:
            # Verify root ownership, mode, link count and parent before replacement.
            pilot.protected_file(path,old,False)
            import tempfile
            fd,name=tempfile.mkstemp(prefix='.model-nginx-',dir=path.parent)
            temporary=Path(name)
            try:
                with os.fdopen(fd,'wb') as stream:
                    os.fchmod(stream.fileno(),0o644);stream.write(data);stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,path)
            finally:temporary.unlink(missing_ok=True)
    pilot.protected_file(path,data,create)


def validate_model_relay(engine,tenant,lock):
    """Run the pinned nginx parser under the deployed non-root/readonly restrictions."""
    control=paths(tenant)[2]
    engine.run(['docker','--context','default','run','--rm','--network','agent-platform-local_default',
        '--user','101:101','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--security-opt','apparmor:docker-default','--memory','64m','--cpus','0.5','--pids-limit','64',
        '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777',
        '--mount','type=bind,src='+str(control/'model-nginx.conf')+',dst=/etc/nginx/nginx.conf,readonly',
        '--entrypoint','nginx',lock['proxy']['image'],'-t'],timeout=30)


IDENTITY_STAGES={'django_setup','account_inventory','transaction','password_validation','blueprint_validation',
    'blueprint_import','application_membership','embedded_outpost','embedded_outpost_lookup',
    'embedded_outpost_config','embedded_outpost_providers','embedded_outpost_save','embedded_outpost_readback',
    'invitation_issue','invitation_revoke','invitation_readback','invitation_policy_probe','diagnostic_readback','brand_appearance',
    'brand_domain_migration','brand_scope','brand_css','brand_theme_write','brand_theme_readback','brand_flow_lookup',
    'brand_layout_family_login','brand_layout_family_authorize','brand_layout_family_logout',
    'brand_layout_family_enroll_alejandro','brand_layout_family_enroll_kimberly'}

def identity(engine,payload):
    code=(ROOT/'scripts/household/identity-native.py').read_text()
    try:
        output=engine.run(['docker','--context','default','exec','-i','agent-platform-identity-local-server-1',
                          'python','-B','-c',code],input=json.dumps(payload).encode(),timeout=120)
    except Exception as error:
        # Engine.run deliberately discards native output. Preserve only its fixed categories.
        category={'operation_unavailable_or_timed_out':'unavailable_or_timed_out',
                  'operation_failed':'exec_failed','invalid_operation_output':'output_too_large'}.get(str(error),'transport_failed')
        raise HouseholdError('household_identity_'+category) from None
    try:result=json.loads(output)
    except (ValueError,UnicodeError,TypeError):raise HouseholdError('household_identity_invalid_json_response') from None
    if not isinstance(result,dict) or result.get('status') not in ('passed','failed'):
        raise HouseholdError('household_identity_invalid_response_schema')
    if result['status']!='passed':
        stage=result.get('stage','unknown')
        if not isinstance(stage,str) or stage not in IDENTITY_STAGES:stage='unknown'
        kind=result.get('exception_category')
        suffix='_'+kind if isinstance(kind,str) and kind in {'type_error','attribute_error','lookup_error','database_error','assertion_failed','other'} else ''
        raise HouseholdError('household_identity_operation_failed_'+stage+suffix)
    return result


def diagnose_root():
    """Read only fixed process state and public identity configuration booleans."""
    if os.geteuid()!=0:raise HouseholdError('host_admin_required')
    _,_,store=source();engine=store.Engine();services={}
    for service in ('database','server','worker'):
        try:
            raw=json.loads(engine.run(['docker','--context','default','inspect','--format','{{json .State}}',
                                     'agent-platform-identity-local-'+service+'-1'],timeout=20))
            services[service]={'running':raw.get('Running') is True,'oom_killed':raw.get('OOMKilled') is True,
                'status':raw.get('Status') if raw.get('Status') in {'running','exited','created','restarting','paused','dead'} else 'unknown',
                'exit_code':raw.get('ExitCode') if type(raw.get('ExitCode')) is int else None}
        except Exception:services[service]={'status':'unavailable'}
    personal={}
    for tenant in POLICY['tenants']:
        personal[tenant['id']]={}
        for service in ('openhands','ingress','model-relay'):
            try:
                raw=json.loads(engine.run(['docker','--context','default','inspect','--format','{{json .State}}',
                    'agent-platform-household-'+tenant['id']+'-'+service+'-1'],timeout=20))
                personal[tenant['id']][service]={'running':raw.get('Running') is True,
                    'oom_killed':raw.get('OOMKilled') is True,'exit_code':raw.get('ExitCode') if type(raw.get('ExitCode')) is int else None}
            except Exception:personal[tenant['id']][service]={'status':'unavailable'}
    result={'status':'collected','household_instances':personal,'services':services,'scope':'Read-only process state and public ORM/configuration checks; no imports, accounts or restarts'}
    try:result['identity']=identity(engine,{'action':'diagnose'})
    except HouseholdError as error:result['identity']={'status':'failed','error':str(error)}
    return result

def environment_root():
    if os.geteuid()!=0:raise HouseholdError('household_setup_requires_host_admin')
    gateway,pilot,store=source();engine=store.Engine();store.safe_path(BASE)
    policy=storage_policy()
    # Reuse the tested fixed-image/mount primitives with an independent purpose/base.
    store.prepare(policy,engine,base=STORE)
    lock=store.read_yaml(ROOT/'infra/openhands/versions.yaml')
    for image in (lock['image'],lock['proxy']['image']):
        engine.run(['docker','--context','default','pull',image],timeout=1200)
    metadata=pilot.image_metadata(engine,lock)
    (BASE/'control').mkdir(mode=0o700,exist_ok=True);store.safe_path(BASE/'control')
    for tenant in POLICY['tenants']:
        state,workspace,control=paths(tenant);control.mkdir(mode=0o700,exist_ok=True);store.safe_path(control)
        for folder in ('.openhands','.cache','.config','.local','workspace'):pilot.safe_child(state,folder,tenant,True)
        for kind in ('passwd','group'):pilot.protected_file(control/kind,pilot.remap_accounts(metadata[kind],tenant,kind).encode(),True)
        for name,text in [('compose.yaml',yaml.safe_dump(render(tenant,lock),sort_keys=False))]:
            pilot.protected_file(control/name,text.encode(),True)
        prepare_model_control(control/'model-nginx.conf',pilot,True)
    return {'status':'prepared','scope':'Separate household bounded storage, controls and cached images; no accounts or services created'}


def setup_step(stage, callback, *args, **kwargs):
    """Retain only fixed stage/category codes across privileged setup failures."""
    try:return callback(*args,**kwargs)
    except HouseholdError:raise
    except Exception as error:
        category={'operation_unavailable_or_timed_out':'unavailable_or_timed_out',
                  'operation_failed':'operation_failed','invalid_operation_output':'output_too_large'}.get(str(error),'failed')
        raise HouseholdError('household_setup_'+stage+'_'+category) from None


def models_check_root(tune=False):
    if os.geteuid()!=0:raise HouseholdError('host_admin_required')
    runtime_root()
    _,_,store=source();engine=store.Engine();instances={}
    for tenant in POLICY['tenants']:
        try:
            raw=engine.run(['docker','--context','default','exec','-i',
                'agent-platform-household-'+tenant['id']+'-openhands-1','python','-B','-'],
                input=(ROOT/('scripts/household/tune-model.py' if tune else 'scripts/household/check-models.py')).read_bytes(),timeout=90)
            result=json.loads(raw)
            if not isinstance(result,dict) or result.get('status')!=('passed' if tune else 'collected'):raise ValueError()
            instances[tenant['id']]=result
        except Exception:instances[tenant['id']]={'status':'unavailable'}
    return {'status':('passed' if all(item.get('status')=='passed' for item in instances.values()) else 'failed') if tune else 'collected','instances':instances,
            'scope':'Verified household containers; managed model tuning' if tune else 'Verified household containers; local API/model readback only, no browser-session acceptance'}


def seed_agent(engine, project):
    raw=engine.run(['docker','--context','default','exec','-i',project+'-openhands-1','python','-B','-'],
                   input=(ROOT/'scripts/household/seed-agent.py').read_bytes(),timeout=300)
    try:result=json.loads(raw)
    except (ValueError,UnicodeError,TypeError):raise HouseholdError('household_agent_seed_invalid_response') from None
    if not isinstance(result,dict):raise HouseholdError('household_agent_seed_invalid_response')
    if result.get('status')!='passed':
        stage=result.get('stage')
        if not isinstance(stage,str) or stage not in {'native_key','backend','model_discovery','profile_create','profile_activate','settings_readback','marker_write'}:stage='unknown'
        category=result.get('category')
        suffix='_'+category if isinstance(category,str) and category in {'http_4xx','http_5xx','network_unavailable','invalid_json','invalid_schema','model_not_listed','other'} else ''
        raise HouseholdError('household_agent_seed_failed_'+stage+suffix)
    return result


def setup_root(payload):
    if os.geteuid()!=0:raise HouseholdError('household_setup_requires_host_admin')
    gateway,pilot,store=source();engine=store.Engine()
    setup_step('storage',store.check,storage_policy(),engine,base=STORE)
    lock=store.read_yaml(ROOT/'infra/openhands/versions.yaml')
    for tenant in POLICY['tenants']:
        control=paths(tenant)[2]
        pilot.protected_file(control/'compose.yaml',yaml.safe_dump(render(tenant,lock),sort_keys=False).encode(),False)
        setup_step('relay_control_'+tenant['id'],prepare_model_control,control/'model-nginx.conf',pilot,False)
        setup_step('relay_config_'+tenant['id'],validate_model_relay,engine,tenant,lock)
    print('[household] Importing and verifying identity configuration; no account passwords are set.',file=sys.stderr,flush=True)
    result=identity(engine,payload)
    print('[household] Identity configuration and native policy checks passed.',file=sys.stderr,flush=True)
    for tenant in POLICY['tenants']:
        control=paths(tenant)[2];project='agent-platform-household-'+tenant['id']
        print('[household] Starting isolated instance for '+tenant['id']+'.',file=sys.stderr,flush=True)
        setup_step('start_'+tenant['id'],engine.run,['docker','--context','default','compose','--project-name',project,'--file',str(control/'compose.yaml'),
                    'up','-d','--pull','never'],timeout=180)
        # A bind-file content change does not change the Compose service hash.
        # Recreate only the relay to use the new inode and resolve the current Ollama IP.
        setup_step('relay_start_'+tenant['id'],engine.run,['docker','--context','default','compose',
            '--project-name',project,'--file',str(control/'compose.yaml'),'up','-d','--no-deps',
            '--force-recreate','--pull','never','model-relay'],timeout=90)
        setup_step('seed_'+tenant['id'],seed_agent,engine,project)
    keys=[]
    for tenant in POLICY['tenants']:
        path=paths(tenant)[0]/'.openhands/agent-canvas/api-key.txt'
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=tenant['uid'] or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:raise HouseholdError('unsafe_household_native_key')
            key=os.read(fd,129).strip()
            if not re.fullmatch(rb'[a-f0-9]{64}',key):raise HouseholdError('invalid_household_native_key')
            keys.append(key)
        finally:os.close(fd)
    if hmac.compare_digest(*keys):raise HouseholdError('household_native_keys_not_distinct')
    setup_step('runtime',runtime_root)
    return {'status':'prepared','users':[t['id'] for t in POLICY['tenants']],'separate_instances':'passed',
            'separate_bounded_storage':'passed','native_keys_distinct':'passed','local_model_configured':'passed',
            'scope':'Invitation enrollment/instances prepared; no new passwords or users created; gateway up and browser MFA/agent acceptance still required'}

def runtime_root():
    if os.geteuid()!=0:raise HouseholdError('host_admin_required')
    gateway,pilot,store=source();engine=store.Engine();store.check(storage_policy(),engine,base=STORE)
    lock=store.read_yaml(ROOT/'infra/openhands/versions.yaml')
    inspected_networks=set()
    for tenant in POLICY['tenants']:
        config=render(tenant,lock);prefix='agent-platform-household-'+tenant['id']
        for service,expected in config['services'].items():
            info=json.loads(engine.run(['docker','--context','default','inspect','--format','{{json .}}',prefix+'-'+service+'-1']))
            host=info['HostConfig'];actual=info['Config'];labels=actual.get('Labels',{})
            memory={'2g':2*1024**3,'64m':64*1024**2}[expected['mem_limit']]
            if (not info['State']['Running'] or actual['Image']!=expected['image'] or actual['User']!=expected['user']
                or labels.get('com.docker.compose.project')!=prefix or labels.get('com.docker.compose.service')!=service
                or host['ReadonlyRootfs'] is not True or host['Privileged'] or host.get('PortBindings') or host.get('CapAdd')
                or set(host.get('CapDrop') or [])!={'ALL'} or host['Memory']!=memory or host['PidsLimit']!=expected['pids_limit']
                or host['NanoCpus']!=int(expected['cpus']*1000000000) or info.get('AppArmorProfile')!='docker-default'
                or set(host['SecurityOpt'])!={'no-new-privileges:true','apparmor:docker-default'}
                or host.get('Devices') or host.get('DeviceRequests') or host.get('PidMode') or host.get('IpcMode')=='host'):
                raise HouseholdError('household_runtime_process_drift_'+tenant['id']+'_'+service)
            wanted={prefix+'_'+name if name!='models' else 'agent-platform-local_default' for name in expected['networks']}
            if set(info['NetworkSettings']['Networks'])!=wanted:raise HouseholdError('household_runtime_network_drift')
            for name in wanted-inspected_networks:
                network=json.loads(engine.run(['docker','--context','default','network','inspect',name]))[0]
                if network.get('Driver')!='bridge' or network.get('Internal') is not name.endswith('_backend'):raise HouseholdError('household_network_boundary_drift')
                inspected_networks.add(name)
            mounts={(m['Destination'],m['Source'],m['RW']) for m in info['Mounts'] if m['Type']=='bind'}
            wanted_mounts={(m['target'],m['source'],not m.get('read_only',False)) for m in expected['volumes']}
            if mounts!=wanted_mounts or any(m['Type']=='volume' for m in info['Mounts']):raise HouseholdError('household_runtime_mount_drift')
    return {'status':'passed','instances':2,'runtime_process_mount_networks':'passed','bounded_storage':'passed'}

def root_call(action,payload):
    helper=helpers()[0].pki().backup()
    with helper.memory_file() as data,helper.memory_file() as result:
        data.write(json.dumps(payload).encode());data.seek(0)
        try:
            helper.stream_command(['sudo','-n','env','-i','PATH=/usr/sbin:/usr/bin:/sbin:/bin',
                str(ROOT/'.venv/bin/python3'),'-B',str(ROOT/'scripts/household/household.py'),action],data,result,
                timeout=1500,detached=False)
        except helper.BackupError:
            result.seek(0)
            try:category=json.load(result).get('error','household_privileged_operation_failed')
            except (ValueError,AttributeError):category='household_privileged_operation_failed'
            if not isinstance(category,str) or not re.fullmatch(r'[a-z0-9_]{1,160}',category):category='household_privileged_operation_failed'
            raise HouseholdError(category) from None
        result.seek(0);return json.load(result)


def check_authorization_edges(gateway):
    release,network=gateway.state()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    context=ssl.create_default_context(cafile=str(release/'trust/root.crt'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=context))
    for tenant in POLICY['tenants']:
        url=f"https://{network['address']}:{tenant['https_port']}/canvas"
        for headers in ({},{'X-Authentik-Username':tenant['id'],'X-Session-API-Key':'synthetic-invalid-native-key'}):
            for attempt in range(20):
                try:
                    with opener.open(urllib.request.Request(url,headers=headers),timeout=5) as response:
                        if response.status==200:raise HouseholdError('anonymous_or_forged_identity_reached_canvas')
                        status=response.status
                except urllib.error.HTTPError as error:status=error.code;error.close()
                if status in (302,303,307,401,403):break
                if status>=500 and attempt<19:time.sleep(2);continue
                raise HouseholdError('household_authentication_gate_not_ready')
    return {'anonymous_and_forged_identity_denied':'passed'}


def identity_payload():
    gateway,_,_=source();_,network=gateway.state()
    urls={t['id']:f"https://{network['address']}:{t['https_port']}" for t in POLICY['tenants']}
    return {'action':'apply','blueprint':blueprint(network['address']),
            'branding_css':(ROOT/'infra/identity/household-light.css').read_text(),
            'urls':urls,'login_url':f"https://{network['address']}:8443"}


def owner_setup():
    payload=identity_payload()
    root_call('root-status',{'action':'status'})
    return root_call('root-setup',payload)


def check_public_brand():
    """Verify the native brand chosen for the actual HTTPS Host, including port."""
    gateway,_,_=source();release,network=gateway.state()
    context=ssl.create_default_context(cafile=str(release/'trust/root.crt'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(f"https://{network['address']}:8443/api/v3/core/brands/current/",timeout=10) as response:data=json.load(response)
    except Exception:raise HouseholdError('household_public_brand_unavailable') from None
    expected=(ROOT/'infra/identity/household-light.css').read_text().strip()
    if (not isinstance(data,dict) or data.get('matched_domain')!=network['address']+':8443'
        or data.get('ui_theme')!='light' or not isinstance(data.get('branding_custom_css'),str)
        or data['branding_custom_css'].strip()!=expected):raise HouseholdError('household_public_brand_mismatch')
    return {'public_https_brand':'passed','light_theme_and_css':'passed'}


def check_public_browser_routes():
    """Probe browser authorization redirects, with no owner credentials or cookies."""
    from urllib.parse import urlencode, urlsplit
    gateway,_,_=source();release,network=gateway.state()
    context=ssl.create_default_context(cafile=str(release/'trust/root.crt'))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),
        urllib.request.HTTPSHandler(context=context))
    expected='https://'+network['address']+':8443'
    for tenant in POLICY['tenants']:
        origin=f"https://{network['address']}:{tenant['https_port']}"
        url=origin+'/outpost.goauthentik.io/start?'+urlencode({'rd':origin+'/canvas'})
        for attempt in range(6):
            status=None;location=None
            try:
                with opener.open(url,timeout=5) as response:
                    status=response.status;location=response.headers.get('Location')
            except urllib.error.HTTPError as error:
                status=error.code;location=error.headers.get('Location');error.close()
            except Exception:pass
            try:
                parsed=urlsplit(location or '')
                valid=(status in (302,303) and parsed.scheme=='https'
                    and parsed.netloc==urlsplit(expected).netloc
                    and parsed.username is None and parsed.password is None
                    and not parsed.fragment and parsed.path=='/application/o/authorize/')
            except ValueError:valid=False
            if valid:break
            if attempt==5:raise HouseholdError('household_public_login_redirect_invalid')
            print('[household] Waiting for public login route refresh.',flush=True)
            time.sleep(2)
    return {'public_login_redirects':'passed'}


def owner_identity_apply():
    result=root_call('root-status',identity_payload())
    result.update(check_public_brand())
    result.update(check_public_browser_routes())
    result['scope']='Identity policy/appearance updated; public HTTPS brand and both login redirect origins verified; no invitations issued, passwords reset or agent containers restarted'
    return result


def save_invitation(username, result, directory=None):
    """Create a new owner-only credential file; never print the bearer link."""
    import secrets
    directory=directory or Path.home()/'.local/share/agent-platform/invitations'
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Reject symlink ancestors and a shared final directory before writing a credential.
    for parent in [directory,*directory.parents]:
        if parent.is_symlink():raise HouseholdError('unsafe_invitation_directory')
    info=directory.stat()
    if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise HouseholdError('unsafe_invitation_directory')
    path=directory/(username+'-'+secrets.token_hex(8)+'.txt')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write('Private invitation for '+username+'\nExpires: '+result['expires']+'\n'+result['invitation_url']+'\n')
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {'status':'issued','username':username,'expires':result['expires'],'private_invitation_file':str(path),
            'previous_pending_invitation':'revoked','scope':'Share the private link manually; browser password/TOTP acceptance pending'}


def owner_invitation(username,revoke=False):
    if username not in {t['id'] for t in POLICY['tenants']}:raise HouseholdError('unknown_household_username')
    gateway,_,_=source();_,network=gateway.state()
    result=root_call('root-status',{'action':'invite-revoke' if revoke else 'invite','username':username,
                                  'login_url':f"https://{network['address']}:8443"})
    return result if revoke else save_invitation(username,result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','setup','check','root-runtime','root-status','root-setup','root-environment','invite','invite-revoke','diagnose','root-diagnose','logs','root-logs','identity-apply','models-check','root-models-check','models-tune','root-models-tune']);parser.add_argument('--username',choices=['alejandro','kimberly']);args=parser.parse_args()
    try:
        gateway,pilot,store=source()
        if args.mode=='plan':
            network=gateway.lan();result={'status':'planned','users':[{'username':t['id'],'url':f"https://{network['address']}:{t['https_port']}/canvas"} for t in POLICY['tenants']]}
        elif args.mode=='setup':result=owner_setup()
        elif args.mode=='identity-apply':result=owner_identity_apply()
        elif args.mode=='models-check':result=root_call('root-models-check',{})
        elif args.mode=='root-models-check':result=models_check_root()
        elif args.mode=='models-tune':result=root_call('root-models-tune',{})
        elif args.mode=='root-models-tune':result=models_check_root(tune=True)
        elif args.mode=='diagnose':result=root_call('root-diagnose',{})
        elif args.mode=='root-diagnose':result=diagnose_root()
        elif args.mode=='logs':result=root_call('root-logs',{})
        elif args.mode=='root-logs':
            if os.geteuid()!=0:raise HouseholdError('host_admin_required')
            result=module('household_identity_logs','scripts/identity/log-diagnostics.py').collect()
            result['identity_state']=diagnose_root()
        elif args.mode in ('invite','invite-revoke'):result=owner_invitation(args.username,args.mode=='invite-revoke')
        elif args.mode=='check':
            result=root_call('root-runtime',{})
            gateway.check()
            result.update(check_authorization_edges(gateway))
            result.update(check_public_brand())
            result.update(check_public_browser_routes())
            result.update(browser_mfa_and_real_agent_execution='pending',scope='Applied runtime and HTTPS; both account/browser acceptances remain owner-run')
        elif args.mode=='root-runtime':result=runtime_root()
        elif args.mode=='root-status':
            if os.geteuid()!=0:raise HouseholdError('host_admin_required')
            result=identity(store.Engine(),json.load(sys.stdin))
        else:
            # Preserve the established root-owned storage/control boundary.
            BASE.parent.mkdir(mode=0o700,exist_ok=True);store.safe_path(BASE.parent)
            fd=os.open(BASE.parent/'household.lock',os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
            try:
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:raise HouseholdError('unsafe_household_lock')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                result=environment_root() if args.mode=='root-environment' else setup_root(json.load(sys.stdin))
            finally:os.close(fd)
    except Exception as error:
        result={'status':'failed','error':str(error) if isinstance(error,HouseholdError) else 'household_operation_failed_details_withheld',
                'existing_accounts_and_data':'preserved_no_automatic_deletion'}
    result['household_readiness']='pending';print(json.dumps(result,indent=2));return int(result['status']=='failed')
if __name__=='__main__':raise SystemExit(main())
