#!/usr/bin/env python3
"""Report courtyard overlaps + board-edge/hole violations for a generated board.

Placement debugging aid: kicad-cli tells you *that* courtyards overlap, one
footprint per report block. This says which PAIR, by how much, and in which
direction — which is what you need to actually move something.
"""
import os, re, sys, math

def matching(s, i):
    d=0
    for k in range(i, len(s)):
        if s[k]=='(':d+=1
        elif s[k]==')':
            d-=1
            if d==0: return k+1
    raise ValueError("unbalanced")

def courtyards(path):
    """-> {ref: (x1,y1,x2,y2)} absolute courtyard bboxes."""
    s=open(path).read()
    out={}; k=0
    while True:
        f=s.find('(footprint ',k)
        if f<0: break
        e=matching(s,f); blk=s[f:e]; k=e
        ref=re.search(r'\(property "Reference" "([^"]+)"',blk)
        am=re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)',blk)
        if not (ref and am): continue
        fx,fy,fr=float(am.group(1)),float(am.group(2)),float(am.group(3) or 0)
        c,si=math.cos(math.radians(fr)),math.sin(math.radians(fr))
        xs=[];ys=[]
        for tag in ('(fp_line','(fp_rect','(fp_poly','(fp_circle','(fp_arc'):
            j=0
            while True:
                p=blk.find(tag,j)
                if p<0: break
                pe=matching(blk,p); pb=blk[p:pe]; j=pe
                if 'CrtYd' not in pb: continue
                for m in re.finditer(r'\((?:start|end|mid|center|xy) (-?[\d.]+) (-?[\d.]+)\)',pb):
                    px,py=float(m.group(1)),float(m.group(2))
                    # KiCad's y-down rotation, same convention router.py uses.
                    # Getting the sign wrong mirrors rotated parts and hides
                    # real collisions (it hid four, all on the USB-C receptacles).
                    xs.append(fx+px*c+py*si); ys.append(fy-px*si+py*c)
        if xs: out[ref.group(1)]=(min(xs),min(ys),max(xs),max(ys))
    return out

def overlaps(cy):
    out=[]
    refs=sorted(cy)
    for i,a in enumerate(refs):
        for b in refs[i+1:]:
            ax1,ay1,ax2,ay2=cy[a]; bx1,by1,bx2,by2=cy[b]
            ox=min(ax2,bx2)-max(ax1,bx1); oy=min(ay2,by2)-max(ay1,by1)
            if ox>0 and oy>0: out.append((round(ox*oy,2),a,b,round(ox,2),round(oy,2)))
    return sorted(out,reverse=True)

if __name__=='__main__':
    path=sys.argv[1] if len(sys.argv)>1 else 'powermod_v2.kicad_pcb'
    W,H=(float(sys.argv[2]),float(sys.argv[3])) if len(sys.argv)>3 else (65.0,30.0)
    cy=courtyards(path)
    ov=overlaps(cy)
    print(f"{len(cy)} courtyards; {len(ov)} overlapping pairs")
    for area,a,b,ox,oy in ov:
        print(f"  {a:4s} <-> {b:4s}  overlap {ox:5.2f} x {oy:5.2f} mm  (area {area})")
    off=[(r,bb) for r,bb in cy.items() if bb[0]<0 or bb[1]<0 or bb[2]>W or bb[3]>H]
    if off:
        print(f"\n{len(off)} footprints off-board / over the edge:")
        for r,(x1,y1,x2,y2) in sorted(off):
            print(f"  {r:4s} bbox ({x1:.2f},{y1:.2f})-({x2:.2f},{y2:.2f})")
