#!/usr/bin/env python3
"""Tie the F/B ground pours to the In1 ground plane with a stitching via grid.

    python3 stitch_gnd.py powermod_v2.kicad_pcb

On a 4-layer board this is the easy version of the problem that dominated v1:
In1 is a solid plane, so ANY legal via location ties the outer pours to it and
to each other. No island archaeology, no hunting for the one legal spot next to
a stranded pad — just sweep a grid and keep every via that is legal on both
outer layers.

Legality reuses router.py's obstacle model (pads, tracks, vias, board edge) and
guards mounting holes and PTH pads by hole-to-hole distance.
"""
import os, re, sys, math, subprocess
sys.path.insert(0, os.path.dirname(__file__) or '.')
import router as R

PITCH   = 2.5     # via grid pitch (mm)
HOLE_KO = 1.35    # keep this far from any drilled hole centre (mm)

def board_size(path):
    """Read the outline from Edge.Cuts. router.py hard-codes BW/BH, which went
    stale two board sizes ago; edge legality must follow the actual outline."""
    s = open(path).read()
    xs, ys = [], []
    for tag in ('(gr_line', '(gr_rect', '(gr_arc', '(gr_poly'):
        k = 0
        while True:
            f = s.find(tag, k)
            if f < 0: break
            e = R.matching(s, f); blk = s[f:e]; k = e
            if 'Edge.Cuts' not in blk: continue
            for m in re.finditer(r'\((?:start|end|mid|xy) (-?[\d.]+) (-?[\d.]+)\)', blk):
                xs.append(float(m.group(1))); ys.append(float(m.group(2)))
    return max(xs), max(ys)

def main(board):
    R.BOARD = board
    R.BW, R.BH = board_size(board)
    print(f"board outline: {R.BW} x {R.BH} mm")
    pads  = R.parse_pads()
    codes = R.net_codes()
    inv   = {v: k for k, v in codes.items() if isinstance(v, int)}
    obs   = R.Obstacles(pads)
    R.parse_existing(obs, inv)

    holes = [(p[1], p[2]) for p in pads if p[5] == 'BOTH']
    s = open(board).read()
    for m in re.finditer(r'\(pad "" np_thru_hole[^)]*\)\s*\(at (-?[\d.]+) (-?[\d.]+)', s):
        holes.append((float(m.group(1)), float(m.group(2))))
    # mounting holes come through as footprints; catch them by drill presence
    for m in re.finditer(r'\(footprint "MountingHole[^"]*"[\s\S]{0,400}?\(at (-?[\d.]+) (-?[\d.]+)', s):
        holes.append((float(m.group(1)), float(m.group(2))))

    # router.py's obstacle model only knows F/B — it was written for a 2-layer
    # board. A through via also passes In2, where signals now route, so parse
    # those separately or the grid drills straight through them.
    inner = []
    k = 0
    while True:
        f = s.find('(segment', k)
        if f < 0: break
        e = R.matching(s, f); blk = s[f:e]; k = e
        if '(layer "In2.Cu")' not in blk: continue
        st = re.search(r'\(start (-?[\d.]+) (-?[\d.]+)\)', blk)
        en = re.search(r'\(end (-?[\d.]+) (-?[\d.]+)\)', blk)
        wd = re.search(r'\(width ([\d.]+)\)', blk)
        nt = re.search(r'\(net "([^"]+)"\)', blk)
        if st and en and wd:
            inner.append((float(st.group(1)), float(st.group(2)),
                          float(en.group(1)), float(en.group(2)),
                          float(wd.group(1))/2, nt.group(1) if nt else ''))
    print(f"In2 traces to avoid: {len(inner)}")

    def in2_clear(x, y):
        r = R.VIA_SIZE/2 + R.CLEAR
        for x1, y1, x2, y2, hw, net in inner:
            if net == 'GND': continue
            if R.seg_dist(x, y, x1, y1, x2, y2) < hw + r: return False
        return True

    em = []
    y = PITCH
    while y < R.BH - PITCH:
        x = PITCH
        while x < R.BW - PITCH:
            if (not obs.blocked('GND', R.VIA_SIZE, 'F', x, y, frozenset())
                    and not obs.blocked('GND', R.VIA_SIZE, 'B', x, y, frozenset())
                    and in2_clear(x, y)
                    and not any(math.hypot(x-hx, y-hy) < HOLE_KO for hx, hy in holes)):
                em.append(f'  (via (at {x:.2f} {y:.2f}) (size {R.VIA_SIZE}) (drill {R.VIA_DRILL}) '
                          f'(layers "F.Cu" "B.Cu") (net {codes["GND"]}))')
                obs.add_via(x, y, 'GND')
            x += PITCH
        y += PITCH
    if em:
        txt = open(board).read()
        open(board, 'w').write(txt[:txt.rstrip().rfind(')')] + '\n' + '\n'.join(em) + '\n)\n')
    print(f"placed {len(em)} GND stitching vias at {PITCH}mm pitch")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'powermod_v2.kicad_pcb')
