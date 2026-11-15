# Platform CLI

The CLI presents one read-only status snapshot for the local OpenHands runtime,
household instances, Authentik, the LAN gateway and observability services. It
reads only container names, image references and Docker process status from a
fixed Compose-project allowlist. It does not read logs, environment variables,
mount contents, passwords, tokens or conversation data.

## Commands

```bash
mise exec task -- task platform:status
mise exec task -- task platform:status SCOPE=household
mise exec task -- task platform:status:json SCOPE=all
```

The JSON task emits schema version 1 to stdout for shell, CI and monitoring
automation. Exit code `0` means every selected container is running or healthy;
`1` means a container is stopped, missing, starting or unhealthy; `2` means the
Docker engine cannot be queried without an interactive authentication prompt.

Set `SCOPE` to `all`, `local`, `household`, `identity`, `gateway` or
`observability` to filter either Go Task command. Invalid values are rejected
by the CLI. The standalone local OpenHands container is listed separately from
Alejandro's and Kimberly's authenticated household instances. This is a
host-owner/operator inventory, not a Canvas page or an administrator login; it
does not grant access to an agent. Open each person's Canvas URL through the
normal Authentik login to use that person's isolated instance.

## State meanings

- `healthy`: Docker's configured container health check passed.
- `running`: the container is running but has no passing Docker health check.
- `starting`, `stopped`, `unhealthy`, `missing` and `unknown` preserve the
  distinction between process state and a functioning application.

A running container does not prove that its API, login, model inference,
per-user routing or security controls work. Use the existing component-specific
`check`, `diagnose` and `accept` tasks for those deeper checks. The status command
never starts, stops, recreates or deletes services.

## Reading the snapshot

The overall state is `healthy` only when every selected container has a passing
health check, `running` when containers are running without health checks,
`partial` when some selected services are stopped or absent, and `degraded` or
`unhealthy` when a selected service is starting, unknown or unhealthy. Since
services are optional and may be intentionally stopped, `partial` is an inventory
result, not proof of a platform incident.
