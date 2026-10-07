#!/usr/bin/env python3
"""Validate published ports, exact images and network/mount boundaries."""
import json
import yaml
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
config = json.load(sys.stdin)
locks = yaml.safe_load((root/'infra/observability/versions.yaml').read_text())['components']
assert config['name'] == 'agent-platform-observability'
assert config['networks']['data']['internal'] is True
for name, service in config['services'].items():
    assert service['image'] == locks[name]['image'], name
    assert service['platform'] == 'linux/amd64'
    assert not service.get('privileged') and service.get('network_mode') != 'host'
    assert service['cap_drop'] == ['ALL']
    assert 'no-new-privileges:true' in service['security_opt']
    assert not service.get('ports') or name == 'grafana'
    for mount in service.get('volumes', []):
        assert 'docker.sock' not in mount.get('source', '')
        if mount['type'] == 'bind':
            assert mount['read_only'], (name, mount)
ports = config['services']['grafana']['ports']
assert len(ports) == 1 and ports[0]['host_ip'] == '127.0.0.1'
assert str(ports[0]['published']) == '3000'
assert set(config['services']['litellm']['networks']) == {'data', 'agent-link'}
assert set(config['services']['collector']['networks']) == {'data'}
assert config['services']['litellm']['environment']['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] == 'NO_CONTENT'

assert config['services']['collector']['environment']['LITELLM_MASTER_KEY']
assert config['services']['litellm']['environment']['LITELLM_MASTER_KEY']
assert 'LITELLM_DANGEROUSLY_PERMIT_WEAK_OR_UNSET_MASTER_KEY' not in config['services']['litellm']['environment']
assert set(config['services']['blackbox']['networks']) == {'data', 'agent-link'}
assert config['services']['blackbox']['user'] == '65534:65534'
print('Seven pinned images, internal backends, loopback Grafana and read-only config mounts verified.')
