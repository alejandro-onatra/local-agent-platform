# Security review and hardening plan — October 28, 2026

## Scope and trust boundary

This is a scoped publication review, not a penetration test, OWASP certification
or assurance that all dependencies are free of vulnerabilities. The host runs
Docker Engine and shares its kernel/GPU across services. The owner and Docker
administrators are trusted; an authenticated agent user is not a host administrator.
Treat agent-produced code, prompts, browser data and tool results as untrusted.
Keep public Internet exposure and general agent egress disabled until accepted.

Local tooling is sufficient to inspect the source, lockfiles, image declarations
and live host controls. SSH access was verified against the GitHub main branch;
it does not provide evidence about branch protections, repository permissions,
Actions policy, alerts or available security products. Detailed settings require authenticated
GitHub API/UI access. The public API does expose the main-branch protection flag
recorded below. No integration is required to create or execute this plan's
local checks; a connector or GitHub CLI can support the remote readback later.

## Review evidence and gaps

| Area | Observed evidence | Limit |
| --- | --- | --- |
| Secrets | Real pinned Gitleaks gate passes candidate files, index and local history; detection/redaction canary and temporary-repository tests pass. | Pattern coverage is limited. Ignored runtime material and binary archives are not comprehensively scanned. |
| Host dependencies | OSV queried `pyyaml==6.0.3` from `uv.lock` on October 28; no advisory returned. Response and lock hashes are recorded in an ignored local report. | This covers one host library only. It excludes container packages, OS, tools and the SDK's dependency tree; the online database was not frozen. |
| Runtime source | Pinned images, resource restrictions, non-root agents, readonly roots, network/mount allowlists and negative fixtures are present. | Pinning is not a vulnerability scan. Tests and source declarations do not certify escape resistance. |
| Authentication | Alejandro completed MFA and entered personal Canvas; recent invalid TOTP attempts and an incomplete OAuth continuation were distinguished. | Root cause of the lost continuation is unresolved; Kimberly and repeated phone/browser acceptance are incomplete. |
| Telemetry | Synthetic pipeline verifies token metrics, traces, logs and privacy canaries after recovery. | Household relays bypass LiteLLM; security-event retention and full family correlation need separate acceptance. |
| Repository enforcement | Local hooks run the complete gate; a least-privilege GitHub workflow is prepared. | The workflow has not run on GitHub. The public API reports `main.protected: false`; detailed access/security settings are not visible without authentication. |
| Recovery | Encrypted identity backup, rewrapped key and isolated SQL restore were exercised. | Full application decryption/login/MFA, user data and host disaster recovery remain pending. |

## Remote readback — October 28, 2026

Unauthenticated GET requests to GitHub's repository and `/branches/main` API
reported a public repository, default branch `main`, and `protected: false`.
This is a concrete protection gap, not a completed permissions audit. The public
response did not expose `security_and_analysis`; secret-scanning/alert settings,
collaborator roles and administrative bypass permissions remain unverified.
The SSH dry run confirms the prepared ref can be proposed for update; it does not
turn on a required check or prove that all remote safeguards are enabled.

## Prioritized work

Each item needs a reviewed change, its negative tests and dated evidence. A local
pass must not be promoted into a global SEC pass. Critical/high findings affecting
the actual path block broader exposure until fixed or explicitly dispositioned.

