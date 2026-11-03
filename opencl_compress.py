"""Educational block-parallel OpenCL RLE compressor. Not ZIP-compatible."""
import argparse, hashlib, os, struct, time
from pathlib import Path
import numpy as np
import pyopencl as cl

MAGIC = b'OCLRLE01'
BLOCK = 4096
BATCH = 1024
KERNELS = r'''
__kernel void encode(__global const uchar *src, __global uchar *dst,
                     __global const uint *lengths, __global uint *sizes, uint block) {
    uint id=get_global_id(0), n=lengths[id], i=0, p=0;
    size_t s=(size_t)id*block, d=(size_t)id*block*2;
    while(i<n) {
        uchar v=src[s+i]; uint count=1;
        while(i+count<n && count<255 && src[s+i+count]==v) count++;
        dst[d+p++]=(uchar)count; dst[d+p++]=v; i+=count;
    }
    sizes[id]=p;
}
__kernel void decode(__global const uchar *src, __global uchar *dst,
                     __global const uint *sizes, __global const uint *lengths, uint block) {
    uint id=get_global_id(0), size=sizes[id], n=lengths[id];
    size_t s=(size_t)id*block*2, d=(size_t)id*block;
    if(size==n) { for(uint i=0;i<n;i++) dst[d+i]=src[s+i]; }
    else { uint p=0; for(uint i=0;i<size;i+=2) {
        uint count=src[s+i]; uchar v=src[s+i+1];
        for(uint j=0;j<count;j++) dst[d+p++]=v;
    }}
}
'''

def devices():
    return [d for p in cl.get_platforms() for d in p.get_devices()]

class Engine:
    def __init__(self, name=''):
        self.cpu=name=='CPU'
        if self.cpu:
            from types import SimpleNamespace
            self.device=SimpleNamespace(name='CPU')
            return
        candidates=[d for d in devices() if name.lower() in d.name.lower()]
        if not candidates: raise ValueError('No matching OpenCL device')
        self.device=max(candidates, key=lambda d: (bool(d.type & cl.device_type.GPU), not d.host_unified_memory, d.global_mem_size))
        self.ctx=cl.Context([self.device]); self.q=cl.CommandQueue(self.ctx)
        program=cl.Program(self.ctx,KERNELS).build()
        self.enc=cl.Kernel(program,'encode'); self.dec=cl.Kernel(program,'decode')
        self.kernel_seconds=0
    def run(self, data, lengths, sizes=None):
        if self.cpu:
            if sizes is None: raise ValueError('CPU compression uses ZIP mode')
            out=np.zeros((len(lengths),BLOCK),dtype=np.uint8)
            for i in range(len(lengths)):
                size=int(sizes[i]); length=int(lengths[i])
                if size==length: out[i,:length]=data[i,:length]
                else: out[i,:length]=np.repeat(data[i,1:size:2], data[i,:size:2].astype(np.int64))
            return out,None
        n=len(lengths); flags=cl.mem_flags
        def upload(a): return cl.Buffer(self.ctx,flags.READ_ONLY|flags.COPY_HOST_PTR,hostbuf=a)
        source=upload(data); lens=upload(lengths)
        out=np.empty((n, BLOCK if sizes is not None else BLOCK*2),dtype=np.uint8)
        dest=cl.Buffer(self.ctx,flags.WRITE_ONLY,out.nbytes)
        start=time.perf_counter()
        if sizes is None:
            result=np.empty(n,dtype=np.uint32)
            result_buf=cl.Buffer(self.ctx,flags.WRITE_ONLY,result.nbytes)
            self.enc(self.q,(n,),None,source,dest,lens,result_buf,np.uint32(BLOCK))
            cl.enqueue_copy(self.q,result,result_buf)
        else:
            self.dec(self.q,(n,),None,source,dest,upload(sizes),lens,np.uint32(BLOCK))
            result=None
        cl.enqueue_copy(self.q,out,dest).wait()
        self.kernel_seconds+=time.perf_counter()-start
        return out,result

def exact(f,n):
    data=f.read(n)
    if len(data)!=n: raise ValueError('Truncated archive')
    return data

