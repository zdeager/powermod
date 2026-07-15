# PowerMOD — Schematic (pin-exact netlist, v1)

Last updated: 2026-07-15
Status: **Complete pin-for-pin connectivity, ready for capture in any EDA tool.** This document *is* the schematic's source of truth; the EDA file transcribes it. Every IC pin number below is read from the part's datasheet (extraction noted per part); two jellybean pinouts are flagged as convention-verify-at-capture.
Sources: `powermod-spec.md` §Pre-BOM electrical walk (net map), `powermod-bom.md` (refs and values).

**Machine transcription: `hardware/netlist.py`** — the same connectivity as a Python data structure, with a validator (golden board-killer facts, pin counts, no singleton nets) and generators for `hardware/powermod.net` (import into pcbnew for layout) and `hardware/powermod.kicad_sch` (global-label-style schematic; run ERC on open — no kicad-cli was available where these were generated, so KiCad itself is the final parser check).

## 0. Pinout provenance

| Part | Pinout basis |
|---|---|
| TP4056 (ESOP-8) | datasheet pin functions: 1 TEMP, 2 PROG, 3 GND, 4 VCC, 5 BAT, 6 STDBY, 7 CHRG, 8 CE |
| TPS63020 (VSON-14) | TI pin table: 1 VINA, 2 GND, 3 FB, 4-5 VOUT, 6-7 L2, 8-9 L1, 10-11 VIN, 12 EN, 13 PS/SYNC, 14 PG, pad PGND |
| AON7407 (DFN-8) | AOS top view: 1-3 S, 4 G, 5-8 D, pad = D |
| BM8563 (SOP-8) | Belling pin table: 1 OSCI, 2 OSCO, 3 INT, 4 VSS, 5 SDA, 6 SCL, 7 CLKOUT, 8 VDD |
| ATtiny1617 (VQFN-24) | Microchip Table 5-1 (full map below); TWI0 default SDA=PB1, SCL=PB0; UPDI=PA0 |
| XC6206 (SOT-23) | ⚠ convention (1 VSS, 2 VOUT, 3 VIN) — **confirm against the LCSC footprint at capture** |
| BSS138 (SOT-23) | ⚠ convention (1 G, 2 S, 3 D) — **confirm against the LCSC footprint at capture** |

## 1. MCU pin assignment — 18 used + 4 spare, exactly the budget

| VQFN-24 | Port | Signal | Direction / mode | Why this pin |
|---|---|---|---|---|
| 16 | PB0 | `SCL` (host bus) | TWI0 slave | **hardware TWI, fixed** |
| 15 | PB1 | `SDA` (host bus) | TWI0 slave | **hardware TWI, fixed** |
| 23 | PA0 | `UPDI` | programming | **fixed**; reserved, never GPIO |
| 5 | PA4 | `VBAT_SENSE` | ADC0 AIN4 | analog port pin; 1M/330k + 100nF |
| 6 | PA5 | `VBUS_SENSE` | ADC0 AIN5 | analog port pin; identical divider |
| 17 | PC0 | `RTC_SDA` | bit-banged, open-drain | internal bus |
| 18 | PC1 | `RTC_SCL` | bit-banged, open-drain | internal bus |
| 1 | PA2 | `RTC_INT` | input, 10k↑3V3 | **Px2 = fully-async pin** — edge wake from deepest sleep |
| 19 | PC2 | `BUTTON` | input, internal pull-up | **Px2 = fully-async** — wake on press |
| 2 | PA3 | `CONV_EN` | output (+100k↓) | TPS63020 EN |
| 20 | PC3 | `Q1_GATE_DRV` | output (+100k↓) | drives Q3 gate |
| 21 | PC4 | `CHG_CE` | output | TP4056 CE (high = charge) |
| 12 | PB4 | `CHG_CHRG` | input, 10k↑3V3 | TP4056 CHRG (open-drain) |
| 11 | PB5 | `CHG_STDBY` | input, 10k↑3V3 | TP4056 STDBY (open-drain) |
| 14 | PB2 | `LED_PWR_A` | output, 560Ω | TOSC pin — free, no MCU crystal |
| 13 | PB3 | `LED_PWR_B` | output, 560Ω | TOSC pin — free |
| 10 | PB6 | `LED_BAT_A` | output, 560Ω | |
| 9 | PB7 | `LED_BAT_B` | output, 560Ω | |
| 24, 7, 8, 22 | PA1, PA6, PA7, PC5 | **spare ×4** | — | PA6/PA7 are ADC-capable — spares keep analog options open |
| 4 / 3 / pad | VDD / GND / pad | 3V3 / GND / GND | | pad to GND (Microchip recommendation) |

