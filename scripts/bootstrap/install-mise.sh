#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - "$repo_root/infra/host/mise-version.json" <<'PYCODE'
import hashlib, io, json, os, platform, sys, tarfile, urllib.request
from pathlib import Path
if platform.system() != 'Linux' or platform.machine() != 'x86_64':
    raise SystemExit('This mise lock targets Linux x86_64.')
if os.geteuid() == 0:
    raise SystemExit('Run as your normal user, without sudo.')
lock=json.loads(Path(sys.argv[1]).read_text())
dest=Path.home()/'.local/bin/mise'
if dest.exists():
    if hashlib.sha256(dest.read_bytes()).hexdigest()==lock['binary_sha256']:
        print(f"mise {lock['version']} already installed at {dest}")
        raise SystemExit(0)
    raise SystemExit(f'{dest} already exists with a different binary; review before replacing it.')
raw=urllib.request.urlopen(lock['url'],timeout=120).read()
if hashlib.sha256(raw).hexdigest()!=lock['sha256']:
    raise SystemExit('Download checksum mismatch; nothing installed.')
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
    member=next(m for m in archive.getmembers() if m.name.endswith('/bin/mise') and m.isfile())
    binary=archive.extractfile(member).read()
if hashlib.sha256(binary).hexdigest()!=lock['binary_sha256']:
    raise SystemExit('Binary checksum mismatch; nothing installed.')
dest.parent.mkdir(parents=True,exist_ok=True)
with dest.open('xb') as out:
    out.write(binary)
dest.chmod(0o755)
print(f"Installed mise {lock['version']} at {dest}; checksum verified.")
PYCODE
