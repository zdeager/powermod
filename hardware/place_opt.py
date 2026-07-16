#!/usr/bin/env python3
"""Net-aware placement optimiser: pull net-mates together, push courtyards apart.

    python3 place_opt.py [iterations]

place_relax.py only resolves overlaps — it keeps the hand floorplan's geometry.
But the hand floorplan grouped parts by FUNCTION NAME rather than by what they
are wired to, which is what actually limits routing: CHG_CE ran 30mm across the
board, VOUT's members were strewn from x=24 to x=53, and the router plateaued at
~10 unrouted no matter how many layers or how thin the traces got.

So: springs between components that share a net (weighted 1/fanout, so a 2-pin
net pulls hard and GND does not dominate), repulsion between overlapping
courtyards, and the same pinning/edge/hole constraints as place_relax. This is a
crude force-directed placer, but "crude and net-aware" beats "tidy and blind".

GND and the power planes are excluded from the springs: GND has 55 pads and would
collapse the board into a ball, and the plane rails do not need short traces.
"""
import os, re, sys, math
sys.path.insert(0, os.path.dirname(__file__) or '.')
import place_check
import layout_v2 as L
from netlist import COMPONENTS, build_nets

GAP     = 0.15
EDGE    = 0.35
HOLE_R  = 3.05
ATTRACT = 0.010     # spring gain toward net-mates
REPEL   = 1.0       # overlap resolution is absolute (must not be violated)
HOME    = 0.004     # weak memory of the intended floorplan
PINNED  = {'J1','J2','J3','J4','SW1','TP1','TP2','TP3','TP4','TP5','TP6'}
# Nets that ride planes/pours, or are too fat to be meaningful springs.
SKIP_NETS = {'GND','VBUS','VSYS','VOUT','NC'}

def net_edges():
    """-> [(refA, refB, weight)] over components sharing a net."""
    nets = build_nets()          # {net: [(ref, pin), ...]}
    out = []
    for net, pins in nets.items():
        if net in SKIP_NETS: continue
        refs = sorted({ref for ref, _pin in pins if ref in L.FLOORPLAN})
        if len(refs) < 2 or len(refs) > 8: continue
        w = 1.0/(len(refs)-1)
        for i, a in enumerate(refs):
            for b in refs[i+1:]:
                out.append((a, b, w))
    return out

def main(iters=1500):
    board = 'powermod_v2.kicad_pcb'
    cy = place_check.courtyards(board)
    geo = {}
    for ref,(x1,y1,x2,y2) in cy.items():
        if ref not in L.FLOORPLAN: continue
        px,py,_ = L.FLOORPLAN[ref]
        geo[ref] = ((x2-x1)/2, (y2-y1)/2, (x1+x2)/2-px, (y1+y2)/2-py)
    edges = [(a,b,w) for a,b,w in net_edges() if a in geo and b in geo]
    print(f"{len(geo)} placeable parts, {len(edges)} net springs")

    pos  = {r:[float(L.FLOORPLAN[r][0]), float(L.FLOORPLAN[r][1])] for r in geo}
    home = {r:tuple(pos[r]) for r in geo}
    refs = sorted(geo)

    for it in range(iters):
        # attraction along nets
        for a,b,w in edges:
            ax,ay = pos[a]; bx,by = pos[b]
            dx,dy = bx-ax, by-ay
            d = math.hypot(dx,dy)
            if d < 0.01: continue
            f = ATTRACT*w*min(d, 12.0)
            ux,uy = dx/d, dy/d
            if a not in PINNED: pos[a][0] += ux*f; pos[a][1] += uy*f
            if b not in PINNED: pos[b][0] -= ux*f; pos[b][1] -= uy*f
        # repulsion (hard): resolve every courtyard overlap
        for _ in range(3):
            for i,a in enumerate(refs):
                ahx,ahy,aox,aoy = geo[a]
                acx,acy = pos[a][0]+aox, pos[a][1]+aoy
                for b in refs[i+1:]:
                    bhx,bhy,box_,boy = geo[b]
                    bcx,bcy = pos[b][0]+box_, pos[b][1]+boy
                    ox = (ahx+bhx+GAP) - abs(acx-bcx)
                    oy = (ahy+bhy+GAP) - abs(acy-bcy)
                    if ox <= 0 or oy <= 0: continue
                    if a in PINNED and b in PINNED: continue
                    if ox < oy:
                        d = ox/2 if acx <= bcx else -ox/2
                        if a in PINNED:   pos[b][0] += 2*d*REPEL
                        elif b in PINNED: pos[a][0] -= 2*d*REPEL
                        else: pos[a][0] -= d*REPEL; pos[b][0] += d*REPEL
                    else:
                        d = oy/2 if acy <= bcy else -oy/2
                        if a in PINNED:   pos[b][1] += 2*d*REPEL
                        elif b in PINNED: pos[a][1] -= 2*d*REPEL
                        else: pos[a][1] -= d*REPEL; pos[b][1] += d*REPEL
                    acx,acy = pos[a][0]+aox, pos[a][1]+aoy
        # holes, edges, home
        for r in refs:
            if r in PINNED: continue
            hx,hy,ox_,oy_ = geo[r]
            cx,cy = pos[r][0]+ox_, pos[r][1]+oy_
            for hxc,hyc in L.HOLES:
                px_ = max(cx-hx, min(hxc, cx+hx)); py_ = max(cy-hy, min(hyc, cy+hy))
                dist = math.hypot(px_-hxc, py_-hyc)
                if dist < HOLE_R:
                    ang = math.atan2(cy-hyc, cx-hxc) if (cy!=hyc or cx!=hxc) else 0.0
                    push = HOLE_R-dist
                    pos[r][0] += math.cos(ang)*push; pos[r][1] += math.sin(ang)*push
            cx,cy = pos[r][0]+ox_, pos[r][1]+oy_
            if cx-hx < EDGE:           pos[r][0] += EDGE-(cx-hx)
            if cx+hx > L.BOARD_W-EDGE: pos[r][0] -= (cx+hx)-(L.BOARD_W-EDGE)
            if cy-hy < EDGE:           pos[r][1] += EDGE-(cy-hy)
            if cy+hy > L.BOARD_H-EDGE: pos[r][1] -= (cy+hy)-(L.BOARD_H-EDGE)
            gx,gy = home[r]
            pos[r][0] += (gx-pos[r][0])*HOME; pos[r][1] += (gy-pos[r][1])*HOME

    before = sum(math.hypot(home[a][0]-home[b][0], home[a][1]-home[b][1])*w for a,b,w in edges)
    after  = sum(math.hypot(pos[a][0]-pos[b][0], pos[a][1]-pos[b][1])*w for a,b,w in edges)
    print(f"weighted net length: {before:.0f} -> {after:.0f} mm ({(after-before)/before*100:+.0f}%)")

    s = open('layout_v2.py').read()
    for ref,(x,y) in sorted(pos.items()):
        rot = L.FLOORPLAN[ref][2]
        s = re.sub(r"'%s': \(-?[\d.]+, -?[\d.]+, -?[\d.]+\)" % re.escape(ref),
                   "'%s': (%.2f, %.2f, %s)" % (ref, x, y, rot), s, count=1)
    open('layout_v2.py','w').write(s)
    print("FLOORPLAN rewritten")

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1500)
