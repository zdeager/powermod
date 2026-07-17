#!/usr/bin/env python3
"""Finish a freerouted board: import SES, stitch GND, tie floating pour islands, refill.

    <kicad-python> finish_board.py [board.kicad_pcb]

Run AFTER freerouting has produced <board>.ses. Steps, in order (order matters):

  1. ImportSpecctraSES        - needs a wx.App() to exist first, else returns False.
  2. stitch_gnd.main()        - the 2.5mm via grid tying F/B pours to the In1 plane.
  3. tie_islands()            - the step the grid misses; see below.
  4. ZONE_FILLER              - MANDATORY. DRC measures the fill stored in the file,
                               so a stale fill invents hundreds of phantom clearance
                               violations ("actual 0.0000 mm" is the tell).

Why tie_islands() exists: stranded GND pads (C9.2, U5.1, C4.2, R7.2 ...) are not a
routing failure. They sit on F.Cu pour islands that have no via down to the In1 GND
plane. Zones already default to island_removal_mode=ALWAYS, so any island that
survives the fill is one that *touches a GND pad* - i.e. exactly the stranded-pad
case. One via anywhere inside the island fixes it.

The subtlety that made earlier attempts fail: do NOT require the via pad *plus*
clearance to sit inside the fill. The fill polygon already respects clearance from
foreign copper, so that test is doubly conservative and rejects every thin sliver.
Require only the via pad (0.3mm r) inside the fill, and check foreign copper
separately against the real obstacle set.
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__) or '.', '..'))
import wx, pcbnew

VIA_SIZE, VIA_DRILL, CLEAR = 0.6, 0.3, 0.21
HOLE_KO = 1.35

FM = pcbnew.FromMM
def mm(v): return pcbnew.ToMM(v)


def tie_islands(b, verbose=True):
    """Drop one GND via into every floating F.Cu GND pour island. Returns count."""
    FCU, BCU, IN2 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu
    gnd = None
    for n in range(b.GetNetCount()):
        ni = b.GetNetInfo().GetNetItem(n)
        if ni.GetNetname() == 'GND':
            gnd = ni.GetNetCode(); break
    if gnd is None:
        return 0

    obst = [t for t in b.GetTracks() if t.GetNetCode() != gnd]
    padshapes = []
    for p in b.GetPads():
        if p.GetNetCode() == gnd:
            continue
        for L in (FCU, BCU, IN2):
            if p.IsOnLayer(L):
                try:
                    padshapes.append(p.GetEffectiveShape(L))  # needs an explicit layer
                except Exception:
                    pass
                break
    holes = [(mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in b.GetPads()
             if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)]
    for f in b.GetFootprints():
        if f.GetReference().startswith('H'):
            holes.append((mm(f.GetPosition().x), mm(f.GetPosition().y)))

    def legal(x, y):
        sh = pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(FM(x), FM(y)), FM(VIA_SIZE / 2))
        for t in obst:
            if t.GetEffectiveShape().Collide(sh, FM(CLEAR)):
                return False
        for ps in padshapes:
            if ps.Collide(sh, FM(CLEAR)):
                return False
        return not any(math.hypot(x - hx, y - hy) < HOLE_KO for hx, hy in holes)

    R = VIA_SIZE / 2
    ring = [(R * math.cos(k * math.pi / 6), R * math.sin(k * math.pi / 6)) for k in range(12)]
    placed = 0
    for z in b.Zones():
        if z.GetNetname() != 'GND' or not z.IsOnLayer(FCU):
            continue
        poly = z.GetFilledPolysList(FCU)
        for i in range(poly.OutlineCount()):
            vias = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']
            if any(poly.Contains(pcbnew.VECTOR2I(v.GetPosition().x, v.GetPosition().y), i) for v in vias):
                continue
            bb = poly.Outline(i).BBox()
            x0, y0 = mm(bb.GetLeft()), mm(bb.GetTop())
            x1, y1 = mm(bb.GetRight()), mm(bb.GetBottom())
            pads_in = [f"{p.GetParentFootprint().GetReference()}.{p.GetPadName()}"
                       for p in b.GetPads() if p.GetNetCode() == gnd
                       and poly.Contains(pcbnew.VECTOR2I(p.GetPosition().x, p.GetPosition().y), i)]
            best = None
            x = x0
            while x <= x1 and not best:
                y = y0
                while y <= y1:
                    # only the via pad need sit in the fill; the fill already clears foreign copper
                    if all(poly.Contains(pcbnew.VECTOR2I(FM(x + dx), FM(y + dy)), i) for dx, dy in ring) \
                            and legal(x, y):
                        best = (x, y); break
                    y += 0.05
                x += 0.05
            lbl = ",".join(pads_in) if pads_in else "(dead copper)"
            if best:
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(pcbnew.VECTOR2I(FM(best[0]), FM(best[1])))
                v.SetWidth(FM(VIA_SIZE)); v.SetDrill(FM(VIA_DRILL))
                v.SetLayerPair(FCU, BCU); v.SetNetCode(gnd)
                b.Add(v); placed += 1
                if verbose:
                    print(f"  island {i:2} [{lbl}]: via at ({best[0]:.2f},{best[1]:.2f})")
            elif verbose:
                print(f"  island {i:2} [{lbl}]: no legal via - needs a ~1mm nudge of that part")
    return placed


def main(board):
    app = wx.App()
    b = pcbnew.LoadBoard(board)
    stem = os.path.splitext(board)[0]

    ok = pcbnew.ImportSpecctraSES(b, stem + '.ses')
    print(f"SES import: {ok}")
    if not ok:
        sys.exit("SES import failed")
    pcbnew.SaveBoard(board, b)

    import stitch_gnd
    stitch_gnd.main(board)          # rewrites the file as text; reload after

    b = pcbnew.LoadBoard(board)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())   # islands are only discoverable once filled
    n = tie_islands(b)
    print(f"tied {n} floating GND islands")
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(board, b)

    tr = len([t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK'])
    vi = len([t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA'])
    print(f"done: {tr} tracks, {vi} vias")
    print("NOW RUN DRC WITH --refill-zones (without it you get phantom violations)")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'powermod.kicad_pcb')
