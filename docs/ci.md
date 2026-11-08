# Continuous integration

The required `Repository validation` check runs for pull requests and pushes
to `main`. It runs the repository's commit validation, followed by disposable
Docker Compose integration checks.

The integration checks validate a temporary Authentik/PostgreSQL deployment
and two synthetic OpenHands instances. They cover runtime controls, storage,
cross-instance authentication and state isolation, network boundaries,
WebSocket authentication, and recovery.

CI uses a disposable GitHub-hosted runner. It does not connect to the household
services or use household accounts, CA keys, passwords, persistent storage, or
the host Ollama model. These checks do not certify real-device login or model
inference.

## Local and CI security scans

The versioned pre-commit hook and the GitHub Actions workflow both run
`repo:commit:check`. That shared task runs Gitleaks for secret detection and
Trivy for dependency vulnerabilities and supported infrastructure
misconfigurations.

Install the checksum-locked tools once, then run only the Trivy scan:

```sh
mise install --locked
mise exec -- task security:trivy:check
```

Run the same full validation used by the pre-commit hook and CI with:

```sh
mise exec -- task repo:commit:check
```

The Trivy task fails on HIGH or CRITICAL findings. It scans repository files;
this initial check does not scan built or running container images. Trivy
refreshes its vulnerability database, so new advisories can change results
even when the source is unchanged. Gitleaks remains responsible for staged
content and local Git history; this Trivy scan does not replace it.
The check uses a temporary empty Docker configuration to download the public
vulnerability database without calling host credential helpers. It removes
that temporary configuration afterward and leaves the user's Docker settings
unchanged.
