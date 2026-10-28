# Automated SEC checks

The requirement matrix in `config/security/controls.yaml` covers SEC-01 through
SEC-15. It declares required probes, not operator-supplied pass/fail results.
The checker derives results from implemented probes. Missing probes stay pending.
The checks do not deploy Authentik, create identities or private keys, change
firewall rules, publish ports or modify running containers.

## Commands and outcomes

Prepare the pinned Python/PyYAML/Gitleaks environment with mise. Operations and
code tests use Task; their implementation lives in `scripts/security/`.

```bash
mise exec -- task security:config
mise exec -- task security:check
mise exec -- task security:controls:test
```

- `security:config`: eight offline guards over the declared source baseline.
  The checker exits 0 when those guards pass, even though SEC readiness is pending.
  This command is included in the local pre-commit sequence.
- `security:check`: the same source guards plus the existing redacted secret gate
  and a report of all required SEC evidence. The checker exits 0 only when every
  control passes, 1 for failed/invalid evidence and 2 for incomplete readiness.
  Task reports its child command failure; Task's own exit code need not be 2.
- `security:controls:test`: regression tests with disposable source copies and
  synthetic TLS peers. `security:test` also includes these tests and the existing
  real Gitleaks tests. Passing tests validate checker behavior, not deployed MFA.

A fresh report is written to `artifacts/security/controls-*.json`, excluded from
Git, with mode 0600, a UTC timestamp and SHA-256 hashes of source configuration,
requirement matrix and checker. Reports contain identifiers, fixed reasons and
results; source values and external exception text are withheld. They are local
snapshots, not signed audit evidence. No report can be imported to override results.
The default commands do not connect to the portal or scan runtime secrets.

## Source guard coverage

The fixed inputs are `infra/llm/compose.yaml`, `infra/openhands/compose.yaml` and
`infra/observability/compose.yaml` and the optional `infra/openhands/hardening.yaml`.
The checker examines source declarations and
the known partial Ollama and hardening overrides, not a normalized Compose merge. Generated
log/tracing overrides, interpolation values and actual container state are not
covered. New deployment files require explicit coverage before use.

| Guard | Current source assertion | Still required for SEC acceptance |
| --- | --- | --- |
| `compose.loopback` | Explicit IPv4/IPv6 loopback publications; no network-mode override | Intended LAN gateway binding, effective Docker firewall and guest-segment denial |
| `compose.hardening` | No privileged containers, added capabilities, management API socket, host namespaces or unconfined profiles; all full services drop ALL capabilities and set no-new-privileges; agent cannot explicitly request root | Inspect actual UID, permissions, mounts and isolation boundary; an image default is not proof of non-root execution |
| `compose.mounts` | Deny recognizable Docker/Podman/containerd socket and root-CA-key mounts; exact baseline agent state/workspace mount declarations | Verify resolved workspace, host filesystem access and cross-user separation; filename matching does not discover arbitrary private keys |
| `compose.agent_network` | OpenHands has only the declared internal agent-link network and no published port | Real network reachability, model gateway allow-list and denied admin/LAN egress |
| `compose.resources` | Positive CPU/memory limits, bounded json-file rotation and agent process limit; override fragments cannot remove these constraints | Effective quotas, disk growth, fair inference scheduling and load behavior |
| `compose.digests` | Immutable image digest references | Authentic artifacts, dated vulnerability review, maintained software and rehearsed rollback |
| `compose.hardening_candidate` | Verified-user placeholder, read-only root, init, explicit AppArmor and bounded temporary filesystems in the opt-in candidate | Apply and verify on the real host; persistent quotas are separate |
| `compose.secret_delivery` | No literal values in recognized credential environment fields or root-key environment references | Migrate current referenced environment credentials to protected secret delivery; inspect effective permissions/custody |

The guard intentionally preserves today's loopback baseline. Publishing a future
LAN gateway will require a reviewed policy extension and actual authorization/
firewall acceptance, rather than removing this safeguard to make a test pass.
Recognized credential fields accept variable references and required-variable
error messages, but reject literal defaults. This does not enumerate every secret
format; the separate Gitleaks gate remains necessary.

Malformed input, unsupported structures, duplicate YAML keys, missing sources,
unknown incomplete services and directly symlinked inputs fail closed. Source
symlink checks are a local regression safeguard, not protection against an attacker
who already controls the checkout or host. A failed probe takes precedence over
pending evidence; an empty or absent result cannot turn a control into a pass.

## Explicit TLS probe after portal deployment

Obtain the public root certificate from the administrator and independently verify
its SHA-256 fingerprint over the certificate's DER bytes. Supply only this public
material; never pass a private key, passphrase or runtime credential.

```bash
mise exec -- task security:tls:check \
  CA_CERT=/absolute/path/public-root.crt \
  CA_SHA256=VERIFIED_SHA256_CERTIFICATE_FINGERPRINT
```

This command additionally connects only to `portal.home.arpa:443`. It first checks
the public root fingerprint, then requires the hostname, certificate chain, TLS
1.2 or newer and at least seven days of remaining server-certificate validity.
There is no insecure/skip-verification option. A fingerprint mismatch prevents
connection. It does not install trust on clients or prove their DNS/trust behavior.
Full SEC readiness can remain pending even when the TLS probe passes.