Board temperature needs **no pin** — internal ADC channel with `SIGROW.TEMPSENSE0/1` calibration.

## 2. Block connections (every pin, every net)

### 2.1 USB-C input (J1) and VBUS
- J1 VBUS → **VBUS**; J1 GND → GND; J1 CC1 → R-cc-in-a (5.1k) → GND; J1 CC2 → R-cc-in-b (5.1k) → GND; D+/D− NC; shield → GND.
- **VBUS net**: C-vbus 10µF → GND; VBUS divider 1MΩ → node `VBUS_DIV` → 330kΩ → GND, `VBUS_DIV` → 100nF → GND and → **PA5 (pin 6)**.

### 2.2 Charger — TP4056 (U4)
| Pin | Net |
|---|---|
| 1 TEMP | **GND** (disables sensing — this part's documented method; never copy the MCP73871's biasing here) |
| 2 PROG | R-prog 1.2kΩ → GND (1A) |
| 3 GND, pad | GND |
| 4 VCC | VBUS |
| 5 BAT | **VBAT** (+ C-bat 4.7µF → GND) |
| 6 STDBY | `CHG_STDBY` = PB5 (pin 11), 10k↑ 3V3 |
| 7 CHRG | `CHG_CHRG` = PB4 (pin 12), 10k↑ 3V3 |
| 8 CE | `CHG_CE` = PC4 (pin 21) |

### 2.3 Battery and sense
- J3 (JST-PH) pin+ and **BAT pad** → VBAT; pin− and **GND pad** → GND. Same copper — the 2A limit is the plug's.
- VBAT divider: 1MΩ → `VBAT_DIV` → 330kΩ → GND; `VBAT_DIV` → 100nF → GND and → **PA4 (pin 5)**.

### 2.4 Power OR — Q1, Q2 (AON7407), Q3 (BSS138)
| Ref pin | Net |
|---|---|
| Q1 S (1-3) | **VSYS** |
| Q1 G (4) | `Q1_GATE`: 100kΩ → VSYS (pull-up); 100nF → VSYS (gate-source); 47kΩ → Q3 drain |
| Q1 D (5-8, pad) | VBUS |
| Q2 S (1-3) | VSYS |
| Q2 G (4) | `Q2_GATE`: → VBUS direct; 100kΩ → GND |
| Q2 D (5-8, pad) | VBAT |
| Q3 G (1) | `Q1_GATE_DRV` = PC3 (pin 20); 100kΩ → GND |
| Q3 S (2) | GND |
| Q3 D (3) | 47kΩ → `Q1_GATE` |

Body-diode orientation check (capture-time ERC): Q1 body diode conducts VBUS→VSYS; Q2 conducts VBAT→VSYS. **Source = VSYS on both is the whole safety argument** — a swapped D/S is the latch bug reborn.

### 2.5 Converter — TPS63020 (U3)
| Pin | Net |
|---|---|
| 1 VINA | VSYS **+ C16 100nF → GND** (TI reference design decouples VINA separately — found during KiCad transcription; the doc originally had it bare) |
| 2 GND | GND |
| 3 FB | `FB`: R-fb-low 180kΩ → GND; R-fb-hi-a 1MΩ → node `FB_MID` → R-fb-hi-b 620kΩ → **VOUT**; **JP2 solder jumper across R-fb-hi-b** |
| 4-5 VOUT | **VOUT** (+ 3× 22µF → GND) |
| 6-7 L2 | L1 inductor pin 2 |
| 8-9 L1 | L1 inductor pin 1 (1.5µH, Isat ≥ 4.5A) |
| 10-11 VIN | VSYS (+ 2× 10µF → GND) |
| 12 EN | `CONV_EN` = PA3 (pin 2); **100kΩ → GND** (defined during MCU reset) |
| 13 PS/SYNC | **GND** (power-save on — mandatory) |
| 14 PG | NC (datasheet: may be left open) |
| pad PGND | GND |

