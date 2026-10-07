# Diagramas de observabilidad

5 de octubre de 2026. Diagramas Mermaid versionados; visibles en lectores Markdown con soporte Mermaid, incluido GitHub. El host pasó la aceptación sintética de la pila. La conversación diagnosticada fue reparada para usar LiteLLM y pasó la comprobación SSE; se observaron incrementos adicionales en las tarjetas Grafana. La correlación detallada por conversación sigue pendiente. Las líneas discontinuas indican integración optativa o trabajo futuro.

## 1. Ruta del modelo y telemetría

```mermaid
flowchart LR
    User[Usuario en navegador] --> Canvas[OpenHands / Agent Canvas]
    Canvas -->|OpenAI compatible| LiteLLM[LiteLLM Proxy]
    LiteLLM -->|OpenAI compatible| Ollama[Ollama]
    Ollama --> GPU[Qwen3 en RTX 4060 Ti]
    LiteLLM -->|OTLP metadatos LLM| Collector[OTel Collector]
    Canvas -.->|Tracing nativo optativo| Collector
    Docker[Archivos stdout y stderr de Docker] -->|filelog: tres contenedores| Collector
    Collector --> Filter[Lista permitida y categorías fijas]
    Filter --> Tempo[Tempo: trazas]
    Filter --> Loki[Loki: logs sanitizados]
    Filter --> Metrics[Endpoint de métricas del Collector]
    Prometheus[Prometheus] -->|scrape| Metrics
    Grafana[Grafana] -->|consulta| Prometheus
    Grafana -->|consulta| Tempo
    Grafana -->|consulta| Loki
```

El modelo permanece en el volumen de Ollama; LiteLLM no ejecuta ni almacena sus pesos. La ruta directa OpenHands → Ollama sigue siendo el perfil anterior. El tracing nativo necesita habilitación independiente.

## 2. Redes y límites de confianza

```mermaid
flowchart TB
    Host[Host Linux: navegador]
    subgraph Entry[Puertos publicados solo en loopback]
        OHProxy[127.0.0.1:8000 / proxy Nginx]
        GF[127.0.0.1:3000 / Grafana]
        OPort[127.0.0.1:11434 / Ollama]
    end
    subgraph AgentLink[Red interna agent-link]
        Agent[OpenHands: sin GPU ni socket Docker]
        LLM[LiteLLM]
        Model[Ollama: GPU y volumen de pesos]
    end
    subgraph Data[Red interna observability data]
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
    Agent -.->|Solo tracing optativo| Col
    Col --> T
    Col --> L
    Prom --> Col
    GF --> Prom
    GF --> T
    GF --> L
    Files[Dirs seleccionados de logs Docker] -->|mounts de lectura; sin socket| Col
```

Grafana y el proxy UI tienen también una red normal para publicar sus puertos. Ollama conserva la red de descarga de modelos. Los archivos y el estado de OpenHands no son una auditoría inmutable. Esta red interna no equivale a una política de permisos del agente.

## 3. Secuencia de una llamada observada

```mermaid
sequenceDiagram
    actor User as Usuario
    participant Agent as OpenHands
    participant Proxy as LiteLLM
    participant Model as Ollama / Qwen3
    participant Col as Collector
    participant Tempo as Tempo
    participant Prom as Prometheus
    participant Grafana as Grafana
    User->>Agent: Tarea sintética
    Agent->>Proxy: Solicitud compatible con OpenAI y Bearer key
    Proxy->>Model: Inferencia local
    Model-->>Proxy: Respuesta y uso de tokens
    Proxy-->>Agent: Respuesta compatible
    Proxy->>Col: Spans y métricas sin mensajes
    Col->>Col: Filtrar metadatos y normalizar nombres
    Col->>Tempo: Spans sanitizados
    Prom->>Col: Scrape de métricas
    Grafana->>Tempo: Consulta de trazas
    Grafana->>Prom: Consulta de métricas
    Agent-->>User: Resultado del agente
```

Los logs viajan por un pipeline separado. La pertenencia de spans OpenHands y LiteLLM a una misma traza requiere comprobar propagación de `traceparent`; esta secuencia no la presupone.

## 4. Almacenamiento y privacidad

```mermaid
flowchart TD
    Raw[Entradas originales de emisores controlados] --> Receiver[Receiver OTLP / filelog: memoria]
    Receiver --> Privacy[Eliminar atributos libres; normalizar nombres]
    Privacy --> Reject[Rechazar spans con links y métricas con exemplars]
    Reject --> Batch[Batch en memoria]
    Batch --> Backends[Tempo / Loki / Prometheus: datos sanitizados]
    Original[Logs Docker y estado OpenHands originales] --> Local[Almacenamiento Docker local: puede contener contenido]
    Work[Archivos de proyectos sintéticos] --> CloudDrive[artifacts/openhands/projects: CloudDrive]
    Admin[Contraseña Grafana y clave LiteLLM] --> Secret[local share del usuario: fuera de Git y CloudDrive]
```

