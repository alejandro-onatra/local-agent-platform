#!/usr/bin/env python3
"""Test authenticated native-cache scraping and privacy with the pinned Collector."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def values(text, name):
    return [float(line.split()[-1]) for line in text.splitlines()
            if line.startswith(name+'{') or line.startswith(name+' ')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--collector', required=True)
    args = parser.parse_args()
    token = 'synthetic-'+secrets.token_hex(16)
    marker = 'SENSITIVE_CACHE_CANARY_'+secrets.token_hex(8)
    state = {'read': None, 'write': None, 'fail': False, 'authenticated': 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Authorization') != 'Bearer '+token:
                self.send_response(401); self.end_headers(); return
            state['authenticated'] += 1
            if state['fail']:
                self.send_response(503); self.end_headers(); return
            lines = []
            for kind, key in [('cached', 'read'), ('cache_creation', 'write')]:
                name = 'litellm_input_'+kind+'_tokens_metric'
                lines.append('# TYPE '+name+' counter')
                if state[key] is not None:
                    lines.append(name+'_total{model="openai/qwen3:8b",hashed_api_key="'+marker+'",user="'+marker+'"} '+str(state[key]))
                    lines.append(name+'_total{model="'+marker+'",user="'+marker+'"} 9999')
            lines.extend(['# TYPE litellm_spend_metric counter', 'litellm_spend_metric_total{user="'+marker+'"} 9999'])
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(('\n'.join(lines)+'\n').encode())
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='agent-cache-test-') as directory:
            temp = Path(directory)
            config = json.loads((ROOT/'infra/observability/collector.json').read_text())
            prom = port()
            config['receivers']['otlp']['protocols'] = {'http': {'endpoint': f'127.0.0.1:{port()}'}}
            config['extensions']['health_check']['endpoint'] = f'127.0.0.1:{port()}'
            config['service']['telemetry']['metrics']['readers'][0]['pull']['exporter']['prometheus'].update(host='127.0.0.1', port=port())
            scrape = config['receivers']['prometheus/litellm-cache']['config']['scrape_configs'][0]
            scrape['static_configs'][0]['targets'] = [f'127.0.0.1:{server.server_port}']
            scrape['scrape_interval'] = '200ms'
            scrape['scrape_timeout'] = '150ms'
            config['processors']['batch']['timeout'] = '100ms'
            config['exporters'] = {'prometheus': {'endpoint': f'127.0.0.1:{prom}', 'add_metric_suffixes': False}, 'file/metrics': {'path': str(temp/'metrics.json')}}
            config['service']['pipelines'] = {'metrics/cache': config['service']['pipelines']['metrics/cache']}
            config['service']['pipelines']['metrics/cache']['exporters'].append('file/metrics')
            config['connectors'] = {}
            file = temp/'config.json'
            file.write_text(json.dumps(config))
            with (temp/'collector.log').open('w') as log:
                process = subprocess.Popen([args.collector, '--config='+str(file)], stdout=log, stderr=log, env={**os.environ, 'LITELLM_MASTER_KEY': token})
                try:
                    def wait(name, expected):
                        text = ''
                        for _ in range(70):
                            if process.poll() is not None:
                                raise RuntimeError((temp/'collector.log').read_text().replace(token, '[redacted]'))
                            try:
                                text = urllib.request.urlopen(f'http://127.0.0.1:{prom}/metrics', timeout=5).read().decode()
                                if values(text, name) == expected:
                                    return text
                            except OSError:
                                pass
                            time.sleep(0.1)
                        raise AssertionError(name+' did not match: '+str(values(text, name)))
                    text = wait('litellm_cache_scrape_up', [1])
                    assert not values(text, 'litellm_input_cached_tokens_metric_total'), 'Missing cache was fabricated as zero'
                    for multiplier in (1, 2):
                        state.update(read=70*multiplier, write=5*multiplier)
                        text = wait('litellm_input_cached_tokens_metric_total', [70*multiplier])
                        wait('litellm_input_cache_creation_tokens_metric_total', [5*multiplier])
                        assert 'gen_ai_request_model="qwen3:8b"' in text
                        assert marker not in text and token not in text
                        assert 'litellm_spend_metric' not in text
                    state['fail'] = True
                    wait('litellm_cache_scrape_up', [0])
                    assert state['authenticated'] > 0
                finally:
                    process.terminate(); process.wait(timeout=10)
            exported = (temp/'metrics.json').read_text()
            assert marker not in exported and token not in exported
            print('PASS: authenticated cache scrape preserved cumulative values 70→140 and 5→10, normalized model, removed private labels/unselected metrics, and exposed HTTP failure as scrape=0.')
            print('PASS: missing cache stayed absent rather than fabricated as zero; repeated scrapes did not add the cumulative counter again.')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
