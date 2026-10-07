# Agent Platform — laboratorio pedagógico

Proyecto de aprendizaje para explorar agentes, modelos locales, OpenHands y una plataforma agnóstica con seguridad y observabilidad.

**Uso pedagógico y experimental.** No ofrecemos garantías, soporte comercial ni compromiso de adecuación para producción. Quien lo utilice debe evaluar sus riesgos y requisitos. MIT permite uso comercial; este aviso no modifica sus permisos ni sustituye sus cláusulas de ausencia de garantías y limitación de responsabilidad.

## Inicio

```bash
# Solo para un equipo sin mise:
bash scripts/bootstrap/install-mise.sh

export PATH="$HOME/.local/bin:$PATH"
mise trust mise.toml
mise install --locked
mise run env:python:setup
mise tasks ls
mise exec -- task --list
mise run env:plan
mise run env:check
```

Para preparar Docker/Toolkit en un host nuevo: `mise run env:setup` (requiere sudo). En este equipo Docker/GPU ya están validados; no hace falta repetir la instalación.

## Organización

- `mise.toml`: Python, uv y Task fijados; activación y tareas de preparación/validación del ambiente.
- `pyproject.toml` / `uv.lock`: descripción del proyecto y dependencias Python resueltas con hashes.
- `Taskfile.yml`: operación de servicios y tests de código mediante llamadas breves.
- `scripts/bootstrap/`, `scripts/host/`, `scripts/repo/`: implementación en scripts shell.
- `scripts/llm/`: servidor, modelo y pruebas; `scripts/openhands/`: despliegue y comprobación de OpenHands.
- `infra/`: configuración y versiones de infraestructura.
- `docs/`: documentación detallada.
- `artifacts/`: informes locales, excluidos de Git.

## Documentación

- [Infraestructura explicada con código](docs/infrastructure_walkthrough.md)
- [Registro de cambios](docs/changelog.md)
- [Plan por fases](docs/plan.md)
- [Entorno, mise y Task](docs/environment.md)
- [Control de secretos y cobertura de seguridad](docs/security.md)
- [Instalación Docker/GPU](docs/docker_gpu.md)
- [LLM local: preparación e inferencia](docs/local_llm.md)
- [OpenHands local](docs/openhands.md)
- [Observabilidad: despliegue, perfiles, logs y privacidad](docs/observability.md)
- [Diagramas de observabilidad](docs/architecture/observability_diagrams.md)
- [ADR 001: integraciones existentes](docs/architecture/adr-001-observability.md)
- [Diagnóstico GPU](docs/diagnostics/gpu-2026-10-04.md)
- [Aviso pedagógico](docs/educational_use.md)

Estado: GPU, Docker y Ollama/Qwen3 validados en el host; contexto 32768 y modelo 100% GPU. OpenHands completó la demo y una reparación de bug: tests originales y aceptación independiente satisfactorios. La reparación requirió guía tras una llamada de herramienta inválida. Ver `docs/openhands.md`. La pila de observabilidad y siete dashboards provisionados ya pasaron el chequeo del host para una petición sintética. El desglose de caché ya pasó la prueba integral del host el 6 de octubre a las 09:57 Europe/Berlin. Falta confirmar una nueva llamada de la conversación OpenHands después de volver a seleccionar su perfil guardado. Ver `docs/diagnostics/tokens-2026-10-06.md`. Repositorio GitHub indicado: `git@github.com:alejandro-onatra/local-agent-platform.git`; publicación pendiente de validar SSH.

## Licencia

[MIT](LICENSE). Los componentes de terceros mantienen sus propias licencias.

Dashboard de entrada: [Plataforma de agentes · Vista general](http://127.0.0.1:3000/d/platform-overview). Diseño, cobertura y diagnóstico: [docs/dashboards.md](docs/dashboards.md).

## Revisión de cambios y Git

Repositorio local en rama `main`. La instantánea inicial incluye infraestructura, scripts, pruebas y documentación; `.idea/`, reportes, pesos y credenciales quedan excluidos. Remoto solicitado: `git@github.com:alejandro-onatra/local-agent-platform.git`. Antes de publicar, ejecutar `mise exec -- task security:secrets`; publicación pendiente de validar SSH.

```bash
git log --oneline
git show --stat HEAD
git diff
```

Las modificaciones se anuncian antes de editar y se entregan con enlaces, diff o fragmentos y validación. La regla está en [AGENTS.md](AGENTS.md); el detalle está en [docs/changelog.md](docs/changelog.md).
