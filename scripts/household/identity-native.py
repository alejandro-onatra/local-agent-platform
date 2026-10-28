"""Run inside the pinned Authentik server. Payload via stdin, sanitized result only."""
import contextlib,json,logging,sys
logging.disable(logging.CRITICAL)
stage='input'

def configure_embedded_outpost(outpost, providers, login_url):
    """Use Authentik's typed configuration; retain unrelated options/providers."""
    global stage
    from dataclasses import replace
    stage='embedded_outpost_config'
    # Embedded outposts use authentik_host for browser-facing OIDC endpoints.
    config=replace(outpost.config,authentik_host=login_url,
                   authentik_host_browser=login_url)
    stage='embedded_outpost_providers'
    outpost.providers.add(*providers)
    outpost.config=config
    stage='embedded_outpost_save'
    outpost.save()
    stage='embedded_outpost_readback'
    outpost.refresh_from_db()
    assert outpost.config.authentik_host==login_url
    assert outpost.config.authentik_host_browser==login_url
    assert {provider.pk for provider in providers} <= set(outpost.providers.values_list('pk',flat=True))


def apply_brand_appearance(brand,expected_css,flows):
    """Read back native appearance without rejecting DRF's boundary whitespace trim."""
    global stage
    stage='brand_scope'
    assert not brand.default
    stage='brand_css'
    # ModelSerializer CharField trims boundary whitespace. Internal CSS is still exact.
    assert isinstance(brand.branding_custom_css,str) and isinstance(expected_css,str)
    assert brand.branding_custom_css.strip()==expected_css.strip()
    stage='brand_theme_write'
    attributes=dict(brand.attributes or {})
    settings=dict(attributes.get('settings') or {})
    theme=dict(settings.get('theme') or {})
    theme['base']='light';settings['theme']=theme;attributes['settings']=settings
    brand.attributes=attributes;brand.save();brand.refresh_from_db()
    stage='brand_theme_readback'
    assert brand.attributes['settings']['theme']['base']=='light'
    for flow in flows:
        stage='brand_layout_'+flow.slug.replace('-','_')
        assert flow.layout=='content_right'


def migrate_brand_origin(Brand,login_url):
    """Rename only our non-default family brand from bare host to exact host:port."""
    global stage
    from urllib.parse import urlsplit
    stage='brand_domain_migration'
    url=urlsplit(login_url)
    assert url.scheme=='https' and url.port==8443 and url.username is None and url.password is None
    legacy=Brand.objects.filter(domain=url.hostname).first()
    target=Brand.objects.filter(domain=url.netloc).first()
    if legacy:
        assert target is None
        assert not legacy.default and legacy.flow_authentication.slug=='family-login'
        legacy.domain=url.netloc;legacy.save()
    elif target:
        assert not target.default and target.flow_authentication.slug=='family-login'


def invitation_plan_summary(plan, name, group):
    """Return fixed booleans only; never serialize session or credential values."""
    context=getattr(plan,'context',None)
    if not isinstance(context,dict):return None
    invite=context.get('invitation')
    if not invite or getattr(invite,'name',None)!='family-invite-'+name:return None
    flow=getattr(invite,'flow',None)
    if not flow or getattr(flow,'slug',None)!='family-enroll-'+name:return None
    fixed=getattr(invite,'fixed_data',None)
    generation=fixed.get('generation') if isinstance(fixed,dict) else None
    attributes=getattr(group,'attributes',None)
    current=attributes.get('invitation_generation') if isinstance(attributes,dict) else None
    invite_valid=isinstance(generation,str) and len(generation)==64
    group_valid=isinstance(current,str) and len(current)==64
    return {'invitation_in_effect':context.get('invitation_in_effect') is True,
            'invitation_generation_valid':invite_valid,
            'group_generation_valid':group_valid,
            'generation_matches':invite_valid and group_valid and generation==current,
            'group_is_admin':bool(group.is_superuser)}


def mfa_failure_summary(events, observed_at, method_args_key):
    """Summarize native failed-login metadata without exporting event context."""
    rejected=[]
    for event in events:
        context=event.context if isinstance(event.context,dict) else {}
        args=context.get(method_args_key)
        if not isinstance(args,dict) or args.get('device_class')!='totp':continue
        age=int((observed_at-event.created).total_seconds())
        if 0 <= age <= 900:rejected.append(age)
    return {'totp_rejections_last_15m':len(rejected),
            'last_totp_rejection_age_seconds':min(rejected) if rejected else None}


