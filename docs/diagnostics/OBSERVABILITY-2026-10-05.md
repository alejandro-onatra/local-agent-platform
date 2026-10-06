# Preparación de observabilidad — 5 de octubre de 2026

## Resultado verificado desde Work

- Se resolvieron manifests y digests Linux amd64 publicados para las seis imágenes; el lock está en `infra/observability/versions.json`.
- Compose resuelto y validado: backends internos, solo Grafana publicada en loopback, sin Docker socket, imágenes coincidentes con el lock, mounts de configuración de lectura y límites declarados.
- Collector 0.162.0, Tempo 3.1.0, Loki 3.7.8 y promtool 3.15.0 aceptaron sus configuraciones. Los binarios se extrajeron de layers verificados contra sus digests en un directorio temporal; no se instalaron servicios en el host.
- La prueba del Collector ejecutó de verdad receivers OTLP y filelog, processors, spanmetrics y exporters de archivo/Prometheus sobre datos sintéticos. Pasó la exclusión de canarias en cuerpos, atributos, nombres/scope, mensajes de estado y eventos, con rechazo de spans con links y datapoints con exemplars. Se conservó información operativa y se ingirió un archivo Docker sintético.
- La configuración generada de filelog y checkpoint se validó usando un directorio temporal de offsets. No se leyó ningún log real del host en esta comprobación.
- Se confirmaron nombres Prometheus reales: `agent_calls_total`, `agent_duration_seconds_bucket`, `gen_ai_client_operation_duration_seconds_bucket` y `gen_ai_client_token_usage_sum`. Se ajustaron las consultas Grafana a esos nombres.
- Los seis dashboards JSON se parsearon y tienen UID y panel IDs estables. No se comprobó todavía su render en Grafana.
- Sintaxis shell, estructura del repositorio, `task observability:plan` y el plan previo OpenHands pasaron; los 11 tests existentes de validación LLM siguen pasando.

## Repetir comprobaciones

```bash
mise exec -- task repo:check
mise exec -- task repo:test
mise exec -- task observability:plan
# En host con Docker: validadores dentro de las imágenes fijadas
mise exec -- task observability:validate
# Con un binario Collector de la versión fijada disponible localmente
python3 scripts/observability/test-privacy.py --collector /ruta/al/otelcol-contrib
```

## Pendiente en host

Ejecutar `task observability:setup`; verificar el reporte del smoke test, readiness y lectura de nuevos logs reales. Activar el perfil observado, comprobar una conversación real y explorar los seis dashboards. El tracing nativo OpenHands es optativo para datos sintéticos: confirmar dependencia, spans y propagación real de contexto antes de declarar trazabilidad completa.

No se declara validada la ejecución Docker completa, el callback dentro de la imagen LiteLLM, la correlación del agente ni la interfaz Grafana. Los controles de origen del callback se corroboraron también leyendo el código de la versión 1.104.0; esa inspección no sustituye el smoke test del despliegue. La [guía](../OBSERVABILITY.md) describe estos límites y el almacenamiento local que todavía puede contener contenido.

## Primer despliegue en host — 21:32–21:34 UTC

La salida compartida por el usuario confirma descarga de las seis imágenes, validación nativa de Collector/Prometheus/Loki/Tempo dentro de Docker y creación/arranque inicial de todos los contenedores. OpenHands y la conexión a Ollama pasaron.

El flujo se detuvo al configurar logs: `Start observability first.` Ese mensaje se emitía al no encontrar LiteLLM entre contenedores en ejecución. No demuestra un error del usuario ni determina el motivo del fallo del proceso. Los logs y el estado de LiteLLM son necesarios para distinguir error de configuración, dependencia, memoria u otra causa.

Se corrigió el diagnóstico: status incluye contenedores detenidos; el arranque comprueba los seis procesos y la disponibilidad HTTP de LiteLLM antes de configurar filelog. Si un servicio termina, informa nombre, estado, exit code y OOMKilled. No se ha cambiado la configuración de LiteLLM sin conocer sus logs ni se declara corregida la causa de arranque.

## Causa confirmada por los logs de LiteLLM

El usuario compartió estado `exited`, exit code 3, `OOMKilled=false`. El traceback concluye `UnsafeMasterKeyError`: la master key estaba ausente y el servidor rechazó aceptar solicitudes sin autenticación. Los avisos de trusted proxy ranges no explican ese cierre.

