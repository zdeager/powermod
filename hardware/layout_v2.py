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
 # ============ WEST: input power (VBUS domain) ============
 # J1 centred on the west short edge; everything VBUS clusters beside it.
 'J1': (5.40, 15.00, -90),
 'R2': (11.80, 17.24, 0), 'R3': (11.80, 18.33, 0),   # CC Rd, at the port
 'C7': (11.52, 7.80, 0), 'C15': (14.28, 7.80, 0),    # VBUS bulk + HF
 'R12': (16.40, 7.80, 0),                            # VBUS bleed (Q2 gate release)
 'R8': (19.00, 8.00, 0), 'R9': (21.20, 8.00, 0),     # VBUS divider (cap C11 lives at the MCU)
 'U4': (15.40, 12.83, 0),                            # TP4056 charger
 'R1': (12.84, 16.15, 0),                            # PROG 1.2k = 1A
 'C6': (15.40, 17.00, 0),                            # BAT cap
 'R28': (17.96, 17.00, 0),                           # CE pull-up to VBUS
 # ============ OR stage: VBUS/VBAT -> VSYS ============
 'Q1': (21.50, 12.00, 180),                             # VBUS pass PFET
 'C12': (24.80, 10.22, 90), 'R10': (26.40, 10.40, 90),   # Q1 gate RC (soft start)
 'R11': (24.80, 12.21, 90), 'Q3': (26.03, 14.99, 0), 'R13': (24.80, 17.77, 90),
 'Q2': (21.50, 17.50, 180),                            # VBAT pass PFET (passive)
 # ============ CENTRE: buck-boost (VSYS -> VOUT) ============
 # U3 rotated 180 so VIN pins face the OR stage (west) and VOUT pins face J2 (east).
 'U3': (33.00, 14.49, 180),
 'C1': (29.09, 13.51, 90), 'C2': (29.09, 17.06, 90),  # input caps, VIN side
 'C3': (37.84, 11.79, 90), 'C4': (39.95, 12.22, 90), 'C5': (37.80, 15.34, 90),  # output caps
 'C16': (39.60, 14.98, 90),                          # VINA bypass (<=0.22uF rule)
 'L1': (32.61, 8.16, 0),                            # inductor, south of U3
 'R14': (30.20, 19.38, 0),                            # CONV_EN pulldown, at U3's EN
 'R24': (37.19, 18.80, 0), 'R25': (39.20, 18.74, 0), 'R26': (42.28, 18.80, 0), 'JP2': (46.10, 18.73, 0),
 # LDO hangs off VSYS south-west of the inductor; 3V3 runs east in the south channel
 'U5': (25.50, 21.41, 0), 'C8': (23.70, 23.99, 0), 'C9': (27.30, 23.99, 0),
 # ============ EAST-CENTRE: MCU hub ============
 'U2': (46.20, 11.50, 0), 'C14': (42.00, 12.60, 90),
 'C11': (39.67, 20.26, 90), 'C10': (40.74, 19.07, 90),   # ADC sampling caps AT the pins
 'R15': (43.83, 19.05, 90), 'R16': (48.37, 19.05, 90),   # CHRG/STDBY pullups
 # ============ EAST: RTC + backup (quiet corner, far from L1) ============
 'U1': (54.50, 11.50, 0), 'Y1': (52.00, 15.60, 0), 'C13': (59.60, 9.00, 0),
 'R17': (49.46, 19.05, 90), 'R18': (50.55, 19.05, 90), 'R19': (52.20, 20.20, 90),
 'D3': (57.40, 15.45, 0), 'D4': (57.40, 17.50, 0),
 'R27': (53.94, 19.80, 0), 'JP1': (56.66, 19.85, 0),
 'TP1': (60.80, 14.60, 0), 'TP5': (60.80, 18.00, 0),     # VBACKUP + GND pads
 # ============ NORTH band: human/host interface ============
 'J5': (26.90, 27.00, 90),                            # UPDI
 'SW1': (15.50, 3.40, 0),
 'J4': (23.50, 3.40, 0),                             # STEMMA QT host I2C
 'D1': (40.00, 2.60, 0), 'R20': (39.00, 5.30, 0), 'R21': (41.00, 5.30, 0),
 'D2': (48.00, 2.60, 0), 'R22': (47.00, 5.30, 0), 'R23': (49.00, 5.30, 0),
 # ============ SOUTH band: battery + output + test pads ============
 'J3': (15.50, 25.70, 180),                          # battery JST
 'R6': (19.03, 23.60, 0), 'R7': (21.04, 23.60, 0),   # VBAT divider
 'TP2': (19.60, 27.20, 0), 'TP4': (22.80, 27.20, 0), # BAT+ / GND
 'J2': (46.00, 25.40, 0),                          # USB-C out, beside the converter output
 'R4': (52.60, 25.40, 0), 'R5': (52.60, 27.00, 0),   # CC Rp
 'TP3': (35.40, 27.20, 0), 'TP6': (38.60, 27.20, 0), # VOUT / GND
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
    # Pi Zero / Witty Pi 4 mounting spec: 4x M2.5, drill 2.75mm, on the 58x23mm
    # grid. KiCad's stock footprint drills 2.70mm -- patch it to match exactly.
    mh = load_footprint(HOLE_FP).replace('(drill 2.7)', '(drill 2.75)')
    for n,(x,y) in enumerate(HOLES,1):
        body.append(place_footprint(mh, f'H{n}', 'M2.5', x, y, 0, {}))
    # Pi Zero / Witty Pi outline: 65x30 with 3mm corner radius.
    R=3.0; K=R*(1-0.7071067811865476)
    for (x1,y1,x2,y2) in [(R,0,W-R,0),(W,R,W,H-R),(W-R,H,R,H),(0,H-R,0,R)]:
        body.append(f' (gr_line (start {x1} {y1}) (end {x2} {y2}) (layer "Edge.Cuts") (width 0.1))')
    for (sx,sy,mx,my,ex,ey) in [(0,R,K,K,R,0), (W-R,0,W-K,K,W,R),
                                (W,H-R,W-K,H-K,W-R,H), (R,H,K,H-K,0,H-R)]:
        body.append(f' (gr_arc (start {sx} {sy}) (mid {mx:.4f} {my:.4f}) (end {ex} {ey}) (layer "Edge.Cuts") (width 0.1))')
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
    # Edge keepout frames (F/B, tracks only): Freerouting has no concept of the
    # board's 0.5mm copper-to-edge constraint and will happily lay tracks 0.2mm
    # from the outline. Thin frames keep it honest; vias/pads/pour unaffected.
    # (NOT a full-board rule area -- that kills all vias; see the In1 lesson.)
    M=0.55
    frames=[(0,0,W,M),(0,H-M,W,H),(0,0,M,H),(W-M,0,W,H)]
    for n,(x1,y1,x2,y2) in enumerate(frames):
        for ly in ('F.Cu','B.Cu'):
            body.append(f''' (zone (net 0) (net_name "") (layer "{ly}") (uuid "ko-edge-{n}-{ly[0]}")
  (name "ko_edge_{n}_{ly[0]}") (hatch edge 0.5)
  (connect_pads (clearance 0)) (min_thickness 0.25)
  (keepout (tracks not_allowed) (vias allowed) (pads allowed) (copperpour allowed) (footprints allowed))
  (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
  (polygon (pts (xy {x1} {y1}) (xy {x2} {y1}) (xy {x2} {y2}) (xy {x1} {y2}))))''')
    # Local F.Cu power pours (priority 1, above the GND pour): J1's VBUS field,
    # J2's VOUT field, and the OR-output -> converter-input VSYS strap. USB-C
    # power pads sit at 0.5mm pitch between CC/GND pads -- a 0.55mm-minimum
    # Power trace cannot escape them laterally, and should not have to: pour the
    # field and the pads are absorbed instead of routed (same mechanism that
    # makes the GND pour absorb 55 GND pads).
    if os.environ.get('PADPOURS'):     # off by default: pours fragment and
        for name,(x1,y1,x2,y2) in (('VBUS',(1.0,8.8,13.0,21.2)),   # need stitching;
                                    ('VOUT',(41.0,23.5,51.0,29.5)), # plain traces are
                                    ('VSYS',(22.3,10.5,31.4,18.0))):# cleaner (v2-r12)
            body.append(f''' (zone (net {codes[name]}) (net_name "{name}") (layer "F.Cu") (priority 1) (hatch edge 0.5)
  (connect_pads (clearance 0.25)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
  (polygon (pts (xy {x1} {y1}) (xy {x2} {y1}) (xy {x2} {y2}) (xy {x1} {y2}))))''')
    # In2 left FREE for signals (v2-r8 experiment): with the F.Cu pad-field
    # pours handling the USB-C escapes and In1 carrying GND, the In2 partition
    # planes cost more routing freedom than they delivered -- Freerouting sat at
    # 6-9 unrouted with them and left B.Cu nearly empty (11 segments). Power
    # bulk rides the pours + 0.6mm class-width traces instead.
    body.append(')')
    open(path,'w').write('\n'.join(body))

if __name__=='__main__':
    missing = set(COMPONENTS) - set(FLOORPLAN)
    if missing: print("NOT PLACED:", sorted(missing)); sys.exit(1)
    gen_pcb(os.path.join(os.path.dirname(__file__) or '.','powermod_v2.kicad_pcb'))
    print(f"OK: {len(FLOORPLAN)} components on {BOARD_W}x{BOARD_H}mm, 4 layers")