The regression suite mocks transport and TLS context using public format fixtures;
it generates no private key. Real TLS acceptance must be run after deployment.
The TLS probe does not read CA signing keys or prove offline root custody.

## Remaining automatic and physical acceptance

The matrix reserves live probes for identity/MFA, HTTP and WebSocket authorization,
cross-user canaries, container inspections, egress, sessions, quotas, security
logs, restore and renewal. These probes are not implemented yet; their names in
YAML do not execute them. Each must be implemented and tested with deliberate
failures when the corresponding service exists. Vulnerability scanners still
need pinned tools and a dated database snapshot; no OWASP certification is claimed.

Physical custody cannot be proven by a source scanner: offline encrypted root
storage, two separately stored encrypted copies and passphrase custody need a
supervised procedure and recorded review. Do not upload those materials as evidence.
All fifteen household controls remain pending deployed/physical acceptance.

## Recorded validation — October 8, 2026

The complete `repo:commit:check` sequence passed 83 tests, including 31 new SEC
regression tests and the five existing real secret-gate tests. Gitleaks found no
findings in 160 publishable files, staged content or local history and passed its
redaction canary. Documentation validation resolved 91 local links across 24
Markdown files; `git diff --check` passed.

`repo:hooks:test` accepted a clean actual commit and rejected synthetic secrets,
wildcard Compose port exposure and invalid shell syntax in a disposable clone.
The existing hooks path preservation test also passed; project history was untouched.

`security:check` produced `config_guard: passed` and fifteen pending controls
(zero passed, zero failed). Its checker returned 2, and Task reported that child
failure as expected. No live TLS probe was run: the household portal and CA are
not deployed. The TLS tests used mocked peers, not host/client acceptance.

Related: [security requirements](security.md), [household architecture](lan_access.md),
[plan](plan.md), [commit validation](git_hooks.md).
Primary references: [Docker Compose service declarations](https://docs.docker.com/reference/compose-file/services/),
[Python TLS context verification](https://docs.python.org/3/library/ssl.html#ssl.SSLContext.check_hostname).


The selected boundary is now host containers. [Runtime checks and opt-in hardening](container_isolation.md)
add process/cgroup/filter/mount evidence and synthetic file probes. They are
separate from the global SEC readiness checker: its live evidence identifiers
remain pending; local JSON reports are not imported as trusted pass declarations.


## Synthetic storage probes — prepared October 11, 2026

The [storage pilot](storage_isolation.md) adds strict source/lifecycle regression
checks to the existing security test suite and local commit gate. It rejects
unmounted-directory fallbacks, wrong backing files, expanded capacities, linked
paths, incorrect identities, unsafe permissions and incomplete existing setups.
Hooks never run privileged setup or live fill probes.

`storage:accept` is a separate opt-in operation against empty synthetic mounted
filesystems. Its four probes require denied cross-UID canary reads and actual
ENOSPC; preparation and mocked tests cannot count as live acceptance. Reports
remain pilot-specific and are not imported into global SEC evidence. Real
application tenant separation, persistent family budgets, host/agent egress,
fair inference and authenticated HTTP isolation remain pending.


The owner ran live storage acceptance on October 11: four probes passed all six
conditions, including ENOSPC and foreign UID canary denial. Saved setup/check/
acceptance reports have mode 0600 and match the source fingerprint. This accepts
only the synthetic pilot storage boundary; global SEC evidence remains pending.
See the storage guide for report names, capacity measurements and remaining scope.


## Separate-instance source guards — prepared October 12, 2026

`openhands:instances:config` now runs in the commit gate without Docker/sudo.
[Instance regression tests](instance_isolation.md) reject missing explicit state
binds, foreign mounts, root/shared identities, wildcard ports, injected/shared
keys, relaxed resource/filter settings and shared agent networks. Live check/accept
remain separate opt-in operations; source checks cannot establish native startup,
authenticated secret/conversation separation or family access. Global SEC
readiness remains pending.


## Owner running-instance/API acceptance — October 12, 2026

After corrected-inspector recovery, both synthetic instances passed their applied
runtime/API checks and six acceptance categories: filesystem, own authentication,
anonymous rejection, foreign-key rejection, native secret-store separation and
idle-conversation separation. Saved down/up/check/accept reports have mode 0600
and match the checker; see [recorded evidence](instance_isolation.md). These
selected exercises are accepted for the pilot. Global household SEC readiness
stays pending; WebSocket, effective egress, authenticated family routing, model
access/fairness and restart/restore evidence remain required.


## Extended pilot checks — prepared October 18, 2026

New Task operations test selected live IPv4 peer endpoints from actual agent
namespaces, native session WebSocket first-frame authentication and synthetic
restart/application-import recovery. Positive controls and exact protocol denial
codes prevent unreachable services or arbitrary errors from counting as passes.
Recovery exports only generated records, blocks active work and rejects unsafe
manifest/marker input; native keys stay in place. [Procedure and limits](instance_isolation.md).

Code tests are in the existing commit gate. Host execution is pending. None of
these checks by itself accepts complete egress/WebSocket coverage, encrypted
full-state backup, host reboot or global household SEC readiness.
