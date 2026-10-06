#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
report_dir="$repo_root/artifacts/diagnostics"
mkdir -p -- "$report_dir"
report="$(mktemp "$report_dir/gpu-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.txt")"
set +e
(
    printf 'GPU diagnostic — %s\n' "$(date -u +%FT%TZ)"
    printf '\nSystem\n'
    cat /etc/os-release
    uname -r
    printf '\nPCI display devices\n'
    if command -v lspci >/dev/null 2>&1; then
        lspci -nnk | grep -A 3 -E 'VGA compatible controller|3D controller|Display controller'
    else
        printf 'lspci unavailable\n'
    fi
    printf '\nLoaded NVIDIA driver\n'
    if [[ -r /proc/driver/nvidia/version ]]; then
        cat /proc/driver/nvidia/version
    else
        printf 'No readable NVIDIA driver version\n'
    fi
    printf '\nVisible device nodes\n'
    find /dev -maxdepth 1 -name 'nvidia*' -ls
    printf '\nSecure Boot\n'
    if command -v mokutil >/dev/null 2>&1; then
        mokutil --sb-state
    else
        printf 'mokutil unavailable\n'
    fi
    printf '\nNVIDIA driver query\n'
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        printf 'RESULT: unavailable; nvidia-smi is not installed or not on PATH\n'
        exit 2
    fi
    nvidia-smi
    status=$?
    if [[ "$status" -ne 0 ]]; then
        printf 'RESULT: failed (exit %s); compare host terminal vs sandbox before changing drivers\n' "$status"
        exit "$status"
    fi
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    status=$?
    if [[ "$status" -ne 0 ]]; then
        printf 'RESULT: detailed query failed (exit %s)\n' "$status"
        exit "$status"
    fi
    printf 'RESULT: basic NVIDIA driver query passed; inference and container GPU tests remain pending\n'
) >"$report" 2>&1
status=$?
set -e
cat -- "$report"
printf '\nReport: %s\n' "$report"
exit "$status"
