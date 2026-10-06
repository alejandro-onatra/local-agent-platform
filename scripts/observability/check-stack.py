#!/usr/bin/env python3
"""Synthetic checks only; this is not a runtime telemetry adapter."""
import json
import os
import re
import urllib.error
import secrets
import time
import urllib.parse
import urllib.request


def request(url, data=None, timeout=10, token=None, traceparent=None):
    headers = {'Accept': 'application/json'}
    if token:
        if urllib.parse.urlsplit(url).hostname != 'litellm':
            raise ValueError('Proxy credential must only be sent to LiteLLM')
        headers['Authorization'] = 'Bearer '+token
    if traceparent:
        if urllib.parse.urlsplit(url).hostname != 'litellm' or not re.fullmatch(r'00-[0-9a-f]{32}-[0-9a-f]{16}-01', traceparent):
            raise ValueError('Synthetic trace context must only be sent to LiteLLM')
        headers['traceparent'] = traceparent
    if data is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as response:
        return response.read().decode()


def model_trace_valid(payload):
    """Require the proxy entry span under its actual resource, not a canary span."""
    for batch in payload.get('resourceSpans', payload.get('batches', [])):
        attributes = batch.get('resource', {}).get('attributes', [])
        if not any(a.get('key') == 'service.name' and a.get('value', {}).get('stringValue') == 'litellm-proxy' for a in attributes):
            continue
        for scope in batch.get('scopeSpans', batch.get('instrumentationLibrarySpans', [])):
            if any(span.get('name') == 'Received Proxy Server Request' for span in scope.get('spans', [])):
                return True
    return False


def canary_payloads(include_genai=False):
    marker = 'SENSITIVE_CANARY_' + secrets.token_hex(12)
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    now = time.time_ns()
    attr = lambda key, value: {'key':key, 'value':{'stringValue':value}}
    resource = {'attributes':[attr('service.name','observability-smoke'),attr('secret',marker)]}
    scope = {'name':marker,'version':marker,'attributes':[attr('secret',marker)]}
    span = {'traceId':trace_id,'spanId':span_id,'name':marker,'kind':1,'startTimeUnixNano':str(now),'endTimeUnixNano':str(now+1000000),'attributes':[attr('prompt',marker),attr('gen_ai.request.model',marker),attr('gen_ai.usage.input_tokens',marker)],'status':{'code':2,'message':marker},'events':[{'timeUnixNano':str(now),'name':marker,'attributes':[attr('secret',marker)]}],'links':[{'traceId':secrets.token_hex(16),'spanId':secrets.token_hex(8),'attributes':[attr('secret',marker)]}]}
    unsafe_span = dict(span)
    unsafe_span['spanId'] = secrets.token_hex(8)
    span = dict(span)
    span.pop('links')
    trace = {'resourceSpans':[{'resource':resource,'scopeSpans':[{'scope':scope,'spans':[span,unsafe_span]}]}]}
    log = {'resourceLogs':[{'resource':resource,'scopeLogs':[{'scope':scope,'logRecords':[{'timeUnixNano':str(now),'observedTimeUnixNano':str(now),'body':{'stringValue':'Error validating tool: '+marker},'severityNumber':17,'severityText':marker,'attributes':[attr('secret',marker)]}]}]}]}
    metric = {'resourceMetrics':[{'resource':resource,'scopeMetrics':[{'scope':scope,'metrics':[{'name':'privacy_smoke','description':marker,'unit':'1','sum':{'aggregationTemporality':2,'isMonotonic':True,'dataPoints':[{'startTimeUnixNano':str(now),'timeUnixNano':str(now+1000000),'asInt':'1','attributes':[attr('secret',marker),attr('service.name',marker),attr('span.name',marker),attr('gen_ai.request.model',marker)],'exemplars':[{'timeUnixNano':str(now),'asInt':'1','filteredAttributes':[attr('secret',marker)]}]}]}}]}]}]}
    unsafe_point = metric['resourceMetrics'][0]['scopeMetrics'][0]['metrics'][0]['sum']['dataPoints'][0]
    safe_point = dict(unsafe_point)
    safe_point.pop('exemplars')
    metric['resourceMetrics'][0]['scopeMetrics'][0]['metrics'][0]['sum']['dataPoints'].append(safe_point)
    if include_genai:
        metric['resourceMetrics'][0]['scopeMetrics'][0]['metrics'].extend([{'name':'gen_ai.client.operation.duration','unit':'s','histogram':{'aggregationTemporality':2,'dataPoints':[{'timeUnixNano':str(now),'count':'1','sum':0.25,'bucketCounts':['1','0'],'explicitBounds':[0.5]}]}},{'name':'gen_ai.client.token.usage','unit':'{token}','histogram':{'aggregationTemporality':2,'dataPoints':[{'timeUnixNano':str(now),'count':'1','sum':10,'bucketCounts':['1','0'],'explicitBounds':[20]}]}}])
    return marker, trace_id, {'traces':trace,'logs':log,'metrics':metric}


