"""Machine-readable setup checks; no packages are installed by this helper."""
import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys

p=argparse.ArgumentParser();p.add_argument('mode',choices=['python','dependencies']);args=p.parse_args()
if args.mode=='python':
    valid=(3,12)<=sys.version_info[:2]<=(3,14) and not (Path(sys.base_prefix)/'conda-meta').exists()
    error=''
    try:
        import tkinter
        import venv
        import ensurepip
    except ImportError as exc:valid=False;error=str(exc)
    print(json.dumps(dict(valid=valid,version=sys.version.split()[0],base=sys.base_prefix,executable=sys.executable,error=error)))
else:
    missing=[];installed=[]
    for line in Path(__file__).with_name('requirements.txt').read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        name,version=line.split('==')
        try:
            actual=importlib.metadata.version(name)
            importlib.import_module(name)
            if actual!=version:raise ValueError(f'version {actual}')
            installed.append(f'{name} {actual}')
        except Exception:missing.append(line)
    print(json.dumps(dict(missing=missing,installed=installed)))
