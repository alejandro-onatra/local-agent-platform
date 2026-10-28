"""Read bounded recent identity logs; return fixed indicators, never log contents."""
import json,subprocess
PROJECT='agent-platform-identity-local'
INDICATORS={
    'policy_exception':(b'policy_exception',b'policyexception',b'policy failed to execute'),
    'validation_rejected':(b'validationerror',b'validation error',b'passwords don',b'password validation'),
    'csrf_or_origin_rejected':(b'csrf',b'origin checking failed'),
    'flow_error':(b'flowerror',b'flow execution',b'invalid invite',b'invitation not found'),
    'database_error':(b'databaseerror',b'operationalerror',b'deadlock',b'could not connect'),
    'permission_denied':(b'permission denied',b'permissionerror'),
    'traceback':(b'traceback (most recent call last)',),
    'tls_certificate_error':(b'x509:',b'certificate verify failed',b'certificate signed by unknown authority'),
    'oauth_exchange_error':(b'failed to exchange token',b'failed to redeem code',b'oauth2:',b'invalid_grant'),
    'callback_session_error':(b'failed to save session',b'invalid state'),
    'totp_rejected':(b'invalid totp',b'invalid otp',b'totp validation failed'),
}

def structured_failures(raw):
    """Summarize only fixed routes/statuses; never return request or error text."""
    from collections import Counter
    from urllib.parse import urlsplit
    allowed={400,401,403,404,405,409,422,429,500,502,503,504}
    routes={
        '/api/v3/flows/executor/family-login/':'login_flow',
        '/api/v3/flows/executor/family-authorize/':'authorization_flow',
        '/api/v3/flows/executor/family-enroll-alejandro/':'enrollment_flow',
        '/api/v3/flows/executor/family-enroll-kimberly/':'enrollment_flow',
        '/application/o/authorize/':'oauth_authorize',
        '/application/o/token/':'oauth_token',
        '/outpost.goauthentik.io/callback':'proxy_callback',
    }
    counts=Counter();errors=False
    for line in raw.splitlines():
        try:item=json.loads(line)
        except (ValueError,UnicodeError):continue
        if not isinstance(item,dict):continue
        level=item.get('level')
        if isinstance(level,str) and level.lower() in ('error','critical','fatal'):errors=True
        status=next((item.get(key) for key in ('status','status_code','http_status') if key in item),None)
        if isinstance(status,str) and status.isascii() and status.isdigit():status=int(status)
        if type(status) is not int or status not in allowed:continue
        route='other'
        for key in ('path','request_path','event'):
            value=item.get(key)
            if not isinstance(value,str):continue
            parts=value.split(' ')
            if len(parts)>1 and parts[0] in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'):value=parts[1]
            try:path=urlsplit(value).path
            except ValueError:continue
            if path in routes:route=routes[path];break
        counts[(route,status)]+=1
    return {'http_failures':[{'route':route,'status':status,'count':count}
            for (route,status),count in sorted(counts.items())],
            'structured_error_seen':errors}


def command(args):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)

def collect(run=command):
    result={}
    for service in ('server','worker'):
        name=PROJECT+'-'+service+'-1'
        try:
            inspected=run(['docker','--context','default','inspect','--format','{{json .Config.Labels}}',name])
            labels=json.loads(inspected.stdout)
            if inspected.returncode or labels.get('com.docker.compose.project')!=PROJECT or labels.get('com.docker.compose.service')!=service:
                result[service]={'status':'identity_check_failed'};continue
            logs=run(['docker','--context','default','logs','--since','15m','--tail','200',name])
            if logs.returncode:result[service]={'status':'logs_unavailable'};continue
            raw=logs.stdout[:1048576].lower()
            result[service]={'status':'collected','indicators':{key:any(marker in raw for marker in markers) for key,markers in INDICATORS.items()},'truncated':len(logs.stdout)>1048576,**structured_failures(logs.stdout[:1048576])}
        except Exception:result[service]={'status':'probe_unavailable'}
    return {'status':'collected','services':result,'scope':'Last 15 minutes / at most 200 Docker log lines per identity service; fixed indicators and structured HTTP failure counts only; absence is not proof of success or a confirmed root cause'}
