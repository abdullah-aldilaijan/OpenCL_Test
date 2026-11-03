"""Discover installed CPU models and usable OpenCL GPUs before processing."""
import json
import os
import platform
import subprocess


def discover():
    cpus=[]; gpus=[]; notices=[]
    if os.name=='nt':
        try:
            result=subprocess.run(['powershell.exe','-NoProfile','-Command',
                'ConvertTo-Json -InputObject @(Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name)'],
                capture_output=True,text=True,timeout=15,check=True,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            names=json.loads(result.stdout)
            if isinstance(names,str):names=[names]
            cpus=list(dict.fromkeys(n.strip() for n in names if n.strip()))
        except Exception as exc:notices.append('CPU model lookup unavailable; using system CPU information.')
    if not cpus:cpus=[platform.processor() or platform.machine() or 'System processor']
    try:
        import pyopencl as cl
        for p in cl.get_platforms():
            try:
                for d in p.get_devices(device_type=cl.device_type.GPU):
                    if d.available and d.compiler_available:gpus.append(d)
            except cl.Error:notices.append(f'Could not query OpenCL devices on {p.name}.')
        gpus.sort(key=lambda d:(bool(d.host_unified_memory),-d.global_mem_size))
    except Exception:notices.append('No usable OpenCL GPU runtime found. CPU mode remains available.')
    options={}
    for name in cpus:options['CPU — '+name]='CPU'
    for d in gpus:
        label='GPU — '+d.name
        if label in options:label+=' ('+d.platform.name+')'
        options[label]=d.name
    if not gpus and not notices:notices.append('No OpenCL GPU with compiler support was found. CPU mode remains available.')
    return options,notices

if __name__=='__main__':
    options,notices=discover()
    print(json.dumps({'devices':list(options),'notices':notices},indent=2,ensure_ascii=False))