def totp_runtime_summary(devices, observed_at):
    """Read verification metadata only; never generate or verify a token."""
    recent=0;blocked=0
    for device in devices:
        used=device.last_used
        if used is not None and 0 <= (observed_at-used).total_seconds() <= 600:recent+=1
        allowed,_=device.verify_is_allowed()
        if not allowed:blocked+=1
    return {'confirmed_devices':len(devices),'devices_verified_last_10m':recent,
            'devices_temporarily_blocked':blocked}


def authorization_plan_summary(plan, flow_ids, session_username=None):
    """Expose fixed flow-state indicators, never OAuth parameters or session values."""
    context=getattr(plan,'context',None)
    if not isinstance(context,dict):return None
    flow=flow_ids.get(getattr(plan,'flow_pk',None))
    if flow not in ('family-login','family-authorize'):return None
    user=context.get('pending_user')
    name=getattr(user,'username',None) or session_username
    if name not in ('alejandro','kimberly'):return None
    bindings=getattr(plan,'bindings',[])
    stages=[binding.stage for binding in bindings]
    return {'username':name,'flow':flow,
        'mfa_pending':any(getattr(item,'name',None) in ('family-mfa-login','family-mfa-access') for item in stages),
        'oauth_parameters_present':context.get('goauthentik.io/providers/oauth2/params') is not None,
        'oauth_completion_pending':any(getattr(getattr(item,'view',None),'__name__',None)=='OAuthFulfillmentStage' for item in stages),
        'application_context_present':context.get('application') is not None}


def invitation_entry_url(origin, name, token):
    """Start through native cancellation so same-flow browser plans cannot reuse old invites."""
    import ipaddress
    from urllib.parse import urlencode, urlsplit
    from uuid import UUID
    assert name in ('alejandro','kimberly')
    parsed=urlsplit(origin)
    assert parsed.scheme=='https' and parsed.port==8443 and parsed.username is None and parsed.password is None
    address=ipaddress.IPv4Address(parsed.hostname)
    assert address.is_private and not address.is_loopback and not address.is_link_local
    assert parsed.path in ('','/') and not parsed.query and not parsed.fragment
    target='/if/flow/family-enroll-'+name+'/?'+urlencode({'itoken':str(UUID(str(token)))})
    return 'https://'+parsed.netloc+'/flows/-/cancel/?'+urlencode({'next':target})


