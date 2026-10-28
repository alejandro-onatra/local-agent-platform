#!/usr/bin/env python3
"""Check the authenticated backend and proxy without exporting credentials/content."""
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

KEY_FILE = Path('/home/openhands/.openhands/agent-canvas/api-key.txt')
ROUTES = {
    'agent_server': 'http://127.0.0.1:18000/api/settings',
    'canvas_proxy': 'http://127.0.0.1:8000/api/settings',
}


def probe(opener, key, url):
    request = urllib.request.Request(url, headers={'X-Session-API-Key': key})
    try:
        with opener.open(request, timeout=2) as response:
            # Do not read or print settings, which may contain credentials.
            if response.status == 200 and response.headers.get_content_type() == 'application/json':
                return 'passed'
            return 'unexpected_response'
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in (401, 403):
            return 'authentication_rejected'
        if exc.code == 502:
            return 'upstream_unavailable'
        return 'http_error'
    except (urllib.error.URLError, TimeoutError, OSError):
        return 'unreachable'


def check(key_file=KEY_FILE, opener=None, attempts=15, pause=2, sleep=time.sleep):
    try:
        key = key_file.read_text().strip()
    except OSError:
        return {'status': 'failed', 'error': 'session_key_unavailable'}
    if not key:
        return {'status': 'failed', 'error': 'session_key_unavailable'}
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(attempts):
        checks = {name: probe(opener, key, url) for name, url in ROUTES.items()}
        if all(result == 'passed' for result in checks.values()):
            return {'status': 'passed', 'checks': checks}
        if 'authentication_rejected' in checks.values() or attempt == attempts - 1:
            return {'status': 'failed', 'checks': checks}
        sleep(pause)
    return {'status': 'failed', 'error': 'invalid_attempt_count'}


READONLY_LOCATIONS = (
    ('/home/openhands/.openhands', 'persistent_state'),
    ('/home/openhands/.cache', 'temporary_cache'),
    ('/home/openhands/workspace', 'temporary_workspace'),
    ('/home/openhands/.local', 'unmounted_home_local'),
    ('/home/openhands/.config', 'unmounted_home_config'),
    ('/home/openhands', 'other_home_path'),
    ('/usr/local', 'image_python_runtime'),
    ('/opt', 'image_application'),
    ('/agent-server', 'image_backend_source'),
    ('/workspace', 'image_workspace'),
    ('/projects', 'mounted_projects'),
    ('/tmp', 'temporary_files'),
)


def readonly_locations(text):
    # Only classify paths following an EROFS marker, not traceback frame paths.
    # JSON stacktraces can contain escaped quotes; strip escaping for matching,
    # but never return the source text or any individual pathname.
    normalized = text.replace('\\"', '"').replace('\\\\', '\\')
    pattern = r"(?:\[errno 30\]|read-only file system)[^\n]*?['\"](/[^'\"\n]+)['\"]"
    found = set()
    for match in re.finditer(pattern, normalized, re.IGNORECASE):
        path = match.group(1)
        category = next((category for prefix, category in READONLY_LOCATIONS
                         if path == prefix or path.startswith(prefix + '/')), 'other_or_unknown')
        found.add(category)
    if ('read-only file system' in text.lower() or '[errno 30]' in text.lower()) and not found:
        found.add('other_or_unknown')
    return sorted(found)


def summarize_logs(stream):
    # Fixed categories only: never emit matched lines, paths, keys or prompts.
    raw = stream.read(2 * 1024 * 1024)
    text = raw.lower()
    indicators = {
        'cache_usage_attribute_error': (
            'prompttokensdetailswrapper' in text and
            'has no attribute' in text and 'cache_creation_tokens' in text),
        'readonly_filesystem': 'read-only file system' in text or '[errno 30]' in text,
        'permission_denied': 'permissionerror' in text or '[errno 13]' in text,
        'storage_full': 'no space left on device' in text or '[errno 28]' in text,
        'python_traceback': 'traceback (most recent call last)' in text,
        'startup_failed': 'application startup failed' in text,
        'backend_startup_timeout': 'agent server on port 18000 did not become ready' in text,
        'memory_error': 'memoryerror' in text,
        'pyinstaller_loader_error': '[pyi-' in text and 'error' in text,
        'binary_extraction_failed': 'failed to extract' in text or 'could not extract' in text,
        'library_mapping_denied': ('failed to map segment' in text or
                                   'failed to load python shared library' in text),
    }
    return {'log_indicators': indicators,
            'readonly_path_categories': readonly_locations(raw),
            'scope': 'Recent container logs; indicators are not a confirmed root cause. Raw text omitted.'}


if __name__ == '__main__':
    if sys.argv[1:] == ['--logs']:
        print(json.dumps(summarize_logs(sys.stdin), indent=2))
    elif not sys.argv[1:]:
        report = check()
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report['status'] == 'passed' else 1)
    else:
        raise SystemExit('Use no arguments for health or --logs for sanitized log indicators.')
