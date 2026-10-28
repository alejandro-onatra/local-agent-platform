# Host-container isolation

Date: October 11, 2026
Status: owner applied the optional hardening profile; UI/model startup checks
passed. The owner-reported post-apply baseline passed all 14 selected runtime
checks. The owner subsequently applied the Python launcher compatibility fix:
authenticated backend/proxy and model connectivity passed. The owner then applied
the bounded runtime configuration tmpfs; the latest backend log diagnostic reported
no recognized error indicators at that time. A subsequent agent call reported the
SDK cache-write AttributeError; the owner applied its compatibility backport and the real normalization preflight
passed. The owner applied the 1.26.0 upgrade on October 11: isolated candidate,
native cache-usage, backup, authenticated backend/proxy and model checks passed.
Grafana readiness and a recent streamed proxy
report also passed. Latest October 11 recovery restarted the services, refreshed
Collector log mounts and passed a streamed proxy call with matching input/output
usage and counter increments 23/8. The subsequent runtime check passed 13 controls
but rejected the image because the checker retained the old release digest. That
checker now uses the deployment lock. The owner reran it at 14:57 UTC and all 14
selected runtime conditions passed. The owner then supplied a successful agent
terminal result from /projects/demo. This establishes the reported read-only
terminal exercise; broader tool functionality and household acceptance remain
pending. The existing demo acceptance subsequently passed all three generated
unit tests and additional arithmetic checks under the upgraded container.

## Post-upgrade runtime evidence — October 11, 2026

After service recovery, the corrected deployment-lock checker passed all 14
selected runtime conditions on the upgraded container. The owner supplied the
output and the local `artifacts/security/container-mfk5ix6b.json` report was
independently read. Its checker SHA-256 matches the current source. This records
selected runtime acceptance at 14:57 UTC (16:57 Europe/Berlin), not an assistant-run
Docker probe or a certification of resistance to container escape.

Exit 2 reflects `baseline: passed` with `household_readiness: pending`. Remaining
acceptance covers cross-user canaries, agent egress denial, persistent disk limits,
fair shared inference and authenticated application isolation. Rootless/user
namespaces remain unverified. The owner subsequently supplied a real agent
terminal result for `cd /projects/demo && pwd && ls -la`. OpenHands reported the
expected working directory and existing demo files, with no modifications or
installations. The transcript is owner-provided evidence; this task did not
independently execute Docker or verify before/after filesystem hashes. The owner
subsequently ran `openhands:demo:check`: all three generated tests and additional
arithmetic acceptance checks passed inside the existing container. This accepts
the basic upgraded runtime/demo compatibility, not all agent tools or household
isolation. Dedicated per-user persistent storage with verified disk limits is the
next boundary to prepare; the current demo data remains unmigrated.

## Owner-reported runtime evidence — October 9, 2026

The owner recovered Ollama and OpenHands with the existing operational tasks.
The UI returned HTTP 200 and the container-to-Ollama model digest check passed.
The subsequent runtime report (`container-xxr2rndg.json`) passed 13 of 14 selected
checks. Only `runtime.readonly_root` failed, consistent with the existing baseline.
The earlier stopped-state report showed exit code 255 with `oom_killed: false`;
that flag does not establish the termination cause.

These are owner-provided host results, not independently executed Docker probes
from this task. They do not approve multi-user security or the optional profile.
The owner subsequently completed hardening apply: OpenHands/proxy were recreated,
UI HTTP 200 and internal model digest checks passed, and apply reported success.
This task independently observed UI HTTP 200 and validated the activation record
(UID/GID 10001:10001, mode 0600). It did not run the Docker apply itself.
The owner provided the post-apply report `container-dvvhad0x.json` at
2026-10-09T21:17:24Z: all 14 selected checks passed, including readonly-root,
non-root identity, capability removal, seccomp/AppArmor, effective cgroup limits,
mount/network declarations, rotated logs and synthetic file canaries. The
checker reported `baseline: passed`, `household_readiness: pending` and exit 2.
This establishes the selected single-agent baseline at that time, not complete
host escape resistance, destination allow-listing or tenant isolation.
Synthetic agent execution under the new profile remains a separate next check.

Remaining runtime acceptance covers denied cross-user canaries, denied unrelated
LAN/admin destinations, persistent disk limits, fair shared inference and
application/HTTP/WebSocket identity isolation. Rootless/user namespaces remain
unverified. No pending requirement is accepted by changing an exit status.

