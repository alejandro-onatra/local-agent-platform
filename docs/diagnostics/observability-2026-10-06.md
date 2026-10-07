# Acceptance of observability — October 6, 2026

## Host evidence

The user executed `mise exec -- task observability:up` and `mise exec -- task observability:check` in the repository. The check ended with **status: passed** at **00:09:47 of October 6, 2026, Europe/Berlin** (`2026-10-05T22:09:47Z`).

The native configurations of Collector, Prometheus, Loki, Tempo and Blackbox were validated. Both alert rules and their scenarios passed. The seven observability containers started and the filelog mounts of the three selected services were regenerated, preserving the credentials and volumes.

| Acceptance | Result |
| --- | --- |
| Readiness of the backends and proxy | Passed |
| API request without key | Rejected as expected |
| Authenticated call LiteLLM → Ollama/Qwen3 | Passed |
| Nine HTTP probes of the platform | All healthy in the check |
| Native trace of the test request to LiteLLM | Found in Tempo with the trace ID propagated |
| Native metrics of LLM tokens | Found in Prometheus |
| Canary OTLP: traces, logs and metrics | Found in Tempo, Loki and Prometheus |
| Sensitive canary in the checked fields | Excluded from the backends |

The correction of the OTel attribute filter is accepted on the host. It is not necessary to reinstall Docker, Ollama or the model.

## Dashboard confirmed from Grafana

The local API confirmed that `platform-overview` is provisioned and has 24 panels, including text and sections. The 23 queries were accepted by their real sources. Data of endpoints, scrape, timeline, requests/errors/latency of the proxy, tokens/duration LLM, queues, flow and memory of the Collector, and sanitized logs were found.

The absence of alert series or export failure should not be substituted by a general guarantee of success. The dashboard distinguishes these health signals from real inference.

## Scope and next acceptance

The checked model call was the test request of the check. **It has not yet been demonstrated that a real conversation of OpenHands is using LiteLLM**, nor a complete trace that spans of the agent and the proxy.

Next step: create/select `local-qwen3-8b-observed`, model `openai/qwen3:8b`, base URL `http://litellm:4000/v1`, private file key `litellm-master-key`; start a new conversation and run the read task in `/projects/demo` described in [observability.md](../observability.md). Keep sub-agents and automatic profile switching disabled.

Native tracing of the agent remains an optional later step; it is not assumed activated by this validation. GPU/host, quality evaluated, audit/policies, tools/MCP typed and business results remain pending instrumentation.

## Golden signals and totals visible

A call after the check was observed by LiteLLM. The dashboards were updated to show golden signals with explicit scope and current accumulated totals against estimated increments of the period. The first request is reflected in the accumulated although `increase` may omit it. Grafana reloaded both JSON as provisioned; the 43 queries were accepted. The snapshot showed 30 input tokens, 4 output tokens, 34 in total; 3 requests and 1 error (includes the expected rejection of the check). The total of tokens was compared with the real sum input+output. No services were restarted and no instrumentation or credentials were modified. The model/GPU saturation remains pending; the queue card corresponds to the Collector.
