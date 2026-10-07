# Observability Diagrams

October 5, 2026. Mermaid versioned diagrams; visible in Markdown readers with Mermaid support, including GitHub. The host passed the synthetic acceptance of the stack. The diagnosed conversation was repaired to use LiteLLM and passed the SSE check; additional increments were observed in Grafana cards. Detailed correlation by conversation is still pending. Dashed lines indicate optional integration or future work.

## 1. Model Path and Telemetry

```mermaid
flowchart LR
    User[Browser user] --> Canvas[OpenHands / Agent Canvas]
    Canvas -->|OpenAI compatible| LiteLLM[LiteLLM Proxy]
    LiteLLM -->|OpenAI compatible| Ollama[Ollama]
    Ollama --> GPU[Qwen3 on RTX 4060 Ti]
    LiteLLM -->|OTLP LLM metadata| Collector[OTel Collector]
    Canvas -.->|Optional native tracing| Collector
    Docker[Docker stdout/stderr files] -->|filelog: three containers| Collector
    Collector --> Filter[Allowlist and fixed categories]
    Filter --> Tempo[Tempo: traces]
    Filter --> Loki[Loki: sanitized logs]
    Filter --> Metrics[Collector metrics endpoint]
    Prometheus[Prometheus] -->|scrape| Metrics
    Grafana[Grafana] -->|query| Prometheus
    Grafana -->|query| Tempo
    Grafana -->|query| Loki
```

The model remains in the Ollama volume; LiteLLM does not execute or store its weights. The direct OpenHands → Ollama path remains the previous profile. Native tracing requires independent enablement.

## 2. Networks and Trust Boundaries

```mermaid
flowchart TB
    Host[Linux host: browser]
    subgraph Entry[Ports published on loopback only]
        OHProxy[127.0.0.1:8000 / Nginx proxy]
        GF[127.0.0.1:3000 / Grafana]
        OPort[127.0.0.1:11434 / Ollama]
    end
    subgraph AgentLink[Internal agent-link network]
        Agent[OpenHands: no GPU or Docker socket]
        LLM[LiteLLM]
        Model[Ollama: GPU and model volume]
    end
    subgraph Data[Internal observability data network]
        Col[Collector]
        Prom[Prometheus]
        T[Tempo]
        L[Loki]
    end
    Host --> OHProxy --> Agent
    Host --> GF
    Host --> OPort --> Model
    Agent --> LLM --> Model
    LLM --> Col
    Agent -.->|Optional tracing only| Col
    Col --> T
    Col --> L
    Prom --> Col
    GF --> Prom
    GF --> T
    GF --> L
    Files[Selected Docker log directories] -->|read-only mounts; no socket| Col
```

Grafana and the proxy UI also have a normal network for publishing their ports. Ollama retains the model download network. Files and the state of OpenHands are not an immutable audit. This internal network does not equate to an agent permission policy.

## 3. Observed Call Sequence

```mermaid
sequenceDiagram
    actor User as User
    participant Agent as OpenHands
    participant Proxy as LiteLLM
    participant Model as Ollama / Qwen3
    participant Col as Collector
    participant Tempo as Tempo
    participant Prom as Prometheus
    participant Grafana as Grafana
    User->>Agent: Synthetic task
    Agent->>Proxy: OpenAI-compatible request and Bearer key
    Proxy->>Model: Local inference
    Model-->>Proxy: Response and token usage
    Proxy-->>Agent: Compatible response
    Proxy->>Col: Spans and metrics without messages
    Col->>Col: Filter metadata and normalize names
    Col->>Tempo: Sanitized spans
    Prom->>Col: Metrics scrape
    Grafana->>Tempo: Trace query
    Grafana->>Prom: Metrics query
    Agent-->>User: Agent result
```

Logs travel through a separate pipeline. The belonging of OpenHands and LiteLLM spans to the same trace requires checking propagation of `traceparent`; this sequence does not assume it.

## 4. Storage and Privacy

```mermaid
flowchart TD
    Raw[Original input from controlled emitters] --> Receiver[OTLP / filelog receiver: memory]
    Receiver --> Privacy[Remove free attributes; normalize names]
    Privacy --> Reject[Reject linked spans and metrics with exemplars]
    Reject --> Batch[In-memory batch]
    Batch --> Backends[Tempo / Loki / Prometheus: sanitized data]
    Original[Original Docker logs and OpenHands state] --> Local[Local Docker storage: may contain content]
    Work[Synthetic project files] --> CloudDrive[artifacts/openhands/projects: CloudDrive]
    Admin[Grafana password and LiteLLM key] --> Secret[User local share: outside Git and CloudDrive]
```

