#!/usr/bin/env python3
"""Inspect one conversation's route and numeric usage; never print its content."""
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID


def summarize(data):
    llm = (data.get('agent') or {}).get('llm') or {}
    url = urllib.parse.urlsplit(llm.get('base_url') or '')
    route = {'ollama': 'direct Ollama', 'litellm': 'LiteLLM proxy'}.get(url.hostname, 'other or unset (address hidden)')
    metrics = (data.get('stats') or {}).get('usage_to_metrics') or {}
    keys = ('prompt_tokens', 'completion_tokens', 'cache_read_tokens', 'cache_write_tokens')
    total = dict.fromkeys(keys, 0)
    snapshots = []
    for metric in metrics.values():
        usage = metric.get('accumulated_token_usage') or {}
        numbers = {k: usage[k] for k in keys if type(usage.get(k)) is int and usage[k] >= 0}
        for k, v in numbers.items():
            total[k] += v
        snapshots.append(numbers)
    result = {'current_route': route, 'model': llm.get('model'),
              'metrics_snapshots': snapshots, 'combined_usage': total,
              'total_tokens': total['prompt_tokens'] + total['completion_tokens']}
    if total['cache_read_tokens'] <= total['prompt_tokens']:
        result['input_without_cache_reads'] = total['prompt_tokens'] - total['cache_read_tokens']
    result['scope'] = 'Conversation lifetime; current route does not prove past routes.'
    return result


def main():
    identifier = str(UUID(sys.argv[1]))
    key = Path('/home/openhands/.openhands/agent-canvas/api-key.txt').read_text().strip()
    request = urllib.request.Request('http://127.0.0.1:18000/api/conversations/' + identifier,
                                    headers={'X-Session-API-Key': key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'Conversation inspection failed: HTTP {exc.code}; response omitted.') from None
    except (urllib.error.URLError, TimeoutError):
        raise SystemExit('Conversation API unreachable; no credential values displayed.') from None
    print(json.dumps(summarize(data), indent=2))


if __name__ == '__main__':
    main()
