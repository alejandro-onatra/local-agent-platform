# Reproducible Repository Security

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
[Git commit validation](git_hooks.md). CI and branch protection do not enforce it yet. It does not guarantee finding secrets of any format.

## Proposed Controls, Still Not Installed or Executed

| Control | Tool and Evidence |
| --- | --- |
| Python Code | Semgrep with locally versioned rules, without `--config auto`; positive/negative cases of each rule |
| Python Dependencies | OSV-Scanner over `uv.lock`; pin the scanner and snapshot/date of the vulnerability database |
| Container Images | Trivy over existing digests; pin the scanner and vulnerability database |
| Infrastructure Configuration | Trivy config for supported formats; custom tests for our policies of Compose/Collector |
| Application Controls | Versioned OWASP ASVS 5.0.0 matrix and tests for authentication, permissions, isolation, redaction and auditing |
| Publishing | CI gate with pinned scanners and branch protection; not enabled yet |

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
