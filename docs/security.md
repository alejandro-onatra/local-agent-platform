# Platform and Repository Security

## Current scope — October 28, 2026

Repository publication checks and deployed application security are separate.
The local gate currently passes its scoped source, secret and regression checks;
this does not certify OWASP compliance or absence of vulnerabilities. Household
identity/gateway/container controls are implemented with partial live evidence;
full SEC acceptance remains pending. Earlier dated sections retain their
historical proposal/acceptance scope. See the [release review](release_review.md)
for the deployed checkpoint and remaining exposure restrictions.


## Implemented: Secret Control

Gitleaks 8.30.1 is pinned in `mise.toml` and its download/checksum is in `mise.lock`.
The official rules included in that binary are extended with `.gitleaks.toml`
to detect the local master key of LiteLLM. We do not use comment suppressions,
`.gitleaksignore` nor accepted findings baseline.

```bash
mise install --locked
mise exec -- task security:secrets
mise exec -- task security:test
```

The task reviews versioned files and new unignored files, staged content and
the history of all locally available Git references. It rejects shallow clones,
symlinks and unexpected publishable paths of credentials, weights and artifacts.
It does not review ignored secrets that remain outside of Git; it does not read the local
credentials stored outside the repository. It also does not open compressed files.

The script generates a canary key in a temporary directory to check that
the detector actually finds and redacts it. It never adds the key to the repository.
The tests in `tests/security/` check blocking of new, staged and deleted secrets from history,
rejection of symlinks and exclusion of an ignored runtime secret. They only create temporary repositories.

If findings are found, the task fails. It shows only file, line, rule and commit;
numerical reports and hashes remain in `artifacts/security/`, excluded from Git.
Scanner errors fail the control; they are not interpreted as absence of secrets.

Each report records commit, hash of analyzed files, configuration,
version and hash of the binary. The rules do not consult an API or a model. To
repeat a result, exactly those same inputs are needed. The gate can be run explicitly and is included in the installed pre-commit hook.
Enable the hook per checkout with `mise run repo:hooks:install`; see
[Git commit validation](git_hooks.md). A pinned, least-privilege CI workflow is prepared under `.github/workflows/validate.yml`; its first remote run and required-check branch protection are not verified yet. It does not guarantee finding secrets of any format.

## Proposed Controls, Still Not Installed or Executed

| Control | Tool and Evidence |
| --- | --- |
| Python Code | Semgrep with locally versioned rules, without `--config auto`; positive/negative cases of each rule |
| Python Dependencies | OSV-Scanner over `uv.lock`; pin the scanner and snapshot/date of the vulnerability database |
| Container Images | Trivy over existing digests; pin the scanner and vulnerability database |
| Infrastructure Configuration | Trivy config for supported formats; custom tests for our policies of Compose/Collector |
| Application Controls | Versioned OWASP ASVS 5.0.0 matrix and tests for authentication, permissions, isolation, redaction and auditing |
| Publishing | CI runs the current local gate when published; first remote run and branch protection remain unverified. Additional scanners are planned, not active. |

A hash or a scanner version does not fix the vulnerability database. We must
preserve its snapshot/digest and date to reproduce SCA; refresh it deliberately
to know about new vulnerabilities. The same principle applies to SAST rules.

OWASP Top 10 guides risks; ASVS contains verifiable requirements. Each applicable requirement
must have ID/version, evidence, test, result and limits. A scanner
without findings does not mean that all OWASP passes. The effective authorization, the
exposure of services and the behavior of an agent require dynamic testing.

If a real credential appears: stop the publishing, revoke it/rotate it and handle
its history. Deleting the current file does not remove the secret from previous commits.

