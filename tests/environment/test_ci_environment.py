"""CI rejects incompatible crypto/OS without requiring desktop ceremony tools."""
import importlib.util,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ci_environment_tests',ROOT/'scripts/environment/check-ci.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

class CIEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.native=SimpleNamespace(profile=mock.Mock(),tool=mock.Mock(),openssl_tool=mock.Mock(),
            EXPECTED={'step_version':'0.30.6','openssl_version':'3.5.5'})
        self.target={'id':'ubuntu','version_id':'26.04'}
        self.os={'ID':'ubuntu','VERSION_ID':'26.04'}

    def test_native_tools_pass_without_any_desktop_facilities(self):
        result=C.verify(self.native,self.target,self.os)
        self.assertEqual(result['status'],'passed')
        self.native.profile.assert_called_once();self.native.tool.assert_called_once()
        self.native.openssl_tool.assert_called_once()
        self.assertIn('no host ceremony',result['scope'])

    def test_unreviewed_os_fails_before_native_commands(self):
        with self.assertRaises(C.CIEnvironmentError):C.verify(self.native,self.target,{'ID':'ubuntu','VERSION_ID':'24.04'})
        self.native.tool.assert_not_called();self.native.openssl_tool.assert_not_called()

    def test_native_crypto_contract_failures_are_never_ignored(self):
        for name in ('profile','tool','openssl_tool'):
            with self.subTest(check=name):
                command=getattr(self.native,name);command.side_effect=ValueError('unreviewed tool')
                with self.assertRaises(ValueError):C.verify(self.native,self.target,self.os)
                command.side_effect=None
