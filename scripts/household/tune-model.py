"""Inside one verified household container: repair only the managed local Qwen profile."""
import json,re,urllib.request
from pathlib import Path
PROFILE='local-qwen3-8b'

def tune(api):
    detail=api('/api/profiles/'+PROFILE)
    config=dict(detail['config'])
    if config.get('model')!='openai/qwen3:8b' or config.get('base_url')!='http://model-relay:8080/v1':
        raise ValueError('managed_profile_changed')
    settings=api('/api/settings')
    extra=dict(config.get('extra_body') or {})
    needs_change=config.get('reasoning_effort')!='none' or 'think' in extra
    if needs_change:
        # Backend-only loopback read: retain the current key in memory, never report it.
        config=dict(api('/api/profiles/'+PROFILE,expose=True)['config'])
        if config.get('model')!='openai/qwen3:8b' or config.get('base_url')!='http://model-relay:8080/v1':
            raise ValueError('managed_profile_changed')
        extra=dict(config.get('extra_body') or {});extra.pop('think',None)
        config.update(reasoning_effort='none',extra_body=extra)
        api('/api/profiles/'+PROFILE,{'llm':config,'include_secrets':True})
    active=settings.get('active_profile')==PROFILE
    if active:
        api('/api/profiles/'+PROFILE+'/activate',{})
    readback=api('/api/profiles/'+PROFILE)['config']
    if readback.get('reasoning_effort')!='none' or 'think' in (readback.get('extra_body') or {}):
        raise ValueError('profile_readback_failed')
    if active and api('/api/settings')['agent_settings']['llm'].get('reasoning_effort')!='none':
        raise ValueError('active_settings_readback_failed')
    return {'status':'passed','profile_changed':needs_change,'active_defaults_updated':active,
        'reasoning_effort':'none','scope':'Managed local Qwen profile and active defaults only; existing conversations unchanged'}

def main():
    key=Path('/home/openhands/.openhands/agent-canvas/api-key.txt').read_text().strip()
    if not re.fullmatch(r'[a-f0-9]{64}',key):raise ValueError('native_key_unavailable')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path,body=None,expose=False):
        headers={'X-Session-API-Key':key,'Content-Type':'application/json'}
        if expose:headers['X-Expose-Secrets']='plaintext'
        request=urllib.request.Request('http://127.0.0.1:18000'+path,
            data=None if body is None else json.dumps(body).encode(),headers=headers)
        with opener.open(request,timeout=15) as response:return json.load(response)
    return tune(api)

if __name__=='__main__':
    try:result=main()
    except Exception:result={'status':'failed','error':'managed_model_tuning_failed_details_withheld'}
    print(json.dumps(result));raise SystemExit(result['status']!='passed')
