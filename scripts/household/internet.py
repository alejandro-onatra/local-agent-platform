"""Owner-only household Internet cutoff and runtime verification."""
import datetime
import json
import os
import stat
from pathlib import Path


class InternetError(ValueError):
    """Fixed public errors; never include Docker output or URLs."""


def effective_on(proxy_running, global_off):
    return bool(proxy_running and not global_off)


def _text(value):
    return value.decode().strip() if isinstance(value, bytes) else str(value).strip()


def _container(engine, project, service):
    rows=_text(engine.run(['docker','--context','default','ps','--all','--format','{{.Names}}',
        '--filter','label=com.docker.compose.project='+project,
        '--filter','label=com.docker.compose.service='+service])).splitlines()
    if not rows:return None
    expected=project+'-'+service+'-1'
    if rows!=[expected]:raise InternetError('internet_container_identity_drift')
    try:
        return json.loads(engine.run(['docker','--context','default','inspect','--format','{{json .}}',expected]))
    except Exception:
        raise InternetError('internet_container_inspection_failed') from None


def _state(container):
    if container is None:return 'absent'
    state=container.get('State',{})
    if state.get('Running') is True:return 'running'
    if state.get('Running') is False:return 'stopped'
    raise InternetError('internet_container_state_unknown')


def _browser_enabled(container):
    if container is None:return False
    values=set(container.get('Config',{}).get('Env',[]))
    return ('OH_ENABLE_BROWSER=true' in values and 'VITE_ENABLE_BROWSER_TOOLS=true' in values and
        'HTTPS_PROXY=http://egress-proxy:3128' in values and
        'BROWSER_USE_PROXY_SERVER=http://egress-proxy:3128' in values)


def _ensure_state_directory(base):
    parent=Path(base)
    target=parent/'internet'
    if not parent.exists() or parent.is_symlink():raise InternetError('internet_state_root_unavailable')
    parent_info=parent.lstat()
    if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid!=0 or stat.S_IMODE(parent_info.st_mode)!=0o700:
        raise InternetError('unsafe_internet_state_root')
    if not target.exists() and not target.is_symlink():target.mkdir(mode=0o700)
    info=target.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:
        raise InternetError('unsafe_internet_state_directory')
    return target


def _global_off(marker):
    if not marker.exists() and not marker.is_symlink():return False
    info=marker.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600:
        raise InternetError('unsafe_global_internet_override')
    if marker.read_bytes()!=b'global-off\n':raise InternetError('unsafe_global_internet_override')
    return True


