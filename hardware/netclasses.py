#!/usr/bin/env python3
"""Inject net classes into a KiCad .kicad_pro so trace widths are ENFORCED.

    python3 netclasses.py powermod.kicad_pro

Why this exists: without net classes every net lands in Default (0.2mm), so
Freerouting has nothing to aim for and routes 3A rails as hair. These classes
export into the DSN and the router honours them.

This is only HALF the fix. A net class track_width is a router preference —
KiCad's DRC does not check it, and a 0.2mm 3A trace still reports 0 violations
with these classes defined (measured on v1). Enforcement needs an explicit
custom rule: see powermod.kicad_dru / powermod_v2.kicad_dru, which turn the same
untouched v1 board from "0 violations" into 171 track_width errors.

Widths follow powermod-schematic.md's ratings table, read as PER-CONDUCTOR
current (see the note on escape widths below). IPC-2221, 1oz external copper,
~10C rise: 3A wants ~1.1mm, 1.5A ~0.6mm.
"""
import json, sys, os

# net -> (class name, trace width mm, via dia, via drill)
#
# These are ESCAPE widths, not bulk-distribution widths, and the difference is
# the whole trick. Bulk current travels in the In2 power planes; a trace only
# carries what one pad sources. USB-C splits VBUS across four pins (A4/B4/A9/B9),
# so a single escape sees ~0.75A of a 3A load, not 3A — and a TPS63020 or TP4056
# pin likewise carries only its own share.
#
# Forcing a uniform 1.1mm on every escape is over-conservative and does real
# damage: it cannot fan out of a 0.3mm USB-C pad at 0.5mm pitch, which is what
# jammed both boards (v1: 12/117 unrouted at 58x40 2-layer; v2: 10-13/117 at
# 65x30 4-layer — near-identical, because the bottleneck was the connector
# escape, not layers or area).
#
# 0.6mm carries ~1.5A on 1oz external copper at ~10C rise (IPC-2221) — ample per
# pin, with the planes carrying the aggregate. The plane is the conductor; the
# trace is just the on-ramp.
POWER   = 0.60   # VBUS/VSYS/VBAT/VOUT: per-pin escape into the In2 planes
SWITCH  = 1.10   # L1N/L2: NOT an escape — the full inductor current really does
                 # flow in this one trace, and it has no plane. Keep it wide.
LOGIC   = 0.40   # 3V3: XC6206 LDO, 200mA ceiling

CLASSES = {
    'Power':  (POWER, 0.8, 0.4, ['VBUS', 'VSYS', 'VBAT', 'VOUT']),
    'Switch': (SWITCH, 0.8, 0.4, ['L1N', 'L2']),
    'Logic':  (LOGIC, 0.6, 0.3, ['3V3']),
}

def base(name, width, via_d, via_dr, priority):
    return {
        "bus_width": 12.0, "clearance": 0.2,
        "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
        "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "name": name, "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": priority,
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": width, "via_diameter": via_d, "via_drill": via_dr,
        "wire_width": 6.0,
    }

def main(path):
    d = json.load(open(path))
    ns = d.setdefault('net_settings', {})
    classes = [c for c in ns.get('classes', []) if c.get('name') == 'Default']
    if not classes:
        classes = [base('Default', 0.2, 0.6, 0.3, 2147483647)]
    patterns = []
    for i, (name, (w, vd, vdr, nets)) in enumerate(CLASSES.items()):
        classes.append(base(name, w, vd, vdr, i))
        for n in nets:
            patterns.append({"netclass": name, "pattern": n})
    ns['classes'] = classes
    ns['netclass_patterns'] = patterns
    ns.setdefault('meta', {"version": 4})
    json.dump(d, open(path, 'w'), indent=2)
    print(f"{os.path.basename(path)}: {len(classes)} classes, {len(patterns)} patterns")
    for name, (w, vd, vdr, nets) in CLASSES.items():
        print(f"  {name:7s} {w}mm  {', '.join(nets)}")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'powermod.kicad_pro')
