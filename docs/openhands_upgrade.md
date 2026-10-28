# OpenHands upgrade operations

Date: October 11, 2026
Status: owner applied Canvas 1.26.0 / SDK 1.53.0 on October 11.
Candidate, backup and API/model checks passed. Service recovery, Collector log
mount refresh and synthetic streamed usage passed. The stale image checker was
corrected and the owner revalidated all 14 selected runtime conditions. The owner
reported successful read-only agent terminal execution in /projects/demo.
The existing demo acceptance also passed all three generated tests and additional
arithmetic checks. Broader tool behavior and household acceptance remain pending.

## Applied host evidence — October 11, 2026

The owner supplied successful `openhands:upgrade:plan` and
`openhands:upgrade:apply` output. The isolated candidate identity, installed
modules and native cache-usage self-test passed. Apply stopped only
OpenHands/proxy, validated private state/project archives, recreated the services
and passed UI, authenticated Agent Server/Canvas proxy and Ollama model checks.

The backup is outside Git and CloudDrive:
`/home/alejandro/.local/share/agent-platform/backups/openhands-20261011T061635Z-ryao0nx7`.
Independent local metadata/integrity checks found directory permissions 0700,
archive permissions 0600, and matching SHA-256 values in the saved manifest for
both archives (state: 91,760,640 bytes; projects: 112,640 bytes). No archive
contents were displayed. Hash agreement is an integrity check, not a restore
drill or proof that the archives are encrypted.

Do not repeat apply solely to complete acceptance. Recheck current runtime
restrictions, refresh Collector log mounts after container recreation, verify
streamed proxy usage and execute a real read-only terminal task in
`/projects/demo`. API readiness and the accounting self-test do not establish
complete agent functionality or household readiness.

## Later service availability failure — October 11, 2026

At 14:37 UTC the owner reported OpenHands stopped with exit code 0 and
`OOMKilled=false`; LiteLLM was also stopped with exit code 0 and no OOM flag.
The selected security baseline failed with `agent_not_running`, log configuration
could not find a running OpenHands service and the streamed proxy check could not
run. These checks do not invalidate the earlier upgrade transaction, but current
service availability and post-upgrade acceptance are not established.

Independent host metadata showed Docker started at 13:20:57 Europe/Berlin
(11:20:57 UTC), after the successful upgrade, while the host boot time was
October 8 at 20:48:13 UTC. Loopback checks found Ollama reachable and OpenHands
and Grafana unreachable. Ollama uses `unless-stopped`; OpenHands/proxy and the
observability stack use `no`. A Docker restart is a plausible explanation for
that difference; container stop timestamps are needed to correlate the outage.
Exit code 0 alone does not identify the reason for stopping.

Recover with the existing operations, without rerunning upgrade apply:

```bash
mise exec -- task openhands:up &&
mise exec -- task observability:up &&
mise exec -- task observability:stream:check
```

`openhands:up` loads the saved hardening activation and refuses an unreviewed old
image. `observability:up` reuses existing secrets/data and refreshes Collector log
mounts after recreation. Neither operation changes the restart policy. Run
`security:container:check` separately after recovery: exit 2 means the selected
baseline passed while household acceptance remains incomplete. A successful real
agent tool task is still required.

## Recovery and image-check regression — October 11, 2026

The owner supplied successful `openhands:up` and `observability:up` output:
UI, authenticated backend/proxy and Ollama checks passed; all seven observability
services started. Collector configuration refreshed three selected read-only log
mounts. `observability:stream:check` passed with 23 input and 8 output tokens and
matching counter increments. The local `llm-stream-Je3b5O.json` report was also
independently read for those numeric results. This verifies a synthetic proxy
call, not that an existing OpenHands conversation uses that route.

The subsequent runtime report passed 13 selected controls but failed the image
check. The checker still contained the old 1.24.0 digest; its tests reused that
constant and therefore missed its disagreement with the deployment lock.
The checker now reads the immutable `image` from
`infra/openhands/versions.yaml`, rejects missing/malformed/mutable references
before probing Docker and compares the running image's repository digests against
that exact reference. It does not accept the prior release as an alternative.

Five regression tests cover the prior-release rejection, current-lock collection,
changed lock reads and invalid-lock failure before Docker probes. All 115 security
tests and the configuration guard passed. No runtime restrictions or services
were changed by this checker fix. The owner reran `security:container:check`
at 14:57 UTC: all 14 selected runtime conditions passed. The saved
`artifacts/security/container-mfk5ix6b.json` report was independently checked;
its checker hash matches the current source. Exit 2 retains pending household
acceptance. A real agent task and household controls remain separate checks.

## Reported real agent terminal exercise — October 11, 2026

Following the passing runtime baseline, the owner supplied the OpenHands response
to a read-only terminal task: `cd /projects/demo && pwd && ls -la`. It reported
`/projects/demo` and the existing demo project files. The agent stated that no
files were modified and no dependencies installed. The private conversation was
not exported to this repository. This is owner-reported tool execution, not an
independent assistant Docker run or a before/after filesystem comparison.

