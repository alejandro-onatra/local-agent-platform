"""Run inside the restored pinned Authentik only; emit no identities or keys."""
import contextlib
import hmac
import json
import logging
import os
from pathlib import Path
import sys


def readback(phase):
    from authentik.root.setup import setup
    setup()
    import django
    django.setup()
    from authentik.tenants.models import Tenant
    tenant=Tenant.objects.get(schema_name='public',ready=True)
    with tenant:
        return inspect_restored(phase)


def inspect_restored(phase):
    from django.conf import settings
    from django.core import signing
    from authentik.core.models import User, Session
    from authentik.events.models import Event
    from authentik.stages.authenticator_totp.models import TOTPDevice
    secret=Path('/run/secrets/authentik-secret').read_text()
    if phase=='baseline':Session.objects.all().delete()  # Restore copy only: fresh login required.
    devices=list(TOTPDevice.objects.filter(confirmed=True,user__is_active=True)[:33])
    if not 0<len(devices)<=32:raise ValueError('restored_factor_inventory_unusable')
    result={'status':'passed','secret_loaded':hmac.compare_digest(settings.SECRET_KEY,secret),
        'signing_roundtrip':signing.loads(signing.dumps('synthetic-restore-signing'))=='synthetic-restore-signing',
        'host_only_cookie':settings.SESSION_COOKIE_DOMAIN in (None,''),
        'active_users_present':User.objects.filter(is_active=True).exists(),
        'confirmed_totp_present':True,'totp_material_readable':all(0<len(device.bin_key)<=40 for device in devices),
        'login_events':Event.objects.filter(action='login').count(),
        'totp_max_step':max(device.last_t for device in devices)}
    if not all(result[key] for key in ('secret_loaded','signing_roundtrip','host_only_cookie','active_users_present','totp_material_readable')):
        raise ValueError('restored_native_readback_failed')
    return result


def main():
    result={'status':'failed'}
    logging.disable(logging.CRITICAL)
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        try:
            phase=sys.argv[1]
            if phase not in ('baseline','check'):raise ValueError('invalid_phase')
            result=readback(phase)
        except Exception:pass
    print('IDENTITY_REHEARSAL_RESULT='+json.dumps(result),flush=True)
    return int(result['status']!='passed')


if __name__=='__main__':raise SystemExit(main())