def compress(engine,source,target):
    digest=hashlib.sha256(); total=source.stat().st_size; seen=0
    with source.open('rb') as src, target.open('xb') as dst:
        dst.write(MAGIC+struct.pack('<IQ',BLOCK,total))
        while chunk:=src.read(BLOCK*BATCH):
            digest.update(chunk); seen+=len(chunk)
            n=(len(chunk)+BLOCK-1)//BLOCK
            data=np.zeros((n,BLOCK),dtype=np.uint8)
            data.ravel()[:len(chunk)]=np.frombuffer(chunk,dtype=np.uint8)
            lengths=np.array([min(BLOCK,len(chunk)-i*BLOCK) for i in range(n)],dtype=np.uint32)
            encoded,sizes=engine.run(data,lengths)
            dst.write(struct.pack('<I',n))
            for i in range(n):
                length=int(lengths[i]); size=int(sizes[i])
                payload=encoded[i,:size].tobytes() if size<length else data[i,:length].tobytes()
                dst.write(struct.pack('<II',length,len(payload))); dst.write(payload)
        if seen!=total: raise ValueError('Source changed size during compression')
        dst.write(struct.pack('<I',0)+digest.digest())

def decompress(engine,source,target):
    with source.open('rb') as src, target.open('xb') as dst:
        if exact(src,8)!=MAGIC: raise ValueError('Not an OCLRLE01 archive')
        block,total=struct.unpack('<IQ',exact(src,12))
        if block!=BLOCK: raise ValueError('Unsupported block size')
        digest=hashlib.sha256(); seen=0
        while True:
            n,=struct.unpack('<I',exact(src,4))
            if n==0: break
            if not 1<=n<=BATCH: raise ValueError('Invalid batch count')
            data=np.zeros((n,BLOCK*2),dtype=np.uint8)
            lengths=np.empty(n,dtype=np.uint32); sizes=np.empty(n,dtype=np.uint32)
            for i in range(n):
                length,size=struct.unpack('<II',exact(src,8))
                if not 1<=size<=length<=BLOCK or seen+length>total:
                    raise ValueError('Invalid block lengths')
                payload=exact(src,size)
                if size<length:
                    if size%2 or 0 in payload[::2] or sum(payload[::2])!=length:
                        raise ValueError('Invalid RLE payload')
                data[i,:size]=np.frombuffer(payload,dtype=np.uint8)
                lengths[i]=length; sizes[i]=size; seen+=length
            restored,_=engine.run(data,lengths,sizes)
            for i in range(n):
                piece=restored[i,:int(lengths[i])].tobytes()
                digest.update(piece); dst.write(piece)
        expected=exact(src,32)
        if seen!=total or digest.digest()!=expected or src.read(1):
            raise ValueError('Integrity verification failed')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['devices','compress','decompress'])
    parser.add_argument('source',nargs='?',type=Path)
    parser.add_argument('target',nargs='?',type=Path)
    parser.add_argument('--device',default='',help='Device name substring, e.g. NVIDIA or Intel')
    args=parser.parse_args()
    if args.action=='devices':
        for d in devices(): print(f'{d.name} | {d.platform.name}')
        return
    if args.source is None or args.target is None: parser.error('source and target are required')
    if args.target.exists(): parser.error('target exists; choose a new filename')
    engine=Engine(args.device); print('Device:',engine.device.name)
    start=time.perf_counter()
    globals()[args.action](engine,args.source,args.target)
    elapsed=time.perf_counter()-start
    print(f'{args.source.stat().st_size:,} -> {args.target.stat().st_size:,} bytes')
    print(f'Elapsed: {elapsed:.3f}s (excludes OpenCL setup/compilation)')
    if args.action=='compress':
        original=args.source.stat().st_size; stored=args.target.stat().st_size
        if stored>=original:
            print(f'NO SPACE SAVED: archive is {stored-original:,} bytes larger. This RLE codec is unsuitable for this input.')
        else:
            print(f'Space saved: {(original-stored)/original:.2%}')
    if args.action=='decompress': print('SHA-256 integrity check: PASS')

if __name__=='__main__': main()
