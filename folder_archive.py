"""Folder/file ZIP creation and safe restoration using CPU DEFLATE."""
import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import time
import zipfile


def archive(source, target, stored=False):
    source=Path(source).resolve(strict=True); target=Path(target).absolute()
    if target.exists(): raise FileExistsError('Output already exists')
    if source.is_dir() and target.resolve().is_relative_to(source):
        raise ValueError('Save the archive outside the folder being compressed')
    if source.is_symlink(): raise ValueError('Symbolic links are not supported')
    total=0; count=0
    with tempfile.TemporaryDirectory(prefix='.zip-build-',dir=target.parent) as tmp:
        staged=Path(tmp)/'archive.zip'
        with zipfile.ZipFile(staged,'w',compression=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,compresslevel=None if stored else 6,allowZip64=True) as z:
            def add(path):
                nonlocal total,count
                info=path.lstat()
                if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
                    raise ValueError(f'Links/junctions are not supported: {path}')
                z.write(path,path.relative_to(source.parent).as_posix())
                if path.is_file(): total+=info.st_size;count+=1
            add(source)
            if source.is_dir():
                for base,dirs,files in os.walk(source,followlinks=False,onerror=lambda e: (_ for _ in ()).throw(e)):
                    for name in sorted(dirs)+sorted(files): add(Path(base)/name)
        # Windows rename refuses to replace an existing destination.
        staged.rename(target)
    stored_mode=stored
    stored=target.stat().st_size
    print(f'{"Folder packaging only (no CPU compression)" if stored_mode else "ZIP / DEFLATE (CPU)"}: {count:,} files; folder structure preserved',flush=True)
    print(f'{total:,} file bytes -> {stored:,} archive bytes',flush=True)
    if stored>=total: print(f'Archive overhead: {stored-total:,} bytes.' if stored_mode else f'NO SPACE SAVED: archive is {stored-total:,} bytes larger.',flush=True)
    else: print(f'Space saved: {(total-stored)/total:.2%}',flush=True)


def restore(source,target):
    source=Path(source); target=Path(target).absolute()
    if target.exists(): raise FileExistsError('Choose a new destination folder')
    with zipfile.ZipFile(source) as z, tempfile.TemporaryDirectory(prefix='.zip-restore-',dir=target.parent) as tmp:
        root=Path(tmp)/'restored';root.mkdir()
        names=set()
        for info in z.infolist():
            name=info.filename
            parts=PurePosixPath(name).parts
            if not parts or name.startswith('/') or '\\' in name or any(p in ('.','..') or ':' in p or p.rstrip(' .')!=p for p in parts):
                raise ValueError('Unsafe archive path')
            if any(p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts):
                raise ValueError('Unsupported Windows filename')
            key='/'.join(parts).casefold()
            if key in names: raise ValueError('Duplicate archive path')
            names.add(key)
            if stat.S_ISLNK(info.external_attr>>16): raise ValueError('Archive links are not supported')
            out=root.joinpath(*parts)
            if not out.resolve().is_relative_to(root.resolve()): raise ValueError('Unsafe archive path')
            if info.is_dir():out.mkdir(parents=True,exist_ok=True)
            else:
                out.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as src,out.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
        root.rename(target)
    print(f'Restored to: {target}\nZIP CRC integrity checks: PASS',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['compress','decompress']);p.add_argument('source',type=Path);p.add_argument('target',type=Path)
    args=p.parse_args();start=time.perf_counter()
    (archive if args.action=='compress' else restore)(args.source,args.target)
    print(f'Elapsed: {time.perf_counter()-start:.3f}s',flush=True)
