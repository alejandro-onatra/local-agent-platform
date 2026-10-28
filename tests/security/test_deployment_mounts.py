"""Reject substituted or writable launcher mounts before deployment."""
import contextlib
import copy
import io
import json
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[2]


class DeploymentMountTests(unittest.TestCase):
    def setUp(self):
        lock=yaml.safe_load((ROOT/'infra/openhands/versions.yaml').read_text())
        llm=yaml.safe_load((ROOT/'infra/llm/versions.yaml').read_text())
        self.config={'networks':{'agent-link':{'internal':True}},'services':{
            'openhands':{'image':lock['image'],'platform':'linux/amd64','networks':['agent-link'],
                'read_only':True,'environment':{'OH_TELEMETRY_EXPORTER':'none','OH_WORKSPACE_PATH':'/projects/demo'},
                'volumes':[{'type':'bind','target':'/projects','source':str(ROOT/'artifacts/openhands/projects')},
                           {'type':'volume','target':'/home/openhands/.openhands','source':'openhands-state'}]},
            'openhands-proxy':{'image':lock['proxy']['image'],'user':'101:101','read_only':True,
                'networks':['default','agent-link'],'ports':[{'host_ip':'127.0.0.1','target':8080,'published':'8000'}],
                'volumes':[{'source':str(ROOT/'infra/openhands/nginx.conf'),'read_only':True}]},
            'ollama':{'image':llm['ollama']['image'],'networks':['default','agent-link']}}}
        self.launcher={'type':'bind','target':'/usr/local/bin/openhands-agent-server',
                       'source':str(ROOT/'scripts/openhands/start-agent-server.py'),'read_only':True}

    def validate(self):
        with patch.object(sys,'stdin',io.StringIO(json.dumps(self.config))),contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT/'scripts/openhands/validate-config.py'),run_name='__main__')

    def test_original_and_exact_readonly_launcher_are_accepted(self):
        self.validate()
        self.config['services']['openhands']['volumes'].append(self.launcher)
        self.validate()

    def test_substituted_writable_or_duplicate_launcher_is_rejected(self):
        original=copy.deepcopy(self.config)
        for mutation in [{'read_only':False},{'source':'/home/other/launcher.py'},{'type':'volume'}]:
            with self.subTest(mutation=mutation):
                self.config=copy.deepcopy(original)
                self.config['services']['openhands']['volumes'].append({**self.launcher,**mutation})
                with self.assertRaises(AssertionError):self.validate()
        self.config=copy.deepcopy(original)
        self.config['services']['openhands']['volumes'] += [self.launcher,self.launcher]
        with self.assertRaises(AssertionError):self.validate()


if __name__=='__main__':unittest.main()