The partial Ollama Compose invocation can report OpenHands/proxy as orphans.
They remain defined in the OpenHands overlay. Do not use `--remove-orphans` to
address that warning; it would remove services retained by the other file.

## Selected boundary

The owner chose to continue with restricted containers on the personal Linux
host. KVM/UEFI SVM is not a prerequisite for this path. The VM budget remains an
optional alternative, not a required installation gate. Containers share the host
kernel; rootful Docker administrators remain able to access container data.
Neither a successful login nor a passing configuration check proves escape resistance.

## Opt-in hardening profile

`infra/openhands/hardening.yaml` overlays the existing Compose deployment:

- Explicit numeric UID/GID, derived from the current process only after checking
  the running image's pinned repository digest. Root UID/GID is rejected.
- Read-only image filesystem, an init process and explicit `docker-default` AppArmor.
- Bounded temporary filesystems: 64 MiB `/tmp`, 512 MiB transient workspace and
  128 MiB cache, plus 64 MiB runtime configuration at `.config`, with
  UID/GID-specific ownership. The configuration tmpfs explicitly uses noexec. They disappear on recreation;
  tmpfs consumes memory and does not provide persistent disk quotas.
- Read-only launcher bind at `/usr/local/bin/openhands-agent-server`, sourced
  only from `scripts/openhands/start-agent-server.py`. It runs the already installed
  locked Python module, avoiding PyInstaller extraction on the noexec temporary
  filesystem. Plan rejects a missing module or mismatched package version.
- Existing capabilities removal, no-new-privileges, memory/CPU/PID limits,
  internal network and persistent workspace/state mounts remain in place.

The two persistent mounts are still writable. The current demo workspace lives
in CloudDrive and must contain synthetic data only. Persistent storage outside
CloudDrive, hard disk quotas, per-user networks/instances and model-route egress
restrictions remain requirements before family use. Rootless/user namespaces
are not enabled by this change; evaluate their compatibility separately from
non-root process execution, including storage permissions and the GPU backend.

## Operations and rollback

Run from the host terminal where sudo can authenticate. First inspect the current
container and prepare the candidate:

```bash
mise exec -- task security:container:check
mise exec -- task openhands:security:plan
```

The first check may fail `runtime.readonly_root` on the current writable-root
profile; this is an observed restriction gap, not evidence that the checker broke.
Review every other failure before applying. Plan does not activate a record or
recreate services. It requires an existing running, pinned OpenHands image and
verified process identity; it does not pull a different image.

Stop active agent work before the explicit apply operation, which recreates
OpenHands and its UI proxy. It does not recreate Ollama or delete persistent data:

```bash
mise exec -- task openhands:security:apply
mise exec -- task security:container:check
```

The mode-0600 activation record `artifacts/openhands/hardening.yaml` activates
the overlay for subsequent OpenHands operations. It contains only schema/UID/GID,
uses mode 0600, is validated as data (never sourced as shell), rejects duplicate
fields/root identities/symlinks and remains excluded from Git. Do not edit it to
invent a different identity. Subsequent startup/plan/check commands honor the record.

If candidate startup, UI, authenticated backend/proxy or model checks fail, apply attempts to restore the prior
activation record/profile and recreate the same two services. Failure is reported;
rollback success is not assumed. Review container status locally. To explicitly
return to the previous image-user/writable-root baseline:

```bash
mise exec -- task openhands:security:rollback
```

Rollback changes the security profile and recreates services; it does not undo
files written by an agent or restore application data. Use a separate data backup
for that purpose. No volume removal or recursive ownership change is performed.

## Non-interactive identity probes

The owner reported a hang after sudo authentication. Host process inspection
located a stopped (`T`) Docker Compose `exec` under both a pending security plan
and an apply invocation, before an activation record existed. The exact stop
signal was not captured. The previous identity command captured stdout but used
only `-T`, which disables TTY allocation without disabling interactive stdin.

The identity probe now uses `exec --interactive=false -T` and redirects stdin
from `/dev/null`. Inline permission/model checks use the same closed-input mode;
Python programs supplied through stdin retain their existing input transport.
Phase messages distinguish Docker authentication, discovery, identity, configuration,
recreation and readiness checks. No sudoers setting or authentication policy changes.

