"""Bounded peer-network and native session WebSocket acceptance; no model execution."""
import ipaddress
import json
import socket
import sys
import uuid


def network_target(api,engine,tenant,service,network,port):
    cid=api.selected(engine,tenant,service)
    info=json.loads(engine.run(['docker','--context','default','inspect','--format',api.INSPECT,cid]))
    address=info['networks'][api.project(tenant)+'_'+network].get('IPAddress')
    value=ipaddress.ip_address(address)
    if value.version!=4 or not value.is_private or value.is_loopback or value.is_unspecified or value.is_multicast:
        raise api.PilotError('invalid_pilot_network_target')
    return {'address':str(value),'port':port}


def host_control(api,target,connect=socket.create_connection):
    try:
        with connect((target['address'],target['port']),timeout=2):pass
    except OSError:
        raise api.PilotError('network_target_positive_control_failed') from None


def checked_result(api,result,expected,category,tenant):
    if not isinstance(result,dict) or set(result)!=set(expected) or any(v is not True for v in result.values()):
        failed=[name for name in expected if not isinstance(result,dict) or result.get(name) is not True]
        raise api.PilotError(category,{'tenant':tenant['id'],'failed_checks':failed or ['probe_response_shape']})


def network_check(api,policy,lock,engine):
    api.health(policy);targets={}
    for tenant in policy['tenants']:
        api.runtime(engine,tenant,lock)
        targets[tenant['id']]=[
          network_target(api,engine,tenant,'openhands','backend',8000),
          network_target(api,engine,tenant,'ingress','backend',8080),
          network_target(api,engine,tenant,'ingress','frontend',8080)]
    for tenant_id,values in targets.items():
        for label,target in zip(('agent','backend_ingress','frontend_ingress'),values):
            try:host_control(api,target)
            except api.PilotError:
                raise api.PilotError('network_target_positive_control_failed',{'tenant':tenant_id,'target':label,'probe_phase':'before'}) from None
    results=[]
    for index,tenant in enumerate(policy['tenants']):
        data={'own':targets[tenant['id']][1],'foreign':targets[policy['tenants'][1-index]['id']]}
        cid=api.selected(engine,tenant,'openhands')
        program=(api.ROOT/'scripts/instances/network_probe.py').read_bytes()
        # Program and bounded JSON input travel on stdin; raw IPs are never printed.
        # exec() uses an explicit namespace: expose the callable without importing host packages.
        source=b'namespace={"__name__":"probe"}\nexec('+repr(program).encode()+b',namespace)\nimport json\nprint(json.dumps(namespace["check"]('+repr(data).encode()+b')))\n'
        result=json.loads(engine.run(['docker','--context','default','exec','-i',cid,'python','-B','-'],input=source,timeout=20))
        checked_result(api,result,('own_ingress_reachable','peer_agent_denied','peer_backend_ingress_denied','peer_frontend_ingress_denied'),
                       'live_peer_network_probe_failed',tenant)
        results.append({'tenant':tenant['id'],'checks':result})
    # Targets must still be listening; a dead target cannot explain a negative result.
    for tenant_id,values in targets.items():
        for label,target in zip(('agent','backend_ingress','frontend_ingress'),values):
            try:host_control(api,target)
            except api.PilotError:
                raise api.PilotError('network_target_positive_control_failed',{'tenant':tenant_id,'target':label,'probe_phase':'after'}) from None
    api.health(policy)
    return {'status':'passed','instances':results,'household_readiness':'pending',
      'scope':'Selected IPv4 TCP peer endpoints from actual agent namespaces; not host/LAN/internet/IPv6 or ingress-compromise egress certification'}


def websocket_check(api,policy,lock,engine):
    sessions=api.health(policy);created=[];identifiers=[str(uuid.uuid4()),str(uuid.uuid4())];results=[]
    try:
        for index,tenant in enumerate(policy['tenants']):
            api.runtime(engine,tenant,lock)
            path='/api/conversations/'+identifiers[index]
            if api.request(tenant,path,sessions[index])[0]!=404:raise api.PilotError('websocket_canary_collision')
            created.append((tenant,sessions[index],path))
            if api.request(tenant,'/api/conversations',sessions[index],'POST',api.conversation_payload(identifiers[index]))[0]!=201:
                raise api.PilotError('websocket_canary_create_failed')
        for index,tenant in enumerate(policy['tenants']):
            payload={'own_id':identifiers[index],'foreign_id':identifiers[1-index],
                     'own_key':sessions[index],'foreign_key':sessions[1-index]}
            script=(api.ROOT/'scripts/instances/websocket_probe.py').read_bytes()
            # The client uses the existing pinned image's websockets dependency.
            # Pass private payload to exec code via stdin, never Docker args/Env.
            program=b'namespace={"__name__":"probe"}\nexec('+repr(script).encode()+b',namespace)\nfrom websockets.sync.client import connect\nfrom websockets.exceptions import ConnectionClosed\nimport json\nprint(json.dumps(namespace["check"]('+repr(payload).encode()+b',connect,ConnectionClosed)))\n'
            name='agent-platform-ws-probe-'+uuid.uuid4().hex
            args=['docker','--context','default','run','--rm','-i','--name',name,
              '--label','agent-platform.websocket-probe=synthetic','--network',api.project(tenant)+'_frontend',
              '--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true',
              '--security-opt','apparmor=docker-default','--memory','256m','--cpus','1','--pids-limit','64',
              '--log-driver','none','--env','HTTP_PROXY=','--env','HTTPS_PROXY=','--env','ALL_PROXY=',
              '--env','http_proxy=','--env','https_proxy=','--env','all_proxy=','--env','NO_PROXY=*','--env','no_proxy=*',
              '--entrypoint','python',lock['image'],'-B','-']
            try:result=json.loads(engine.run(args,input=program,timeout=45))
            finally:
                try:engine.run(['docker','--context','default','rm','--force',name])
                except api.store.StorageError:pass
            checked_result(api,result,('own_authenticated_sync','anonymous_rejected','foreign_key_rejected','foreign_conversation_denied'),
                           'live_session_websocket_probe_failed',tenant)
            results.append({'tenant':tenant['id'],'checks':result})
    finally:
        failed=False
        for tenant,credential,path in created:
            try:
                status,_=api.request(tenant,path,credential,'DELETE')
                if status not in (200,404):failed=True
            except api.PilotError:failed=True
        if failed:
            original=sys.exc_info()[1]
            if isinstance(original,api.PilotError):
                original.details=(original.details or {})|{'synthetic_cleanup':'pending'}
            else:raise api.PilotError('websocket_canary_cleanup_failed')
    return {'status':'passed','instances':results,'household_readiness':'pending',
      'scope':'Native /sockets/session via each ingress, first-frame auth and idle conversation canaries only; legacy event/bash sockets, browser login/Origin policy and model execution remain pending'}
