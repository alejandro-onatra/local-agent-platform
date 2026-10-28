"""Run in the actual agent network namespace; no credentials or address output."""
import errno
import ipaddress
import json
import socket
import sys


def validate_target(target):
    if not isinstance(target,dict) or set(target)!={'address','port'}:
        raise ValueError('invalid_target')
    address=ipaddress.ip_address(target['address'])
    if address.version!=4 or not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError('invalid_target')
    if type(target['port']) is not int or target['port'] not in (8000,8080):
        raise ValueError('invalid_port')
    return str(address),target['port']


def reachable(target,connect=socket.create_connection):
    address,port=validate_target(target)
    try:
        with connect((address,port),timeout=2):return True
    except OSError as error:
        if error.errno not in {errno.ECONNREFUSED,errno.EHOSTUNREACH,errno.ENETUNREACH,
                              errno.ETIMEDOUT,errno.EACCES,errno.EPERM} and not isinstance(error,TimeoutError):
            raise
        return False


def check(data,connect=socket.create_connection):
    if not isinstance(data,dict) or set(data)!={'own','foreign'} or len(data['foreign'])!=3:
        raise ValueError('invalid_probe')
    results={'own_ingress_reachable':reachable(data['own'],connect)}
    for name,target in zip(('peer_agent_denied','peer_backend_ingress_denied','peer_frontend_ingress_denied'),data['foreign']):
        results[name]=not reachable(target,connect)
    return results


if __name__=='__main__':
    try:
        report=check(json.load(sys.stdin));print(json.dumps(report))
    except Exception:
        print(json.dumps({'error':'bounded_network_probe_failed'}));raise SystemExit(1) from None
