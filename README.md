# Agent Platform — laboratorio pedagógico

Proyecto de aprendizaje para explorar agentes, modelos locales, OpenHands y una plataforma agnóstica con seguridad y observabilidad.

**Uso pedagógico y experimental.** No ofrecemos garantías, soporte comercial ni compromiso de adecuación para producción. Quien lo utilice debe evaluar sus riesgos y requisitos. MIT permite uso comercial; este aviso no modifica sus permisos ni sustituye sus cláusulas de ausencia de garantías y limitación de responsabilidad.

## Inicio

```bash
# Solo para un equipo sin mise:
bash scripts/bootstrap/install-mise.sh

export PATH="$HOME/.local/bin:$PATH"
mise trust mise.toml
mise install
mise exec -- task --list
mise exec -- task env:plan
mise exec -- task env:check
```

Para preparar Docker/Toolkit en un host nuevo: `mise exec -- task env:setup` (requiere sudo). En este equipo Docker/GPU ya están validados; no hace falta repetir la instalación.

## Organización

- `mise.toml`: herramientas y entorno, con Task fijado.
- `Taskfile.yml`: coordinación de tareas mediante llamadas breves.
- `scripts/bootstrap/`, `scripts/host/`, `scripts/repo/`: implementación en scripts shell.
- `scripts/llm/`: servidor, modelo y pruebas; `scripts/openhands/`: despliegue y comprobación de OpenHands.
- `infra/`: configuración y versiones de infraestructura.
- `docs/`: documentación detallada.
- `artifacts/`: informes locales, excluidos de Git.

## Documentación

- [Infraestructura explicada con código](docs/INFRASTRUCTURE_WALKTHROUGH.md)
- [Registro de cambios](docs/CHANGELOG.md)
- [Plan por fases](docs/PLAN.md)
- [Entorno, mise y Task](docs/ENVIRONMENT.md)
- [Instalación Docker/GPU](docs/DOCKER_GPU.md)
- [LLM local: preparación e inferencia](docs/LOCAL_LLM.md)
- [OpenHands local](docs/OPENHANDS.md)
- [Observabilidad: despliegue, perfiles, logs y privacidad](docs/OBSERVABILITY.md)
- [Diagramas de observabilidad](docs/architecture/OBSERVABILITY_DIAGRAMS.md)
- [ADR 001: integraciones existentes](docs/architecture/ADR-001-OBSERVABILITY.md)
- [Diagnóstico GPU](docs/diagnostics/GPU-2026-10-04.md)
- [Aviso pedagógico](docs/EDUCATIONAL_USE.md)

Estado: GPU, Docker y Ollama/Qwen3 validados en el host; contexto 32768 y modelo 100% GPU. OpenHands completó la demo y una reparación de bug: tests originales y aceptación independiente satisfactorios. La reparación requirió guía tras una llamada de herramienta inválida. Ver `docs/OPENHANDS.md`. La pila de observabilidad y siete dashboards provisionados ya pasaron el chequeo del host para una petición sintética. El desglose de caché ya pasó la prueba integral del host el 6 de octubre a las 09:57 Europe/Berlin. Falta confirmar una nueva llamada de la conversación OpenHands después de volver a seleccionar su perfil guardado. Ver `docs/diagnostics/TOKENS-2026-10-06.md`. Remoto Git y usuario GitHub pendientes de indicar.

## Licencia

[MIT](LICENSE). Los componentes de terceros mantienen sus propias licencias.

Dashboard de entrada: [Plataforma de agentes · Vista general](http://127.0.0.1:3000/d/platform-overview). Diseño, cobertura y diagnóstico: [docs/DASHBOARDS.md](docs/DASHBOARDS.md).

## Revisión de cambios y Git

Repositorio local en rama `main`. La instantánea inicial incluye infraestructura, scripts, pruebas y documentación; `.idea/`, reportes, pesos y credenciales quedan excluidos. El remoto GitHub se añadirá cuando se proporcione su URL.

```bash
git log --oneline
git show --stat HEAD
git diff
```

Las modificaciones se anuncian antes de editar y se entregan con enlaces, diff o fragmentos y validación. La regla está en [AGENTS.md](AGENTS.md); el detalle está en [docs/CHANGELOG.md](docs/CHANGELOG.md).