**JP2 open (ships): high-side = 1.62MΩ → VOUT = 500mV×(1+1620/180) = 5.00V. Closed: 1MΩ → 3.28V** (TI's own 3.3V values, Table 3). Divider draws ~2.8µA from VOUT — only while the converter runs, so standby is untouched. Both jumpers on the board ship open; open is always the default state.

### 2.6 Logic rail — XC6206 (U5)
IN (3) → VSYS + 1µF→GND; OUT (2) → **3V3** + 1µF→GND; VSS (1) → GND. *(Pin numbers: convention — verify at capture.)*

### 2.7 RTC — BM8563 (U1) + backup
| Pin | Net |
|---|---|
| 1 OSCI / 2 OSCO | Y1 32.768kHz crystal (CL per Belling — one cap on-die; confirm split at layout) |
| 3 INT | `RTC_INT` = PA2 (pin 1); **10kΩ ↑ 3V3** (deliberately not the backup node — see spec) |
| 4 VSS | GND |
| 5 SDA | `RTC_SDA` = PC0 (pin 17); 10kΩ ↑ 3V3 |
| 6 SCL | `RTC_SCL` = PC1 (pin 18); 10kΩ ↑ 3V3 |
| 7 CLKOUT | **NC** (open-drain; firmware writes FE=0 at init — ships enabled) |
| 8 VDD | `RTC_VDD` node + 100nF → GND |

**`RTC_VDD` diode-OR**: D3 (1N4148WS) anode → 3V3, cathode → RTC_VDD. D4 (1N4148WS) anode → **VBACKUP pad**, cathode → RTC_VDD. **JP1 + R-chg 1kΩ**: 3V3 → R-chg → JP1 → VBACKUP pad (ships open; close only for supercap).

### 2.8 MCU (U2), LEDs, button, UPDI, host connector
- U2 VDD (4) → 3V3 + 100nF→GND; GND (3) + pad → GND. All signal pins per §1.
- **J4 (JST-SH/STEMMA)**: 1 GND, 2 **NC** (VCC position — deliberate), 3 SDA → PB1, 4 SCL → PB0. **No pull-ups fitted on this bus.** *(Confirm J4 pin order against the chosen connector's datasheet at capture — SH pin-1 orientation varies by mounting.)*
- **D1 (Power LED, bicolor red/green, common-cathode → GND)**: anode A ← 560Ω ← PB2 (14); anode B ← 560Ω ← PB3 (13).
- **D2 (Battery LED)**: anode A ← 560Ω ← PB6 (10); anode B ← 560Ω ← PB7 (9).
- **SW1**: PC2 (19) → SW1 → GND (internal pull-up).
- **UPDI header**: 1 UPDI → PA0 (23), 2 3V3, 3 GND.

### 2.9 USB-C output (J2) and VOUT header
- J2 VBUS → VOUT; J2 GND → GND; CC1 → R-cc-out-a 56kΩ → VOUT; CC2 → R-cc-out-b 56kΩ → VOUT (Rp to the 5V rail); D± NC.
- VOUT/GND raw header pads → VOUT / GND.

## 3. Capture-time checklist (each item cites its source)

1. **Q1/Q2 source = VSYS** — swapped D/S recreates the unplug latch (spec §OR stage).
2. `EN` and `PS/SYNC` **must not float** (TI pin table) — both are tied here; keep it that way through edits.
3. TP4056 `TEMP` grounded; **never** carry the MCP73871 `THERM` idiom over (spec, claims row 25).
4. Rp pulls to **VOUT**, not 3V3/5V-fixed — in 3.3V mode the out-of-spec advertisement is documented (guide 5.4).
5. `INT` pull-up to **3V3**, not VBACKUP (claims row 39).
6. Both solder jumpers **ship open**; open = safe/default in every case.
7. Exposed pads: U2→GND, U3→PGND, U4→GND, Q1/Q2 pad = drain (net check!).
8. Crystal guard ring; keep the 2.4MHz converter's L1 loop away from OSCI/OSCO.
9. XC6206, BSS138, J4 pin orders: **verify against the actual LCSC footprints** before ordering (flagged in §0).
