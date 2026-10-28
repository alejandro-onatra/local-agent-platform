# Persistent localhost identity bootstrap

Prepared October 18, 2026. Owner-reported administrator login, password recovery
and TOTP browser checks were completed by October 20; see the acceptance record below.
The disposable native blueprint check passed separately; it did not leave a UI.
This candidate starts a persistent Authentik UI on the current computer only.

## Start and open the UI

Run in the host terminal from the repository:

```bash
mise run env:identity:setup &&
mise exec -- task identity:up &&
mise exec -- task identity:check
```

Only after these complete successfully, open **http://127.0.0.1:9000/** in a
browser on the same computer. Use the native initial-setup screen to configure
the default administrator (`akadmin`); choose and retain the password privately,
not in Git, task arguments or chat. The application may redirect to its native
setup flow. No administrator password/token is preloaded or printed by our tasks.

If setup is not offered, inspect the native page and `identity:status`; do not
reset the database or regenerate keys to obtain a new setup screen. On repeat
starts, sign in using the existing administrator rather than creating a replacement.
Enable the administrator's TOTP factor in native user settings before further
configuration. Browser login/enrollment must still be verified; service health
alone does not establish MFA enforcement.

Use TOTP for this temporary local bootstrap origin. WebAuthn/passkey enrollment
for the household should wait for the final trusted HTTPS identity name; changing
origins can require re-enrollment. `login.home.arpa` and `portal.home.arpa` remain
planned names: these tasks do not configure DNS, certificates or the gateway.
No client certificate trust change is needed for this loopback HTTP step.

The tested household blueprint is **not automatically imported into this UI**.
Its mandatory MFA flows and per-application bindings remain a candidate until the
admin factor is enrolled, the final origin is ready and protected access is tested.
Fresh installation uses Authentik's bundled bootstrap defaults; default flows
must not be treated as the accepted household MFA policy. Create no family
accounts and publish no LAN listener at this stage.

## What the tasks own

| Command | Purpose |
| --- | --- |
| `mise run env:identity:check` | Check native/local source, pinned versions and topology without Docker deployment |
| `mise run env:identity:setup` | Prepare directories, private credential files and a protected Compose snapshot; requires sudo, starts no service |
| `mise exec -- task identity:plan` | Show the local deployment boundary without reading private state |
| `mise exec -- task identity:up` | Check protected state and existing container identity/restrictions, pull pinned images and start the three services |
| `mise exec -- task identity:status` | Report selected service running/health states without application logs |
| `mise exec -- task identity:check` | Require all three services healthy, effective restrictions intact and local HTTP readiness |
| `mise exec -- task identity:down` | Remove only this Compose project's containers/networks while retaining all private files/data |

All operational/private-state tasks require interactive host sudo. Authentication
happens before the reporting pipe, with explicit progress messages. Docker
operations use bounded waits and periodic progress. The fixed report contains
public control results/source fingerprints, not passwords, environment dumps or
raw health/application logs. Reports stay in ignored `artifacts/security/` as
mode-0600 files. No `reset`, data deletion, key regeneration or account-creation
command is supplied.

## Persistent files and key preservation

The fixed root is `/var/lib/agent-platform/identity-local`, outside Git and
CloudDrive. Its parent chain must be administrator-owned and not group/other
writable; the root directory is mode 0700.

| Path under the private root | Owner/mode | Purpose |
| --- | --- | --- |
| `database/` | 70:70 / 0700 | PostgreSQL 18 data root, explicitly replacing its image-declared volume |
| `data/`, `certs/` | 1000:1000 / 0700 | Native application data and server certificate storage |
| `secrets/` | root / 0700 | Parent of separately delivered DB/password/signing-secret files |
| `secrets/postgres-password` | 70:70 / 0400 | PostgreSQL password-file input |
| `secrets/authentik-password`, `secrets/authentik-secret` | 1000:1000 / 0400 | Authentik file-based configuration |
| `compose.yaml`, `manifest.json` | root / 0600 | Validated snapshot, pinned-image identity and private key-integrity fingerprints |