Primary sources: [Gitleaks](https://github.com/gitleaks/gitleaks),
[Semgrep](https://docs.semgrep.dev/running-rules),
[OSV-Scanner: uv.lock](https://google.github.io/osv-scanner/supported-languages-and-lockfiles/),
[Trivy](https://trivy.dev/docs/latest/),
[OWASP ASVS](https://owasp.org/projects/asvs).


## Planned household LAN controls — October 8, 2026

The agreed entry point is `https://portal.home.arpa`. Each approved identity will
have a persistent, separate OpenHands instance, state and workspace. Local accounts
and mandatory MFA will be managed by Authentik. These are planned controls, not
features already deployed. Existing loopback access stays in place until acceptance.
See [household access and key custody](lan_access.md) for architecture and procedures.

All controls below are **pending implementation and host acceptance**. Existing
single-user restrictions are useful starting points, not evidence of multi-user isolation.

| ID | Practice to implement | Required acceptance evidence |
| --- | --- | --- |
| SEC-01 | LAN-only exposure: publish only the HTTPS gateway on the intended LAN interface; no router forwarding, automatic port opening or public tunnel. | Test intended LAN access and denied access from a guest/untrusted segment, with IPv4/IPv6 and Docker firewall rules reviewed; do not rely on UFW alone. |
| SEC-02 | Trusted HTTPS, local DNS and verified distribution of the public CA certificate. | Resolve portal.home.arpa from each enrolled device; validate hostname, chain and expiry without bypassing browser warnings; independently verify the root SHA-256 fingerprint. |
| SEC-03 | Individual local accounts, invitation/admin provisioning and a separate administrator account. | Public registration is denied; ordinary users cannot administer identity or other users; disabling a user prevents subsequent access. |
| SEC-04 | Mandatory MFA and controlled recovery: passkeys/security keys where compatible, or password plus TOTP. | Users without a factor must enroll before access; invalid factors fail; recovery codes are individual, one-use and stored privately; recovery must not silently bypass MFA. |
| SEC-05 | Per-instance, default-deny authorization derived from verified identity. | User A cannot access user B's URL, API, files or WebSockets; forged identity headers and unknown users fail; use single-application policies, not domain-wide authorization alone. |
| SEC-06 | Persistent tenant separation: dedicated OpenHands state, workspace, secrets and restricted networks per user. | A synthetic canary belonging to B is inaccessible to A through both browser and agent tools; no shared parent workspace/state mount or direct cross-instance route. |
| SEC-07 | Host protection: non-root agents, no privilege escalation/capabilities or Docker socket, minimal mounts; record the selected shared-kernel boundary and verify effective restrictions before family rollout. | Inspect actual runtime settings and prove personal HOME/SSH/browser credentials and host management endpoints are inaccessible; containers are not claimed to be a complete sandbox. |
| SEC-08 | Restricted agent egress and tools; model output cannot grant permissions. | Agent cannot reach unrelated LAN devices or identity/admin/CA endpoints; only required model routes work; deny unapproved tools and test injection attempts. The offline reference policy does not yet enforce OpenHands execution. |
| SEC-09 | Private-key and secret custody with an offline encrypted root and narrowly accessible online keys. | No root private key/password in running services; no key/password in Git, CloudDrive, images, environment variables, command arguments, logs or agent mounts; verify ownership and effective access. |
| SEC-10 | Expiring sessions, secure cookies, logout, throttling and account/session revocation. | Login attempts are rate-limited; cookies are Secure/HttpOnly with suitable SameSite; logout and account disabling stop new requests; measure and bound any existing WebSocket/session grace period. |
| SEC-11 | Bounded resource use and shared inference scheduling. | Limit CPU, memory, processes, disk/workspace growth and model concurrency; test that one user cannot exhaust the host or indefinitely starve another. |
| SEC-12 | Pinned, maintained dependencies and image vulnerability review. | Record versions/digests and dated scan evidence; address applicable findings and rehearse rollback. Planned scanners/CI are not described as active. |
| SEC-13 | Minimal, protected security audit and privacy-aware observability. | Record login/denial/admin events with restricted access and defined retention; exclude passwords, MFA QR seeds, recovery codes, cookies, keys and content. Use opaque user IDs, not emails, in general dashboards. |
| SEC-14 | Encrypted backups and verified restoration. | Back up identity state, per-user data and PKI materials with separate access; root copies stay offline; recover test identities/workspaces without exporting secrets into reports. |
| SEC-15 | Incident response, certificate renewal and trustworthy rotation. | Rehearse user/session revocation, key rotation, certificate expiry and CA trust replacement; do not assume browser CRL/OCSP enforcement. Renew through operational tasks; document each result and remaining limit. |

A valid MFA login does not make agent-generated code safe. Host isolation, tenant
permissions and credential custody remain independent acceptance requirements.
The local pre-commit gate does not enforce these deployed controls or certify OWASP compliance.


## Automated SEC evidence checks — October 8, 2026

[Executable checks and limits](security_checks.md) now implement eight source
regression guards, the existing secret gate and an explicitly requested TLS probe.
`config/security/controls.yaml` maps all fifteen controls to required evidence.
Missing probes remain pending; failed probes block readiness. Neither passing
source guards nor mocked regression tests approve a deployed SEC control.

`security:config` runs offline in the pre-commit sequence. `security:check` includes
secret scanning and reports incomplete readiness with checker exit status 2.
`security:tls:check` additionally verifies the public root fingerprint, portal
certificate chain, hostname and expiry, without disabling TLS verification.
All deployed household controls remain pending. No portal, identity service,
private key or network exposure is created by these checks.

The owner selected host containers. The optional [hardening profile and runtime
checks](container_isolation.md) add readonly-root preparation and effective process/
cgroup observations. They do not certify tenant separation, persistent disk limits
or egress isolation; all household SEC acceptance remains pending.

## Publication hardening checkpoint — October 28, 2026

The publishable-path gate now rejects `.age`, `.agekey`, `.p12` and `.pfx`
containers (case-insensitive suffix matching), including forced index additions
whose working copy is absent. This is a path policy, not decryption or binary
secret analysis. Historical encrypted archives remain outside Gitleaks' full
content-analysis guarantee. Tests use disposable Git repositories and synthetic
data only.

An OSV API review returned no advisories for PyYAML 6.0.3, the only registry
package in the host `uv.lock`, on October 28. Container/OS/tool vulnerability
scans and full SAST are still pending; this result is not a whole-platform scan.
See [the prioritized hardening plan](hardening_plan.md) for evidence, remaining
risks, acceptance criteria and required GitHub settings readback.
