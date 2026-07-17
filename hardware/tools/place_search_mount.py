#!/usr/bin/env python3
"""Placement search for the mount board: user I/O + jumpers + holes are FIXED;
circuit parts go anywhere on the board (under the Pi AND on the extension --
density spread out is the whole point). Anneal on ratsnest crossings, remove
overlaps, and let Freerouting judge each candidate. Keep the best-routing one.
"""
import os,sys,re,math,random,json,subprocess,time
sys.path.insert(0,os.path.join(os.path.dirname(__file__) or '.', '..'))
import layout_mount              # configures layout_v2 globals to the mount board
import layout_v2 as L
from netlist import build_nets

KPY='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
BOARD='powermod.kicad_pcb'; DSN='powermod.dsn'
W,H=L.BOARD_W,L.BOARD_H
SIZE=json.load(open('_sizes.json'))
HOLES=L.HOLES; HOLE_R=3.05; EDGE=0.4; GAP=0.2
# user-placed parts (from the stencil) + jumpers -> FIXED
PIN={'J1','J2','J3','J4','J5','JP1','JP2','SW1','D1','D2','TP1','TP2','TP3','TP4','TP5','TP6'}
BASE=dict(L.FLOORPLAN)
MOV=[r for r in BASE if r not in PIN]

def half(r,rot):
    w,h=SIZE[r]; return (h/2,w/2) if round(rot)%180==90 else (w/2,h/2)

def netgroups():
    out=[]
    for net,pins in build_nets().items():
        if net=='GND': continue
        refs=sorted({r for r,_ in pins if r in BASE})
        if 2<=len(refs)<=10: out.append(refs)
    return out
GROUPS=netgroups()

def mst_segs(pos):
    segs=[]
    for refs in GROUPS:
        pts=[(pos[r][0],pos[r][1]) for r in refs]
        inm=[0]; rest=list(range(1,len(pts)))
        while rest:
            best=None
            for a in inm:
                for b in rest:
                    d=(pts[a][0]-pts[b][0])**2+(pts[a][1]-pts[b][1])**2
                    if best is None or d<best[0]: best=(d,a,b)
            _,a,b=best; segs.append((pts[a],pts[b])); inm.append(b); rest.remove(b)
    return segs
def _ccw(a,b,c): return (c[1]-a[1])*(b[0]-a[0])>(b[1]-a[1])*(c[0]-a[0])
def _x(s1,s2):
    a,b=s1;c,d=s2
    if a in(c,d) or b in(c,d): return False
    return _ccw(a,c,d)!=_ccw(b,c,d) and _ccw(a,b,c)!=_ccw(a,b,d)
def crossings(pos):
    s=mst_segs(pos); n=len(s); c=0
    for i in range(n):
        for j in range(i+1,n):
            if _x(s[i],s[j]): c+=1
    return c

def relax(pos,iters=3000):
    pos={r:[pos[r][0],pos[r][1],pos[r][2]] for r in pos}
    home={r:(BASE[r][0],BASE[r][1]) for r in pos}
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

def spread():
    """random circuit spread over the whole board, then relax."""
    p=dict(BASE)
    for r in MOV:
        p[r]=(random.uniform(6,W-6), random.uniform(4,H-4),
              random.choice([0,90]) if random.random()<0.3 else BASE[r][2])
    return relax(relax(p))

def anneal(start,steps=2500,T0=8.0):
    cur={r:tuple(start[r]) for r in start}; curc=crossings(cur); best=dict(cur); bestc=curc
    for s in range(steps):
        T=T0*(1-s/steps)+0.05
        r=random.choice(MOV); x,y,ro=cur[r]
        if random.random()<0.2: nr=(x,y,random.choice([0,90,180,270]))
        else: nr=(x+random.uniform(-4,4), y+random.uniform(-4,4), ro)
        old=cur[r]; cur[r]=nr; nc=crossings(cur)
        if nc<=curc or random.random()<math.exp(-(nc-curc)/max(T,0.01)):
            curc=nc
            if nc<bestc: best=dict(cur); bestc=nc
        else: cur[r]=old
    return relax(relax(best))

def score(pos,passes=2):
    L.FLOORPLAN=pos; L.gen_pcb(BOARD)
    subprocess.run([KPY,'fr_pipeline.py','export',BOARD],capture_output=True)
    best=99
    for i in range(passes):
        r=subprocess.run(['java','-Djava.awt.headless=true','-jar','freerouting.jar','-de',DSN,'-do',f'_ms{i}.ses','-mp','50'],capture_output=True,text=True,timeout=200)
        m=re.findall(r'\((\d+) unrouted',r.stdout+r.stderr)
        if m: best=min(best,int(m[-1]))
    return best

def main(N=12):
    random.seed(7); t0=time.time()
    cands=[('baseline',relax(relax(BASE)))]
    for i in range(5): cands.append((f'spread{i}', spread()))
    cands.append(('anneal-base', anneal(BASE)))
    for i in range(3): cands.append((f'anneal-spread{i}', anneal(spread())))
    scored=[]
    for name,p in cands:
        scored.append((crossings(p),overlaps(p),name,p)); print(f"  {name}: crossings={scored[-1][0]} overlaps={scored[-1][1]}",flush=True)
    scored.sort()
    todo=[c for c in scored if c[1]<=3][:N]
    print(f"\nfreerouting {len(todo)}...",flush=True)
    res=[]
    for cr,ov,name,p in todo:
        try: u=score(p)
        except Exception as e: u=99
        res.append((u,cr,name,p)); print(f"  {name}: cross={cr} -> {u} unrouted  ({time.time()-t0:.0f}s)",flush=True)
    res.sort(); u,cr,name,p=res[0]
    print(f"\nBEST: {name}  {u} unrouted",flush=True)
    L.FLOORPLAN=p; L.gen_pcb('powermod_best.kicad_pcb')
    open('mount_best.py','w').write("UNROUTED=%d\nFLOORPLAN=%r\n"%(u,p))
if __name__=='__main__': main()
