#!/usr/bin/env python3
"""Constraint-aware placer for the mount board.

Force-directed placement with electrical constraints:
  - net springs (connected parts attract) so functional sub-circuits self-assemble;
    GND is excluded (it bridges everything), global rails pull weakly.
  - padded repulsion: every part keeps a few-mm gap from its neighbours.
  - wide-net halo: parts carrying high-current nets (switch node, VBUS, VOUT, VSYS)
    reserve extra clearance so a fat trace has a corridor.
  - the converter power stage is a RIGID block (the hand-tuned layout) moved as a unit.
  - user I/O + mounting holes are fixed anchors; hole/edge keep-outs apply to all.

Writes the result into powermod.kicad_pcb via layout_v2.gen_pcb and can Freerouting-score.
"""
import sys,os,math,json,random,subprocess,re
sys.path.insert(0,os.path.join(os.path.dirname(__file__) or '.', '..'))
import layout_v2 as L
import layout_mount            # configure layout_v2 globals to the mount board
from netlist import build_nets
import place_search_mount as P  # PIN set, half(), overlaps(), relax()

SIZE=json.load(open('_sizes.json'))
W,H=L.BOARD_W,L.BOARD_H
HOLES=L.HOLES; HOLE_R=3.05; EDGE=0.6; YMAX=30.0    # circuit stays above the I/O strip
PIN=P.PIN
START=json.load(open('_startpos.json'))

# the hand-tuned converter power stage, relative to U3 (rigid)
CONV_BLOCK={"C16":(4.95,-7.8,90),"R24":(-6.56,-1.3,0),"R26":(-6.55,2.7,0),"C1":(-3.17,-12.11,0),
 "U3":(0.0,0.0,0),"L1":(1.45,6.2,180),"C4":(1.95,-7.8,90),"C2":(0.57,-12.11,0),"C5":(-1.55,-7.8,90),
 "R25":(-6.55,0.7,0),"R14":(4.94,-3.8,0),"C3":(-5.05,-7.8,90)}
BLOCK=set(CONV_BLOCK)
WIDE={'L2','L1N','VSYS','VBUS','VOUT'}          # halo nets
LOWWT={'VSYS','VBUS','VOUT','3V3','VBAT','VBACKUP','VSYS'}  # global rails: weak spring
IC={'U1','U2','U3','U4','U5'}                    # multi-pin parts get an escape halo
PAD=1.9; HALO=1.1; ICHALO=0.6; KS=0.010; KR=0.5; KHOLE=0.9

def half(r,rot):
    w,h=SIZE[r]; return (h/2,w/2) if round(rot)%180==90 else (w/2,h/2)

nets=build_nets()
wide_parts=set(r for n in WIDE for r,_ in nets.get(n,()))
def halo(r):
    # a power part (or IC) reserves extra clearance from ALL neighbours, not just other power parts
    return (HALO if r in wide_parts else 0.0)+(ICHALO if r in IC else 0.0)
springs=[]
for net,pins in nets.items():
    if net=='GND': continue
    refs=sorted({r for r,_ in pins if r in START})
    if not (2<=len(refs)<=12): continue
    wt=0.25 if net in LOWWT else 1.0
    for i in range(len(refs)):
        for j in range(i+1,len(refs)): springs.append((refs[i],refs[j],wt))

# block bbox relative to U3 (for clamping the unit)
_bx=[o[0] for o in CONV_BLOCK.values()]; _by=[o[1] for o in CONV_BLOCK.values()]
def block_ext(pos):
    xs=[];ys=[]
    for r,o in CONV_BLOCK.items():
        hx,hy=half(r,o[2]); xs+=[o[0]-hx,o[0]+hx]; ys+=[o[1]-hy,o[1]+hy]
    return min(xs),max(xs),min(ys),max(ys)

