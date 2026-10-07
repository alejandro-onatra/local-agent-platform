# Docker and GPU — Local Reproducible Installation

## Status

The host GPU passed the check: RTX 4060 Ti, 16380 MiB, driver 580.178.04. Docker and NVIDIA Container Toolkit were installed and passed the checks from the host terminal on October 4, 2026, according to the output shared by the user.

Work has `no_new_privs` enabled, which prevents elevating privileges with sudo, and cannot control systemd. Therefore, the installation must be executed in a normal host terminal. There is no need to start Work as root or change the driver.

## Entry Point with mise

```bash
mise run env:plan
mise run env:setup  # only when host installation/configuration is needed
mise run env:check  # routine check of the installed environment
```

See [bootstrap of mise and tasks](environment.md). The scripts remain the implementation. Running them directly requires activating the prepared Python/PyYAML environment; for a new checkout follow environment.md first.

## Review and Install

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise run docker:plan
mise run docker:install
```

The script runs as Alejandro and asks for the password via sudo where appropriate. Do not paste the password in the chat. If APT proposes an unexpected operation, interrupt and review the result.

## Changes Made by the Installer

- Checks Ubuntu 26.04 `resolute`, architecture amd64, and confirms a satisfactory GPU.
- Stops before incompatible container packages; does not remove them automatically.
- Stops if it finds active containers before modifying the runtime/restarting Docker.
- Adds the official stable Docker/NVIDIA repositories and keys with `signed-by`.
- Installs the nine versions of `infra/host/versions.yaml`, verified in the official indexes on October 4, 2026.
- Configures NVIDIA in `/etc/docker/daemon.json`, enables and restarts Docker.
- Preserves previous configurations, if any, in `/var/backups/agent-platform/` with restricted access.
- Checks versions and runs hello-world and a `nvidia-smi` query inside a container.
- Saves local reports in `artifacts/diagnostics/`, excluded from Git.

Does not install CUDA Toolkit, does not replace drivers, does not open TCP ports, does not mount the personal folder in test containers, and does not add users to the docker group. The temporary test processes are removed with `--rm`; the downloaded images are stored.

System packages require privileges. The docker group provides equivalent access to root; for now, the checks use sudo when necessary, without modifying groups.

## Versions and Reproducibility Limits

The direct versions are fixed in `infra/host/versions.yaml`. The two test images are pinned by digest for Linux amd64; Ubuntu corresponds to the tag 24.04 in the initial resolution. APT validates repository signatures. The indexes consulted when preparing the lock are evidence of availability, not a validation of installation.

Transitive dependencies, base packages, and the kernel are not frozen. The script records what is verified and fails if a pinned version is no longer available; it does not automatically switch to latest. Apt holds are not used to prevent future security updates; upgrades must review and update the lock.

## Recheck

```bash
mise run docker:check
```

A satisfactory GPU query inside Docker verifies access to the device and the driver. CUDA loading and inference with a model will be later tests.

## If It Fails

- **sudo/no new privileges:** run in a normal host terminal, outside of Work.
- **Incompatible package:** review its use before uninstalling it; the script does not remove data from other runtimes.
- **APT cannot find a version:** review connectivity, repositories, and lock; do not substitute the Ubuntu codename.
- **Docker daemon does not start:** review `sudo systemctl status docker` and `sudo journalctl -u docker -n 80 --no-pager` before sharing an excerpt without secrets.
- **GPU does not appear in the container:** confirm `nvidia-smi` first on the host, review `sudo docker info` and NVIDIA configuration.
- **Partial installation:** the script stops at the first error and may have created repositories or installed part of the packages. Review the report before repeating. Reinstalling the same versions normally allows continuing.

Restoring configuration requires reviewing the specific backups and stopping the workloads first. There is no automatic rollback that removes Docker, images, or volumes.

## Sources

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [docker group permissions](https://docs.docker.com/engine/install/linux-postinstall/)

## Validation completed — October 4, 2026

Evidence: installer output shared by the user; it is not a daemon execution from Work.

| Component | Result |
| --- | --- |
| Docker Engine client/server | 29.8.2 / 29.8.2 |
| containerd | 2.3.6 |
| Compose | 5.6.0 |
| Buildx | 0.37.1 |
| NVIDIA Container Toolkit | 1.20.1-1 installed and runtime configured |
| hello-world | Correct execution with image pinned by digest |
| GPU inside container | RTX 4060 Ti, 16380 MiB, driver 580.178.04 |
| APT versions fixed | The installer completed the check of the nine versions |

The NVIDIA runtime is available and the default runtime remains runc. The GPU test passed with `--gpus` without changing the host driver.

Local check report: `artifacts/diagnostics/docker-gpu-20261004T203234Z-ME33dN.txt`.

Backup of configuration reported by the installer: `/var/backups/agent-platform/20261004T203210Z-158073`.

Status: Docker installation and GPU visibility from containers approved. Missing to install a model server and verify real inference, VRAM usage, latency, and tool calls before testing OpenHands.
