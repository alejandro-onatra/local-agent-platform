#!/usr/bin/env python3
"""Apply a saved proxy profile to one idle conversation; omit secrets/content."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID, uuid4

API = 'http://127.0.0.1:18000'
PROXY = 'http://litellm:4000'


def profile_llm(profile):
    config = dict(profile.get('config') or {})
    if config.get('base_url') != PROXY + '/v1':
        raise RuntimeError('Saved profile must point exactly to the local LiteLLM /v1 endpoint.')
    if config.get('model') != 'openai/qwen3:8b':
        raise RuntimeError('Saved profile does not match the locked local model.')
    key = config.get('api_key')
    if not profile.get('api_key_set') or not isinstance(key, str) or not re.fullmatch(r'sk-[a-f0-9]{64}', key):
        raise RuntimeError('Saved profile needs the existing local proxy credential; no value displayed.')
    # SDK 1.49.6 reuses a registry entry if usage_id already exists.
    config.update(stream=True, usage_id='proxy-route:' + str(uuid4()))
    return config


def ensure_idle(conversation):
    if conversation.get('execution_status') not in {'idle', 'paused', 'finished', 'error', 'stuck'}:
        raise RuntimeError('Wait for the agent to finish or pause it before switching the route.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('conversation_id', type=UUID)
    parser.add_argument('--profile', default='local-qwen3-8b')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', args.profile):
        raise RuntimeError('Invalid saved profile name.')
    if importlib.metadata.version('openhands-agent-server') != '1.49.6':
        raise RuntimeError('This repair is validated for the locked agent-server 1.49.6.')
    key = Path('/home/openhands/.openhands/agent-canvas/api-key.txt').read_text().strip()
    # Requests stay inside this container. Never follow redirects with credentials.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def api(path, body=None, expose=False):
        headers = {'X-Session-API-Key': key, 'Content-Type': 'application/json'}
        if expose:
            # Backend-only loopback request; credential stays in memory, never stdout.
            headers['X-Expose-Secrets'] = 'plaintext'
        request = urllib.request.Request(API + path, headers=headers,
                    data=None if body is None else json.dumps(body).encode())
        with opener.open(request, timeout=20) as response:
            return json.load(response)

    path = '/api/conversations/' + str(args.conversation_id)
    before = api(path)
    ensure_idle(before)
    profile_path = '/api/profiles/' + urllib.parse.quote(args.profile, safe='')
    llm = profile_llm(api(profile_path, expose=True))
    # Verify authentication before changing any settings; discard the model list.
    request = urllib.request.Request(PROXY + '/v1/models',
                                    headers={'Authorization': 'Bearer ' + llm['api_key']})
    with opener.open(request, timeout=15) as response:
        json.load(response)
    previous_url = ((before.get('agent') or {}).get('llm') or {}).get('base_url')
    if previous_url != PROXY + '/v1':
        api(path + '/switch_llm', {'llm': llm})
    after = api(path)
    actual = (after.get('agent') or {}).get('llm') or {}
    if actual.get('base_url') != PROXY + '/v1' or actual.get('model') != llm['model']:
        raise RuntimeError('Conversation route verification failed; no configuration dump displayed.')
    # Activation updates defaults for future conversations as well.
    api(profile_path + '/activate', {})
    settings = api('/api/settings')
    default = ((settings.get('agent_settings') or {}).get('llm') or {})
    if default.get('base_url') != PROXY + '/v1':
        raise RuntimeError('Conversation repaired, but future-conversation default failed verification.')
    print(json.dumps({'status': 'passed', 'current_route': 'LiteLLM proxy',
                     'default_route': 'LiteLLM proxy', 'stream': actual.get('stream'),
                     'changed_conversation_route': previous_url != PROXY + '/v1',
                     'scope': 'Future calls only. Existing usage is retained, not backfilled into Prometheus.'}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # API error bodies can contain credentials; never print them or tracebacks.
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            detail += ' HTTP ' + str(exc.code)
        print(json.dumps({'status': 'failed', 'stage': detail}))
        raise SystemExit(1)
