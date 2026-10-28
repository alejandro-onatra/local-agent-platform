"""Inventory regressions: incomplete visibility never becomes deployment evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('lan_inventory', ROOT / 'scripts/environment/inventory-lan.py')
LAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAN)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.candidate = LAN.load_candidate(ROOT)
        self.candidate['decision'] = 'pending'
        self.observation = {'cpu': {'logical_cpus': 16, 'virtualization_flag_visible': True},
                            'memory': {'available_gib': 24}, 'storage': {'free_gib': 80},
                            'virtualization': {'device_visible': True, 'device_accessible': True,
                                               'tools': {name: True for name in LAN.TOOLS}}}

    def test_complete_collection_uses_linux_platform_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            for name in ('proc', 'sys', 'dev'):
                (fixture / name).mkdir()
            (fixture / 'proc/meminfo').write_text('MemTotal: 8388608 kB\nMemAvailable: 4194304 kB\nSwapTotal: 0 kB\n')
            (fixture / 'proc/cpuinfo').write_text('flags\t: fpu svm\n')
            report = LAN.collect(proc=fixture / 'proc', sys=fixture / 'sys', dev=fixture / 'dev',
                                 runner=lambda args: '[]', which=lambda name: '/synthetic/tool')
            self.assertIsInstance(report['os']['ID'], str)
            self.assertEqual(report['memory']['available_gib'], 4)
            self.assertTrue(report['cpu']['virtualization_flag_visible'])
            self.assertFalse(report['virtualization']['device_visible'])
            self.assertEqual(report['offline_ca_custody'], 'pending_supervised_procedure')

    def test_selected_host_containers_do_not_require_kvm(self):
        self.candidate['decision'] = 'host_containers'
        self.observation['virtualization']['device_visible'] = False
        self.observation['cpu']['virtualization_flag_visible'] = False
        self.assertEqual(LAN.assess(self.observation,self.candidate)['status'],'not_required')

    def test_missing_cpu_flags_remain_unknown(self):
        self.assertIsNone(LAN.cpu('processor : 0\n')['virtualization_flag_visible'])
        self.assertTrue(LAN.cpu('flags\t: fpu svm\n')['virtualization_flag_visible'])
        self.assertTrue(LAN.cpu('flags\t: fpu vmx\n')['virtualization_flag_visible'])

    def test_memory_missing_is_not_zero_or_sufficient(self):
        observed = LAN.memory('MemTotal: 8388608 kB\n')
        self.assertEqual(observed['total_gib'], 8)
        self.assertIsNone(observed['available_gib'])
        self.observation['memory']['available_gib'] = None
        self.assertEqual(LAN.assess(self.observation, self.candidate)['capacity']['memory'], 'pending')

    def test_low_capacity_fails_even_if_prerequisites_pass(self):
        self.observation['memory']['available_gib'] = 4
        result = LAN.assess(self.observation, self.candidate)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['capacity']['memory'], 'failed')

    def test_owner_decision_and_missing_kvm_cannot_pass(self):
        self.assertEqual(LAN.assess(self.observation, self.candidate)['status'], 'pending')
        self.candidate['decision'] = 'virtual_machine'
        self.observation['virtualization']['device_visible'] = False
        self.assertEqual(LAN.assess(self.observation, self.candidate)['status'], 'pending')

    def test_vm_feasibility_pass_scope_is_not_sec_acceptance(self):
        self.candidate['decision'] = 'virtual_machine'
        result = LAN.assess(self.observation, self.candidate)
        self.assertEqual(result['status'], 'passed')
        self.assertIn('not allocation', result['scope'])

    def test_network_omits_macs_and_nondefault_interfaces(self):
        interfaces = [{'ifname': 'wifi0', 'address': 'synthetic-mac-marker',
                       'addr_info': [{'scope': 'global', 'local': '192.0.2.12', 'prefixlen': 24}]},
                      {'ifname': 'docker0', 'addr_info': [{'scope': 'global', 'local': '198.51.100.1', 'prefixlen': 24}]}]
        result = LAN.clean_network(interfaces, [{'dev': 'wifi0', 'gateway': '192.0.2.1', 'protocol': 'dhcp'}], [], {'wifi0'})
        serialized = json.dumps(result)
        self.assertNotIn('synthetic-mac-marker', serialized)
        self.assertNotIn('198.51.100.1', serialized)
        self.assertTrue(result['default_routes'][0]['wireless'])
        self.assertTrue(result['default_routes'][0]['dhcp_reported'])

    def test_ipv6_and_invalid_prefix(self):
        interfaces = [{'ifname': 'eth0', 'addr_info': [{'scope': 'global', 'local': '2001:db8::12', 'prefixlen': 64}]}]
        result = LAN.clean_network(interfaces, [], [{'dev': 'eth0', 'gateway': 'fe80::1'}], set())
        self.assertEqual(result['host_addresses'][0]['family'], 6)
        interfaces[0]['addr_info'][0]['prefixlen'] = 129
        with self.assertRaises(ValueError):
            LAN.clean_network(interfaces, [], [{'dev': 'eth0'}], set())

    def test_external_command_errors_are_withheld(self):
        with patch.object(LAN.subprocess, 'run', side_effect=OSError('synthetic-sensitive-error')):
            self.assertIsNone(LAN.command(['ip', '-json', 'address', 'show']))

    def test_report_permissions_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = LAN.save(root, {'status': 'collected'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.unlink()
            (root / 'artifacts/diagnostics').rmdir()
            (root / 'artifacts').rmdir()
            (root / 'artifacts').symlink_to(root)
            with self.assertRaises(ValueError):
                LAN.save(root, {})


if __name__ == '__main__':
    unittest.main()