A pseudo-terminal regression exercises the identity probe with terminal input
and verifies that the automated child receives closed, noninteractive input.
This is isolated regression evidence; live confirmation requires the owner to
cancel old stopped plan/apply clients and run the updated plan once before apply.
Do not run another apply while an earlier invocation remains active.

Reference: [Docker Compose exec interactive defaults](https://docs.docker.com/reference/cli/docker/compose/exec/).

## Troubleshooting missing runtime evidence

Both security checks require an existing running OpenHands container. The checker
uses `docker ps -a` with the expected project/service labels. Fixed categories
separate `docker_access_unavailable`, `agent_not_found`, `agent_not_running`,
`agent_selection_ambiguous` and `agent_state_unavailable`. A stopped/paused agent
is not executed or approved; reports include only validated state, exit code and
OOM flag. Raw Docker errors, logs and environment remain excluded.

`mise exec -- task openhands:status` includes stopped containers. The current
Compose profile has `restart: "no"`; services do not automatically resume after
a host restart. This is a possible explanation, not a diagnosis of any specific
failure. Check state/exit/OOM before deciding to restart a crashed service.

For a deliberately stopped existing stack, use `mise exec -- task llm:up`, then
`mise exec -- task openhands:up`, then repeat the security check and security plan.
These are existing service operations; they retain model/state volumes and the
workspace. No reinstall or volume deletion is required. A crash/OOM or missing
container needs diagnosis first; do not repeatedly restart a failing service.
The security check/plan never starts a stopped agent or changes restart policy.

## Effective runtime checks

`security:container:check` finds exactly one running Compose agent through project/
service labels, compares its repository digest and reads selected inspection fields.
It does not retrieve environment variables, command arguments, application logs,
conversation content or runtime credentials. Raw inspection data is not persisted.

A bounded Python probe runs under the actual container identity. It checks:

- Non-root executing process and PID 1; zero effective/bounding capabilities.
- No-new-privileges, seccomp filtering and AppArmor enforcing status.
- Declared namespaces/device restrictions; no GPU device requested by the agent.
- Exact persistent workspace/state mounts and an allow-list for the three temporary
  tmpfs paths; expected internal network and no ports. Tmpfs size/ownership are
  source declarations here, not measured effective runtime limits.
- Docker memory/CPU/PID limits and effective cgroup-v2 limits; bounded log rotation.
- Read-only root filesystem.
- A fresh synthetic host file cannot be read at its host path inside the container.
- Synthetic writes succeed in the allowed demo workspace/state and are cleaned up.

The host canary uses a temporary host directory; no real credential is opened.
The two write canaries create uniquely named temporary directories and remove
only their own files. These tests do not prove arbitrary host-path inaccessibility,
per-user authorization or all forms of filesystem escape.

Reports use fixed identifiers/results and a checker hash, are mode 0600 and live
under excluded `artifacts/security/container-*.json`. The checker exits 1 if a
probe is unavailable or a baseline restriction fails; it exits 2 when those
checks pass but household acceptance is still incomplete. Task can return its
own nonzero exit code for the child's status. No successful household exit 0 is
currently implemented. Unsupported/missing cgroup observations fail the baseline.

## Remaining acceptance

An internal network alone is not a destination allow-list: services sharing it
can communicate, and host reachability must be tested explicitly. Current model,
UI and telemetry peers do not constitute multi-user separation. Before household
exposure, provision separate instances/state/workspaces/networks and test two
identities through HTTP, WebSockets and agent tools, including denied cross-user
canaries and denied LAN/admin/host destinations. Those probes are not implemented yet.

The observed root filesystem is ext4 without quota mount options in this
inspection. That observation does not prove every mounted volume lacks quotas.
Do not claim `storage_opt: size` or bounded tmpfs caps the bind workspace/named
state volume. Prepare dedicated persistent storage outside CloudDrive with
verified hard limits; evaluate fixed-size filesystem backing or a supported
project-quota setup and rehearse restart/restore before migrating any data.
No quota setup, storage migration or filesystem reconfiguration was performed.
Tmpfs contents can enter host swap; this profile is not an encrypted-memory
guarantee. Review swap encryption before sensitive household workloads.

All household SEC controls remain pending live/physical acceptance. Source checks,
regression fixtures and simulated rollback are separate from live startup/runtime
acceptance, which requires the owner's authenticated Docker access.

Related: [security requirements](security.md), [automated checks](security_checks.md),
[household design](lan_access.md), [isolation decision](architecture/adr-003-household-isolation.md).
Primary references: [Docker security](https://docs.docker.com/engine/security/),
[AppArmor](https://docs.docker.com/engine/security/apparmor/),
[seccomp](https://docs.docker.com/engine/security/seccomp/),
[Compose services](https://docs.docker.com/reference/compose-file/services/),
[tmpfs behavior](https://docs.docker.com/engine/storage/tmpfs/).

## Backend unavailable after hardening — October 9, 2026

The owner reported Canvas HTTP 502 with internal connection refused on port 18000.
This task independently observed HTTP 200 on `/canvas` but HTTP 502 on `/ready`
and `/api/settings`. The earlier checks covered HTML and Ollama connectivity,
not the authenticated Agent Server API. All 14 runtime restrictions passed at
the reported time; that result does not establish application functionality.

The pinned image entrypoint keeps the container alive while the static frontend
runs, even when a backend subprocess fails. Container `running` and frontend
HTTP 200 therefore cannot stand in for backend readiness.

`openhands:check` now requires authenticated JSON responses from `/api/settings`
on both internal ports 18000 (Agent Server) and 8000 (Canvas proxy) before checking
Ollama. The persisted session key stays inside the container; response bodies are
never read or printed. Startup retries are bounded. Hardening apply uses this
stronger check before declaring success.

Run `mise exec -- task openhands:backend:check` in the host terminal. It reports
backend/proxy status and fixed error indicators from the last 1,000 log lines,
without displaying logs, credentials or conversation text. Indicators can include
read-only filesystem, permissions or full storage; they are clues, not a root-cause
finding. No writable mounts or security exceptions have been added. The initial native loader error remains unconfirmed; subsequent backend recovery
is recorded below.

Source: [pinned image entrypoint](https://github.com/OpenHands/OpenHands/blob/7dc6805406ea3c76cb4a3ce407c3c72d481b0ac6/docker/entrypoint.sh).

## PyInstaller temporary filesystem incompatibility

The owner diagnostic reported an unreachable Agent Server, proxy upstream failure
and backend startup timeout, without Python traceback or filesystem-error matches.
Host process inspection found the entrypoint, automation and frontend but no
Agent Server process. Actual `/tmp` mount flags were `rw,nosuid,nodev,noexec` with
64 MiB capacity; cache and transient workspace were also noexec.

The pinned Agent Server build is a one-file PyInstaller executable which extracts
support libraries to a temporary directory. PyInstaller explicitly documents
noexec temporary filesystems as incompatible. This establishes an incompatibility;
the exact native loader error was not captured by the initial log classifier.
The 64 MiB extraction budget could also be insufficient; no actual archive size
or space exhaustion has been established. Log diagnostics now recognize native
loader/extraction/library-mapping errors without printing matched lines.

The owner-applied fix mounts a small, read-only Python launcher over the image's
backend executable path. It requires the existing `openhands-agent-server`
package at version 1.49.6 and its `__main__` module, then forwards the original
entrypoint arguments with `runpy`. No package installation or writable/executable
temporary mount is introduced. Plan checks module availability before recreation;
apply requires authenticated backend and proxy responses before success.

The mount validators admit only this exact launcher source/target and reject
writable or substituted mounts. Existing persistent mounts and all kernel/resource
restrictions remain required. The owner verified the live Python module and backend/proxy recovery. Synthetic
agent tool execution and runtime restrictions after launcher recreation still
require separate checks; isolated launcher/control tests are not deployment.
Run `openhands:security:plan`, then `openhands:security:apply` only if plan passes,
then `openhands:backend:check` and `security:container:check`. Exit 2 from the
security check still means the selected baseline passed but family readiness is pending.

Sources: [pinned backend spec](https://github.com/OpenHands/software-agent-sdk/blob/v1.49.6/openhands-agent-server/openhands/agent_server/agent-server.spec),
[PyInstaller one-file operation](https://pyinstaller.org/en/stable/operating-mode.html#how-the-one-file-program-works).

Restoring an activation record on failed apply does not restore an older revision
of the Compose YAML or launcher file. Inspect the actual backend and restrictions;
do not infer recovery from an attempted recreation. Explicit rollback selects
the original writable-root baseline and removes the launcher overlay.

## Owner-applied backend recovery and remaining log findings

The owner ran plan, apply and backend check after the launcher change. The installed
Python Agent Server 1.49.6 module preflight passed. After recreation, authenticated
Agent Server and Canvas proxy checks passed, and container-to-Ollama model digest
verification passed. A subsequent authenticated backend check also passed. This
task independently observed `/canvas` HTTP 200, `/ready` HTTP 200 and unauthenticated
`/api/settings` HTTP 401, consistent with a reachable protected API.

At that intermediate stage, the logs still contained read-only filesystem and
Python traceback indicators; the latest post-configuration result is recorded below.
They do not contradict API readiness, but do not establish complete functionality.
The subsequent classifier localized the read-only error to the unmounted home
configuration directory. The precise tool/function is not yet identified. `openhands:backend:check` now reports
fixed `readonly_path_categories` from paths following the EROFS marker, excluding
traceback frame paths and individual filenames. Unrecognized or missing paths stay
`other_or_unknown`. No exception, raw path, credential or conversation is emitted.

Do not add writable mounts solely because an indicator is present. Identify the
operation, repeat selected runtime restrictions after recreation and perform a
synthetic tool task. Household readiness and the exact original loader error
remain unverified. Recovery of authenticated APIs is distinct from all agent tools,
conversation persistence, tenant isolation and quota/egress acceptance.

## Runtime configuration and model-route failures

The owner reported that conversations no longer return responses. The sanitized
log classifier localized the read-only filesystem error to
`/home/openhands/.config` (`unmounted_home_config`). The owner-applied profile adds
only that directory as a 64 MiB tmpfs, mode 0700 with the verified UID/GID and
explicit nosuid/nodev/noexec. It does not make the home or image root writable.
Runtime write canaries now require this directory as well as demo/state writes.
Configuration is transient and disappears on recreation; persistent OpenHands
state remains under `.openhands`. The owner applied this mount and reported clean recognized log indicators.
A real synthetic agent response is still needed, rather than API health alone.

Separately, the owner reported Grafana unavailable and an OpenHands LLM connection
error. This task observed OpenHands `/ready` and Ollama `/api/version` HTTP 200,
but Grafana port 3000 unreachable; no loaded Ollama model was visible in that
snapshot. This does not prove the cause or that all prior model requests failed.
LiteLLM belongs to the separate observability Compose project. The OpenHands
hardening task intentionally recreates only OpenHands/proxy; it does not start
LiteLLM/Grafana. Inspect `observability:status` before recovery. Authentication,
model-route reachability and filesystem compatibility are separate checks.

The owner subsequently provided `observability:status`: all seven services
(Collector, Prometheus, Tempo, Loki, Grafana, LiteLLM and Blackbox) were exited
with code 255 approximately 25 hours earlier. That confirms the proxy was
unavailable and predates the current night's hardening changes. Exit code alone
does not establish why the stack stopped. All seven Compose services explicitly
use `restart: "no"`; this task has not changed that policy.

Recover with `observability:up`, which reuses existing credentials/data volumes,
then `observability:stream:check` to prove a real streamed proxy call and usage
counters. Apply the prepared configuration tmpfs separately through
`openhands:security:plan` and `openhands:security:apply`, then check backend logs,
runtime controls and an actual synthetic agent response. Restoring the proxy is
not proof that the read-only tool configuration issue has also been resolved.

## Owner applied runtime configuration fix — October 9, 2026

The owner provided successful plan/apply/backend-check output after the configuration
mount change. Module preflight, authenticated Agent Server/proxy, internal Ollama
model digest and UI checks all passed. All ten recognized log error indicators
were false in the reviewed recent log tail, with no read-only path categories.
This is snapshot evidence, not a guarantee that future operations cannot fail.

This task independently observed OpenHands readiness, Ollama version and Grafana
health HTTP 200. It also read the fresh local owner-generated report
`llm-stream-PjpUlJ.json`: a streamed proxy request passed with input/output usage
23/8 and matching counter increments 23/8. The file was observed shortly after
completion; its modification time is metadata, not a signed execution timestamp.
This task did not itself execute the authenticated Docker inference or apply.

Selected runtime restrictions must be rechecked after the launcher/configuration
changes, including the new configuration write canary. The next functional
acceptance is a real agent terminal task in `/projects/demo`. Proxy streaming,
API readiness and clean selected log indicators do not prove all agent tools,
conversation persistence, household identity separation or quota/egress controls.


## SDK cache-write telemetry compatibility candidate — October 10, 2026

After successful authenticated API recovery, the owner reported
`PromptTokensDetailsWrapper` missing `cache_creation_tokens` during agent use.
This matches the upstream SDK 1.49.6 regression documented in
[PR #5327](https://github.com/OpenHands/software-agent-sdk/pull/5327).
The updated read-only launcher prepares a version/source-guarded, process-local
backport and tests null/absent/numeric cache-write details before launch. No
additional mount, writable image path or security exception is introduced.
The safe backend log classifier now includes `cache_usage_attribute_error`.
See [OpenHands operations](openhands.md#cache-usage-attributeerror-with-agent-server-1496).

The prepared launcher requires owner apply/recreation and real agent acceptance.
The earlier clean log tail and API checks preceded this newly reported failure;
they do not prove that complete conversations work. Recheck runtime restrictions
after recreation; all household acceptance requirements remain pending.


## Prepared OpenHands 1.26.0 upgrade — October 10, 2026

The owner applied the legacy SDK compatibility backport and provided passing
installed-runtime/API tests with all recognized error indicators false. They then
requested the latest stable release. The repository pins Canvas 1.26.0, Agent
Server/SDK 1.53.0 and Automation 1.19.0. The owner applied the upgrade on October 11;
candidate identity/native accounting, private backups and API/model checks passed.
Post-upgrade runtime restrictions, log collection and actual agent acceptance
remain pending. The earlier 14-control runtime result belongs to the previous
container and must be rechecked against the recreated instance.

The native SDK fix replaces the process-memory backport in the launcher. Version,
source fingerprint and cache-usage self-tests remain required. The image retains
an installed Python package, so the noexec/PyInstaller workaround remains in place.
Upgrade operations preflight the new image with no network and no existing state
mounts, then stop only OpenHands/proxy and create private state/project archives
before recreation. Source recovery files were saved separately for this owner.

See [upgrade procedure and recovery limitations](openhands_upgrade.md). Source
checks do not establish new image UID, startup, actual agent execution or family
security. Re-run current runtime checks and refresh Collector log mounts after
recreation. New upstream HTML session-key injection is disabled by default;
keep that default and supply preserved credentials locally if the UI asks.


## Current runtime acceptance and storage preparation — October 11, 2026

After the locked upgrade and recovery, the owner's current checker report passed
all 14 selected runtime conditions. The owner reported a read-only agent terminal
exercise in `/projects/demo`; the existing three-test arithmetic demo acceptance
passed. These results establish the selected controls and that small exercise,
not household isolation or complete agent behavior.

The owner applied the [two-identity storage pilot](storage_isolation.md) on
October 11. All four synthetic workspace/state volume probes passed UID/own
access, foreign canary denial, ENOSPC and cleanup. Current OpenHands mounts/data
are unchanged. This evidence covers the pilot's storage boundary; authenticated
application separation, final family budgets, restart/restore and effective
network isolation remain pending.


## Separate synthetic instances — prepared October 12, 2026

A [two-instance Compose pilot](instance_isolation.md) gives each accepted
synthetic UID its own bounded home/state, workspace, internal agent network,
localhost ingress and native session/encryption keys. The image's declared
state volume is overridden by an explicit own-state bind; anonymous/foreign
mounts fail the source/runtime checks. No Docker socket, GPU, shared model
network, copied provider credential or LAN exposure is added. Current OpenHands
is unchanged. Real deployment, API isolation, WebSocket/egress and restart/restore
acceptance remain pending; this is not completed family tenancy.


## Owner two-instance acceptance — October 12, 2026

The owner successfully ran pilot down/up/check/accept after the inspector fix.
Both running instances passed the applied image/identity/resource/mount/network
declaration guards and authenticated API health. Synthetic own-state, anonymous/
foreign-key rejection, secret-store and idle-conversation namespace exercises
passed for both identities. [Private report evidence](instance_isolation.md) was
reviewed against source fingerprints and mode 0600. Effective peer/host egress,
WebSocket, arbitrary tool behavior, reboot/restore and household authentication
remain pending; declared network isolation is not a live egress proof.
