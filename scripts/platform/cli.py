#!/usr/bin/env python3
"""Read-only, scoped status view for local agent platform containers."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass(frozen=True)
class Component:
    scope: str
    label: str
    project: str
    service: str


COMPONENTS = (
    Component("local", "Ollama", "agent-platform-local", "ollama"),
    Component("local", "OpenHands local (standalone)", "agent-platform-local", "openhands"),
    Component("local", "Local Canvas proxy", "agent-platform-local", "openhands-proxy"),
    Component("household", "Alejandro agent", "agent-platform-household-alejandro", "openhands"),
    Component("household", "Alejandro ingress", "agent-platform-household-alejandro", "ingress"),
    Component("household", "Alejandro model relay", "agent-platform-household-alejandro", "model-relay"),
    Component("household", "Alejandro egress proxy", "agent-platform-household-alejandro", "egress-proxy"),
    Component("household", "Kimberly agent", "agent-platform-household-kimberly", "openhands"),
    Component("household", "Kimberly ingress", "agent-platform-household-kimberly", "ingress"),
    Component("household", "Kimberly model relay", "agent-platform-household-kimberly", "model-relay"),
    Component("household", "Kimberly egress proxy", "agent-platform-household-kimberly", "egress-proxy"),
    Component("identity", "Authentik database", "agent-platform-identity-local", "database"),
    Component("identity", "Authentik server", "agent-platform-identity-local", "server"),
    Component("identity", "Authentik worker", "agent-platform-identity-local", "worker"),
    Component("gateway", "Caddy gateway", "agent-platform-gateway", "gateway"),
    Component("observability", "Grafana", "agent-platform-observability", "grafana"),
    Component("observability", "Prometheus", "agent-platform-observability", "prometheus"),
    Component("observability", "Loki", "agent-platform-observability", "loki"),
    Component("observability", "Tempo", "agent-platform-observability", "tempo"),
    Component("observability", "OTel Collector", "agent-platform-observability", "collector"),
    Component("observability", "LiteLLM", "agent-platform-observability", "litellm"),
    Component("observability", "Blackbox exporter", "agent-platform-observability", "blackbox"),
)
SCOPES = ("all", "local", "household", "identity", "gateway", "observability")
STATE_STYLE = {
    "healthy": "bold green",
    "running": "cyan",
    "starting": "yellow",
    "stopped": "yellow",
    "unhealthy": "bold red",
    "missing": "dim yellow",
    "unknown": "bold magenta",
}


def run(command: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def docker_client() -> tuple[list[str] | None, str]:
    docker = shutil.which("docker")
    if not docker:
        return None, "docker_cli_missing"
    candidates = [[docker, "--context", "default"]]
    sudo = shutil.which("sudo")
    if sudo:
        candidates.append([sudo, "-n", docker, "--context", "default"])
    for candidate in candidates:
        result = run([*candidate, "info", "--format", "{{.ServerVersion}}"])
        if result and result.returncode == 0:
            return candidate, "available"
    return None, "docker_engine_unavailable_or_auth_required"


def state_from_detail(detail: str) -> str:
    value = detail.lower()
    if "(unhealthy)" in value:
        return "unhealthy"
    if "(health: starting)" in value or value.startswith("restarting") or value.startswith("created"):
        return "starting"
    if "(healthy)" in value:
        return "healthy"
    if value.startswith("up"):
        return "running"
    if value.startswith("exited") or value.startswith("dead"):
        return "stopped"
    return "unknown"


def inspect_component(client: list[str], component: Component) -> dict[str, object]:
    result = run([
        *client,
        "ps",
        "--all",
        "--filter", f"label=com.docker.compose.project={component.project}",
        "--filter", f"label=com.docker.compose.service={component.service}",
        "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}",
    ])
    base = {"scope": component.scope, "component": component.label}
    if not result or result.returncode != 0:
        return {**base, "status": "unknown", "containers": [], "reason": "docker_query_failed"}
    containers = []
    for row in result.stdout.splitlines():
        fields = row.split("\t", 2)
        if len(fields) != 3:
            continue
        name, image, detail = fields
        containers.append({
            "name": name,
            "image": image,
            "status": state_from_detail(detail),
            "detail": detail,
        })
    if not containers:
        return {**base, "status": "missing", "containers": []}
    states = [str(container["status"]) for container in containers]
    if "unhealthy" in states:
        status = "unhealthy"
    elif all(state == "healthy" for state in states):
        status = "healthy"
    elif all(state in {"healthy", "running"} for state in states):
        status = "running"
    elif "unknown" in states:
        status = "unknown"
    elif "starting" in states:
        status = "starting"
    else:
        status = "stopped"
    return {**base, "status": status, "containers": containers}


def overall_status(components: list[dict[str, object]], engine_status: str) -> str:
    if engine_status != "available":
        return "unknown"
    states = [str(item["status"]) for item in components]
    if any(state == "unhealthy" for state in states):
        return "unhealthy"
    if any(state in {"stopped", "missing"} for state in states):
        return "partial"
    if any(state in {"starting", "unknown"} for state in states):
        return "degraded"
    if all(state == "healthy" for state in states):
        return "healthy"
    return "running"


def snapshot(scope: str) -> dict[str, object]:
    client, engine_status = docker_client()
    selected = [item for item in COMPONENTS if scope == "all" or item.scope == scope]
    components = [
        inspect_component(client, item) if client else {
            "scope": item.scope,
            "component": item.label,
            "status": "unknown",
            "containers": [],
            "reason": engine_status,
        }
        for item in selected
    ]
    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": scope,
        "engine": {"status": engine_status},
        "status": overall_status(components, engine_status),
        "observation": "Docker container state only; application/API readiness is not checked.",
        "components": components,
    }


def render(data: dict[str, object]) -> None:
    table = Table(expand=True, show_lines=False)
    table.add_column("Area", style="dim", no_wrap=True)
    table.add_column("Component", min_width=20)
    table.add_column("State", no_wrap=True)
    table.add_column("Container / image", overflow="fold")
    for item in data["components"]:
        containers = item["containers"]
        detail = "not created"
        if containers:
            detail = "\n".join(
                f"{escape(container['name'])} · {escape(container['image'])} · {escape(container['detail'])}"
                for container in containers
            )
        state = str(item["status"])
        table.add_row(str(item["scope"]), str(item["component"]), f"[{STATE_STYLE[state]}]{state.upper()}[/]", detail)
    title = f"Local Agent Platform · {str(data['status']).upper()}"
    note = "Container/process snapshot only; API, login, inference and security acceptance require separate checks."
    console.print(Panel(table, title=title, subtitle=note, border_style="cyan"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the local agent platform.")
    commands = parser.add_subparsers(dest="command", required=True)
    status_parser = commands.add_parser("status", help="Show read-only container state.")
    status_parser.add_argument("--scope", choices=SCOPES, default="all")
    status_parser.add_argument("--json", dest="json_output", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Show a read-only snapshot of the project's fixed Compose services."""
    args = parse_args()
    data = snapshot(args.scope)
    if args.json_output:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        render(data)
    states = {str(item["status"]) for item in data["components"]}
    if data["engine"]["status"] != "available":
        raise SystemExit(2)
    if states - {"healthy", "running"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
