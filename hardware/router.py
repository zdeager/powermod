#!/usr/bin/env python3
"""PowerMOD grid autorouter.

Philosophy: same loop as ERC/placement — generate, let KiCad judge, iterate.
A deliberately simple Manhattan A* on a 0.25mm grid, two layers:
  - F.Cu preferred; B.Cu costs extra (it cuts the GND pour) and needs vias
  - power nets routed first and wide
  - GND is NOT routed: the two-sided pour + --refill-zones owns it
Targets come from KiCad's own DRC ratsnest report, so endpoints are exactly
what KiCad thinks is unconnected; obstacles come from parsing every pad in
the board file (positions self-calibrated against the report's coordinates).
"""
import re, math, heapq, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, 'powermod.kicad_pcb')
KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
GRID = 0.25
CLEAR = 0.21           # target copper clearance (DRC floor 0.2 + margin)
EDGE_MARGIN = 0.5
WIDTH = {'VBUS':1.0,'VSYS':1.0,'VBAT':1.0,'VOUT':1.0,'L1N':1.0,'L2':1.0,'3V3':0.5}
DEF_W = 0.3
VIA_SIZE, VIA_DRILL = 0.6, 0.3
BW, BH = 62.0, 46.0

def gi(v): return int(round(v/GRID))
def gf(i): return i*GRID

# ---------------------------------------------------------------- parse board
def matching(s,i):
    d=0
    for k in range(i,len(s)):
        if s[k]=='(':d+=1
        elif s[k]==')':
            d-=1
            if d==0: return k+1

def parse_pads():
    """-> list of (net, cx, cy, hx, hy, layers) absolute, bbox half-extents."""
    s=open(BOARD).read()
    pads=[]
    k=0
    while True:
        f=s.find('(footprint ',k)
        if f<0: break
        e=matching(s,f); blk=s[f:e]; k=e
        am=re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)',blk)
        fx,fy,fr=float(am.group(1)),float(am.group(2)),float(am.group(3) or 0)
        c,si=math.cos(math.radians(fr)),math.sin(math.radians(fr))
        fpid=len(pads)  # marker: pads appended below share this footprint
        j=0
        while True:
            p=blk.find('(pad "',j)
            if p<0: break
            pe=matching(blk,p); pb=blk[p:pe]; j=pe
            pm=re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)',pb)
            sm=re.search(r'\(size ([\d.]+) ([\d.]+)\)',pb)
            nm=re.search(r'\(net (?:\d+ )?"([^"]*)"\)',pb)
            ly=re.search(r'\(layers ([^)]+)\)',pb)
            px,py=float(pm.group(1)),float(pm.group(2))
            pa=float(pm.group(3) or 0)
            sx,sy=float(sm.group(1)),float(sm.group(2))
            if '(primitives' in pb: sx+=1.0; sy+=1.0   # custom-shape pad: bbox is a lie
            # pad bbox half extents in board frame: pad angle pa is absolute
            if abs(pa%180)>45: sx,sy=sy,sx
            ax=fx + px*c + py*si
            ay=fy - px*si + py*c
            layers=ly.group(1)
            through='*.Cu' in layers or 'thru' in pb
            pads.append((nm.group(1) if nm else '', ax, ay, sx/2, sy/2,
                         'BOTH' if through else ('F' if 'F.Cu' in layers else 'B'), fpid))
    return pads

def net_codes():
    s=open(BOARD).read()
    out={}
    for m in re.finditer(r'\(net (\d+) "([^"]+)"\)',s):
        out[m.group(2)]=int(m.group(1))
    if not out:  # KiCad 10 name-based format
        for m in re.finditer(r'\(net "([^"]+)"\)',s):
            out.setdefault(m.group(1), f'"{m.group(1)}"')
    return out

# ------------------------------------------------------------- ratsnest edges
def ratsnest():
    rpt=os.path.join(HERE,'drc_route.rpt')
    subprocess.run([KCLI,'pcb','drc',BOARD,'-o',rpt,'--refill-zones'],capture_output=True)
    txt=open(rpt).read()
    edges=[]
    blocks=re.split(r'\n(?=\[)', txt)
    for b in blocks:
        if not b.startswith('[unconnected_items]'): continue
        items=re.findall(r'@\((-?[\d.]+) mm, (-?[\d.]+) mm\): ([^\n]*)', b)
        if len(items)!=2: continue
        (x1,y1,d1),(x2,y2,d2)=items
        n1=re.search(r'\[([A-Za-z0-9_]+)\]',d1); n2=re.search(r'\[([A-Za-z0-9_]+)\]',d2)
        if not n1 or not n2 or n1.group(1)!=n2.group(1): continue
        edges.append((n1.group(1),(float(x1),float(y1)),(float(x2),float(y2))))
    viol=len(re.findall(r'^\[(?!unconnected)',txt,re.M))
    return edges, viol, txt

