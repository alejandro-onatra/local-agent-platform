"""Owner-operated HTTPS household gateway; per-user agent routes, no CA key mounts."""
import argparse
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import resource
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
BASE=Path.home()/'.local/share/agent-platform/gateway'
IMAGE='caddy@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f'
PROFILE={'schema_version':1,'purpose':'household_users_https',
    'hostnames':['login.home.arpa','portal.home.arpa'],'https_port':8443,'public_trust_port':8080,
    'leaf_lifetime_hours':720,'root_fingerprint_sha256':'e08db0333e0e5efee452e90a56688ecf3f02157496541e56372638f48762d8bc',
    'intermediate_fingerprint_sha256':'d83278b69d446d697f5a14fc1f226d9cd7be670c65e2b3cbf66f6e1939d2ef1e',
    'root_key_mounted':False,'access_logs':False,'openhands_routes':True,'renewal':'supervised_task'}
# Update only with reviewed source/template changes and regression validation.
SOURCE_HASHES={'infra/gateway/compose.yaml': '8152e49e6c433ee138ede766e58e650df074ae9564b40b6f66e1bffabdc3d54f', 'infra/gateway/Caddyfile': '5c4eb6461b87810db6ebbce5074916b6fa027b72c970c4d19e2354f10262c00c', 'infra/gateway/entrypoint.sh': '440c55213de5127a8698719f63c31ae1ceac9566270925a8201bf19898ffceba'}
class GatewayError(ValueError):
    def __init__(self,code,diagnostic=None):
        super().__init__(code);self.diagnostic=diagnostic


def command_diagnostic(result):
    # Inspect in memory; publish only fixed categories, never native stderr/stdout.
    text=(result.stderr+result.stdout).lower()
    categories=[('sudo_authentication_required',(b'a password is required',b'interactive authentication is required')),
        ('docker_daemon_unavailable',(b'cannot connect to the docker daemon',b'connection refused')),
        ('registry_authentication_failed',(b'unauthorized',b'authentication required',b'pull access denied')),
        ('registry_certificate_failed',(b'x509:',b'certificate signed by unknown authority')),
        ('permission_or_file_capability_denied',(b'operation not permitted',b'permission denied')),
        ('network_resolution_or_timeout',(b'no such host',b'network is unreachable',b'i/o timeout',b'tls handshake timeout')),
        ('executable_unavailable',(b'executable file not found',b'no such file or directory'))]
    category=next((category for category,markers in categories if any(marker in text for marker in markers)),'unclassified_command_failure')
    return {'category':category,'exit_code':result.returncode}



