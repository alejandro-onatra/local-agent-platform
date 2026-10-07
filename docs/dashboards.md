# Dashboard general de la plataforma

Abrir [Plataforma de agentes · Vista general](http://127.0.0.1:3000/d/platform-overview) dentro de Grafana local. Está en la carpeta **Agent Platform** y se provisiona desde `infra/observability/grafana/dashboards/platform-overview.json`. No requiere importar JSON manualmente. Los seis dashboards especializados enlazan de vuelta a esta vista.

## Activación

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise exec -- task observability:up
mise exec -- task observability:check
```

El archivo JSON se actualiza por el provisioning de Grafana; las sondas y la configuración del Collector/Prometheus necesitan reaplicar Compose. `up` conserva las credenciales existentes y los volúmenes; recrea los servicios de observabilidad para recargar también el contenido de los archivos montados. Ejecutarlo cuando el agente esté inactivo. Sudo, si Docker lo requiere, se autentica en la terminal del host. El chequeo comprueba nueve endpoints, una llamada local con traza nativa correlacionada por `traceparent`, métricas de tokens y canarias de privacidad. La correlación con una conversación real de OpenHands sigue siendo una aceptación separada.

## Diseño y lectura

Orden: golden signals → totales acumulados y del período → disponibilidad → tendencias del modelo → transporte OTel → errores y detalles. Sigue la navegación de general a específico de las [recomendaciones de Grafana](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/).

| Bloque | Pregunta | Fuente y límites |
| --- | --- | --- |
| Endpoints y timeline | ¿Qué servicio responde y desde cuándo falla? | Sondas HTTP de Blackbox Exporter; no ejecutan inferencia ni validan un workflow |
| Scrape del monitor | ¿La observación sigue funcionando? | `up` de Prometheus; separado de `probe_success` de la aplicación |
| Alertas | ¿Un fallo HTTP/scrape dura al menos 2 minutos? | Dos reglas locales en Prometheus, pendientes/activas; sin notificaciones |
| Solicitudes y errores | ¿Hay tráfico y qué proporción falla? | Un span SERVER de entrada a LiteLLM por solicitud; no suma spans hijos ni canarias |
| Duración p95 del proxy | ¿Qué tarda el recorrido por el proxy? | Histograma de spans, incluye overhead; percentiles aproximados e inestables con pocas muestras |
| Tokens y p50/p95 LLM | ¿Cuánto uso y duración reporta el modelo? | Callback OTel nativo; entrada/salida separadas, sin prompts/respuestas |
| Colas y fallos de exportación | ¿Se atasca el envío a los backends? | Métricas internas del Collector; una exportación fallida puede reintentarse |
| Flujo y memoria del Collector | ¿Qué señales circulan y cuánto ocupa ese proceso? | Spans, puntos métricos y logs separados; RSS solo del Collector |
| Errores y logs | ¿Qué categorías recientes requieren investigación? | Loki con cuerpos sanitizados; no equivale a auditoría durable ni calidad evaluada |

Solo las llamadas mediante `http://litellm:4000/v1` aparecen en RED/LLM. El perfil directo a Ollama omite este proxy. Las pruebas negativas de autenticación pueden producir errores esperados: revisar su contexto antes de interpretar un aumento como incidente.

El filtro **Servicio (HTTP/logs)** controla disponibilidad y logs. Las gráficas LLM observan la ruta local completa; hay un único destino Qwen3. Los enlaces superiores llevan a operaciones de agente, LLM/routing, calidad, seguridad, tools/MCP, workflows y búsqueda de trazas en Tempo. El filtro de privacidad normaliza alias de modelo no reconocidos a `unknown`; no es otro modelo.

### Convenciones

- Rango inicial: última hora. Actualización: 30 s, con scrape de 15 s; `$__rate_interval` adapta las ventanas al rango/resolución.
- HTTP/scrape: **OK** verde, **FALLO** rojo. Los huecos no se conectan ni se transforman en éxito.
- **Sin datos** exige revisar tráfico, instrumentación o scrape. Nunca se sustituye por coste cero, cero errores o éxito. El porcentaje de error solo se muestra cuando hay tráfico observado.
- Duraciones en segundos, memoria en bytes, ratios en porcentaje. Tokens/s representa consumo agregado, no la velocidad de generación por usuario.
- Las señales exportadas no se suman entre unidades distintas. Los spans hijos y las canarias se excluyen del contador de solicitudes del proxy.
- Colas: 70% y 90% son referencias visuales iniciales, no SLO aceptados. No se fijan presupuestos de coste ni umbrales de latencia sin una línea base de cargas representativas.
- UID y fuentes estables, archivos versionables, edición en UI deshabilitada y variables de cardinalidad acotada; no se etiquetan usuarios, prompts, claves o IDs de conversación.

## Golden signals y totales

Las [cuatro golden signals del libro SRE de Google](https://sre.google/sre-book/monitoring-distributed-systems/) son tráfico, errores, latencia y saturación. La primera fila ahora muestra:

| Señal | Panel y alcance |
| --- | --- |
| Tráfico | Solicitudes completadas observadas / segundo en el span SERVER del proxy |
| Errores | Porcentaje de solicitudes técnicas con error, incluyendo autenticación; sin tráfico no se muestra un ratio |
| Latencia | p95 de solicitudes exitosas del proxy; la gráfica separa éxito y error para evitar mezclar fallos rápidos con inferencia lenta |
| Saturación disponible | Máxima ocupación de colas de exportación del Collector; no se presenta como saturación de GPU/servidor LLM |

La saturación del servidor del modelo y GPU continúa pendiente de instrumentación. Los paneles indican qué componente mide cada señal.

Dos filas de **totales** muestran solicitudes, errores, tokens de entrada, tokens de salida y suma entrada+salida:

- **Acumulados actuales por emisor:** último valor expuesto al final del rango. Incluyen la primera petición, pruebas y todas las conversaciones por LiteLLM. Los tokens pueden reiniciarse con el emisor LiteLLM; los spans se agregan en el Collector y pueden reiniciarse independientemente. No son un registro histórico durable ni cifras por conversación.
- **Totales del período seleccionado:** `increase` de Prometheus dentro del rango. Corrige resets que observó y extrapola bordes, por lo que puede dar decimales. No recupera el valor inicial si la serie apareció después de la primera petición y necesita al menos dos muestras. Se muestran como estimados. Ver [comportamiento de increase](https://prometheus.io/docs/prometheus/latest/querying/functions/#increase).

Las gráficas de rate se conservan: muestran actividad por segundo, no el total consumido. El dashboard **LLM cost and routing** también muestra entrada, salida y total, con acumulados e incrementos en filas separadas. Sus consultas filtran el emisor `litellm-proxy` y el job de métricas del Collector.

Las consultas son instantáneas para tarjetas y de rango para tendencias. Los totales responden al final/rango seleccionado según su tipo; no usar acumulados como contabilidad de una conversación o facturación. Para un histórico durable exacto se necesitará un registro de uso y una política de acceso/retención, fuera de este cambio de visualización.

Los cambios de visualización por sí solos se cargan con el polling de provisioning de Grafana. La ampliación de caché también cambia el callback y el Collector: requiere aplicar `observability:up` como se explica abajo; no borra volúmenes.

## Sondas existentes, sin adaptador propio

Se incorpora el [Blackbox Exporter oficial de Prometheus](https://github.com/prometheus/blackbox_exporter) v0.28.0, fijado por digest Linux amd64. Corre como usuario 65534, raíz de solo lectura, sin capacidades ni Docker socket, máximo 64 MiB. Sus puertos no se publican; solo accede a las redes internas de observabilidad y del laboratorio. Las sondas usan GET, timeout de 3 s, sin seguir redirects ni adjuntar credenciales.

| Servicio | Endpoint interno |
| --- | --- |
| OpenHands | `http://openhands:8000/canvas` |
| Acceso web OpenHands | `http://openhands-proxy:8080/canvas` |
| Ollama | `http://ollama:11434/api/version` |
| LiteLLM | `http://litellm:4000/health/liveliness` |
| Collector | `http://collector:13133/` |
| Prometheus | `http://prometheus:9090/-/ready` |
| Tempo | `http://tempo:3200/ready` |
| Loki | `http://loki:3100/ready` |
| Grafana | `http://grafana:3000/api/health` |

Se mezclan endpoints de liveness, readiness y UI, por eso el panel se llama **Endpoints**. La extensión `health_check` del Collector confirma su ciclo de vida, no la entrega a los backends. La prueba de ingestión complementa estas sondas. La [telemetría interna de OTel](https://opentelemetry.io/docs/collector/internal-telemetry/) se expone en 8888, solo en la red de datos; Prometheus conserva una lista limitada de métricas operativas y elimina el ID de instancia del servicio.

## Diagnóstico y alertas

`PlatformEndpointUnavailable`: HTTP falla durante 2 minutos. Revisar servicio, logs y dependencias. `ObservabilityScrapeUnavailable`: Prometheus no puede leer un target durante 2 minutos. Resolver primero el monitor si faltan datos. Las reglas están en `infra/observability/alerts.yaml`; se prueban con promtool en `observability:validate` mediante escenarios de espera, activación, recuperación y fallo independiente del monitor.

Un dashboard no notifica por sí solo. No hay Alertmanager, destinos de contacto ni alertas de coste/calidad configurados. La ausencia de series de `ALERTS` significa ausencia de alertas activas solo si Prometheus está disponible y sus reglas cargadas. Prometheus caído no puede avisar de su propia caída: un monitor externo sería una fase posterior.

1. Endpoint rojo: revisar `task observability:status`, el servicio concreto y sus logs.
2. HTTP OK sin métricas LLM: verificar perfil por LiteLLM y el resultado de `task observability:check`; un callback deshabilitado no impide que el modelo responda.
3. Exportaciones fallidas o colas crecientes: comprobar Loki/Tempo, red de datos y límites de memoria/disco. Un intento fallido no prueba pérdida definitiva.
4. Errores de tools: abrir Tools/MCP y una traza en Tempo cuando esté disponible. Una regex en logs no sustituye un resultado tipado de herramienta.

## Cobertura que falta

CPU/RAM/disco del host y otros contenedores; métricas de GPU/VRAM/temperatura; tareas completadas y duración completa; calidad con evaluación etiquetada y escalaciones; políticas/aprobaciones y auditoría durable; herramientas/MCP y resultados de negocio. Se muestran como pendientes, sin métricas inventadas. La retención aproximada de Prometheus/Loki/Tempo es de 7 días. Coste de API local, coste eléctrico y coste total del equipo siguen sin cálculo.

## Verificación realizada

Se validan con binarios oficiales fijados las configuraciones del Collector, Prometheus y Blackbox, junto con las dos reglas y sus escenarios de activación/recuperación. La prueba real del Collector con señales sintéticas conserva metadatos operativos y elimina canarias sensibles de trazas, logs, métricas y filelog. Las pruebas de autenticación y contexto de trazas comprueban aislamiento de credenciales.

Grafana local cargó la vista desde provisioning. Sus consultas se verifican contra las APIs reales de Prometheus/Loki. Esto validó inicialmente carga y sintaxis. El 6 de octubre se reaplicó `observability:up` y `observability:check` pasó en el host: nueve sondas sanas y telemetría nativa de la petición de prueba al modelo. Grafana muestra datos de los nuevos paneles; la conversación OpenHands y las áreas pendientes mantienen su aceptación separada. Ver [evidencia](diagnostics/observability-2026-10-06.md).

Además, una ejecución temporal con el binario oficial confirmó los nombres de RSS, colas, señales enviadas y señales con fallo del Collector. Blackbox devolvió éxito para los endpoints locales actuales de OpenHands, Grafana y Ollama y fallo para un HTTP 503 controlado. Las 23 consultas de la vista final fueron aceptadas por las fuentes reales. Estos ensayos no arrancaron ni modificaron los contenedores del usuario.

Validación del cambio de golden signals/totales: Grafana cargó el contenido final de ambos JSON como provisionado (vista general: 39 paneles contando secciones/texto; LLM: 9). Las 43 consultas de ambos dashboards fueron aceptadas por las fuentes reales. En la instantánea verificada, los contadores dieron 30 tokens de entrada + 4 de salida = 34, iguales en ambos dashboards; 3 solicitudes y 1 error, incluyendo el chequeo de autenticación. Estas cifras son evidencia de esa instantánea, no una expectativa fija para futuras ejecuciones.

## Caché de contexto del modelo

**Cache Hit** cuenta tokens de entrada reutilizados, no solicitudes ni respuestas completas. En la ruta OpenAI/Ollama está incluido en Entrada. Total sigue siendo Entrada + Salida. No confundir con la caché de respuestas de LiteLLM: esa es otra funcionalidad, no activada aquí.

El callback Prometheus oficial de LiteLLM exporta `litellm_input_cached_tokens_metric_total` y `litellm_input_cache_creation_tokens_metric_total`. Solo se habilitan esas métricas y la etiqueta `model` en origen. El receiver autenticado `prometheus/litellm-cache` del Collector selecciona los dos contadores, normaliza Qwen3 y elimina etiquetas privadas antes de exportar. El estado `litellm_cache_scrape_up` permite detectar fallo de esa lectura aunque el último contador siga visible.

Los dos dashboards incluyen acumulados, incrementos estimados del período, tasas y porcentaje de entrada reutilizada. Caché e input/output reinician con LiteLLM; los incrementos manejan resets observados, pero los huecos de captura y la primera muestra pueden perder uso. El porcentaje debe compararse en un rango con cobertura continua; no es una medición de ahorro de GPU/tiempo/energía. No se resta el acumulado de caché del acumulado de entrada para fabricar otro total.

**Sin datos** significa que no hay serie reportada: el callback omite valores ausentes/cero. Cache Write 0 en OpenHands no garantiza que Ollama informe una métrica de escritura. Solo se captura uso nuevo que pasa por el proxy; no se importa el acumulado de conversaciones anteriores o directas.

```bash
mise exec -- task observability:up
mise exec -- task observability:cache:check
mise exec -- task observability:check
```

Aplicar con el agente inactivo: `up` reinicia servicios y contadores del emisor, preservando volúmenes y conversaciones. Para repetir la prueba aislada del receiver y privacidad con la imagen fijada: `mise exec -- task observability:cache:test`. Ver [diagnóstico y ejemplo real](diagnostics/tokens-2026-10-06.md).

Verificación final de archivos y visualización: Grafana cargó ambos dashboards provisionados (Platform Overview: 48 paneles incluyendo filas/texto, versión de archivo 5; LLM: 18, versión 3). Las 59 consultas fueron aceptadas por Prometheus/Loki reales; no hay superposición de paneles. El callback actualizado ya está activo: la prueba integral del host pasó el 6 de octubre a las 09:57 Europe/Berlin y Grafana devuelve una serie real de Cache Hit (1.626 al consultar). La función oficial de normalización de LiteLLM v1.104.0 interpretó los dos `usage` reales de Ollama como 1 y 1.623 tokens cacheados. El chequeo del contenedor actualizado consta en los reportes locales de aceptación.
