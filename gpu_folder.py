"""Uncompressed folder packaging plus OpenCL GPU LZ compression."""
import argparse
from pathlib import Path
import tempfile
import time
from folder_archive import archive, restore
from opencl_lz import Engine, compress, decompress


def process(action,source,target,device=''):
    source=Path(source).resolve(strict=True);target=Path(target).absolute()
    if target.exists():raise FileExistsError('Choose a new output name')
    if action=='compress' and target.resolve().is_relative_to(source):
        raise ValueError('Save the archive outside the source folder')
    if action=='decompress':
        with source.open('rb') as f: magic=f.read(8)
        if magic==b'OCLRLE01':
            import opencl_compress as old
            engine=old.Engine(device); decoder=old.decompress
        else: engine=Engine(device); decoder=decompress
    else: engine=Engine(device)
    print('Folder archive processing device:',engine.device.name,flush=True)
    print('CPU handles packaging and file I/O. Archive decoding uses the selected device.',flush=True)
    with tempfile.TemporaryDirectory(prefix='.gpu-folder-',dir=target.parent) as tmp:
        bundle=Path(tmp)/'folder.zip'
        if action=='compress':
            if not source.is_dir():raise ValueError('Select a folder')
            archive(source,bundle,stored=True)
            staged=Path(tmp)/'folder.oclr'
            compress(engine,bundle,staged)
            # Read and validate the packaged entries to calculate actual source byte size.
            import zipfile
            with zipfile.ZipFile(bundle) as z:original=sum(i.file_size for i in z.infolist())
            size=staged.stat().st_size
            staged.rename(target)
            print(f'{original:,} source file bytes -> {size:,} archive bytes',flush=True)
            if size>=original:print(f'NO SPACE SAVED: archive is {size-original:,} bytes larger.',flush=True)
            else:print(f'Space saved: {(original-size)/original:.2%}',flush=True)
        else:
            decoder(engine,source,bundle)
            print('Decompression SHA-256 check: PASS',flush=True)
            restore(bundle,target)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['compress','decompress']);p.add_argument('source',type=Path);p.add_argument('target',type=Path);p.add_argument('--device',default='')
    args=p.parse_args();start=time.perf_counter()
    process(args.action,args.source,args.target,args.device)
    print(f'Total elapsed including packaging, setup, GPU work and I/O: {time.perf_counter()-start:.3f}s')
