// Fixed-Huffman DEFLATE, independent byte-aligned chunks (RFC 1951).
__constant uint LB[29]={3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258};
__constant uint LE[29]={0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0};
__constant uint DB[30]={1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577};
__constant uint DE[30]={0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13};
uint rev(uint v,uint n){uint r=0;for(uint i=0;i<n;i++){r=(r<<1)|(v&1);v>>=1;}return r;}
void bits(__global uchar *out,uint *pos,uint value,uint n){
 for(uint i=0;i<n;i++){uint p=*pos;out[p>>3]|=(uchar)(((value>>i)&1)<<(p&7));*pos=p+1;}
}
void symbol(__global uchar *out,uint *pos,uint s){
 uint c,n;if(s<=143){c=48+s;n=8;}else if(s<=255){c=400+s-144;n=9;}
 else if(s<=279){c=s-256;n=7;}else{c=192+s-280;n=8;}
 bits(out,pos,rev(c,n),n);
}
__kernel void deflate_blocks(__global const uchar *src,__global uchar *dst,
 __global const uint *lengths,__global uint *sizes,__global int *tables,uint block){
 uint id=get_global_id(0),n=lengths[id],i=0,p=0;
 size_t s=(size_t)id*block,d=(size_t)id*block*2,t=(size_t)id*4096;
 __global uchar *out=dst+d;
 for(uint j=0;j<block*2;j++)out[j]=0;
 for(uint j=0;j<4096;j++)tables[t+j]=-1;
 bits(out,&p,2,3); // BFINAL=0, fixed Huffman
 while(i<n){
  uint len=0,distance=0;
  if(i+3<=n){
   uint h=(((uint)src[s+i]*251u+src[s+i+1])*251u+src[s+i+2])&4095u;
   int prev=tables[t+h];tables[t+h]=(int)i;
   if(prev>=0 && i-(uint)prev<=32768){
    uint limit=min(258u,n-i);
    while(len<limit && src[s+(uint)prev+len]==src[s+i+len])len++;
    distance=i-(uint)prev;
   }
  }
  if(len>=3){
   uint lc=0;while(lc<28 && LB[lc+1]<=len)lc++;
   symbol(out,&p,257+lc);bits(out,&p,len-LB[lc],LE[lc]);
   uint dc=0;while(dc<29 && DB[dc+1]<=distance)dc++;
   bits(out,&p,rev(dc,5),5);bits(out,&p,distance-DB[dc],DE[dc]);i+=len;
  }else{symbol(out,&p,src[s+i]);i++;}
 }
 symbol(out,&p,256);
 bits(out,&p,0,3); // non-final empty stored block aligns next chunk
 p=(p+7)&~7u;bits(out,&p,0,16);bits(out,&p,65535,16);
 uint size=(p+7)/8;
 if(size>=n+5){
  out[0]=0;out[1]=(uchar)n;out[2]=(uchar)(n>>8);
  uint inverse=(~n)&65535;out[3]=(uchar)inverse;out[4]=(uchar)(inverse>>8);
  for(uint j=0;j<n;j++)out[5+j]=src[s+j];size=n+5;
 }
 sizes[id]=size;
}
