# Git commit validation

## Install in each checkout with mise

```bash
mise trust mise.toml
mise install --locked
mise run env:python:setup
mise run repo:hooks:install
mise run repo:hooks:check
```

The installer sets local `core.hooksPath` to `.githooks`. Hooks are versioned;
Git does not enable them automatically when cloning. The installer refuses to
replace a different existing hooks path. It does not alter global Git settings.

## What runs on every normal commit

`.githooks/pre-commit` runs `mise exec -- task repo:commit:check`:

1. Repository files and shell syntax (`mise run repo:check`).
2. Existing Python environment and uv lock consistency (`mise run env:python:check`).
3. Offline Compose baseline regression guards (`security:config`); this is not SEC deployment approval.
4. Secrets in publishable files, staged content and local history (`security:secrets`).
5. Host inventory privacy/capacity regression tests (`repo:environment:test`).
6. LLM validation tests (`repo:test`).
7. Proxy authentication, routing and stream parsing tests (`observability:test`).
8. Secret gate and SEC source/TLS guard tests using disposable fixtures (`security:test`).
9. Synthetic workflow routing, denial, approval and resumption checks (`workflow:test`).

Commands run sequentially. Any failure returns a nonzero status and aborts the
commit. The hook does not install dependencies, invoke sudo, download models or
start/stop containers. Prepare the environment explicitly before committing.
Secret scan reports are redacted and stored locally under `artifacts/security/`.
Test output is shown in the terminal. These checks validate current code and the
staged secret content; commit coherent, reviewed changes rather than relying on
unstaged fixes to make a staged version pass its tests.

## Add checks

Add a short task call to `repo:commit:check` in `Taskfile.yml`. Keep implementation
in categorized scripts. mise owns tool installation, environment checks and hook
installation; Task owns code tests and the commit validation sequence.

```bash
# Run the same sequence explicitly:
mise exec -- task repo:commit:check
```

These hooks are local safeguards. Git can bypass them with `--no-verify`; CI and
branch protection must enforce the same checks for a shared repository. A remote
workflow is now prepared; the first GitHub run remains unverified and the public API
reported main as unprotected on October 28.


The optional `repo:hooks:test` exercises actual commits in a disposable clone:
clean changes pass; synthetic secrets, unsafe wildcard Compose exposure and
invalid shell syntax are rejected. It never commits to the project checkout.
The hook uses source guards only; it does not connect to the household portal.

## GitHub validation workflow

`.github/workflows/validate.yml` uses the same `repo:commit:check` gate on main
pushes, pull requests and manual runs. It fetches complete history, does not
persist checkout credentials, gives the job only read access to contents, and
uses the existing checksum-verified pinned mise bootstrap plus locked tools.
It does not deploy, use runtime credentials or request an OIDC token. The hosted
Ubuntu runner image itself is maintained by GitHub, not frozen by this repository.

The workflow file being present does not make it a required check. After its first
successful remote run, verify required `Repository validation` checks, review
requirements and bypass/force-push rules through authenticated GitHub settings.
A pull request's success is not evidence of deployed tenant or firewall controls.

The rehearsal creates a harmless text change inside the disposable clone so it
can exercise a real clean commit even when the source checkout has no changes.
Failures return a fixed phase name, not potentially sensitive command output.

The October 28 public API readback reports `main.protected: false`. Treat branch
enforcement as a pending hardening action, not an active safeguard. Detailed
repository access/security settings still require authenticated review.
