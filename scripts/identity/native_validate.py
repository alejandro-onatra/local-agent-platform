"""Executed only inside the pinned Authentik image against its disposable DB.

Use native migrations, blueprint validation/import and ORM readback, not a
host-side emulation of Authentik. Never emit library logs, credentials or values.
"""
import contextlib
import json
import logging
import os
from pathlib import Path
import sys


def readback():
    from authentik.brands.models import Brand
    from authentik.core.models import Application, Group
    from authentik.flows.models import Flow, FlowStageBinding
    from authentik.outposts.models import Outpost
    from authentik.providers.proxy.models import ProxyProvider
    from authentik.policies.models import PolicyBinding
    from authentik.stages.authenticator_validate.models import AuthenticatorValidateStage
    flows={key:Flow.objects.get(slug='household-'+key) for key in ('login','authorize','logout')}
    assert flows['authorize'].authentication=='require_authenticated'
    for name,action in [('mfa-login','configure'),('mfa-access','deny')]:
        stage=AuthenticatorValidateStage.objects.get(name='household-'+name)
        assert stage.not_configured_action==action and set(stage.device_classes)=={'webauthn','totp'}
        assert stage.last_auth_threshold=='seconds=0' and stage.webauthn_user_verification=='required'
        assert set(stage.configuration_stages.values_list('name',flat=True))==({'household-webauthn','household-totp'} if action=='configure' else set())
    for key,names in [('login',['identify','password','mfa-login','session']),('authorize',['mfa-access']),('logout',['end-session'])]:
        assert list(FlowStageBinding.objects.filter(target=flows[key]).order_by('order').values_list('stage__name',flat=True))==['household-'+name for name in names]
    providers=[]
    for tenant in ('probe-a','probe-b'):
        group=Group.objects.get(name='household-group-'+tenant)
        assert not group.is_superuser and not group.users.exists()
        app=Application.objects.get(slug='household-'+tenant)
        provider=ProxyProvider.objects.get(name='household-provider-'+tenant)
        assert app.provider_id==provider.pk
        assert app.policy_engine_mode=='all' and provider.name=='household-provider-'+tenant
        assert provider.mode=='forward_single' and provider.external_host=='https://'+tenant+'.home.arpa'
        assert not provider.skip_path_regex and not provider.intercept_header_auth and not provider.basic_auth_enabled and not provider.cookie_domain
        assert provider.authentication_flow_id==flows['login'].pk and provider.authorization_flow_id==flows['authorize'].pk
        assert provider.invalidation_flow_id==flows['logout'].pk
        bindings=list(PolicyBinding.objects.filter(target=app))
        assert len(bindings)==1
        binding=bindings[0]
        assert binding.group_id==group.pk and binding.enabled and not binding.negate and not binding.failure_result
        assert binding.user_id is None and binding.policy_id is None
        providers.append(provider.pk)
    brand=Brand.objects.get(domain='login.home.arpa')
    assert brand.flow_authentication_id==flows['login'].pk and brand.flow_recovery_id is None
    outpost=Outpost.objects.get(name='authentik Embedded Outpost')
    assert set(outpost.providers.values_list('pk',flat=True))==set(providers)
    assert outpost.type=='proxy' and outpost.service_connection_id is None


def initialize():
    # Match manage.py in the pinned release: configure Authentik before Django.
    from authentik.root.setup import setup
    setup()
    import django
    django.setup()


def diagnostic(error):
    # Do not serialize exception text, module names, paths or connection strings.
    if isinstance(error,ModuleNotFoundError):return 'module_missing'
    if isinstance(error,ImportError):return 'import_error'
    if isinstance(error,PermissionError):return 'permission_denied'
    if isinstance(error,FileNotFoundError):return 'file_missing'
    if isinstance(error,AssertionError):return 'assertion_failed'
    if isinstance(error,OSError):return 'os_error'
    return {'ImproperlyConfigured':'configuration_error','AppRegistryNotReady':'registry_not_ready',
            'OperationalError':'database_unavailable','ProgrammingError':'database_schema_error','EntryInvalidError':'blueprint_rejected'}.get(type(error).__name__,'other')


VALIDATION_CODES={'required','invalid','invalid_choice','null','blank','unique','does_not_exist',
                  'incorrect_type','max_length','min_length','max_value','min_value'}


def validation_summary(error,entries):
    """Extract public entry/field identifiers and fixed codes; never error text."""
    entry=next((row for row in entries if row.id==getattr(error,'entry_id',None)),None)
    if entry is None:return None,[]
    validation=getattr(error,'validation_error',None)
    if validation is None:return entry.id,[]
    codes=validation.get_codes()
    if not isinstance(codes,dict):codes={'non_field_errors':codes}
    known=set(entry.attrs)|set(entry.identifiers)|{'non_field_errors'}
    def leaves(value,depth=0):
        if depth>3:return []
        if isinstance(value,str):return [value] if value in VALIDATION_CODES else []
        if isinstance(value,list):return [code for child in value[:8] for code in leaves(child,depth+1)]
        if isinstance(value,dict):return [code for child in list(value.values())[:8] for code in leaves(child,depth+1)]
        return []
    issues=[]
    for field,value in codes.items():
        if field in known:
            issues.extend({'field':field,'code':code} for code in sorted(set(leaves(value))))
    return entry.id,issues[:8]


def validate_native(importer):
    global failed_entry,validation_issues
    failed_entry=None;validation_issues=[]
    try:
        valid,_=importer.validate(raise_validation_errors=True)
    except Exception as error:
        failed_entry,validation_issues=validation_summary(error,importer.blueprint.entries)
        raise
    assert valid is True


def execute():
    initialize()
    from lifecycle.migrate import run_migrations
    from authentik.tenants.models import Tenant
    from authentik.blueprints.v1.importer import Importer
    global stage,failed_entry
    stage='migrations'
    run_migrations()
    stage='fresh_tenant'
    # The entire DB is new and disposable; use its fully migrated default realm.
    tenant=Tenant.objects.get(schema_name='public',ready=True)
    with tenant:
        from authentik.flows.models import Flow
        assert not Flow.objects.filter(slug='household-login').exists()
        stage='native_validation'
        raw=Path('/candidate/household-blueprint.yaml').read_text()
        importer=Importer.from_string(raw)
        stage='native_fields'
        from authentik.blueprints.v1.meta.registry import registry
        for entry in importer.blueprint.entries:
            failed_entry=entry.id
            label,name=entry.model.split('.')
            model=registry.get_model(label,name)
            fields=model().serializer().fields
            assert set(entry.attrs)|set(entry.identifiers) <= set(fields)
        failed_entry=None
        stage='native_validation'
        validate_native(importer)
        stage='native_import';assert importer.apply() is True
        stage='native_readback';readback()
        stage='idempotency'
        importer=Importer.from_string(raw)
        validate_native(importer);assert importer.apply() is True
        readback()


def main():
    global stage,failed_entry,validation_issues
    stage='django_setup';failed_entry=None;validation_issues=[];ok=False;reason=None
    # All intermediate output stays off the terminal and Docker logs.
    logging.disable(logging.CRITICAL)
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        try:execute();ok=True
        except Exception as error:reason=diagnostic(error)
    result={'status':'passed' if ok else 'failed','stage':'completed' if ok else stage}
    if not ok:
        result['diagnostic']=reason
        if failed_entry is not None:result['entry']=failed_entry
        if validation_issues:result['issues']=validation_issues
    print('IDENTITY_NATIVE_RESULT='+json.dumps(result),flush=True)
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