def execute(data):
    global stage
    stage='django_setup'
    from authentik.root.setup import setup
    setup()
    import django
    django.setup()
    from authentik.tenants.models import Tenant
    tenant=Tenant.objects.get(schema_name='public',ready=True)
    with tenant:
        from authentik.core.models import User,Group,Application
        from authentik.providers.proxy.models import ProxyProvider
        from authentik.outposts.models import Outpost
        from django.db import transaction
        from authentik.flows.models import Flow, FlowStageBinding
        from authentik.stages.invitation.models import Invitation, InvitationStage
        from authentik.stages.prompt.models import PromptStage
        from authentik.stages.user_write.models import UserWriteStage
        from django.utils.timezone import now
        from datetime import timedelta
        import secrets
        names=['alejandro','kimberly']
        if data['action']=='diagnose':
            from dataclasses import is_dataclass
            stage='diagnostic_readback'
            outpost=Outpost.objects.get(name='authentik Embedded Outpost')
            config=outpost.config
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FILTER (WHERE cardinality(pg_blocking_pids(pid)) > 0), "
                               "count(*) FILTER (WHERE state = 'idle in transaction') "
                               "FROM pg_stat_activity WHERE datname = current_database()")
                blocked,idle_transaction=cursor.fetchone()
            from authentik.stages.authenticator_totp.models import TOTPDevice
            enrollment={}
            for name in names:
                user=User.objects.filter(username=name).first()
                enrollment[name]={'account_exists':user is not None,'account_active':user.is_active if user else None,
                    'totp_configured':TOTPDevice.objects.filter(user=user,confirmed=True).exists() if user else False,
                    'pending_invitation':Invitation.objects.filter(name='family-invite-'+name).exists()}
                devices=list(TOTPDevice.objects.filter(user=user,confirmed=True).defer('key')) if user else []
                enrollment[name]['totp_runtime']=totp_runtime_summary(devices,now())
                from authentik.events.models import Event, EventAction
                from authentik.stages.password.stage import PLAN_CONTEXT_METHOD_ARGS
                observed_at=now()
                failures=list(Event.objects.filter(action=EventAction.LOGIN_FAILED,
                    user__username=name,created__gte=observed_at-timedelta(minutes=15))
                    .order_by('-created').only('created','context')[:101])
                enrollment[name]['mfa_failure_events']={
                    **mfa_failure_summary(failures[:100],observed_at,PLAN_CONTEXT_METHOD_ARGS),
                    'scan_truncated':len(failures)>100}

            # Inspect at most 100 recent, unexpired anonymous sessions in the native store.
            # Decode inside Authentik; no session key, password, token or arbitrary context is returned.
            from authentik.core.models import Session
            from authentik.core.sessions import SessionStore
            from authentik.flows.views.executor import SESSION_KEY_PLAN
            groups={name:Group.objects.get(name='family-group-'+name) for name in names}
            registration_sessions={name:[] for name in names}
            decode_errors=0
            rows=list(Session.objects.filter(expires__gt=now(),authenticatedsession__isnull=True)
                .order_by('-last_used').only('session_data')[:101])
            for row in rows[:100]:
                try:
                    decoded=SessionStore().decode(bytes(row.session_data))
                    plan=decoded.get(SESSION_KEY_PLAN)
                    for name in names:
                        summary=invitation_plan_summary(plan,name,groups[name])
                        if summary is not None:registration_sessions[name].append(summary)
                except Exception:decode_errors+=1
            # Include authenticated plans: invitation-only scans cannot explain post-login loops.
            flow_ids={flow.pk.hex:flow.slug for flow in Flow.objects.filter(slug__in=('family-login','family-authorize'))}
            authorization_sessions=[];authorization_decode_errors=0
            auth_rows=list(Session.objects.filter(expires__gt=now(),
                authenticatedsession__user__username__in=names).select_related('authenticatedsession','authenticatedsession__user')
                .order_by('-last_used')[:101])
            for row in auth_rows[:100]:
                try:
                    decoded=SessionStore().decode(bytes(row.session_data))
                    summary=authorization_plan_summary(decoded.get(SESSION_KEY_PLAN),flow_ids,row.authenticatedsession.user.username)
                    if summary is not None:
                        summary['browser_session_current']=bool(row.authenticatedsession.is_current)
                        authorization_sessions.append(summary)
                except Exception:authorization_decode_errors+=1
            authorization_diagnostic={'sessions':authorization_sessions,
                'scan_truncated':len(auth_rows)>100,'decode_errors':authorization_decode_errors,
                'scope':'At most 100 unexpired household authenticated sessions; fixed flow indicators only'}
            invitation_diagnostic={'registration_sessions':registration_sessions,
                'group_generation_valid':{name:isinstance(groups[name].attributes.get('invitation_generation'),str)
                    and len(groups[name].attributes['invitation_generation'])==64 for name in names},
                'scan_truncated':len(rows)>100,'decode_errors':decode_errors,
                'scope':'At most 100 recent unexpired anonymous sessions; fixed enrollment booleans only'}
            return {'status':'passed','authorization_diagnostic':authorization_diagnostic,'invitation_diagnostic':invitation_diagnostic,'enrollment':enrollment,'database_activity':{'blocked_sessions':blocked,'idle_transactions':idle_transaction},'outpost_exists':True,'config_is_dataclass':is_dataclass(config),
                'embedded_public_host_https':config.authentik_host.startswith('https://'),
                'browser_host_https':config.authentik_host_browser.startswith('https://'),
                'family_provider_membership':{name:outpost.providers.filter(name='family-provider-'+name).exists() for name in names},
                'invitation_flows_present':{name:Flow.objects.filter(slug='family-enroll-'+name).exists() for name in names}}
        stage='account_inventory'
        if data['action']=='status':
            records=[]
            stage='password_validation'
            for name in names:
                user=User.objects.filter(username=name).first()
                if user and (user.attributes.get('agent_platform_managed')!='household-v1' or user.is_superuser):
                    raise ValueError('existing_unmanaged_or_admin_account')
                records.append({'username':name,'exists':user is not None})
            return {'status':'passed','users':records}
        if data['action'] in ('invite','invite-revoke'):
            stage='invitation_issue' if data['action']=='invite' else 'invitation_revoke'
            name=data['username']
            assert name in names
            with transaction.atomic():
                group=Group.objects.select_for_update().get(name='family-group-'+name)
                assert not group.is_superuser
                # A fresh generation also invalidates a consumed link still at its password prompt.
                attributes=dict(group.attributes or {})
                generation=secrets.token_hex(32)
                attributes['invitation_generation']=generation
                group.attributes=attributes;group.save()
                invitation_name='family-invite-'+name
                Invitation.objects.including_expired().filter(name=invitation_name).delete()
                if data['action']=='invite-revoke':
                    return {'status':'passed','username':name,'pending_invitation':'revoked','existing_account':'preserved'}
                # Existing or partially enrolled accounts use native login/recovery, never an invite reset.
                assert not User.objects.filter(username=name).exists()
                flow=Flow.objects.get(slug='family-enroll-'+name,designation='enrollment',authentication='require_unauthenticated')
                owner=User.objects.get(username='akadmin',is_active=True)
                assert owner.is_superuser
                expires=now()+timedelta(hours=24)
                invite=Invitation.objects.create(name=invitation_name,flow=flow,created_by=owner,
                    single_use=True,expiring=True,expires=expires,fixed_data={'generation':generation})
                url=invitation_entry_url(data['login_url'],name,invite.pk)
                return {'status':'passed','username':name,'expires':expires.isoformat(),'invitation_url':url}
        assert data['action']=='apply'
        from authentik.blueprints.v1.importer import Importer
        stage='transaction'
        with transaction.atomic():
            # Inventory guards preserve existing managed accounts and refuse adoption of admins.
            for name in names:
                user=User.objects.filter(username=name).first()
                if user:
                    assert user.attributes.get('agent_platform_managed')=='household-v1' and not user.is_superuser
            from authentik.brands.models import Brand
            migrate_brand_origin(Brand,data['login_url'])
            stage='blueprint_validation'
            importer=Importer.from_string(data['blueprint'])
            valid,_=importer.validate(raise_validation_errors=True)
            assert valid is True
            stage='blueprint_import'
            assert importer.apply() is True
            stage='brand_appearance'
            from authentik.brands.models import Brand
            from urllib.parse import urlsplit
            brand=Brand.objects.get(domain=urlsplit(data['login_url']).netloc)
            stage='brand_flow_lookup'
            flows=[Flow.objects.get(slug=slug) for slug in
                   ('family-login','family-authorize','family-logout','family-enroll-alejandro','family-enroll-kimberly')]
            apply_brand_appearance(brand,data['branding_css'],flows)
            stage='application_membership'
            providers=[]
            for name in names:
                user=User.objects.filter(username=name).first();group=Group.objects.get(name='family-group-'+name)
                assert not group.is_superuser
                if user:group.users.add(user)
                # Only this user's group may contain this managed account.
                other=names[1] if name==names[0] else names[0]
                if user:Group.objects.get(name='family-group-'+other).users.remove(user)
                provider=ProxyProvider.objects.get(name='family-provider-'+name)
                assert provider.external_host==data['urls'][name] and provider.mode=='forward_single'
                assert Application.objects.get(slug='family-'+name).provider_id==provider.pk
                providers.append(provider)
            stage='invitation_readback'
            for name in names:
                flow=Flow.objects.get(slug='family-enroll-'+name)
                bindings=list(FlowStageBinding.objects.filter(target=flow).order_by('order'))
                assert [binding.order for binding in bindings]==[10,20,30,40,50]
                assert [binding.stage.name for binding in bindings]==[
                    'family-invitation-'+name,'family-invite-credentials-'+name,
                    'family-invite-write-'+name,'family-totp','family-session']
                assert not InvitationStage.objects.get(name='family-invitation-'+name).continue_flow_without_invitation
                writer=UserWriteStage.objects.get(name='family-invite-write-'+name)
                assert writer.user_creation_mode=='always_create' and writer.create_users_group_id==Group.objects.get(name='family-group-'+name).pk
                prompt=PromptStage.objects.get(name='family-invite-credentials-'+name)
                assert set(prompt.fields.values_list('field_key',flat=True))=={'password','password_repeat'}
                assert list(prompt.validation_policies.values_list('name',flat=True))==['family-invitation-identity-'+name]
            stage='invitation_policy_probe'
            from authentik.policies.expression.models import ExpressionPolicy
            from authentik.policies.types import PolicyRequest
            from authentik.flows.views.executor import SESSION_KEY_PLAN
            from types import SimpleNamespace
            for name in names:
                group=Group.objects.get(name='family-group-'+name)
                original=dict(group.attributes or {})
                generation=secrets.token_hex(32)
                group.attributes={**original,'invitation_generation':generation};group.save()
                policy=ExpressionPolicy.objects.get(name='family-invitation-identity-'+name)
                assert not policy.execution_logging
                flow=Flow.objects.get(slug='family-enroll-'+name)
                expires=now()+timedelta(hours=1)
                invite=Invitation(name='family-invite-'+name,flow=flow,single_use=True,
                    expiring=True,expires=expires,fixed_data={'generation':generation})
                def evaluate(invitation):
                    from django.http import HttpRequest
                    from authentik.flows.views.executor import SESSION_KEY_PLAN
                    request=PolicyRequest(User())
                    http=HttpRequest();http.META['REMOTE_ADDR']='127.0.0.1'
                    http.resolver_match=SimpleNamespace(kwargs={'flow_slug':flow.slug})
                    http.session={SESSION_KEY_PLAN:SimpleNamespace(flow_pk=flow.pk.hex,
                        context={'invitation':invitation,'invitation_in_effect':True,'prompt_data':{},'groups':[]})}
                    request.http_request=http
                    request.context['prompt_data']={'password':'Isolated native policy check sentence 2026!',
                        'password_repeat':'Isolated native policy check sentence 2026!',
                        'username':'injected-name','is_superuser':True}
                    result=policy.passes(request)
                    return result.passing,request
                # No users, devices, sessions or invitation rows are created by this probe.
                passed,request=evaluate(invite)
                if not User.objects.filter(username=name).exists():
                    assert passed and request.context['prompt_data']['username']==name
                    assert 'is_superuser' not in request.context['prompt_data']
                    assert request.context['prompt_data']['attributes']=={'agent_platform_managed':'household-v1'}
                    assert request.http_request.session[SESSION_KEY_PLAN].context['prompt_data']=={}
                    assert request.http_request.session[SESSION_KEY_PLAN].context['redirect']==data['urls'][name]+'/canvas'
                else:assert not passed
                invite.expires=now()-timedelta(seconds=1);assert not evaluate(invite)[0]
                invite.expires=expires;invite.fixed_data={'generation':secrets.token_hex(32)}
                assert not evaluate(invite)[0]
                group.attributes=original;group.save()
            stage='embedded_outpost_lookup'
            outpost=Outpost.objects.get(name='authentik Embedded Outpost')
            configure_embedded_outpost(outpost,providers,data['login_url'])
        return {'status':'passed','users':names,'application_policies':'individual','mfa':'mandatory_totp_enrollment','new_accounts':'invitation_only',
                'existing_admin':'preserved','existing_outpost_providers':'preserved'}

try:
    data=json.load(sys.stdin)
    with open('/dev/null','w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):result=execute(data)
except Exception as error:
    kind=('database_error' if any(base.__name__=='DatabaseError' for base in type(error).__mro__) else
          'type_error' if isinstance(error,TypeError) else
          'attribute_error' if isinstance(error,AttributeError) else
          'assertion_failed' if isinstance(error,AssertionError) else
          'lookup_error' if isinstance(error,LookupError) or type(error).__name__ in {'DoesNotExist','MultipleObjectsReturned'} else 'other')
    result={'status':'failed','stage':stage,'exception_category':kind,'error':'household_identity_native_failed_details_withheld'}
print(json.dumps(result))  # Parent checks status; retain the sanitized stage on failure.
