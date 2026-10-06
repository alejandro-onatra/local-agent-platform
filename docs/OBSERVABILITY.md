# Observabilidad local: integración y operación

Actualización: 5 de octubre de 2026. Configuración preparada; el despliegue completo en Docker y la primera conversación observada requieren validación en el host. Ver [diagramas](architecture/OBSERVABILITY_DIAGRAMS.md) y [decisión de arquitectura](architecture/ADR-001-OBSERVABILITY.md).

## Qué añadimos y por qué

Usamos integraciones existentes: callback OpenTelemetry de **LiteLLM Proxy**, trazado nativo opcional del SDK de **OpenHands** y receiver **filelog del OTel Collector**. Los scripts del repositorio despliegan, configuran y comprueban; no interceptan conversaciones mediante un adaptador propio.

LiteLLM ofrece un endpoint compatible con OpenAI. OpenHands llama al proxy; el proxy llama a Ollama y emite metadatos de las solicitudes. Ollama sigue cargando el mismo Qwen3 en la GPU. No se reinstala el modelo ni se duplican sus pesos. Esta ruta inicial tiene un único modelo local y no configura fallback cloud.

El trazado del proxy muestra llamadas LLM, no cada paso del agente. El tracing nativo de OpenHands se habilita aparte para ejercicios sintéticos, porque sus decoradores pueden capturar argumentos y resultados de herramientas. `LMNR_TRACE_CONTENT=false` no garantiza excluir ese contenido de todos los spans. No se requiere una cuenta Laminar ni se configura un exporter cloud.

## Servicios y accesos

La infraestructura se encuentra en `infra/observability/`; las tareas llaman a `scripts/observability/`. El proyecto Compose `agent-platform-observability` se conecta a la red interna existente `agent-platform-local_agent-link` y conserva los volúmenes del laboratorio.

| Componente | Responsabilidad | Dirección dentro de Docker | Acceso desde host |
| --- | --- | --- | --- |
| LiteLLM | Ruta del modelo y telemetría nativa | `http://litellm:4000/v1` | Sin puerto publicado |
| Collector | Recibe OTLP, filtra y distribuye | `collector:4318` HTTP / `4317` gRPC | Sin puerto publicado |
| Prometheus | Scrapea las métricas del Collector | `prometheus:9090` | Mediante Grafana |
| Tempo | Almacena trazas OTLP | `tempo:3200` consultas / `4318` ingestión | Mediante Grafana |
| Loki | Almacena registros sanitizados | `loki:3100` | Mediante Grafana |
| Grafana | Explora los tres backends | `grafana:3000` | `http://127.0.0.1:3000` |

Se fijaron digests Linux amd64: Collector 0.162.0, Prometheus 3.15.0, Tempo 3.1.0, Loki 3.7.8, Grafana 13.2.3 y LiteLLM 1.104.0. Las referencias exactas y tamaños están en `infra/observability/versions.json`. Las siete imágenes, incluyendo Blackbox Exporter 0.28.0, suman aproximadamente **1.22 GB comprimidos**, además del laboratorio instalado. Los límites de RAM de la nueva pila suman aproximadamente 2.81 GiB; no representan consumo medido.

Tempo se configura en modo monolítico con disco local, sin Kafka. Los backends y LiteLLM usan redes internas. Grafana añade una red normal para publicar su UI en loopback. Este diseño no constituye una política de autorización para herramientas.

## Arranque y comprobación

Ejecutar desde la terminal del host, donde sudo ya funciona:

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise exec -- task observability:plan
mise exec -- task observability:setup
```

`setup` reaplica el laboratorio existente, arranca los siete servicios, configura la lectura de logs de los tres contenedores seleccionados y comprueba una llamada sintética a Qwen3 a través de LiteLLM junto con ingestión/redacción en Tempo, Loki y Prometheus. No borra volúmenes. Ejecutarlo cuando el agente esté inactivo, porque `openhands:up` puede recrear Ollama/OpenHands.

Grafana requiere usuario `admin` y una contraseña generada en el host, fuera de Git y CloudDrive:

```bash
cat "${XDG_DATA_HOME:-$HOME/.local/share}/agent-platform/observability/admin-password"
```

No compartir esa salida. El archivo se crea con permisos restringidos. La contraseña se transmite a Grafana mediante una variable Compose: administradores de Docker pueden verla en inspect. Cambiarla en Grafana requiere gestionar también ese archivo; el valor de arranque no restablece la contraseña de una base Grafana ya inicializada.

## Activar la ruta observada en OpenHands

No se modifica automáticamente el perfil que ya funciona. En Settings → LLM, crear `local-qwen3-8b-observed`:

| Campo | Valor |
| --- | --- |
| Modelo | `openai/qwen3:8b` |
| Base URL | `http://litellm:4000/v1` |
| API key | Contenido del archivo local `litellm-master-key` generado por `observability:up` |
| Contexto | Coherente con 32768 |
| Reasoning effort | `none`, si lo permite la interfaz |

