# Preparation of observability — October 5, 2026

## Verified result from Work

- Manifests and Linux amd64 digests for the six images were resolved; the lock is in `infra/observability/versions.yaml`.
- Compose was resolved and validated: internal backends, only Grafana published in loopback, no Docker socket, images matching the lock, configuration mounts for read and declared limits.
- Collector 0.162.0, Tempo 3.1.0, Loki 3.7.8 and promtool 3.15.0 accepted their configurations. The binaries were extracted from layers verified against their digests in a temporary directory; no services were installed on the host.
- The Collector test executed real OTLP and filelog receivers, processors, spanmetrics and file/Prometheus exporters over synthetic data. It passed the canary exclusion in bodies, attributes, names/scope, status messages and events, with rejection of spans with links and datapoints with exemplars. Operational information was preserved and a synthetic Docker file was ingested.
- The generated filelog and checkpoint configuration was validated using a temporary directory of offsets. No real host logs were read during this verification.
- Real Prometheus names were confirmed: `agent_calls_total`, `agent_duration_seconds_bucket`, `gen_ai_client_operation_duration_seconds_bucket` and `gen_ai_client_token_usage_sum`. Grafana queries were adjusted to those names.
- The six JSON dashboards were parsed and have stable UID and panel IDs. Their rendering in Grafana has not been verified yet.
- Shell syntax, repository structure, `task observability:plan` and the previous OpenHands plan passed; the existing 11 validation LLM tests continue to pass.

## Repeat verifications

```bash
mise run repo:check
mise exec -- task repo:test
mise exec -- task observability:plan
# On a Docker host: validators inside the pinned images
mise exec -- task observability:validate
# With the pinned Collector binary available locally
python3 scripts/observability/test-privacy.py --collector /path/to/otelcol-contrib
```

## Pending on host

Run `task observability:setup`; verify the smoke test report, readiness and reading of new real logs. Activate the observed profile, check a real conversation and explore the six dashboards. Native OpenHands tracing is optional for synthetic data: confirm dependency, spans and real context propagation before declaring full traceability.

Full Docker execution is not declared validated, the callback within the LiteLLM image, agent correlation or Grafana interface. The origin controls of the callback were also corroborated by reading the code of version 1.104.0; that inspection does not replace the smoke test of the deployment. The [guide](../observability.md) describes these limits and the local storage that still may contain content.

## First deployment on host — 21:32–21:34 UTC

The shared output by the user confirms download of the six images, native validation of Collector/Prometheus/Loki/Tempo within Docker and creation/initial startup of all containers. OpenHands and the connection to Ollama passed.

The flow stopped when configuring logs: `Start observability first.` This message was emitted when LiteLLM was not found among running containers. It does not demonstrate a user error nor determine the cause of the process failure. Logs and LiteLLM status are necessary to distinguish configuration error, dependency, memory or another cause.

The diagnosis was corrected: status includes stopped containers; the startup checks the six processes and HTTP availability of LiteLLM before configuring filelog. If a service terminates, it reports name, status, exit code and OOMKilled. The LiteLLM configuration has not been changed without knowing its logs nor is the cause of startup declared corrected.

## Cause confirmed by LiteLLM logs

The user shared status `exited`, exit code 3, `OOMKilled=false`. The traceback concludes `UnsafeMasterKeyError`: the master key was missing and the server rejected accepting requests without authentication. The trusted proxy range warnings do not explain that closure.

Correction: strong persistent key outside of Git/CloudDrive, proxy environment variable and explicit passing when using sudo. The smoke test passes that key only to the LiteLLM endpoint and checks rejection of unauthenticated requests. The observed profile stops using `local-only` for proxy entry; that placeholder is maintained only in the Ollama segment. The weak/missing key bypass is not used. Restart and host acceptance are still pending.

## Verification of authentication correction

Five local tests passed: distinct credentials with modes 700/600, preservation on repeated startup, rejection of existing invalid key without overwriting it, rejection of symlink and Bearer sending only to LiteLLM hostname. The running/created/exited states were verified with a stub to avoid treating a stopped container as ready. The real privacy test of the Collector was repeated and passed after modifying the verification client.

These tests verify the scripts and credential preparation; the LiteLLM restart and real rejection of unauthenticated requests are pending from the host command. Local repetition: `mise exec -- task observability:test`.

## Second deployment and correction of the counter name

The new host output confirms LiteLLM and the other services running, correct native validators, persistent credentials and active filelog/checkpoints mounts. `observability:check` passed readiness, unauthenticated rejection, authenticated model response and OTLP sending; failed to query stored signals.

An authenticated query to Grafana and its sources showed: Tempo stored a trace `observability-smoke` with sanitized operation, Loki stored `operational record` with category `tool_validation_error`, the Collector scrape gave `up=1` and Prometheus had `privacy_smoke_total=1`. The check was incorrectly looking for `privacy_smoke`; it was corrected to `privacy_smoke_total`. The counter suffix was also verified in the local test with the real Collector. Diagnostic by stage/HTTP was added without printing bodies, secrets or canaries.

This confirms existing synthetic signals; it does not confirm yet real LiteLLM callback spans/metrics or an OpenHands conversation through the observed profile. Repeat `mise exec -- task observability:check` to confirm the full check with a new canary.

### Additional observed status from Grafana

The local Grafana API responded and displayed the three provisioned data sources along with their UID. A search for Tempo returned only the canary; a query for Prometheus names returned counters/histograms of the synthetic span and `privacy_smoke_total`, without metrics `gen_ai.*`. Loki showed recent error categories from `litellm-proxy` with sanitized bodies.

Therefore, synthetic ingestion and LLM callback are treated as separate acceptances. Local LiteLLM logs were requested to check why telemetry from its calls is still not observed. That configuration was not modified without identifying the error. The check also saves a JSON failure report with stage/type/HTTP code, avoiding empty diagnostic files.

## Overview and callback correction

It was confirmed in logs that `gen_ai.token.type` in the attribute filter prevented initializing the native LiteLLM callback. It was corrected without disabling privacy or authentication. A general provisioned dashboard is added, Blackbox Exporter fixed, nine probes, internal metrics of the Collector, and two local rules with wait of 2 minutes. Native validations, privacy canaries, and seven authentication/context tests pass. Grafana recognizes the dashboard as provisioned; queries are verified through their real sources. Pending is to reapply Compose and demonstrate real tracing/metrics and nine healthy probes with the host check.

Final verification: dashboard `platform-overview` recognized as provisioned, 24 panels (includes sections and text), 23 queries without errors in the real Prometheus/Loki APIs. A temporary test confirmed internal Collector metrics RSS/queues/sends/fails and healthy Blackbox probes in OpenHands/Grafana/Ollama plus an HTTP 503 controlled. It is not claimed that the nine new probes or the corrected callback are active before the next `observability:up` on the host.

Reorganization note (October 7): the example structure check now uses mise; the historical result is preserved.