The two database password files contain the same generated random value with
separate ownership. The Authentik secret is independently generated. Values
never appear in Compose environment values or command arguments; Authentik
receives `file://` references and PostgreSQL its native password-file setting.
Only the selected service mounts its credential files read-only. No source
checkout, personal HOME, agent workspace, issuer/root CA key or Docker socket
is mounted into these identity services.

On repeat setup, exact metadata, file types, ownership, modes, singleton links,
password-copy equality and private SHA-256 fingerprints must match. Files are
opened no-follow/nonblocking and verified before reading, rejecting symlinks,
hardlinks and FIFOs. An incomplete tree is not automatically repaired. A secret,
version or Compose mismatch stops startup; recovery or migration needs a separate
reviewed procedure. Never delete this directory to resolve an ordinary health error.

These files are permission-protected, not an encrypted backup. Retaining the
Authentik secret with a consistent database backup is necessary for recovery;
full backup/encryption/restore acceptance is still pending. Local administrators
and Docker administrators remain inside the host trust boundary.

## Container and network boundaries

The fixed Compose project is `agent-platform-identity-local`. PostgreSQL and the
worker join only its private internal database bridge. The server also joins a
separate frontend bridge and publishes only **127.0.0.1:9000 -> 9000/tcp**.
No HTTPS port, IPv6 listener or LAN wildcard binding is published. The frontend
is not an egress-denial policy for the server; broad egress acceptance remains open.
No identity network is shared with OpenHands, Ollama or observability.

All three use pinned images, non-root users, read-only roots, dropped capabilities,
no-new-privileges, Docker AppArmor, private namespaces and restricted bind mounts.
Temporary files use bounded noexec tmpfs. CPU/memory/PID limits are explicit;
combined configured memory maxima are 3.75 GiB. Startup requires a 6 GiB available
host-memory snapshot. Initial environment preparation requires 10 GiB free storage;
this is not a persistent filesystem quota or reservation. Rotated Docker logs
are capped at two 2 MiB files per service and are not yet sent to the Collector.

Data is durable through container removal/recreation. Automatic service restart
or host-boot startup is deliberately not configured for this bootstrap stage.
After a reboot, use `identity:up` with the same protected state. An unhealthy/failed
start retains the data and service state for diagnosis; it does not roll back or
wipe a partially initialized database.

## Source and validation scope

- `infra/identity/local-compose.yaml`: reviewed persistent-loopback definition.
- `scripts/identity/local.py`: source/state guards, one-time preparation, selected
  runtime inspection and service operations.
- `scripts/identity/local.sh`: terminal authentication and fixed reporting.
- `tests/security/test_identity_local.py`: state-preservation and rejection probes.

Native application setup is handled by the pinned image's normal server/worker
entrypoint. The local checker verifies image/user/command/entrypoint identity,
capabilities, namespaces, AppArmor, resource/log limits, exact bind/tmpfs mounts,
network membership/bridge privacy and exact host-port binding. It checks service
health and HTTP readiness, not user authentication or MFA. Reports explicitly
keep household readiness pending and say the task did not perform blueprint
application; they do not infer whether an administrator later applied it manually.

Prepared code passed 323 repository tests, including 59 identity tests (21 new
local-state/runtime regressions), installed Compose source parsing, and repository
structure/shell/whitespace checks. Privileged filesystem preparation, actual
server/worker runtime verification is separate from the owner-reported administrator
browser checks recorded below. Household MFA enforcement remains pending.

