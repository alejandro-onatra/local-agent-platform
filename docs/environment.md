# Entorno de desarrollo reproducible

## Responsabilidades

| Componente | Responsabilidad |
| --- | --- |
| `mise.toml` | Versiones de Task/Python/uv, venv y preparación/validación del ambiente. |
| `mise.lock` | Resolución y checksums de herramientas para la plataforma fijada. |
| `pyproject.toml` / `uv.lock` | Metadatos, dependencias Python y resolución de paquetes con hashes. |
| `Taskfile.yml` | Despliegue y operación de servicios, pruebas funcionales y tests de código. |
| `scripts/bootstrap/` | Instalar mise antes de poder utilizarlo. |
| `scripts/environment/` | Secuencias de preparación/validación y dependencias Python. |
| `scripts/host/` | GPU, Docker/Toolkit y comprobaciones del host. |
| `scripts/repo/` | Estructura/sintaxis del repositorio y ejecución de tests. |
| `scripts/llm/`, `scripts/openhands/`, `scripts/observability/` | Operación de los servicios y comprobaciones funcionales. |
| `infra/` | Configuración de servicios, versiones APT, digests de imágenes y dependencias fijadas. |

mise prepara y valida el ambiente; Task opera los servicios. Ambos contienen llamadas breves y los scripts contienen la lógica. Instalar Python/PyYAML/Docker/Toolkit pertenece al ambiente. Arrancar Ollama/OpenHands, descargar pesos, consultar logs y comprobar una inferencia o telemetría pertenecen a la operación de la plataforma. Los tests de código siguen en Task; no comprueban la instalación del ambiente.

## Bootstrap y herramientas

Linux x86_64/glibc es el objetivo actual. Python estándar y acceso HTTPS son los requisitos iniciales del bootstrap:

```bash
# Solo si mise aún no existe:
bash scripts/bootstrap/install-mise.sh
export PATH="$HOME/.local/bin:$PATH"
mise trust mise.toml
mise install --locked
mise run env:python:setup
mise tasks ls
mise exec -- task --list
```

El bootstrap utiliza `infra/host/mise-version.json` y sus checksums antes de disponer de PyYAML. mise fija Task 3.54.0, Python 3.14.4 y uv 0.12.23. mise crea/activa `.venv`; `env:python:setup` ejecuta `uv sync --locked` con las dependencias de `pyproject.toml` y los artefactos/hashes de `uv.lock`. La dependencia actual es PyYAML 6.0.3 para leer configuración YAML. No se instala en Python del sistema ni requiere sudo. El proyecto exige Python 3.14.4 y el lock cubre Linux x86_64. uv no descarga intérpretes ni compila paquetes: mise suministra Python y uv instala wheels del lock.

`mise install --locked` instala las herramientas; la instalación Docker/Toolkit es una acción explícita separada. No se editan automáticamente los archivos de inicio del shell. `mise run` activa el entorno para sus tareas; para ejecutar Task sin activar mise en el shell se usa `mise exec -- task ...`.

## Preparar y validar el ambiente con mise

```bash
mise run env:plan
mise run env:check
# Host nuevo, tras revisar el plan:
mise run env:setup
```

| Comando | Alcance |
| --- | --- |
| `mise run env:plan` | Python/PyYAML, estructura y vista previa del instalador del host. |
| `mise run env:setup` | Dependencias Python, estructura, GPU e instalación Docker/Toolkit. |
| `mise run env:check` | Python/PyYAML, estructura, GPU y Docker/GPU. |
| `mise run env:python:setup` / `env:python:check` | Dependencias Python o comprobación de versiones/venv. |
| `mise run repo:check` | Estructura y sintaxis de scripts. |
| `mise run gpu:check` | Consulta del driver NVIDIA del host. |
| `mise run docker:plan` / `docker:install` / `docker:check` | Vista previa, instalación o comprobación Docker/Toolkit. |

