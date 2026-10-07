# Reproducible Development Environment

## Responsibilities

| Component | Responsibility |
| --- | --- |
| `mise.toml` | Task/Python/uv/Gitleaks versions, venv, environment setup/checks and hook installation. |
| `mise.lock` | Resolution and checksums of tools for the fixed platform. |
| `pyproject.toml` / `uv.lock` | Metadata, Python dependencies and package resolution with hashes. |
| `Taskfile.yml` | Deployment and operation of services, functional testing and code tests. |
| `scripts/bootstrap/` | Install mise before being able to use it. |
| `scripts/environment/` | Preparation/validation sequences and Python dependencies. |
| `scripts/host/` | GPU, Docker/Toolkit and host checks. |
| `scripts/repo/` | Repository structure/syntax and execution of tests. |
| `scripts/llm/`, `scripts/openhands/`, `scripts/observability/` | Operation of the services and functional checks. |
| `infra/` | Service configuration, APT versions, image digests and fixed dependencies. |

mise prepares and validates the environment; Task operates the services. Both contain brief calls and the scripts contain the logic. Installing Python/PyYAML/Docker/Toolkit belongs to the environment. Starting Ollama/OpenHands, downloading weights, consulting logs and verifying an inference or telemetry belong to the operation of the platform. The code tests remain in Task; they do not check the installation of the environment.

## Bootstrap and Tools

Linux x86_64/glibc is the current target. Standard Python and HTTPS access are the initial requirements of the bootstrap:

```bash
# Only if mise is not installed:
bash scripts/bootstrap/install-mise.sh
export PATH="$HOME/.local/bin:$PATH"
mise trust mise.toml
mise install --locked
mise run env:python:setup
mise tasks ls
mise exec -- task --list
```

The bootstrap uses `infra/host/mise-version.json` and its checksums before having PyYAML. mise pins Task 3.54.0, Python 3.14.4, uv 0.12.23 and Gitleaks 8.30.1. mise creates/activates `.venv`; `env:python:setup` runs `uv sync --locked` with the dependencies of `pyproject.toml` and the artifacts/hashes of `uv.lock`. The current dependency is PyYAML 6.0.3 for reading YAML configuration. It is not installed in the system Python and does not require sudo. The project requires Python 3.14.4 and the lock covers Linux x86_64. uv does not download interpreters or compile packages: mise supplies Python and uv installs wheels from the lock.

`mise install --locked` installs the tools; the Docker/Toolkit installation is a separate explicit action. Shell startup files are not edited automatically. `mise run` activates the environment for its tasks; to run Task without activating mise in the shell, `mise exec -- task ...` is used.

## Prepare and Validate the Environment with mise

```bash
mise run env:plan
mise run env:check
# New host, after reviewing the plan:
mise run env:setup
```

| Command | Scope |
| --- | --- |
| `mise run env:plan` | Python/PyYAML, structure and host installer preview. |
| `mise run env:setup` | Python dependencies, structure, GPU and Docker/Toolkit installation. |
| `mise run env:check` | Python/PyYAML, structure, GPU and Docker/GPU. |
| `mise run env:python:setup` / `env:python:check` | Python dependencies or version/check version/venv. |
| `mise run repo:check` | Script structure and syntax. |
| `mise run gpu:check` | Host NVIDIA driver check. |
| `mise run docker:plan` / `docker:install` / `docker:check` | Preview, installation or Docker/Toolkit check. |

Composite tasks call a `scripts/environment/` script, which executes the steps sequentially and stops at the first error. It does not use parallel dependencies to prepare the host. `env:setup` requires sudo and can restart Docker; the installer stops if it detects active containers. On this machine, the host has already been installed and validated: use the checks, do not repeat the installation.

GPU/Docker are checked in the normal host terminal session: this session cannot authenticate interactive sudo or access all devices. Docker checks can download test images if they are missing. Reports remain in `artifacts/diagnostics/`, excluded from Git.

## Operate Services with Task

```bash
mise exec -- task llm:status
mise exec -- task openhands:status
mise exec -- task observability:status
mise exec -- task llm:check
mise exec -- task observability:stream:check
```

`llm:setup`, `openhands:setup` and `observability:setup` are service deployments, not host package installers. Their structure preflight calls `mise run repo:check`; this task is not duplicated in Task. The aggregator `dev:check`, which mixed host and inference, has been removed: now run `mise run env:check` and then `mise exec -- task llm:check`.

## Reproducibility and State

- Tools, Python dependencies, direct APT versions and image digests are fixed. Kernel, driver and system transitive dependencies are not frozen by mise.
- Configuration is maintained in YAML; dashboards, bootstrap and generated artifacts retain JSON. Credentials outside of Git and CloudDrive.
- The user validated October 4, 2026 the RTX 4060 Ti 16 GB, driver 580.178.04, Docker 29.8.2, Compose 5.6.0, Buildx 0.37.1 and GPU inside the container. Original reports: `gpu-20261004T205604Z-BXWpeu.txt` and `docker-gpu-20261004T205608Z-Zn1rK0.txt` in artifacts/diagnostics.
- Ollama/OpenHands and the observability stack have already passed the documented host tests. The change of task owners does not reinstall or restart that stack.
- The October 7, 2026 corrected the separation: environment in mise, operation in Task. The configuration and the privilege-less steps are validated separately from the full GPU/Docker check on the host.

References: [mise TOML tasks](https://mise.jdx.dev/tasks/toml-tasks.html), [go-task](https://taskfile.dev/docs/installation), [Docker/GPU](docker_gpu.md), [LLM local](local_llm.md) and [observability](observability.md).


## Python Dependencies with uv

`pyproject.toml` contains metadata and explains each dependency/configuration. `uv.lock` records the resolution, versions and hashes; it is preserved in Git. `.venv` contains local installations and is outside of Git. `infra/` contains host/service infrastructure, not Python requirements.

```bash
# Prepare or restore the exact environment:
mise run env:python:setup
# Check without installing or updating the lock:
mise run env:python:check
# After editing pyproject.toml dependencies, deliberately regenerate the lock:
mise exec -- uv lock
```

Updating a dependency requires reviewing the diff of `pyproject.toml`/`uv.lock`, synchronizing and checking the affected scripts. `--locked` fails if the metadata and the lock do not match; it does not silently select another version. Current tests use unittest from the standard library and do not require pytest. The Python runtime of the containers remains defined by their pinned images.

Validation of October 7: preparation/check with uv, environment preview, mise/Task and Compose approvals; 26 existing tests approved; 64 local links resolved. A clean temporary venv was restored from uv.lock and the check detected an absent dependency without installing it or altering the lock. No host packages were reinstalled and no containers were restarted. The full GPU/Docker check by the new task remains an operation of the host terminal session.

## Git hooks

Install the versioned hook for each checkout with `mise run repo:hooks:install`; verify it with `mise run repo:hooks:check`. The hook runs the code/security validation sequence from Task on every normal commit. See [Git commit validation](git_hooks.md) for the exact checks and local enforcement limits.
