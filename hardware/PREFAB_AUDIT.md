# PowerMOD mount board — pre-fab audit (2026-07-17)

Full verification of `powermod.kicad_pcb` (renamed from powermod_mount 2026-07-17) against `netlist.py`, datasheets,
and fab constraints. Method + findings recorded so a re-audit after any change
can rerun the same checks.

## Checks performed and results

| Check | Method | Result |
|---|---|---|
| Board ↔ netlist | per-pad diff script (every pad's net vs `netlist.py`) | 212/212 pads exact, 11 NCs correct, no extras |
| IC pinouts | datasheet re-verification, pin by pin | ATtiny1616 SOIC-20 ✓, TPS63020 ✓, TP4056 ✓, BM8563(=PCF8563) ✓, XC6206 ✓, BSS138 ✓, AON7407 ✓, 1N4148WS ✓ |
| FB divider | VFB=0.5V; R24=180k, R25=1M, R26=620k | JP2 open **5.000V**, closed **3.278V** |
| ADC ranges | 330k/1M divider | VBAT 4.2→1.042V; VBUS 5.25→1.303V (**needs 1.5V ref, 1.1V clips**) |
| Power path | state-walk USB-in / battery-only / unplug / boot | correct; TP4056 charges undisturbed (proper load sharing) |
| Off-state drain | budget sum | ~7.5µA total |
| Width rules | `.kicad_dru` fires (4 hits = U3 QFN necks, intrinsic) | enforced |
| Paste | all 232 SMD pads; EPs windowed 65% (unnamed aperture pads) | ✓ |
| Gerbers/drills | kicad-cli export smoke test; drills ≥0.3mm | ✓ 21 files, 4 layers |

## Findings

1. **VBACKUP back-drain (design flaw)** — supercap discharges through
   R27(1k)+JP1 into the dead 3V3 rail at ~3mA exactly when backup is needed;
   0.47F flat in minutes vs the RTC's 0.25µA. **Fix APPLIED 2026-07-17: D5
   (1N4148WS) in series: 3V3→R27→D5→JP1** (new net CHG_JPD; D5 at (58.6,31.0)
   rot 90 between R27 and JP1; netlist.py + board both updated, pad-diff 214/214
   clean). Supercap tops at ~2.85V, RTC sees ~2.5V on backup (keeps time to
   1.0V — fine). BOM: order one extra 1N4148WS (5 total with D3/D4… D3, D4, D5).
2. **U3 EP had zero PGND vias within 3.5mm** (FIXED 2026-07-17: 2 vias placed
   in the EP's unpasted center strip at (38.55, 8.15/8.95)). The TPS63020 EP
   *is* the power ground return of the 4A switching loop.

## BOM obligations (no DRC can catch these)

- **LEDs D1/D2 — RESOLVED 2026-07-17.** Part = TOGIALED TJ-S3227 (LCSC
  **C601677**, ~7.7k stock), a yellow-green/red dual die (2.4V green → 1.6mA
  through 560Ω, so no longer dim — the earlier InGaN-green concern is moot).
  Its pinout is NOT the stock KiCad Avago PLCC4 (numbering runs the opposite
  way → would reverse polarity), so a local footprint
  `powermod.pretty/LED_TJ-S3227_RG_3.2x2.7mm.kicad_mod` was built from LCSC's
  EasyEDA model (2 independent diodes: anodes = pins 2,3; cathodes = pins 1,4).
  netlist.py + board updated (pad-diff 214/214). **Residual: red-vs-green die
  identity (netlist assumes top row = red) is not fixed by the EasyEDA data —
  electrically irrelevant (identical 560Ω on both) and firmware-adjustable;
  confirm against the datasheet colour drawing only if the silk label must
  match. Also verify LED rotation in JLCPCB's placement preview** (JLC's
  rotation convention for 4-pin LEDs often differs from KiCad by 90/180°).
- **Crystal — RESOLVED 2026-07-17.** Epson Q13FC13500004 (LCSC **C32346**,
  ~286k stock): 32.768kHz, **CL=12.5pF** (matches BM8563), 3215 2-pin,
  ±20ppm. In netlist.py.
- **LCSC numbers VERIFIED against lcsc.com 2026-07-17** — two were wrong and
  are fixed in netlist.py:
  | Part | Number | Verdict |
  |---|---|---|
  | TPS63020DSJR | C15483 | ✓ (VSON-14-EP 3x4, in stock) |
  | TP4056 | C382139 | ✓ (TPOWER, ESOP-8, 60k stock) |
  | ATtiny1616 | ~~C2891852~~ → **C614136** | old # was a 4-pin 1.2mm header(!). C614136 = ATTINY1616-SN, 0 LCSC stock at check; sub C145558 (-SFR, 16MHz, **2.7V min** — thin at battery-empty) or buy -SN at Mouser/DigiKey |
  | AON7407 | C176756 | ✓ (AOS, DFN-8 3x3, 24k stock) |
  | XC6206P332MR-G | C5446 | ✓ (SOT-23, 206k stock) |
  | BSS138 | C52895 | ✓ (onsemi, SOT-23, 39k stock) |
  | BM8563 | ~~C194063~~ → **C269877** | old # was the TSSOP-8 (doesn't fit our SOIC-8 footprint) and OOS. C269877 = BM8563ESA SOP-8, 80k stock |
  Stock numbers are point-in-time — recheck at order.

## Firmware contract (hardware assumes these)

1. ADC reference **1.5V** (1.1V clips VBUS_DIV at 5.25V input).
2. Internal pull-up on PA2 (button has no external pull-up).
3. Poll VBUS_DIV; **drop Q1_GATE_DRV when VBUS disappears** (hardware allows
   a brief battery→USB backfeed window through Q1 until firmware reacts).
4. CONV_EN idles low via R14 → Pi is off until firmware enables (by design).

## Accepted minor notes

- 56k Rp on J2 advertises 500mA to compliant C-C sinks (22k would advertise
  1.5A); C-to-microB cables ignore CC anyway.
- TP4056 dissipates up to 2W at low VBAT — thermal regulation folds back;
  expect <1A effective charge on hot days.
- CHG_CE 100k pull-up to 5V injects ~15µA into a tri-stated MCU pin (in spec;
  drive the pin in firmware).
- 122 silk-overlap warnings = refdes cosmetics; fabs clip silk over pads.

## Bring-up plan

Populate one board first. Bench supply, current-limited, on VBUS pads before
any battery. Verify: 3V3 rail → UPDI contact → VOUT=5.00V with CONV_EN driven
high → charge current 1A into a dummy load/cell → then battery + Pi.
