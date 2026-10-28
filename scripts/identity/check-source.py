#!/usr/bin/env python3
"""Check a candidate Authentik graph without evaluating tags or contacting an IdP.

This is a narrow source guard, not Authentik model validation or login acceptance.
Only !KeyOf references are allowed. No environment, file, expression or lookup
instructions are executed. Errors deliberately omit document values.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import yaml

ROOT=Path(__file__).resolve().parents[2]
BLUEPRINT=ROOT/'infra/identity/household-blueprint.yaml'

class InvalidSource(ValueError):
    """Fixed public error category."""

@dataclass(frozen=True)
class Ref:
    target: str

class Loader(yaml.SafeLoader):
    def construct_mapping(self,node,deep=False):
        result={}
        for key,value in node.value:
            field=self.construct_object(key,deep=deep)
            if not isinstance(field,str) or field in result:raise InvalidSource('duplicate_or_invalid_yaml_key')
            result[field]=self.construct_object(value,deep=deep)
        return result

Loader.add_constructor('!KeyOf',lambda loader,node:Ref(loader.construct_scalar(node)))

def parse(raw):
    if len(raw)>32768:raise InvalidSource('blueprint_oversized')
    try:
        if any(isinstance(token,(yaml.tokens.AliasToken,yaml.tokens.AnchorToken)) for token in yaml.scan(raw)):
            raise InvalidSource('yaml_aliases_not_allowed')
        return yaml.load(raw,Loader=Loader)
    except yaml.YAMLError:raise InvalidSource('invalid_blueprint_yaml') from None


def require(condition):
    if not condition:raise InvalidSource('identity_source_contract_violated')


def same(actual,expected):
    """Avoid accepting YAML true as integer 1 or a string as a tagged reference."""
    if type(actual) is not type(expected):return False
    if isinstance(expected,dict):return actual.keys()==expected.keys() and all(same(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list):return len(actual)==len(expected) and all(same(a,b) for a,b in zip(actual,expected))
    return actual==expected


def validate(document):
    require(isinstance(document,dict) and set(document)=={'version','metadata','entries'})
    require(same(document['version'],1))
    require(same(document['metadata'],{'name':'Household isolated pilot access','labels':{'blueprints.goauthentik.io/instantiate':'false'}}))
    require(isinstance(document['entries'],list))
    rows={}
    for row in document['entries']:
        require(isinstance(row,dict) and set(row)=={'id','model','identifiers','attrs'})
        require(isinstance(row['id'],str) and row['id'] not in rows)
        require(isinstance(row['attrs'],dict) and isinstance(row['identifiers'],dict))
        rows[row['id']]=row
    consumed=set()
    def entry(id,model,identifiers,attrs):
        require(id in rows)
        row=rows[id];consumed.add(id)
        require(row['model']==model and same(row['identifiers'],identifiers) and same(row['attrs'],attrs))
    def named(id,model,attrs):entry(id,model,{'name':'household-'+id},attrs)
    # Authentication always performs password -> MFA -> session. No bypass bindings.
    for id,designation,auth in [('login','authentication','none'),('authorize','authorization','require_authenticated'),('logout','invalidation','none')]:
        entry(id,'authentik_flows.flow',{'slug':'household-'+id},{'name':'Household '+id,'title':'Local Agent Platform','designation':designation,'authentication':auth,'denied_action':'message'})
    named('identify','authentik_stages_identification.identificationstage',{'user_fields':['username'],'sources':[],'show_source_labels':False,'enrollment_flow':None,'recovery_flow':None,'passwordless_flow':None})
    named('password','authentik_stages_password.passwordstage',{'backends':['authentik.core.auth.InbuiltBackend'],'configure_flow':None})
    named('totp','authentik_stages_authenticator_totp.authenticatortotpstage',{'digits':6})
    named('webauthn','authentik_stages_authenticator_webauthn.authenticatorwebauthnstage',{'user_verification':'required','resident_key_requirement':'preferred'})
    for id,action in [('mfa-login','configure'),('mfa-access','deny')]:
        named(id,'authentik_stages_authenticator_validate.authenticatorvalidatestage',{
            'device_classes':['webauthn','totp'],'not_configured_action':action,
            'configuration_stages':[Ref('webauthn'),Ref('totp')] if action=='configure' else [],
            'last_auth_threshold':'seconds=0','webauthn_user_verification':'required'})
    named('session','authentik_stages_user_login.userloginstage',{'session_duration':'hours=1','remember_me_offset':'seconds=0'})
    named('end-session','authentik_stages_user_logout.userlogoutstage',{})
    for flow,stages in [('login',['identify','password','mfa-login','session']),('authorize',['mfa-access']),('logout',['end-session'])]:
        for index,stage in enumerate(stages,1):
            entry(flow+'-'+stage,'authentik_flows.flowstagebinding',{'target':Ref(flow),'stage':Ref(stage),'order':index*10},{'evaluate_on_plan':False,'re_evaluate_policies':True})
    for tenant in ('probe-a','probe-b'):
        named('group-'+tenant,'authentik_core.group',{'is_superuser':False})
        # Single-app auth is essential: domain-level auth cannot encode this binding.
        named('provider-'+tenant,'authentik_providers_proxy.proxyprovider',{
            'mode':'forward_single','external_host':'https://'+tenant+'.home.arpa',
            'authentication_flow':Ref('login'),'authorization_flow':Ref('authorize'),
            'invalidation_flow':Ref('logout'),'skip_path_regex':'',
            'intercept_header_auth':False,'basic_auth_enabled':False,'cookie_domain':'',
            'access_token_validity':'minutes=5','refresh_token_validity':'hours=1'})
        entry('app-'+tenant,'authentik_core.application',{'slug':'household-'+tenant},{
            'name':'OpenHands '+tenant,'provider':Ref('provider-'+tenant),
            'policy_engine_mode':'all','meta_launch_url':'https://'+tenant+'.home.arpa'})
        entry('allow-'+tenant,'authentik_policies.policybinding',{
            'target':Ref('app-'+tenant),'group':Ref('group-'+tenant),'order':10},
            {'enabled':True,'negate':False,'failure_result':False})
    entry('brand','authentik_brands.brand',{'domain':'login.home.arpa'},{
        'default':True,'branding_title':'Local Agent Platform','flow_authentication':Ref('login'),
        'flow_invalidation':Ref('logout'),'flow_recovery':None,'flow_unenrollment':None,
        'flow_user_switch':None,'flow_device_code':None})
    entry('outpost','authentik_outposts.outpost',{'name':'authentik Embedded Outpost'},{
        'type':'proxy','service_connection':None,
        'providers':[Ref('provider-probe-a'),Ref('provider-probe-b')],
        'config':{'authentik_host':'https://login.home.arpa','authentik_host_browser':'https://login.home.arpa'}})
    # No unknown models, extra allow rules, enrollment flows, users or credentials.
    require(set(rows)==consumed)
    return {'status':'prepared','source_contract':'passed','applications':2,
            'native_authentik_validation':'pending','browser_mfa_acceptance':'pending',
            'gateway_authorization_acceptance':'pending','household_readiness':'pending'}


def main():
    try:
        raw=BLUEPRINT.read_bytes();report=validate(parse(raw))
        report['blueprint_sha256']=hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError,TypeError,KeyError):
        print(json.dumps({'status':'failed','error':'identity_source_invalid','household_readiness':'pending'}));return 1
    print(json.dumps(report,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
