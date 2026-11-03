"""Standard ZIP/ZIP64 with OpenCL GPU fixed-Huffman DEFLATE encoding."""
import argparse
import sys
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8",errors="replace")
import os
from pathlib import Path
import struct
import tempfile
import time
import zlib
import numpy as np
import pyopencl as cl

BLOCK=32768
BATCH=256

class Deflater:
    def __init__(self,device=''):
        candidates=[d for p in cl.get_platforms() for d in p.get_devices(device_type=cl.device_type.GPU)
                    if device.lower() in d.name.lower() and d.available and d.compiler_available]
        if not candidates:raise ValueError('Selected OpenCL GPU is not available')
        self.device=max(candidates,key=lambda d:(not d.host_unified_memory,d.global_mem_size))
        self.context=cl.Context([self.device]);self.queue=cl.CommandQueue(self.context)
        program=cl.Program(self.context,Path(__file__).with_name('deflate.cl').read_text(encoding='utf-8-sig')).build()
        self.kernel=cl.Kernel(program,'deflate_blocks')
        self.dispatches=0
    def encode(self,chunk):
        n=(len(chunk)+BLOCK-1)//BLOCK
        if not n:return b''
        data=np.zeros(n*BLOCK,dtype=np.uint8);data[:len(chunk)]=np.frombuffer(chunk,dtype=np.uint8)
        lengths=np.array([min(BLOCK,len(chunk)-i*BLOCK) for i in range(n)],dtype=np.uint32)
        output=np.empty((n,BLOCK*2),dtype=np.uint8);sizes=np.empty(n,dtype=np.uint32)
        f=cl.mem_flags
        src=cl.Buffer(self.context,f.READ_ONLY|f.COPY_HOST_PTR,hostbuf=data)
        lens=cl.Buffer(self.context,f.READ_ONLY|f.COPY_HOST_PTR,hostbuf=lengths)
        dst=cl.Buffer(self.context,f.WRITE_ONLY,output.nbytes)
        sizebuf=cl.Buffer(self.context,f.WRITE_ONLY,sizes.nbytes)
        tables=cl.Buffer(self.context,f.READ_WRITE,n*4096*4)
        self.kernel(self.queue,(n,),None,src,dst,lens,sizebuf,tables,np.uint32(BLOCK))
        cl.enqueue_copy(self.queue,sizes,sizebuf)
        cl.enqueue_copy(self.queue,output,dst).wait();self.dispatches+=1
        return b''.join(output[i,:int(sizes[i])].tobytes() for i in range(n))


def entries(source):
    def checked(path):
        info=path.lstat()
        if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError(f'Links and junctions are not supported: {path}')
        return path
    yield checked(source)
    if source.is_dir():
        def failed(exc):raise exc
        for root,dirs,files in os.walk(source,followlinks=False,onerror=failed):
            for name in sorted(dirs)+sorted(files):yield checked(Path(root)/name)


def create(source,target,device=''):
    source=Path(source).absolute();target=Path(target).absolute()
    if not source.exists():raise FileNotFoundError(source)
    if target.exists():raise FileExistsError('Choose a new archive name')
    if source.is_dir() and target.resolve().is_relative_to(source.resolve()):
        raise ValueError('Save the archive outside the source folder')
    engine=Deflater(device)
    print('Standard ZIP / GPU DEFLATE:',engine.device.name,flush=True)
    print('GPU: match search and Huffman encoding. CPU: file I/O, CRC and ZIP headers.',flush=True)
    records=[];total=0;count=0;start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='.gpu-zip-',dir=target.parent) as temp:
        staged=Path(temp)/'archive.zip'
        with staged.open('w+b') as out:
            for path in entries(source):
                directory=path.is_dir()
                name=(path.relative_to(source.parent).as_posix()+('/' if directory else '')).encode('utf8')
                if len(name)>65535:raise ValueError('Archive path is too long')
                stamp=time.localtime(path.stat().st_mtime)
                year=max(1980,min(2107,stamp.tm_year))
                date=((year-1980)<<9)|(stamp.tm_mon<<5)|stamp.tm_mday
                clock=(stamp.tm_hour<<11)|(stamp.tm_min<<5)|(stamp.tm_sec//2)
                offset=out.tell();method=0 if directory else 8;flags=0x800
                extra=struct.pack('<HHQQ',1,16,0,0)
                out.write(struct.pack('<IHHHHHIIIHH',0x04034b50,45,flags,method,clock,date,0,0xffffffff,0xffffffff,len(name),len(extra)))
                out.write(name);out.write(extra)
                payload_start=out.tell();crc=0;size=0
                if not directory:
                    with path.open('rb') as src:
                        while chunk:=src.read(BLOCK*BATCH):
                            size+=len(chunk);crc=zlib.crc32(chunk,crc)
                            out.write(engine.encode(chunk))
                    # Final byte-aligned empty stored block terminates this raw DEFLATE stream.
                    out.write(b'\x01\x00\x00\xff\xff');count+=1
                compressed=out.tell()-payload_start;end=out.tell()
                out.seek(offset+14);out.write(struct.pack('<I',crc))
                out.seek(offset+30+len(name)+4);out.write(struct.pack('<QQ',size,compressed));out.seek(end)
                records.append((name,method,clock,date,crc,size,compressed,offset,directory))
                total+=size
                print(f'Packed: {path.name} ({size:,} bytes)',flush=True)
            central_offset=out.tell()
            for name,method,clock,date,crc,size,compressed,offset,directory in records:
                extra=struct.pack('<HHQQQ',1,24,size,compressed,offset)
                attr=((0o40755 if directory else 0o100644)<<16)|(16 if directory else 0)
                out.write(struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,0x032d,45,0x800,method,clock,date,crc,0xffffffff,0xffffffff,len(name),len(extra),0,0,0,attr,0xffffffff))
                out.write(name);out.write(extra)
            central_size=out.tell()-central_offset;end64=out.tell();n=len(records)
            out.write(struct.pack('<IQHHIIQQQQ',0x06064b50,44,45,45,0,0,n,n,central_size,central_offset))
            out.write(struct.pack('<IIQI',0x07064b50,0,end64,1))
            out.write(struct.pack('<IHHHHIIH',0x06054b50,0,0,0xffff,0xffff,0xffffffff,0xffffffff,0))
        staged.rename(target)
    size=target.stat().st_size
    print(f'{count:,} files; {total:,} source bytes -> {size:,} ZIP bytes',flush=True)
    if size>=total:print(f'NO SPACE SAVED: ZIP is {size-total:,} bytes larger.',flush=True)
    else:print(f'Space saved: {(total-size)/total:.2%}',flush=True)
    print(f'OpenCL kernel batches: {engine.dispatches}; elapsed after GPU setup: {time.perf_counter()-start:.3f}s',flush=True)
    return engine.dispatches

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['compress','decompress']);p.add_argument('source',type=Path);p.add_argument('target',type=Path);p.add_argument('--device',default='')
    args=p.parse_args()
    if args.action=='compress':create(args.source,args.target,args.device)
    else:
        from folder_archive import restore
        print('Standard ZIP extraction uses CPU decoding.',flush=True)
        restore(args.source,args.target)
