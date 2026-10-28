"""Validate CI native-test tools without requiring desktop/offline-ceremony facilities."""
import importlib.util,json,platform
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]

class CIEnvironmentError(ValueError):pass

def verify(native,target,observed):
    if observed.get('ID')!=target['id'] or observed.get('VERSION_ID')!=target['version_id']:
        raise CIEnvironmentError('ci_runner_os_mismatch')
    native.profile()
    native.tool()
    native.openssl_tool()
    return {'status':'passed','step_version':native.EXPECTED['step_version'],
        'openssl_version':native.EXPECTED['openssl_version'],
        'scope':'CI native crypto tools only; no host ceremony, USB, keys, trust or Docker acceptance'}

def main():
    spec=importlib.util.spec_from_file_location('ci_pki',ROOT/'scripts/pki/pki.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    try:
        target=yaml.safe_load((ROOT/'infra/host/versions.yaml').read_text())['target']
        result=verify(native,target,platform.freedesktop_os_release())
    except Exception as error:
        reason=str(error) if isinstance(error,(CIEnvironmentError,native.PKIError)) else 'ci_native_tooling_unavailable'
        result={'status':'failed','error':reason}
    print(json.dumps(result,indent=2));return int(result['status']!='passed')

if __name__=='__main__':raise SystemExit(main())
