#!/usr/local/bin/python
"""Launch the locked installed backend without PyInstaller temporary extraction."""
import hashlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import runpy
import sys

# Both locked releases use the same upstream normalize_usage implementation.
USAGE_SOURCE_SHA256_BY_VERSION = {
    '1.53.0': 'd67ed7d48ada7620a60246c09e63b01871bc440a426d9f6889236730c6265634',
    '1.58.1': 'd67ed7d48ada7620a60246c09e63b01871bc440a426d9f6889236730c6265634',
}


def installed_agent_server_version():
    try:
        return importlib.metadata.version('openhands-agent-server')
    except (ImportError, ValueError, importlib.metadata.PackageNotFoundError):
        return None


def runtime_ready():
    try:
        return (installed_agent_server_version() in USAGE_SOURCE_SHA256_BY_VERSION
                and importlib.util.find_spec('openhands.agent_server.__main__') is not None)
    except (ImportError, ValueError, importlib.metadata.PackageNotFoundError):
        return False


class UsageCompatibilityError(ValueError):
    """Fixed public diagnostic raised only by our compatibility guards."""


def verified_usage_source(source, version):
    """Require the locked upstream normalizer without rewriting it."""
    expected = USAGE_SOURCE_SHA256_BY_VERSION.get(version)
    if expected is None or hashlib.sha256(source.encode()).hexdigest() != expected:
        raise UsageCompatibilityError('Locked usage normalizer source mismatch')


def verify_usage_compatibility():
    """Test native SDK/LiteLLM accounting without changing code or calling an LLM."""
    server_version = importlib.metadata.version('openhands-agent-server')
    sdk_version = importlib.metadata.version('openhands-sdk')
    if server_version != sdk_version or sdk_version not in USAGE_SOURCE_SHA256_BY_VERSION:
        raise UsageCompatibilityError('Locked Agent Server/SDK version mismatch')
    telemetry = importlib.import_module('openhands.sdk.llm.utils.telemetry')
    verified_usage_source(inspect.getsource(telemetry.normalize_usage), sdk_version)
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
        print(f'Installed Python Agent Server {installed_agent_server_version()} and native cache-usage compatibility verified; no runtime patch or extraction required.')
        return 0
    runpy.run_module('openhands.agent_server', run_name='__main__', alter_sys=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
