"""Regress the upstream cache-write crash against the locked reference function."""
import contextlib
from dataclasses import dataclass
import importlib.util
import inspect
import io
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('usage_launcher', ROOT/'scripts/openhands/start-agent-server.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
FIXTURE = Path(__file__).parent/'fixtures/sdk_normalize_usage_1_49_6.py'


@dataclass
class Snapshot:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Usage:
    """Minimal fixture reproducing LiteLLM's set-but-deleted optional field."""
    def __init__(self, prompt_tokens=100, completion_tokens=5, prompt_tokens_details=None):
        self.prompt_tokens=prompt_tokens
        self.completion_tokens=completion_tokens
        self.completion_tokens_details=None
        self.prompt_tokens_details=None
        if prompt_tokens_details is not None:
            values=prompt_tokens_details
            details=SimpleNamespace(model_fields_set=set(values),cached_tokens=values.get('cached_tokens'))
            if values.get('cache_creation_tokens') is not None:
                details.cache_creation_tokens=values['cache_creation_tokens']
            self.prompt_tokens_details=details


class ResponsesUsage:
    def __init__(self):
        self.input_tokens=50
        self.output_tokens=10
        self.input_tokens_details=SimpleNamespace(cached_tokens=9)
        self.output_tokens_details=SimpleNamespace(reasoning_tokens=4)


def reference_module(fixture=FIXTURE):
    module=ModuleType('reference_telemetry')
    module.__dict__.update(Usage=Usage,ResponseAPIUsage=ResponsesUsage,UsageSnapshot=Snapshot)
    exec(compile(fixture.read_text(),str(fixture),'exec'),module.__dict__)
    return module


class UsageCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.telemetry=reference_module(FIXTURE.with_name('sdk_normalize_usage_1_53_0.py'))

    def apply(self):
        with patch.object(launcher.importlib.metadata,'version',return_value='1.53.0'),patch.object(launcher.importlib,'import_module',return_value=self.telemetry):
            launcher.verify_usage_compatibility()

    def test_original_sdk_reproduces_exact_null_attribute_error(self):
        usage=Usage(prompt_tokens_details={'cached_tokens':3,'cache_creation_tokens':None})
        self.assertIn('cache_creation_tokens',usage.prompt_tokens_details.model_fields_set)
        self.assertFalse(hasattr(usage.prompt_tokens_details,'cache_creation_tokens'))
        with self.assertRaisesRegex(AttributeError,'cache_creation_tokens'):
            reference_module().normalize_usage(usage)

    def test_native_sdk_preserves_totals_and_numeric_read_write_buckets(self):
        self.apply()
        for details,write in [({'cached_tokens':3,'cache_creation_tokens':None},0),
                              ({'cached_tokens':3},0),
                              ({'cached_tokens':3,'cache_creation_tokens':7},7),
                              ({'cached_tokens':3,'cache_creation_tokens':0},0)]:
            result=self.telemetry.normalize_usage(Usage(prompt_tokens_details=details))
            self.assertEqual((result.prompt_tokens,result.completion_tokens,result.cache_read_tokens,result.cache_write_tokens),(100,5,3,write))

    def test_missing_usage_and_details_are_not_invented(self):
        self.apply()
        self.assertIsNone(self.telemetry.normalize_usage(None))
        self.assertIsNone(self.telemetry.normalize_usage(object()))
        self.assertEqual(self.telemetry.normalize_usage(Usage()).cache_write_tokens,0)
        usage=Usage(prompt_tokens_details={'cached_tokens':3})
        usage.prompt_tokens_details.cache_creation_tokens=99
        self.assertEqual(self.telemetry.normalize_usage(usage).cache_write_tokens,0)

    def test_responses_api_and_reasoning_usage_are_unchanged(self):
        expected=self.telemetry.normalize_usage(ResponsesUsage())
        self.apply()
        self.assertEqual(self.telemetry.normalize_usage(ResponsesUsage()),expected)
        self.assertEqual(expected,Snapshot(50,10,4,9,0))

    def test_native_verification_does_not_change_code_or_package_files(self):
        alias=self.telemetry.normalize_usage
        before=FIXTURE.read_bytes()
        code=alias.__code__
        self.apply()
        self.assertIs(alias,self.telemetry.normalize_usage)
        self.assertIs(alias.__code__,code)
        self.assertEqual(alias(Usage(prompt_tokens_details={'cache_creation_tokens':None})).cache_write_tokens,0)
        self.assertEqual(FIXTURE.read_bytes(),before)
        self.apply()  # Verification is read-only and repeatable.

    def test_unexpected_sdk_version_is_rejected_before_import_or_patch(self):
        code=self.telemetry.normalize_usage.__code__
        with patch.object(launcher.importlib.metadata,'version',return_value='1.50.0'),patch.object(launcher.importlib,'import_module') as imports:
            with self.assertRaisesRegex(ValueError,'version mismatch'):
                launcher.verify_usage_compatibility()
        imports.assert_not_called()
        self.assertIs(self.telemetry.normalize_usage.__code__,code)

    def test_modified_reference_source_is_rejected_without_partial_patch(self):
        source=inspect.getsource(self.telemetry.normalize_usage)
        with self.assertRaisesRegex(ValueError,'source mismatch'):
            launcher.verified_usage_source(source+'\n')
        code=self.telemetry.normalize_usage.__code__
        with patch.object(launcher.importlib.metadata,'version',return_value='1.53.0'),patch.object(launcher.importlib,'import_module',return_value=self.telemetry),patch.object(launcher.inspect,'getsource',return_value=source.replace('cache_write = 0','cache_write = 8')):
            with self.assertRaisesRegex(ValueError,'source mismatch'):
                launcher.verify_usage_compatibility()
        self.assertIs(self.telemetry.normalize_usage.__code__,code)

    def test_runtime_probe_self_test_failure_never_launches_server_or_leaks_details(self):
        output=io.StringIO()
        with patch.object(launcher,'runtime_ready',return_value=True),patch.object(launcher,'verify_usage_compatibility',side_effect=ValueError('private payload')),patch.object(launcher.runpy,'run_module') as run,contextlib.redirect_stderr(output):
            self.assertEqual(launcher.main(),1)
        run.assert_not_called()
        self.assertNotIn('private payload',output.getvalue())
        self.assertIn('usage compatibility check failed',output.getvalue())


if __name__=='__main__':
    unittest.main()