def clamp_one(pos,r):
    hx,hy=half(r,pos[r][2]); x,y=pos[r][0],pos[r][1]
    for hxc,hyc in HOLES:
        px=max(x-hx,min(hxc,x+hx)); py=max(y-hy,min(hyc,y+hy)); d=math.hypot(px-hxc,py-hyc)
        if 1e-6<d<HOLE_R:
            a=math.atan2(y-hyc,x-hxc); x+=math.cos(a)*(HOLE_R-d); y+=math.sin(a)*(HOLE_R-d)
    x=max(EDGE+hx,min(W-EDGE-hx,x)); y=max(EDGE+hy,min(YMAX-hy,y))
    pos[r][0],pos[r][1]=x,y

def place(iters=1300,seed=1):
    random.seed(seed)
    pos={r:[START[r][0],START[r][1],START[r][2]] for r in START}
    def sync():
        ux,uy=pos['U3'][0],pos['U3'][1]
        for r,o in CONV_BLOCK.items(): pos[r][0]=ux+o[0]; pos[r][1]=uy+o[1]; pos[r][2]=o[2]
    sync()
    mov=[r for r in pos if r not in PIN and r not in BLOCK]
    for _ in range(iters):
        F={r:[0.0,0.0] for r in pos if r not in PIN}
        for a,b,wt in springs:
            dx=pos[b][0]-pos[a][0]; dy=pos[b][1]-pos[a][1]; d=math.hypot(dx,dy)+1e-6
            f=wt*KS*d; ux,uy=dx/d,dy/d
            if a not in PIN: F[a][0]+=f*ux; F[a][1]+=f*uy
            if b not in PIN: F[b][0]-=f*ux; F[b][1]-=f*uy
        refs=list(pos)
        for i,a in enumerate(refs):
            ahx,ahy=half(a,pos[a][2])
            for b in refs[i+1:]:
                bhx,bhy=half(b,pos[b][2])
                dx=pos[a][0]-pos[b][0]; dy=pos[a][1]-pos[b][1]
                pad=PAD+max(halo(a),halo(b))     # the part needing more room sets the gap
                ox=(ahx+bhx+pad)-abs(dx); oy=(ahy+bhy+pad)-abs(dy)
                if ox>0 and oy>0:
                    if ox<oy:
                        p=ox*(1 if dx>=0 else -1)*KR
                        if a not in PIN: F[a][0]+=p
                        if b not in PIN: F[b][0]-=p
                    else:
                        p=oy*(1 if dy>=0 else -1)*KR
                        if a not in PIN: F[a][1]+=p
                        if b not in PIN: F[b][1]-=p
        # move block as a unit (sum its parts' forces onto U3)
        bf=[sum(F.get(r,(0,0))[0] for r in CONV_BLOCK), sum(F.get(r,(0,0))[1] for r in CONV_BLOCK)]
        pos['U3'][0]+=bf[0]*0.5/len(CONV_BLOCK); pos['U3'][1]+=bf[1]*0.5/len(CONV_BLOCK)
        for r in mov: pos[r][0]+=F[r][0]; pos[r][1]+=F[r][1]
        sync()
        # clamp block unit to bounds, then movable parts
        mnx,mxx,mny,mxy=block_ext(pos); ux,uy=pos['U3'][0],pos['U3'][1]
        ux=max(EDGE-mnx,min(W-EDGE-mxx,ux)); uy=max(EDGE-mny,min(YMAX-mxy,uy))
        pos['U3'][0],pos['U3'][1]=ux,uy; sync()
        for r in mov: clamp_one(pos,r)
    return {r:(round(pos[r][0],2),round(pos[r][1],2),pos[r][2]) for r in pos}

if __name__=='__main__':
    pos=place()
    pos=P.relax(P.relax(pos))          # final overlap cleanup (respects PIN)
    print("overlaps:",P.overlaps(pos))
    L.FLOORPLAN=pos; L.gen_pcb('powermod.kicad_pcb')
    open('mount_best.py','w').write("UNROUTED=0\nFLOORPLAN=%r\n"%pos)
    print("wrote placement")
