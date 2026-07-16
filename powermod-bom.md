# PowerMOD — Bill of Materials (v1 hardware)

Last updated: 2026-07-15
Status: **Draft, walked line-by-line 2026-07-15 (three findings: missing VBUS bulk, missing `INT` pull-up, and the `CE` timing claim falsified by this BOM's own values). Prices verified on LCSC 2026-07-15 at the stated tier unless marked ~estimated.**
Sources of truth: `powermod-spec.md` §Pre-BOM electrical walk (the net map this BOM implements) and §Appendix (claims register — every part capability cited there). This document adds nothing to the design; it is the transcription the spec was written to make boring.

---

## 1. Semiconductors — all datasheet-verified, all priced

| Ref | Part | Package | LCSC | Qty | Unit @100–150 | Role |
|---|---|---|---|---|---|---|
| U1 | **BM8563** (Shanghai Belling) | TSSOP/SOP-8 | [C194063](https://www.lcsc.com/product-detail/Others_Shanghai-Belling-BM8563_C194063.html) | 1 | **$0.056** | RTC, PCF8563-class. **Reversed from RV-3028 (−$1.67)**. Belling's own datasheet gate-verified (claims row 44, closed); GATEMODE C269877 ($0.108) is the equally-verified alternate |
| U2 | **ATTINY1617-MNR** (Microchip) | VQFN-24 4×4 | [C614176](https://www.lcsc.com/product-detail/C614176.html) | 1 | **$0.93** ⚠ see sourcing | MCU. 18 of 22 I/O used, 4 spare |
| U3 | **TPS63020DSJR** (TI) — adjustable, **not** 63021 | VSON-14 | [C15483](https://www.lcsc.com/product-detail/C15483.html) | 1 | **$0.54** | Buck-boost, 5V/3.3V out, load disconnect = host switch |
| U4 | **TP4056** (TPOWER) | ESOP-8 | [C382139](https://www.lcsc.com/product-detail/Battery-Management-ICs_TPOWER-TP4056_C382139.html) | 1 | **$0.084** | 1A LiPo charger, behind the OR |
| U5 | **XC6206P332MR-G** (Torex) | SOT-23 | [C5446](https://lcsc.com/product-detail/Dropout-Regulators-LDO_Torex-Semicon-XC6206P332MR_C5446.html) | 1 | **$0.096** | 3.3V logic rail. Iq 1µA |
| Q1, Q2 | **AON7407** (AOS) | DFN-8 3×3 | [C176756](https://www.lcsc.com/product-detail/C176756.html) | 2 | **$0.174 ×2** | Power-OR PFETs. 12.5mΩ @ Vgs −2.5V |
| Q3 | **BSS138** (onsemi) | SOT-23 | [C52895](https://www.lcsc.com/product-detail/MOSFET_FAIRCHILD_BSS138_BSS138_C52895.html) | 1 | ~$0.01 | Q1 gate level-shifter |

**Semiconductor subtotal: ≈ $3.74**

### ⚠ Do-not-substitute notes (each one is a documented failure mode)

- **U4 `TEMP` pin is GROUNDED.** The opposite of the MCP73871 this design once used — grounding *that* part's `THERM` kills charging permanently. Both instructions live in the spec; neither transfers.
- **Q1/Q2 substitutes must specify Rds(on) at Vgs = −2.5V.** AO4407A (`Vgs(th)`=3V) passes every bench test and fails in the field as the cell ages — it is **fully off** at the −3.0V worst case. Also note AON7407's `VGS` limit is **±8V**, not the usual ±20V.
- **U3 must be the adjustable TPS63020** — the 5V/3.3V jumper needs the external FB divider; the fixed-output 63021 cannot do it. `PS/SYNC` ties **low** (power-save on) or light-load efficiency collapses.
- **U5 clones ("662K", from $0.0074) and U4 clones are legitimate second sources — qualify the specific vendor's part, not the number.**
- **U1's `CLKOUT` ships ENABLED at 32kHz** (open-drain, burns backup-scale current, radiates) — firmware disables it unconditionally at init. Delivery-default trap #3; the RV-3028's `BSM`/`TCE` traps died with the part swap.
- **U1 substitutes must be checked for the 6.5V-independent I2C pin rating** (claims row 41) — the diode-OR's legality rests on it.

## 2. Power passives — values from the TI/TP4056 datasheets

| Ref | Value | Spec | Qty | Unit ~est | Note |
|---|---|---|---|---|---|
| L1 | **1.5µH** | **Isat ≥ 4.5A**, low-DCR power inductor | 1 | ~$0.15 | TPS63020 reference design. **Isat is the spec that matters** — the switch limit is 4A typ/4.5A max |
| C-in | 10µF X5R ≥10V | 0805 | 2 | ~$0.02 | TPS63020 input, per datasheet |
| C-out | 22µF X5R ≥10V | 0805/1206 | 3 | ~$0.05 | TPS63020 output, per datasheet |
| C-bat | 4.7µF | 0603 | 1 | ~$0.01 | TP4056 `BAT` — **required for no-battery stability and the `CE` test** (with the 1.33MΩ divider it sets the test's τ≈6.2s — hence the 500ms decay-delta method) |
| **C-vbus** | **10µF X5R ≥10V** | 0805 | 1 | ~$0.02 | **Added by the BOM walk** — VBUS bulk: TP4056 `VCC` decoupling + hot-plug damping. The net had no capacitance at all |
| C-ldo | 1µF | 0402/0603 | 2 | ~$0.01 | XC6206 in/out |
| C-adc | 100nF | 0402 | 2 | ~$0.005 | Divider sampling reservoirs (VBAT, VBUS) |
| C-gate | 100nF | 0402 | 1 | ~$0.005 | Q1 gate-source (τ ≈ 5ms with R-gate) |
| C-vdd | 100nF | 0402 | 4 | ~$0.005 | Decoupling: U1, U2, U4, **U3 `VINA` (TI ref design — added at KiCad transcription)** |
| **Y1** | **32.768 kHz crystal**, CL per U1 (one oscillator cap is on-die — confirm CL split at layout) | 3215 | 1 | ~$0.08 | **New with the RTC reversal.** Guard-ring the layout |
| **D3, D4** | **1N4148WS** (silicon, nA leakage — deliberately not Schottky) | SOD-323 | 2 | ~$0.01 | RTC VDD diode-OR: D3←3V3, D4←backup pads. Legal per claims row 41 |
| **R-chg + JP1** | 1kΩ + solder jumper, **open by default** | 0402 | 1 | ~$0.002 | Supercap charge path. Open = coin-cell-safe; no register can close it |

## 3. Configured resistors — every value is load-bearing, from the net map

| Ref | Value | Net | Why this value |
|---|---|---|---|
| R-prog | **1.2kΩ 1%** | TP4056 `PROG` | Sets 1A charge current |
| R-cc-in ×2 | **5.1kΩ** | USB-C in CC1/CC2 (Rd) | Without these, **no USB-C charger ever powers the board** |
| R-cc-out ×2 | **56kΩ** | USB-C out CC1/CC2 (Rp) | Advertises Default (500/900mA) — deliberate under-advertise; the floor is ~1.0A |
| R-div ×4 | **1MΩ + 330kΩ** ×2 | VBAT→ADC, VBUS→ADC | **Identical ratios on purpose** — makes the Q1 comparison ratio-free. ~3.2µA / ~4µA |
| R-q1-pu | 100kΩ | Q1 gate → VSYS | Fail-safe: Q1 off, body diode carries (board degrades, never dies) |
| R-q1-s | **47kΩ** | Q3 drain → Q1 gate | Gate lands at 0.32×VSYS ⇒ Vgs ≈ −3.4V — **adequate by check, not luck** (part specified at −2.5V) |
| R-q2-pd | 100kΩ | Q2 gate → GND | Q2 on when VBUS absent |
| R-q3-pd | 100kΩ | Q3 gate → GND | MCU reset ⇒ Q1 off (defined state) |
| R-en-pd | **100kΩ** | TPS63020 `EN` → GND | **Defines the host rail during MCU reset.** Stated tradeoff: an MCU WDT reset power-cycles the host |
| R-pu ×5 | 10kΩ | `CHRG`, `STDBY`, internal SDA, SCL, **RTC `INT`** → 3V3 | TP4056 outputs and the RTC's `INT` are open-drain (datasheet: "requires pull-up resistor"). **`INT` pulls to 3V3, deliberately against the app manual's tie-to-VBACKUP advice** — an alarm asserting during a total outage would bleed the coin cell ~300µA into a pull-up serving a dead MCU |
| R-led ×4 | ~560Ω | LED cathodes ← MCU | ~2mA at Vf ≈ 2.1V |
| R28 | **100kΩ** | `CHG_CE` ↑ VBUS | **Charge-by-default (added 2026-07-16):** without it CE floats whenever PC4 is high-Z (reset, UPDI, unprogrammed MCU) — undefined charger state. Pull-up, not pull-down, so a dead-MCU board still charges; PC4 push-pull overrides. ~17µA only while on mains with PC4 driven low |
| R-fb ×3 | **180kΩ low; 1MΩ + 620kΩ high-side, JP2 across the 620k** | TPS63020 FB + jumper | **Closed at schematic (was TBD):** VFB=500mV → open = 5.00V (ships), closed = 3.28V (TI Table 3's own 3.3V values). ~2.8µA, only while the converter runs |

**Passives subtotal (all jellybean): ≈ $0.35**

## 4. Connectors and electromechanical — ~estimated, price at order

| Ref | Part | Qty | Unit ~est | Note |
|---|---|---|---|---|
| J1, J2 | USB-C receptacle, 16-pin, 5V-only class | 2 | ~$0.08 | Input and output — identical on purpose; silkscreen differentiates |
| J3 | JST **PH** 2-pin, top or side entry | 1 | ~$0.04 | Battery. **2A rating is the connector's, not the board's** |
| J4 | JST **SH** 4-pin (STEMMA-QT/Qwiic) | 1 | ~$0.06 | I2C. **Pin 4 (VCC position) is NC — deliberate** |
| SW1 | Tactile switch, SMD | 1 | ~$0.02 | The button |
| D1, D2 | **Bicolor LED, red/green only** | 2 | ~$0.04 | **Blue/white (Vf≈3V) have no headroom on a 3.3V rail** — this is a requirement, not a preference |
| — | UPDI: 3 pads or 1×3 header | 1 | ~$0.02 | Field firmware updates |
| — | **Paired** solder pads — BAT+GND, VOUT+GND, VBACKUP+GND (each interface with its ground adjacent); JP1 (backup charge) + JP2 (5V/3.3V) solder jumpers — **both ship open** | — | $0 | Copper |

**Connector subtotal: ≈ $0.38**

---

## 5. Rollup

| | @ ~100–150 |
|---|---|
| Semiconductors (LCSC-verified) | **$2.07** |
| Power passives + resistors (~est) | $0.45 |
| Connectors/electromech (~est) | $0.38 |
| **Component total** | **≈ $2.90** |

PCB and assembly excluded. For scale: after the RTC reversal the costliest chip is the MCU ($0.93), and the entire timing subsystem (RTC + crystal + diodes + jumper) is ~$0.20 — down from $1.73. The estimated lines are ~28% of the total, all jellybeans — the number is solid to ±$0.30.

## 6. Sourcing risks — the two ⚠ flags

- **U2 ATTINY1617-MNR: only 62 units in LCSC stock at the verified price.** The -MN variant is stocked deeper at $1.63 (+$0.70). Fallback is *not* the ATtiny1616 — it no longer fits (18 signals vs 17 free with `INT` fitted). Check stock at order time; the family is mainstream Microchip and this is a timing risk, not an availability risk.
- **U1 BM8563: both vendors now gate-verified from their own datasheets** (claims row 44, closed 2026-07-15 — Belling's PDF surfaced via M5Stack's mirror of belling.com.cn, and its electrical tables are byte-identical to GATEMODE's). **Primary: Belling C194063 ($0.056)**, with M5Stack's shipped volume as field evidence; **alternate: GATEMODE C269877 ($0.108)**. Commodity PCF8563-class silicon, NXP as the architecture reference — the former sole-source risk is fully retired.

## 7. Open at the bench — unchanged, and this BOM adds nothing to the list

Converter efficiency (sets the final ratings-table numbers), standby current, the `CE` battery-detect **decay-delta** test (~500ms; the "millisecond collapse" version was falsified on paper — τ≈6.2s), factory-reset gesture feel, Q1/Q2 handover scope check.