| ID / priority | Action | Acceptance and evidence |
| --- | --- | --- |
| HARD-01 / P0 publication | Reject private backup/key-container paths even when force-added or missing from the working tree; retain redacted scanning. | Real temporary Git repositories prove `.age`, `.agekey`, `.p12` and `.pfx` cannot enter the publication set. Final index/history secret scan passes. |
| HARD-02 / P0 publication | Run the local gate in CI using complete history, an exact action commit, read-only token and no deployment secrets. | Workflow validates locally, then passes on GitHub. Owner enables required `Repository validation` check and prevents bypass/force-push according to repository policy. Remote settings need authenticated readback. |
| HARD-03 / P0 before wider access | Complete own-user/foreign-user browser, API and WebSocket authorization; forged headers, anonymous and disabled-user cases. | Separate real users and devices demonstrate denial across all entry paths, including existing streams and session revocation timing. Map SEC-03/04/05/10 evidence explicitly. |
| HARD-04 / P0 operation | Consolidate restart into a checked Task operation: verified mounts before containers, declared model networks and refreshed log paths. | Restart/reboot tests preserve data and deny startup with missing/wrong mounts; no empty underlying directories become user state. Existing services remain healthy after repeated runs. |
| HARD-05 / P0 before Internet switch | Enforce egress outside agents and test public destination/host/LAN/metadata/DNS/IPv6 boundaries. | Default off and global off stop new and existing connections; agents cannot self-enable or bypass the proxy. Follow `internet_access.md`; a UI toggle alone is insufficient. |
| HARD-06 / P1 supply chain | Use maintained Semgrep/Bandit, OSV-Scanner and Trivy for SAST, lockfile/image/OS scanning and supported configuration checks. | Pin tool/rules versions, retain dated database snapshot/hash and SBOM, triage applicable findings with owner, remediation or expiring exceptions. Do not treat unavailable scanners as clean. |
| HARD-07 / P1 fail closed | Replace security-critical Python `assert` checks with explicit errors where they control provisioning or access boundaries. | Optimized Python (`-O` / `PYTHONOPTIMIZE`) cannot bypass negative checks. Review `identity-native.py`, native validation and seed/readback assertions; do not classify every test assertion as a production vulnerability. |
| HARD-08 / P1 identity reliability | Reproduce the stale/bare authorization plan and implement a bounded restart from the application without weakening MFA. | Fresh, cancelled, expired, refreshed and concurrent-browser exchanges complete or produce an explicit safe restart; no endless challenge loop, shared state or open redirect. |
| HARD-09 / P1 resource safety | Measure shared GPU/RAM load, model queues, disk full, inode pressure and process limits. | One user cannot indefinitely starve another or exhaust the host; distinguish bounded synthetic mounts from real per-user quotas and inference budgets. |
| HARD-10 / P1 custody and recovery | Rehearse certificate renewal/failure, recovery key custody, full isolated application restore and revocation. | A restored synthetic identity can log in with MFA and decrypt required application data; expired/revoked access and old trust fail according to documented limits. Root USB stays disconnected during normal operation. |
| HARD-11 / P1 auditing | Define audit access/retention and route household request accounting through an accepted existing integration. | Login/denial/admin events and family usage are attributable without prompts, keys, cookie values or TOTP seeds; positive/negative privacy tests and retention deletion are exercised. |
| HARD-12 / P2 maintenance | Verify GitHub collaborators, token scope, Actions policy, private reporting, Dependabot/security alerts and a review cadence. | Authenticated settings inventory records enabled, unavailable and pending features; account/repository plan limitations are explicit. No broad token is requested solely for local scanning. |

## OWASP mapping

Use [OWASP ASVS 5.0.0](https://asvs.owasp.org/) as the versioned verification basis.
For example, `v5.0.0-1.2.5` covers protection against OS command injection; inspect
argument-array subprocess execution and negative input cases, not just scanner
output. Extend the existing SEC-01–SEC-15 matrix with applicable exact ASVS IDs,
implementation locations, executable checks, live evidence, exclusions and owner.
That complete requirement-level mapping is pending; do not label the current
regression suite as passing OWASP Top 10 or all of ASVS.

## Execution order and publication limits

1. Finish HARD-01, prepare HARD-02 and commit the reviewed source/docs with hooks.
2. Review the two local commits and push only the prepared refs when authorized.
3. Observe the first CI run and apply repository settings with the owner.
4. Complete HARD-03 through HARD-05 before broader network exposure.
5. Execute the P1/P2 backlog with small commits and dated native acceptance.

Publishing this source is not approval to expose the home host or grant an agent
new network/credential access. Report non-actionable or unavailable evidence as
pending. No private keys, database dumps, invitation links or raw runtime reports
belong in the repository or public vulnerability reports.