Las tareas compuestas llaman un script de `scripts/environment/`, que ejecuta los pasos secuencialmente y se detiene al primer error. No usa dependencias paralelas para preparar el host. `env:setup` necesita sudo y puede reiniciar Docker; el instalador se detiene si detecta contenedores activos. En este equipo el host ya fue instalado y validado: utilizar las comprobaciones, no repetir la instalación.

GPU/Docker se comprueban en la terminal normal del host: esta sesión no puede autenticar sudo interactivo ni acceder a todos los dispositivos. Las comprobaciones Docker pueden descargar las imágenes de prueba si faltan. Los informes permanecen en `artifacts/diagnostics/`, excluidos de Git.

## Operar servicios con Task

```bash
mise exec -- task llm:status
mise exec -- task openhands:status
mise exec -- task observability:status
mise exec -- task llm:check
mise exec -- task observability:stream:check
```

`llm:setup`, `openhands:setup` y `observability:setup` son despliegues de servicios, no instaladores de paquetes del host. Su preflight de estructura llama `mise run repo:check`; esa tarea no se duplica en Task. Se retiró el agregador `dev:check`, que mezclaba host e inferencia: ahora ejecutar `mise run env:check` y después `mise exec -- task llm:check`.

## Reproducibilidad y estado

- Herramientas, dependencias Python, versiones directas APT y digests de imágenes están fijados. Kernel, driver y dependencias transitivas del sistema no quedan congelados por mise.
- Configuración mantenida en YAML; dashboards, bootstrap y artefactos generados conservan JSON. Credenciales fuera de Git y CloudDrive.
- El usuario validó el 4 de octubre de 2026 la RTX 4060 Ti 16 GB, driver 580.178.04, Docker 29.8.2, Compose 5.6.0, Buildx 0.37.1 y GPU dentro del contenedor. Informes originales: `gpu-20261004T205604Z-BXWpeu.txt` y `docker-gpu-20261004T205608Z-Zn1rK0.txt` en artifacts/diagnostics.
- Ollama/OpenHands y la pila de observabilidad ya pasaron las pruebas del host documentadas. El cambio de responsables de las tareas no reinstala ni reinicia esa pila.
- El 7 de octubre de 2026 se corrigió la separación: ambiente en mise, operación en Task. La configuración y los pasos sin privilegios se validan por separado del chequeo completo GPU/Docker en el host.

Referencias: [tareas TOML de mise](https://mise.jdx.dev/tasks/toml-tasks.html), [go-task](https://taskfile.dev/docs/installation), [Docker/GPU](docker_gpu.md), [LLM local](local_llm.md) y [observabilidad](observability.md).


## Dependencias Python con uv

`pyproject.toml` contiene metadatos y explica cada dependencia/configuración. `uv.lock` registra la resolución, versiones y hashes; se conserva en Git. `.venv` contiene instalaciones locales y queda fuera de Git. `infra/` contiene infraestructura del host/servicios, no requirements Python.

```bash
# Preparar o restaurar exactamente el entorno:
mise run env:python:setup
# Comprobar sin instalar ni actualizar el lock:
mise run env:python:check
# Tras editar dependencias en pyproject.toml, regenerar el lock deliberadamente:
mise exec -- uv lock
```

Actualizar una dependencia requiere revisar el diff de `pyproject.toml`/`uv.lock`, sincronizar y comprobar los scripts afectados. `--locked` falla si los metadatos y el lock no coinciden; no selecciona silenciosamente otra versión. Los tests actuales usan unittest de la biblioteca estándar y no requieren pytest. El runtime Python de los contenedores permanece definido por sus imágenes fijadas.

Validación del 7 de octubre: preparación/check con uv, vista previa del ambiente, referencias mise/Task y Compose aprobados; 26 tests existentes aprobados; 64 enlaces locales resueltos. Un venv temporal limpio se restauró desde uv.lock y la comprobación detectó una dependencia ausente sin instalarla ni alterar el lock. No se reinstalaron paquetes del host ni se reiniciaron contenedores. El chequeo completo GPU/Docker por la nueva tarea sigue siendo una operación de la terminal del host.
