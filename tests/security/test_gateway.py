"""Gateway source, failures and native temporary CA/TLS/proxy integration."""
import copy
import http.client
import http.server
import importlib.util
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('gateway_tests',ROOT/'scripts/gateway/gateway.py')
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)


def row(address='192.168.42.20',prefix=24,name='wlan0'):
    return {'ifname':name,'flags':['UP','LOWER_UP'],'addr_info':[{'family':'inet','scope':'global','local':address,'prefixlen':prefix}]}


class LANTests(unittest.TestCase):
    def test_single_private_active_lan(self):
        self.assertEqual(G.lan([row(),row('172.19.0.1',16,'br-test')]),{'address':'192.168.42.20','network':'192.168.42.0/24'})

    def test_ambiguous_absent_public_and_invalid_prefix_fail(self):
        for records in ([],[row(),row('10.1.2.3')],[row('8.8.8.8')],[row(prefix=True)],
                        [row('192.168.42.0')],[row(prefix=8)],[row(name='wg0')]):
            with self.subTest(records=records),self.assertRaises((G.GatewayError,ValueError)):G.lan(records)

    def test_root_media_must_stay_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(G,'run',return_value=json.dumps({'filesystems':[{'target':folder}]}).encode()):
                G.root_removed();(Path(folder)/'agent-platform-ca-root').mkdir()
                with self.assertRaisesRegex(G.GatewayError,'remove_root'):G.root_removed()
        with mock.patch.object(G,'run',return_value=b'{"filesystems":[]}'):
            with self.assertRaises(G.GatewayError):G.root_removed()


class SourceTests(unittest.TestCase):
    def test_reviewed_source_and_tls_only_mounts(self):
        helper=G.source()
        with tempfile.TemporaryDirectory() as folder:
            compose,caddy=G.render(Path(folder),{'address':'192.168.42.20','network':'192.168.42.0/24'},uid=1000,gid=1000)
        service=helper.parse(compose)['services']['gateway']
        self.assertEqual(service['ports'],['192.168.42.20:8443:8443','192.168.42.20:8080:8080','192.168.42.20:8444:8444','192.168.42.20:8445:8445'])
        self.assertTrue(service['read_only']);self.assertEqual(service['user'],'1000:1000')
        self.assertEqual(service['cap_drop'],['ALL']);self.assertEqual(len(service['tmpfs']),4)
        self.assertEqual({v['target'] for v in service['volumes']},{'/opt/gateway-entrypoint.sh','/etc/caddy/Caddyfile','/run/gateway/fullchain.crt','/run/gateway/server.key','/run/trust'})
        for item in service['volumes']:self.assertTrue(item['read_only']);self.assertFalse(item['bind']['create_host_path'])
        for forbidden in ('intermediate.key','root.key','docker.sock','tls internal'):
            self.assertNotIn(forbidden,compose+caddy)
        self.assertIn('auto_https off',caddy);self.assertIn('admin off',caddy)
        self.assertIn('respond "Application access is not enabled yet." 503',caddy)

    def test_changed_profile_version_and_templates_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            for name in ['config/gateway/pilot.yaml','infra/gateway/versions.yaml',*G.SOURCE_HASHES]:
                dest=base/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
            real_pki=G.pki()
            with mock.patch.object(G,'ROOT',base),mock.patch.object(G,'pki',return_value=real_pki):
                G.source()
                for name in ['config/gateway/pilot.yaml','infra/gateway/versions.yaml',*G.SOURCE_HASHES]:
                    path=base/name;original=path.read_bytes()
                    if name.endswith('pilot.yaml'):changed=original.replace(b'openhands_routes: true',b'openhands_routes: false')
                    elif name.endswith('versions.yaml'):changed=original.replace(b'2.11.7',b'2.11.8')
                    else:changed=original+b'\n# unreviewed\n'
                    path.write_bytes(changed)
                    with self.assertRaises(G.GatewayError):G.source()
                    path.write_bytes(original)

    def test_invalid_lan_cannot_be_rendered(self):
        for value in ['0.0.0.0','127.0.0.1','8.8.8.8','::1','192.168.42.20\nmalicious']:
            with self.subTest(value=value),self.assertRaises(ValueError):
                G.render(Path('/tmp/synthetic'),{'address':value,'network':'192.168.42.0/24'})


