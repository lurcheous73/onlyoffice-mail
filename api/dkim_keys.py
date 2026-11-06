"""Bounded conversion of OO 12.8's noncanonical PKCS#1 ASN.1 encoding.

CryptoUtil.AppendLength uses long-form lengths even below 128 and exports RSA
integers without a positive sign octet. Current strict DER readers reject it.
Parse exactly the nine PKCS#1 RSA integers and emit canonical DER. The caller
must still validate the resulting RSA private key with its crypto library.
"""


def canonical_oo_pkcs1(data):
    if not isinstance(data,bytes) or not 16<=len(data)<=16384:
        raise ValueError('Invalid OO RSA key size')

    def tlv(offset,tag,limit):
        if offset+2>limit or data[offset]!=tag:raise ValueError('Invalid OO RSA key tag')
        length=data[offset+1];start=offset+2
        if length&128:
            count=length&127
            if count not in (1,2) or start+count>limit:raise ValueError('Invalid OO RSA key length')
            length=int.from_bytes(data[start:start+count],'big');start+=count
        end=start+length
        if not length or end>limit:raise ValueError('Truncated OO RSA key')
        return start,end

    def encoded(tag,value):
        size=len(value)
        if size<128:length=bytes([size])
        else:
            count=(size.bit_length()+7)//8
            length=bytes([128+count])+size.to_bytes(count,'big')
        return bytes([tag])+length+value

    start,end=tlv(0,48,len(data))
    if end!=len(data):raise ValueError('Trailing OO RSA key data')
    values=[]
    for index in range(9):
        first,last=tlv(start,2,end);raw=data[first:last]
        if len(raw)>1025:raise ValueError('Oversize OO RSA integer')
        value=int.from_bytes(raw,'big')
        if (index==0 and value!=0) or (index>0 and value==0):raise ValueError('Unsupported OO RSA key version/integer')
        raw=value.to_bytes(max(1,(value.bit_length()+7)//8),'big')
        if raw[0]&128:raw=b'\0'+raw
        values.append(encoded(2,raw));start=last
    if start!=end:raise ValueError('Extra OO RSA key fields')
    return encoded(48,b''.join(values))
