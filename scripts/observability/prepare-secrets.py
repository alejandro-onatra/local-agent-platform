#!/usr/bin/env python3
"""Create persistent host-only credentials without printing their values."""
import argparse
import os
from pathlib import Path
import re
import secrets
import stat


def prepare(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Secret directory must not be a symlink')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for name, generate in [('admin-password', lambda: secrets.token_urlsafe(32)),
                           ('litellm-master-key', lambda: 'sk-'+secrets.token_hex(32))]:
        path = directory/name
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as output:
                output.write(generate()+'\n')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r') as existing:
            info = os.fstat(existing.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('Credential must be a regular file owned by the current user: '+name)
            value = existing.read(1024).strip()
            if name == 'litellm-master-key' and not re.fullmatch(r'sk-[a-f0-9]{64}', value):
                raise ValueError('Existing LiteLLM key is invalid; not overwritten automatically')
            if name == 'admin-password' and len(value) < 32:
                raise ValueError('Existing Grafana password is too short; not overwritten automatically')
            os.fchmod(existing.fileno(), 0o600)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    prepare(parser.parse_args().directory)
    print('Persistent Grafana and LiteLLM credentials prepared; values are not printed.')
