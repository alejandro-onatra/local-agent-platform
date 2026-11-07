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
