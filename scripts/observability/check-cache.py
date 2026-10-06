#!/usr/bin/env python3
"""Compare real Ollama cache usage through LiteLLM with native exported counters."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def request(url, data=None, auth=False):
    headers = {'Content-Type': 'application/json'}
    if auth:
        if urllib.parse.urlsplit(url).hostname != 'litellm':
            raise ValueError('Credential may only be sent to LiteLLM')
        headers['Authorization'] = 'Bearer '+os.environ['LITELLM_MASTER_KEY']
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=180 if data else 10) as response:
        return json.load(response)


def query(expr):
    result = request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query': expr}))
    return result['data']['result']


def counter():
    rows = query('sum(litellm_input_cached_tokens_metric_total{job="otel-collector",exported_job="litellm-proxy",gen_ai_request_model="qwen3:8b"})')
    return float(rows[0]['value'][1]) if rows else 0


def main():
    # Authenticate /metrics; no metrics body, credentials or model text is printed.
    req = urllib.request.Request('http://litellm:4000/metrics/', headers={'Authorization': 'Bearer '+os.environ['LITELLM_MASTER_KEY']})
    with urllib.request.urlopen(req, timeout=10) as response:
        response.read()
    try:
        urllib.request.urlopen('http://litellm:4000/metrics/', timeout=10)
    except urllib.error.HTTPError as exc:
        assert exc.code in (401, 403), 'Unexpected metrics auth failure'
    else:
        raise RuntimeError('Metrics endpoint accepted an unauthenticated request')
    before = counter()
    prompt = 'Synthetic cache diagnostic. '+('A stable shared prefix explains a simple arithmetic exercise. '*160)+' Reply only with the number 2.'
    body = {'model': 'qwen3:8b', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 8, 'temperature': 0, 'stream': False}
    usages = []
    for _ in range(2):
        response = request('http://litellm:4000/v1/chat/completions', body, auth=True)
        usage = response.get('usage') or {}
        cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        if type(cached) is not int or cached < 0:
            raise RuntimeError('Provider cache field missing or invalid; do not infer zero')
        usages.append({'input_tokens': usage.get('prompt_tokens'), 'cached_input_tokens': cached,
                       'output_tokens': usage.get('completion_tokens')})
    expected = sum(x['cached_input_tokens'] for x in usages)
    assert expected > 0, 'Neither test call reported positive cache reuse'
    for _ in range(60):
        rows = query('min(litellm_cache_scrape_up{job="otel-collector",exported_job="litellm-proxy"})')
        after = counter()
        if rows and float(rows[0]['value'][1]) == 1 and after-before >= expected:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Native cache counter failed to reflect provider usage; check callback and authenticated scrape')
    print(json.dumps({'status': 'passed', 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      'synthetic_calls': usages, 'reported_cached_tokens': expected,
                      'observed_counter_increase': after-before, 'metrics_auth_verified': True,
                      'scope': 'New synthetic calls via proxy; concurrent calls may add usage; no historical conversation imported.'}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            detail += ' HTTP '+str(exc.code)
        print(json.dumps({'status': 'failed', 'stage': detail}))
        raise SystemExit(1)
