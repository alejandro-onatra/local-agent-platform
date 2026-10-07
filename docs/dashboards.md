# General platform dashboard

Open [Agent Platform · Overview](http://127.0.0.1:3000/d/platform-overview) inside local Grafana. It is in the **Agent Platform** folder and is provisioned from `infra/observability/grafana/dashboards/platform-overview.json`. It does not require manual JSON import. The six specialized dashboards link back to this view.

## Activation

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise exec -- task observability:up
mise exec -- task observability:check
```

The JSON file is updated by Grafana provisioning; the probes and Collector/Prometheus configuration need to reapply Compose. `up` preserves existing credentials and volumes; it recreates observability services to reload the content of mounted files. Run it when the agent is inactive. Sudo, if Docker requires it, authenticates in the host terminal. The check verifies nine endpoints, a local call with native trace correlation by `traceparent`, token metrics, and privacy canaries. Correlation with a real OpenHands conversation remains a separate acceptance.

## Design and reading

Order: golden signals → accumulated totals and period → availability → model trends → OTel transport → errors and details. Follows the general to specific navigation of the [Grafana recommendations](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/).

| Block | Question | Source and limits |
| --- | --- | --- |
| Endpoints and timeline | What service responds and when does it fail? | Blackbox Exporter HTTP probes; they do not run inference or validate a workflow |
| Monitor scrape | Is the observation still working? | `up` of Prometheus; separated from `probe_success` of the application |
| Alerts | Does an HTTP/scrape failure last at least 2 minutes? | Two local Prometheus rules, pending/active; no notifications |
| Requests and errors | Is there traffic and what proportion fails? | A SERVER span entry to LiteLLM per request; it does not sum child spans or canaries |
| Proxy p95 duration | How long does the proxy journey take? | Histogram of spans, includes overhead; approximate and unstable percentiles with few samples |
| Tokens and p50/p95 LLM | How much usage and duration reports the model? | Native OTel callback; input/output separated, no prompts/responses |
| Queues and export failures | Is the sending to backends getting stuck? | Internal Collector metrics; a failed export can be retried |
| Collector flow and memory | What signals circulate and how much does that process occupy? | Spans, metric points, and logs separated; RSS only of the Collector |
| Errors and logs | What recent categories require investigation? | Loki with sanitized bodies; it does not equate to durable auditing or quality evaluation |

Only calls via `http://litellm:4000/v1` appear in RED/LLM. The direct profile to Ollama omits this proxy. Negative authentication tests may produce expected errors: review their context before interpreting an increase as an incident.

The **Service (HTTP/logs)** filter controls availability and logs. LLM graphs observe the full local path; there is a single destination Qwen3. The upper links lead to agent operations, LLM/routing, quality, security, tools/MCP, workflows, and trace search in Tempo. The privacy filter normalizes unrecognized model aliases to `unknown`; it is not another model.

### Conventions

- Initial range: last hour. Update: 30 s, with scrape of 15 s; `$__rate_interval` adapts the windows to the range/resolution.
- HTTP/scrape: **OK** green, **FALLO** red. Gaps are not connected nor transformed into success.
- **No data** requires reviewing traffic, instrumentation, or scrape. It is never substituted by zero cost, zero errors, or success. The error percentage is only shown when there is observed traffic.
- Durations in seconds, memory in bytes, ratios in percentage. Tokens/s represents aggregated consumption, not the generation speed per user.
- Exported signals are not summed across distinct units. Child spans and canaries are excluded from the proxy's request count.
- Queues: 70% and 90% are initial visual references, not accepted SLOs. No cost budgets or latency thresholds are set without a representative load baseline.
- UID and stable sources, versionable files, UI editing disabled, and bounded cardinality variables; users, prompts, keys, or conversation IDs are not tagged.

## Golden signals and totals

The [four golden signals from Google's SRE book](https://sre.google/sre-book/monitoring-distributed-systems/) are traffic, errors, latency, and saturation. The first row now shows:

| Signal | Panel and scope |
| --- | --- |
| Traffic | Completed requests observed / second in the proxy's SERVER span |
| Errors | Percentage of technical requests with error, including authentication; no ratio is shown without traffic |
| Latency | p95 of successful proxy requests; the graph separates success and error to avoid mixing fast failures with slow inference |
| Available saturation | Maximum occupation of Collector export queues; it is not presented as GPU/LLM server saturation |

Server model and GPU saturation continues pending instrumentation. The panels indicate which component measures each signal.

Two rows of **totals** show requests, errors, input tokens, output tokens, and sum input+output:

- **Current accumulated by emitter:** last value exposed at the end of the range. They include the first request, tests, and all conversations via LiteLLM. Tokens can be reset with the LiteLLM emitter; spans are aggregated in the Collector and can be reset independently. They are not a durable historical record nor per-conversation figures.
- **Totals of the selected period:** `increase` of Prometheus within the range. It corrects resets observed and extrapolates edges, so it may give decimals. It does not recover the initial value if the series appeared after the first request and needs at least two samples. They are shown as estimates. See [increase behavior](https://prometheus.io/docs/prometheus/latest/querying/functions/#increase).

Rate graphs are preserved: they show activity per second, not the total consumed. The **LLM cost and routing** dashboard also shows input, output, and total, with accumulated and increases in separate rows. Its queries filter the emitter `litellm-proxy` and the Collector's metric job.

Queries are instant for cards and range-based for trends. Totals respond to the selected end/range according to their type; do not use accumulated values as conversation or billing accounting. For an exact durable history, a usage log and an access/retention policy are needed, outside of this visualization change.

Visualization changes themselves are loaded with Grafana's provisioning polling. Cache expansion also changes the callback and the Collector: requires applying `observability:up` as explained below; does not erase volumes.

## Existing Probes, Without a Dedicated Adapter

The [official Prometheus Blackbox Exporter](https://github.com/prometheus/blackbox_exporter) v0.28.0 is incorporated, pinned by Linux amd64 digest. It runs as user 65534, read-only root filesystem, no capabilities or Docker socket, maximum 64 MiB. Its ports are not published; it only accesses the internal observability and local platform networks. The probes use GET, timeout of 3 s, without following redirects or attaching credentials.

| Service | Internal Endpoint |
| --- | --- |
| OpenHands | `http://openhands:8000/canvas` |
| OpenHands Web Access | `http://openhands-proxy:8080/canvas` |
| Ollama | `http://ollama:11434/api/version` |
| LiteLLM | `http://litellm:4000/health/liveliness` |
| Collector | `http://collector:13133/` |
| Prometheus | `http://prometheus:9090/-/ready` |
| Tempo | `http://tempo:3200/ready` |
| Loki | `http://loki:3100/ready` |
| Grafana | `http://grafana:3000/api/health` |

Liveness, readiness, and UI endpoints are mixed, hence the panel is called **Endpoints**. The `health_check` extension of the Collector confirms its lifecycle, not its delivery to backends. The ingestion test complements these probes. The [internal OTel telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/) is exposed in 8888, only in the data network; Prometheus retains a limited list of operational metrics and removes the service instance ID.

## Diagnosis and Alerts

`PlatformEndpointUnavailable`: HTTP fails during 2 minutes. Review service, logs, and dependencies. `ObservabilityScrapeUnavailable`: Prometheus cannot read a target during 2 minutes. Resolve the monitor first if data is missing. The rules are in `infra/observability/alerts.yaml`; they are tested with promtool in `observability:validate` through scenarios of waiting, activation, recovery, and failure independent of the monitor.

A dashboard does not notify on its own. There is no Alertmanager, contact destinations, or cost/quality alerts configured. The absence of series of `ALERTS` means absence of active alerts only if Prometheus is available and its rules are loaded. A down Prometheus cannot warn of its own failure: an external monitor would be a later phase.

1. Red endpoint: review `task observability:status`, the specific service, and its logs.
2. HTTP OK without LLM metrics: verify profile by LiteLLM and the result of `task observability:check`; a disabled callback does not prevent the model from responding.
3. Failed exports or growing queues: check Loki/Tempo, data network, and memory/disk limits. A failed attempt does not prove definitive loss.
4. Tool errors: open Tools/MCP and a trace in Tempo when it is available. A regex in logs does not replace a typed tool result.

## Missing Coverage

CPU/RAM/disk of the host and other containers; GPU/VRAM/temperature metrics; completed tasks and full duration; quality with labeled evaluation and escalations; policies/approvals and durable auditing; tools/MCP and business results. They are shown as pending, without invented metrics. The approximate retention of Prometheus/Loki/Tempo is of 7 days. Local API cost, electrical cost, and total equipment cost remain without calculation.

## Verified Changes

The Collector, Prometheus, and Blackbox configurations are validated with pinned official binaries, along with the two rules and their activation/recovery scenarios. The real Collector test with synthetic signals preserves operational metadata and removes sensitive canaries from traces, logs, metrics, and filelog. Authentication and trace context tests check credential isolation.

Local Grafana loaded the view from provisioning. Its queries are verified against the real APIs of Prometheus/Loki. This validated initial loading and syntax. The October 6 was reapplied `observability:up` and `observability:check` passed on the host: nine healthy probes and native telemetry of the test request to the model. Grafana shows data from the new panels; the OpenHands conversation and pending areas maintain their separate acceptance. See [evidence](diagnostics/observability-2026-10-06.md).

Additionally, a temporary run with the official binary confirmed the names of RSS, queues, signals sent, and signals with failure of the Collector. Blackbox returned success for the current local endpoints of OpenHands, Grafana, and Ollama and failure for an HTTP 503 controlled. The 23 queries of the final view were accepted by the real sources. These trials did not start or modify the user containers.

Validation of the change of golden signals/totals: Grafana loaded the final content of both JSON as provisioned (overview: 39 panels counting sections/text; LLM: 9). The 43 queries of both dashboards were accepted by the real sources. In the verified snapshot, the counters gave 30 input tokens + 4 output = 34, equal in both dashboards; 3 requests and 1 error, including the authentication check. These figures are evidence of that snapshot, not a fixed expectation for future runs.

## Model Context Cache

**Cache Hit** counts reused input tokens, not full requests or responses. In the OpenAI/Ollama route, it is included in Input. Total remains Input + Output. Do not confuse with LiteLLM's response cache: that is another functionality, not activated here.

The official Prometheus callback of LiteLLM exports `litellm_input_cached_tokens_metric_total` and `litellm_input_cache_creation_tokens_metric_total`. Only those metrics and the label `model` are enabled in origin. The authenticated receiver `prometheus/litellm-cache` of the Collector selects the two counters, normalizes Qwen3, and removes private labels before exporting. The state `litellm_cache_scrape_up` allows detecting failure of that reading even if the last counter remains visible.

The two dashboards include accumulated values, estimated period increments, rates, and percentage of reused input. Cache and input/output reset with LiteLLM; increments handle observed resets, but capture gaps and the first sample may lose usage. The percentage should be compared within a range with continuous coverage; it is not a measurement of GPU/time/energy savings. The accumulated cache value is not subtracted from the input accumulated value to fabricate another total.

**No data** means there is no reported series: the callback omits missing/zero values. Cache Write 0 in OpenHands does not guarantee that Ollama reports a write metric. Only new usage that passes through the proxy is captured; the accumulated previous or direct conversation data is not imported.

```bash
mise exec -- task observability:up
mise exec -- task observability:cache:check
mise exec -- task observability:check
```

Apply with the agent inactive: `up` restarts the emitter's services and counters, preserving volumes and conversations. To repeat the isolated receiver test and privacy with the pinned image: `mise exec -- task observability:cache:test`. See [diagnosis and real example](diagnostics/tokens-2026-10-06.md).

Final file and visualization verification: Grafana loaded both provisioned dashboards (Platform Overview: 48 panels including rows/text, file version 5; LLM: 18, version 3). The 59 queries were accepted by real Prometheus/Loki; there is no panel overlap. The updated callback is already active: the host's full test passed October 6 at 09:57 Europe/Berlin and Grafana returns a real Cache Hit series (1,626 when queried). The official normalization function of LiteLLM v1.104.0 interpreted the two `usage` real Ollama metrics as 1 and 1,623 cached tokens. The updated container check is included in the local acceptance reports.
