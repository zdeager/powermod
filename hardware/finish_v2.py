#!/usr/bin/env python3
"""Batch finish pass for v2: power-pour straps + leftover signal routes.

    python3 finish_v2.py [board]

Runs AFTER stitch_gnd.py (which ties the F/B GND pours to the In1 plane). This
closes the two things Freerouting leaves:

  1. Power-pour fragments. Each F.Cu pad-field pour (VBUS/VOUT/VSYS) fragments
     around foreign-pad clearances; Freerouting sees the pour as one plane and
     never routes between the pieces. Connect fragments with B.Cu straps
     (B.Cu is nearly empty, so a same-net strap almost always clears).
  2. Leftover signal edges Freerouting could not complete: A* from the wire's
     free end (not the pad — a fine-pitch pad has ~3 reachable grid cells; the
     wire end has thousands).

SPEED: everything is decided by GEOMETRY (obstacle model + fill-polygon
point-in-poly + straight-line clearance), applied in one shot, with a SINGLE
refill+DRC at the end. The previous version refilled and ran DRC after every
trial via (~25s each, dozens of trials -> ~20 min); this is ~1 min. The
per-trial DRC only ever re-validated the geometric checks, which are now
In2-aware, so it was redundant.
"""
import os, re, sys, math, subprocess, itertools
sys.path.insert(0, os.path.dirname(__file__) or '.')
import router as R
from stitch_gnd import board_size

KPY = '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
R.WIDTH.update({'VBUS':0.35,'VSYS':0.35,'VOUT':0.35,'VBAT':0.35,
                'L1N':1.1,'L2':1.1,'3V3':0.3})

def refill(board):
    subprocess.run([KPY,'-c',
        f"import pcbnew;b=pcbnew.LoadBoard('{board}');pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard('{board}',b)"],
        capture_output=True)

def drc(board):
    subprocess.run([CLI,'pcb','drc',board,'--refill-zones','-o','drc_v2.rpt'],capture_output=True)
    r=open('drc_v2.rpt').read()
    return (int(re.search(r'Found (\d+) unconnected',r).group(1)),
            int(re.search(r'Found (\d+) DRC violations',r).group(1)))

def fill_polys(board):
    s=open(board).read(); out={}; k=0
    while True:
        z=s.find('(zone',k)
        if z<0: break
        e=R.matching(s,z); blk=s[z:e]; k=e
        nm=re.search(r'\(net_name "([^"]*)"\)',blk) or re.search(r'\(net "([^"]*)"\)',blk)
        if not nm or not nm.group(1): continue
        net=nm.group(1); j=0
        while True:
            f=blk.find('(filled_polygon',j)
            if f<0: break
            fe=R.matching(blk,f); fp=blk[f:fe]; j=fe
            ly=re.search(r'\(layer "([^"]+)"\)',fp).group(1)
            pts=[(float(m.group(1)),float(m.group(2))) for m in re.finditer(r'\(xy (-?[\d.]+) (-?[\d.]+)\)',fp)]
            out.setdefault((net,ly),[]).append(pts)
    return out

def inside(pt,poly):
    x,y=pt; n=len(poly); c=False
    for i in range(n):
        x1,y1=poly[i]; x2,y2=poly[(i+1)%n]
        if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: c=not c
    return c

def in2_segments(board):
    s=open(board).read(); out=[]; k=0
    while True:
        f=s.find('(segment',k)
        if f<0: break
        e=R.matching(s,f); blk=s[f:e]; k=e
        if '(layer "In2.Cu")' not in blk: continue
        st=re.search(r'\(start (-?[\d.]+) (-?[\d.]+)\)',blk); en=re.search(r'\(end (-?[\d.]+) (-?[\d.]+)\)',blk)
        wd=re.search(r'\(width ([\d.]+)\)',blk); nt=re.search(r'\(net "([^"]+)"\)',blk)
        if st and en and wd:
            out.append((float(st.group(1)),float(st.group(2)),float(en.group(1)),float(en.group(2)),
                        float(wd.group(1))/2, nt.group(1) if nt else '?'))
    return out

def emit(board, lines):
    if not lines: return
    txt=open(board).read()
    open(board,'w').write(txt[:txt.rstrip().rfind(')')]+'\n'+'\n'.join(lines)+'\n)\n')

