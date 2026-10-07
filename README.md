# Local Agent Platform

A model-agnostic local agent platform with OpenHands, Ollama, Docker Compose, and OpenTelemetry observability. The current implementation provides GPU-backed inference, agent execution, authenticated model routing, and provisioned Grafana dashboards. Decoupled runtime/provider contracts, policy enforcement, and multi-user deployment are planned extensions.

## Getting started

```bash
# Only on a machine where mise is not installed:
bash scripts/bootstrap/install-mise.sh

export PATH="$HOME/.local/bin:$PATH"
mise trust mise.toml
mise install --locked
mise run env:python:setup
mise run repo:hooks:install
mise tasks ls
mise exec -- task --list
mise run env:plan
mise run env:check
```

To prepare Docker/NVIDIA Container Toolkit on a new host, review `mise run env:plan` and run `mise run env:setup` in the host terminal. This requires sudo and can restart Docker. The documented development host already passed Docker/GPU installation checks; use validation tasks rather than reinstalling it.

## Repository layout

- `mise.toml` / `mise.lock`: pinned tools, environment activation, environment setup/checks, and Git hook installation.
- `pyproject.toml` / `uv.lock`: project metadata and resolved Python dependencies with hashes.
- `Taskfile.yml`: service operations, code tests, and commit validation through short task calls.
- `scripts/bootstrap/`, `scripts/environment/`, `scripts/host/`, `scripts/repo/`: implementation of bootstrap, environment, host, and repository checks.
- `scripts/llm/`, `scripts/openhands/`, `scripts/observability/`: service deployment and functional checks.
- `scripts/security/`: redacted secret detection and acceptance tests.
- `infra/`: host/service configuration, pinned versions, image digests, and Grafana provisioning.
- `docs/`: architecture, operating procedures, and recorded validation evidence.
- `artifacts/`: local reports and workspaces, excluded from Git.

## Documentation

- [Infrastructure explained with code](docs/infrastructure_walkthrough.md)
- [Changelog](docs/changelog.md)
- [Implementation plan](docs/plan.md)
- [Environment, mise, uv, and Task](docs/environment.md)
- [Git commit validation](docs/git_hooks.md)
- [Secret detection and security coverage](docs/security.md)
- [Docker/GPU installation](docs/docker_gpu.md)
- [Local LLM inference](docs/local_llm.md)
- [Local OpenHands](docs/openhands.md)
- [Observability: deployment, profiles, logs, and privacy](docs/observability.md)
- [Observability diagrams](docs/architecture/observability_diagrams.md)
- [ADR 001: existing integrations](docs/architecture/adr-001-observability.md)
- [GPU diagnostics](docs/diagnostics/gpu-2026-10-04.md)
- [Project scope and warranty](docs/project_scope.md)

## Current validation status

The host GPU/Docker stack and Ollama/Qwen3 passed the recorded checks; the current model context is 32768 and GPU residency was verified. OpenHands completed the arithmetic demo and Decimal bug repair with independent acceptance checks. The repair required guidance after an invalid tool call.

The observability stack and seven provisioned dashboards passed synthetic-request checks. Cache counters passed host acceptance on October 6, 2026, at 09:57 Europe/Berlin. The inspected conversation was subsequently switched to LiteLLM; a streamed proxy request reported 23 input and 8 output tokens, matching the metric increases. Historical OpenHands usage is not backfilled into Prometheus. Full conversation-to-trace correlation remains pending. See [token diagnostics](docs/diagnostics/tokens-2026-10-06.md).

Repository: [alejandro-onatra/local-agent-platform](https://github.com/alejandro-onatra/local-agent-platform), branch `main`. SSH and the initial push were verified.

Dashboard entry point: [Agent platform overview](http://127.0.0.1:3000/d/platform-overview). See [dashboard coverage](docs/dashboards.md) for metrics and limitations.

## Commit validation and change review

Git hooks are versioned under `.githooks/` and enabled per checkout with `mise run repo:hooks:install`. Before a normal commit, the hook runs `mise exec -- task repo:commit:check`: repository/environment checks, secret detection, and code tests. Any failure stops the commit. These local hooks do not replace CI or branch protection.

`main` tracks `origin/main` at `git@github.com:alejandro-onatra/local-agent-platform.git`. Credentials, reports, model weights, `.venv/`, and IDE files are excluded from Git.

Changes are announced before actions and explained with inline diffs, step by step. The persistent collaboration rules are in [AGENTS.md](AGENTS.md); the implementation record is in [docs/changelog.md](docs/changelog.md).

```bash
git log --oneline
git show --stat HEAD
git diff
```

## License and scope

[MIT](LICENSE). Third-party components retain their own licenses. The project is provided as is, without a warranty, commercial support commitment, or service-level agreement. Review the [project scope](docs/project_scope.md) before adopting it.
