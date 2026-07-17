# PowerMOD hardware

Machine-generated PCB design for a Raspberry Pi Zero 2 W power scheduler /
UPS / battery board. The electrical design is defined in code (`netlist.py`);
the board was laid out and routed with the scripted KiCad + Freerouting
toolchain below, then hand-finished.

## The board — `powermod.kicad_pcb` (final)

65 × 40 mm, 4-layer (F.Cu signal / In1 solid GND / In2 signal / B.Cu signal).
Bolts under a Pi Zero 2 W (holes on the Pi's 58×23 grid, flush to the N+W
edges); the Pi covers y0–30, and all user-facing parts (USB-C out, battery,
button, LEDs, jumpers, test pads) sit on the exposed strip below it.
Single-sided assembly.

One KiCad project, one stem: `powermod.kicad_pro` (netclasses + DRC config),
`powermod.kicad_sch` (generated schematic), `powermod.kicad_pcb` (board),
`powermod.kicad_dru` (width-enforcement rules — net classes alone are NOT
checked by DRC).

**Status: fab-ready.** Fully routed, 0 unconnected, 0 clearance; the only DRC
items are 4 `track_width` flags on the L2/L1N necks at U3's 0.65 mm pins,
which physically cannot be 1.0 mm wide. Pre-fab audit (pad-for-pad netlist
diff, datasheet pin checks, operating-point math, the D5 supercap fix):
see **`PREFAB_AUDIT.md`** — read it before ordering (BOM traps, firmware
contract, bring-up plan).

> **Do NOT regenerate this board from `netlist.py`.** Placement and the
> USB-C fine-pitch escapes are hand-done. Make changes surgically on
> `powermod.kicad_pcb` and update `netlist.py` in parallel, then prove they
> agree with a pad-diff (the audit doc describes it).

## Electrical source of truth

- **`netlist.py`** — every component, pin, and net (73 components, 45 nets).
  Run it to (re)generate `powermod.kicad_sch`, `powermod.net`,
  `powermod.kicad_sym`, `sym-lib-table`, `fp-lib-table`. Has a self-test
  (golden vectors, pin counts).
- **`powermod.pretty/`** — local footprint lib: the merged-pad USB-C
  receptacle (reversible twin pads share one pad, so VBUS/GND escape cleanly
  and DRC sees no coincident-pad conflicts). Required to open the board.

## Reusable tools

All the layout/routing/placement scripts live in **`tools/`** (run them from
this directory, e.g. `python3 tools/finish_board.py powermod.kicad_pcb`, so
board paths and `_sizes.json` resolve; they add the parent dir to `sys.path`
to import `netlist.py`). `netlist.py` itself stays here — it's the design
source and writes the deliverables alongside itself. SPICE decks are in
`tools/spice/`.

Routing pipeline (for derivative boards — not this one):
- **`fr_pipeline.py`** — strip copper + export Specctra DSN / import routed
  SES. Freerouting must never see a pre-routed board.
- `tools/freerouting.jar` (gitignored, ~55 MB) — the autorouter. Java 21+, run
  with `-Djava.awt.headless=true` or it hangs on macOS.
- **`finish_board.py`** — post-route finisher: SES import → GND stitching →
  floating-pour-island tie vias → zone refill. Then DRC with
  `--refill-zones` (without it you get hundreds of phantom violations).
- **`stitch_gnd.py`** — the 2.5 mm GND stitching-via grid to the In1 plane.
- **`close_nets.py`** — route leftover nets with the In2-capable grid A*,
  each route validated by refill+DRC and reverted if it doesn't improve.
- **`router.py`** — grid A* + obstacle model (F/In2/B) used by the above.
- **`netclasses.py`** — inject net-class width targets into a `.kicad_pro`.

Placement:
- **`layout_v2.py`** — the board generator (`gen_pcb`: footprints, GND
  planes, keepouts). `layout_mount.py` configures it for this board's
  outline/holes/pinned I/O.
- **`place_constrained.py`** — constraint-aware force-directed placer
  (net springs, padded repulsion, wide-net/IC halos, rigid converter block).
- **`place_search_mount.py`** / **`relax_mount.py`** — placement search
  scored by Freerouting / overlap relaxer. **`mount_best.py`** — placer
  output snapshot (stale vs the hand-edited board; the board is
  authoritative).
- **`place_check.py`** — courtyard-overlap + off-board report.
- **`make_stencil.py`** — generates a bare user-facing-parts canvas for
  human I/O placement (its output board was removed once the layout froze).
- `_sizes.json` — cached footprint courtyard sizes (kept in this dir; the
  placer reads it cwd-relative).

SPICE (`tools/spice/`):
- **`power_path_scenarios.py`** — behavioural ngspice model of the Q1/Q2/Q3
  power path; runs the startup/switchover/unplug scenario matrix (see the
  SPICE section of `PREFAB_AUDIT.md`). Needs `ngspice` on PATH.

## Hard-won rules (cost real time — don't relearn them)

- A green DRC only checks rules that exist: keep `powermod.kicad_dru` next
  to the board, and after any rename/move confirm the 4 known `track_width`
  flags still fire (if they vanish, the rules got orphaned, not fixed).
- Netclasses live in the `.kicad_pro`. A board file copied away from its
  project routes everything at 0.2 mm and "routes fully" — a fake win.
- Zone fills are stored in the file: refill before DRC or judging renders.
- Scripted tracks don't bind to large connector pads (USB-C, bar pads) —
  those few escapes are interactive-routing territory; small pads bind fine.

## History

v1 (58×40, 2-layer) had 3A rails at 0.2 mm (the `.kicad_dru` lesson); v2
(65×30) was superseded by this board; the QFN-package MCU was swapped for the
SOIC-20 ATtiny1616 to break the routing wall; `powermod_mount.*` was renamed
to `powermod.*` once it became the only board (2026-07-17). Lessons live in
the tools and `PREFAB_AUDIT.md`, not in stale board files.
