# Change Log of the Local Agent Platform

This log summarizes decisions and verifiable files. Before this review, the repository had no commits: the previous entries are retrospective and supported by current configuration and reports, not an exact diff of all revisions. The initial local snapshot of this run establishes the first Git baseline.

**October 6, 2026 — transparency and infrastructure guide (this run)**

- New `AGENTS.md`: save the user's instruction to announce and display modifications always, with code/diff, validation, and application status.
- New `docs/infrastructure_walkthrough.md`: explain host/GPU, mise/Task, Ollama, OpenHands, permissions, networks, LiteLLM, privacy, logs, backends, provisioning, golden signals, totals, cache, and pending limits through fragments of the actual files.
- The guide includes the optional location of LangChain/LangGraph and an explicitly non-installed and non-executed example, in response to the user's question.
- New `docs/changelog.md`: centralize this change log and separate retrospective reconstruction from real diff.
- `README.md`: link guide/log and correct the old observability status with the already registered acceptance. The new cache passed the host's full test; a new observed conversation call maintains pending acceptance.
- `.gitignore`: exclude `.idea/` without modifying or deleting the IDE files.
- First local commit requested by the user, with Git identity already configured and an explicit selection of project files. Remote GitHub pending URL.
- No changes to Compose, images, models, callbacks, dashboards, credentials, or services in this run.

**October 6, 2026 — recent cache expansion**

| File | Concrete Change |
| --- | --- |
| `infra/observability/litellm.yaml` | Add native Prometheus callback, enable only the two token counters cache-read/cache-write with model label, require auth in /metrics/ |
| `infra/observability/collector.yaml` | Authenticated Prometheus receiver for LiteLLM; metric and model selection, limited labels; cache pipeline and scrape status |
| `infra/observability/compose.yaml` | Deliver the existing key to the Collector for reading authenticated metrics |
| `infra/observability/grafana/dashboards/platform-overview.json` | Add Cache Hit/Write, periods, rates, percentage, and scrape status; file version 5 |
| `infra/observability/grafana/dashboards/llm-cost-routing.json` | Same cache breakdown in the LLM dashboard; file version 3 |
| `scripts/openhands/usage-check.sh` and `.py` | New route diagnostics and numeric usage of a conversation, without messages or keys |
| `scripts/observability/check-cache.sh` and `.py` | Compare two new LiteLLM calls with the exported cache counter |
| `scripts/observability/test-cache.sh` and `.py` | Isolated test with the pinned Collector: auth, accumulated, redaction, and HTTP failure |
| `scripts/observability/test-privacy.py` | Isolate the canary test of the new scrape dependency from the proxy |
| `scripts/observability/validate-config.py` | Verify that the Collector receives the required credential without displaying its value |
| `Taskfile.yml` | `openhands:usage:check`, `observability:cache:check` and `observability:cache:test` |
| `docs/dashboards.md`, `observability.md`, `plan.md` | Document source, scope, deployment, and pending acceptance |
| `docs/architecture/adr-001-observability.md`, `observability_diagrams.md` | Decision of existing integration and cache traversal |
| `docs/diagnostics/tokens-2026-10-06.md` | Real Ollama evidence, clarification of the OpenHands capture and different proxy coverage |

Prepared and tested in isolation; after that applied and validated on the host on October 6 at 09:57 Europe/Berlin. Two synthetic calls produced 1,623 tokens reused and the counter increased exactly 1,623. The dashboards loaded by provisioning show real cache series. Missing to compare a new conversation call. The derivation test from spans does not form part of the final implementation; the existing Prometheus exporter was chosen that handles the nested field of Ollama.

**October 5–6, 2026 — observability, golden signals and totals**

- Stack Collector/Prometheus/Tempo/Loki/Grafana/LiteLLM/Blackbox pinned by digest, internal networks and only Grafana published in loopback.
- Native LiteLLM OTel callback, privacy processors, limited filelog and optional native OpenHands tracing.
- Strong persistent master key outside of Git/CloudDrive after rejection of startup without key; correction of the reserved filter gen_ai.token.type.
- Seven dashboards and sources provisioned; nine HTTP probes, internal Collector metrics and two local alerts.
- Golden signals with explicit scope; current accumulated totals separated from period increase and rate. Do not sum counter samples.
- Acceptance of the stack and synthetic request registered in `docs/diagnostics/observability-2026-10-06.md`. Full correlation of a pending conversation.

**October 4–5, 2026 — environment base and local platform**

- Git structure, LICENSE, README, docs, infra and scripts categorized. Remote Git pending.
- mise with Task pinned and locked; bootstrap and host scripts with pinned packages, signed APT, backups, NVIDIA runtime and checks.
- Ollama/Qwen3 pinned by digest, weights in Docker volume, API loopback, GPU ID 0 and limits; context increased from 8192 to 32768.
- OpenHands Agent Canvas with persistent state, workspace /projects, host group and Nginx loopback; preservation of variables when using sudo.
- Real GPU/Docker/inference tests and demo/bugfix exercises. Separate generation time from load/prefill and synthetic check of general agent quality.

