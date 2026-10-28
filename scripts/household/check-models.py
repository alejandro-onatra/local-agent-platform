"""Run inside a household instance: fixed API/model diagnostics, never credentials."""
import json,re,urllib.request,urllib.error
from pathlib import Path

EXPECTED_MODEL='openai/qwen3:8b'
EXPECTED_BASE='http://model-relay:8080/v1'

def check_backend(api):
    result={}
    for label,path in [('settings','/api/settings'),('server_info','/server_info')]:
        try:
            data=api(path)
            if not isinstance(data,dict):raise ValueError()
            if label=='settings':
                agent=data.get('agent_settings') or {};llm=agent.get('llm') or {}
                result[label]={'status':'passed','qwen_selected':llm.get('model')==EXPECTED_MODEL,
                    'model_relay_selected':llm.get('base_url')==EXPECTED_BASE,
                    'llm_key_configured':data.get('llm_api_key_is_set') is True,
                    'qwen_profile_active':data.get('active_profile')=='local-qwen3-8b'}
            else:
                version=data.get('version') or data.get('sdk_version')
                result[label]={'status':'passed' if isinstance(version,str) and bool(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.]+)?',version)) else 'invalid_version_schema'}
        except urllib.error.HTTPError as e:
            result[label]={'status':'failed','http_status':e.code if e.code in (400,401,403,404,405,422,429,500,502,503,504) else 'other','category':'http_4xx' if 400<=e.code<500 else 'http_5xx'};e.close()
        except (ValueError,TypeError,AttributeError):result[label]={'status':'failed','category':'invalid_schema'}
        except Exception:result[label]={'status':'failed','category':'unavailable'}
    return result

def profile_checks(api):
    result={}
    try:
        data=api('/api/profiles/local-qwen3-8b');llm=data.get('config') or {}
        result['qwen_profile']={'status':'passed','model_matches':llm.get('model')==EXPECTED_MODEL,
            'relay_matches':llm.get('base_url')==EXPECTED_BASE,'key_configured':data.get('api_key_set') is True}
    except Exception:result['qwen_profile']={'status':'unavailable'}
    try:
        data=api('/api/agent-profiles/default');profile=data.get('profile') or {}
        result['default_agent']={'status':'passed','references_qwen':profile.get('llm_profile_ref')=='local-qwen3-8b'}
    except Exception:result['default_agent']={'status':'unavailable'}
    return result

def main():
    try:
        key=Path('/home/openhands/.openhands/agent-canvas/api-key.txt').read_text().strip()
        if not re.fullmatch(r'[a-f0-9]{64}',key):raise ValueError()
    except Exception:return {'status':'collected','native_key':'unavailable'}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api_at(port):
        def api(path):
            request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,headers={'X-Session-API-Key':key})
            with opener.open(request,timeout=8) as response:return json.loads(response.read(2097152))
        return api
    backend=api_at(18000)
    result={'status':'collected','native_key':'available','agent_server':check_backend(backend),
            'canvas_proxy':check_backend(api_at(8000)),**profile_checks(backend)}
    try:
        with opener.open('http://model-relay:8080/v1/models',timeout=8) as response:data=json.loads(response.read(2097152))
        result['relay_model_discovery']='passed' if any(m.get('id')=='qwen3:8b' for m in data.get('data',[]) if isinstance(m,dict)) else 'qwen_missing'
    except Exception:result['relay_model_discovery']='unavailable'
    result['scope']='Local authenticated API reads only; no browser-cookie test, writes, generation or secret export'
    return result

if __name__=='__main__':print(json.dumps(main()))
