# ADR 001 — Reuse Observability Integrations

Date: October 5, 2026. Decision accepted for the local platform; deployment and integration remain pending validation.

## Problem

Ollama and OpenHands already perform synthetic tasks. We need to see LLM requests, errors, and agent activity in Grafana, without duplicating instrumentation or storing personal content. An adapter that interprets upstream conversations would add maintenance and depend on internal formats.

## Decision

1. LiteLLM Proxy will be the OpenAI-compatible API boundary for model calls and will emit OTel via its existing callback.
2. OpenHands will retain its runtime. Its SDK has native tracing based on Laminar/OTel; it will be enabled separately with synthetic data. No cloud Laminar account or endpoint is configured.
3. The Collector Contrib will use OTLP, filelog, and the native Prometheus receiver for cache tokens; it will sanitize before sending to Tempo, Prometheus, and Loki.
4. Grafana will provision sources and seven dashboards (overview and six specialized) from versioned files. Indicators without a source will be identified as pending.
5. There will be no proprietary conversation adapter in this phase. Only configuration, operational scripts, and synthetic checks.

## Alternatives

- **Grafana Alloy:** available for collecting logs/OTel; valid if the stack is unified within its ecosystem. Collector Contrib is chosen because it is already part of the goal and offers filelog/transform. We do not need two collectors now.
- **Langfuse/Phoenix:** useful for evaluation, datasets, and generation content. They are not added alongside Grafana in this phase; avoid more content persistence and services until there is a need for evaluation.
- **Automatic Python Instrumentation:** can capture library calls but does not reconstruct decisions, approvals, or business results on its own. Review version and privacy before incorporating it.
- **Ollama/GPU Community Exporter:** can complement server/GPU metrics; it does not replace agent tracing. It is postponed until compatibility with the RTX 4060 Ti and maintenance is verified.
- **Proprietary Adapter:** reserve it for a demonstrated specific lack. Metrics specific to decisions/quality will be emitted from future runtime contracts, not deducing success from logs.

## Consequences

There is an additional HTTP hop and a service in between agent and model. We must measure latency and repeat real tool calls when changing the route. The direct profile remains available to return to the previous local platform.

The initial coverage is limited to LLM calls and sanitized logs. Full correlation requires proven context propagation. Native tracing may introduce content into memory before filtering; it does not yet fulfill an absolute prohibition of capturing it at the source. It remains optional.

The collector that reads logs uses UID 0 with limited and read-only mounts, without Docker socket. The configuration depends on container IDs and must be refreshed after recreating them. Stored telemetry deliberately omits error text; full diagnostics, if needed, are performed locally with synthetic data.

Durable auditing and tool authorization still belong to the runtime design. Grafana, LiteLLM, and OTel do not implement these policies on their own.

## Evolution

Validate ingestion and a conversation; define the specific SDK span/error contract; instrument the first workflow and its results; incorporate labeled evaluation. In Kubernetes: replace Docker filelog with pod logs, separate credentials/identity, use TLS and appropriate storage, preserve OTLP protocols and dashboard UID. It is not claimed that the current Compose is an enterprise installation.

## Proxy Authentication — Correction After the First Deployment

LiteLLM 1.104.0 rejects starting without a strong master key. It is generated and kept outside of Git/CloudDrive, and clients use it to authenticate requests. Virtual keys by user are not yet implemented without a database; the master key is administrative and only suitable for this trusted local platform. Multi-user evolution will need to separate client privileges and administration. Startup control is not relaxed.

Official Blackbox Exporter is added for nine endpoint probes and internal Collector telemetry for queues/sending failures. No runtime metrics adapter is written. Probes do not imply successful execution or quality; alerts are evaluated locally without notifications. See `docs/dashboards.md`.

## Ollama Cache — Expansion of October 6, 2026

The local test confirmed `prompt_tokens_details.cached_tokens` in Ollama v0.35.1. The pinned OTel callback does not transform that nested field into its cache attributes. The official LiteLLM Prometheus callback is chosen, limited to two metrics and model label, along with the existing Prometheus receiver of the Collector with authentication. No conversation adapter or alpha components that accumulate numbers from spans are required.

The Collector receives the master key of the local platform in its exclusive environment for reading `/metrics/`; no anonymous access is enabled nor is that port published. Privacy of metrics and local model is verified before exporting. The prefix cache remains included in Input and is not added to Total. This instrumentation covers new usage through the proxy; it preserves the scope difference with the persisted accumulated OpenHands. See `docs/diagnostics/tokens-2026-10-06.md` for pending tests and acceptance of the host.