class OperationalTests(unittest.TestCase):
    def test_environment_checks_hardened_image_execution_and_version(self):
        with mock.patch.object(G,'docker',side_effect=[b'cached',b'v2.11.7 synthetic']) as docker:
            self.assertEqual(G.cache_image()['hardened_image_execution'],'passed')
            run=docker.call_args.args
            self.assertIn('none',run);self.assertIn('no-new-privileges:true',run)
            self.assertIn(G.IMAGE,run);self.assertIn('--read-only',run)
        with mock.patch.object(G,'docker',side_effect=[b'cached',b'v9.0.0 synthetic']):
            with self.assertRaisesRegex(G.GatewayError,'version_mismatch'):G.cache_image()

    def test_cache_failure_identifies_pull_vs_hardened_execution(self):
        diagnostic={'category':'permission_or_file_capability_denied','exit_code':126}
        for failure,expected in [([G.GatewayError('command',diagnostic)],'gateway_image_pull_failed'),
                                 ([b'cached',G.GatewayError('command',diagnostic)],'gateway_hardened_image_probe_failed')]:
            with mock.patch.object(G,'docker',side_effect=failure):
                with self.assertRaises(G.GatewayError) as error:G.cache_image()
                self.assertEqual(str(error.exception),expected);self.assertEqual(error.exception.diagnostic,diagnostic)

    def test_command_diagnostics_never_include_native_secret_values(self):
        cases=[(b'sudo: interactive authentication is required','sudo_authentication_required'),
               (b'exec caddy: operation not permitted','permission_or_file_capability_denied'),
               (b'Cannot connect to the Docker daemon','docker_daemon_unavailable'),
               (b'unauthorized: authentication required','registry_authentication_failed'),
               (b'network is unreachable','network_resolution_or_timeout')]
        for text,expected in cases:
            result=__import__('subprocess').CompletedProcess(['synthetic'],126,b'PRIVATE_TOKEN_NEVER_PRINT',text)
            diagnostic=G.command_diagnostic(result)
            self.assertEqual(diagnostic,{'category':expected,'exit_code':126})
            self.assertNotIn('PRIVATE_TOKEN',repr(diagnostic))

    def test_cleanup_works_without_state_lan_or_tls_read(self):
        labels={'com.docker.compose.project':'agent-platform-gateway','com.docker.compose.service':'gateway'}
        def docker(*args,**kwargs):
            if args[0]=='inspect':return json.dumps({'Config':{'Labels':labels}}).encode()
            self.assertEqual(args,('rm','--force','agent-platform-gateway-gateway-1'));return b''
        with mock.patch.object(G,'state',side_effect=AssertionError('must not need state')),mock.patch.object(G,'docker',side_effect=docker) as engine:
            self.assertEqual(G.down()['tls_material'],'preserved')
            self.assertEqual(engine.call_count,2)
            labels['com.docker.compose.project']='foreign'
            with self.assertRaisesRegex(G.GatewayError,'identity_mismatch'):G.down()
            self.assertEqual(engine.call_count,3)

    def test_runtime_rejects_exposure_mounts_and_process_drift(self):
        helper=G.source();network={'address':'192.168.42.20','network':'192.168.42.0/24'}
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        release=Path(temp.name);compose,_=G.render(release,network,uid=1000,gid=1000)
        (release/'compose.yaml').write_text(compose)
        service=helper.parse(compose)['services']['gateway']
        base={'State':{'Running':True},'Config':{'Image':G.IMAGE,'User':'1000:1000','Entrypoint':['/bin/sh','/opt/gateway-entrypoint.sh']},
              'AppArmorProfile':'docker-default','HostConfig':{'ReadonlyRootfs':True,'Privileged':False,
              'CapAdd':None,'CapDrop':['ALL'],'Memory':256*1024**2,'PidsLimit':64,'NanoCpus':1000000000,
              'SecurityOpt':['no-new-privileges:true','apparmor:docker-default'],'NetworkMode':'agent-platform-identity-local_frontend',
              'PidMode':'','IpcMode':'private','Tmpfs':{item.split(':',1)[0]:item.split(':',1)[1] for item in service['tmpfs']},'LogConfig':{'Type':'json-file','Config':{'max-size':'2m','max-file':'2'}},
              'PortBindings':{str(port)+'/tcp':[{'HostIp':network['address'],'HostPort':str(port)}] for port in [8443,8080,8444,8445]}},
              'Mounts':[{'Type':'bind','Destination':item['target'],'Source':item['source'],'RW':False} for item in service['volumes']],
              'NetworkSettings':{'Networks':{'agent-platform-identity-local_frontend':{},'agent-platform-household-alejandro_frontend':{},'agent-platform-household-kimberly_frontend':{}}}}
        for mutate in [lambda value:value['Config'].update(Image='caddy:latest'),
                       lambda value:value['Config'].update(User='0:0'),
                       lambda value:value['HostConfig'].update(ReadonlyRootfs=False),
                       lambda value:value['HostConfig']['PortBindings']['8443/tcp'][0].update(HostIp='0.0.0.0'),
                       lambda value:value['Mounts'][0].update(RW=True),
                       lambda value:value['Mounts'].append({'Type':'volume','Destination':'/data'}),
                       lambda value:value['HostConfig'].update(LogConfig={'Type':'json-file','Config':{}}),
                       lambda value:value['NetworkSettings']['Networks'].update({'foreign':{}})]:
            changed=copy.deepcopy(base);mutate(changed)
            with self.subTest(mutate=mutate),mock.patch.object(G,'state',return_value=(release,network)),mock.patch.object(G,'docker',return_value=json.dumps(changed).encode()),self.assertRaises(G.GatewayError):G.check()


class BootstrapTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('caddy'),'mise Caddy required')
    def test_identical_binary_runs_without_source_xattrs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'source';binary=base/'runtime-caddy';script=base/'entrypoint.sh'
            source.write_bytes(Path(shutil.which('caddy')).read_bytes());source.chmod(0o755)
            os.setxattr(source,'user.synthetic-capability',b'test-only')
            content=(ROOT/'infra/gateway/entrypoint.sh').read_text().replace('source=/usr/bin/caddy','source='+str(source)).replace('binary=/run/caddy-bin/caddy','binary='+str(binary))
            script.write_text(content)
            result=subprocess.run(['/bin/sh',str(script),'version'],capture_output=True)
            self.assertEqual(result.returncode,0);self.assertTrue(result.stdout.startswith(b'v2.11.7 '))
            self.assertEqual(binary.read_bytes(),source.read_bytes())
            self.assertNotIn('user.synthetic-capability',os.listxattr(binary))
            self.assertEqual(os.getxattr(source,'user.synthetic-capability'),b'test-only')
            self.assertEqual(binary.stat().st_mode&0o777,0o500)
            again=subprocess.run(['/bin/sh',str(script),'version'],capture_output=True)
            self.assertNotEqual(again.returncode,0);self.assertEqual(binary.read_bytes(),source.read_bytes())

    def test_changed_bytes_are_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'source';binary=base/'runtime';script=base/'entrypoint.sh'
            source.write_text('trusted reference bytes')
            commands=base/'bin';commands.mkdir();cat=commands/'cat'
            cat.write_text("#!/bin/sh\nprintf '#!/bin/sh\\nprintf BOOTSTRAP_EXECUTED\\n'\n");cat.chmod(0o755)
            script.write_text((ROOT/'infra/gateway/entrypoint.sh').read_text().replace('source=/usr/bin/caddy','source='+str(source)).replace('binary=/run/caddy-bin/caddy','binary='+str(binary)))
            result=subprocess.run(['/bin/sh',str(script)],capture_output=True,env={**os.environ,'PATH':str(commands)+':/usr/bin:/bin'})
            self.assertNotEqual(result.returncode,0);self.assertNotIn(b'BOOTSTRAP_EXECUTED',result.stdout)



class NativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('caddy') and shutil.which('step'),'mise gateway tools required')
    def test_real_leaf_tls_proxy_headers_and_closed_routes(self):
        p=G.pki();helper=p.backup()
        with tempfile.TemporaryDirectory(prefix='gateway-synthetic-') as folder:
            base=Path(folder);root=base/'root';issuer=base/'issuer';release=base/'release'
            for path in (root,issuer,release):path.mkdir(mode=0o700)
            with helper.memory_file() as rp,helper.memory_file() as ip,p.Native(p.tool()) as native:
                for handle in (rp,ip):handle.write(secrets.token_hex(32).encode()+b'\n');handle.seek(0)
                descriptor=lambda handle:Path('/proc')/str(os.getpid())/'fd'/str(handle.fileno())
                p.generate(native,helper,root,issuer,descriptor(rp),descriptor(ip))
                with self.assertRaisesRegex(G.GatewayError,'fingerprint'):G.check_public_ca(native,issuer)
                G.leaf(native,issuer,release,{'address':'127.0.0.1'},descriptor(ip))
                info=json.loads(native.run(['certificate','inspect','--format','json',release/'server.crt']))
                self.assertLessEqual(info['validity']['length'],720*3600)
                self.assertFalse(info['extensions']['basic_constraints']['is_ca'])
                self.assertEqual(os.stat(release/'server.key').st_mode&0o777,0o600)
                # A server-only leaf must fail client-auth purpose verification.
                with self.assertRaises(Exception):native.execute(native.openssl,['verify','-CAfile',root/'root.crt','-untrusted',issuer/'intermediate.crt','-purpose','sslclient',release/'server.crt'])
            class Backend(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path.startswith('/outpost.goauthentik.io/auth/caddy'):
                        username=self.headers.get('Cookie','').removeprefix('session=')
                        if username not in ('alejandro','kimberly'):self.send_response(401);self.end_headers();return
                        if self.headers.get('X-Forwarded-Host') not in ('127.0.0.1:'+str(ports[2]),'127.0.0.1:'+str(ports[3])):self.send_response(400);self.end_headers();return
                        self.send_response(204);self.send_header('X-Authentik-Username',username);self.end_headers();return
                    data=json.dumps({'forwarded_proto':self.headers.get('X-Forwarded-Proto'),
                                     'identity':self.headers.get('X-Authentik-Username'),
                                     'remote_user':self.headers.get('Remote-User'),
                                     'forwarded_for':self.headers.get('X-Forwarded-For'),'forwarded_host':self.headers.get('X-Forwarded-Host')}).encode()
                    self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                def do_POST(self):
                    # Synthetic protected upstream: exercises actual header forwarding, no real credentials.
                    self.rfile.read(int(self.headers.get('Content-Length','0')))
                    if self.headers.get('X-Authentik-CSRF')!='synthetic-csrf-only':
                        self.send_response(403);self.end_headers();return
                    self.do_GET()
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Backend)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            process=None
            try:
                # Only the isolated test rewrites deployment addresses/ports/upstream.
                sockets=[];ports=[]
                for _ in range(4):
                    sock=socket.socket();sock.bind(('127.0.0.1',0));sockets.append(sock);ports.append(sock.getsockname()[1])
                for sock in sockets:sock.close()
                _,config=G.render(release,{'address':'192.168.42.20','network':'192.168.42.0/24'})
                config=config.replace('192.168.42.20','127.0.0.1').replace('192.168.42.0/24','127.0.0.1/32')
                config=config.replace(':8443',':'+str(ports[0])).replace(':8080',':'+str(ports[1])).replace(':8444',':'+str(ports[2])).replace(':8445',':'+str(ports[3]))
                config=config.replace('admin off','admin off\n    default_bind 127.0.0.1')
                config=config.replace('agent-platform-identity-local-server-1:9000','127.0.0.1:'+str(server.server_port))
                config=re.sub(r'agent-platform-household-(?:alejandro|kimberly)-ingress-1:[0-9]+','127.0.0.1:'+str(server.server_port),config)
                config=config.replace('/run/gateway/fullchain.crt',str(release/'fullchain.crt')).replace('/run/gateway/server.key',str(release/'server.key')).replace('/run/trust',str(release/'trust'))
                (release/'Caddyfile').write_text(config)
                G.native_validate(Path(shutil.which('caddy')),release)
                with open(base/'caddy-log','wb') as log:
                    process=subprocess.Popen([shutil.which('caddy'),'run','--config',str(release/'Caddyfile'),'--adapter','caddyfile'],stdout=log,stderr=log)
                    context=ssl.create_default_context(cafile=str(root/'root.crt'))
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
                    url='https://127.0.0.1:'+str(ports[0])
                    for attempt in range(50):
                        try:
                            with opener.open(url,timeout=1) as response:response.read();break
                        except urllib.error.URLError:
                            if attempt==49:raise
                            time.sleep(.1)
                    request=urllib.request.Request(url,headers={'X-Forwarded-For':'8.8.8.8','X-Forwarded-Proto':'http','X-Authentik-Username':'forged','Remote-User':'forged'})
                    with opener.open(request,timeout=3) as response:body=json.load(response)
                    self.assertEqual(body,{'forwarded_proto':'https','identity':None,'remote_user':None,'forwarded_for':'127.0.0.1','forwarded_host':'127.0.0.1:'+str(ports[0])})
                    # Browser CSRF proof must survive while spoofed identity headers remain stripped.
                    protected=url+'/synthetic-protected'
                    csrf_request=urllib.request.Request(protected,data=b'{}',headers={
                        'X-authentik-CSRF':'synthetic-csrf-only','X-Authentik-Username':'forged',
                        'Remote-User':'forged','Content-Type':'application/json'})
                    with opener.open(csrf_request,timeout=3) as response:csrf_body=json.load(response)
                    self.assertIsNone(csrf_body['identity']);self.assertIsNone(csrf_body['remote_user'])
                    for headers in ({},{'X-authentik-CSRF':'invalid-synthetic-value'}):
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            opener.open(urllib.request.Request(protected,data=b'{}',headers=headers),timeout=3)
                        self.assertEqual(error.exception.code,403);error.exception.close()
                    for port,own,foreign in [(ports[2],'alejandro','kimberly'),(ports[3],'kimberly','alejandro')]:
                        app='https://127.0.0.1:'+str(port)+'/canvas'
                        with opener.open(urllib.request.Request(app,headers={'Cookie':'session='+own}),timeout=3) as response:self.assertEqual(response.status,200)
                        for headers,expected in [({},401),({'X-Authentik-Username':own},401),({'Cookie':'session='+foreign,'X-Authentik-Username':own},403)]:
                            with self.assertRaises(urllib.error.HTTPError) as error:opener.open(urllib.request.Request(app,headers=headers),timeout=3)
                            self.assertEqual(error.exception.code,expected);error.exception.close()
                    public='http://127.0.0.1:'+str(ports[1])
                    with opener.open(public+'/root.crt',timeout=3) as response:self.assertEqual(response.read(),(root/'root.crt').read_bytes())
                    for path in ['/','/root.key','/intermediate.key','/server.key','/../server.key']:
                        with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:opener.open(public+path,timeout=3)
                        self.assertEqual(error.exception.code,404);error.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(urllib.request.Request(url,headers={'Host':'portal.home.arpa:'+str(ports[0])}),timeout=3)
                    self.assertEqual(error.exception.code,503);error.exception.close()
                    connection=http.client.HTTPSConnection('127.0.0.1',ports[0],context=context,source_address=('127.0.0.2',0),timeout=3)
                    try:connection.request('GET','/');self.assertEqual(connection.getresponse().status,403)
                    finally:connection.close()
                    untrusted=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
                    with self.assertRaises(urllib.error.URLError):untrusted.open(url,timeout=3)
            finally:
                if process is not None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                server.shutdown();server.server_close();thread.join(timeout=5)


