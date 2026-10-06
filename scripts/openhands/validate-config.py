#!/usr/bin/env python3
"""Reject dangerous or inconsistent deployment configuration before startup."""
import json
from pathlib import Path
import sys
r = Path(__file__).resolve().parents[2]
c = json.load(sys.stdin)
s = c['services']['openhands']
lock = json.loads((r/'infra/openhands/versions.json').read_text())
assert s['image'] == lock['image'], 'Image differs from lock'
assert s['platform'] == 'linux/amd64'
assert set(s['networks']) == {'agent-link'}, 'Agent must use internal network only'
assert c['networks']['agent-link']['internal'] is True
assert not s.get('ports'), 'Internal agent must not publish ports'
proxy = c['services']['openhands-proxy']
assert proxy['image'] == lock['proxy']['image']
assert proxy['user'] == '101:101' and proxy['read_only'] is True
assert set(proxy['networks']) == {'default', 'agent-link'}
assert len(proxy['ports']) == 1
port = proxy['ports'][0]
assert port['host_ip'] == '127.0.0.1' and port['target'] == 8080 and str(port['published']) == '8000'
assert not proxy.get('privileged') and proxy.get('network_mode') != 'host'
assert len(proxy['volumes']) == 1
assert proxy['volumes'][0]['read_only'] is True
assert Path(proxy['volumes'][0]['source']) == r/'infra/openhands/nginx.conf'
assert not s.get('privileged') and s.get('network_mode') != 'host'
assert s['environment']['OH_TELEMETRY_EXPORTER'] == 'none'
assert s['environment']['OH_WORKSPACE_PATH'] == '/projects/demo'
volumes = s['volumes']
assert {v['target'] for v in volumes} == {'/projects', '/home/openhands/.openhands'}
workspace = next(v for v in volumes if v['target'] == '/projects')
assert workspace['type'] == 'bind'
assert Path(workspace['source']) == r/'artifacts/openhands/projects'
assert set(c['services']['ollama']['networks']) == {'default', 'agent-link'}
assert c['services']['ollama']['image'] == json.loads((r/'infra/llm/versions.json').read_text())['ollama']['image']
print('OpenHands image, loopback port, mounts and internal network verified.')