References: [Authentik Docker Compose and initial setup](https://docs.goauthentik.io/install-config/install/docker-compose/),
[file-based native configuration](https://docs.goauthentik.io/install-config/configuration/),
[household identity design and accepted native blueprint](identity_access.md).


Preparation evidence: registered mise source checks and Task `identity:plan`
passed without service deployment. Gitleaks 8.30.1 scanned 226 candidate files,
staged content and local refs with no findings and passed its canary; private
report basename `secrets-7uw705rt.json`. The `pending` native fields printed by
source-only plans mean the plan did not execute a new native test; they do not
invalidate the separately recorded successful disposable native report.

## Owner-reported administrator acceptance — October 20, 2026

The owner reports successful administrator login, an interactive password reset,
TOTP enrollment, and completion of the requested private-window login check
(invalid TOTP rejected, valid TOTP accepted). This is manual browser evidence,
not an automated report or proof of the effective configuration for other users.
No credentials, QR codes, seeds or recovery links are recorded here.

Still pending: no-factor enrollment/denial, enforced household flow selection,
recovery after loss of MFA, final HTTPS origin, application authorization and
household readiness. The tested candidate blueprint has not been applied by
these tasks; browser success must not be interpreted as its deployment.

## Next gate: inspect the active MFA policy before changing it

Keep the current authenticated administrator session open. In the admin UI:

1. Under **System > Brands**, identify the brand selected for the current host
   and its authentication flow. Do not assume a flow with a familiar name is active.
2. Under **Flows and Stages > Flows**, inspect that flow's stage bindings. Locate
   the **Authenticator Validation** stage after password validation and before
   session creation. Inspect its bindings/policies for conditions that skip it.
3. Open the corresponding stage under **Flows and Stages > Stages**. Record only
   the public stage name, allowed device classes, **Not configured action**,
   configuration stages and last-authentication threshold. Do not export users,
   tokens, device secrets or database contents to obtain these settings.
4. A **Skip** action permits a user without a compatible factor to continue.
   The household candidate instead uses **Configure** with explicit TOTP/WebAuthn
   setup stages; protected application access uses **Deny** without a factor.
   Do not change this dropdown alone: enrollment stages, flow ordering, bindings
   and recovery must be reviewed together. Do not import the entire household
   blueprint into the temporary HTTP origin merely to change one MFA setting.

Before applying a policy change, prepare a consistent private backup of the
identity database and required application secrets, with a tested restore path.
That backup/restore acceptance is not implemented by the current local tasks.
Then test with synthetic accounts: enrolled factor accepted, invalid factor
rejected, and no-factor account required to enroll or denied as intended. Repeat
in a clean browser session; an existing authenticated session is not a fresh-login
control. Do not publish a LAN listener until the HTTPS/gateway gates pass.

## Administrator password recovery (owner-tested)

Run this interactive command in the host terminal if only the password is lost:

```bash
sudo docker --context default compose \
  --project-name agent-platform-identity-local \
  --file /var/lib/agent-platform/identity-local/compose.yaml \
  exec server ak changepassword akadmin
```

Use the actual username if it was renamed. Enter the new password only at the
interactive prompts; never put it in a command argument, repository file or chat.
This changes the account password without deleting the database or deliberately
resetting its authenticators. It does not recover a lost TOTP device. A signing
secret or database password is not the administrator's login password and must
not be replaced to fix a forgotten login.

Loss of MFA requires a separate reviewed recovery operation. Native recovery
links can grant direct account access and must never be logged, pasted into chat,
or treated as ordinary API tokens. No recovery link is generated by this guide.
Host administrators with Docker execution access remain inside the trust boundary.
Store the administrator password in a password manager; keep any approved MFA
recovery material private and separate from this repository.

References: [native login recovery](https://docs.goauthentik.io/troubleshooting/login/),
[authenticator validation semantics](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_validate/).


## Encrypted backup candidate — October 20, 2026

[Backup custody, owner commands and isolated SQL restore scope](identity_backup.md)
now have prepared operational tasks. Earlier pending full-backup statements remain
applicable: no real snapshot, native application restore or browser recovery has
been accepted by these source changes.