class ConfigRefreshTests(unittest.TestCase):
    def test_current_config_refresh_is_a_noop(self):
        with mock.patch.object(G,'state',return_value=(Path('/unused'),{})),mock.patch.object(G,'atomic_public_config') as write:
            self.assertEqual(G.refresh_config()['status'],'unchanged');write.assert_not_called()

    def test_unreviewed_revision_is_not_refreshed(self):
        with mock.patch.object(G,'state',side_effect=G.GatewayError('reissue_gateway_for_source_or_identity_change')),mock.patch.object(G,'atomic_public_config') as write:
            with self.assertRaises(G.GatewayError):G.refresh_config()
            write.assert_not_called()

    def test_atomic_refresh_refuses_keys_and_changed_input(self):
        with self.assertRaisesRegex(G.GatewayError,'target_refused'):G.atomic_public_config(Path('/unused/server.key'),b'new',b'old')
        helper=mock.Mock();helper.safe_read.return_value=b'changed'
        pki=mock.Mock();pki.backup.return_value=helper
        with mock.patch.object(G,'pki',return_value=pki):
            with self.assertRaisesRegex(G.GatewayError,'changed_during_refresh'):G.atomic_public_config(Path('/unused/Caddyfile'),b'new',b'old')

    def test_refresh_writes_only_config_and_manifest_after_validation(self):
        release=Path('/synthetic/release');network={'address':'192.168.42.20','network':'192.168.42.0/24'}
        old_manifest=json.dumps({'source_sha256':{'old':'value'},'release':'retained'}).encode()
        helper=mock.Mock();helper.safe_read.side_effect=lambda path,*a,**kw:old_manifest if path.name=='deployment.json' else b'old Caddy text'
        pki=mock.Mock();pki.backup.return_value=helper
        def state(*,legacy=False):
            if not legacy:raise G.GatewayError('reissue_gateway_for_source_or_identity_change')
            return release,network
        with mock.patch.object(G,'state',side_effect=state),mock.patch.object(G,'pki',return_value=pki),mock.patch.object(G,'tools',return_value=Path('/synthetic/caddy')),mock.patch.object(G,'native_validate') as validate,mock.patch.object(G,'render',return_value=('unchanged compose','new Caddy text')),mock.patch.object(G,'atomic_public_config') as write:
            self.assertEqual(G.refresh_config()['status'],'refreshed')
        validate.assert_called_once_with(Path('/synthetic/caddy'),release,'new Caddy text')
        self.assertEqual([call.args[0].name for call in write.call_args_list],['Caddyfile','deployment.json'])
        written_manifest=json.loads(write.call_args_list[1].args[1])
        self.assertEqual(written_manifest['release'],'retained')
        self.assertEqual(written_manifest['source_sha256'],G.source_hashes())

    def test_manifest_failure_restores_previous_caddyfile(self):
        release=Path('/synthetic/release');helper=mock.Mock()
        helper.safe_read.side_effect=lambda path,*a,**kw:b'{}' if path.name=='deployment.json' else b'old'
        pki=mock.Mock();pki.backup.return_value=helper
        def state(*,legacy=False):
            if not legacy:raise G.GatewayError('reissue_gateway_for_source_or_identity_change')
            return release,{}
        with mock.patch.object(G,'state',side_effect=state),mock.patch.object(G,'pki',return_value=pki),mock.patch.object(G,'tools'),mock.patch.object(G,'native_validate'),mock.patch.object(G,'render',return_value=('compose','new')),mock.patch.object(G,'atomic_public_config',side_effect=[None,OSError(),None]) as write:
            with self.assertRaises(OSError):G.refresh_config()
        self.assertEqual(write.call_args_list[-1].args,(release/'Caddyfile',b'old',b'new'))


