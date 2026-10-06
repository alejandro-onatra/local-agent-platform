#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:---plan}"
[[ "$#" -le 1 && ( "$mode" == --plan || "$mode" == --apply ) ]] || {
    printf 'Usage: bash scripts/host/install-docker-gpu.sh [--plan|--apply]\n' >&2; exit 2;
}
command -v python3 >/dev/null || { printf 'Python 3 is required.\n' >&2; exit 1; }
# Host packages are pinned separately from development tools managed by mise.
mapfile -t package_specs < <(python3 - "$repo_root/infra/host/versions.json" <<'PYCODE'
import json, sys
for package, version in json.load(open(sys.argv[1]))['packages'].items():
    print(f'{package}={version}')
PYCODE
)
[[ "${#package_specs[@]}" -eq 9 ]] || { printf 'Invalid package lock.\n' >&2; exit 1; }
printf 'Ubuntu 26.04 amd64: install these pinned packages:\n'
printf '  %s\n' "${package_specs[@]}"
printf 'Actions: add signed official APT repositories; install packages; configure NVIDIA Docker runtime; enable/restart Docker; run smoke checks.\n'
printf 'No GPU drivers will be replaced. No user is added to the docker group.\n'
[[ "$mode" == --apply ]] || exit 0
[[ "$EUID" -ne 0 ]] || { printf 'Run as your normal user; the script uses sudo where required.\n' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 26.04 && "${UBUNTU_CODENAME:-$VERSION_CODENAME}" == resolute && "$(dpkg --print-architecture)" == amd64 ]] || {
    printf 'This lock targets Ubuntu 26.04 resolute amd64 only.\n' >&2; exit 1;
}
# Do not remove distribution packages or alter an existing container workload.
for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    if [[ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)" == installed ]]; then
        printf 'Conflicting package installed: %s. Review before proceeding; nothing was removed.\n' "$package" >&2
        exit 1
    fi
done
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
sudo -v
if command -v docker >/dev/null && sudo docker info >/dev/null 2>&1; then
    if [[ -n "$(sudo docker ps -q)" ]]; then
        printf 'Running containers detected. Stop/review them before restarting Docker.\n' >&2; exit 1
    fi
fi
report_dir="$repo_root/artifacts/diagnostics"
mkdir -p -- "$report_dir"
report="$(mktemp "$report_dir/install-docker-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.txt")"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
backup_dir="/var/backups/agent-platform/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install_stack() {
    printf 'Started: %s\n' "$(date -u +%FT%TZ)"
    sudo install -m 0700 -d "$backup_dir"
    for file in /etc/apt/sources.list.d/docker.sources /etc/apt/sources.list.d/nvidia-container-toolkit.list /etc/apt/keyrings/docker.asc /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg /etc/docker/daemon.json; do
        if sudo test -f "$file"; then
            sudo cp --parents --preserve=mode,ownership,timestamps "$file" "$backup_dir/"
        fi
    done
    printf 'Configuration backups: %s\n' "$backup_dir"
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg
    # Download keys as user, then install them; no remote shell scripts are executed.
    curl --proto '=https' --tlsv1.2 -fsSL --retry 3 https://download.docker.com/linux/ubuntu/gpg -o "$work_dir/docker.asc"
    curl --proto '=https' --tlsv1.2 -fsSL --retry 3 https://nvidia.github.io/libnvidia-container/gpgkey -o "$work_dir/nvidia.asc"
    gpg --batch --dearmor --output "$work_dir/nvidia.gpg" "$work_dir/nvidia.asc"
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo install -m 0644 "$work_dir/docker.asc" /etc/apt/keyrings/docker.asc
    sudo install -m 0644 "$work_dir/nvidia.gpg" /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    cat > "$work_dir/docker.sources" <<'SOURCES'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: resolute
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
    printf '%s\n' 'deb [arch=amd64 signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/amd64 /' > "$work_dir/nvidia.list"
    sudo install -m 0644 "$work_dir/docker.sources" /etc/apt/sources.list.d/docker.sources
    sudo install -m 0644 "$work_dir/nvidia.list" /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update
    # APT must verify repository signatures; do not allow insecure repositories or downgrades.
    sudo apt-get install -y --no-install-recommends "${package_specs[@]}"
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl enable --now docker
    sudo systemctl restart docker
    # Assert exact requested package versions; host transitive dependencies are not fully locked.
    for spec in "${package_specs[@]}"; do
        package="${spec%%=*}"
        expected="${spec#*=}"
        actual="$(dpkg-query -W -f='${Version}' "$package")"
        [[ "$actual" == "$expected" ]] || { printf 'Version mismatch for %s: %s\n' "$package" "$actual" >&2; return 1; }
    done
    bash "$repo_root/scripts/host/check-docker-gpu.sh"
    printf 'Installation and basic container GPU checks completed.\n'
}
install_stack 2>&1 | tee "$report"
printf 'Installation report: %s\n' "$report"
