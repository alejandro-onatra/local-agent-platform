# Encrypted identity backup and isolated SQL restore

## Status and boundary

Prepared October 20, 2026. No real recovery identity or production backup was
created by the assistant. Live backup creation and isolated SQL restoration need
owner execution in a terminal with sudo. Household readiness remains pending.

The owner reports that a new synthetic user was forced to enroll TOTP and that
a subsequent login rejected an incorrect code. This does not assert every login
path is covered or that the test account has already been deactivated. Keep the
administrator session available and deactivate only the intended `mfa-probe`
account after completing the positive login control, never an `ak-outpost-*` user.

## Contents and custody

A snapshot contains a custom-format `pg_dump` of `identity_local`, the Authentik
signing secret, both database-password copies, private deployment manifest and
Compose snapshot, pinned versions, and regular files beneath `data/` and `certs/`.
It excludes raw PostgreSQL data files. The archive carries hashes for its members.
`age` 1.3.2 encrypts it to one native X25519 public recipient. Public-key encryption
alone is not proof of the sender; retain backups under trusted custody.

The backup task pauses server and worker, takes the snapshot with PostgreSQL
remaining up, and attempts to resume both writers even when snapshot creation
fails. It checks runtime health after resuming before publishing ciphertext.
Allow a brief login interruption. The same identity operation lock serializes
backup and the existing local lifecycle tasks. Unrelated direct Docker/SQL writes
must not run during the snapshot.

Plaintext is kept in anonymous Linux memory-backed files or Python memory, not
named disk staging files. These can still be swapped: host swap encryption,
core-dump policy and trusted host administrators remain relevant. The initial
implementation accepts at most 128 MiB of aggregate payload and 4,096 entries;
it refuses oversized data rather than creating an incomplete successful backup.

Ciphertext is root-owned mode 0600 in `/var/lib/agent-platform/identity-backups/`
(mode 0700), outside Git and CloudDrive. Failed partial ciphertext is removed.
The recovery identity is separately passphrase-encrypted under the desktop
user's `~/.config/agent-platform/recovery/identity.age`, mode 0600 in a private
directory. The public recipient is in `recipient.txt`. Repeat key creation refuses
to overwrite an existing identity. No private key or passphrase belongs in chat,
arguments, environment variables, Git, logs or an unencrypted synced folder.

Copy the encrypted recovery identity to offline storage and retain its passphrase
privately, separately from the backup. Also copy ciphertext off this computer:
a local encrypted file does not protect against disk loss. This stage supplies
no automatic remote copy, deletion policy, schedule or key rotation.

## Owner execution

From the repository, install the pinned tool and validate the environment:

```bash
mise install --locked age
mise run env:identity:backup:check
mise exec -- task identity:backup:plan
```

Generate the recovery identity as your desktop user, without sudo:

```bash
mise exec -- task identity:recovery:key:create
```

Enter and retain a strong passphrase in the native age terminal prompt. The task
prints file locations only. Do not paste the encrypted identity, passphrase or
any decrypted key here. Save the encrypted identity offline before depending on
this backup. If its public-recipient file could not be saved, preserve the
successfully encrypted identity and review the failure; do not delete it to retry.

Create a consistent encrypted snapshot; this task requires sudo and briefly
interrupts the identity UI:

```bash
mise exec -- task identity:backup:create \
  RECIPIENT="$(cat "$HOME/.config/agent-platform/recovery/recipient.txt")"
```

Use the exact `backup_file` path from its fixed report in the next command:

```bash
mise exec -- task identity:backup:restore:check \
  BACKUP=/var/lib/agent-platform/identity-backups/identity-REPLACE_WITH_REPORTED_ID.age \
  IDENTITY="$HOME/.config/agent-platform/recovery/identity.age"
```

The recovery identity's passphrase is requested privately through the terminal.
Reports in ignored `artifacts/security/` contain fixed results and paths, not
archive contents, raw database errors, account names, seeds or keys.

## What the restore check proves

The task decrypts and validates the complete archive before executing SQL. It
rejects unsafe paths, duplicate entries, links, missing keys, changed hashes,
password-copy mismatches and incompatible pinned images. It never extracts the
archive onto the host or writes into the current identity deployment.

