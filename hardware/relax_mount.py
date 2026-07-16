#!/usr/bin/env python3
"""Overlap-removal relax for the mount board, with a Pi-footprint constraint:
tall / user-facing parts are held on the bottom strip (y >= YMIN) so the Pi
never covers them. Writes the cleaned FLOORPLAN back into layout_mount.py.
"""
import os,sys,re,math,json
sys.path.insert(0,os.path.dirname(__file__) or '.')
import layout_mount   # sets layout_v2 globals to the mount board
import layout_v2 as L

SIZE=json.load(open('_sizes.json'))
W,H=L.BOARD_W,L.BOARD_H
HOLES=L.HOLES; HOLE_R=3.05; EDGE=0.4; GAP=0.15
# parts that must stay OUT of the Pi body (kept on the bottom strip, y>=30)
PIN={'J1','J2','J3','J4','J5','SW1','D1','D2','TP1','TP2','TP3','TP4','TP5','TP6'}  # user-placed, keep fixed
STRIP=set(); YMIN=30.5
BASE=dict(L.FLOORPLAN)
def half(r,rot):
    w,h=SIZE[r]; return (h/2,w/2) if round(rot)%180==90 else (w/2,h/2)

def relax(iters=4000):
    pos={r:[BASE[r][0],BASE[r][1],BASE[r][2]] for r in BASE}
    home={r:(BASE[r][0],BASE[r][1]) for r in BASE}
    refs=list(pos)
    for _ in range(iters):
        moved=False
        for i,a in enumerate(refs):
            ahx,ahy=half(a,pos[a][2])
            for b in refs[i+1:]:
                bhx,bhy=half(b,pos[b][2])
                ox=(ahx+bhx+GAP)-abs(pos[a][0]-pos[b][0]); oy=(ahy+bhy+GAP)-abs(pos[a][1]-pos[b][1])
                if ox<=0 or oy<=0: continue
                moved=True; pa,pb=a in PIN,b in PIN
                if pa and pb: continue
                if ox<oy:
                    d=ox/2 if pos[a][0]<=pos[b][0] else -ox/2
                    if pa: pos[b][0]+=2*d
                    elif pb: pos[a][0]-=2*d
                    else: pos[a][0]-=d; pos[b][0]+=d
                else:
                    d=oy/2 if pos[a][1]<=pos[b][1] else -oy/2
                    if pa: pos[b][1]+=2*d
                    elif pb: pos[a][1]-=2*d
                    else: pos[a][1]-=d; pos[b][1]+=d
        for r in refs:
            if r in PIN: continue
            hx,hy=half(r,pos[r][2]); x,y=pos[r][0],pos[r][1]
            for hxc,hyc in HOLES:
                px=max(x-hx,min(hxc,x+hx)); py=max(y-hy,min(hyc,y+hy)); dist=math.hypot(px-hxc,py-hyc)
                if dist<HOLE_R:
                    ang=math.atan2(y-hyc,x-hxc) if (x,y)!=(hxc,hyc) else 0.0
                    pos[r][0]+=math.cos(ang)*(HOLE_R-dist); pos[r][1]+=math.sin(ang)*(HOLE_R-dist)
            x,y=pos[r][0],pos[r][1]
            if x-hx<EDGE: pos[r][0]+=EDGE-(x-hx)
            if x+hx>W-EDGE: pos[r][0]-=(x+hx)-(W-EDGE)
            if y-hy<EDGE: pos[r][1]+=EDGE-(y-hy)
            if y+hy>H-EDGE: pos[r][1]-=(y+hy)-(H-EDGE)
            if r in STRIP and pos[r][1]-hy<YMIN: pos[r][1]+=YMIN-(pos[r][1]-hy)   # keep off the Pi
            gx,gy=home[r]; pos[r][0]+=(gx-pos[r][0])*0.002; pos[r][1]+=(gy-pos[r][1])*0.002
        if not moved: break
    return {r:(round(pos[r][0],2),round(pos[r][1],2),pos[r][2]) for r in pos}

def overlaps(pos):
    refs=list(pos); c=0
    for i,a in enumerate(refs):
        ahx,ahy=half(a,pos[a][2])
        for b in refs[i+1:]:
            bhx,bhy=half(b,pos[b][2])
            if (ahx+bhx)-abs(pos[a][0]-pos[b][0])>0 and (ahy+bhy)-abs(pos[a][1]-pos[b][1])>0: c+=1
    return c

if __name__=='__main__':
    p=relax()
    print("overlaps after relax:",overlaps(p))
    # write FLOORPLAN back into layout_mount.py
    s=open('layout_mount.py').read()
    for r,(x,y,rot) in p.items():
        s=re.sub(r"'%s': \(-?[\d.]+, -?[\d.]+, -?[\d.]+\)"%re.escape(r), "'%s': (%.2f, %.2f, %s)"%(r,x,y,rot), s, count=1)
    open('layout_mount.py','w').write(s)
    print("wrote relaxed FLOORPLAN")