LiteLLM excludes messages at source. Native OpenHands and Docker logs may introduce content before the filter; only use synthetic data in this phase. The canary test verifies specific fields, not a general anonymization certification.

## 5. Current Coverage and Runtime Evolution

```mermaid
flowchart LR
    LLM[LLM metadata: existing callback] --> OTel[OTel Collector]
    Logs[Operational errors: existing filelog] --> OTel
    Native[OpenHands: optional native tracing] -.-> OTel
    Runtime[Future decoupled runtime] -.-> Run[agent.run and result]
    Decisions[Future DecisionProvider] -.-> Decision[Evaluated decisions and escalations]
    Policy[Future policy and approval] -.-> Security[Permissions and durable audit]
    Tools[Future tool gateway and MCP] -.-> Tool[tool.call and technical results]
    Run -.-> OTel
    Decision -.-> OTel
    Security -.-> OTel
    Tool -.-> OTel
    OTel --> Dash[Overview and six specialized dashboards]
```

KPIs require definitions and results emitted by those components. Business metrics are not invented from tokens, spans, or a correct HTTP response.

## 6. Availability and Transport Health

```mermaid
flowchart LR
    Targets[OpenHands / web proxy / Ollama / LiteLLM / Collector / Prometheus / Tempo / Loki / Grafana] -->|GET without credentials| Blackbox[Blackbox Exporter: internal network]
    Blackbox -->|probe_success and duration| Prom[Prometheus]
    Internal[Collector: internal metrics on 8888] -->|Scrape with limited allowlist| Prom
    Prom --> Rules[Two local rules: 2-minute wait]
    Prom --> Overview[Grafana: overview]
    Loki[Loki: sanitized logs] --> Overview
    Overview --> Detail[Six dashboards and Tempo search]
```

`up` indicates scrape health; `probe_success` indicates endpoint response. Neither substitutes the model call with native tracing, the canary of ingestion/redaction, or the acceptance of a real conversation. No external notifications were configured.

## 7. Real Cache and Counter Walkthrough

```mermaid
sequenceDiagram
    participant OH as OpenHands
    participant LL as LiteLLM
    participant OL as Ollama / model
    participant C as OTel Collector
    participant P as Prometheus
    participant G as Grafana
    OH->>LL: History + tools + new instruction
    LL->>OL: OpenAI-compatible request
    OL->>OL: Reuse matching-prefix KV state
    OL->>OL: Process new input and generate response
    OL-->>LL: Usage: prompt_tokens and cached_tokens within input
    LL-->>OH: Response and usage for conversation totals
    LL->>LL: Native Prometheus callback: accumulate cached tokens
    C->>LL: Authenticated /metrics/ scrape over internal network
    LL-->>C: Selected counters
    C->>C: Allow only two metrics, local model and limited labels
    P->>C: Sanitized metrics scrape
    G->>P: Counter / increase / rate / percentage
```

Input and output also arrive through the existing OTel callback. The cache is a subset of input; it is not summed again. Repeated readings of a counter do not equate to additional usage. `litellm_cache_scrape_up` indicates if the Collector can read the authenticated exporter. A conversation that accesses Ollama directly skips LiteLLM and remains outside these counters. The current conversation path is verified with `openhands:usage:check`; its previous history is not automatically imported.

## 8. Effective Path: Why Tokens Were Not Growing

```mermaid
flowchart LR
    Conversation[Existing conversation] --> Actual{Effective model route}
    Actual -->|Detected: direct Ollama| Direct[Ollama]
    Direct --> Usage[Accumulated usage visible in OpenHands]
    Direct -.->|LiteLLM does not receive these calls| Flat[Proxy counters do not increase]
    Saved[Saved profile with LiteLLM URL] --> Apply[route:proxy: switch_llm with new usage_id]
    Apply --> Verify[Conversation GET verifies effective URL]
    Verify --> Future[Future calls through LiteLLM]
    Future --> Col[Collector: OTel usage and native cache]
    Col --> Prom[Prometheus]
    Prom --> Dashboard[Grafana: emitter increases and counters]
```

The saved profile and the effective model of a conversation are different states. The repair uses the existing OpenHands API, not a new adapter. The 301,409 tokens of conversation life are not imported into Prometheus; this counter only reflects observed traffic. `observability:stream:check` passed with numeric usage and exact increment 23/8. After repairing the path, two additional proxy calls were observed, in addition to that test; the added query does not attribute each call to a conversation.
