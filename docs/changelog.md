# Registro de cambios del laboratorio

Este registro resume decisiones y archivos verificables. Antes de esta revisión el repositorio no tenía commits: las entradas anteriores son retrospectivas apoyadas por configuración actual y reportes, no un diff exacto de todas las revisiones. La instantánea inicial local de este turno establece el primer baseline Git.

**6 de octubre de 2026 — transparencia y guía de infraestructura (este turno)**

- Nuevo `AGENTS.md`: guardar la instrucción del usuario de anunciar y mostrar siempre las modificaciones, con código/diff, validación y estado de aplicación.
- Nuevo `docs/infrastructure_walkthrough.md`: explicar host/GPU, mise/Task, Ollama, OpenHands, permisos, redes, LiteLLM, privacidad, logs, backends, provisioning, golden signals, totales, caché y límites pendientes mediante fragmentos de los archivos reales.
- La guía incluye la ubicación opcional de LangChain/LangGraph y un ejemplo explícitamente no instalado ni ejecutado, en respuesta a la pregunta del usuario.
- Nuevo `docs/changelog.md`: centralizar este registro de cambios y separar reconstrucción retrospectiva de diff real.
- `README.md`: enlazar guía/registro y corregir el estado antiguo de observabilidad con la aceptación ya registrada. La caché nueva pasó la prueba integral del host; una nueva llamada de la conversación observada mantiene aceptación pendiente.
- `.gitignore`: excluir `.idea/` sin modificar ni borrar los archivos del IDE.
- Primer commit local solicitado por el usuario, con la identidad Git ya configurada y una selección explícita de archivos del proyecto. Remoto GitHub pendiente de URL.
- No se cambian Compose, imágenes, modelos, callbacks, dashboards, credenciales ni servicios en este turno.

**6 de octubre de 2026 — ampliación reciente de caché**

| Archivo | Cambio concreto |
| --- | --- |
| `infra/observability/litellm.yaml` | Añadir callback Prometheus nativo, habilitar solo los dos contadores de tokens cache-read/cache-write con etiqueta model, exigir auth en /metrics/ |
| `infra/observability/collector.yaml` | Receiver Prometheus autenticado para LiteLLM; selección de métricas y modelo, etiquetas limitadas; pipeline de caché y estado del scrape |
| `infra/observability/compose.yaml` | Entregar la clave ya existente al Collector para leer métricas autenticadas |
| `infra/observability/grafana/dashboards/platform-overview.json` | Añadir Cache Hit/Write, períodos, tasas, porcentaje y estado del scrape; versión de archivo 5 |
| `infra/observability/grafana/dashboards/llm-cost-routing.json` | Mismo desglose de caché en el dashboard LLM; versión de archivo 3 |
| `scripts/openhands/usage-check.sh` y `.py` | Nuevo diagnóstico de ruta actual y uso numérico de una conversación, sin mensajes ni claves |
| `scripts/observability/check-cache.sh` y `.py` | Cotejar dos llamadas nuevas por LiteLLM con el contador de caché exportado |
| `scripts/observability/test-cache.sh` y `.py` | Prueba aislada con el Collector fijado: auth, acumulados, redacción y fallo HTTP |
| `scripts/observability/test-privacy.py` | Aislar la prueba canaria de la nueva dependencia de scrape del proxy |
| `scripts/observability/validate-config.py` | Verificar que el Collector reciba la credencial requerida sin mostrar su valor |
| `Taskfile.yml` | Tareas openhands:usage:check, observability:cache:check y observability:cache:test |
| `docs/dashboards.md`, `observability.md`, `plan.md` | Documentar fuente, alcance, despliegue y aceptación pendiente |
| `docs/architecture/adr-001-observability.md`, `observability_diagrams.md` | Decisión de integración existente y recorrido de caché |
| `docs/diagnostics/tokens-2026-10-06.md` | Evidencia Ollama real, aclaración de la captura OpenHands y distinta cobertura del proxy |

Preparado y probado aisladamente; después aplicado y validado en el host el 6 de octubre a las 09:57 Europe/Berlin. Dos llamadas sintéticas produjeron 1.623 tokens reutilizados y el contador aumentó exactamente 1.623. Los dashboards cargados por provisioning muestran series reales de caché. Falta cotejar una nueva llamada de la conversación. El ensayo de derivación desde spans no forma parte de la implementación final; se eligió el exportador Prometheus existente que maneja el campo anidado de Ollama.

**5–6 de octubre de 2026 — observabilidad, golden signals y totales**

- Stack Collector/Prometheus/Tempo/Loki/Grafana/LiteLLM/Blackbox fijado por digest, redes internas y solo Grafana publicado en loopback.
- Callback OTel nativo LiteLLM, privacy processors, filelog limitado y tracing nativo OpenHands optativo.
- Master key fuerte persistente fuera de Git/CloudDrive tras rechazo de arranque sin clave; corrección del filtro reservado gen_ai.token.type.
- Siete dashboards y fuentes provisionadas; nueve sondas HTTP, métricas internas del Collector y dos alertas locales.
- Golden signals con alcance explícito; totales acumulados actuales separados de increase del período y rate. No sumar muestras de contadores.
- Aceptación de la pila y petición sintética registrada en `docs/diagnostics/observability-2026-10-06.md`. Correlación completa de una conversación pendiente.

