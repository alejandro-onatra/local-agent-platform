#!/usr/bin/env python3
"""Read-only phase-A inventory. Visibility is evidence, not deployment approval."""
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
GIB = 1024 ** 3
TOOLS = ('virsh', 'virt-install', 'qemu-system-x86_64', 'kvm-ok')


def command(args):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
        return proc.stdout if proc.returncode == 0 and len(proc.stdout) <= 256_000 else None
    except (OSError, subprocess.SubprocessError):
        return None


def memory(text):
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] in {'MemTotal:', 'MemAvailable:', 'SwapTotal:'} and parts[2] == 'kB':
            value = int(parts[1])
            if value < 0:
                raise ValueError('Invalid memory observation')
            values[parts[0].rstrip(':')] = round(value * 1024 / GIB, 2)
    return {name: values.get(field) for name, field in
            [('total_gib', 'MemTotal'), ('available_gib', 'MemAvailable'), ('swap_gib', 'SwapTotal')]}


def cpu(text):
    flags = [set(line.split(':', 1)[1].split()) for line in text.splitlines()
             if line.startswith(('flags\t', 'flags ', 'Features\t', 'Features ')) and ':' in line]
    return {'logical_cpus': os.cpu_count(),
            'virtualization_flag_visible': any({'vmx', 'svm'} & flag for flag in flags) if flags else None}


def clean_network(addresses, routes4, routes6, wireless):
    """Retain only default-route interfaces; do not persist MACs or device identifiers."""
    if not all(isinstance(value, list) for value in (addresses, routes4, routes6)):
        raise ValueError('Invalid network observation')
    routes = []
    for route in [*routes4, *routes6]:
        if not isinstance(route, dict) or not isinstance(route.get('dev'), str):
            raise ValueError('Invalid route')
        item = {'interface': route['dev'], 'wireless': route['dev'] in wireless,
                'dhcp_reported': route.get('protocol') == 'dhcp'}
        if 'gateway' in route:
            item['gateway'] = str(ipaddress.ip_address(route['gateway']))
        routes.append(item)
    interfaces = {route['interface'] for route in routes}
    observed = []
    for link in addresses:
        if not isinstance(link, dict):
            raise ValueError('Invalid interface')
        if link.get('ifname') not in interfaces:
            continue
        for addr in link.get('addr_info', []):
            if addr.get('scope') != 'global':
                continue
            address = ipaddress.ip_address(addr['local'])
            prefix = int(addr['prefixlen'])
            if not 0 <= prefix <= address.max_prefixlen:
                raise ValueError('Invalid address prefix')
            observed.append({'interface': link['ifname'], 'address': str(address),
                             'prefix': prefix, 'family': address.version})
    return {'default_routes': routes, 'host_addresses': observed,
            'scope': 'Observed interfaces and routes; router DNS, guest isolation and reachability untested'}


def load_candidate(repo):
    path = repo / 'config/lan/candidate.yaml'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 10_000:
        raise ValueError('Invalid candidate file')
    value = yaml.safe_load(path.read_text())
    if (not isinstance(value, dict) or
            set(value) != {'schema_version', 'portal', 'decision', 'recommended_boundary', 'vm_candidate'} or
            value.get('schema_version') != 1 or value.get('portal') != 'portal.home.arpa' or
            value.get('recommended_boundary') not in {'virtual_machine','host_containers','dedicated_host'}):
        raise ValueError('Invalid candidate schema')
    limits = value['vm_candidate']
    fields = {'vcpus', 'memory_gib', 'disk_gib', 'host_memory_reserve_gib', 'storage_reserve_gib'}
    if set(limits) != fields or any(type(limits[k]) is not int or limits[k] <= 0 for k in fields):
        raise ValueError('Invalid resource proposal')
    if value.get('decision') not in {'pending', 'virtual_machine', 'dedicated_host', 'host_containers'}:
        raise ValueError('Invalid isolation decision')
    return value