class NativeIPWithoutSNITests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('caddy') and shutil.which('step'),'mise native TLS tools required')
    def test_ip_san_differs_from_listener_and_default_sni_is_required(self):
        p=G.pki();helper=p.backup()
        with tempfile.TemporaryDirectory(prefix='gateway-no-sni-') as folder:
            base=Path(folder);root=base/'root';issuer=base/'issuer';release=base/'release'
            for path in (root,issuer,release):path.mkdir(mode=0o700)
            with helper.memory_file() as rp,helper.memory_file() as ip,p.Native(p.tool()) as native:
                for handle in (rp,ip):handle.write(secrets.token_hex(32).encode()+b'\n');handle.seek(0)
                descriptor=lambda handle:Path('/proc')/str(os.getpid())/'fd'/str(handle.fileno())
                p.generate(native,helper,root,issuer,descriptor(rp),descriptor(ip))
                G.leaf(native,issuer,release,{'address':'127.0.0.2'},descriptor(ip))
            for use_default in (False,True):
                with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
                default='    default_sni login.home.arpa\n' if use_default else ''
                config='{\n    admin off\n    auto_https off\n    persist_config off\n'+default+'}\n'
                config+=f'https://127.0.0.2:{port} {{\n bind 127.0.0.1\n tls {release / "fullchain.crt"} {release / "server.key"}\n respond "ok"\n}}\n'
                path=base/'Caddyfile';path.write_text(config)
                context=ssl.create_default_context(cafile=str(root/'root.crt'))
                with open(base/'log','wb') as log:
                    process=subprocess.Popen([shutil.which('caddy'),'run','--config',str(path),'--adapter','caddyfile'],stdout=log,stderr=log)
                    try:
                        for attempt in range(60):
                            try:
                                with socket.create_connection(('127.0.0.1',port),timeout=1):break
                            except OSError:
                                if attempt==59:raise
                                time.sleep(.05)
                        with socket.create_connection(('127.0.0.1',port),timeout=2) as raw:
                            if use_default:
                                # Python omits SNI for an IP literal but still verifies that IP's SAN.
                                with context.wrap_socket(raw,server_hostname='127.0.0.2') as tls:
                                    tls.sendall(f'GET / HTTP/1.1\r\nHost: 127.0.0.2:{port}\r\nConnection: close\r\n\r\n'.encode())
                                    self.assertIn(b'200',tls.recv(1024).split(b'\r\n',1)[0])
                            else:
                                with self.assertRaises(ssl.SSLError):context.wrap_socket(raw,server_hostname='127.0.0.2')
                    finally:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=='__main__':unittest.main()


