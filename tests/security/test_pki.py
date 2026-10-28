"""PKI guards and temporary native encrypted certificate tests; no real USB writes."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('offline_pki_tests',ROOT/'scripts/pki/pki.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


class NetworkTests(unittest.TestCase):
    def run_guard(self,links=None,route4=None,route6=None,state=b'disconnected',containers=b''):
        def command(args):
            if args[:3]==['ip','-json','link']:return json.dumps(links if links is not None else [{'ifname':'lo','flags':['UP','LOWER_UP']}]).encode()
            if args[:2]==['ip','-4']:return json.dumps(route4 if route4 is not None else []).encode()
            if args[:2]==['ip','-6']:return json.dumps(route6 if route6 is not None else []).encode()
            if args[0]=='nmcli':return state
            if args[0]=='sudo':return containers
            raise AssertionError(args)
        with mock.patch.object(P,'command',side_effect=command):return P.offline()

    def test_offline_snapshot_passes_without_claiming_clean_host(self):
        result=self.run_guard()
        self.assertEqual(result['network_snapshot'],'passed')
        self.assertEqual(result['host_integrity_and_other_agent_review'],'manual_not_certified')

    def test_physical_link_ipv4_ipv6_or_connected_manager_rejected(self):
        lo={'ifname':'lo','flags':['UP','LOWER_UP']}
        for values in ({'links':[lo,{'ifname':'wlan0','flags':['UP','LOWER_UP']}]},
                       {'route4':[{'dst':'default'}]},{'route6':[{'dst':'default'}]}, {'state':b'connected'}):
            with self.subTest(values=values),self.assertRaises(P.PKIError):self.run_guard(**values)

    def test_containers_running_or_unavailable_daemon_never_pass(self):
        with self.assertRaisesRegex(P.PKIError,'containers_running'):self.run_guard(containers=b'abc')
        with mock.patch.object(P,'command',side_effect=P.PKIError('metadata_failed')):
            with self.assertRaises(P.PKIError):P.offline()

    def test_empty_network_inventory_rejected(self):
        with self.assertRaisesRegex(P.PKIError,'inventory_incomplete'):self.run_guard(links=[])
        with self.assertRaises(P.PKIError):self.run_guard(route4={})


class OnlineChoiceTests(unittest.TestCase):
    def test_default_still_requires_offline_checks(self):
        with mock.patch.object(P,'offline',side_effect=P.PKIError('online')) as offline:
            with self.assertRaises(P.PKIError):P.ceremony_checks()
        offline.assert_called_once()

    def test_explicit_online_choice_records_lower_assurance(self):
        with mock.patch.object(P,'offline') as offline,mock.patch.object(P,'stopped_containers') as containers:
            result=P.ceremony_checks(True)
        offline.assert_not_called();containers.assert_called_once()
        self.assertEqual(result['ceremony_mode'],'online')
        self.assertEqual(result['network_snapshot'],'not_required_owner_accepted_online_exposure')

    def test_online_choice_does_not_skip_running_container_guard(self):
        with mock.patch.object(P,'command',return_value=b'active-container'):
            with self.assertRaisesRegex(P.PKIError,'containers_running'):P.ceremony_checks(True)


class USBTests(unittest.TestCase):
    def test_only_verified_rw_usb_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            row={'target':folder,'source':'/dev/sdz1','fstype':'vfat','options':'rw,nosuid,nodev','uuid':'TEST-UUID'}
            disk={'path':'/dev/sdz','tran':'usb','rm':True,'type':'disk','children':[
                {'path':'/dev/sdz1','tran':None,'rm':True,'type':'part','uuid':'TEST-UUID'}]}
            def command(args):
                return json.dumps({'filesystems':[row]} if args[0]=='findmnt' else {'blockdevices':[disk]}).encode()
            with mock.patch.object(P,'command',side_effect=command):
                self.assertEqual(P.usb_mount(path)['uuid'],'TEST-UUID')
                for field,value in [('fstype','ext3'),('options','ro'),('uuid',''),('target','/another')]:
                    original=row[field];row[field]=value
                    with self.assertRaises(P.PKIError):P.usb_mount(path)
                    row[field]=original
                disk['tran']='nvme'
                with self.assertRaisesRegex(P.PKIError,'removable_usb'):P.usb_mount(path)

    def test_explicit_tree_required_for_usb_partition_ancestry(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            row={'target':folder,'source':'/dev/sdz1','fstype':'vfat','options':'rw','uuid':'TEST-UUID'}
            partition={'path':'/dev/sdz1','tran':None,'rm':True,'type':'part','uuid':'TEST-UUID'}
            disk={'path':'/dev/sdz','tran':'usb','rm':True,'type':'disk','uuid':None}
            def command(args):
                if args[0]=='findmnt':return json.dumps({'filesystems':[row]}).encode()
                # Like lsblk: PATH without --tree returns a flat list, with no
                # transport inherited by the partition. The old command fails.
                devices=[{**disk,'children':[partition]}] if '--tree' in args else [disk,partition]
                return json.dumps({'blockdevices':devices}).encode()
            with mock.patch.object(P,'command',side_effect=command):
                self.assertEqual(P.usb_mount(path)['uuid'],'TEST-UUID')
                partition['uuid']='FOREIGN-UUID'
                with self.assertRaisesRegex(P.PKIError,'removable_usb'):P.usb_mount(path)
                partition['uuid']='TEST-UUID';disk['rm']=False
                with self.assertRaisesRegex(P.PKIError,'removable_usb'):P.usb_mount(path)

    def test_flat_unrelated_usb_cannot_validate_an_internal_partition(self):
        with tempfile.TemporaryDirectory() as folder:
            row={'target':folder,'source':'/dev/nvme0n1p1','fstype':'ext4','options':'rw','uuid':'TEST-UUID'}
            devices=[{'path':'/dev/sdz','tran':'usb','rm':True,'type':'disk'},
                     {'path':'/dev/nvme0n1p1','tran':None,'rm':False,'type':'part','uuid':'TEST-UUID'}]
            def command(args):
                return json.dumps({'filesystems':[row]} if args[0]=='findmnt' else {'blockdevices':devices}).encode()
            with mock.patch.object(P,'command',side_effect=command):
                with self.assertRaisesRegex(P.PKIError,'removable_usb'):P.usb_mount(Path(folder))

    def test_linked_mount_rejected_before_metadata_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);link=path/'link';link.symlink_to(path)
            with mock.patch.object(P,'command') as command:
                with self.assertRaises(P.PKIError):P.usb_mount(link)
            command.assert_not_called()


class CryptoContractTests(unittest.TestCase):
    def test_certificates_must_be_ca_with_reviewed_path_length_and_lifetime(self):
        info={'extensions':{'basic_constraints':{'is_ca':True,'max_path_len':1},
              'key_usage':{'certificate_sign':True,'crl_sign':True}},
              'validity':{'length':315360000,'start':'start','end':'end'},'fingerprint_sha256':'a'*64}
        native=mock.Mock();native.run.return_value=json.dumps(info).encode()
        self.assertEqual(P.cert_info(native,Path('/public.crt'),'root')['max_path_len'],1)
        for mutate in (lambda value:value['extensions']['basic_constraints'].update(is_ca=False),
                       lambda value:value['extensions']['basic_constraints'].update(max_path_len=True),
                       lambda value:value['validity'].update(length=315360001),
                       lambda value:value['extensions']['key_usage'].update(certificate_sign=False)):
            changed=copy.deepcopy(info);mutate(changed);native.run.return_value=json.dumps(changed).encode()
            with self.assertRaises(P.PKIError):P.cert_info(native,Path('/public.crt'),'root')

    def test_unencrypted_private_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            key=Path(folder)/'synthetic.key';key.write_bytes(b'-----BEGIN PRIVATE KEY-----\nsynthetic')
            with self.assertRaisesRegex(P.PKIError,'encrypted_pkcs8'):P.encrypted_key(key)

    def test_phrase_confirmation_short_and_whitespace_rejected(self):
        helper=mock.Mock()
        for phrase,confirm in ((b'short',b'short'),(b'a'*20,b'b'*20),(b' '+b'a'*20,b' '+b'a'*20)):
            helper.terminal_phrase.side_effect=[phrase,confirm]
            with self.assertRaises(P.PKIError):P.pair(helper,'TEST')

    def test_unreviewed_crypto_versions_rejected(self):
        with mock.patch.object(P,'command',return_value=b'OpenSSL 9.0.0 unreviewed'):
            with self.assertRaisesRegex(P.PKIError,'openssl_version'):P.openssl_tool()
        with mock.patch.object(P.shutil,'which',return_value='/synthetic/step'),mock.patch.object(P,'command',return_value=b'Smallstep CLI/9.0.0'):
            with self.assertRaisesRegex(P.PKIError,'pinned_step'):P.tool()

    def test_profile_mutation_rejected(self):
        helper=P.backup().local_module().native().source_module()
        bad=copy.deepcopy(P.EXPECTED);bad['key']['encrypted']=False
        with mock.patch.object(helper,'parse',return_value=bad),mock.patch.object(P,'backup') as backup:
            backup.return_value.local_module.return_value.native.return_value.source_module.return_value=helper
            with self.assertRaises(P.PKIError):P.profile()


class CreateGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/'home';self.home.mkdir();self.usb=Path(self.temp.name)/'usb';self.usb.mkdir()
        self.helper=mock.Mock();self.helper.terminal_phrase.side_effect=[b'a'*24,b'a'*24,b'b'*24,b'b'*24]
        for obj,name,value in ((P,'profile',mock.Mock(return_value=P.EXPECTED)),(P,'tool',mock.Mock(return_value=Path('/step'))),
                               (P,'usb_mount',mock.Mock(return_value={'uuid':'TEST'})),(P,'offline',mock.Mock(return_value={})),
                               (P,'backup',mock.Mock(return_value=self.helper)),(P,'openssl_tool',mock.Mock(return_value=Path('/openssl'))),(P.Path,'home',mock.Mock(return_value=self.home)),
                               (P.resource,'setrlimit',mock.Mock())):
            patch=mock.patch.object(obj,name,value);patch.start();self.addCleanup(patch.stop)

    def test_online_or_existing_material_blocks_before_phrase_or_write(self):
        with mock.patch.object(P,'offline',side_effect=P.PKIError('online')):
            with self.assertRaises(P.PKIError):P.create(self.usb)
        self.helper.terminal_phrase.assert_not_called()
        existing=self.usb/P.EXPECTED['root_directory_name'];existing.mkdir();marker=existing/'KEEP';marker.write_text('preserve')
        with self.assertRaisesRegex(P.PKIError,'no_overwrite'):P.create(self.usb)
        self.assertEqual(marker.read_text(),'preserve');self.helper.terminal_phrase.assert_not_called()

    def test_identical_root_and_intermediate_phrases_rejected_before_write(self):
        self.helper.terminal_phrase.side_effect=[b'a'*24]*4
        with self.assertRaisesRegex(P.PKIError,'must_differ'):P.create(self.usb)
        self.assertFalse((self.usb/P.EXPECTED['root_directory_name']).exists())

    def test_swapped_usb_before_creation_preserves_existing_contents(self):
        P.usb_mount.side_effect=[{'uuid':'ORIGINAL'},{'uuid':'SWAPPED'}]
        with self.assertRaisesRegex(P.PKIError,'usb_changed'):P.create(self.usb)
        self.assertEqual(list(self.usb.iterdir()),[])

    def test_online_choice_still_refuses_existing_output_before_phrases(self):
        existing=self.usb/P.EXPECTED['root_directory_name'];existing.mkdir()
        with mock.patch.object(P,'command',return_value=b''):
            with self.assertRaisesRegex(P.PKIError,'no_overwrite'):P.create(self.usb,allow_online=True)
        P.offline.assert_not_called();self.helper.terminal_phrase.assert_not_called()

    def test_online_creation_rechecks_and_records_mode(self):
        # Synthetic filesystem orchestration; real crypto is tested separately.
        spec=importlib.util.spec_from_file_location('pki_real_helpers_online',ROOT/'scripts/identity/backup.py')
        real=importlib.util.module_from_spec(spec);spec.loader.exec_module(real)
        self.helper.memory_file=real.memory_file
        with mock.patch.object(P,'private_parent',side_effect=lambda path:path.mkdir(parents=True)),mock.patch.object(P,'Native'),mock.patch.object(P,'generate',return_value={'synthetic':True}),mock.patch.object(P,'stopped_containers') as containers:
            result=P.create(self.usb,allow_online=True)
        self.assertEqual(result['status'],'created')
        self.assertEqual(result['checks']['ceremony_mode'],'online')
        self.assertEqual(containers.call_count,3)
        self.assertEqual(P.usb_mount.call_count,3)
        P.offline.assert_not_called()
        self.assertTrue((self.usb/P.EXPECTED['root_directory_name']/'public-inventory.json').exists())

    def test_native_failure_preserves_partial_material_for_review(self):
        spec=importlib.util.spec_from_file_location('pki_real_helpers',ROOT/'scripts/identity/backup.py')
        real=importlib.util.module_from_spec(spec);spec.loader.exec_module(real)
        self.helper.memory_file=real.memory_file
        with mock.patch.object(P,'private_parent',side_effect=lambda path:path.mkdir(parents=True)),mock.patch.object(P,'Native') as native,mock.patch.object(P,'generate',side_effect=P.PKIError('synthetic_failure')):
            with self.assertRaises(P.PKIError):P.create(self.usb)
        self.assertTrue((self.usb/P.EXPECTED['root_directory_name']).exists())
        self.assertTrue((self.home/P.EXPECTED['issuer_directory_name']).exists())


class NativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('step'),'mise Smallstep required')
    def test_real_encrypted_root_intermediate_chain_and_memory_password_files(self):
        # Synthetic only: never install trust or use the real USB/issuer directory.
        helper=P.backup();step=P.tool()
        with tempfile.TemporaryDirectory(prefix='pki-native-synthetic-') as folder:
            base=Path(folder);root=base/'root';issuer=base/'issuer';root.mkdir();issuer.mkdir()
            directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:
                held=Path('/proc')/str(os.getpid())/'fd'/str(directory)
                with helper.memory_file() as root_pass,helper.memory_file() as issuer_pass,P.Native(step) as native:
                    for handle in (root_pass,issuer_pass):
                        handle.write(secrets.token_hex(32).encode()+b'\n');handle.seek(0)
                    path=lambda handle:Path('/proc')/str(os.getpid())/'fd'/str(handle.fileno())
                    result=P.generate(native,helper,held,issuer,path(root_pass),path(issuer_pass))
                    self.assertEqual(result['root']['max_path_len'],1)
                    self.assertEqual(result['intermediate']['max_path_len'],0)
                    for file in (root/'root.key',issuer/'intermediate.key'):
                        P.encrypted_key(file)
                        # Inspect public encryption parameters, never print ciphertext.
                        parameters=native.execute(native.openssl,['asn1parse','-in',file])
                        for algorithm in (b'PBES2',b'PBKDF2',b'hmacWithSHA256',b'aes-256-cbc'):
                            self.assertIn(algorithm,parameters)
                        self.assertIn(b'0927C0',parameters)  # 600000 PBKDF2 iterations.
                        original=file.read_bytes()
                        with self.assertRaises(FileExistsError):P.encrypted_pkcs8(native,helper,file,path(root_pass))
                        self.assertEqual(file.read_bytes(),original)
                    self.assertEqual((issuer/'root.crt').read_bytes(),(root/'root.crt').read_bytes())
                    with helper.memory_file() as wrong:
                        wrong.write(secrets.token_hex(32).encode());wrong.seek(0)
                        with self.assertRaises(Exception):P.matched_key(native,root/'root.crt',root/'root.key',path(wrong))
            finally:os.close(directory)


if __name__=='__main__':unittest.main()