def assess(observation, candidate):
    if candidate['decision'] in {'host_containers','dedicated_host'}:
        return {'status':'not_required','capacity':{},'prerequisites':{},
                'scope':'Selected boundary does not require this VM; household SEC acceptance remains pending'}
    limits = candidate['vm_candidate']
    capacity = {}
    for name, available, needed in [
        ('cpu', observation['cpu']['logical_cpus'], limits['vcpus']),
        ('memory', observation['memory']['available_gib'], limits['memory_gib'] + limits['host_memory_reserve_gib']),
        ('storage', observation['storage']['free_gib'], limits['disk_gib'] + limits['storage_reserve_gib']),
    ]:
        capacity[name] = 'pending' if available is None else 'passed' if available >= needed else 'failed'
    visible = observation['virtualization']
    prerequisites = {
        'cpu_flag_visible': 'passed' if observation['cpu']['virtualization_flag_visible'] is True else 'pending',
        'kvm_device_visible': 'passed' if visible['device_visible'] else 'pending',
        'kvm_device_accessible': 'passed' if visible['device_accessible'] else 'pending',
        'tools_installed': 'passed' if all(visible['tools'].values()) else 'pending',
        'owner_isolation_decision': 'passed' if candidate['decision'] == 'virtual_machine' else 'pending',
    }
    states = {*capacity.values(), *prerequisites.values()}
    return {'status': 'failed' if 'failed' in states else 'pending' if 'pending' in states else 'passed',
            'capacity': capacity, 'prerequisites': prerequisites,
            'scope': 'Snapshot feasibility for proposed VM; not allocation, firmware diagnosis or SEC acceptance'}


def collect(*, proc=Path('/proc'), sys=Path('/sys'), dev=Path('/dev'), runner=command, which=shutil.which):
    mem = memory((proc / 'meminfo').read_text())
    cpu_info = cpu((proc / 'cpuinfo').read_text())
    disk_path = Path('/var/lib/docker') if Path('/var/lib/docker').is_dir() else Path('/')
    disk = shutil.disk_usage(disk_path)
    network = None
    outputs = [runner(['ip', '-json', 'address', 'show']),
               runner(['ip', '-json', '-4', 'route', 'show', 'default']),
               runner(['ip', '-json', '-6', 'route', 'show', 'default'])]
    if all(output is not None for output in outputs):
        wireless = {p.name for p in (sys / 'class/net').glob('*') if (p / 'wireless').is_dir()}
        network = clean_network(*(json.loads(output) for output in outputs), wireless)
    info = platform.freedesktop_os_release()
    return {'os': {k: info.get(k) for k in ('ID', 'VERSION_ID')}, 'cpu': cpu_info, 'memory': mem,
            'storage': {'observed_path': str(disk_path), 'free_gib': round(disk.free / GIB, 2),
                        'scope': 'Filesystem containing this path; Docker data-root and guest storage not verified'},
            'virtualization': {'device_visible': (dev / 'kvm').exists(),
                              'device_accessible': os.access(dev / 'kvm', os.R_OK | os.W_OK),
                              'module_visible': (sys / 'module/kvm').is_dir(),
                              'tools': {name: bool(which(name)) for name in TOOLS},
                              'scope': 'Current execution context only; absent observations do not prove hardware incapability'},
            'network': network if network is not None else {'status': 'unavailable'},
            'router_dns_guest_networks': 'pending_owner_information',
            'family_devices_and_users': 'pending_owner_information',
            'offline_ca_custody': 'pending_supervised_procedure'}


def save(repo, report):
    directory = repo / 'artifacts/diagnostics'
    if directory.is_symlink() or directory.parent.is_symlink():
        raise ValueError('Linked output location')
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', prefix='lan-host-', suffix='.json', dir=directory, delete=False) as stream:
        os.chmod(stream.name, 0o600)
        json.dump(report, stream, indent=2)
        stream.write('\n')
        return Path(stream.name)


def main():
    os.umask(0o077)
    try:
        candidate = load_candidate(ROOT)
        observation = collect()
        readiness = assess(observation, candidate)
        report = {'schema_version': 1, 'time_utc': datetime.now(timezone.utc).isoformat(),
                  'status': 'collected', 'observations': observation, 'vm_candidate': readiness,
                  'proposal': candidate,
                  'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                    for name in ('config/lan/candidate.yaml', 'scripts/environment/inventory-lan.py')},
                  'scope': 'Read-only inventory; no host changes, allocation or deployed acceptance'}
        path = save(ROOT, report)
        print(json.dumps({'status': 'collected', 'cpu': observation['cpu'], 'memory': observation['memory'],
                          'storage_free_gib': observation['storage']['free_gib'], 'vm_candidate': readiness,
                          'network_details': 'Local private report only', 'household_sec_acceptance': 'pending'}, indent=2))
        print(f'Report: {path}')
        return 0
    except Exception:
        print('LAN inventory failed; raw diagnostics withheld. No changes applied.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
