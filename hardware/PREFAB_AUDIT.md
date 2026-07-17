# PowerMOD mount board — pre-fab audit (2026-07-17)

Full verification of `powermod.kicad_pcb` (renamed from powermod_mount 2026-07-17) against `netlist.py`, datasheets,
and fab constraints. Method + findings recorded so a re-audit after any change
can rerun the same checks.

## Checks performed and results

| Check | Method | Result |
|---|---|---|
| Board ↔ netlist | per-pad diff script (every pad's net vs `netlist.py`) | 214/214 pads exact, 11 NCs correct, no extras (73 comps, 45 nets) |
| IC pinouts | datasheet re-verification, pin by pin | ATtiny1616 SOIC-20 ✓, TPS63020 ✓, TP4056 ✓, BM8563(=PCF8563) ✓, XC6206 ✓, BSS138 ✓, AON7407 ✓, 1N4148WS ✓ |
| FB divider | VFB=0.5V; R24=180k, R25=1M, R26=620k | JP2 open **5.000V**, closed **3.278V** |
| ADC ranges | 330k/1M divider | VBAT 4.2→1.042V; VBUS 5.25→1.303V → **use VDD (3.3V) or 2.5V ref; 1.1V clips, 1.5V is marginal (1.37V at 5.5V USB max)** |
| Power path | state-walk USB-in / battery-only / unplug / boot | correct; TP4056 charges undisturbed (proper load sharing) |
| Off-state drain | budget sum | ~7.5µA total |
| Width rules | `.kicad_dru` fires (4 hits = U3 QFN necks, intrinsic) | enforced |
| Paste | 234 SMD pads; 14 intentionally paste-free (6 test pts, 2 solder jumpers, 4 exposed pads); EPs get separate windowed apertures 65% | ✓ |
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
   *is* the power ground return of the 4A switching loop. **Fab assumption:
   these EP vias must be tented/plugged** (they sit in the unpasted strip, but
   an open barrel in a reflowed pad wicks solder → weak thermal joint). JLCPCB
   tents vias < 0.3mm by default; confirm in the fab order or mark them tented.

3. **Power-rail width vs current (the audit originally only checked "meets the
   0.6mm Power-class minimum", not "is 0.6mm enough").** Re-examined 2026-07-17:
   - **Worst-case VBUS** = charge (1A, R1=1.2k) + Pi system via the converter.
     Pi Zero 2W sustained ~0.5A → ~0.56A at VBUS; stress-peak ~1.2A → ~1.33A.
     So VBUS ~**1.6A sustained, ~2.3A peak**.
   - **Topology finding**: the two USB-C VBUS contacts do NOT share the load.
     A9's pad has the low-impedance path to U4/Q1; A4 reaches the loads only
     through the 0.4mm bridge up via R28. So **A9's single 0.6mm trace carries
     essentially all input current** (the ~4mm A9→U4.4 segment sees the full
     charge+system sum before the charger current drops off at U4.4).
   - **Verdict — acceptable, not a defect**: 0.6mm 1oz carries ~1.6A at +10°C,
     so sustained 1.6A ≈ +10°C; the 2.3A peaks are brief and on a short segment
     (thermal mass + surrounding copper). Drop is negligible (~4mm ≈ 2mΩ).
   - **VSYS** (converter input, up to ~2.2A in boost from a low battery, and
     this one is *sustained* if the Pi draws steadily): 0.6mm, ~58mm, no pour —
     ~42mV drop / ~+18°C at 2A. Consciously accepted; warm but fine.
   - **Hardening DONE (see open item (d))**: A4↔A9 tied with a 0.6mm F.Cu link;
     split is now A9 73% / A4 27%, contacts 0.84A each (was 1.15A).

## SPICE verification — power path (2026-07-17)

Behavioral ngspice model of the discrete power stage (Q1/Q2/Q3 OR-ing + the
R10/R11/C12 soft-start) with the TPS63020 modelled as a constant-power load on
VSYS (output regulated while VSYS > 1.8V). Deck: `tools/spice/`. FETs are
behavioural (body diode + Vgs-gated switch) — good for switchover logic, not
exact RDSon.

**Passes — the OR-ing power path works:**
- Battery-only cold start: VSYS comes up to ~VBAT via Q2. ✓
- USB plug-in: VSYS bootstraps to VBUS−0.7 through Q1's body diode (powers the
  MCU before firmware acts), then Q1 turns on with a ~3ms soft-start ramp
  (C12 limits inrush). ✓
- **VOUT holds its setpoint through USB unplug in every battery-backed case**
  — 5V stays 5V, 3.3V stays 3.3V — because the TPS63020 keeps regulating down
  to 1.8V input. Tested {5V,3.3V} out × {4.2V,3.0V batt} × {idle,active}. ✓
- No-battery case correctly drops out on unplug (no cell = no backup).

**Findings (none are board-changers):**
1. **Unplug VSYS sag.** C12 holds Q1 on after the gate is released, and Q1
   ties VBUS≈VSYS, which keeps Q2's *channel* off — so the battery briefly
   feeds only through Q2's body diode and VSYS sags to ~VBAT−0.7. **Harmless:
   VOUT is uninterrupted (converter masks it); MCU/RTC ride through.** A real
   fix needs two changes (fast Q1-off AND faster VBUS bleed via smaller R12,
   which costs standby current) — not worth it. **Bench-verify: scope VSYS
   while yanking USB.**
2. **Low-battery margin.** At 3.0V batt + 0.4A, the unplug sag reaches
   VSYS≈2.03V — only ~0.2V above the converter's 1.8V floor. Fine for a Zero
   2W; a heavier load/emptier cell would eat the margin. Reinforces the Zero
   2W scope.
3. **3.3V rail droops during the sag** → **use the ATtiny1616-SN (1.8V min),
   not the -SF/-SFR (2.7V min)**, which would be marginal here. (Third
   independent reason for the -SN.)

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

1. ADC reference: **use VDD (3.3V) or the 2.5V internal ref** — VBUS_DIV maxes
   ~1.3V, well inside either. Do NOT use 1.1V (clips VBUS_DIV) and avoid 1.5V
   (only 0.13V headroom at 5.5V USB max — brittle). VDD-ref is simplest;
   2.5V-ref is more accurate if VDD ripple matters. Divider resolution with
   VDD ref: ~13mV/LSB at the battery (10-bit) — ample for monitoring.
2. Internal pull-up on PA2 (button has no external pull-up).
3. Poll VBUS_DIV; **drop Q1_GATE_DRV when VBUS disappears** (hardware allows
   a brief battery→USB backfeed window through Q1 until firmware reacts).
4. CONV_EN idles low via R14 → Pi is off until firmware enables (by design).

## Open items (decide before fab)

- **(d) VBUS current-sharing — RESOLVED 2026-07-17** (hand-routed in KiCad
  after the scripts could only manage a 0.4mm detour). A 0.6mm F.Cu tie was
  run from A4 down to A9 in the ~0.1mm-clear channel just right of the pad
  column (x≈9.79). Measured split now **A9 73% / A4 27%** (was ~100/0):
  A9's trace peak drops 2.3A→1.68A and its USB-C contacts **1.15A→0.84A/contact**
  (comfortably inside the ~1.25A rating). Not 50/50 (A4 is farther from the
  load) but the margin we wanted, at full width. Board pad-diff 214/214, DRC
  clean.

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
