#!/usr/bin/env python3
"""Validate a public hardening activation record without sourcing shell text."""
from pathlib import Path
import sys
import yaml


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader,node,deep=False):
    value={}
    for key_node,value_node in node.value:
        key=loader.construct_object(key_node,deep=deep)
        if not isinstance(key,str) or key in value: raise ValueError('Duplicate/non-string field')
        value[key]=loader.construct_object(value_node,deep=deep)
    return value


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)


def load(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1000:
        raise ValueError('Invalid activation record')
    value = yaml.load(path.read_text(),Loader=UniqueLoader)
    if not isinstance(value,dict) or set(value) != {'schema_version','uid','gid'} or value['schema_version'] != 1:
        raise ValueError('Invalid activation schema')
    if type(value['uid']) is not int or type(value['gid']) is not int or not 0 < value['uid'] <= 2**31-1 or not 0 < value['gid'] <= 2**31-1:
        raise ValueError('Invalid identity')
    return value['uid'],value['gid']


if __name__=='__main__':
    try:
        uid,gid=load(Path(sys.argv[1]));print(f'{uid}:{gid}')
    except Exception:
        print('Invalid hardening activation record; details withheld.',file=sys.stderr)
        raise SystemExit(1)
