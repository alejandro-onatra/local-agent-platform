# Registro de cambios del laboratorio

Este registro resume decisiones y archivos verificables. Antes de esta revisión el repositorio no tenía commits: las entradas anteriores son retrospectivas apoyadas por configuración actual y reportes, no un diff exacto de todas las revisiones. La instantánea inicial local de este turno establece el primer baseline Git.

**6 de octubre de 2026 — transparencia y guía de infraestructura (este turno)**

- Nuevo `AGENTS.md`: guardar la instrucción del usuario de anunciar y mostrar siempre las modificaciones, con código/diff, validación y estado de aplicación.
- Nuevo `docs/INFRASTRUCTURE_WALKTHROUGH.md`: explicar host/GPU, mise/Task, Ollama, OpenHands, permisos, redes, LiteLLM, privacidad, logs, backends, provisioning, golden signals, totales, caché y límites pendientes mediante fragmentos de los archivos reales.
- La guía incluye la ubicación opcional de LangChain/LangGraph y un ejemplo explícitamente no instalado ni ejecutado, en respuesta a la pregunta del usuario.
- Nuevo `docs/CHANGELOG.md`: centralizar este registro de cambios y separar reconstrucción retrospectiva de diff real.
- `README.md`: enlazar guía/registro y corregir el estado antiguo de observabilidad con la aceptación ya registrada. La caché nueva pasó la prueba integral del host; una nueva llamada de la conversación observada mantiene aceptación pendiente.
- `.gitignore`: excluir `.idea/` sin modificar ni borrar los archivos del IDE.
- Primer commit local solicitado por el usuario, con la identidad Git ya configurada y una selección explícita de archivos del proyecto. Remoto GitHub pendiente de URL.
- No se cambian Compose, imágenes, modelos, callbacks, dashboards, credenciales ni servicios en este turno.

**6 de octubre de 2026 — ampliación reciente de caché**

| Archivo | Cambio concreto |
| --- | --- |
| `infra/observability/litellm.yaml` | Añadir callback Prometheus nativo, habilitar solo los dos contadores de tokens cache-read/cache-write con etiqueta model, exigir auth en /metrics/ |
| `infra/observability/collector.json` | Receiver Prometheus autenticado para LiteLLM; selección de métricas y modelo, etiquetas limitadas; pipeline de caché y estado del scrape |
| `infra/observability/compose.yaml` | Entregar la clave ya existente al Collector para leer métricas autenticadas |
| `infra/observability/grafana/dashboards/platform-overview.json` | Añadir Cache Hit/Write, períodos, tasas, porcentaje y estado del scrape; versión de archivo 5 |
| `infra/observability/grafana/dashboards/llm-cost-routing.json` | Mismo desglose de caché en el dashboard LLM; versión de archivo 3 |
| `scripts/openhands/usage-check.sh` y `.py` | Nuevo diagnóstico de ruta actual y uso numérico de una conversación, sin mensajes ni claves |
| `scripts/observability/check-cache.sh` y `.py` | Cotejar dos llamadas nuevas por LiteLLM con el contador de caché exportado |
| `scripts/observability/test-cache.sh` y `.py` | Prueba aislada con el Collector fijado: auth, acumulados, redacción y fallo HTTP |
| `scripts/observability/test-privacy.py` | Aislar la prueba canaria de la nueva dependencia de scrape del proxy |
| `scripts/observability/validate-config.py` | Verificar que el Collector reciba la credencial requerida sin mostrar su valor |
| `Taskfile.yml` | Tareas openhands:usage:check, observability:cache:check y observability:cache:test |
| `docs/DASHBOARDS.md`, `OBSERVABILITY.md`, `PLAN.md` | Documentar fuente, alcance, despliegue y aceptación pendiente |
| `docs/architecture/ADR-001-OBSERVABILITY.md`, `OBSERVABILITY_DIAGRAMS.md` | Decisión de integración existente y recorrido de caché |
| `docs/diagnostics/TOKENS-2026-10-06.md` | Evidencia Ollama real, aclaración de la captura OpenHands y distinta cobertura del proxy |

Preparado y probado aisladamente; después aplicado y validado en el host el 6 de octubre a las 09:57 Europe/Berlin. Dos llamadas sintéticas produjeron 1.623 tokens reutilizados y el contador aumentó exactamente 1.623. Los dashboards cargados por provisioning muestran series reales de caché. Falta cotejar una nueva llamada de la conversación. El ensayo de derivación desde spans no forma parte de la implementación final; se eligió el exportador Prometheus existente que maneja el campo anidado de Ollama.

**5–6 de octubre de 2026 — observabilidad, golden signals y totales**

- Stack Collector/Prometheus/Tempo/Loki/Grafana/LiteLLM/Blackbox fijado por digest, redes internas y solo Grafana publicado en loopback.
- Callback OTel nativo LiteLLM, privacy processors, filelog limitado y tracing nativo OpenHands optativo.
- Master key fuerte persistente fuera de Git/CloudDrive tras rechazo de arranque sin clave; corrección del filtro reservado gen_ai.token.type.
- Siete dashboards y fuentes provisionadas; nueve sondas HTTP, métricas internas del Collector y dos alertas locales.
- Golden signals con alcance explícito; totales acumulados actuales separados de increase del período y rate. No sumar muestras de contadores.
- Aceptación de la pila y petición sintética registrada en `docs/diagnostics/OBSERVABILITY-2026-10-06.md`. Correlación completa de una conversación pendiente.

**4–5 de octubre de 2026 — base de entorno y laboratorio local**

- Estructura Git, LICENSE, README, docs, infra y scripts categorizados. Remoto Git pendiente.
- mise con Task fijado y lock; scripts de bootstrap y host con paquetes fijados, APT firmado, backups, NVIDIA runtime y checks.
- Ollama/Qwen3 fijados por digest, pesos en volumen Docker, API loopback, GPU ID 0 y límites; contexto aumentado de 8192 a 32768.
- OpenHands Agent Canvas con estado persistente, workspace /projects, grupo host y Nginx loopback; preservación de variables al usar sudo.
- Pruebas reales de GPU/Docker/inferencia y ejercicios demo/bugfix. Separar tiempo de generación de carga/prefill y comprobación sintética de calidad general del agente.

La [guía con código](INFRASTRUCTURE_WALKTHROUGH.md) relaciona estas decisiones con los archivos actuales.

## Seguimiento del consumo y aceptación del host

- Actualizados README, guía de infraestructura, plan, observabilidad, dashboards y diagnóstico con la prueba integral de caché ya aprobada en el host.
- En la UI se volvió a seleccionar `local-qwen3-8b` en la conversación existente, usando su configuración guardada que apunta a LiteLLM. No se modificaron secretos. Falta comprobar una respuesta nueva por esa conversación; los contadores históricos de OpenHands no se importan.
