"""Public activation metadata must not permit root, shell evaluation or linked records."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('hardening_settings',ROOT/'scripts/openhands/hardening-settings.py')
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'activation.yaml'

    def test_valid_numeric_identity(self):
        self.path.write_text('schema_version: 1\nuid: 1000\ngid: 1000\n')
        self.assertEqual(MOD.load(self.path),(1000,1000))

    def test_root_boolean_shell_and_extra_field_rejected(self):
        for fields in ['uid: 0\ngid: 1000','uid: 1000\ngid: 0','uid: true\ngid: 1000',
                       'uid: "$(touch synthetic)"\ngid: 1000','uid: 1000\ngid: 1000\nextra: unexpected']:
            self.path.write_text('schema_version: 1\n'+fields+'\n')
            with self.assertRaises(ValueError): MOD.load(self.path)

    def test_duplicate_field_rejected(self):
        self.path.write_text('schema_version: 1\nuid: 1000\nuid: 2000\ngid: 1000\n')
        with self.assertRaises(ValueError): MOD.load(self.path)

    def test_missing_and_symlink_rejected(self):
        with self.assertRaises(ValueError): MOD.load(self.path)
        target=Path(self.temp.name)/'other.yaml';target.write_text('schema_version: 1\nuid: 1000\ngid: 1000\n')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError): MOD.load(self.path)


if __name__=='__main__': unittest.main()