This completes the reported basic terminal exercise under the upgraded, hardened
runtime. It does not validate every tool, a write task, persistent conversation
recovery or household isolation. The owner subsequently ran
`mise exec -- task openhands:demo:check`: synthetic arithmetic acceptance and all
three original generated tests (`test_negative`, `test_positive`, `test_zero`)
passed inside the existing agent container. No implementation or test changes
were made by this task. This completes the basic upgraded runtime/demo exercise;
dedicated per-user storage, quotas and household isolation remain separate work.

The earlier synthetic proxy stream check remains distinct from proving that this
particular conversation uses LiteLLM and adds usage to the dashboard.

## Pinned target

[Latest stable release 1.26.0](https://github.com/OpenHands/OpenHands/releases/tag/v1.26.0)
was published October 8. [Release defaults](https://github.com/OpenHands/OpenHands/blob/v1.26.0/config/defaults.json)
select Agent Server/SDK 1.53.0 and Automation 1.19.0. The linux/amd64 image is locked
by immutable digest, with source revision matching the release. Compressed layers
sum to 1,565,822,625 bytes; disk and network transfer can differ with shared layers.

The installed Python backend is retained by the
[released Dockerfile](https://github.com/OpenHands/OpenHands/blob/v1.26.0/docker/Dockerfile).
The hardened launcher continues avoiding executable PyInstaller extraction. Its
native SDK normalizer already includes the cache-creation attribute guard, so no
runtime source compilation or function replacement remains. A pinned-version /
source-fingerprint / synthetic token normalization test is still required.

## Plan and apply

Stop active agent work and host edits to `/projects` before apply. Run from the
host terminal with Docker sudo authentication available:

```bash
mise exec -- task openhands:upgrade:plan
mise exec -- task openhands:upgrade:apply
```

Plan requires one existing recognized old/new image and the active protected
hardening record. It checks exact state/project mount sources, pulls the immutable
candidate and checks its UID/GID and native accounting in an isolated container.
The candidate uses no network, a readonly root, no capabilities, no-new-privileges,
Docker AppArmor and bounded CPU/memory/PIDs/tmpfs. It does not mount existing state
or projects. Image pulls are host-side network operations; fixed progress messages
prevent a silent download. Pulls change the local image cache, not running services.

Apply repeats preflight, pulls the existing pinned Ubuntu helper, stops only
OpenHands/proxy, and streams state and project archives into a private host folder.
Archive validation and SHA-256 manifests precede recreation. Existing volume names,
workspace binds, internal networks and loopback port 8000 remain unchanged. Ollama
and the observability stack are not recreated by the upgrade task.

Ordinary `openhands:up` refuses an older recognized image so it cannot silently
skip this backup procedure. A fresh deployment without an existing container can
still use the normal startup task. `security:apply` is a hardening task, not an
old-to-new image migration task; use upgrade operations for this transition.

## Backup custody and recovery

State/project backups are under `~/.local/share/agent-platform/backups/` outside
Git and CloudDrive. Folder mode is 0700 and archive/manifest mode is 0600; symlinked
backup paths and a different directory owner are rejected. The entire state can
include credentials and conversation content. Archives are local and unencrypted;
permissions do not protect them from root, a compromised owner account or disk
access. Do not upload or share them. Encryption/offline copies remain a separate
backup-custody requirement before household security acceptance.

Before repository edits for this owner, the current 1.24.0 compose/version lock,
legacy Python launcher, plan and route utility were preserved under
`~/.local/share/agent-platform/backups/openhands-source-1.24.0-20261010/`, with hashes.
This is a local source recovery snapshot, not a Git commit or application backup.
It is not shipped in a new clone; another deployment must preserve its own known
working checkout before updating. The new upgrade task supplies application data
archives, but it cannot reconstruct an arbitrary older uncommitted checkout.

If a backup fails before recreation, previously running containers are restarted;
a previously stopped deployment remains stopped.
If recreation or subsequent health checks fail, the candidate is stopped and the
validated archives are retained. There is no automatic downgrade over potentially
migrated data. Recovery requires reviewing the actual failure, preserving failed
candidate data, verifying archive hashes and restoring the matched prior source
and data together. Do not use `docker compose down -v`, prune volumes, or run the
old backend over upgraded state as an assumed rollback. The existing
`security:rollback` removes the hardening overlay; it does not restore versions
or schemas. No live backup/restore drill has been accepted yet.

## Post-upgrade verification

```bash
mise exec -- task openhands:backend:check
mise exec -- task security:container:check
mise exec -- task observability:logs:configure
mise exec -- task observability:stream:check
```

The container check still returns exit 2 when the selected runtime baseline passes
but household acceptance is pending. Check each result; do not chain later checks
behind that expected exit with `&&`. The Collector log task refreshes its narrow
readonly mounts for the recreated OpenHands container. It requires the relevant
observability services already running; recover that stack separately if stopped.

Finally run a synthetic terminal task in OpenHands, explicitly using `/projects/demo`
and no file changes. Confirm a real agent response/tool execution and new proxy
usage before accepting functionality. API health and an isolated accounting test
are narrower evidence. Per-user isolation, egress tests and persistent quotas
remain pending.

The new [entrypoint](https://github.com/OpenHands/OpenHands/blob/v1.26.0/docker/entrypoint.sh)
disables frontend HTML session-key injection by default. Keep that default. An
existing browser may retain its credential; if an API-key screen appears, use the
preserved local backend session credential locally without pasting it in chat.
This is backend session authentication, not household accounts or Google login.