**4–5 de octubre de 2026 — base de entorno y laboratorio local**

- Estructura Git, LICENSE, README, docs, infra y scripts categorizados. Remoto Git pendiente.
- mise con Task fijado y lock; scripts de bootstrap y host con paquetes fijados, APT firmado, backups, NVIDIA runtime y checks.
- Ollama/Qwen3 fijados por digest, pesos en volumen Docker, API loopback, GPU ID 0 y límites; contexto aumentado de 8192 a 32768.
- OpenHands Agent Canvas con estado persistente, workspace /projects, grupo host y Nginx loopback; preservación de variables al usar sudo.
- Pruebas reales de GPU/Docker/inferencia y ejercicios demo/bugfix. Separar tiempo de generación de carga/prefill y comprobación sintética de calidad general del agente.

La [guía con código](infrastructure_walkthrough.md) relaciona estas decisiones con los archivos actuales.

## Seguimiento del consumo y aceptación del host

- Actualizados README, guía de infraestructura, plan, observabilidad, dashboards y diagnóstico con la prueba integral de caché ya aprobada en el host.
- En la UI se volvió a seleccionar `local-qwen3-8b` en la conversación existente, usando su configuración guardada que apunta a LiteLLM. No se modificaron secretos. Falta comprobar una respuesta nueva por esa conversación; los contadores históricos de OpenHands no se importan.

## 6 de octubre de 2026 — YAML mantenido por humanos

- Migrados a YAML `infra/observability/collector` y los manifiestos `versions` de host, LLM, OpenHands y observabilidad. Se conservan valores, tipos, digests y límites.
- Actualizados lectores con `yaml.safe_load`, rutas de Compose, scripts de validación y pruebas de privacidad/caché.
- mise fija Python 3.14.4 y crea el venv; Task coordina scripts `scripts/environment/` para instalar/verificar PyYAML 6.0.3 desde un wheel oficial con hash.
- JSON se conserva para dashboards Grafana, el manifiesto de bootstrap de mise, respuestas/API y artefactos generados automáticamente.
- La pila en ejecución no se reinicia para cambiar únicamente el formato. La configuración YAML y la generación de overrides se validan antes de su próxima aplicación.

- Diagnóstico confirmado: la conversación inspeccionada seguía en `direct Ollama`, aunque el perfil guardado se había editado. Preparadas `openhands:route:proxy` (cambio verificado de conversación/default) y `observability:stream:check` (uso SSE→contadores). Aplicadas ambas tareas en el host: ruta efectiva/default LiteLLM y streaming activo; prueba SSE con incremento exacto 23/8. Grafana confirmó después entrada 16.646, salida 2.243 y total 18.889. No hubo cambio de consultas ni importación de tokens históricos. La correlación completa por conversación sigue pendiente.


## 7 de octubre de 2026 — Ambiente en mise, operación en Task

- Movidas las tareas de preparación/validación env/Python/GPU/Docker/repositorio a mise, con llamadas breves a scripts categorizados. Sin aliases duplicados en Task.
- `scripts/environment/plan.sh`, `setup.sh` y `check.sh` conservan orden secuencial y fallo inmediato. Los scripts del host mantienen sus acciones y controles originales.
- Task conserva despliegues, logs, estado, inferencia, telemetría y tests de código. Los despliegues usan `mise run repo:check` como preflight.
- Retirado el agregador `dev:check`: ambiente e inferencia se invocan por separado. Actualizadas las guías y mensajes de error. No se modifican versiones ni servicios en ejecución.


- Convención de documentación: los 17 archivos Markdown de `docs/`, incluidos architecture/diagnostics, usan nombres en minúsculas. Se actualizaron enlaces y referencias requeridas por scripts. README.md, LICENSE y AGENTS.md conservan sus nombres convencionales en la raíz.


- Dependencias Python migradas de infra a `pyproject.toml`/`uv.lock` en la raíz. Metadatos y comentarios explican propósito, PyYAML, plataforma y límites del entorno. mise fija uv 0.12.23; setup/check usan uv con lock estricto. Eliminado el requirements anterior, sin duplicar definiciones.

**7 de octubre de 2026 — control de secretos antes de publicar**

- Gitleaks 8.30.1 y artefacto/checksum fijados en mise; regla adicional para la master key local de LiteLLM.
- Nueva tarea Task `security:secrets`, implementada en `scripts/security/`: archivos publicables, contenido staged e historial local completo; reportes redactados y prueba canaria.
- `security:test`: cinco pruebas con el scanner real en repositorios temporales; secretos nuevos, staging divergente, historial borrado, symlinks y credenciales ignoradas.
- `docs/security.md`: cobertura aplicada y propuesta; Semgrep/OSV/Trivy/ASVS todavía pendientes, sin declarar certificación OWASP.
- README registra el repositorio GitHub solicitado; push pendiente de SSH.