A randomly named pinned PostgreSQL container uses `--network none`, no ports,
no host mounts, a read-only root, non-root UID 70, dropped capabilities, NNP,
AppArmor and bounded database tmpfs/resources. Local trust authentication is
confined to this disposable container. Native `pg_restore` uses a single
transaction and exits on any SQL error. The public table-name inventory must
match the source. Cleanup removes this container and its temporary database;
a cleanup failure makes the task fail.

This is a native SQL restore plus archive-integrity check. It does **not** prove
row-by-row equality, successful Authentik field decryption with the saved secret,
filesystem permissions after full restore, application startup, login/TOTP after
recovery, or complete host disaster recovery. Those gates need an isolated
application restore before family/LAN readiness. No in-place restore is provided.

## Implementation and verification

- `scripts/identity/backup.py`: snapshot, encrypted key generation, safe archive
  reader, native SQL restore orchestration and fixed reports.
- `scripts/identity/backup.sh`: terminal privilege boundary and report file.
- `scripts/identity/check-backup-tools.sh`: mise environment validation.
- `tests/security/test_identity_backup.py`: malformed archives, native encryption,
  wrong-key/corruption rejection, failure recovery and cleanup orchestration.
- `mise.toml` and `mise.lock`: exact encryption tool version and checksums.
- `Taskfile.yml`: operational tasks; no service logic embedded in mise.

Automated tests use synthetic bytes and temporary test keys only. SQL/container
orchestration is mocked locally until the owner executes the live restore task.
A successful source test must not be recorded as live restore acceptance.