def _write_global_off(marker):
    import tempfile
    fd,name=tempfile.mkstemp(prefix='.global-off-',dir=marker.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o600);stream.write(b'global-off\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,marker)
        directory_fd=os.open(marker.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:temporary.unlink(missing_ok=True)


def _audit(directory, action, username, actor_uid, outcome):
    path=directory/'audit.jsonl'
    flags=os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK
    fd=os.open(path,flags,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600:
            raise InternetError('unsafe_internet_audit_log')
        row={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'action':action,'tenant':username,'requested_by_uid':actor_uid,'result':outcome}
        os.write(fd,(json.dumps(row,separators=(',',':'))+'\n').encode());os.fsync(fd)
    finally:os.close(fd)


def _stop_proxy(engine, project):
    container=_container(engine,project,'egress-proxy')
    if _state(container)!='running':return
    name=project+'-egress-proxy-1'
    try:engine.run(['docker','--context','default','stop','--time','0',name],timeout=15)
    except Exception:pass
    container=_container(engine,project,'egress-proxy')
    if _state(container)=='running':
        try:engine.run(['docker','--context','default','kill',name],timeout=15)
        except Exception:pass
    if _state(_container(engine,project,'egress-proxy'))=='running':
        raise InternetError('internet_cutoff_unverified')


def _verify_proxy(container, tenant, project, image, config_path, engine):
    actual=container.get('Config',{});host=container.get('HostConfig',{})
    labels=actual.get('Labels',{})
    if (container.get('State',{}).get('Running') is not True or actual.get('Image')!=image or
        actual.get('User')!='584792:584792' or labels.get('com.docker.compose.project')!=project or
        labels.get('com.docker.compose.service')!='egress-proxy' or
        host.get('ReadonlyRootfs') is not True or host.get('Privileged') or host.get('CapAdd') or
        set(host.get('CapDrop') or [])!={'ALL'} or host.get('PortBindings') or host.get('Devices') or
        host.get('DeviceRequests') or host.get('PidMode') or host.get('IpcMode')=='host' or
        host.get('Memory')!=192*1024**2 or host.get('PidsLimit')!=96 or host.get('NanoCpus')!=10**9 or
        set(host.get('SecurityOpt') or [])!={'no-new-privileges:true','apparmor:docker-default'} or
        container.get('AppArmorProfile')!='docker-default'):
        raise InternetError('internet_proxy_runtime_drift')
    expected_tmpfs={'/tmp':'rw,nosuid,nodev,noexec,size=16m,mode=1777',
        '/var/log/squid':'rw,nosuid,nodev,noexec,size=8m,mode=0750,uid=584792,gid=584792',
        '/var/spool/squid':'rw,nosuid,nodev,noexec,size=16m,mode=0750,uid=584792,gid=584792',
        '/run':'rw,nosuid,nodev,noexec,size=8m,mode=0750,uid=584792,gid=584792'}
    if host.get('Tmpfs')!=expected_tmpfs:raise InternetError('internet_proxy_tmpfs_drift')
    networks=container.get('NetworkSettings',{}).get('Networks',{})
    if set(networks)!={project+'_backend',project+'_egress'}:
        raise InternetError('internet_proxy_network_drift')
    for name in networks:
        try:network=json.loads(engine.run(['docker','--context','default','network','inspect',name]))[0]
        except Exception:raise InternetError('internet_proxy_network_inspection_failed') from None
        if network.get('Driver')!='bridge' or network.get('Internal') is not name.endswith('_backend'):
            raise InternetError('internet_proxy_network_boundary_drift')
    binds=[mount for mount in container.get('Mounts',[]) if mount.get('Type')=='bind']
    if len(binds)!=1 or binds[0].get('Source')!=str(config_path) or binds[0].get('Destination')!='/etc/squid/squid.conf' or binds[0].get('RW') is not False:
        raise InternetError('internet_proxy_mount_drift')


def _verify_control_file(path, expected):
    path=Path(path)
    try:info=path.lstat()
    except OSError:raise InternetError('internet_control_file_unavailable') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or
        stat.S_IMODE(info.st_mode)!=0o644 or path.read_bytes()!=expected):
        raise InternetError('internet_control_file_drift')


def operate(action, username, *, engine, base, tenants, controls, lock, actor_uid,
            render_compose, expected_squid):
    if os.geteuid()!=0:raise InternetError('host_admin_required')
    if action not in {'on','off','global-off','global-on','status'}:raise InternetError('unknown_internet_action')
    by_id={tenant['id']:tenant for tenant in tenants}
    if action in {'on','off'} and username not in by_id:raise InternetError('unknown_household_username')
    if action=='status' and username is not None and username not in by_id:raise InternetError('unknown_household_username')
    directory=_ensure_state_directory(base);marker=directory/'global-off'
    globally_off=_global_off(marker)
    selected=[by_id[username]] if username in by_id else tenants
    projects={tenant['id']:'agent-platform-household-'+tenant['id'] for tenant in selected}
    if action=='status':
        states={}
        for tenant in selected:
            project=projects[tenant['id']]
            proxy=_container(engine,project,'egress-proxy')
            agent=_container(engine,project,'openhands')
            running=_state(proxy)=='running'
            states[tenant['id']]={'proxy':'running' if running else 'stopped',
                'effective_internet':effective_on(running,globally_off),
                'browser_tools_enabled':_browser_enabled(agent)}
        if globally_off and any(row['effective_internet'] for row in states.values()):
            raise InternetError('global_internet_cutoff_not_enforced')
        return {'status':'passed','global_off':globally_off,'instances':states,
            'scope':'Runtime switch state only; browser traffic and DNS acceptance require the live checks'}
    if type(actor_uid) is not int or actor_uid<0:raise InternetError('invalid_internet_actor')
    outcome='passed'
    try:
        if action=='global-off':
            _write_global_off(marker)
            for tenant in tenants:_stop_proxy(engine,'agent-platform-household-'+tenant['id'])
        elif action=='global-on':
            if globally_off:
                for tenant in tenants:_stop_proxy(engine,'agent-platform-household-'+tenant['id'])
                marker.unlink()
                directory_fd=os.open(marker.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
            # Clearing the override never starts a proxy; each tenant remains off.
        elif action=='off':
            _stop_proxy(engine,projects[username])
        elif action=='on':
            if globally_off:raise InternetError('global_internet_cutoff_active')
            tenant=by_id[username];project=projects[username];control=Path(controls[username])
            import yaml
            expected=yaml.safe_dump(render_compose(tenant,lock),sort_keys=False).encode()
            compose=control/'compose.yaml';squid=control/'squid.conf'
            _verify_control_file(compose,expected);_verify_control_file(squid,expected_squid)
            agent=_container(engine,project,'openhands')
            if not _browser_enabled(agent):raise InternetError('household_browser_tools_not_applied')
            try:
                engine.run(['docker','--context','default','compose','--project-name',project,
                    '--file',str(compose),'--profile','internet','up','-d','--no-deps','--pull','never','egress-proxy'],timeout=120)
            except Exception:raise InternetError('internet_proxy_start_failed') from None
            proxy=_container(engine,project,'egress-proxy')
            try:_verify_proxy(proxy,tenant,project,lock['egress']['image'],squid,engine)
            except InternetError:
                _stop_proxy(engine,project)
                raise
        _audit(directory,action,username,actor_uid,outcome)
    except InternetError:
        outcome='failed'
        try:_audit(directory,action,username,actor_uid,outcome)
        except Exception:pass
        if action=='on':_stop_proxy(engine,projects[username])
        raise
    except Exception:
        outcome='failed'
        try:_audit(directory,action,username,actor_uid,outcome)
        except Exception:pass
        if action=='on':_stop_proxy(engine,projects[username])
        raise InternetError('internet_operation_failed') from None
    try:
        state=operate('status',username if action in {'on','off'} else None,engine=engine,base=base,
            tenants=tenants,controls=controls,lock=lock,actor_uid=actor_uid,
            render_compose=render_compose,expected_squid=expected_squid)
    except Exception:
        if action=='on':_stop_proxy(engine,projects[username])
        raise
    return {'status':'passed','action':action,'global_off':state['global_off'],
        'instances':state['instances'],'scope':'Owner-controlled proxy state; no browser request was made'}
