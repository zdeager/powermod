#!/usr/bin/env python3
"""Resolve courtyard overlaps by relaxation, then rewrite FLOORPLAN in place.

Hand-nudging a 71-component floorplan is whack-a-mole: every fix creates a new
collision. This pushes overlapping courtyards apart iteratively while a weak
spring pulls each part back toward the position the human floorplan intended,
so functional grouping survives and only the collisions dissolve.

Constraints honoured:
  - PINNED refs never move (connectors and human-facing parts belong on their
    edge; relaxation must not drift them inboard).
  - Everything stays inside the board outline, with a margin.
  - Nothing enters a mounting-hole keepout.

Rotation is preserved throughout; only translation is relaxed.
"""
import os, re, sys, math, subprocess
sys.path.insert(0, os.path.dirname(__file__) or '.')
import place_check
import layout_v2 as L

GAP     = 0.15     # extra breathing room beyond touching courtyards (mm)
EDGE    = 0.35     # keep courtyards this far inside the outline (mm)
HOLE_R  = 3.05     # mounting-hole keepout radius from centre (mm)
SPRING  = 0.02     # pull back toward the intended position each iteration
ITERS   = 4000

# Connectors and human-facing parts are placed against edges on purpose.
# J5 (UPDI) is deliberately NOT pinned: it is a programming header, so it only
# needs to be reachable, not edge-mounted, and letting it float gives the
# charger cluster the room it actually needs.
PINNED = {'J1','J2','J3','J4','SW1','TP1','TP2','TP3','TP4','TP5','TP6'}

def geometry(board):
    """-> {ref: (hx, hy, ox, oy)} courtyard half-extents and centre offset
    relative to the footprint's placement origin (they differ for many parts)."""
    cy = place_check.courtyards(board)
    out = {}
    for ref,(x1,y1,x2,y2) in cy.items():
        if ref not in L.FLOORPLAN: continue          # mounting holes
        px,py,_ = L.FLOORPLAN[ref]
        out[ref] = ((x2-x1)/2, (y2-y1)/2, (x1+x2)/2 - px, (y1+y2)/2 - py)
    return out

def relax(geo):
    pos  = {r:[float(L.FLOORPLAN[r][0]), float(L.FLOORPLAN[r][1])] for r in geo}
    goal = {r:tuple(pos[r]) for r in geo}
    refs = sorted(geo)
    for _ in range(ITERS):
        moved = False
        # pairwise separation
        for i,a in enumerate(refs):
            ahx,ahy,aox,aoy = geo[a]
            acx,acy = pos[a][0]+aox, pos[a][1]+aoy
            for b in refs[i+1:]:
                bhx,bhy,box_,boy = geo[b]
                bcx,bcy = pos[b][0]+box_, pos[b][1]+boy
                ox = (ahx+bhx+GAP) - abs(acx-bcx)
                oy = (ahy+bhy+GAP) - abs(acy-bcy)
                if ox <= 0 or oy <= 0: continue
                moved = True
                # push along the axis of least penetration
                if ox < oy:
                    d = ox/2 if acx <= bcx else -ox/2
                    if a in PINNED and b in PINNED: continue
                    if a in PINNED:   pos[b][0] += 2*d
                    elif b in PINNED: pos[a][0] -= 2*d
                    else: pos[a][0] -= d; pos[b][0] += d
                else:
                    d = oy/2 if acy <= bcy else -oy/2
                    if a in PINNED and b in PINNED: continue
                    if a in PINNED:   pos[b][1] += 2*d
                    elif b in PINNED: pos[a][1] -= 2*d
                    else: pos[a][1] -= d; pos[b][1] += d
        # holes, edges, spring
        for r in refs:
            if r in PINNED: continue
            hx,hy,ox_,oy_ = geo[r]
            cx,cy = pos[r][0]+ox_, pos[r][1]+oy_
            for hxc,hyc in L.HOLES:
                dx,dy = cx-hxc, cy-hyc
                need = HOLE_R + max(hx,hy)*0.0        # bbox vs circle: use overlap test
                # rectangle-vs-circle: closest point on rect to hole centre
                px = max(cx-hx, min(hxc, cx+hx)); py = max(cy-hy, min(hyc, cy+hy))
                dist = math.hypot(px-hxc, py-hyc)
                if dist < HOLE_R:
                    ang = math.atan2(cy-hyc, cx-hxc) or 0.0
                    push = (HOLE_R - dist)
                    pos[r][0] += math.cos(ang)*push; pos[r][1] += math.sin(ang)*push
                    moved = True
            cx,cy = pos[r][0]+ox_, pos[r][1]+oy_
            if cx-hx < EDGE:            pos[r][0] += EDGE-(cx-hx); moved=True
            if cx+hx > L.BOARD_W-EDGE:  pos[r][0] -= (cx+hx)-(L.BOARD_W-EDGE); moved=True
            if cy-hy < EDGE:            pos[r][1] += EDGE-(cy-hy); moved=True
            if cy+hy > L.BOARD_H-EDGE:  pos[r][1] -= (cy+hy)-(L.BOARD_H-EDGE); moved=True
            gx,gy = goal[r]
            pos[r][0] += (gx-pos[r][0])*SPRING; pos[r][1] += (gy-pos[r][1])*SPRING
        if not moved: break
    return pos

def rewrite(pos, path):
    s = open(path).read()
    for ref,(x,y) in sorted(pos.items()):
        rot = L.FLOORPLAN[ref][2]
        s = re.sub(r"'%s': \(-?[\d.]+, -?[\d.]+, -?[\d.]+\)" % re.escape(ref),
                   "'%s': (%.2f, %.2f, %s)" % (ref, x, y, rot), s, count=1)
    open(path,'w').write(s)

if __name__=='__main__':
    board = 'powermod_v2.kicad_pcb'
    geo = geometry(board)
    pos = relax(geo)
    moves = sorted(((math.hypot(pos[r][0]-L.FLOORPLAN[r][0], pos[r][1]-L.FLOORPLAN[r][1]), r)
                    for r in pos), reverse=True)
    print("largest moves:", ", ".join(f"{r}{d:.1f}mm" for d,r in moves[:6]))
    rewrite(pos, os.path.join(os.path.dirname(__file__) or '.', 'layout_v2.py'))
    print("FLOORPLAN rewritten")