class CSRFConfigRevisionTests(unittest.TestCase):
    def test_only_exact_prior_source_pairs_are_accepted(self):
        current=G.source_hashes()
        for name,(caddy,script) in G.LEGACY_CONFIG_REVISIONS.items():
            old={**current,'infra/gateway/Caddyfile':caddy,'scripts/gateway/gateway.py':script}
            self.assertEqual(G.legacy_source_revision(old,current),(name,old))
            for key in ('infra/gateway/compose.yaml','infra/gateway/Caddyfile','scripts/gateway/gateway.py'):
                with self.assertRaises(G.GatewayError):G.legacy_source_revision({**old,key:'unreviewed'},current)
        with self.assertRaises(G.GatewayError):G.legacy_source_revision({},current)

    def test_legacy_render_is_the_exact_reviewed_template(self):
        import hashlib
        current=(ROOT/'infra/gateway/Caddyfile').read_text()
        for name,(digest,_) in G.LEGACY_CONFIG_REVISIONS.items():
            old=G.legacy_caddy_text(current,name)
            self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),digest)
            self.assertNotIn('header_up X-Authentik-CSRF',old)
        self.assertIn('default_sni login.home.arpa',G.legacy_caddy_text(current,'pre_csrf'))
        with self.assertRaises(G.GatewayError):G.legacy_caddy_text(current,'arbitrary')
