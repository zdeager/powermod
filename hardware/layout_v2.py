#!/usr/bin/env python3
"""PowerMOD v2 layout generator — Raspberry Pi Zero form factor, 4 layers.

Same electrical design as v1: reads connectivity from netlist.py, which is
untouched. Only the geometry changes, so ERC and the BOM carry over verified.

v2 vs v1 (hardware/layout.py, 58x40mm 2-layer):
  - 65 x 30mm, the Pi Zero outline, with the Pi's own M2.5 mounting-hole grid
    (58 x 23mm, 3.5mm in from each corner) so the board stacks on the same
    standoffs as the host.
  - 4 layers: F.Cu signal / In1.Cu solid GND plane / In2.Cu signal+power / B.Cu
    signal. The inner GND plane is the point of the exercise. v1's entire
    endgame was fighting a 2-layer pour that signal traces kept carving into
    isolated islands; with a dedicated plane, any GND pad connects with one via
    and the island/stitching failure mode structurally cannot occur.
  - Trace widths are ENFORCED via net classes (netclasses.py). v1 silently
    routed 3A rails at 0.2mm and passed DRC clean, because with no net class
    defined there was no width rule to check. v2 does not repeat that.

Layer policy: In1 is the GND plane and carries no tracks (a full-board rule area
forbids them; vias and pour still allowed). In2 is left free for routing —
splitting it into power planes was tried and abandoned because the power nets'
pads are geographically interleaved under this placement, so no clean partition
exists that doesn't strand pads. The high-current rails instead get 1.1mm traces
per netclass, and the router gets a third layer, which is what a 65x30 board at
this density actually needs.

Floorplan intent: power flows left to right, J1 (USB-C in) on the west short
edge -> charger/OR -> VSYS -> converter (tight L1 loop) -> VOUT -> J2 (USB-C
out) on the east short edge. Human-facing parts (LEDs, button, jumpers, test
pads) and the remaining connectors live on the long edges. Crystal sits far
from the converter's switching loop.

NOT done here: signal routing (Freerouting, via fr_pipeline.py). Build the whole
thing with ./build_v2.sh.

STATUS (2026-07-16): placement clean (0 courtyard overlaps, verified against
KiCad's own DRC), routing ~91% — 10 of 117 nets fail. NOT yet fab-ready. What the
failed experiments rule out, so they are not repeated:

  * Layers/area are NOT the constraint. v1 (2-layer, 58x40, 2320mm2) leaves 12
    unrouted at full width; v2 (4-layer, 65x30, 1950mm2) leaves 10-13. Nearly
    identical — the extra copper layers just offset the 16% smaller board.
  * Trace width is NOT the constraint. 1.1mm rails -> 10 unrouted; 0.6mm escapes
    into power planes -> also 10.
  * In2 as power planes vs free routing: no material difference (11 vs 10), and
    the planes add dangling vias, because Freerouting still routes signals across
    a plane sitting on a signal-typed layer.
  * Shorter nets are NOT better. A force-directed pass (place_opt.py) cut
    weighted net length 24% and made routing WORSE (17 unrouted): it clustered
    parts and closed the routing channels. Congestion, not length, is the
    objective that matters here.

The remaining failures are all long hauls whose members this floorplan scatters
(CHG_CE spans 30mm; VOUT's members run x 24..53). The next honest lever is a
floorplan designed around routing channels and power-domain geography — a human
judgement call, not another optimiser pass.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__) or '.')
from netlist import COMPONENTS, build_nets

KISHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
BOARD_W, BOARD_H = 65.0, 30.0        # Raspberry Pi Zero outline

# Pi Zero mounting holes: 3.5mm in from each corner -> 58 x 23mm grid, M2.5.
HOLE_INSET = 3.5
HOLES = [(HOLE_INSET, HOLE_INSET), (BOARD_W-HOLE_INSET, HOLE_INSET),
         (HOLE_INSET, BOARD_H-HOLE_INSET), (BOARD_W-HOLE_INSET, BOARD_H-HOLE_INSET)]
HOLE_FP = 'MountingHole:MountingHole_2.7mm_M2.5'

# ref: (x, y, rot) — origin top-left, y down. Iterated under place_check.py.
#
# Geometry that drives everything: rotated, each USB-C receptacle is 9.4 wide x
# 10.6 tall and sits centred on its short edge (J1 x 0.7..10.1, J2 x 54.9..64.3,
# both y 9.7..20.3). The four M2.5 holes claim ~5.5mm circles at the corners.
# What is left is a centre block x 10.2..54.9 plus north/south strips at the
# ends — so the north strip (y 0..6) and south strip (y 24..30) carry the small
# passives and human-facing parts, and the middle band carries the power chain.
FLOORPLAN = {
 # --- west short edge: USB-C input
 'J1': (5.40, 15.00, -90),
 # --- north strip: dividers, OR biasing, UPDI, host header, button, LEDs
 'R2': (8.00, 1.40, 0), 'R3': (8.00, 3.00, 0),              # CC pulldowns for J1
 'R8': (11.00, 1.40, 0), 'R9': (11.00, 3.00, 0), 'C11': (11.00, 4.60, 0),
 'C12': (14.00, 1.40, 0), 'R10': (14.00, 3.00, 0), 'R13': (14.00, 4.60, 0),
 'R11': (16.50, 0.87, 0),
 'J5': (18.46, 3.26, 0),                                  # UPDI header
 'R24': (24.00, 1.40, 0), 'R25': (24.00, 3.00, 0), 'R26': (24.00, 4.60, 0),
 'JP2': (27.00, 2.00, 0),
 'J4': (33.00, 3.50, 0),                                  # STEMMA QT / host I2C
 'SW1': (42.00, 3.20, 0),
 'D1': (49.00, 2.00, 0), 'D2': (55.00, 2.00, 0),
 'R20': (46.73, 5.20, 0), 'R21': (48.74, 5.20, 0),
 'R22': (53.00, 5.20, 0), 'R23': (55.00, 5.20, 0),
 # --- input / charger cluster (east of J1)
 'C7': (11.32, 6.60, 0), 'C15': (14.08, 6.06, 0), 'R12': (15.62, 7.14, 0),
 'U4': (15.16, 12.96, 0),                                 # TP4056
 'C6': (12.30, 16.54, 0), 'R1': (14.86, 16.50, 0),
 'JP1': (17.59, 17.07, 0), 'R27': (19.86, 16.75, 90),
 # --- power-OR block
 'Q1': (23.50, 11.00, 0), 'Q2': (22.61, 15.50, 0), 'Q3': (22.00, 20.00, 0),
 'R14': (26.00, 20.00, 90),
 # --- converter: tight L1 loop, board centre
 'U3': (33.00, 12.00, 0), 'L1': (33.00, 19.55, 0),
 'C16': (29.50, 7.90, 90), 'C1': (29.50, 10.66, 90), 'C2': (29.50, 14.20, 90),
 'C3': (36.50, 9.98, 90), 'C4': (36.45, 13.52, 90), 'C5': (38.55, 16.50, 90),
 # --- LDO + 3V3
 'U5': (41.50, 10.04, 0), 'C8': (39.72, 12.62, 0), 'C9': (42.83, 12.62, 0),
 # --- MCU
 'U2': (47.06, 12.50, 0), 'C14': (42.00, 7.73, 0),
 'R15': (50.50, 8.00, 90), 'R16': (52.20, 8.00, 90),
 # --- RTC + crystal: east end, far from the L1 loop
 'U1': (57.00, 10.00, 0), 'Y1': (57.00, 14.00, 0), 'C13': (61.50, 14.00, 90),
 'D3': (53.50, 16.48, 0), 'D4': (53.50, 18.52, 0),
 'R17': (56.00, 18.50, 90), 'R18': (57.70, 18.50, 90), 'R19': (59.40, 18.50, 90),
 # --- south strip: battery, test pads
 'J3': (15.60, 25.70, 180),                               # battery JST
 'R6': (18.67, 23.00, 90), 'R7': (20.00, 23.00, 90), 'C10': (22.00, 23.00, 90),
 'TP2': (19.60, 27.00, 0), 'TP4': (22.80, 27.00, 0),        # BAT+ / GND
 'TP3': (26.00, 27.00, 0), 'TP6': (29.50, 27.00, 0),        # VOUT / GND
 'TP1': (57.00, 24.50, 0), 'TP5': (60.50, 24.50, 0),        # VBACKUP / GND
 # --- east short edge: USB-C output
 'J2': (46.00, 24.50, 180),
 'R4': (53.00, 22.00, 0), 'R5': (53.00, 23.60, 0),          # CC pullups for J2
}

# ------------------------------------------------------------- s-expr helpers
def matching(s, i):
    """index just past the paren block starting at s[i]=='('."""
    d=0
    for k in range(i, len(s)):
        if s[k]=='(':d+=1
        elif s[k]==')':
            d-=1
            if d==0: return k+1
    raise ValueError("unbalanced")

def load_footprint(lib_name):
    lib, name = lib_name.split(':')
    return open(os.path.join(KISHARE, lib+'.pretty', name+'.kicad_mod')).read()

# --------------------------------------------------------------------- build
def pad_net_map():
    nets = build_nets()
    named = sorted(n for n in nets if n != 'NC')
    codes = {n: i+1 for i, n in enumerate(named)}
    m = {}
    for ref,(val,fp,lcsc,pins) in COMPONENTS.items():
        m[ref] = {p:(codes[net],net) for p,(pn,net) in pins.items() if net!='NC'}
    return m, codes

def place_footprint(src, ref, val, x, y, rot, padnets):
    s = src
    i = s.find('(layer'); j = matching(s, i)
    s = s[:j] + f'\n  (at {x} {y} {rot})' + s[j:]
    def fix_pad(block):
        am = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)( (-?[\d.]+))?\)', block)
        if am:
            pa = float(am.group(4) or 0) + rot
            block = block.replace(am.group(0), f'(at {am.group(1)} {am.group(2)} {pa})', 1)
        return block
    s = re.sub(r'\(property "Reference" "[^"]*"', f'(property "Reference" "{ref}"', s, 1)
    s = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{val}"', s, 1)
    out=[]; k=0
    while True:
        p = s.find('(pad "', k)
        if p < 0:
            out.append(s[k:]); break
        e = matching(s, p)
        block = fix_pad(s[p:e])
        num = re.match(r'\(pad "([^"]*)"', block).group(1)
        if num in padnets:
            code, name = padnets[num]
            block = block[:-1] + f' (net {code} "{name}")' + ')'
        out.append(s[k:p]); out.append(block); k=e
    return ''.join(out)

def gen_pcb(path):
    padmap, codes = pad_net_map()
    W,H = BOARD_W, BOARD_H
    body=[]
    body.append('(kicad_pcb (version 20221018) (generator powermod_layout_v2_py)')
    body.append(' (general (thickness 1.6))')
    body.append(' (paper "A4")')
    # 4-layer stackup: signal / GND plane / signal+power / signal.
    # In2 MUST be declared "signal": a layer typed "power" exports to DSN as
    # (type power), which Freerouting treats as a plane and refuses to route on
    # — silently turning this into a 2-layer problem on a smaller board.
    body.append(' (layers (0 "F.Cu" signal) (1 "In1.Cu" power) (2 "In2.Cu" signal) (31 "B.Cu" signal)'
                ' (32 "B.Adhes" user) (33 "F.Adhes" user) (34 "B.Paste" user) (35 "F.Paste" user)'
                ' (36 "B.SilkS" user) (37 "F.SilkS" user) (38 "B.Mask" user) (39 "F.Mask" user)'
                ' (40 "Dwgs.User" user) (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user)'
                ' (48 "B.Fab" user) (49 "F.Fab" user))')
    body.append(' (setup (pad_to_mask_clearance 0.05))')
    body.append(' (net 0 "")')
    for name, code in sorted(codes.items(), key=lambda kv: kv[1]):
        body.append(f' (net {code} "{name}")')
    for ref,(x,y,rot) in FLOORPLAN.items():
        val, fp, lcsc, pins = COMPONENTS[ref]
        body.append(place_footprint(load_footprint(fp), ref, val, x, y, rot, padmap.get(ref,{})))
    mh = load_footprint(HOLE_FP)
    for n,(x,y) in enumerate(HOLES,1):
        body.append(place_footprint(mh, f'H{n}', 'M2.5', x, y, 0, {}))
    for (x1,y1,x2,y2) in [(0,0,W,0),(W,0,W,H),(W,H,0,H),(0,H,0,0)]:
        body.append(f' (gr_line (start {x1} {y1}) (end {x2} {y2}) (layer "Edge.Cuts") (width 0.1))')
    poly = f'(polygon (pts (xy 0 0) (xy {W} 0) (xy {W} {H}) (xy 0 {H})))'
    # In1 = the solid GND plane, and nothing else. Every GND pad reaches it with
    # one via, which is the whole reason for going to four layers: v1's endgame
    # was signal traces carving a 2-layer pour into isolated islands, and a
    # dedicated plane makes that failure mode impossible.
    body.append(f''' (zone (net {codes['GND']}) (net_name "GND") (layer "In1.Cu") (hatch edge 0.5)
  (connect_pads (clearance 0.3)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
  {poly})''')
    # NO rule area on In1, deliberately. Declaring the layer "power" (above) is
    # already enough to stop Freerouting routing tracks on it — it treats a
    # power-type layer as a plane and never puts wires there.
    #
    # A full-board "no tracks, vias allowed" rule area here looks harmless and is
    # catastrophic: it exports to DSN such that Freerouting will not place a via
    # ANYWHERE on the board, because every through-via necessarily passes through
    # In1. The router then silently degrades to single-layer (zero vias, 100% of
    # wires on F.Cu) and leaves ~50 nets unrouted. Measured: 51 unrouted with the
    # rule area, 10 without it, same placement.
    # GND also pours on F/B. Not for current — In1 handles that — but because a
    # poured GND is absorbed by the pour instead of being handed to the router
    # as ~55 pads to connect. Dropping these pours took the routing problem from
    # 120 connections to 166 and made it materially worse. Any fragments here are
    # harmless: the real plane is In1, one via away.
    for layer in ('F.Cu','B.Cu'):
        body.append(f''' (zone (net {codes['GND']}) (net_name "GND") (layer "{layer}") (hatch edge 0.5)
  (connect_pads (clearance 0.3)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
  {poly})''')
    # In2 = power planes, partitioned along the power flow (west -> east).
    #
    # This only works in combination with THIN escapes (netclasses.py): the plane
    # is the conductor and carries the aggregate current, while each pad needs
    # only a short 0.6mm on-ramp into it. Planes with fat 1.1mm escapes was tried
    # and failed (11 unrouted) — the escapes still could not fan out of the USB-C
    # pads, so the planes bought nothing.
    #
    # The partition follows where each rail's pads actually cluster: VBUS around
    # J1/charger (pads x 9..25), VSYS across the OR/converter (x 13..42), VOUT
    # from the converter out to J2. A few outliers (JP2, TP3, C12) sit over a
    # neighbouring plane and simply route on F/B instead.
    for name,(x1,y1,x2,y2) in (('VBUS', (0,0,27,H)), ('VSYS', (27,0,42,H)), ('VOUT', (42,0,W,H))):
        body.append(f''' (zone (net {codes[name]}) (net_name "{name}") (layer "In2.Cu") (hatch edge 0.5)
  (connect_pads (clearance 0.3)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
  (polygon (pts (xy {x1} {y1}) (xy {x2} {y1}) (xy {x2} {y2}) (xy {x1} {y2}))))''')
    body.append(')')
    open(path,'w').write('\n'.join(body))

if __name__=='__main__':
    missing = set(COMPONENTS) - set(FLOORPLAN)
    if missing: print("NOT PLACED:", sorted(missing)); sys.exit(1)
    gen_pcb(os.path.join(os.path.dirname(__file__) or '.','powermod_v2.kicad_pcb'))
    print(f"OK: {len(FLOORPLAN)} components on {BOARD_W}x{BOARD_H}mm, 4 layers")
