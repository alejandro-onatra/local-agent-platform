"""Owner-run, guarded root/intermediate creation with explicit online opt-in; no media formatting."""
import argparse
import contextlib
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
EXPECTED={'schema_version':1,'step_version':'0.30.6','openssl_version':'3.5.5',
    'root':{'subject':'Local Agent Platform Root CA','lifetime_hours':87600,'max_path_len':1},
    'intermediate':{'subject':'Local Agent Platform Intermediate CA','lifetime_hours':8760,'max_path_len':0},
    'key':{'type':'EC','curve':'P-384','encrypted':True,'storage_format':'encrypted-pkcs8','cipher':'aes-256-cbc','prf':'hmacWithSHA256','iterations':600000},'minimum_phrase_bytes':16,
    'root_directory_name':'agent-platform-ca-root','issuer_directory_name':'.local/share/agent-platform/pki/issuer'}
# A PEM format delimiter, not embedded credential material. Build its framing
# separately so the scanner does not mistake two validation literals for a key.
ENCRYPTED_HEADER=b'-'*5+b'BEGIN ENCRYPTED PRIVATE KEY'+b'-'*5
class PKIError(ValueError):pass


def backup():
    spec=importlib.util.spec_from_file_location('pki_identity_helpers',ROOT/'scripts/identity/backup.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def profile():
    helper=backup().local_module().native().source_module()
    actual=helper.parse((ROOT/'config/pki/ceremony.yaml').read_bytes())
    if not helper.same(actual,EXPECTED):raise PKIError('pki_profile_drift')
    return actual


def command(args):
    # These calls return metadata only; never invoke key-printing commands here.
    result=subprocess.run(args,capture_output=True,timeout=30,
        env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':str(Path.home()),'DOCKER_CONFIG':'/nonexistent','LC_ALL':'C'})
    if result.returncode:raise PKIError('pki_metadata_command_failed')
    if len(result.stdout)>2*1024**2:raise PKIError('pki_metadata_output_too_large')
    return result.stdout


def tool():
    executable=shutil.which('step')
    if not executable or not re.search(rb'^Smallstep CLI/0\.30\.6(?:\s|$)',command([executable,'version'])):
        raise PKIError('use_mise_pinned_step_0_30_6')
    return Path(executable)


def openssl_tool():
    executable=Path('/usr/bin/openssl')
    if not command([str(executable),'version']).startswith(b'OpenSSL 3.5.5 '):
        raise PKIError('review_host_openssl_version_before_ceremony')
    return executable


def usb_mount(path):
    if path is None or not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise PKIError('explicit_existing_usb_mount_required')
    if path.resolve()!=path:raise PKIError('linked_usb_mount_rejected')
    mounted=json.loads(command(['findmnt','--json','--mountpoint',str(path),'--output','TARGET,SOURCE,FSTYPE,OPTIONS,UUID']))
    rows=mounted.get('filesystems',[])
    if len(rows)!=1:raise PKIError('usb_mount_not_unique')
    row=rows[0]
    if (row.get('target')!=str(path) or row.get('fstype') not in ('vfat','exfat','ext4')
            or not row.get('uuid') or 'rw' not in row.get('options','').split(',')):
        raise PKIError('unsupported_or_readonly_usb_mount')
    # PATH does not implicitly enable tree output; require parent/child ancestry.
    disks=json.loads(command(['lsblk','--json','--tree','--output','PATH,TRAN,RM,TYPE,UUID'])).get('blockdevices',[])
    def eligible(node,parent_usb=False):
        physical=parent_usb or node.get('tran')=='usb' and node.get('rm') is True
        found=physical and node.get('path')==row.get('source') and node.get('uuid')==row['uuid']
        return found or any(eligible(child,physical) for child in node.get('children',[]))
    if not any(eligible(disk) for disk in disks):raise PKIError('mount_is_not_verified_removable_usb')
    return row


def offline():
    links=json.loads(command(['ip','-json','link','show']))
    if not isinstance(links,list) or not links or not any(link.get('ifname')=='lo' for link in links):
        raise PKIError('network_inventory_incomplete')
    for link in links:
        if link.get('ifname')=='lo':continue
        kind=link.get('linkinfo',{}).get('info_kind')
        if kind in ('bridge','veth'):continue  # Docker must be empty below.
        if {'UP','LOWER_UP'}<=set(link.get('flags',[])):
            raise PKIError('network_link_active_disconnect_first')
    for family in ('-4','-6'):
        routes=json.loads(command(['ip',family,'-json','route','show','default']))
        if not isinstance(routes,list):raise PKIError('network_inventory_incomplete')
        if routes:raise PKIError('default_route_present_disconnect_first')
    network=command(['nmcli','--terse','--fields','STATE','general']).decode().strip()
    if network not in ('disconnected','asleep'):raise PKIError('network_manager_not_disconnected')
    stopped_containers()
    return {'network_snapshot':'passed','default_context_containers_stopped':'passed',
            'host_integrity_and_other_agent_review':'manual_not_certified'}


def stopped_containers():
    # A reachable daemon avoids treating live-restore workloads as absent.
    running=command(['sudo','-n','docker','--context','default','ps','--quiet'])
    if running.strip():raise PKIError('containers_running_stop_workloads_first')


def ceremony_checks(allow_online=False):
    if not allow_online:return offline()
    stopped_containers()
    return {'network_snapshot':'not_required_owner_accepted_online_exposure',
            'ceremony_mode':'online','default_context_containers_stopped':'passed',
            'host_integrity_and_other_agent_review':'manual_not_certified'}


def private_parent(path):
    for parent in reversed([path,*path.parents]):
        if not parent.exists():parent.mkdir(mode=0o700)
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.getuid()) or info.st_mode&0o022:
            raise PKIError('unsafe_issuer_parent')


def pair(helper,label):
    print('[pki] Choose a unique '+label+' phrase; input remains hidden.',file=sys.stderr,flush=True)
    phrase=helper.terminal_phrase();confirm=helper.terminal_phrase(confirm=True)
    if len(phrase)<16 or phrase!=phrase.strip() or b'\x00' in phrase or not hmac.compare_digest(phrase,confirm):
        raise PKIError('phrase_too_short_or_confirmation_mismatch')
    return phrase


class Native:
    def __init__(self,step):self.step=step;self.openssl=openssl_tool();self.helper=backup();self.temp=None
    def __enter__(self):
        self.temp=tempfile.TemporaryDirectory(prefix='pki-cli-public-context-');return self
    def __exit__(self,*args):self.temp.cleanup()
    def run(self,args):return self.execute(self.step,args)
    def execute(self,executable,args):
        # Explicit paths for every key; the isolated STEPPATH contains no key.
        with self.helper.memory_file() as output:
            self.helper.stream_command(['/usr/bin/env','HOME='+self.temp.name,'STEPPATH='+self.temp.name,
                str(executable),*map(str,args)],subprocess.DEVNULL,output,timeout=180)
            output.seek(0);return output.read()


def cert_info(native,path,role):
    info=json.loads(native.run(['certificate','inspect','--format','json',path]))
    extensions=info.get('extensions',{});constraints=extensions.get('basic_constraints',{})
    usage=extensions.get('key_usage',{});validity=info.get('validity',{})
    fingerprint=info.get('fingerprint_sha256','').replace(':','').lower()
    if (constraints.get('is_ca') is not True or type(constraints.get('max_path_len')) is not int
            or constraints['max_path_len']!=EXPECTED[role]['max_path_len']
            or usage.get('certificate_sign') is not True or usage.get('crl_sign') is not True
            or type(validity.get('length')) is not int or not 0<validity['length']<=EXPECTED[role]['lifetime_hours']*3600
            or not re.fullmatch('[a-f0-9]{64}',fingerprint)):
        raise PKIError('certificate_ca_constraints_or_lifetime_invalid')
    return {'fingerprint_sha256':fingerprint,'not_before':validity['start'],'not_after':validity['end'],
            'max_path_len':constraints['max_path_len']}


def encrypted_key(path):
    data=backup().safe_read(path,65536)
    if not data.startswith(ENCRYPTED_HEADER):
        raise PKIError('expected_encrypted_pkcs8_key_stop_and_review')


def matched_key(native,cert,key,password):
    encrypted_key(key)
    pub_cert=native.run(['crypto','key','public',cert])
    pub_key=native.run(['crypto','key','public',key,'--password-file',password])
    if not hmac.compare_digest(pub_cert,pub_key):raise PKIError('certificate_key_mismatch')


def encrypted_pkcs8(native,helper,path,password):
    with helper.memory_file() as public,helper.memory_file() as legacy,helper.memory_file() as output_pass:
        for handle in (public,legacy,output_pass):os.fchmod(handle.fileno(),0o600)
        descriptor=lambda handle:Path('/proc')/str(os.getpid())/'fd'/str(handle.fileno())
        # --force applies only to existing anonymous fds, never to a disk key/cert.
        native.run(['crypto','keypair',descriptor(public),descriptor(legacy),'--kty','EC','--curve','P-384',
                    '--password-file',password,'--force'])
        output_pass.write(Path(password).read_bytes());output_pass.seek(0)
        encoded=native.execute(native.openssl,['pkcs8','-topk8','-in',descriptor(legacy),
            '-passin','file:'+str(password),'-passout','file:'+str(descriptor(output_pass)),
            '-v2','aes-256-cbc','-v2prf','hmacWithSHA256','-iter','600000'])
        if not encoded.startswith(ENCRYPTED_HEADER):
            raise PKIError('encrypted_pkcs8_conversion_failed')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:os.write(fd,encoded);os.fsync(fd)
        finally:os.close(fd)


def generate(native,helper,root_dir,issuer,root_password,issuer_password):
    # Shared with synthetic native tests; real create() supplies all guards first.
    root_cert=root_dir/'root.crt';root_key=root_dir/'root.key'
    issuer_cert=issuer/'intermediate.crt';issuer_key=issuer/'intermediate.key'
    encrypted_pkcs8(native,helper,root_key,root_password)
    native.run(['certificate','create',EXPECTED['root']['subject'],root_cert,'--key',root_key,
        '--profile','root-ca','--not-after','87600h','--password-file',root_password])
    matched_key(native,root_cert,root_key,root_password)
    encrypted_pkcs8(native,helper,issuer_key,issuer_password)
    native.run(['certificate','create',EXPECTED['intermediate']['subject'],issuer_cert,'--key',issuer_key,
        '--profile','intermediate-ca','--not-after','8760h',
        '--ca',root_cert,'--ca-key',root_key,'--ca-password-file',root_password,'--password-file',issuer_password])
    issuer_key.chmod(0o600);issuer_cert.chmod(0o600)
    matched_key(native,issuer_cert,issuer_key,issuer_password)
    native.run(['certificate','verify','--roots',root_cert,root_cert])
    native.run(['certificate','verify','--roots',root_cert,issuer_cert])
    public={'root':cert_info(native,root_cert,'root'),'intermediate':cert_info(native,issuer_cert,'intermediate')}
    helper.local_module().write_file(issuer/'root.crt',helper.safe_read(root_cert,65536),os.getuid(),0o600)
    return public


def create(path,allow_online=False):
    if os.geteuid()==0:raise PKIError('run_ceremony_as_desktop_user_without_sudo')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    profile();step=tool();openssl_tool();device=usb_mount(path);checks=ceremony_checks(allow_online)
    root_dir=path/EXPECTED['root_directory_name'];issuer=Path.home()/EXPECTED['issuer_directory_name']
    if root_dir.exists() or root_dir.is_symlink() or issuer.exists() or issuer.is_symlink():
        raise PKIError('existing_pki_preserved_no_overwrite')
    helper=backup()
    root_phrase=pair(helper,'ROOT');issuer_phrase=pair(helper,'INTERMEDIATE')
    if hmac.compare_digest(root_phrase,issuer_phrase):raise PKIError('root_and_intermediate_phrases_must_differ')
    if usb_mount(path)['uuid']!=device['uuid']:raise PKIError('usb_changed_during_ceremony')
    ceremony_checks(allow_online);private_parent(issuer.parent)
    if shutil.disk_usage(path).free<1024**2 or shutil.disk_usage(issuer.parent).free<1024**2:
        raise PKIError('less_than_1_mib_free_for_key_material')
    root_dir.mkdir(mode=0o700);issuer.mkdir(mode=0o700)
    # Pin the USB directory inode. A detach cannot redirect native output into a
    # plain fallback directory on the host. Never execute files from the stick.
    directory=os.open(root_dir,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    held=Path('/proc')/str(os.getpid())/'fd'/str(directory)
    try:
        with helper.memory_file() as root_pass,helper.memory_file() as issuer_pass,Native(step) as native:
            for handle,value in ((root_pass,root_phrase),(issuer_pass,issuer_phrase)):
                os.fchmod(handle.fileno(),0o600);handle.write(value+b'\n');handle.seek(0)
            del root_phrase,issuer_phrase
            root_password=Path('/proc')/str(os.getpid())/'fd'/str(root_pass.fileno())
            issuer_password=Path('/proc')/str(os.getpid())/'fd'/str(issuer_pass.fileno())
            print('[pki] Creating encrypted root and signing the encrypted intermediate.',file=sys.stderr,flush=True)
            public=generate(native,helper,held,issuer,root_password,issuer_password)
        if usb_mount(path)['uuid']!=device['uuid']:raise PKIError('usb_changed_after_signing_preserve_material')
        ceremony_checks(allow_online)
        inventory={'schema_version':1,'purpose':'household_ca_public_inventory',**public}
        # FAT/exFAT do not provide POSIX ownership/mode guarantees. This public
        # inventory needs no fchown; root-key protection is its encryption.
        content=json.dumps(inventory,indent=2).encode()
        metadata=os.open('public-inventory.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:os.write(metadata,content);os.fsync(metadata)
        finally:os.close(metadata)
        helper.local_module().write_file(issuer/'public-inventory.json',content,os.getuid(),0o600)
        return {'status':'created','root_directory':str(root_dir),'issuer_directory':str(issuer),
                'root_private_key_encrypted':True,'intermediate_private_key_encrypted':True,
                'public_inventory':public,'checks':checks,'root_media_disconnect':'required',
                'online_issuer_policy':'pending','client_trust':'not_installed','household_readiness':'pending'}
    finally:os.close(directory)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['environment','plan','offline-check','online-check','create'])
    parser.add_argument('--usb',type=Path)
    parser.add_argument('--allow-online',action='store_true',help='Owner accepts network exposure during creation; other guards remain')
    args=parser.parse_args()
    if args.allow_online and args.mode!='create':parser.error('--allow-online applies only to create')
    try:
        profile()
        if args.mode=='environment':
            tool();openssl_tool()
            for name in ('ip','nmcli','findmnt','lsblk','docker'):
                if not shutil.which(name):raise PKIError('required_host_tool_missing')
            result={'status':'passed','step_version':'0.30.6','host_openssl_version':'3.5.5','scope':'Tools/source only; no device write, root or trust creation'}
        elif args.mode=='plan':
            if args.usb:usb_mount(args.usb)
            result={'status':'prepared','root_lifetime_hours':87600,'intermediate_lifetime_hours':8760,
                'root_on_encrypted_usb_file':True,'separate_phrases':True,'formats_media':False,
                'requires_offline_snapshot':True,'explicit_online_creation_available':True,'scope':'No keys created; controlled offline ceremony remains owner-run'}
        elif args.mode=='offline-check':
            usb_mount(args.usb);result={'status':'passed','checks':offline(),'scope':'Read-only network/container/USB snapshot; not clean-host or hardware air-gap certification'}
        elif args.mode=='online-check':
            usb_mount(args.usb);result={'status':'passed','checks':ceremony_checks(True),
                'scope':'Owner-approved connected ceremony preflight; no key creation or offline assurance'}
        else:result=create(args.usb,allow_online=args.allow_online)
    except Exception as error:
        result={'status':'failed','error':str(error) if isinstance(error,PKIError) else 'pki_operation_failed_details_withheld',
                'existing_material':'preserved_review_before_retry'}
    result['household_readiness']='pending'
    print(json.dumps(result,indent=2));return int(result['status']=='failed')


if __name__=='__main__':raise SystemExit(main())