Copiar la clave desde la terminal local:

```bash
cat "${XDG_DATA_HOME:-$HOME/.local/share}/agent-platform/observability/litellm-master-key"
```

Pegarla únicamente en el campo API key de OpenHands; no compartirla en el chat. La ruta directa a Ollama conserva el placeholder `local-only`. La clave del proxy autentica OpenHands → LiteLLM; LiteLLM → Ollama sigue usando el placeholder local.

En este laboratorio sin base de datos se usa la master key, que concede privilegios de administración del proxy. No es una clave limitada por usuario/modelo; para compartirlo con familia o evolucionar a multiusuario se necesitarán credenciales de cliente con alcance propio y un diseño de identidad. Se conserva en el archivo privado del host y en el perfil persistente de OpenHands. Administradores Docker pueden verla en el entorno del proxy.

Guardar, seleccionar ese perfil en el agente y crear una conversación nueva. Mantener un solo agente, herramientas en secuencia y cambio automático de perfiles desactivado. El contexto sigue siendo el configurado en Ollama; los 16 tokens del nuevo smoke test no limitan al agente.

Usar primero esta tarea de lectura:

> Usa la herramienta de terminal para ejecutar `pwd` y después `cd /projects/demo && pwd && ls -la`. Muestra la salida real. No modifiques archivos ni accedas a Internet.

En Grafana → carpeta **Agent Platform**, comprobar nuevos spans/métricas del proxy. Una prueba sintética de la infraestructura no demuestra que la conversación haya usado el nuevo perfil; conservar ese paso como aceptación manual.

Para volver a la ruta anterior, seleccionar `local-qwen3-8b` con base `http://ollama:11434/v1` en una conversación nueva.

## Tracing nativo de OpenHands: paso optativo

Después de validar el proxy, y únicamente con datos sintéticos:

```bash
mise exec -- task observability:tracing:on
```

La tarea verifica que `lmnr` y OpenTelemetry estén presentes en la imagen; no instala dependencias en caliente. Conecta OpenHands a la red interna de observabilidad y configura el endpoint OTLP HTTP local. Desactiva las integraciones automáticas adicionales mediante `LMNR_INSTRUMENTS` vacío, conservando los decoradores nativos del SDK. Recrea OpenHands; crear una conversación nueva y repetir la tarea de lectura.

Este paso permite comprobar spans del agente, pero puede enviar contenido de herramientas a la **memoria** del Collector antes de filtrarlo. Por eso está separado del arranque normal. Los exportadores persistentes reciben solo la salida filtrada. La cobertura exacta, el nombre de las operaciones y la propagación del `traceparent` entre OpenHands y LiteLLM deben comprobarse; no se promete una única traza completa hasta observarla.

```bash
mise exec -- task observability:tracing:off
```

También `openhands:up` reaplica el Compose base y deshabilita el tracing optativo. Si se necesita mantenerlo, volver a ejecutar `tracing:on` después y refrescar la configuración de logs.

## Dónde están los logs y cómo llegan a Loki

Docker ya recoge stdout/stderr de OpenHands, Ollama y LiteLLM con su driver `json-file`. Su ubicación real se obtiene de `LogPath` del contenedor; no se supone que Docker esté siempre en `/var/lib/docker`.

```bash
mise exec -- task observability:logs:configure
```

La tarea consulta únicamente ID, LogPath y driver de esos tres servicios. Genera dos archivos ignorados en `artifacts/observability/`: la configuración filelog y los mounts Compose. El Collector monta **solo los directorios de logs de esos contenedores, de lectura**, sin socket Docker ni acceso a logs de otros contenedores. Corre como UID 0 para poder leer esos directorios del host, con capacidades eliminadas, sin elevación y filesystem raíz de solo lectura. No se cambia el daemon ni se añade el usuario al grupo docker.

Filelog empieza desde el final para evitar importar el historial. Guarda offsets en un volumen propio y sigue la rotación del archivo activo; no importa archivos históricos comprimidos. `observability:up` refresca esta configuración automáticamente después de arrancar el núcleo, evitando reutilizar mounts antiguos. Una recreación fuera de esa tarea cambia el ID y LogPath: **volver a ejecutar `logs:configure` tras recrear cualquiera de los tres contenedores**. De lo contrario, podrían faltar logs aunque el Collector siga activo.

