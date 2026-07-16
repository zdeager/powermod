# PowerMOD hardware

Machine-generated PCB design. The electrical design is defined in code
(`netlist.py`); layout and routing are scripted around KiCad + Freerouting.

## Electrical source of truth
- **`netlist.py`** — every component, pin, and net (72 components, 44 nets).
  Run it to (re)generate the schematic + netlist + symbol/footprint tables:
  `powermod.kicad_sch`, `powermod.net`, `powermod.kicad_sym`,
  `sym-lib-table`, `fp-lib-table`. Has a self-test (golden vectors, pin counts).
  ERC-clean in KiCad; the schematic project is `powermod.kicad_pro`.

## Active board — the "mount" board (76 × 46 mm)
Bigger-than-Pi board that still bolts to a Pi Zero 2 W (holes on the Pi's
58×23 grid, flush to the N+W edges); user-facing parts sit on the exposed
strip past the Pi. Single-sided.
- **`layout_mount.py`** — the floorplan (component positions) → generates
  `powermod_mount.kicad_pcb`. User-placed I/O is pinned; circuit spreads freely.
- **`mount_best.py`** — best placement found by the search (apply + route).
- **`powermod_stencil.kicad_pcb`** — bare canvas of just the user-facing parts,
  used to let a human place connectors/LEDs/jumpers, then read back (`make_stencil.py`).
- `powermod_mount.kicad_pro` / `.kicad_dru` — project + width-enforcement rules.

Status: ~95% autorouted. The last ~4 nets (USB-C/QFN fine-pitch escapes) are the
known autorouter wall — they need interactive routing or rip-up to finish.

## Reusable tools
- **`router.py`** — grid A* + obstacle model, routes on F/In2/B (In2 = 4-layer).
- **`fr_pipeline.py`** — strip copper + export Specctra DSN / import routed SES.
- **`netclasses.py`** — inject net classes (trace-width targets) into a `.kicad_pro`.
  (Enforcement needs the `.kicad_dru` — net classes alone are NOT checked by DRC.)
- **`stitch_gnd.py`** — GND stitching vias to the In1 plane.
- **`close_nets.py`** — route leftover nets with the In2 A*, DRC-validated.
- **`place_check.py`** — courtyard-overlap + off-board report (agrees with KiCad).
- **`relax_mount.py`** — overlap-removal for the mount floorplan (pins user I/O).
- **`place_search_mount.py`** — placement search (spread + crossing-anneal),
  scored by Freerouting.
- **`layout_v2.py`** — the shared board GENERATOR (`gen_pcb`, footprint placement,
  GND plane + In2 keepout). `layout_mount` imports it; its own floorplan is legacy.
- `freerouting.jar` (gitignored, ~55MB) — the autorouter. Needs Java 21+, run
  with `-Djava.awt.headless=true` or it hangs on macOS.
- `_sizes.json` — cached footprint courtyard sizes (regenerable).

## Rebuild the board
```
python3 netclasses.py powermod_mount.kicad_pro   # width targets
python3 layout_mount.py                            # placement -> board
# route: fr_pipeline export -> freerouting -> import -> stitch_gnd -> DRC
```

## History
v1 (58×40, 2-layer) and v2 (65×30, Pi footprint) were removed: v1 had a real
defect (3A rails routed at 0.2mm — see the width lesson in
`powermod-schematic.md`), and v2 was superseded by the mount board. The lessons
live in the docs and the tools, not stale board files.
