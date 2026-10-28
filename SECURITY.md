# Security policy

This project is a local agent platform under active development. Passing tests
or publishing the repository does not establish production readiness or isolation
against every container/host attack. Review the [security scope](docs/security.md)
and [hardening plan](docs/hardening_plan.md) before deployment.

## Reporting a vulnerability

Contact the repository owner through a private channel you already trust. If the
repository offers private vulnerability reporting in its Security tab, use it.
Do not open a public issue containing exploit credentials, invitation links,
private keys, TOTP seeds, cookies, database dumps or personal conversation data.
Provide affected revision, prerequisites, expected/actual behavior and a minimal
synthetic reproduction. No security-response service level is promised.

## Supported scope

Security fixes target the current main branch. Older deployment snapshots and
third-party services require their own patch/upgrade review. Digest pinning does
not imply that an image is patched. Keep agent and identity services restricted
to the accepted local/LAN boundary; wider exposure requires separate acceptance.
