#!/usr/bin/env python3
"""Close the remaining unrouted signal nets with the In2-capable A* router.

    python3 close_nets.py [board]

Routes each unconnected net (from KiCad's DRC ratsnest) with router.py's grid
A*, now extended to use the In2.Cu inner layer. Every route is validated by a
full refill + DRC: kept only if it drops the unconnected count and adds no new
short/clearance/dangling error. Safe by construction — a bad route is reverted.
"""
import os, re, sys, math, subprocess
sys.path.insert(0, os.path.dirname(__file__) or '.')
import router as R
from stitch_gnd import board_size

KPY='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

def refill(bd):
    subprocess.run([KPY,'-c',f"import pcbnew;b=pcbnew.LoadBoard('{bd}');pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard('{bd}',b)"],capture_output=True)

def drc(bd):
    subprocess.run([CLI,'pcb','drc',bd,'--refill-zones','-o','drc_v2.rpt'],capture_output=True)
    r=open('drc_v2.rpt').read()
    unc=int(re.search(r'Found (\d+) unconnected',r).group(1))
    err=len(re.findall(r'\[(shorting_items|via_dangling|track_dangling|clearance|hole_clearance|holes_co_located)\]',r))
    return unc,err

def jobs_from_drc(pads):
    """-> [(net, unconnected_pad_xy, nearest_same_net_target_xy)]"""
    r=open('drc_v2.rpt').read()
    tracks=[]  # (net, midx, midy) from the board, to aim at
    s=open(R.BOARD).read(); k=0
    seg={}
    while True:
        f=s.find('(segment',k)
        if f<0: break
        e=R.matching(s,f); blk=s[f:e]; k=e
        st=re.search(r'\(start (-?[\d.]+) (-?[\d.]+)\)',blk);en=re.search(r'\(end (-?[\d.]+) (-?[\d.]+)\)',blk);nt=re.search(r'\(net "([^"]+)"\)',blk)
        if st and en and nt:
            seg.setdefault(nt.group(1),[]).append((float(st.group(1)),float(st.group(2)),float(en.group(1)),float(en.group(2))))
    def segd(px,py,x1,y1,x2,y2):
        dx,dy=x2-x1,y2-y1;L2=dx*dx+dy*dy
        if L2==0: return math.hypot(px-x1,py-y1),x1,y1
        t=max(0,min(1,((px-x1)*dx+(py-y1)*dy)/L2));cx,cy=x1+t*dx,y1+t*dy
        return math.hypot(px-cx,py-cy),cx,cy
    out=[]; seen=set()
    for b in re.split(r'\n(?=\[)',r):
        if not b.startswith('[unconnected_items]'): continue
        for x,y,_,padnum,pn,ref in re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (Pad|PTH pad) (\S+) \[([A-Z0-9_+]+)\] of (\S+)',b):
            if pn=='GND' or (ref,padnum) in seen: continue
            seen.add((ref,padnum)); x,y=float(x),float(y)
            # nearest same-net track point
            best=None
            for x1,y1,x2,y2 in seg.get(pn,[]):
                d,cx,cy=segd(x,y,x1,y1,x2,y2)
                if best is None or d<best[0]: best=(d,cx,cy)
            for p in pads:
                if p[0]!=pn or (abs(p[1]-x)<0.3 and abs(p[2]-y)<0.3): continue
                d=math.hypot(p[1]-x,p[2]-y)
                if best is None or d<best[0]: best=(d,p[1],p[2])
            if best: out.append((pn,(x,y),(best[1],best[2]),best[0]))
    return sorted(out,key=lambda j:j[3])   # shortest first

def main(bd):
    R.BOARD=bd; R.BW,R.BH=board_size(bd)
    R.USE_IN2=True   # 4-layer board: allow routing on the In2 inner layer
    R.WIDTH.update({'VBUS':0.35,'VSYS':0.35,'VOUT':0.35,'VBAT':0.35,'3V3':0.3,
                    'SDA':0.25,'SCL':0.25,'RTC_INT':0.25,'CHG_CE':0.25,
                    'LED_BAT_A':0.25,'Q1_GATE_DRV':0.25,'VBACKUP':0.3})
    R.EDGE_MARGIN=0.85
    codes=R.net_codes(); inv={v:k for k,v in codes.items() if isinstance(v,int)}
    pads=R.parse_pads()
    refill(bd); base=drc(bd); print("start:",base)
    for net,a,b,gap in jobs_from_drc(pads):
        obs=R.Obstacles(pads); R.parse_existing(obs,inv)
        em=[]
        retarget=R.build_escapes(pads,obs,codes,em)
        q1=retarget.get((round(a[0],2),round(a[1],2)),a)
        q2=retarget.get((round(b[0],2),round(b[1],2)),b)
        w=R.WIDTH.get(net,R.DEF_W)
        path=None
        for mult in (20,60,200):
            R.LIMIT_MULT=mult
            path=R.route_edge(obs,net,w,q1,q2)
            if path: break
        if not path:
            print(f"  {net} ({gap:.0f}mm): no path"); continue
        R.emit_path(obs,codes,em,net,w,q1,q2,path)
        src=open(bd).read()
        open(bd,'w').write(src[:src.rstrip().rfind(')')]+'\n'+'\n'.join(em)+'\n)\n')
        refill(bd); unc,err=drc(bd)
        if unc<base[0] and err<=base[1]:
            layers=set(p[2] for p in path)
            via='+In2' if 'I' in layers else ''
            print(f"  {net} ({gap:.0f}mm): routed{via} -> {unc} unc"); base=(unc,err)
        else:
            print(f"  {net} ({gap:.0f}mm): rejected ({unc} unc, {err} err)"); open(bd,'w').write(src)
    refill(bd); print("final:",drc(bd))

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else 'powermod_v2.kicad_pcb')
