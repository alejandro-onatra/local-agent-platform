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
3. Secrets in publishable files, staged content and local history (`security:secrets`).
4. LLM validation tests (`repo:test`).
5. Proxy authentication, routing and stream parsing tests (`observability:test`).
6. Secret gate acceptance tests using disposable Git repositories (`security:test`).
7. Synthetic workflow routing, denial, approval and resumption checks (`workflow:test`).

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
branch protection must enforce the same checks for a shared repository. Those
remote enforcement settings are not enabled yet.
