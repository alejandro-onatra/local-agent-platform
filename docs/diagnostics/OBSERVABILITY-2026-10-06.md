# Aceptación de observabilidad — 6 de octubre de 2026

## Evidencia del host

El usuario ejecutó `mise exec -- task observability:up` y `mise exec -- task observability:check` en el repositorio. El chequeo terminó con **status: passed** a las **00:09:47 del 6 de octubre de 2026, Europe/Berlin** (`2026-10-05T22:09:47Z`).

Las configuraciones nativas de Collector, Prometheus, Loki, Tempo y Blackbox se validaron. Pasaron las dos reglas de alerta y sus escenarios. Los siete contenedores de observabilidad arrancaron y se regeneraron los mounts filelog de los tres servicios seleccionados, conservando las credenciales y volúmenes.

| Aceptación | Resultado |
| --- | --- |
| Readiness de los backends y proxy | Pasó |
| Solicitud API sin clave | Rechazada como se esperaba |
| Llamada autenticada LiteLLM → Ollama/Qwen3 | Pasó |
| Nueve sondas HTTP de la plataforma | Todas sanas en el chequeo |
| Traza nativa de la petición de prueba a LiteLLM | Encontrada en Tempo con el trace ID propagado |
| Métricas nativas de tokens LLM | Encontradas en Prometheus |
| Canary OTLP: trazas, logs y métricas | Encontradas en Tempo, Loki y Prometheus |
| Canary sensible en los campos comprobados | Excluida de los backends |

La corrección del filtro de atributos OTel queda aceptada en el host. No es necesario reinstalar Docker, Ollama ni el modelo.

## Dashboard confirmado desde Grafana

La API local confirmó que `platform-overview` está provisionado y tiene 24 paneles, incluyendo texto y secciones. Las 23 consultas fueron aceptadas por sus fuentes reales. Se encontraron datos de endpoints, scrape, timeline, solicitudes/errores/latencia del proxy, tokens/duración LLM, colas, flujo y memoria del Collector, y logs sanitizados.

La ausencia de series de alerta o fallo de exportación no debe sustituirse por una garantía general de éxito. El dashboard distingue estas señales de salud HTTP e inferencia real.

## Alcance y siguiente aceptación

La llamada al modelo comprobada fue la petición de prueba del chequeo. **Aún no se ha demostrado que una conversación real de OpenHands esté usando LiteLLM**, ni una traza completa que una spans del agente y del proxy.

Siguiente paso: crear/seleccionar `local-qwen3-8b-observed`, modelo `openai/qwen3:8b`, base URL `http://litellm:4000/v1`, clave del archivo privado local `litellm-master-key`; iniciar una conversación nueva y ejecutar la tarea de lectura en `/projects/demo` descrita en [OBSERVABILITY.md](../OBSERVABILITY.md). Mantener subagentes y cambio automático de perfiles desactivados.

El tracing nativo del agente sigue siendo un paso optativo posterior; no se presume activado por esta validación. GPU/host, calidad evaluada, auditoría/políticas, tools/MCP tipados y resultados de negocio siguen pendientes de instrumentación.

## Golden signals y totales visibles

Se observó una llamada posterior al chequeo por LiteLLM. Se actualizaron los dashboards para mostrar golden signals con alcance explícito y totales acumulados actuales frente a incrementos estimados del período. La primera petición se refleja en el acumulado aunque `increase` pueda omitirla. Grafana recargó ambos JSON como provisionados; las 43 consultas fueron aceptadas. La instantánea mostraba 30 tokens de entrada, 4 de salida, 34 en total; 3 solicitudes y 1 error (incluye el rechazo esperado del chequeo). El total de tokens se contrastó con la suma real entrada+salida. No se reiniciaron servicios ni se modificó la instrumentación o las credenciales. La saturación del modelo/GPU permanece pendiente; la tarjeta de colas corresponde al Collector.