def main():
    checks = []
    for name, url in [('collector-via-model', 'http://litellm:4000/health/liveliness'),('prometheus','http://prometheus:9090/-/ready'),('tempo','http://tempo:3200/ready'),('loki','http://loki:3100/ready'),('grafana','http://grafana:3000/api/health')]:
        for attempt in range(45):
            try:
                request(url); checks.append(name); break
            except Exception:
                if attempt == 44: raise RuntimeError('Readiness failed: '+name) from None
                time.sleep(1)
    # An unauthenticated models request must be rejected; never print credentials.
    try:
        request('http://litellm:4000/v1/models')
    except urllib.error.HTTPError as error:
        assert error.code in (401, 403), 'Unexpected authentication failure status'
    else:
        raise RuntimeError('LiteLLM accepted an unauthenticated API request')
    checks.append('unauthenticated-api-request-rejected')
    model_trace_id = secrets.token_hex(16)
    traceparent = '00-'+model_trace_id+'-'+secrets.token_hex(8)+'-01'
    response = json.loads(request('http://litellm:4000/v1/chat/completions', {'model':'qwen3:8b','messages':[{'role':'user','content':'Respond OK.'}],'max_tokens':16,'reasoning_effort':'none','temperature':0}, timeout=180, token=os.environ['LITELLM_MASTER_KEY'], traceparent=traceparent))
    assert response.get('choices'), 'No compatible model completion'
    checks.append('litellm-to-ollama-completion')
    marker, trace_id, payloads = canary_payloads()
    for signal, payload in payloads.items():
        request('http://collector:4318/v1/'+signal, payload)
    failure = 'not checked'
    for attempt in range(45):
        stage = 'tempo-query'
        try:
            trace = request('http://tempo:3200/api/traces/'+trace_id)
            stage = 'litellm-model-trace-missing'
            model_trace = request('http://tempo:3200/api/traces/'+model_trace_id)
            assert model_trace_valid(json.loads(model_trace)), 'Missing native model span'
            stage = 'llm-token-metrics-missing'
            token_metrics = json.loads(request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':'gen_ai_client_token_usage_sum{gen_ai_token_type="output",gen_ai_request_model=~"qwen3:8b|unknown"}'})))
            assert token_metrics['data']['result']
            stage = 'platform-probes-missing-or-failing'
            probes = json.loads(request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':'probe_success{job="platform-health"}'})))['data']['result']
            assert len(probes) == 9 and all(float(probe['value'][1]) == 1 for probe in probes)
            stage = 'loki-query'
            logs = json.loads(request('http://loki:3100/loki/api/v1/query_range?'+urllib.parse.urlencode({'query':'{service_name="observability-smoke"}','start':str(time.time_ns()-120000000000),'end':str(time.time_ns()),'limit':'20'})))
            stage = 'prometheus-query'
            metrics = json.loads(request('http://prometheus:9090/api/v1/query?'+urllib.parse.urlencode({'query':'privacy_smoke_total'})))
            stage = 'loki-log-missing'
            assert logs['data']['result']
            stage = 'prometheus-metric-missing'
            assert metrics['data']['result']
            serialized_logs = json.dumps(logs)
            stage = 'loki-category-missing'
            assert 'tool_validation_error' in serialized_logs
            stage = 'sensitive-canary-leaked'
            assert marker not in trace + serialized_logs + json.dumps(metrics)
            stage = 'tempo-operation-missing'
            assert 'operation' in trace
            break
        except Exception as error:
            # Report only stage, exception type and HTTP code, never response/credential content.
            failure = stage+': '+type(error).__name__
            if isinstance(error, urllib.error.HTTPError): failure += ' HTTP '+str(error.code)
            if stage == 'sensitive-canary-leaked' or attempt == 44:
                raise RuntimeError('Telemetry check failed at '+failure) from None
            time.sleep(1)
    checks.extend(['nine-platform-health-probes','native-litellm-trace-correlated','native-llm-token-metrics','trace-to-tempo','logs-to-loki','metrics-to-prometheus','sensitive-canaries-excluded'])
    print(json.dumps({'status':'passed','time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':checks,'coverage':'HTTP probes, synthetic privacy signals and native telemetry of a test model request; real OpenHands conversation/correlation not yet verified'},indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        if isinstance(error, urllib.error.HTTPError): detail += ' HTTP '+str(error.code)
        print(json.dumps({'status':'failed','time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'failure':detail},indent=2))
        raise SystemExit(1)