References: [Authentik backup components](https://docs.goauthentik.io/sys-mgmt/ops/backup-restore/),
[age encryption tool](https://github.com/FiloSottile/age).

Preparation verification: all 347 repository tests passed, including 83 identity
tests (24 new backup/key regressions). Native age encryption, wrong-key/tamper
rejection and encrypted-identity prompts/decryption were tested with synthetic
keys and a disposable PTY. Environment/memory checks and the registered Task plan
passed. Docker SQL restore and real backup acceptance remain pending.
The mise-generated lock also fills platform checksums for the existing pinned
Gitleaks and uv releases; their selected versions are unchanged.


## Owner-run SQL restore acceptance — October 24, 2026

The owner created `identity-93fa270c09324a1c8354888f12c5c256.age` and reported
services resumed (`identity-backup-qRi2P6QA.json`). The subsequent local report
`identity-backup-VDgZaO9W.json` was read back with archive integrity, isolated SQL
restore and cleanup all **passed**. This closes those specific live gates only.
Native Authentik startup, encrypted-field decryption and browser/TOTP recovery
remain pending. The terminal implementation changed after this run; the successful
run does not certify the revised terminal path under host sudo.

During that operation, age was observed stopped and the owner-provided terminal
transcript included sensitive input. No input values are recorded here. Treat
that recovery phrase as exposed. Do not resume a stopped crypto process and type
secrets as a routine workaround. Updated source runs age in a separate private
PTY, verifies no-echo before forwarding input, rejects a background/echoing owner
terminal, detects stopped crypto children and restores terminal settings on exit.
Only fixed prompts/results are displayed; native PTY output is not streamed.

### Replace the recovery phrase, preserving the same recovery key

Run as the desktop user, **without sudo**:

```bash
mise exec -- task identity:recovery:key:rewrap
```

Enter the existing phrase to unlock the key, then choose and confirm a new phrase,
and enter the new phrase once more for verification. Input is hidden. Do not put
any phrase in chat, command arguments or environment variables. Blank input is
rejected instead of generating and displaying a phrase.

The task verifies the current public recipient, encrypts the same private key to
a mode-0600 candidate, decrypts that candidate and compares the original bytes
before atomic replacement. It leaves `recipient.txt` unchanged, so previously
created backup ciphertext remains compatible. Failures before replacement retain
the original encrypted identity and remove the candidate. No identity service or
backup file is modified by rewrap.

Refresh offline copies of `identity.age` after success. Previously copied identity
files still unlock with the previous phrase: rewrap does not revoke old copies.
If an old encrypted identity was also disclosed, changing its phrase alone cannot
revoke that copy; a separately reviewed new-key/backup migration would be needed.
No such migration is performed automatically.

After rewrap, repeat the isolated restore with the same backup and identity paths
to accept the updated terminal/sudo path. Full application recovery remains a
separate gate even when SQL restoration succeeds.

Terminal/rewrap preparation verification: all 353 repository tests passed,
including 89 identity tests. Synthetic PTY tests changed old/new passphrases,
verified neither appeared in captured output and decrypted existing ciphertext
with the preserved key. Regression tests reject background/echoing terminals,
restore terminal settings, detect/reap stopped crypto children and preserve the
original identity on pre-replacement failures. Real owner rewrap and repeated
SQL restore through the revised sudo path remain pending.


## Privilege separation correction — October 24, 2026

The owner completed same-key passphrase rewrap with hidden input and verified new
phrase decryption. Offline-copy refresh is still required and is not inferred
from that report. The next restore attempt failed with
`recovery_terminal_not_foreground` (`identity-backup-HOJy8Ag3.json`) before asking
for a phrase or creating PostgreSQL. The foreground guard must not be bypassed.

The wrapper now authenticates sudo before the reporting pipe, then runs the
restore orchestrator as the desktop user. Interactive recovery-key reading and
age decryption stay in that user's foreground terminal, using the same private
PTY/no-echo reader as the accepted key-rewrap operation. No passphrase or recovery
identity is passed to a privileged helper.

Two bounded, noninteractive helpers retain only the operations that require root:

- `read-backup` accepts only completed `identity-<32 hex>.age` files beneath the
  fixed private backup directory and emits ciphertext into an anonymous fd.
- `restore-sql` receives the bounded decrypted archive via stdin, revalidates it
  at the privilege boundary and runs the existing isolated SQL restore/cleanup.

The orchestrator also validates the archive before invoking SQL and requires the
exact fixed helper success report. Neither helper prompts; sudo uses `-n`. Helper
calls retain the session for the existing sudo authentication cache, and receive
no key path, phrase or age command. No plaintext archive is staged on disk.
These are internal protocol roles, not new operator tasks.

Use the same `identity:backup:restore:check` command and the NEW recovery phrase.
Do not repeat key creation or rewrap merely to fix this terminal error. Expect
explicit reading-ciphertext, owner-unlock and isolated-SQL stages. The revised
privilege boundary still requires owner execution before live acceptance.

Preparation validation for this split: the full repository suite passed 358 tests.
The identity suite then passed 95 tests after adding a further privileged-timeout
cleanup regression. Tests cover unprivileged-only crypto, no key/phrase arguments
to privileged helpers, fixed ciphertext path selection, archive rejection before
SQL, exact helper-report parsing, wrapper routing and preserving terminal context
for sudo's authentication cache. Existing real-age/private-PTY synthetic tests
continue to pass; the revised root helper path still requires owner acceptance.


## Owner-run privilege-separated acceptance — October 24, 2026

The owner completed the same SQL restore through the revised privilege boundary.
Report `identity-backup-JD09hAso.json` was read back locally with status, archive
integrity, isolated SQL restore and cleanup all **passed**; household readiness
remains **pending**. Terminal evidence shows the owner-side hidden prompt between
protected-ciphertext reading and noninteractive privileged SQL restoration. No
phrase values are recorded. This supersedes the pending revised-path execution
statements above; those describe earlier preparation/failure states.

This accepts the SQL restore path using the rewrapped identity and existing
backup. It does not prove full native Authentik startup, encrypted-field access,
filesystem restoration permissions, browser login or TOTP after disaster recovery.
Offline recovery-identity copy refresh has not been confirmed by the owner.

The next gate is a separate full-application restore rehearsal: isolated temporary
state and networks, restored native database/files/secret, a distinct loopback-only
browser origin, native startup/decryption checks and owner login/TOTP verification.
Do not reuse live mounts, attach the rehearsal to agent networks, publish a LAN
listener or overwrite the current deployment to perform that rehearsal. A backup
predates later account changes, so rehearsal credentials must correspond to that
snapshot. Keep household readiness pending until the remaining gates pass.


## Prepared full-application rehearsal

[The separate rehearsal guide](identity_rehearsal.md) now provides a bounded
RAM-backed application restore at `127.0.0.2:19000`, native signing/TOTP readback,
owner browser checks and guarded cleanup. This is prepared source: application
and browser execution have not been accepted yet. The in-place production
restore remains intentionally outside this procedure.