def pki():
    spec=importlib.util.spec_from_file_location('gateway_pki',ROOT/'scripts/pki/pki.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(args,timeout=60):
    try:result=subprocess.run(list(map(str,args)),capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired:raise GatewayError('gateway_command_timeout',{'category':'command_timeout'}) from None
    except OSError:raise GatewayError('gateway_command_unavailable',{'category':'command_unavailable'}) from None
    if result.returncode:raise GatewayError('gateway_command_failed_details_withheld',command_diagnostic(result))
    return result.stdout


def source():
    helper=pki().backup().local_module().native().source_module()
    if not helper.same(helper.parse((ROOT/'config/gateway/pilot.yaml').read_bytes()),PROFILE):
        raise GatewayError('gateway_profile_drift')
    expected={'version':'2.11.7','tag':'2.11.7-alpine','image':IMAGE,'resolved_at':'2026-10-25'}
    if not helper.same(helper.parse((ROOT/'infra/gateway/versions.yaml').read_bytes()),expected):
        raise GatewayError('gateway_image_lock_drift')
    for name,digest in SOURCE_HASHES.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise GatewayError('gateway_template_drift')
    return helper


def tools():
    p=pki();p.profile();p.tool();p.openssl_tool()
    caddy=shutil.which('caddy')
    if not caddy or not run([caddy,'version']).startswith(b'v2.11.7 '):raise GatewayError('mise_gateway_tools_required')
    return Path(caddy)


def private_address(value):
    address=ipaddress.IPv4Address(value)
    if not any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise GatewayError('rfc1918_lan_address_required')
    return address


def lan(records=None):
    if records is None:records=json.loads(run(['ip','-json','-4','address','show','scope','global']))
    choices=[]
    for row in records:
        if not {'UP','LOWER_UP'}<=set(row.get('flags',[])):continue
        if row.get('ifname','').startswith(('br-','docker','veth','tun','tap','wg','lo')):continue
        for info in row.get('addr_info',[]):
            if info.get('family')!='inet' or info.get('scope')!='global':continue
            address=private_address(info['local']);prefix=info['prefixlen']
            if type(prefix) is not int or not 16<=prefix<=30:raise GatewayError('review_lan_prefix')
            network=ipaddress.IPv4Network(f'{address}/{prefix}',strict=False)
            if address in (network.network_address,network.broadcast_address):raise GatewayError('invalid_lan_host')
            choices.append({'address':str(address),'network':str(network)})
    if len(choices)!=1:raise GatewayError('exactly_one_active_private_lan_required')
    return choices[0]


def root_removed():
    rows=json.loads(run(['findmnt','--json','--list','--output','TARGET'])).get('filesystems',[])
    if not rows:raise GatewayError('mount_inventory_unavailable')
    for row in rows:
        target=row.get('target')
        if not isinstance(target,str) or not target.startswith('/'):raise GatewayError('invalid_mount_inventory')
        if (Path(target)/'agent-platform-ca-root').exists():raise GatewayError('remove_root_ca_media_first')


def write(path,data):
    pki().backup().local_module().write_file(path,data,os.getuid(),0o600)


def render(release,network,uid=None,gid=None):
    source();private_address(network['address'])
    if str(ipaddress.IPv4Network(network['network']))!=network['network'] or ipaddress.IPv4Address(network['address']) not in ipaddress.IPv4Network(network['network']):
        raise GatewayError('invalid_lan_network')
    values={'GATEWAY_IMAGE':IMAGE,'GATEWAY_USER':f'{os.getuid() if uid is None else uid}:{os.getgid() if gid is None else gid}',
            'LAN_ADDRESS':network['address'],'RELEASE_DIR':str(release),
            'GATEWAY_ENTRYPOINT':str(ROOT/'infra/gateway/entrypoint.sh'),
            'GATEWAY_UID':str(os.getuid() if uid is None else uid),'GATEWAY_GID':str(os.getgid() if gid is None else gid)}
    compose=(ROOT/'infra/gateway/compose.yaml').read_text()
    compose=re.sub(r'\$\{([A-Z_]+)\}',lambda match:values[match[1]],compose)
    caddy=(ROOT/'infra/gateway/Caddyfile').read_text().replace('__ADDRESS__',network['address']).replace('__NETWORK__',network['network'])
    return compose,caddy


def check_public_ca(native,issuer):
    for role,file in [('root','root.crt'),('intermediate','intermediate.crt')]:
        observed=json.loads(native.run(['certificate','inspect','--format','json',issuer/file]))
        fingerprint=observed.get('fingerprint_sha256','').replace(':','').lower()
        if not hmac.compare_digest(fingerprint,PROFILE[role+'_fingerprint_sha256']):raise GatewayError('unexpected_ca_fingerprint')
    native.run(['certificate','verify','--roots',issuer/'root.crt',issuer/'intermediate.crt'])


def leaf(native,issuer,release,network,password):
    # Public template is rendered as JSON only because Step's native API requires it.
    template={'subject':{'commonName':'login.home.arpa'},
              'sans':[{'type':'dns','value':name} for name in PROFILE['hostnames']]+[{'type':'ip','value':network['address']}],
              'keyUsage':['digitalSignature'],'extKeyUsage':['serverAuth'],'basicConstraints':{'isCA':False}}
    template_path=Path(native.temp.name)/'server-template.json';template_path.write_text(json.dumps(template))
    native.run(['certificate','create','login.home.arpa',release/'server.crt',release/'server.key',
                '--template',template_path,'--kty','EC','--curve','P-256','--not-after','720h',
                '--ca',issuer/'intermediate.crt','--ca-key',issuer/'intermediate.key','--ca-password-file',password,
                '--no-password','--insecure'])
    (release/'server.key').chmod(0o600)
    native.execute(native.openssl,['verify','-CAfile',issuer/'root.crt','-untrusted',issuer/'intermediate.crt',
                                  '-purpose','sslserver','-verify_hostname','login.home.arpa',release/'server.crt'])
    native.execute(native.openssl,['verify','-CAfile',issuer/'root.crt','-untrusted',issuer/'intermediate.crt',
                                  '-purpose','sslserver','-verify_ip',network['address'],release/'server.crt'])
    write(release/'fullchain.crt',(release/'server.crt').read_bytes()+(issuer/'intermediate.crt').read_bytes())
    (release/'trust').mkdir(mode=0o700)
    write(release/'trust/root.crt',(issuer/'root.crt').read_bytes())


def native_validate(caddy,release,config=None):
    if config is None:config=(release/'Caddyfile').read_text()
    for source_path,target in [('/run/gateway/fullchain.crt',release/'fullchain.crt'),('/run/gateway/server.key',release/'server.key'),('/run/trust',release/'trust')]:
        config=config.replace(source_path,str(target))
    with tempfile.TemporaryDirectory(prefix='gateway-native-validation-') as folder:
        path=Path(folder)/'Caddyfile';path.write_text(config)
        run([caddy,'validate','--config',path,'--adapter','caddyfile'])


def issue():
    if os.geteuid()==0:raise GatewayError('run_gateway_issue_as_desktop_user')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
    source();caddy=tools();root_removed();network=lan();p=pki();helper=p.backup()
    issuer=Path.home()/p.EXPECTED['issuer_directory_name']
    p.private_parent(issuer);p.private_parent(BASE)
    key=issuer/'intermediate.key';info=key.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
        raise GatewayError('unsafe_intermediate_key_file')
    with p.Native(p.tool()) as native:
        check_public_ca(native,issuer)
        print('[gateway] Unlock the existing INTERMEDIATE key; the root USB stays removed.',file=sys.stderr,flush=True)
        phrase=helper.terminal_phrase()
        with helper.memory_file() as password:
            os.fchmod(password.fileno(),0o600);password.write(phrase+b'\n');password.seek(0);del phrase
            descriptor=Path('/proc')/str(os.getpid())/'fd'/str(password.fileno())
            # Check the password before allocating a release or writing a leaf key.
            native.run(['crypto','key','public',key,'--password-file',descriptor])
            root_removed();release=BASE/('release-'+uuid.uuid4().hex);release.mkdir(mode=0o700)
            print('[gateway] Issuing a 30-day server certificate; existing CA material is preserved.',file=sys.stderr,flush=True)
            leaf(native,issuer,release,network,descriptor)
    compose,caddy_config=render(release,network)
    write(release/'compose.yaml',compose.encode());write(release/'Caddyfile',caddy_config.encode())
    print('[gateway] Validating the certificate and Caddy configuration before selecting the release.',file=sys.stderr,flush=True)
    native_validate(caddy,release)
    manifest={'schema_version':1,'release':release.name,**network,'uid':os.getuid(),'gid':os.getgid(),
              'source_sha256':source_hashes(),'root_fingerprint_sha256':PROFILE['root_fingerprint_sha256']}
    candidate=BASE/('deployment-'+uuid.uuid4().hex+'.json');write(candidate,json.dumps(manifest).encode())
    os.replace(candidate,BASE/'deployment.json')
    return {'status':'issued','url':f"https://{network['address']}:8443",'trust_download':f"http://{network['address']}:8080/root.crt",
            'root_fingerprint_sha256':PROFILE['root_fingerprint_sha256'],'validity_hours':720,
            'services_started':False,'renewal':'supervised_task','scope':'Leaf issued; device trust and actual LAN login remain pending'}


def source_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ['config/gateway/pilot.yaml','infra/gateway/versions.yaml','infra/gateway/compose.yaml','infra/gateway/Caddyfile','infra/gateway/entrypoint.sh','scripts/gateway/gateway.py']}


# Exact reviewed revisions only; template/script pairs are validated with every other source hash.
LEGACY_CONFIG_REVISIONS={
    'pre_sni':('5059e92a7228f11cadc9a60f1c2432688cf76c07631852553238a86f81a7b868',
               '4e8def17c78730cbaeb141cdeef584c3b6257e99901771863cbc20004b44a0ba'),
    'pre_csrf':('e893f7f5be007d5a7978c64761a99c53fc82d725dbe855efe92c63689ef00bd7',
                '12dea8cccfcbf8d07e5ae262a05880ce4d540dac0fa25190b830649351805b02'),
}


def legacy_source_revision(observed,current):
    for revision,(caddy_hash,script_hash) in LEGACY_CONFIG_REVISIONS.items():
        expected={**current,'infra/gateway/Caddyfile':caddy_hash,'scripts/gateway/gateway.py':script_hash}
        if observed==expected:return revision,expected
    raise GatewayError('reissue_gateway_for_source_or_identity_change')


def legacy_caddy_text(current,revision):
    if revision not in LEGACY_CONFIG_REVISIONS:raise GatewayError('unreviewed_gateway_revision')
    text=current.replace('    # Capture native form proof before stripping untrusted identity assertions.\n'
                         '    vars authentik_csrf {http.request.header.X-Authentik-CSRF}\n'
                         '    request_header -X-Authentik-*\n','',1)
    text=text.replace('        header_up X-Authentik-CSRF {vars.authentik_csrf}\n',
                      '        header_up -X-Authentik-*\n',1)
    if revision=='pre_sni':text=text.replace('    default_sni login.home.arpa\n','',1)
    return text


def state(*,legacy=False):
    source();p=pki();p.private_parent(BASE)
    manifest=json.loads(p.backup().safe_read(BASE/'deployment.json',32768,private=True))
    if not re.fullmatch(r'release-[a-f0-9]{32}',manifest.get('release','')):raise GatewayError('invalid_gateway_release')
    expected_hashes=source_hashes();revision=None
    if legacy:revision,expected_hashes=legacy_source_revision(manifest.get('source_sha256'),expected_hashes)
    if manifest.get('source_sha256')!=expected_hashes or manifest.get('uid')!=os.getuid() or manifest.get('gid')!=os.getgid():raise GatewayError('reissue_gateway_for_source_or_identity_change')
    network=lan()
    if any(manifest.get(field)!=value for field,value in network.items()):raise GatewayError('lan_changed_reissue_leaf')
    release=BASE/manifest['release'];p.private_parent(release)
    compose,caddy=render(release,network)
    if legacy:caddy=legacy_caddy_text(caddy,revision)
    for file,expected in [('compose.yaml',compose),('Caddyfile',caddy)]:
        if p.backup().safe_read(release/file,32768,private=True).decode()!=expected:raise GatewayError('gateway_deployment_drift')
    for file in ['server.key','server.crt','fullchain.crt','trust/root.crt']:
        meta=(release/file).lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.getuid() or stat.S_IMODE(meta.st_mode)!=0o600 or meta.st_nlink!=1:raise GatewayError('unsafe_gateway_tls_file')
    if (release/'trust').is_symlink():raise GatewayError('linked_trust_directory')
    fingerprint=run(['openssl','x509','-in',release/'trust/root.crt','-noout','-fingerprint','-sha256']).decode().strip().split('=',1)[1].replace(':','').lower()
    if fingerprint!=PROFILE['root_fingerprint_sha256']:raise GatewayError('gateway_root_fingerprint_mismatch')
    run(['openssl','x509','-in',release/'server.crt','-checkend','172800','-noout'])
    return release,network


def atomic_public_config(path,content,previous):
    """Replace an owner-only configuration file, never a key/certificate."""
    if path.name not in {'Caddyfile','deployment.json'}:raise GatewayError('gateway_config_target_refused')
    old=pki().backup().safe_read(path,32768,private=True)
    if old!=previous:raise GatewayError('gateway_config_changed_during_refresh')
    fd,name=tempfile.mkstemp(prefix='.gateway-config-',dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o600);stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def refresh_config():
    """Accept only exact reviewed pre-SNI/pre-CSRF revisions; retain all TLS material."""
    try:
        state()
        return {'status':'unchanged','tls_material':'preserved','scope':'Current configuration already selected; no signing or service restart'}
    except GatewayError as error:
        if str(error)!='reissue_gateway_for_source_or_identity_change':raise
    release,network=state(legacy=True)
    manifest_path=BASE/'deployment.json';config_path=release/'Caddyfile'
    helper=pki().backup()
    old_manifest=helper.safe_read(manifest_path,32768,private=True)
    old_config=helper.safe_read(config_path,32768,private=True)
    _,config=render(release,network)
    # Validate the proposed text using existing TLS files before replacing anything.
    native_validate(tools(),release,config)
    manifest=json.loads(old_manifest);manifest['source_sha256']=source_hashes()
    new_manifest=json.dumps(manifest,indent=2).encode();new_config=config.encode()
    atomic_public_config(config_path,new_config,old_config)
    try:
        atomic_public_config(manifest_path,new_manifest,old_manifest)
    except Exception:
        atomic_public_config(config_path,old_config,new_config)
        raise
    return {'status':'refreshed','tls_material':'preserved','signing_key_used':False,
            'scope':'Existing leaf/key/CA preserved; run gateway:up to recreate only Caddy'}


def docker(*args,timeout=120):return run(['sudo','-n','docker','--context','default',*args],timeout)


def cache_image():
    print('[gateway] Downloading/verifying the pinned Caddy image.',file=sys.stderr,flush=True)
    try:docker('pull',IMAGE,timeout=300)
    except GatewayError as error:raise GatewayError('gateway_image_pull_failed',error.diagnostic) from None
    print('[gateway] Testing Caddy execution as non-root with all capabilities dropped.',file=sys.stderr,flush=True)
    try:
        version=docker('run','--rm','--network','none','--read-only','--user',f'{os.getuid()}:{os.getgid()}',
                       '--cap-drop','ALL','--security-opt','no-new-privileges:true','--security-opt','apparmor:docker-default',
                       '--memory','256m','--cpus','1','--pids-limit','64',
                       '--mount','type=bind,src='+str(ROOT/'infra/gateway/entrypoint.sh')+',dst=/opt/gateway-entrypoint.sh,readonly',
                       '--tmpfs',f'/run/caddy-bin:rw,exec,nosuid,nodev,size=96m,mode=0700,uid={os.getuid()},gid={os.getgid()}',
                       '--entrypoint','/bin/sh',IMAGE,'/opt/gateway-entrypoint.sh','version')
    except GatewayError as error:raise GatewayError('gateway_hardened_image_probe_failed',error.diagnostic) from None
    if not version.startswith(b'v2.11.7 '):raise GatewayError('gateway_native_image_version_mismatch')
    return {'status':'cached','image':IMAGE,'hardened_image_execution':'passed'}


def check():
    release,network=state()
    observed=json.loads(docker('inspect','--format','{{json .}}','agent-platform-gateway-gateway-1'))
    config=pki().backup().local_module().native().source_module().parse((release/'compose.yaml').read_bytes())['services']['gateway']
    host=observed['HostConfig'];declared=observed['Config']
    if (not observed['State']['Running'] or declared['Image']!=IMAGE or declared['User']!=config['user']
        or host['ReadonlyRootfs'] is not True or host['Privileged'] is not False or host.get('CapAdd')
        or set(host.get('CapDrop') or [])!={'ALL'} or host['Memory']!=256*1024**2
        or host['PidsLimit']!=64 or host['NanoCpus']!=1000000000
        or set(host['SecurityOpt'])!={'no-new-privileges:true','apparmor:docker-default'}
        or observed.get('AppArmorProfile')!='docker-default'
        or host.get('NetworkMode')=='host' or host.get('PidMode') or host.get('IpcMode')=='host'
        or declared.get('Entrypoint')!=['/bin/sh','/opt/gateway-entrypoint.sh']
        or host.get('LogConfig')!={'Type':'json-file','Config':{'max-size':'2m','max-file':'2'}}):
        raise GatewayError('gateway_runtime_process_drift')
    expected_tmpfs={item.split(':',1)[0]:item.split(':',1)[1] for item in config['tmpfs']}
    if host.get('Tmpfs')!=expected_tmpfs:raise GatewayError('gateway_temporary_filesystem_drift')
    expected_ports={str(port)+'/tcp':[{'HostIp':network['address'],'HostPort':str(port)}] for port in (8443,8080,8444,8445)}
    if host['PortBindings']!=expected_ports:raise GatewayError('gateway_port_exposure_drift')
    mounts={(item['Destination'],item['Source'],item['RW']) for item in observed['Mounts'] if item['Type']=='bind'}
    expected={(item['target'],item['source'],False) for item in config['volumes']}
    if mounts!=expected or any(item['Type']=='volume' for item in observed['Mounts']):raise GatewayError('gateway_mount_drift')
    if set(observed['NetworkSettings']['Networks'])!={'agent-platform-identity-local_frontend','agent-platform-household-alejandro_frontend','agent-platform-household-kimberly_frontend'}:raise GatewayError('gateway_network_drift')
    context=ssl.create_default_context(cafile=str(release/'trust/root.crt'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    with opener.open(f"https://{network['address']}:8443/-/health/ready/",timeout=15) as response:
        if response.status!=200:raise GatewayError('gateway_identity_not_ready')
    with opener.open(f"http://{network['address']}:8080/root.crt",timeout=10) as response:
        if response.read(65537)!=(release/'trust/root.crt').read_bytes():raise GatewayError('public_trust_download_mismatch')
    return {'status':'passed','url':f"https://{network['address']}:8443",'tls_chain_and_ip':'passed','authentik_readiness':'passed',
            'device_trust':'pending','browser_mfa_login':'pending','openhands_access':'per_user_authentication_configured_browser_acceptance_pending','renewal':'supervised_task'}


def down():
    # Stop by fixed verified identity; stale DHCP/TLS/source must not block cleanup.
    info=json.loads(docker('inspect','--format','{{json .}}','agent-platform-gateway-gateway-1'))
    labels=info['Config'].get('Labels',{})
    if labels.get('com.docker.compose.project')!='agent-platform-gateway' or labels.get('com.docker.compose.service')!='gateway':
        raise GatewayError('gateway_cleanup_identity_mismatch')
    docker('rm','--force','agent-platform-gateway-gateway-1')
    return {'status':'stopped','tls_material':'preserved'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['source','environment','plan','cache','issue','up','check','down','refresh']);args=parser.parse_args()
    try:
        source()
        if args.mode in ('source','environment'):
            if args.mode=='environment':tools()
            result={'status':'passed','scope':'Gateway source/tools only; no TLS key generation, exposure or trust changes'}
        elif args.mode=='plan':
            network=lan();result={'status':'planned',**network,'url':f"https://{network['address']}:8443",'image':IMAGE,
                'scope':'Login HTTPS only; root must remain disconnected; deployment is owner-run'}
        elif args.mode=='cache':
            result=cache_image()
        elif args.mode=='issue':result=issue()
        elif args.mode=='refresh':result=refresh_config()
        elif args.mode=='up':
            root_removed();release,network=state();native_validate(tools(),release)
            # Reuse only the known Authentik frontend, not an arbitrary network.
            info=json.loads(docker('inspect','--format','{{json .}}','agent-platform-identity-local-server-1'))
            if (not info['State']['Running'] or info['Config']['Labels'].get('com.docker.compose.project')!='agent-platform-identity-local'
                    or info['Config']['Labels'].get('com.docker.compose.service')!='server'):raise GatewayError('start_identity_before_gateway')
            for username in ('alejandro','kimberly'):
                instance=json.loads(docker('inspect','--format','{{json .}}','agent-platform-household-'+username+'-openhands-1'))
                labels=instance['Config'].get('Labels',{})
                if not instance['State']['Running'] or labels.get('com.docker.compose.project')!='agent-platform-household-'+username or labels.get('com.docker.compose.service')!='openhands':raise GatewayError('run_household_setup_before_gateway')
            docker('image','inspect',IMAGE)
            docker('compose','--project-name','agent-platform-gateway','--file',release/'compose.yaml','up','-d','--force-recreate','--pull','never')
            for attempt in range(20):
                try:result=check();break
                except (GatewayError,urllib.error.URLError,TimeoutError,ConnectionError):
                    if attempt==19:raise
                    time.sleep(1)
        elif args.mode=='check':result=check()
        else:
            result=down()
    except Exception as error:
        if isinstance(error,urllib.error.URLError) and isinstance(error.reason,ssl.SSLError):error=GatewayError('gateway_tls_handshake_failed')
        elif isinstance(error,ssl.SSLError):error=GatewayError('gateway_tls_handshake_failed')
        elif isinstance(error,urllib.error.HTTPError):error=GatewayError('gateway_readiness_http_failed',{'http_status':error.code})
        diagnostic=error.diagnostic if isinstance(error,GatewayError) else None
        result={'status':'failed','error':str(error) if isinstance(error,GatewayError) else 'gateway_operation_failed_details_withheld',
                'existing_material':'preserved','scope':'Do not delete or regenerate the root/intermediate CA'}
        if diagnostic:result['diagnostic']=diagnostic
    result['household_readiness']='pending';print(json.dumps(result,indent=2));return int(result['status']=='failed')


if __name__=='__main__':raise SystemExit(main())