# ------------------------------------------------------------------ obstacles
BUCKET=2.5
class Obstacles:
    def __init__(self,pads):
        self.pads=pads
        self.tracks={'F':[],'B':[]}
        self.vias=[]
        self.idx={}   # (bx,by,layer) -> list of ('P',i)/('T',layer,i)/('V',i)
        for i,p in enumerate(pads):
            n,cx,cy,hx,hy,pl,_=p
            lys=('F','B') if pl=='BOTH' else (pl,)
            for ly in lys:
                self._put(cx-hx,cy-hy,cx+hx,cy+hy,ly,('P',i))
    def _put(self,x1,y1,x2,y2,layer,item):
        for bx in range(int(min(x1,x2)//BUCKET),int(max(x1,x2)//BUCKET)+1):
            for by in range(int(min(y1,y2)//BUCKET),int(max(y1,y2)//BUCKET)+1):
                self.idx.setdefault((bx,by,layer),[]).append(item)
    def add_track(self,layer,x1,y1,x2,y2,hw,net):
        self.tracks[layer].append((x1,y1,x2,y2,hw,net))
        self._put(x1,y1,x2,y2,layer,('T',layer,len(self.tracks[layer])-1))
    def add_via(self,x,y,net):
        self.vias.append((x,y,net))
        for ly in ('F','B'): self._put(x-0.5,y-0.5,x+0.5,y+0.5,ly,('V',len(self.vias)-1))
    def blocked(self,net,w,layer,x,y,exempt=frozenset()):
        r=w/2+CLEAR
        if x<EDGE_MARGIN+w/2 or x>BW-EDGE_MARGIN-w/2 or y<EDGE_MARGIN+w/2 or y>BH-EDGE_MARGIN-w/2:
            return True
        bx,by=int(x//BUCKET),int(y//BUCKET)
        seen=set()
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for it in self.idx.get((bx+dx,by+dy,layer),()):
                    if it in seen: continue
                    seen.add(it)
                    if it[0]=='P':
                        if it[1] in exempt: continue
                        n,cx,cy,hx,hy,pl,_=self.pads[it[1]]
                        if n==net and n: continue
                        if abs(x-cx)<hx+r and abs(y-cy)<hy+r: return True
                    elif it[0]=='T':
                        x1,y1,x2,y2,hw,n=self.tracks[it[1]][it[2]]
                        if n==net: continue
                        if seg_dist(x,y,x1,y1,x2,y2) < hw+r: return True
                    else:
                        vx,vy,n=self.vias[it[1]]
                        if n==net: continue
                        if (x-vx)**2+(y-vy)**2 < (VIA_SIZE/2+r)**2: return True
        return False

def seg_dist(px,py,x1,y1,x2,y2):
    dx,dy=x2-x1,y2-y1
    L2=dx*dx+dy*dy
    if L2==0: return math.hypot(px-x1,py-y1)
    t=max(0,min(1,((px-x1)*dx+(py-y1)*dy)/L2))
    return math.hypot(px-(x1+t*dx),py-(y1+t*dy))

# ----------------------------------------------------------------------- A*
def endpoint_pads(obs,p):
    out=set()
    for i,(n,cx,cy,hx,hy,pl,_) in enumerate(obs.pads):
        if abs(p[0]-cx)<=hx+0.05 and abs(p[1]-cy)<=hy+0.05:
            out.add(i)
    return out

def route_edge(obs,net,w,p1,p2,allow_b=True):
    exempt=frozenset(endpoint_pads(obs,p1)|endpoint_pads(obs,p2))
    s=(gi(p1[0]),gi(p1[1]),'F'); t=(gi(p2[0]),gi(p2[1]),'F')
    def h(n): return (abs(n[0]-t[0])+abs(n[1]-t[1]))
    def near(fx,fy):
        return (abs(fx-p1[0])<1.0 and abs(fy-p1[1])<1.0) or (abs(fx-p2[0])<1.0 and abs(fy-p2[1])<1.0)
    openq=[(h(s),0,s,None)]; came={}; best={s:0}
    seen_target=None
    LIMIT=250000*globals().get('LIMIT_MULT',1); pops=0
    while openq:
        f,g,n,par=heapq.heappop(openq); pops+=1
        if pops>LIMIT: return None
        if n in came: continue
        came[n]=par
        if abs(n[0]-t[0])<=1 and abs(n[1]-t[1])<=1 and n[2]=='F':
            seen_target=n; break
        x,y,ly=n
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            m=(x+dx,y+dy,ly)
            ng=g+ (1 if ly=='F' else 3)
            if m in came or best.get(m,1e18)<=ng: continue
            fx,fy=gf(m[0]),gf(m[1])
            w_eff = min(w,0.25) if near(fx,fy) else w
            if obs.blocked(net,w_eff,ly,fx,fy,exempt): continue
            best[m]=ng; heapq.heappush(openq,(ng+h(m),ng,m,n))
        if allow_b:
            other='B' if ly=='F' else 'F'
            m=(x,y,other); ng=g+40
            if m not in came and best.get(m,1e18)>ng:
                fx,fy=gf(x),gf(y)
                if (not obs.blocked(net,w,other,fx,fy,exempt)
                        and not obs.blocked(net,VIA_SIZE,ly,fx,fy,exempt)):
                    best[m]=ng; heapq.heappush(openq,(ng+h(m),ng,m,n))
    if not seen_target: return None
    path=[]; n=seen_target
    while n: path.append(n); n=came[n]
    path.reverse()
    return path

def compress(path,p1,p2,w):
    """-> ('seg',x1,y1,x2,y2,layer,width) / ('via',x,y); neck width near endpoints."""
    neck=min(w,0.25)
    pts=[(gf(x),gf(y),l) for x,y,l in path]
    def wat(x,y):
        n=(abs(x-p1[0])<1.0 and abs(y-p1[1])<1.0) or (abs(x-p2[0])<1.0 and abs(y-p2[1])<1.0)
        return neck if n else w
    out=[]; i=0
    while i<len(pts)-1:
        if pts[i][2]!=pts[i+1][2]:
            out.append(('via',pts[i][0],pts[i][1])); i+=1; continue
        j=i+1
        dx=pts[j][0]-pts[i][0]; dy=pts[j][1]-pts[i][1]
        ww=max(wat(*pts[i][:2]),wat(*pts[j][:2]))
        while (j+1<len(pts) and pts[j+1][2]==pts[i][2]
               and (pts[j+1][0]-pts[j][0],pts[j+1][1]-pts[j][1])==(dx,dy)
               and wat(*pts[j+1][:2])==ww):
            j+=1
        out.append(('seg',pts[i][0],pts[i][1],pts[j][0],pts[j][1],pts[i][2],ww))
        i=j
    return out

# --------------------------------------------------------------------- main
def parse_existing(obs, inv):
    s=open(BOARD).read()
    for m in re.finditer(r'\(segment\s+\(start (-?[\d.]+) (-?[\d.]+)\)\s+\(end (-?[\d.]+) (-?[\d.]+)\)\s+\(width ([\d.]+)\)\s*(?:\(locked[^)]*\)\s*)?\(layer "([FB])\.Cu"\)\s+\(net "?([^")]+)"?\)', s):
        x1,y1,x2,y2,w,l,n=m.groups()
        net = inv.get(int(n),'?') if n.isdigit() else n
        obs.add_track(l,float(x1),float(y1),float(x2),float(y2),float(w)/2,net)
    for m in re.finditer(r'\(via \(at (-?[\d.]+) (-?[\d.]+)\)[^)]*\(net (\d+)\)\)', s):
        pass
    for m in re.finditer(r'\(via\s+\(at (-?[\d.]+) (-?[\d.]+)\)\s+\(size [\d.]+\)\s+\(drill [\d.]+\)\s+\(layers "F\.Cu" "B\.Cu"\)\s*(?:\(locked[^)]*\)\s*)?\(net "?([^")]+)"?\)', s):
        x,y,n=m.groups()
        obs.add_via(float(x),float(y),inv.get(int(n),'?') if n.isdigit() else n)

def emit_path(obs,codes,emitted,net,w,p1,p2,path):
    prims=compress(path,p1,p2,w)
    fx,fy=gf(path[0][0]),gf(path[0][1]); lx,ly=gf(path[-1][0]),gf(path[-1][1])
    neck=min(w,0.25)
    full=[('seg',p1[0],p1[1],fx,fy,'F',neck)] + prims + [('seg',lx,ly,p2[0],p2[1],'F',neck)]
    for pr in full:
        if pr[0]=='seg':
            _,x1,y1,x2,y2,l,ww=pr
            if (x1,y1)==(x2,y2): continue
            obs.add_track(l,x1,y1,x2,y2,ww/2,net)
            layer='F.Cu' if l=='F' else 'B.Cu'
            emitted.append(f'  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) (width {ww}) (layer "{layer}") (net {codes[net]}))')
        else:
            x,y=pr[1],pr[2]
            obs.add_via(x,y,net)
            emitted.append(f'  (via (at {x:.3f} {y:.3f}) (size {VIA_SIZE}) (drill {VIA_DRILL}) (layers "F.Cu" "B.Cu") (net {codes[net]}))')

ESCAPE_LEN=1.0
def build_escapes(pads,obs,codes,emitted):
    from collections import defaultdict
    byfp=defaultdict(list)
    for i,p in enumerate(pads): byfp[p[6]].append(i)
    retarget={}
    for fp,idxs in byfp.items():
        if len(idxs)<4: continue
        cx=sum(pads[i][1] for i in idxs)/len(idxs); cy=sum(pads[i][2] for i in idxs)/len(idxs)
        for i in idxs:
            n,x,y,hx,hy,pl,_=pads[i]
            if not n or n=='GND' or pl=='B': continue
            dmin=min(math.hypot(x-pads[j][1],y-pads[j][2]) for j in idxs if j!=i)
            if dmin>=0.8: continue
            dx,dy=x-cx,y-cy
            if abs(dx)>abs(dy): dirs=[((1 if dx>0 else -1),0),(0,(1 if dy>=0 else -1))]
            else: dirs=[(0,(1 if dy>0 else -1)),((1 if dx>=0 else -1),0)]
            # skip if a same-net track already originates at this pad (stub exists)
            if any(n==tn and ((abs(x-x1)<0.05 and abs(y-y1)<0.05) or (abs(x-x2)<0.05 and abs(y-y2)<0.05))
                   for x1,y1,x2,y2,hw,tn in obs.tracks['F']):
                continue
            for ex,ey in dirs:
                tx,ty=x+ex*ESCAPE_LEN,y+ey*ESCAPE_LEN
                ok=all(not obs.blocked(n,0.2,'F',x+ex*ESCAPE_LEN*k/4.0,y+ey*ESCAPE_LEN*k/4.0,frozenset({i}))
                       for k in range(1,5))
                if ok:
                    obs.add_track('F',x,y,tx,ty,0.1,n)
                    emitted.append(f'  (segment (start {x:.3f} {y:.3f}) (end {tx:.3f} {ty:.3f}) (width 0.2) (layer "F.Cu") (net {codes[n]}))')
                    retarget[(round(x,2),round(y,2))]=(tx,ty)
                    break
    return retarget

def main():
    pads=parse_pads(); codes=net_codes()
    inv={v:k for k,v in codes.items()}
    edges,viol,_=ratsnest()
    edges=[e for e in edges if e[0]!='GND']
    if not edges:
        print("nothing to route"); return 0
    order=sorted(edges,key=lambda e:(-WIDTH.get(e[0],DEF_W),
                 abs(e[1][0]-e[2][0])+abs(e[1][1]-e[2][1])))
    obs=Obstacles(pads); parse_existing(obs,inv)
    emitted=[]; failed=[]
    retarget=build_escapes(pads,obs,codes,emitted)
    def rt(p): return retarget.get((round(p[0],2),round(p[1],2)),p)
    order=[(n,rt(a),rt(b)) for n,a,b in order]
    for net,p1,p2 in order:
        w=WIDTH.get(net,DEF_W)
        globals()['LIMIT_MULT']=1
        path=route_edge(obs,net,w,p1,p2)
        if path: emit_path(obs,codes,emitted,net,w,p1,p2,path); print(f"  routed {net}")
        else: failed.append((net,p1,p2))
    retry, failed = failed, []
    for net,p1,p2 in retry:
        w=WIDTH.get(net,DEF_W)
        globals()['LIMIT_MULT']=8
        path=route_edge(obs,net,w,p1,p2)
        if not path and w>DEF_W:
            path=route_edge(obs,net,0.6,p1,p2)
            if path: w=0.6
        if not path:
            globals()['LIMIT_MULT']=12
            path=route_edge(obs,net,min(w,0.4),p1,p2)
            if path: w=min(w,0.4)
        if path: emit_path(obs,codes,emitted,net,w,p1,p2,path); print(f"  routed(retry) {net} w={w}")
        else: failed.append((net,p1,p2)); print(f"  FAILED {net} {p1}->{p2}")
    print(f"\nrouted {len(order)-len(failed)}/{len(order)}; failed: {sorted(set(f[0] for f in failed))}")
    s=open(BOARD).read()
    s=s[:s.rstrip().rfind(')')]+'\n'+'\n'.join(emitted)+'\n)\n'
    open(BOARD,'w').write(s)
    return len(failed)

if __name__=='__main__':
    sys.exit(0 if main()==0 else 2)
