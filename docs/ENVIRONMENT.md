# Entorno de desarrollo reproducible

## Responsabilidades

| Componente | Responsabilidad |
| --- | --- |
| `mise.toml` | Versiones de herramientas de desarrollo y entorno; por ahora Task 3.54.0. |
| `mise.lock` | Resolución y checksums de Task generados mediante mise. |
| `Taskfile.yml` | Tareas públicas y su orden de ejecución. |
| `scripts/bootstrap/` | Instalación inicial de mise, fuera del propio gestor. |
| `scripts/host/` | GPU, instalación Docker/Toolkit y comprobaciones del host. |
| `scripts/repo/` | Validación de estructura y sintaxis. |
| `scripts/llm/` / `scripts/openhands/` | Automatización futura del modelo y del agente. |
| `infra/host/` | Versiones APT, imágenes de prueba y versión/checksum del bootstrap mise. |
| `infra/` | Futura configuración Compose de servicios. |

mise prepara las herramientas; go-task coordina operaciones; los scripts contienen la lógica. Tanto mise.toml como Taskfile.yml se mantienen breves. No se instala Go para usar Task: se utiliza su binario publicado.

## Bootstrap en Linux x86_64

Python 3 y acceso HTTPS son requisitos iniciales. En este equipo mise 2026.10.2 ya está en `~/.local/bin/mise`. Para otro equipo:

```bash
bash scripts/bootstrap/install-mise.sh
```

El script usa la versión y checksums de `infra/host/mise-version.json`, no ejecuta código descargado directamente ni sobrescribe otro binario. El checksum verifica coincidencia con el artefacto revisado; no constituye una verificación independiente de firma.

## Preparar las herramientas del proyecto

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
export PATH="$HOME/.local/bin:$PATH"
mise trust mise.toml
mise install
mise exec -- task --list
```

`mise trust` autoriza la configuración local. Revisar el repositorio antes de confiar en él. La exportación de PATH afecta solo la terminal actual; no se han editado los archivos de inicio del shell.

`mise install` instala las herramientas de desarrollo fijadas, actualmente Task. No instala Docker ni modifica drivers. Para el host se usa la tarea explícita correspondiente.

## Operar el entorno

```bash
mise exec -- task env:plan
mise exec -- task env:check
# En un host nuevo, tras revisar el plan:
mise exec -- task env:setup
```

Si activas mise en tu shell, puedes usar directamente `task env:check`. `mise exec --` funciona sin necesitar esa activación.

| Tarea | Alcance |
| --- | --- |
| `env:plan` | Estructura y vista previa de instalación. |
| `env:setup` | Comprueba GPU y prepara Docker/Toolkit; necesita sudo y puede reiniciar Docker. |
| `env:check` | Comprueba host y contenedor sin reinstalar servicios. |
| `repo:check` | Estructura y sintaxis de todos los scripts, incluidos subdirectorios. |
| `gpu:check` | Consulta del driver en el host. |
| `docker:plan` / `docker:install` / `docker:check` | Operaciones individuales de Docker. |

Las tareas compuestas llaman otras tareas secuencialmente mediante `cmds`; fallan si un paso falla. No se utilizan dependencias paralelas para instalar/verificar servicios. Las comprobaciones pueden descargar las imágenes de prueba si faltan y guardan informes en `artifacts/diagnostics/`, excluidos de Git.

Como este host ya está instalado y validado, usar `env:check`. `env:setup` es para instalar/configurar el host cuando corresponda.

## Reproducibilidad y seguridad

- Fijar herramientas con mise y conservar su lockfile.
- Fijar versiones directas APT y digests de imágenes en el lock de host.
- Documentar kernel, GPU y driver; mise no congela esas capas ni las dependencias transitivas del sistema.
- No guardar secretos ni contenido sensible en Git o diagnósticos.
- Mantener documentación detallada en `docs/`, código operativo en `scripts/` y configuración en `infra/`.
- Validar cada capa antes de añadir la siguiente.
- No reemplazar drivers ni reiniciar servicios usados sin revisar el impacto.

## Validaciones registradas

El 4 de octubre de 2026 el usuario ejecutó la antigua tarea `mise run env:check` desde la terminal del host y pasaron repositorio, GPU y Docker/GPU. Esa ejecución precede a la separación en go-task.

- GPU: RTX 4060 Ti, 16380 MiB, driver 580.178.04.
- Docker 29.8.2, Compose 5.6.0, Buildx 0.37.1 y GPU dentro de un contenedor.
- Informes: `artifacts/diagnostics/gpu-20261004T205604Z-BXWpeu.txt` y `artifacts/diagnostics/docker-gpu-20261004T205608Z-Zn1rK0.txt`.

La validación completa mediante go-task deberá ejecutarse en la terminal del host porque Work no ve los dispositivos NVIDIA ni puede usar sudo. Las tareas sin privilegios se verifican desde Work.

## Siguiente ampliación

Las tareas `llm:*` ya preparan Ollama y Qwen3 8B; `dev:check` combina el host y la inferencia. Ver [LLM local](LOCAL_LLM.md). Su validación de ejecución está pendiente en el host. OpenHands será la siguiente ampliación.

Referencias: [mise](https://mise.jdx.dev/dev-tools/), [go-task](https://taskfile.dev/docs/installation), [Docker/GPU](DOCKER_GPU.md).

## Validación de la reorganización

Se generó `mise.lock`, se instaló Task 3.54.0 en un directorio temporal de validación y se ejecutó `mise exec -- task env:plan` correctamente. También pasó la comprobación de sintaxis de los scripts trasladados.

El sandbox no permitió escribir en la caché habitual de mise. La instalación temporal verifica el flujo, pero no equivale a dejar Task instalado en el directorio persistente del usuario. Desde la terminal normal del host, ejecutar `mise install` y después `mise exec -- task env:check` para validar el flujo reorganizado con la GPU.

## Observabilidad: tareas y configuración

La ampliación usa imágenes fijadas en `infra/observability/versions.json`; mise sigue gestionando Task, no servicios del sistema. `Taskfile.yml` coordina `observability:*` con scripts breves en `scripts/observability/`. Configuraciones y seis dashboards están bajo `infra/observability/`; la [guía](OBSERVABILITY.md) recoge arranque, perfiles, comprobaciones y límites. Collector usa un único archivo fuente JSON compatible con su loader, sin dependencia YAML en el Python del host. Las credenciales de Grafana se guardan fuera de Git y CloudDrive. La pila completa sigue pendiente de validar en Docker.