The [code guide](infrastructure_walkthrough.md) relates these decisions to the current files.

## Host Consumption and Acceptance Tracking

- Updated README, infrastructure guide, plan, observability, dashboards, and diagnostics with the cache full test already approved on the host.
- In the UI, `local-qwen3-8b` was reselected in the existing conversation, using its saved configuration pointing to LiteLLM. Secrets were not modified. Missing to check a new response for that conversation; the historical OpenHands counters are not imported.

## October 6, 2026 — YAML maintained by humans

- Migrated to YAML `infra/observability/collector` and the manifests `versions` of host, LLM, OpenHands and observability. Values, types, digests and limits are preserved.
- Updated readers with `yaml.safe_load`, Compose paths, validation scripts and privacy/cache tests.
- Pinned Python 3.14.4 and created the venv; Task coordinates scripts `scripts/environment/` to install/verify PyYAML 6.0.3 from an official wheel with hash.
- JSON is preserved for Grafana dashboards, the bootstrap manifest of mise, API responses/artifacts and automatically generated artifacts.
- The running stack is not restarted to change only the format. YAML configuration and override generation are validated before their next application.

- Confirmed diagnosis: the inspected conversation was still in `direct Ollama`, although the saved profile had been edited. Prepared `openhands:route:proxy` (verified conversation/default change) and `observability:stream:check` (SSE→counters usage). Both tasks were applied on the host: effective/default LiteLLM path and active streaming; SSE test with exact increment 23/8. Grafana confirmed later input 16,646, output 2,243 and total 18,889. There was no change in queries or import of historical tokens. Full conversation correlation is still pending.


## October 7, 2026 — Environment in mise, operation in Task

- Moved preparation/validation tasks env/Python/GPU/Docker/repository to mise, with brief calls to categorized scripts. No duplicated aliases in Task.
- `scripts/environment/plan.sh`, `setup.sh` and `check.sh` preserve sequential order and immediate failure. Host scripts maintain their original actions and controls.
- Task preserves deployments, logs, state, inference, telemetry and code tests. Deployments use `mise run repo:check` as preflight.
- Removed the aggregator `dev:check`: environment and inference are invoked separately. Updated guides and error messages. No versions or running services are modified.


- Documentation convention: the 17 Markdown files of `docs/`, including architecture/diagnostics, use lowercase names. Links and references required by scripts were updated. README.md, LICENSE and AGENTS.md retain their conventional names at the root.


- Python dependencies migrated from infra to `pyproject.toml`/`uv.lock` at the root. Metadata and comments explain purpose, PyYAML, platform and environment limits. mise fixes uv 0.12.23; setup/check use uv with strict lock. The previous requirements were removed, without duplicating definitions.

**October 7, 2026 — secret control before publishing**

- Gitleaks 8.30.1 and artifact/checksum fixed in mise; additional rule for the local master key of LiteLLM.
- New Task `security:secrets`, implemented in `scripts/security/`: publishable files, staged content and complete local history; redacted reports and canary test.
- `security:test`: five tests with the real scanner in temporary repositories; new secrets, divergent staging, deleted history, symlinks and credentials ignored.
- `docs/security.md`: coverage applied and proposed; Semgrep/OSV/Trivy/ASVS still pending, without declaring OWASP certification.
- README registers the requested GitHub repository; SSH push pending.

**October 7, 2026 — publishing and inline review**

- First push completed: `main` in `alejandro-onatra/local-agent-platform`; commit `320fe6c` verified with GitHub via SSH.
- `AGENTS.md` preserves the preference to announce each action block, explain method/purpose and show inline diffs step by step. A link to the patch does not replace that explanation.
- README registers real publication and tracking of `origin/main`; secrets, artifacts and local environments remain outside the repository.

## October 7, 2026 — English documentation and commit validation

- Translated repository documentation, diagram labels and example comments to English. Technical commands, paths, versions and recorded evidence are preserved; token thousands use English separators.
- Replaced educational-use framing with `docs/project_scope.md`; kept the MIT license and its warranty terms.
- Saved the requirement to announce actions and explain actual inline diffs step by step in `AGENTS.md`.
- Set the GitHub repository description to: Model-agnostic local agent platform with OpenHands, Ollama, Docker Compose, and OpenTelemetry observability.
- Added versioned `.githooks/pre-commit`, safe local installation/check scripts and corresponding mise tasks. Task owns the sequential environment/code/security validation calls. The hook is active in this checkout and performs no package installation or Docker operations.
- Added disposable-clone tests for clean commits, rejected secrets, invalid shell syntax and preservation of a different existing hooks path. Isolated inherited Git environment variables in the nested secret tests.
- Initial commits were pushed to `origin/main` over SSH. No runtime configuration, model weights or running containers were changed for documentation or hooks.