def strap_power(board, obs, codes, polys, in2, holes):
    """B.Cu straps between F.Cu pour fragments of each power net. Geometric."""
    out=[]
    def bclear(net,w,x1,y1,x2,y2):
        n=max(2,int(math.hypot(x2-x1,y2-y1)/0.2))
        for i in range(n+1):
            x=x1+i/n*(x2-x1); y=y1+i/n*(y2-y1)
            if obs.blocked(net,w,'B',x,y,frozenset()): return False
            if any(n2!=net and R.seg_dist(x,y,a1,b1,a2,b2)<hw+w/2+R.CLEAR for a1,b1,a2,b2,hw,n2 in in2):
                return False
        return True
    for net in ('VBUS','VOUT','VSYS'):
        frags=polys.get((net,'F.Cu'),[])
        groups=[]
        for fr in frags:
            mem=[(p[1],p[2]) for p in R.parse_pads() if p[0]==net and inside((p[1],p[2]),fr)]
            if mem: groups.append(mem)
        if len(groups)<2:
            print(f"  {net}: {len(groups)} fragment(s), no strap needed"); continue
        w=R.WIDTH.get(net,R.DEF_W)
        # connect each fragment to fragment[0] (spanning tree via nearest pad)
        base=groups[0]
        straps=0
        for g in groups[1:]:
            pairs=sorted((math.hypot(a[0]-b[0],a[1]-b[1]),a,b) for a in base for b in g)
            done=False
            for _,a,b in pairs[:12]:
                if any(math.hypot(a[0]-hx,a[1]-hy)<1.35 or math.hypot(b[0]-hx,b[1]-hy)<1.35 for hx,hy in holes): continue
                route=None
                if bclear(net,w,a[0],a[1],b[0],b[1]): route=[a,b]
                else:
                    for mx,my in ((b[0],a[1]),(a[0],b[1])):
                        if bclear(net,w,a[0],a[1],mx,my) and bclear(net,w,mx,my,b[0],b[1]):
                            route=[a,(mx,my),b]; break
                if not route: continue
                out.append(f'  (via (at {a[0]:.3f} {a[1]:.3f}) (size {R.VIA_SIZE}) (drill {R.VIA_DRILL}) (layers "F.Cu" "B.Cu") (net {codes[net]}))')
                out.append(f'  (via (at {b[0]:.3f} {b[1]:.3f}) (size {R.VIA_SIZE}) (drill {R.VIA_DRILL}) (layers "F.Cu" "B.Cu") (net {codes[net]}))')
                for (x1,y1),(x2,y2) in zip(route,route[1:]):
                    out.append(f'  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) (width {w}) (layer "B.Cu") (net {codes[net]}))')
                    obs.add_track('B',x1,y1,x2,y2,w/2,net)
                base=base+g; straps+=1; done=True; break
            if not done: print(f"    {net}: no clear strap to a fragment")
        print(f"  {net}: {straps} B-strap(s) across {len(groups)} fragments")
    return out

def route_signals(board, obs0, codes, in2):
    """A* the leftover signal edges, starting from track ends. Geometric."""
    inv={v:k for k,v in codes.items() if isinstance(v,int)}
    r=open('drc_v2.rpt').read()
    jobs={}
    for b in re.split(r'\n(?=\[)',r):
        if not b.startswith('[unconnected_items]'): continue
        net=re.findall(r'\[([A-Z0-9_+]+)\]',b)
        pts=re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (?:Pad|PTH pad|Track|Via)',b)
        if net and net[0] not in ('GND','VBUS','VOUT','VSYS') and len(pts)>=2:
            jobs.setdefault(net[0],(tuple(map(float,pts[0])),tuple(map(float,pts[1]))))
    if not jobs: print("  no signal leftovers"); return []
    print("  signal leftovers:",list(jobs))
    R.EDGE_MARGIN=0.85
    out=[]
    pads=R.parse_pads()
    for net,(a,b) in jobs.items():
        obs=R.Obstacles(pads); R.parse_existing(obs,inv)
        for x1,y1,x2,y2,hw,n2 in in2:
            for ly in ('F','B'): obs.add_track(ly,x1,y1,x2,y2,hw,n2)
        em=[]
        retarget=R.build_escapes(pads,obs,codes,em)
        q1=retarget.get((round(a[0],2),round(a[1],2)),a)
        q2=retarget.get((round(b[0],2),round(b[1],2)),b)
        path=None
        for mult in (30,100):
            R.LIMIT_MULT=mult
            path=R.route_edge(obs,net,R.WIDTH.get(net,R.DEF_W),q1,q2)
            if path: break
        if not path: print(f"    {net}: A* no path"); continue
        R.emit_path(obs,codes,em,net,R.WIDTH.get(net,R.DEF_W),q1,q2,path)
        out+=em; print(f"    {net}: routed")
    return out

def main(board):
    R.BOARD=board; R.BW,R.BH=board_size(board)
    refill(board)
    print("start:",drc(board))
    pads=R.parse_pads(); codes=R.net_codes()
    inv={v:k for k,v in codes.items() if isinstance(v,int)}
    obs=R.Obstacles(pads); R.parse_existing(obs,inv)
    holes=[(p[1],p[2]) for p in pads if p[5]=='BOTH']
    polys=fill_polys(board); in2=in2_segments(board)
    print("power straps:")
    lines=strap_power(board,obs,codes,polys,in2,holes)
    emit(board,lines); refill(board)
    print("signal routes:")
    lines=route_signals(board,obs,codes,in2)
    emit(board,lines); refill(board)
    print("final:",drc(board))

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else 'powermod_v2.kicad_pcb')
