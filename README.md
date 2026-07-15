# PowerMOD

A generic power scheduler, UPS, and battery supply for I2C-capable hosts — Linux SBCs, microcontrollers, anything with a 3.3V I2C bus and a power input to control. Real-time clock, scheduled power-cycling, battery backup with load switchover, opt-in watchdog, and an event log, at a component cost of ≈$2.90.

**Status: design complete on paper. No hardware exists yet.** Every part is selected, priced, and datasheet-verified; every net is mapped pin-for-pin; the register map is ready for firmware review. Next step: transcribe the netlist into an EDA tool and lay out the board.

## Documents

| File | What it is |
|---|---|
| [powermod-spec.md](powermod-spec.md) | **The source of truth.** Full decision record with reasoning history — including reversed decisions, retained and marked. Carries the net map, the semantic-review findings, and a 45-claim verification register (every part capability cited to its datasheet; 18 claims were false and each correction is documented) |
| [powermod-user-guide-draft.md](powermod-user-guide-draft.md) | Draft user manual — integration guide, LED states, scheduling patterns, FAQ, and honest limits (drift table, output-current table, weak-supply behavior) |
| [powermod-register-map.md](powermod-register-map.md) | I2C protocol v1 — 32 registers, wire-level reference for host integration and firmware |
| [powermod-schematic.md](powermod-schematic.md) | Pin-exact netlist — every component pin to every net, MCU pin assignment, capture-time checklist. The EDA schematic transcribes this |
| [powermod-bom.md](powermod-bom.md) | Bill of materials — LCSC part numbers, verified prices, do-not-substitute notes, sourcing flags |
| [powermod_full_state_machine.svg](powermod_full_state_machine.svg) | Power state machine — all states, transitions, and gating rules |

## Open items (all require hardware)

Converter efficiency, standby current, the `CE` battery-detect decay test, factory-reset gesture feel, Q1/Q2 handover scope check.