LiteLLM excluye mensajes en origen. OpenHands nativo y logs Docker pueden introducir contenido antes del filtro; solo usar datos sintéticos en esta fase. La prueba canaria verifica campos concretos, no una certificación general de anonimización.

## 5. Cobertura actual y evolución del runtime

```mermaid
flowchart LR
    LLM[Metadatos LLM: callback existente] --> OTel[OTel Collector]
    Logs[Errores operativos: filelog existente] --> OTel
    Native[OpenHands: tracing nativo optativo] -.-> OTel
    Runtime[Runtime desacoplado futuro] -.-> Run[agent.run y resultado]
    Decisions[DecisionProvider futuro] -.-> Decision[Decisiones y escalaciones evaluadas]
    Policy[Policy y Approval futuros] -.-> Security[Permisos y auditoría durable]
    Tools[Tool Gateway y MCP futuros] -.-> Tool[tool.call y resultados técnicos]
    Run -.-> OTel
    Decision -.-> OTel
    Security -.-> OTel
    Tool -.-> OTel
    OTel --> Dash[Vista general y seis dashboards especializados]
```

Los KPIs requieren definiciones y resultados emitidos por esos componentes. No se inventan métricas de negocio a partir de tokens, spans o una respuesta HTTP correcta.

## 6. Disponibilidad y salud del transporte

```mermaid
flowchart LR
    Targets[OpenHands / proxy web / Ollama / LiteLLM / Collector / Prometheus / Tempo / Loki / Grafana] -->|GET sin credenciales| Blackbox[Blackbox Exporter: red interna]
    Blackbox -->|probe_success y duración| Prom[Prometheus]
    Internal[Collector: métricas internas en 8888] -->|Scrape con lista limitada| Prom
    Prom --> Rules[Dos reglas locales: espera de 2 minutos]
    Prom --> Overview[Grafana: vista general]
    Loki[Loki: logs sanitizados] --> Overview
    Overview --> Detail[Seis dashboards y búsqueda en Tempo]
```

`up` indica salud del scrape; `probe_success` indica respuesta del endpoint. Ninguno sustituye la llamada al modelo con traza nativa, la canaria de ingestión/redacción o la aceptación de una conversación real. No se configuraron notificaciones externas.

## 7. Caché real y recorrido de sus contadores

```mermaid
sequenceDiagram
    participant OH as OpenHands
    participant LL as LiteLLM
    participant OL as Ollama / modelo
    participant C as OTel Collector
    participant P as Prometheus
    participant G as Grafana
    OH->>LL: Historial + herramientas + instrucción nueva
    LL->>OL: Solicitud compatible con OpenAI
    OL->>OL: Reutilizar estado KV del prefijo coincidente
    OL->>OL: Procesar parte nueva y generar respuesta
    OL-->>LL: Usage: prompt_tokens y cached_tokens dentro de input
    LL-->>OH: Respuesta y uso para acumular la conversación
    LL->>LL: Callback Prometheus nativo: acumular tokens de caché
    C->>LL: Scrape /metrics/ autenticado, red interna
    LL-->>C: Contadores seleccionados
    C->>C: Permitir solo dos métricas, modelo local y etiquetas limitadas
    P->>C: Scrape de métricas sanitizadas
    G->>P: Acumulado / incremento / rate / porcentaje
```

La entrada y salida también llegan por el callback OTel existente. La caché es un subconjunto de entrada; no se suma otra vez. Lecturas repetidas de un contador no equivalen a uso adicional. `litellm_cache_scrape_up` indica si el Collector puede leer el exportador autenticado. Una conversación que accede directamente a Ollama salta LiteLLM y queda fuera de estos contadores. La ruta actual de la conversación se verifica con `openhands:usage:check`; su historial anterior no se importa automáticamente.

## 6. Ruta efectiva: por qué no crecían los tokens

```mermaid
flowchart LR
    Conversation[Conversación existente] --> Actual{Ruta efectiva del modelo}
    Actual -->|Detectada: direct Ollama| Direct[Ollama]
    Direct --> Usage[Uso acumulado visible en OpenHands]
    Direct -.->|LiteLLM no recibe estas llamadas| Flat[Contadores del proxy sin incremento]
    Saved[Perfil guardado con URL LiteLLM] --> Apply[route:proxy: switch_llm con usage_id nuevo]
    Apply --> Verify[GET de conversación verifica URL efectiva]
    Verify --> Future[Consultas futuras por LiteLLM]
    Future --> Col[Collector: uso OTel y caché nativa]
    Col --> Prom[Prometheus]
    Prom --> Dashboard[Grafana: incrementos y acumulados del emisor]
```

El perfil guardado y el modelo efectivo de una conversación son estados diferentes. La reparación usa la API existente de OpenHands, no un adaptador nuevo. Los 301.409 tokens de vida de la conversación no se importan en Prometheus; este contador solo refleja tráfico observado. `observability:stream:check` pasó con uso numérico e incremento exacto 23/8. Tras reparar la ruta se observaron dos llamadas adicionales del proxy, además de esa prueba; la consulta agregada no atribuye cada llamada a una conversación.
