#!/usr/bin/env python3
"""Verify real streamed usage and its OTel counters; never print generated text."""
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def read_usage(response):
    usage = None
    finished = False
    for raw in response:
        line = raw.decode('utf-8').strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            finished = True
            break
        chunk = json.loads(payload)
        if 'error' in chunk:
            raise RuntimeError('Stream reported an error; provider message omitted.')
        if chunk.get('usage'):
            usage = chunk['usage']
    if not finished or usage is None:
        raise RuntimeError('Completed stream with usage was not received; do not infer zero tokens.')
    for name in ('prompt_tokens', 'completion_tokens'):
        if type(usage.get(name)) is not int or usage[name] <= 0:
            raise RuntimeError('Stream token usage missing or invalid.')
    return {name: usage[name] for name in ('prompt_tokens', 'completion_tokens')}


def counters():
    expr = 'sum by (gen_ai_token_type) (gen_ai_client_token_usage_sum{job="otel-collector",exported_job="litellm-proxy",gen_ai_request_model="qwen3:8b"})'
    url = 'http://prometheus:9090/api/v1/query?' + urllib.parse.urlencode({'query': expr})
    with urllib.request.urlopen(url, timeout=10) as response:
        result = json.load(response)
    if result.get('status') != 'success':
        raise RuntimeError('Prometheus counter query failed.')
    values = {}
    for row in result['data']['result']:
        value = float(row['value'][1])
        if not math.isfinite(value) or value < 0 :
            raise RuntimeError('Token counter is invalid.')
        values[row['metric']['gen_ai_token_type']] = value
    age_expr = 'max(time()-timestamp(gen_ai_client_token_usage_sum{job="otel-collector",exported_job="litellm-proxy",gen_ai_request_model="qwen3:8b"}))'
    age_url = 'http://prometheus:9090/api/v1/query?' + urllib.parse.urlencode({'query': age_expr})
    with urllib.request.urlopen(age_url, timeout=10) as response:
        ages = json.load(response)
    if ages.get('status') != 'success':
        raise RuntimeError('Counter freshness query failed.')
    if any(float(row['value'][1]) > 45 for row in ages['data']['result']):
        raise RuntimeError('Counter scrape is stale.')
    return values


def main():
    before = counters()
    body = {'model': 'qwen3:8b', 'messages': [{'role': 'user', 'content': 'Synthetic streaming diagnostic. Reply only with the number 2.'}],
            'max_tokens': 8, 'temperature': 0, 'stream': True,
            'stream_options': {'include_usage': True}}
    request = urllib.request.Request('http://litellm:4000/v1/chat/completions',
                  data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
                  'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']})
    with urllib.request.urlopen(request, timeout=180) as response:
        usage = read_usage(response)
    expected = {'input': usage['prompt_tokens'], 'output': usage['completion_tokens']}
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        after = counters()
        delta = {kind: after.get(kind, 0)-before.get(kind, 0) for kind in expected}
        if all(delta[kind] >= expected[kind] for kind in expected):
            print(json.dumps({'status': 'passed', 'stream_usage': usage,
                              'observed_counter_increase': delta,
                              'scope': 'One new synthetic streamed proxy call; concurrent calls may add usage.'}, indent=2))
            return
        time.sleep(2)
    raise RuntimeError('Stream completed but its input/output counters did not increase; inspect the OTel callback.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            detail += ' HTTP ' + str(exc.code)
        print(json.dumps({'status': 'failed', 'stage': detail}))
        raise SystemExit(1)
