# Publication review — October 28, 2026

## Change scope

The previous Git baseline is `1eb4279` (October 7). The accumulated implementation
is being recorded as a coherent snapshot, not reconstructed into fictional
historical commits. Generated artifacts, invitations, backup ciphertext, PKI keys,
credentials, workspaces and model weights are excluded from publication.

| Area | Main sources | Result and limitation |
| --- | --- | --- |
| Environment and operations | `mise.toml`, `mise.lock`, `Taskfile.yml`, `scripts/environment/` | Pinned tools and categorized operations; privileged host work remains owner-controlled. |
| OpenHands upgrade/hardening | `infra/openhands/`, `scripts/openhands/`, `tests/security/` | Pinned Canvas 1.26.0 / SDK 1.53.0, native Python launcher, readonly root and bounded runtime; shared host kernel remains a boundary limitation. |
| Storage and instance isolation | `scripts/storage/`, `scripts/instances/`, `config/storage/` | Fixed-size filesystems and synthetic isolation/HTTP/WebSocket/recovery probes; synthetic acceptance is not full family acceptance. |
| Identity and recovery | `infra/identity/`, `scripts/identity/` | Authentik native validation, persistent identity, encrypted backup and isolated SQL restore; full application/host disaster recovery is not accepted. |
| PKI and ingress | `scripts/pki/`, `infra/gateway/`, `scripts/gateway/` | Existing encrypted CA hierarchy, supervised leaf renewal, scoped Caddy routes and native CSRF forwarding regression; connected root ceremony was owner-accepted. |
| Household access | `config/household/`, `scripts/household/` | Separate users/instances, invitation-only enrollment, TOTP, own-app policies and branding. Alejandro reached Canvas; Kimberly enrollment and device acceptance remain pending. |
| Model behavior | `scripts/household/seed-agent.py`, `tune-model.py`, `config/llm/catalog.yaml` | Correct OpenAI-compatible thinking control applied to Qwen; extra model tiers are proposals, not installed or benchmarked models. |
| Observability | `infra/observability/`, `scripts/observability/` | Synthetic metrics/logs/traces pipeline passed after restart recovery. Household relays currently bypass LiteLLM; dashboard counters do not cover those requests. |
| Internet access | `docs/internet_access.md` | Owner-switch design only; no new general agent Internet access was enabled. |

## Observed validation

The pre-commit sequence runs environment consistency, source controls, secret
scanning, environment/inference/observability tests, security tests and workflow
contracts. Results must be rerun against the final staged tree before publication.
Local reports stay under ignored `artifacts/`; no raw credentials or transcripts
are copied into this review. A passing hook is a repository check, not permission
to expose the platform publicly.

On October 28, service recovery checked Authentik/Grafana HTTP health, trusted
HTTPS login and personal-app authentication redirects. Both household native
Agent Server and Canvas API readbacks and relay model discovery passed. The
synthetic observability test passed end to end. A bounded direct Qwen request
returned in 5.66 seconds without reasoning content. It does not benchmark a real
agent turn or prove tenant-wide trace correlation.

## Open items before wider access

- Reproduce and resolve loss of OAuth continuation context; a fresh exchange
  allowed access, but a permanent root-cause fix is not established.
- Complete Kimberly enrollment and both users' phone/browser, cross-user HTTP,
  API and WebSocket authorization/revocation acceptance.
- Provide a single checked restart operation that verifies/remounts storage,
  restores declared model networks and refreshes log mounts in dependency order.
- Validate a new real conversation after profile tuning; retain timing and model
  settings without exporting conversation content.
- Complete effective egress, IPv4/IPv6/DNS, host/management isolation, disk limits,
  shared inference fairness and session-revocation tests for the deployed setup.
- Establish dated container/OS/tool vulnerability scans and remote repository
  enforcement; digest pinning alone does not establish patched software.
- Complete supervised renewal, recovery/incident exercises and independent copies
  of recovery material. Do not recreate the existing CA to fix service startup.

## Publication boundaries

Do not add `artifacts/`, `.env`, keys, recovery files, model weights or state to
Git. Review the staged file list and redacted scanner output. Keep new public
network exposure and the agent Internet switch blocked until their own acceptance.
Branch protections and GitHub security settings require a separate remote readback;
SSH push access alone does not demonstrate that those settings are enabled.