Pipeline: archivo Docker → receiver filelog → filtro de privacidad → batch → exporter OTLP HTTP → Loki. Los mensajes se reducen a `operational`, `error` o `tool_validation_error`, con cuerpo fijo `operational record`. Se renuncia al texto completo en Grafana para evitar almacenar contenido sensible. El filtrado no convierte logs en una auditoría de acciones autorizadas.

Los logs Docker originales y el estado/conversaciones de OpenHands siguen siendo fuentes locales sin esta redacción. Sus datos están en almacenamiento Docker, no en el repositorio. Los proyectos del agente sí están bajo CloudDrive; mantenerlos sintéticos.

## Privacidad y retención

| Señal | En origen | Antes de persistir en backends |
| --- | --- | --- |
| Solicitudes LLM | LiteLLM `turn_off_message_logging=true`, `NO_CONTENT`, eventos de contenido desactivados | Lista permitida de atributos; nombres de modelo/operaciones normalizados |
| Spans OpenHands | Tracing optativo; posible captura de argumentos/resultados | Eventos eliminados; spans con links rechazados; mensajes de error y atributos libres excluidos |
| Métricas | Lista permitida de dimensiones LiteLLM; exemplars desactivados | Lista de nombres y dimensiones; datapoints con exemplars rechazados; sin identificadores de ejecución/usuario |
| Logs | Docker puede registrar contenido | Cuerpo sustituido y categorías acotadas; sin rutas, prompts, claves ni argumentos originales |

Se usa filtrado por lista permitida, no una expresión regular que pretenda reconocer todos los secretos. La prueba canaria cubre cuerpo, atributos, scope, nombres, eventos, mensajes de estado, links y exemplars. No demuestra seguridad ante cualquier campo o versión futura; repetirla al cambiar dependencias y revisar atributos nuevos. Los esquemas OTLP y el endpoint interno son para emisores controlados del laboratorio, no una API pública multiusuario.

No hay exporter debug ni callback de contenido configurado. Las colas/batches contienen la salida sanitizada después del processor, pero el receiver trabaja inicialmente con la entrada original. No se configura una cola de exportación persistente: una interrupción puede perder datos en memoria; la entrega exactamente una vez no se garantiza.

Prometheus: 7 días, límite de datos de 1 GB. Loki: retención de 7 días mediante compactor. Tempo: objetivo de retención de 7 días mediante backend scheduler, con borrado asíncrono. Los límites no incluyen por igual WAL/índices/metadatos. Estado OpenHands, logs Docker y Grafana tienen retención independiente; los logs de aplicaciones se limitan por tamaño y número de archivos. Loki/Tempo no son la fuente de auditoría inmutable del futuro policy engine.

## Dashboards provisionados

