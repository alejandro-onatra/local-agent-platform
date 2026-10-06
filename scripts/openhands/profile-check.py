#!/usr/bin/env python3
"""Print only selected diagnostic fields, never credentials or conversations."""
import json
from pathlib import Path
import urllib.request
import urllib.error

key_file = Path('/home/openhands/.openhands/agent-canvas/api-key.txt')
if not key_file.is_file():
    raise SystemExit('Persisted session key missing; no secret values displayed.')
key = key_file.read_text().strip()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    req = urllib.request.Request('http://127.0.0.1:18000'+path,
                                 headers={'X-Session-API-Key': key})
    try:
        with opener.open(req, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'Diagnostic API unavailable: HTTP {exc.code}; body omitted.')
    except (urllib.error.URLError, TimeoutError):
        raise SystemExit('Diagnostic API unreachable; no credential values displayed.')

settings = get('/api/settings')
agent = settings.get('agent_settings') or {}
llm = agent.get('llm') or {}
allowed = ('model', 'base_url', 'max_input_tokens', 'max_output_tokens',
           'temperature', 'reasoning_effort', 'extended_thinking',
           'force_enable_function_calling', 'disable_stop_word')
summary = {'active_profile': settings.get('active_profile'),
           'llm': {k: llm[k] for k in allowed if k in llm},
           'agent_type': agent.get('kind'),
           'tools_explicitly_configured': agent.get('tools') is not None,
           'tool_names': [t.get('name', t.get('kind', 'unknown'))
                          for t in (agent.get('tools') or []) if isinstance(t, dict)]}
# Some builds place extra request parameters in this field; print only thinking.
extra = llm.get('extra_body') or {}
if isinstance(extra, dict) and 'think' in extra:
    summary['think'] = extra['think'] if isinstance(extra['think'], (bool, type(None))) else 'configured'
print(json.dumps(summary, indent=2))
print('RESULT: persisted defaults inspected; null tools can mean inherited defaults.\nAn existing conversation may use its own settings; this is not its effective tool list.')
