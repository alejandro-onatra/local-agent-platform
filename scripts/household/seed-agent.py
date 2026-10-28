"""Inside one household agent: bootstrap model defaults without exporting keys."""
import json,re,time,urllib.request,urllib.error
from pathlib import Path
key=None
stage='native_key'

def wait_for_key(path,deadline):
    while True:
        try:
            value=path.read_text().strip()
            if re.fullmatch(r'[a-f0-9]{64}',value):return value
        except FileNotFoundError:pass
        if time.monotonic()>=deadline:raise TimeoutError('native_key_not_ready')
        time.sleep(1)
class DiscoveryError(ValueError):pass

def discover_model(opener,deadline):
    while True:
        category='other'
        try:
            with opener.open('http://model-relay:8080/v1/models',timeout=5) as response:
                try:models=json.load(response)
                except (ValueError,UnicodeError):raise DiscoveryError('invalid_json') from None
            if not isinstance(models,dict) or not isinstance(models.get('data'),list):raise DiscoveryError('invalid_schema')
            if not any(isinstance(item,dict) and item.get('id')=='qwen3:8b' for item in models['data']):raise DiscoveryError('model_not_listed')
            return
        except urllib.error.HTTPError as error:
            code=error.code;error.close()
            category='http_5xx' if 500<=code<600 else 'http_4xx'
            if code not in (502,503,504):raise DiscoveryError(category) from None
        except (OSError,urllib.error.URLError):category='network_unavailable'
        if time.monotonic()>=deadline:raise DiscoveryError(category)
        time.sleep(1)

opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api(path,body=None,method=None):
    request=urllib.request.Request('http://127.0.0.1:18000/api/'+path,
        data=None if body is None else json.dumps(body).encode(),method=method,
        headers={'X-Session-API-Key':key,'Content-Type':'application/json'})
    with opener.open(request,timeout=15) as response:return json.load(response)
try:
    deadline=time.monotonic()+180
    key=wait_for_key(Path('/home/openhands/.openhands/agent-canvas/api-key.txt'),deadline)
    stage='backend'
    while True:
        try:api('settings');break
        except (OSError,urllib.error.URLError):
            if time.monotonic()>=deadline:raise
            time.sleep(2)
    stage='model_discovery'
    discover_model(opener,time.monotonic()+30)
    marker=Path('/home/openhands/.openhands/household-model-bootstrap')
    if not marker.exists():
        llm={'model':'openai/qwen3:8b','base_url':'http://model-relay:8080/v1','api_key':'local-only',
             'temperature':0.2,'max_input_tokens':24000,'max_output_tokens':4096,'stream':True,'reasoning_effort':'none'}
        stage='profile_create'
        api('profiles/local-qwen3-8b',{'llm':llm,'include_secrets':True})
        stage='profile_activate'
        api('profiles/local-qwen3-8b/activate',{})
    stage='settings_readback'
    settings=api('settings')
    assert settings.get('agent_settings',{}).get('llm',{}).get('model')
    if not marker.exists():
        stage='marker_write'
        marker.write_text('Initial local model configured; later user settings are preserved.\n');marker.chmod(0o600)
    print(json.dumps({'status':'passed','native_backend':'passed','model_relay':'passed','profile_seeded':True}))
except Exception as error:
    category=str(error) if isinstance(error,DiscoveryError) else 'other'
    print(json.dumps({'status':'failed','stage':stage,'category':category,'error':'household_agent_seed_failed_details_withheld'}))
    # The parent validates semantic status, retaining this fixed stage without raw exception text.