La entrada principal es [Plataforma de agentes · Vista general](http://127.0.0.1:3000/d/platform-overview). Diseño, métricas, sondas, alertas y runbook: [DASHBOARDS.md](DASHBOARDS.md).

No es necesario importar JSON a mano. Las fuentes tienen UID estable `prometheus`, `tempo` y `loki`; los siete archivos están en `infra/observability/grafana/dashboards/`.

| Dashboard | Qué presenta en esta etapa | Qué sigue pendiente |
| --- | --- | --- |
| Plataforma de agentes · Vista general | Endpoints, RED, transporte OTel y logs; navegación a detalles | GPU/host, resultados de workflows y evaluación etiquetada |
| Agent operations | Tráfico, errores y latencia de spans del proxy | Tareas de agente finalizadas y duración total |
| LLM cost and routing | Tokens y duración LLM; único destino local | Routing múltiple, precios cloud y coste operativo local |
| Model quality and escalations | Errores técnicos; contexto de aceptación de ejercicios | Calidad etiquetada, intentos y escalaciones evaluadas |
| Security | Logs sanitizados y descripción de controles | Denegaciones, aprobaciones, actores y auditoría durable |
| Tools and MCP | Categorías de error de herramientas en logs | Contratos de spans de tools y MCP; no hay MCP configurado |
| Workflow and business KPIs | Disponibilidad del scrape; estado de instrumentación | Resultados de negocio y espera de aprobación |

Paneles sin datos indican falta de tráfico/instrumentación; no equivalen a cero errores ni a éxito. La configuración no evalúa calidad de respuestas automáticamente. Coste de API local y coste total del equipo son conceptos diferentes.

## Operación y validación

```bash
mise exec -- task observability:test
mise exec -- task observability:validate
mise exec -- task observability:status
mise exec -- task observability:check
mise exec -- task observability:logs
mise exec -- task observability:stop
```

`stop` conserva todos los volúmenes. Detener LiteLLM deja sin modelo las conversaciones que lo usan: volver primero al perfil directo si se desea seguir usando OpenHands. No se ejecuta `down -v` ni se elimina almacenamiento como parte de las tareas.

`observability:check` se ejecuta con el Python de LiteLLM en la red interna, sin publicar puertos de diagnóstico. Comprueba nueve endpoints, una respuesta del modelo con traza nativa correlacionada y métricas de tokens, además de señales canarias enviadas a los tres backends. El reporte JSON se guarda en `artifacts/diagnostics/`; no contiene la respuesta del modelo ni el texto de la canaria. La prueba no sustituye la aceptación de una conversación real ni la comprobación de un evento recién escrito en los logs Docker.

Ver el [registro de validación](diagnostics/OBSERVABILITY-2026-10-05.md). Validación de preparación: Compose resuelto, digests oficiales, configuraciones comprobadas con los binarios de las mismas imágenes, y prueba local del Collector con señales/filelog sintéticos. La prueba local se puede repetir con `python3 scripts/observability/test-privacy.py --collector /ruta/al/binario/otelcol-contrib` de la versión fijada. `observability:validate` repite la validación de archivos con los binarios dentro de las imágenes. El estado del despliegue en el host debe actualizarse después de recibir su resultado. El tracing nativo y la correlación real siguen pendientes.

## Fuentes oficiales

- [LiteLLM: integración OpenTelemetry y controles de contenido](https://docs.litellm.ai/docs/observability/opentelemetry_integration)
- [LiteLLM 1.104.0: implementación del callback](https://github.com/BerriAI/litellm/blob/v1.104.0/litellm/integrations/opentelemetry.py)
- [OpenHands: observabilidad del SDK](https://docs.openhands.dev/sdk/guides/observability)
- [SDK 1.49.6: activación y decoradores nativos](https://github.com/OpenHands/software-agent-sdk/blob/v1.49.6/openhands-sdk/openhands/sdk/observability/laminar.py)
- [OTel Collector: filelog](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.162.0/receiver/filelogreceiver)
- [OTel Collector: transform processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.162.0/processor/transformprocessor)
- [Loki: ingestión OTLP](https://grafana.com/docs/loki/latest/send-data/otel/)
- [Tempo 3: modos de despliegue](https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/plan/)

## Diagnóstico de un servicio que se detiene al arrancar

`Started` confirma que Docker inició el proceso, no que la aplicación completó su arranque. El script verifica que los siete procesos sigan ejecutándose y espera la API de LiteLLM además de Grafana. `observability:status` incluye contenedores detenidos.

Si el despliegue informa un servicio detenido, obtener su estado y logs locales. Para LiteLLM:

```bash
mise exec -- task observability:status
sudo docker --context default inspect --format '{{json .State}}' agent-platform-observability-litellm-1
sudo docker --context default logs --tail 100 agent-platform-observability-litellm-1
```

El primer despliegue pasó las validaciones nativas, pero falló antes de activar filelog por ausencia de un LiteLLM en ejecución. La causa del proceso requiere sus logs. No reinstalar Docker ni descargar de nuevo el modelo por ese mensaje.

### Corrección de autenticación LiteLLM 1.104.0

Los logs del primer arranque confirmaron `UnsafeMasterKeyError`, salida 3 y `OOMKilled=false`: faltaba `LITELLM_MASTER_KEY`. Esta versión rechaza por defecto una clave ausente/débil, aunque el puerto sea interno. No era un fallo de GPU, descarga o falta de memoria.

`observability:up` ahora genera una clave aleatoria de 32 bytes (prefijo `sk-`) en el directorio privado junto a la contraseña Grafana. Conserva las claves existentes y los volúmenes; sudo preserva únicamente las variables Compose necesarias. El smoke test autentica la llamada al modelo y exige rechazo de una petición sin clave. No se habilita la excepción que permite arrancar sin autenticación.

Reintentar `mise exec -- task observability:up` seguido de `mise exec -- task observability:check`. La corrección fue aceptada en el host el 6 de octubre; ver [evidencia](diagnostics/OBSERVABILITY-2026-10-06.md).

Fuente: [Cambio de autenticación en LiteLLM 1.104.0](https://docs.litellm.ai/release_notes/v1.104.0/v1-104-0), [API sin base de datos](https://docs.litellm.ai/docs/proxy/docker_quick_start).

### Corrección del contador de aceptación

Tras el arranque autenticado, Tempo/Loki/Prometheus sí recibieron las señales sintéticas. El test usaba el nombre `privacy_smoke`, pero el exporter Prometheus publicó el contador como `privacy_smoke_total`. Se corrigió la consulta y se exige ese nombre en la prueba local del Collector. Si vuelve a fallar una señal, el test indica la etapa y el código HTTP sin mostrar contenido sensible. Repetir solo `observability:check`; no hace falta recrear servicios por este cambio del script.

## Callback OTel de LiteLLM 1.104.0

Se retiró `gen_ai.token.type` de `callback_settings.otel.attributes.include_list`: LiteLLM rechaza configurarlo en ese filtro, por lo que el callback no iniciaba aunque las respuestas HTTP siguieran funcionando. El callback añade ese discriminador automáticamente a métricas de tokens. El Collector continúa admitiéndolo con valores limitados a input/output/unknown. `observability:check` exige ahora una traza nativa de la petición al modelo y sus métricas de tokens; una canaria sintética por sí sola no basta. Aplicar con `observability:up` y validar en el host.

`observability:up` recrea los servicios de observabilidad para aplicar cambios dentro de archivos montados (Compose no detecta su contenido en el hash del servicio). Hay una interrupción breve del proxy y los backends; credenciales y datos de volúmenes se conservan. El registro de logs se regenera después con los IDs actuales.

## Estado validado — 6 de octubre de 2026

`observability:check` pasó completo en el host: nueve sondas sanas, rechazo de solicitudes sin clave, respuesta autenticada del modelo, traza nativa correlacionada de la petición de prueba, tokens LLM y canarias de las tres señales sin contenido sensible en los campos comprobados. Grafana recibe datos de los nuevos paneles. La siguiente aceptación es una conversación real de OpenHands usando el perfil observado; el tracing del agente y su correlación completa siguen separados. Ver [registro de aceptación](diagnostics/OBSERVABILITY-2026-10-06.md).

## Golden signals y totales — actualización del dashboard

La vista general incluye una fila explícita de tráfico, errores, latencia p95 exitosa y saturación de colas OTel; la saturación de GPU/servidor LLM sigue pendiente. Se añadieron acumulados actuales y totales estimados del período de solicitudes, errores y tokens (entrada, salida, total). El dashboard LLM incluye también ambos tipos de totales. Las tasas se conservan. Los acumulados incluyen pruebas y pueden reiniciarse; los incrementos no recuperan automáticamente una primera muestra perdida. Grafana recargó los archivos sin reiniciar la pila; las 43 consultas fueron aceptadas por las fuentes reales. Ver [semántica y límites](DASHBOARDS.md#golden-signals-y-totales).

## Uso de caché reportado por Ollama

La caché de contexto reutiliza cómputo del prefijo de entrada; no evita toda la inferencia ni representa una respuesta guardada. Para esta ruta, Cache Hit ya está dentro de Input. Los totales de una conversación OpenHands y los contadores de LiteLLM tienen alcances e inicios distintos.

Además del callback OTel, LiteLLM usa su callback Prometheus existente restringido a los contadores de tokens de caché y etiqueta `model`. El Collector accede a `/metrics/` por la red interna con autenticación; aplica selección de métricas/modelo y redacción de etiquetas, y exporta a Prometheus. El master key también está disponible en el entorno del Collector solo para esa lectura; se comparte la credencial del laboratorio sin DB, pendiente de identidad/credenciales limitadas para multiusuario. No se publica el endpoint ni se deshabilita su autenticación.

`observability:cache:check` hace dos llamadas sintéticas por el proxy y coteja `cached_tokens` con el contador observado. `observability:cache:test` verifica de forma aislada autenticación, privacidad, acumulados sin doble suma y detección de fallo de scrape usando el Collector fijado. El fallo de scrape es visible como `litellm_cache_scrape_up=0`; los valores retenidos no prueban actividad nueva.

La implementación está preparada y validada aisladamente; el chequeo integral del nuevo callback requiere aplicar `observability:up` en la terminal del host. No se reescribe la conversación ni se rellena Grafana con cifras históricas de capturas. Ver [diagramas](architecture/OBSERVABILITY_DIAGRAMS.md) y [evidencia](diagnostics/TOKENS-2026-10-06.md).

Aceptación de caché del 6 de octubre, 09:57 Europe/Berlin: la prueba integral del host cotejó 1.623 tokens reutilizados con un aumento idéntico del contador; el chequeo general posterior también pasó. Las tarjetas de Grafana ya devuelven datos reales de caché. La ruta efectiva de una nueva llamada de la conversación OpenHands se verifica por separado; no se recupera su uso histórico anterior al proxy.
