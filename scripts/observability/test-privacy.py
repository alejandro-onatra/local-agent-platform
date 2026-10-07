#!/usr/bin/env python3
"""Run the pinned Collector locally with file exporters and a synthetic log."""
import argparse
import importlib.util
import json
import yaml
from pathlib import Path
import socket
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('checks', root/'scripts/observability/check-stack.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--collector',required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='agent-otel-test-') as temp:
        temp = Path(temp)
        (temp/'file').mkdir()
        config = yaml.safe_load((root/'infra/observability/collector.yaml').read_text())
        port, metric_port = free_port(), free_port()
        config['extensions']['health_check']['endpoint'] = '127.0.0.1:'+str(free_port())
        config['service']['telemetry']['metrics']['readers'][0]['pull']['exporter']['prometheus'].update(host='127.0.0.1', port=free_port())
        config['connectors']['spanmetrics']['metrics_flush_interval'] = '1s'
        config['receivers']['otlp']['protocols'] = {'http':{'endpoint':'127.0.0.1:'+str(port)}}
        config['receivers'].pop('prometheus/litellm-cache', None)
        config['service']['pipelines'].pop('metrics/cache', None)
        config['exporters'] = {signal:{'path':str(temp/(signal+'.json'))} for signal in ['file/traces','file/logs','file/metrics']}
        config['exporters']['prometheus'] = {'endpoint':'127.0.0.1:'+str(metric_port),'add_metric_suffixes':False}
        config['service']['pipelines']['traces']['exporters'] = ['file/traces','spanmetrics']
        config['service']['pipelines']['logs']['exporters'] = ['file/logs']
        config['service']['pipelines']['metrics']['exporters'] = ['file/metrics','prometheus']
        log = temp/'docker-json.log';log.write_text('')
        config['receivers']['filelog/synthetic'] = {'include':[str(log)],'start_at':'end','operators':[{'type':'add','field':'resource["service.name"]','value':'openhands'}]}
        config['service']['pipelines']['logs']['receivers'].append('filelog/synthetic')
        file = temp/'config.json';file.write_text(json.dumps(config))
        with (temp/'collector.log').open('w') as output:
            process = subprocess.Popen([args.collector,'--config='+str(file)],stdout=output,stderr=output)
            try:
                marker, trace_id, payloads = checks.canary_payloads(include_genai=True)
                for attempt in range(50):
                    if process.poll() is not None: raise RuntimeError((temp/'collector.log').read_text())
                    try:
                        checks.request('http://127.0.0.1:'+str(port)+'/v1/traces',payloads['traces']);break
                    except OSError as error:
                        if hasattr(error, "read"):
                            raise RuntimeError(error.read().decode()) from None
                        time.sleep(0.1)
                else: raise RuntimeError('Collector receiver not ready')
                for signal in ['logs','metrics']:
                    try:
                        checks.request('http://127.0.0.1:'+str(port)+'/v1/'+signal,payloads[signal])
                    except OSError as error:
                        if hasattr(error, 'read'): raise RuntimeError(signal+': '+error.read().decode()) from None
                        raise
                # Filelog has had time to open the empty file; append after receiver startup.
                time.sleep(1)
                log.write_text(json.dumps({'log':'Error validating tool: '+marker,'stream':'stderr','time':'2026-10-05T00:00:00Z'})+'\n')
                time.sleep(4)
                metrics = checks.request('http://127.0.0.1:'+str(metric_port)+'/metrics')
                assert 'agent_calls_total' in metrics, 'Spanmetrics missing'
                assert 'privacy_smoke_total{' in metrics, 'Prometheus canary counter name differs from host check'
                print('Spanmetrics series:', sorted({line.split('{')[0].split(' ')[0] for line in metrics.splitlines() if line.startswith(('agent_', 'gen_ai_'))}))
            finally:
                process.terminate();process.wait(timeout=10)
        combined = ''
        for signal in ['traces','logs','metrics']:
            data = (temp/('file/'+signal+'.json')).read_text()
            assert data.strip(), 'Missing signal: '+signal
            assert marker not in data, 'Sensitive data leaked to '+signal
            combined += data
        assert trace_id in combined and 'tool_validation_error' in combined
        assert 'openhands' in combined, 'Synthetic filelog not ingested'
        print('PASS: traces, logs, metrics and Docker filelog retained operational metadata and removed synthetic sensitive fields.')


if __name__ == '__main__':
    main()
