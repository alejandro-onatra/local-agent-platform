#!/usr/local/bin/python
"""Launch the locked installed backend without PyInstaller temporary extraction."""
import hashlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import runpy
import sys

EXPECTED_VERSION = '1.53.0'
# Official v1.53.0 normalize_usage already includes upstream PR #5327.
USAGE_SOURCE_SHA256 = 'd67ed7d48ada7620a60246c09e63b01871bc440a426d9f6889236730c6265634'


def runtime_ready():
    try:
        return (importlib.metadata.version('openhands-agent-server') == EXPECTED_VERSION
                and importlib.util.find_spec('openhands.agent_server.__main__') is not None)
    except (ImportError, ValueError, importlib.metadata.PackageNotFoundError):
        return False


class UsageCompatibilityError(ValueError):
    """Fixed public diagnostic raised only by our compatibility guards."""


def verified_usage_source(source):
    """Require the locked upstream normalizer without rewriting it."""
    if hashlib.sha256(source.encode()).hexdigest() != USAGE_SOURCE_SHA256:
        raise UsageCompatibilityError('Locked usage normalizer source mismatch')


def verify_usage_compatibility():
    """Test native SDK/LiteLLM accounting without changing code or calling an LLM."""
    if importlib.metadata.version('openhands-sdk') != EXPECTED_VERSION:
        raise UsageCompatibilityError('Locked SDK version mismatch')
    telemetry = importlib.import_module('openhands.sdk.llm.utils.telemetry')
    verified_usage_source(inspect.getsource(telemetry.normalize_usage))
    for details, expected_write in [
        ({'cached_tokens': 3, 'cache_creation_tokens': None}, 0),
        ({'cached_tokens': 3}, 0),
        ({'cached_tokens': 3, 'cache_creation_tokens': 7}, 7),
    ]:
        usage = telemetry.Usage(prompt_tokens=100, completion_tokens=5,
                                prompt_tokens_details=details)
        result = telemetry.normalize_usage(usage)
        if (result.prompt_tokens, result.completion_tokens, result.cache_read_tokens,
                result.cache_write_tokens) != (100, 5, 3, expected_write):
            raise UsageCompatibilityError('Usage compatibility self-test failed')


def main():
    if not runtime_ready():
        print('Locked Python Agent Server module unavailable; no packages installed or permissions changed.', file=sys.stderr)
        return 1
    try:
        verify_usage_compatibility()
    except UsageCompatibilityError as exc:
        print(f'Locked SDK usage compatibility check failed: {exc}; backend not launched.', file=sys.stderr)
        return 1
    except Exception:
        print('Locked SDK usage compatibility check failed; backend not launched.', file=sys.stderr)
        return 1
    if sys.argv[1:] == ['--runtime-check']:
        print('Installed Python Agent Server 1.53.0 and native cache-usage compatibility verified; no runtime patch or extraction required.')
        return 0
    runpy.run_module('openhands.agent_server', run_name='__main__', alter_sys=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
