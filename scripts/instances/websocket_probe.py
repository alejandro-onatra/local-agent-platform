"""Native session WebSocket probe in an ephemeral client; keys stay on stdin/in memory."""
import json
import logging
import re
import sys
from uuid import UUID

logging.disable(logging.CRITICAL)


def validate(data):
    if not isinstance(data,dict) or set(data)!={'own_id','foreign_id','own_key','foreign_key'}:
        raise ValueError('invalid_probe')
    for field in ('own_id','foreign_id'):
        if str(UUID(data[field]))!=data[field]:raise ValueError('invalid_conversation')
    if data['own_id']==data['foreign_id']:raise ValueError('invalid_conversation')
    for field in ('own_key','foreign_key'):
        if not isinstance(data[field],str) or not re.fullmatch('[a-f0-9]{64}',data[field]):
            raise ValueError('invalid_key')
    if data['own_key']==data['foreign_key']:raise ValueError('shared_key')


def attempt(connect,closed,identifier,credential):
    # Never send a key via query, URI, CLI argument or environment variable.
    url='ws://ingress:8080/sockets/session/'+identifier
    try:
        with connect(url,open_timeout=5,close_timeout=2,max_size=65536) as socket:
            socket.send(json.dumps({'type':'auth','session_api_key':credential}))
            try:
                data=json.loads(socket.recv(timeout=5))
            except closed as error:
                # Only explicit native close codes count. A timeout/500/reset is a failure.
                code=error.rcvd.code if error.rcvd is not None else None
                return ('closed',code)
            return ('sync',None) if isinstance(data,dict) and data.get('type')=='sync' else ('unexpected',None)
    except closed as error:
        return ('closed',error.rcvd.code if error.rcvd is not None else None)


def check(data,connect,closed):
    validate(data)
    return {
      'own_authenticated_sync':attempt(connect,closed,data['own_id'],data['own_key'])==('sync',None),
      'anonymous_rejected':attempt(connect,closed,data['own_id'],None)==('closed',4001),
      'foreign_key_rejected':attempt(connect,closed,data['own_id'],data['foreign_key'])==('closed',4001),
      'foreign_conversation_denied':attempt(connect,closed,data['foreign_id'],data['own_key'])==('closed',4004),
    }


if __name__=='__main__':
    try:
        from websockets.sync.client import connect
        from websockets.exceptions import ConnectionClosed
        print(json.dumps(check(json.load(sys.stdin),connect,ConnectionClosed)))
    except Exception:
        print(json.dumps({'error':'native_session_websocket_probe_failed'}));raise SystemExit(1) from None
