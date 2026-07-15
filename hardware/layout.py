#!/usr/bin/env python3
"""PowerMOD board layout generator.

Reads connectivity from netlist.py and real footprint geometry from the
installed KiCad libraries; emits powermod.kicad_pcb with:
  - board outline (Edge.Cuts)
  - all footprints placed per FLOORPLAN (the design intent lives there)
  - every pad bound to its net (live ratsnest in pcbnew)
  - GND zones on F.Cu and B.Cu
  - 4x M2 mounting holes

NOT done here: signal-net copper routing. Placement is design; routing is
interactive work in pcbnew with the ratsnest + DRC. The GND pours do make
most GND pads genuinely connected.

Floorplan intent (powermod-schematic.md section 3 checklist):
  power flows left to right: J1(USB in) -> charger/OR -> VSYS -> converter
  (tight L1 loop, bottom-center) -> VOUT -> J2. Crystal+RTC top-right,
  far from the converter loop. MCU center-right. Connectors on edges.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__) or '.')
from netlist import COMPONENTS, build_nets

KISHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
BOARD_W, BOARD_H = 58.0, 40.0   # mm (56 sealed the SCL corridor with a pad wall; +2mm on the right reopens it)

# ref: (x, y, rot)  — origin top-left of board; y down. Edited under DRC.
FLOORPLAN = {
 # left edge: power in/out
 'J1': (5.0, 12.0, -90), 'J2': (5.0, 34.0, -90),
 # input cluster
 'C7': (12.5, 6.5, 90), 'C15': (12.5, 10.0, 90), 'R12': (12.5, 13.5, 90),
 'U4': (18.0, 10.0, 0),  'R1': (23.0, 6.0, 90), 'C6': (23.0, 14.0, 90),
 # OR block
 'Q1': (13.5, 21.5, 0), 'Q2': (22.0, 21.5, 0), 'Q3': (17.8, 27.0, 0),
 'R10': (13.5, 26.5, 90), 'R11': (22.0, 26.5, 90), 'C12': (13.5, 29.5, 90),
 'R13': (22.0, 29.5, 90),
 # battery
 'J3': (17.0, 41.5, 180), 'TP2': (25.0, 42.5, 0), 'TP4': (29.5, 42.5, 0),
 'R6': (27.0, 36.5, 90), 'R7': (27.0, 33.0, 90), 'C10': (30.0, 34.5, 90),
 # converter, tight loop bottom-center
 'U3': (35.0, 26.5, 0), 'L1': (35.0, 34.5, 0),
 'C1': (29.5, 25.0, 90), 'C2': (29.5, 29.0, 90), 'C16': (29.7, 21.5, 90),
 'C3': (40.5, 25.0, 90), 'C4': (40.5, 29.0, 90), 'C5': (44.0, 27.0, 90),
 'R24': (40.5, 21.0, 90), 'R25': (44.0, 21.0, 90), 'R26': (47.5, 21.0, 90),
 'JP2': (47.5, 26.0, 0), 'TP3': (44.0, 42.5, 0),
 'R14': (31.5, 17.5, 0),
 # LDO + 3V3
 'U5': (29.5, 6.0, 0), 'C8': (25.5, 9.0, 90), 'C9': (33.5, 9.0, 90),
 # VBUS/VBAT divider spill
 'R8': (9.5, 21.5, 0), 'R9': (9.5, 23.2, 0), 'C11': (9.5, 25.0, 0),
 # MCU center-right
 'U2': (44.0, 12.0, 0), 'C14': (37.5, 9.5, 90),
 'R15': (38.0, 15.5, 90), 'R16': (40.0, 15.5, 90),
 # RTC top-right, crystal in the corner away from L1
 'U1': (55.0, 9.5, 0), 'Y1': (53.5, 3.8, 0),
 'C13': (48.5, 5.5, 90), 'D3': (48.5, 9.0, 0), 'D4': (48.5, 11.5, 0),
 'R17': (54.0, 15.5, 90), 'R18': (56.0, 15.5, 90), 'R19': (58.0, 15.5, 90),
 'TP1': (58.5, 20.5, 0), 'JP1': (53.5, 20.5, 0), 'R27': (49.5, 20.5, 90),
 # right edge: host-facing
 'J4': (58.0, 27.0, -90), 'J5': (40.5, 4.0, 90),
 'SW1': (50.5, 41.0, 0), 'D1': (46.5, 35.5, 0), 'D2': (53.5, 35.5, 0),
 'R20': (45.5, 31.0, 90), 'R21': (47.5, 31.0, 90),
 'R22': (51.5, 31.0, 90), 'R23': (53.5, 31.0, 90),
 # CC resistors near their ports
 'R2': (12.5, 16.0, 0), 'R3': (12.5, 17.6, 0),
 'R4': (12.5, 31.8, 0), 'R5': (12.5, 33.5, 0),
}
# scale the hand floorplan into the smaller outline; edge parts overridden below
_SX,_SY=56.0/62.0,40.0/46.0
FLOORPLAN={r:(round(x*_SX,2),round(y*_SY,2),rot) for r,(x,y,rot) in FLOORPLAN.items()}
FLOORPLAN.update({
 'J1': (4.6, 10.5, -90), 'J2': (4.6, 29.5, -90),
 'J3': (15.5, 36.0, 180), 'J4': (52.4, 23.5, -90), 'J5': (37.0, 3.6, 90),
 'SW1': (46.5, 35.5, 0),
 'TP2': (23.0, 36.5, 0), 'TP4': (26.8, 36.5, 0),
 'TP3': (39.5, 36.5, 0), 'TP6': (43.2, 36.5, 0),
 'TP1': (52.3, 15.5, 0), 'TP5': (52.3, 19.2, 0),
 'JP1': (47.8, 18.0, 0), 'R27': (44.4, 18.0, 90),
 'Y1': (48.5, 3.4, 0), 'U1': (50.0, 8.6, 0),
 'R17': (49.0, 13.0, 90), 'R18': (51.0, 13.0, 90), 'R19': (53.0, 13.0, 90),
 'D1': (41.5, 31.0, 0), 'D2': (48.0, 31.0, 0),
 'R20': (40.5, 27.0, 90), 'R21': (42.5, 27.0, 90), 'R22': (46.5, 27.0, 90), 'R23': (48.5, 27.0, 90),
 'C13': (45.5, 6.5, 90), 'D3': (45.5, 9.3, 0), 'D4': (45.5, 11.6, 0),
 'Y1': (47.3, 3.4, 0),
 'J1': (4.6, 11.2, -90), 'J2': (4.6, 28.6, -90),
 'R17': (49.0, 12.2, 90), 'R18': (51.0, 12.2, 90), 'R19': (53.0, 12.2, 90),
 'TP1': (52.4, 15.4, 0), 'TP5': (52.4, 18.6, 0),
 'C10': (25.6, 30.0, 90),
 'TP3': (37.5, 36.5, 0), 'TP6': (41.0, 36.5, 0),
 'J3': (17.5, 36.0, 180),
 'R4': (11.3, 27.4, 0), 'R5': (11.3, 29.1, 0),
 'D3': (44.3, 9.3, 0), 'D4': (44.3, 11.6, 0),
 'R17': (47.6, 13.3, 90), 'R18': (49.4, 13.3, 90), 'R19': (51.2, 13.3, 90),
 'TP1': (53.0, 29.4, 0), 'TP5': (53.0, 32.5, 0),
 'TP6': (41.0, 37.2, 0),
})
# right-side decompression: everything from x>=42.5 shifts +2 (SCL corridor fix)
FLOORPLAN={r:((x+2.0 if x>=42.5 else x),y,rot) for r,(x,y,rot) in FLOORPLAN.items()}
HOLES = [(3.2,3.2),(BOARD_W-3.2,3.2),(3.2,BOARD_H-3.2),(BOARD_W-3.2,BOARD_H-3.2)]

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
    path = os.path.join(KISHARE, lib+'.pretty', name+'.kicad_mod')
    return open(path).read()

# --------------------------------------------------------------------- build
def pad_net_map():
    """(ref -> {padnum: (netcode, netname)}), net table."""
    nets = build_nets()
    named = sorted(n for n in nets if n != 'NC')
    codes = {n: i+1 for i, n in enumerate(named)}
    m = {}
    for ref,(val,fp,lcsc,pins) in COMPONENTS.items():
        m[ref] = {p:(codes[net],net) for p,(pn,net) in pins.items() if net!='NC'}
    return m, codes

def place_footprint(src, ref, val, x, y, rot, padnets):
    """Inject placement, reference, value, pad nets into a .kicad_mod body."""
    # footprint header: (footprint "NAME" ... insert (at x y rot) after layer
    s = src
    i = s.find('(layer'); j = matching(s, i)
    s = s[:j] + f'\n  (at {x} {y} {rot})' + s[j:]
    # rotate pads: KiCad pads carry their own (at px py prot); when a footprint
    # has (at x y rot), pad rotations must ADD rot (KiCad convention: pad at is
    # relative, but pad rotation in file is absolute-ish: actually relative
    # angles are stored already summed by the editor; for generated boards
    # adding rot to each pad angle matches editor behaviour).
    def fix_pad(m2):
        block = m2.group(0)
        am = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)( (-?[\d.]+))?\)', block)
        if am:
            pa = float(am.group(4) or 0) + rot
            block = block.replace(am.group(0), f'(at {am.group(1)} {am.group(2)} {pa})', 1)
        return block
    # set reference/value texts
    s = re.sub(r'\(property "Reference" "[^"]*"', f'(property "Reference" "{ref}"', s, 1)
    s = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" "{val}"', s, 1)
    # bind nets pad-by-pad
    out=[]; k=0
    while True:
        p = s.find('(pad "', k)
        if p < 0:
            out.append(s[k:]); break
        e = matching(s, p)
        block = s[p:e]
        num = re.match(r'\(pad "([^"]*)"', block).group(1)
        block = fix_pad(re.match(r'(?s).*', block))
        if num in padnets:
            code, name = padnets[num]
            block = block[:-1] + f' (net {code} "{name}")' + ')'
        out.append(s[k:p]); out.append(block); k=e
    return ''.join(out)

def gen_pcb(path):
    padmap, codes = pad_net_map()
    body=[]
    body.append('(kicad_pcb (version 20221018) (generator powermod_layout_py)')
    body.append(' (general (thickness 1.6))')
    body.append(' (paper "A4")')
    body.append(' (layers (0 "F.Cu" signal) (31 "B.Cu" signal)'
                ' (32 "B.Adhes" user) (33 "F.Adhes" user) (34 "B.Paste" user) (35 "F.Paste" user)'
                ' (36 "B.SilkS" user) (37 "F.SilkS" user) (38 "B.Mask" user) (39 "F.Mask" user)'
                ' (40 "Dwgs.User" user) (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user)'
                ' (48 "B.Fab" user) (49 "F.Fab" user))')
    body.append(' (setup (pad_to_mask_clearance 0.05))')
    body.append(' (net 0 "")')
    for name, code in sorted(codes.items(), key=lambda kv: kv[1]):
        body.append(f' (net {code} "{name}")')
    # footprints
    for ref,(x,y,rot) in FLOORPLAN.items():
        val, fp, lcsc, pins = COMPONENTS[ref]
        src = load_footprint(fp)
        body.append(place_footprint(src, ref, val, x, y, rot, padmap.get(ref,{})))
    # mounting holes
    mh = load_footprint('MountingHole:MountingHole_2.2mm_M2')
    for n,(x,y) in enumerate(HOLES,1):
        body.append(place_footprint(mh, f'H{n}', 'M2', x, y, 0, {}))
    # outline
    W,H=BOARD_W,BOARD_H
    for (x1,y1,x2,y2) in [(0,0,W,0),(W,0,W,H),(W,H,0,H),(0,H,0,0)]:
        body.append(f' (gr_line (start {x1} {y1}) (end {x2} {y2}) (layer "Edge.Cuts") (width 0.1))')
    # GND zones both layers
    g = codes['GND']
    for layer in ('F.Cu','B.Cu'):
        body.append(f''' (zone (net {g}) (net_name "GND") (layer "{layer}") (hatch edge 0.5)
  (connect_pads (clearance 0.3)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
  (polygon (pts (xy 0 0) (xy {W} 0) (xy {W} {H}) (xy 0 {H}))))''')
    body.append(')')
    open(path,'w').write('\n'.join(body))

if __name__=='__main__':
    missing = set(COMPONENTS) - set(FLOORPLAN)
    if missing: print("NOT PLACED:", sorted(missing)); sys.exit(1)
    gen_pcb(os.path.join(os.path.dirname(__file__) or '.','powermod.kicad_pcb'))
    print(f"OK: {len(FLOORPLAN)} components placed on {BOARD_W}x{BOARD_H}mm")
