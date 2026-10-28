"""Inside-container filesystem probe. Only synthetic markers; no LLM or conversation contents."""
import json,os,sys
from pathlib import Path
uid, marker, foreign = sys.argv[1:]
assert marker.startswith('.instance-canary-') and '/' not in marker
home=Path('/home/openhands');workspace=Path('/projects')
checks={'uid_matches':os.getuid()==int(uid)}
checks['own_state_visible']=(home/marker).read_text()=='synthetic instance canary'
checks['own_workspace_visible']=(workspace/marker).read_text()=='synthetic instance canary'
try:
    with open(foreign,'rb') as stream:stream.read(1)
    checks['foreign_host_path_denied']=False
except (FileNotFoundError,PermissionError,NotADirectoryError):
    checks['foreign_host_path_denied']=True
print(json.dumps(checks))