Corrección: clave fuerte persistente fuera de Git/CloudDrive, variable de entorno del proxy y paso explícito al usar sudo. El smoke test pasa esa clave solo al endpoint LiteLLM y comprueba rechazo de solicitudes sin autenticar. El perfil observado deja de usar `local-only` para la entrada al proxy; ese placeholder se mantiene solo en el tramo de Ollama. No se utiliza el bypass de clave débil/ausente. Reinicio y aceptación del host todavía pendientes.

## Comprobación de la corrección de autenticación

Pasaron cinco tests locales: credenciales distintas con modos 700/600, conservación al repetir el arranque, rechazo de clave existente inválida sin sobrescribirla, rechazo de symlink y envío de Bearer solo al hostname LiteLLM. Se verificaron con un stub los estados running/created/exited para evitar tratar un contenedor detenido como listo. La prueba real de privacidad del Collector se repitió y pasó después de modificar el cliente de comprobación.

Estos tests verifican los scripts y la preparación de credenciales; el reinicio de LiteLLM y el rechazo real de solicitudes sin autenticar están pendientes del comando del host. Repetición local: `mise exec -- task observability:test`.

## Segundo despliegue y corrección del nombre del contador

La nueva salida del host confirma LiteLLM y los otros servicios en ejecución, validadores nativos correctos, credenciales persistentes y mounts filelog/checkpoints activos. `observability:check` superó readiness, rechazo sin autenticación, respuesta autenticada del modelo y envío OTLP; falló al consultar las señales almacenadas.

Una consulta autenticada a Grafana y sus fuentes mostró: Tempo almacenó una traza `observability-smoke` con operación sanitizada, Loki almacenó `operational record` con categoría `tool_validation_error`, el scrape del Collector dio `up=1` y Prometheus tenía `privacy_smoke_total=1`. El chequeo buscaba incorrectamente `privacy_smoke`; se corrigió a `privacy_smoke_total`. El sufijo del contador se comprobó ahora también en la prueba local con el Collector real. Se añadió diagnóstico por etapa/HTTP sin imprimir cuerpos, secretos ni canarias.

Esto confirma las señales sintéticas existentes; no confirma todavía spans/métricas del callback real de LiteLLM ni una conversación OpenHands por el perfil observado. Repetir `mise exec -- task observability:check` para confirmar el chequeo completo con una canaria nueva.

### Estado adicional observado desde Grafana

La API local de Grafana respondió y mostró las tres fuentes provisionadas con sus UID. Una búsqueda de Tempo devolvió solo la canaria; una consulta de nombres Prometheus devolvió contadores/histogramas del span sintético y `privacy_smoke_total`, sin métricas `gen_ai.*`. Loki mostró categorías de error recientes de `litellm-proxy` con cuerpos sanitizados.

Por tanto, ingestión sintética y callback LLM se tratan como aceptaciones separadas. Se solicitaron los logs locales de LiteLLM para comprobar por qué todavía no se observa telemetría de sus llamadas. No se modificó esa configuración sin identificar el error. El chequeo guarda también un reporte JSON de fallo con etapa/tipo/código HTTP, evitando archivos de diagnóstico vacíos.

## Vista general y corrección del callback

Se confirmó en logs que `gen_ai.token.type` en el filtro de atributos impedía inicializar el callback nativo de LiteLLM. Se corrigió sin desactivar privacidad ni autenticación. Se añade dashboard general provisionado, Blackbox Exporter fijado, nueve sondas, métricas internas del Collector y dos reglas locales con espera de 2 minutos. Validaciones nativas, canarias de privacidad y siete pruebas de autenticación/contexto pasan. Grafana reconoce el dashboard como provisionado; las consultas se comprueban mediante sus fuentes reales. Pendiente reaplicar Compose y demostrar traza/métricas reales y nueve sondas sanas con el chequeo del host.

Verificación final: dashboard `platform-overview` reconocido como provisionado, 24 paneles (incluye secciones y texto), 23 consultas sin errores en las APIs reales de Prometheus/Loki. Ensayo temporal confirmó métricas internas RSS/colas/envíos/fallos del Collector y sondas Blackbox sanas en OpenHands/Grafana/Ollama más un HTTP 503 controlado. No se afirma que las nueve sondas nuevas ni el callback corregido estén activos antes del siguiente `observability:up` en el host.
