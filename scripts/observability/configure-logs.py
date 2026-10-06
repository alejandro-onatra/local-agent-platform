#!/usr/bin/env python3
"""Generate filelog mounts/config using selected container LogPath only."""
import json
from pathlib import Path
import re
root = Path(__file__).resolve().parents[2]
artifacts = root/'artifacts/observability'
# JSON config is the canonical source; no host YAML dependency is needed.
config = json.loads((root/'infra/observability/collector.json').read_text())
mounts = []
for service, resource in [('openhands','openhands'),('ollama','ollama'),('litellm','litellm-proxy')]:
    info = json.loads((artifacts/('inspect-'+service+'.json')).read_text())
    cid = info['Id']; log = Path(info['LogPath'])
    assert re.fullmatch(r'[a-f0-9]{64}', cid)
    assert info['Driver'] == 'json-file', 'Expected json-file logging'
    assert log.is_absolute() and log.name == cid+'-json.log' and log.parent.name == cid
    target = '/docker-logs/'+service
    mounts.append({'type':'bind','source':str(log.parent),'target':target,'read_only':True,'bind':{'create_host_path':False}})
    receiver = 'filelog/'+service
    config['receivers'][receiver] = {'include':[target+'/'+cid+'-json.log'], 'start_at':'end','storage':'file_storage','operators':[{'type':'add','field':'resource["service.name"]','value':resource}]}
    config['service']['pipelines']['logs']['receivers'].append(receiver)
config.setdefault('extensions', {})['file_storage'] = {'directory':'/var/lib/otel'}
config['service'].setdefault('extensions', []).append('file_storage')
mounts.append({'type':'volume','source':'collector-offsets','target':'/var/lib/otel'})
override = {'services':{'collector':{'user':'0:0','volumes':mounts}},'volumes':{'collector-offsets':{}}}
(artifacts/'collector-with-logs.json').write_text(json.dumps(config,indent=2)+'\n')
(artifacts/'logs-compose.json').write_text(json.dumps(override,indent=2)+'\n')
print('Generated narrow filelog mounts; no Docker socket.')
