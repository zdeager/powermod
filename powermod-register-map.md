# PowerMOD — I2C Register Map / Command Set

Last updated: 2026-07-15
Status: **Draft v1, protocol version 1. Ready for firmware implementation review.**
Source of truth: `powermod-spec.md`. This document defines the wire-level interface those decisions imply; where it had to decide something the spec left open, that is called out explicitly in the final section.

---

## 1. Conventions

> ### ⚠️ Electrical preconditions — read before wiring, not before coding
>
> **This document previously described the entire wire protocol without once stating the voltage it runs at.** A developer could implement every register correctly and destroy the board on first connection. The interface's electrical requirements belong in the interface document:
>
> - **3.3V logic only.** PowerMOD's I2C pins have an absolute maximum around 3.8V. **A 5V bus damages the board** — not "fails", damages. 5V hosts need a bidirectional level shifter. See spec §Interface.
> - **PowerMOD fits no pull-up resistors.** The host's pull-ups define the bus voltage. PowerMOD only ever pulls the lines low and never drives them high, so it cannot impose a voltage on your bus — and equally cannot protect itself from one.
> - **The 4th pin on the STEMMA-QT connector (the VCC position) is not connected — decided 2026-07-15, no longer a schematic-time question.** PowerMOD cannot use a host's 3.3V (its logic must run while the host is unpowered — that's the product), and it must not *drive* that pin either: paralleling its LDO with the host's own 3.3V rail invites backfeed and regulator contention on someone else's board. NC is the only option that is safe against every host. **Consequence for integrators: PowerMOD does not power your Qwiic/STEMMA chain** — the connector carries GND/SDA/SCL only.

**Address:** 7-bit, default `0x08`, configurable (`I2C_ADDRESS`, §7). Standard I2C, no clock stretching required.

**Access pattern:** write one byte (the register address) to set the pointer, then either continue writing (data bytes) or issue a repeated start and read. The pointer **auto-increments** on every byte read or written, so multi-byte fields and whole blocks can be transferred in a single transaction.

**Endianness: little-endian** for every multi-byte field. This matches the MCU's native byte order — the current **PY32F003 is a little-endian ARM Cortex-M0+**, and the earlier ATtiny was little-endian too, so firmware does no swapping either way — and the overwhelming majority of hosts (ARM, x86). Stated explicitly because getting it wrong is silent and produces plausible garbage rather than an error.

**Reserved registers** read `0x00` and ignore writes. Do not rely on this — a future protocol version may define them.

**Magic values on commands.** Every register that *does* something when written (power-off request, commits, watchdog kick, factory reset) requires a specific non-trivial value rather than "any write." A stray pointer-only write, a bus glitch, or a host writing `0` to the wrong address should never cut power. Writing any other value to a command register is ignored.

**Every magic value means exactly one thing — this is a rule, not a coincidence, and an earlier draft broke it.** `0x5A` was previously the "go" value for **three** commands at once: `WAKE_CONTROL` commit, `POWER_OFF_REQUEST`, *and* `CONFIG_COMMIT` — **which also lived at address `0x5A`.** That defeats the protection above rather than providing it:

- **`CONFIG_COMMIT` (`0x5A`) sits two addresses from `POWER_OFF_REQUEST` (`0x58`).** "Write `0x5A` to `0x5A`" with a two-byte pointer slip **cut power**.
- **Every host's shutdown routine writes the same byte twice** — commit the wake time, then request power-off. Getting the two address constants wrong cut power *with no wake armed*, stranding the device: exactly the failure the max-sleep safety net exists to catch.

**With values distinct, an address error becomes a no-op instead of an action** — a wrong-address write carries the wrong magic and is ignored. That is the entire value of the rule, and it only works if no byte can mean two things:

| Value | Means, and only means |
|---|---|
| `0x5A` | commit the staged wake time (`WAKE_CONTROL`) |
| `0xC1` | clear the armed wake (`WAKE_CONTROL`) |
| `0x3C` | **cut power** (`POWER_OFF_REQUEST`) |
| `0xA5` | declare the host alive (`WATCHDOG_KICK`) |
| `0xC0` | commit staged configuration (`CONFIG_COMMIT`) |
| `0xDF` | restore factory defaults (`CONFIG_COMMIT`) |
| `0x44` | discard staged changes (`CONFIG_COMMIT`) |

### 1.1 Read atomicity — latch-on-first-byte

**A gap the spec didn't cover.** The spec carefully defines *write* atomicity (staging-and-commit, §Schedule) but says nothing about *reads*, and PowerMOD exposes a live-incrementing 32-bit counter. A naive sequential read of `RTC_TIME` can tear: read the low bytes at `0x0FFFFFFF`, the counter rolls to `0x10000000`, read the high bytes, and the host gets a timestamp off by 256 seconds — plausible, wrong, and undetectable.

**Rule: reading the first byte of any multi-byte field latches a coherent snapshot of that entire field.** Subsequent sequential reads return the latched copy. **The latch is released when the pointer leaves the field *or at the end of the transaction (STOP), whichever comes first — a latch never outlives its transaction.*** Applies to: `RTC_TIME`, `WAKE_TIME_COMMITTED`, all telemetry words, all delay/timeout words, and the event log as one block (§10).

**Why the STOP release matters (semantic review, 2026-07-15 — the original rule had a hole):** the I2C pointer persists across transactions, so "released when the pointer leaves the field" alone meant a host that read `0x10` by itself, stopped, and came back minutes later for `0x11`–`0x13` would receive **three latched bytes from minutes ago, spliced onto a stale first byte it already had — a coherent-looking timestamp, silently wrong by the entire gap, undetectable.** The partial read would have poisoned the later one. With the STOP release, the later read simply gets unlatched live bytes — mid-field, still not *safe*, but now covered by the existing warning below instead of silently sanctified by the latch.

Practical consequence for hosts: **read a multi-byte field in one transaction, starting at its first byte.** Reading `0x11..0x13` alone (skipping `0x10`) returns unlatched bytes and is not safe.

---

## 2. Address map overview

| Range | Block | Access |
|---|---|---|
| `0x00`–`0x0F` | Identity and status | RO |
| `0x10`–`0x1F` | Real time clock | RW |
| `0x20`–`0x2F` | Schedule | RW |
| `0x30`–`0x3F` | Telemetry | RO |
| `0x40`–`0x57` | Configuration (staged) | RW |
| `0x58`–`0x5F` | Commands and commit | W / RO |
| `0x60`–`0x88` | Event log | RO |

---

## 3. Identity and status (`0x00`–`0x0F`, read-only)

| Addr | Name | Type | Notes |
|---|---|---|---|
| `0x00` | `PROTOCOL_VERSION` | uint8 | **`1`**. Increments only when this register map changes incompatibly. Check once at integration time. |
| `0x01` | `FIRMWARE_REVISION` | uint8 | 1–255. Increments on every firmware build. Changes freely without affecting `PROTOCOL_VERSION`. |
| `0x02` | `STATUS` | bitfield | See below. |
| `0x03` | `SHUTDOWN_PENDING_REASON` | enum | Why a shutdown is in progress. Valid only while `STATUS.SHUTDOWN_PENDING` is set; otherwise `0x00`. Uses the power-off enum (§8). |
| `0x04`–`0x05` | `SHUTDOWN_REMAINING` | uint16 | Tenths of a second until power is actually cut. Valid only while `STATUS.SHUTDOWN_PENDING` is set. |
| `0x06` | `LAST_POWER_OFF_REASON` | enum | Why PowerMOD last cut power. Power-off enum (§8). **Not overwritten by a wake.** |
| `0x07` | `LAST_POWER_ON_REASON` | enum | Why PowerMOD last powered the host. Power-on enum (§8). |
| `0x08` | `LAST_OFF_WAS_LOW_VOLTAGE` | uint8 | `0` or `1`. The coarse flag from the spec — redundant with `0x06`, kept for hosts whose logic only needs this one question answered. |

Two separate reason registers rather than one, per spec: booting is itself an event, so a merged register would have its power-off value destroyed by the wake that let the host read it.

### `STATUS` (`0x02`) bitfield

| Bit | Name | Meaning |
|---|---|---|
| 0 | `MAINS_PRESENT` | `1` = running from mains input, `0` = running from battery |
| 1 | `BATTERY_PRESENT` | `1` = a battery is connected. **Re-based 2026-07-15 — the charger was reversed to TP4056 + PFET OR and this bit lost its hardware.** Was decoded from MCP73871's `STAT1`/`STAT2`/`PG`; TP4056 has no such function. **Now a firmware test: pull TP4056's `CE` low and run a ~500ms decay-delta test on VBAT — an absent cell's node sags ~300mV in 500ms (τ≈6.2s through the sense divider — the "collapses in milliseconds" first written here was falsified by the BOM walk), a real cell moves <1mV.** Still separates *absent* from *deeply discharged*, which was always the requirement. **The bit's contract to the host is unchanged; only its mechanism is.** Unvalidated on hardware — see spec §Charger and power path — REVERSED. Sampled periodically while on mains (each test pauses charging for milliseconds; the duty-cycle cost is negligible), so a hot-swapped cell is noticed without a reboot. |
| 2 | `SHUTDOWN_PENDING` | `1` = delay-before-cut timer running; see `0x03`/`0x04` |
| 3 | `RTC_VALID` | `0` = the RTC has lost power since time was last set — **do not trust it for absolute scheduling** |
| 4 | `WAKE_ARMED` | `1` = a committed wake **that has not yet fired** exists — future, **or already due but held awaiting usable power** (battery below recovery, no mains; §5.1). "Armed" answers *will something happen*, and for a held wake the answer is yes |
| 5 | `CHARGING` | `1` = battery is currently being charged |
| 6 | `CHARGE_COMPLETE` | `1` = charge terminated, battery full (TP4056 `STDBY`). **Assigned 2026-07-15** — the pin was already read every second to drive the Battery LED's "full" state, so the protocol was hiding a state the LED showed. Resolves the ambiguity of `CHARGING = 0` alone, which means *full or on-battery or paused*. (This bit was previously reserved, ex-`CHARGE_SUSPENDED_TEMP` — note PowerMOD still has **no battery** temperature sensing; `BOARD_TEMPERATURE` at `0x34` is the *board's*, spec §Charging below freezing stands) |
| 7 | `CONFIG_DEFAULTED` | `1` = configuration failed its CRC at boot and factory defaults are in use |

> **Divergence from Witty Pi, deliberate.** Their register #7 encodes `0` = mains, `1` = battery. `MAINS_PRESENT` is the opposite polarity. The spec already noted their numbering varies by model/revision, so there was no stable convention to inherit; a positively-named bit that reads `1` when the thing it names is true is worth more than false compatibility with a moving target.

---

## 4. Real time clock (`0x10`–`0x1F`)

| Addr | Name | Type | Access | Notes |
|---|---|---|---|---|
| `0x10`–`0x13` | `RTC_TIME` | uint32 | RW | Unix epoch seconds, unsigned (wraps 2106). Latched on read (§1.1). |

**The RTC hardware changed under this format (2026-07-15) and the format survives.** ~~RV-3028's native UNIX counter made epoch seconds a pass-through~~ — the BM8563 (PCF8563-class) that replaced it stores **BCD calendar registers**, so firmware now converts (~30 lines, epoch↔BCD, a solved problem). The host-facing contract is identical: `RTC_TIME` is uint32 epoch seconds, latched per §1.1.

**Firmware read coherency, re-derived for the new part:** the BM8563 has no read latch of its own — the clock runs during a burst read, so a read spanning a seconds rollover can tear across the BCD registers. **Firmware reads the full time block twice and compares** (the same discipline the RV-3028's manual prescribed, needed here for a different reason), and only a stable pair is converted and served to the host. The old part's `0xFFFFFFFF`-on-bus-timeout hazard is gone with the part; the BCD path's equivalent guard is rejecting any register pair that fails twice — a wedged internal bus yields a stale-but-sane time plus `RTC_VALID` handling, never a plausible-garbage timestamp.

**Wake alarms are minute-granular in this part, and the seconds-exact API is preserved in firmware:** the committed wake time arms the minute alarm; on that interrupt, firmware loads the 0–59s residue into the **1Hz countdown timer** (register `0Fh`, source verified) and the true wake fires on its interrupt. Hosts see nothing different.

**Writing `RTC_TIME` automatically clears `STATUS.RTC_VALID`'s error condition** (i.e. sets the bit to `1`). No separate "clear the power-loss flag" step — a host that just set the time has, by definition, made it valid, and requiring a second write only creates a step to forget. The underlying hardware flag (BM8563 `VL`, "voltage low" — bit 7 of the Seconds register) is cleared by firmware as part of the write.

**RTC writes are direct, not staged** — deliberately, unlike the wake time and configuration. Rationale: RTC time is not persisted state that can be silently corrupted and then acted on for months. A torn write produces a wrong clock that the host can immediately read back and correct, and in relative-time mode (spec §RTC default state) it does not matter at all. The staging machinery exists to protect values whose corruption survives a power cycle; this isn't one.

---

## 5. Schedule (`0x20`–`0x2F`)

| Addr | Name | Type | Access | Notes |
|---|---|---|---|---|
| `0x20`–`0x23` | `WAKE_TIME_STAGING` | uint32 | RW | Unix epoch seconds. Writing here has **no effect** until committed. |
| `0x24` | `WAKE_CONTROL` | cmd | W | `0x5A` = commit staged value. `0xC1` = clear any armed wake. |
| `0x25`–`0x28` | `WAKE_TIME_COMMITTED` | uint32 | RO | The currently stored wake time. Latched on read. |
| `0x29` | `WAKE_STATUS` | enum | RO | `0` = none, `1` = armed (includes a due wake held for usable power), `2` = expired-at-commit |

### 5.1 Commit semantics — this is where past-vs-future is decided

Per the spec's resolution of the missed-wake/past-wake contradiction, **the timestamp is evaluated exactly once, at commit**, and never re-evaluated afterward:

- **Staged value is in the future at commit** → `WAKE_STATUS` = `1` (armed). It fires when due, or immediately on power restore if it came due while PowerMOD had no power to act.
- **Staged value is already in the past at commit** → `WAKE_STATUS` = `2` (expired). **It never fires**, and `STATUS.WAKE_ARMED` stays `0`.

This is not validation and the write is never rejected. Any well-formed timestamp is accepted; commit only records what it *means*. A host can read `WAKE_STATUS` immediately after committing to find out which case it got — which is the cheapest possible way to catch a timezone or overflow bug at integration time, and is worth doing during bring-up even if you never check it in production.

An interrupted staging write leaves `WAKE_TIME_COMMITTED` untouched. Commit itself is a single-byte write and is therefore atomic on the wire.

`WAKE_CONTROL = 0xC1` (clear) is separate from committing a new time, per spec — for a host that wants to cancel without supplying a replacement.

---

## 6. Telemetry (`0x30`–`0x3F`, read-only)

| Addr | Name | Type | Notes |
|---|---|---|---|
| `0x30`–`0x31` | `BATTERY_MILLIVOLTS` | uint16 | Raw battery voltage, mV. No state-of-charge estimation (spec: no fuel gauge). Reads `0` when no battery is present. |
| `0x32`–`0x33` | `INPUT_MILLIVOLTS` | uint16 | VBUS voltage, mV. **Adopted 2026-07-15** into the bytes reserved for it — the measurement has existed since the charger reversal (it drives `MAINS_PRESENT` and the Q1 decision); exposing it is a register, not hardware. Reads `0` with no input. **The weak-supply diagnostic**: sagging under load = undersized supply (guide §2) |
| `0x34` | `BOARD_TEMPERATURE` | int8 | Board temperature, °C, signed (−40…+85). **Sensor source migrated with the MCU (instock-parts branch):** the ATtiny's factory-calibrated die sensor (`SIGROW.TEMPSENSE0/1`) does **not** exist on the PY32F003 — firmware instead reads the PY32's internal temperature-sensor ADC channel. **Datasheet-confirmed (Rev 1.7, Table 5-24):** the sensor exists (slope 2.3–2.7 mV/°C, ±1–2 °C linearity) but has **no factory-cal registers** and a wide part-to-part offset (V₃₀ = 0.742–0.785 V ⇒ ~±9 °C) — so an **uncalibrated reading is only ~±10 °C absolute**. Firmware should apply a one-point runtime calibration (store an offset measured at a known temperature) to tighten this; the register is exposed as a coarse enclosure trend, not a precise number. **This is the board's temperature, NOT the battery's** — it does not qualify charging (spec §Charging below freezing stands unchanged); it exists so an outdoor host can evaluate the RTC drift table and the charge-temperature hazard with data instead of guesses |

**PowerMOD reports what it already measures — battery voltage, input voltage, and board temperature — and nothing more.** ~~Battery voltage is the only voltage reported~~ (true until the 2026-07-15 metrics review; the sentence outlived two of its three words). All three are load-bearing for PowerMOD's own operation — cutoff/recovery, mains detection and the Q1 decision, and the drift/charging-hazard context — so exposing them is genuinely free, which is the rule.

**Input voltage is not exposed in protocol v1 — but the reason changed twice in one day, and the current reason is a decision, not a limitation.** The history matters enough to keep straight:

1. **An earlier draft defined `INPUT_MILLIVOLTS` at `0x32`**, assuming mains detection was an ADC read that the number could ride on.
2. **Checked, and it failed:** the then-selected power-path charger (MCP73871) detected input internally and reported a **digital** `PG` output — no input ADC existed, so the register was removed as "not free."
3. **Then the charger was reversed (TP4056 + PFET OR, spec §Charger and power path — REVERSED), and mains detection became a VBUS divider on an ADC-capable pin — the exact hardware whose absence killed the register.** The measurement is genuinely free again, and the spec has formally **reopened** input-voltage telemetry (see spec §Telemetry scope, "REOPENED").

~~It stays out of protocol v1 anyway~~ **Adopted 2026-07-15 after a metrics review** — the deferral was "don't adopt mid-reversal," and the reversal is long since settled and verified. `0x32`–`0x33` carry it, exactly as reserved. Output-voltage telemetry was re-examined per the standing rule at the same time and **stays dropped: it still needs a divider and an ADC channel that do not exist** — the "already free" rule cuts the other way there. (Original deferral text:): adopting a register in the same breath as an architecture reversal is how scope creeps in unexamined, and the spec ties its adoption to reconsidering output-voltage telemetry at the same time. **If adopted, `0x32`–`0x33` is reserved for it** — do not assign those bytes to anything else. `STATUS.MAINS_PRESENT` (now sourced from that same VBUS divider) remains the supported way to ask the presence question.

**Output voltage and output current are likewise not exposed** — no PowerMOD function measures either, so both would require sensing hardware added purely for telemetry (spec §Telemetry scope).

`0x32`–`0x3F` are reserved.

---

## 7. Configuration (`0x40`–`0x57`)

All configuration registers are **staged**: writes land in a RAM shadow and take effect only on `CONFIG_COMMIT` (§8). Reads return the staged (pending) values, not the persisted ones — so a host can read back exactly what it is about to commit.

**Three rules that close the stale-staging hole (semantic review, 2026-07-15).** As originally written, a host that staged values and crashed *without losing power* (a soft reboot — PowerMOD stays up and cannot tell) would boot, read the config block, and see its own **uncommitted leftovers presented as if they were the running configuration** — with no way to read the active values at all. Therefore:
1. **The staging buffer is discarded whenever host power is cut**, for any reason. A freshly powered host always reads active configuration.
2. **`CONFIG_STATUS` reports `5` = uncommitted staged changes present** — differing from active — so a soft-rebooted host can detect the leftovers it cannot otherwise see.
3. **`CONFIG_COMMIT = 0x44` discards all staged changes**, reverting reads to active values. Without this, a host detecting state `5` would have no way out: it cannot re-write the active values (it can't read them through the stale stage), and committing unknown leftovers is worse.

| Addr | Name | Type | Default | Notes |
|---|---|---|---|---|
| `0x40` | `POWER_ON_MODE` | enum | **`2`** | `0` = Always OFF, `1` = Always ON, `2` = Restore previous state |
| `0x41` | `LOW_VOLTAGE_THRESHOLD` | uint8 | **`30`** | Volts × 10 (3.0V). **Cut** power below this. Valid `30`–`42`. `0` = disabled. |
| `0x42` | `CRITICAL_VOLTAGE_THRESHOLD` | uint8 | **`33`** | Volts × 10 (3.3V). Battery LED shows its critical-warning pattern below this — an early warning *before* the cutoff fires. Valid `30`–`42`. `0` = disabled (no warning state). |
| `0x43` | `RECOVERY_VOLTAGE_THRESHOLD` | uint8 | **`36`** | Volts × 10 (3.6V). **Re-enable** power above this. Valid `30`–`42`. `0` = disabled. |
| `0x44`–`0x45` | `DELAY_HOST_REQUESTED` | uint16 | **`0`** | Tenths of a second before cutting after `POWER_OFF_REQUEST`. **Defaults to 0** — the host only sends this once it is already finished, so there is nothing to wait for, and a halted host is still drawing current while you wait (spec §Minimum off-duration). Raise only if your host has a specific settle requirement. |
| `0x46`–`0x47` | `DELAY_FORCED` | uint16 | **`300`** | Tenths of a second (30.0s) before cutting after a button press, low-voltage cutoff, or watchdog expiry. |
| `0x48`–`0x4B` | `MAX_SLEEP_SECONDS` | uint32 | **`0`** | Forced wake after this long asleep. `0` = disabled. |
| `0x4C`–`0x4D` | `WATCHDOG_TIMEOUT` | uint16 | **`0`** | Seconds. `0` = disabled. See §9. |
| `0x4E` | `I2C_ADDRESS` | uint8 | **`0x08`** | Takes effect only after a full power cycle, and requires updating host-side code to match. |
| `0x4F`–`0x50` | `MIN_OFF_DURATION` | uint16 | **`50`** | Tenths of a second (5.0s). Minimum time power stays **off** before any trigger may re-power the host. `0` = disabled. **A different mechanism from the two delays above** — see §7.1. |

`0x51`–`0x57` are reserved for future configuration. (`0x51` was briefly `BACKUP_TRICKLE`, added and removed the same day — see §11 item 15. **Do not reassign it in protocol v1**; a stale host writing the old meaning must hit a reserved no-op, not a new feature.)

**The three voltage thresholds are deliberately adjacent** (`0x41`–`0x43`), and read in the order a discharging cell meets them: **critical warning (3.3V) → cutoff (3.0V) → recovery (3.6V) before power returns.** They were not adjacent in an earlier draft, and **the critical one did not exist at all** — the Battery LED promised a warning state with no trigger behind it. Grouping them is not cosmetic: this design's recurring failure has been *adjacent-but-different things being conflated when documented apart* (delay-before-cut vs. minimum-off-duration; the load switch vs. the power path). Three registers describing one voltage axis belong in one place.

**Commit rejects an invalid configuration atomically.** If any staged value is out of range, `CONFIG_COMMIT` writes nothing and reports `3` (invalid) in `CONFIG_STATUS`. Partial application is never possible.

**Cross-field rule: whichever of the three voltage thresholds are enabled must satisfy `LOW < CRITICAL < RECOVERY`.** A commit violating this is rejected whole. (Each may be disabled with `0` independently; the rule applies only among those that are enabled.)
- `RECOVERY > LOW` — the original rule. Recovery at or below cutoff reintroduces the oscillation the split exists to prevent.
- `CRITICAL > LOW` — **a warning that fires at or below the cutoff is not a warning.** The whole point is to give an operator a chance to act *before* power is pulled; set it under the floor and the LED goes critical at the same instant the host dies.
- `CRITICAL < RECOVERY` — otherwise a device that has just recovered immediately re-enters the critical-warning state, reporting an alarm about the recovery that just succeeded. Rationale: recovery at or below cutoff reintroduces precisely the cut/recover/cut oscillation the two-threshold design exists to prevent, at the moment the battery is least able to tolerate it. Unlike a wake time — where both absolute and relative values are legitimate and PowerMOD cannot know which is intended — there is no intent under which an inverted pair is meaningful. This is the same class of check as the range validation above, not a departure from the hands-off principle (which governs *schedule* writes, per spec §Invalid/past schedule write).

**Ordering is enforced; adequate margin is advice.** `recovery = cutoff + 0.1V` passes validation but is poor practice — boot current can sag the rail more than that, so the oscillation returns. **Recommended margin ≥ 0.3V; the defaults give 0.6V.** Rejecting the impossible while advising on the merely unwise matches the proportionate response used elsewhere in this design (silkscreen labelling for the voltage jumper and port swap, rather than lockout circuitry).

**Change both thresholds in one commit when raising both.** Because validation runs against the whole staged block, a host that commits `LOW_VOLTAGE_THRESHOLD = 38` while the *persisted* `RECOVERY_VOLTAGE_THRESHOLD` is still `36` gets a spurious rejection. Stage both, then commit once. Configuration reads return staged values precisely so this can be checked before committing.

**Either threshold may still be disabled independently** (`0`), and disabling is never blocked by the cross-field rule:
- `LOW_VOLTAGE_THRESHOLD = 0` — no cutoff. Opting out of over-discharge protection; see §11.
- `RECOVERY_VOLTAGE_THRESHOLD = 0` — a legitimate configuration, not a degraded one: after an emergency cutoff the host stays off until **mains** is supplied, never re-booting on battery recovery alone. Sensible where a device should not resume on a marginal cell without someone physically intervening.

**Both thresholds have no effect when no battery is present** (`STATUS.BATTERY_PRESENT = 0`). Mains-only mode has no voltage monitoring and no emergency cutoff, since there is no cell to protect (spec §Scope).

### 7.1 The three timing registers do different things — do not conflate them

They all count tenths of a second, which is exactly why they get confused. **Conflating two of them is how the minimum-off-duration gap survived an entire design review** (spec §Minimum off-duration): the "delay before power cut" register was adopted to solve a problem it does not touch, because the names were adjacent.

| Register | Governs | Fires when |
|---|---|---|
| `DELAY_HOST_REQUESTED` | request → power off | host wrote `POWER_OFF_REQUEST` |
| `DELAY_FORCED` | trigger → power off | button, low-voltage, or watchdog |
| **`MIN_OFF_DURATION`** | **power off → power on** | **any wake trigger, after any cut** |

The first two are **pre-cut** windows: how long the host keeps running after something decided to stop it. The third is a **post-cut** guard: how long the rails stay down before anything is allowed to bring them back. **A pre-cut delay of any length provides zero rapid-reboot protection** — that was the error.

`MIN_OFF_DURATION` applies to **every** wake path without exception: scheduled wake, missed alarm on power restore, button, watchdog recovery, max-sleep timeout, and power-restore under Always-ON or Restore-previous-state. It is invisible in normal operation — a scheduled wake is minutes or hours out — and engages only in the pathological cases the guard exists for.

### Encoding note: thresholds are in 0.1V, telemetry is in mV

A deliberate asymmetry, flagged because it is a footgun. The spec directs reusing Witty Pi's threshold encoding (volts × 10) rather than inventing one, and 0.1V granularity is adequate for a cutoff floor. Voltage *readings* use millivolts because 0.1V would be uselessly coarse for telemetry. **They are not interchangeable**: `LOW_VOLTAGE_THRESHOLD` of `32` and `BATTERY_MILLIVOLTS` of `3200` describe the same voltage.

---

## 8. Commands and commit (`0x58`–`0x5F`)

| Addr | Name | Access | Notes |
|---|---|---|---|
| `0x58` | `POWER_OFF_REQUEST` | W | Write `0x3C` to begin the host-requested power-off sequence. |
| `0x59` | `WATCHDOG_KICK` | W | Write `0xA5` to declare the host alive. See §9. |
| `0x5A` | `CONFIG_COMMIT` | W | `0xC0` = validate, persist and verify staged config. `0xDF` = restore factory defaults. `0x44` = discard staged changes (§7). |
| `0x5B` | `CONFIG_STATUS` | RO | `0` = OK, `1` = busy, `2` = write/verify failed, `3` = staged config invalid (rejected, nothing written), `4` = CRC failed at boot, running defaults, `5` = uncommitted staged changes present (§7) |

**`POWER_OFF_REQUEST` is named for what it does.** Per the spec's naming note, the user-facing concept stays "cut power now," but at this level it is a *request to begin the power-off sequence* — power is removed `DELAY_HOST_REQUESTED` later, not instantly. A firmware implementer reading "cut now" would reasonably expect an immediate rail drop.

**Only issue `POWER_OFF_REQUEST` once your shutdown is genuinely complete.** PowerMOD has no way to check and will not second-guess it.

### 8.1 Config commit sequence

`CONFIG_COMMIT = 0xC0` performs, in order: validate all staged values → write to the non-volatile config store → **read back and compare** → compute and store CRC → set `CONFIG_STATUS`. The read-back verify catches a failed write at the moment it happens; the boot-time CRC (below) is the independent safety net for corruption from any other cause. Both, per spec, because they catch different failures. **(MCU migration note, instock-parts branch:** the PY32F003 has **no EEPROM** — the config store is a reserved page of the MCU's own flash, emulated as byte storage. Endurance is ample: 100 k erase/write cycles at −40…+105 °C, 20-year retention. The one consequence for the host is under "survives a firmware update" — a full chip-erase reflash wipes this page unless the operator uses an application-only, config-preserving update; see the user guide §4.5.**)**

At boot, configuration is CRC-checked. On mismatch, PowerMOD **falls back to factory defaults and sets `STATUS.CONFIG_DEFAULTED`** rather than operating on corrupt values or refusing to boot.

`CONFIG_COMMIT = 0xDF` (factory reset) restores **configuration registers only**. **The I2C address is the one value that does not change immediately** — it follows the standing address rule (§7: effective at the next full power cycle), because reverting the bus address mid-session would disconnect the very host that issued the command, leaving it unable to even confirm the reset. It does not clear the event log or a pending wake time — same scope as the button-hold-during-power-up gesture (spec §Forgotten I2C address; guide FAQ 5.1 — the gesture is not described in this document), for the same reason: the log's whole purpose is surviving exactly the kind of event that makes someone reset a device.

### 8.2 Event reason enum (shared by all reason registers and the log)

One enum, used identically in `LAST_POWER_OFF_REASON`, `LAST_POWER_ON_REASON`, `SHUTDOWN_PENDING_REASON`, and every event-log entry. **Bit 7 = direction, bit 6 = informational** — so a log entry is self-describing and needs no separate direction field.

**Power-off events** (`0x00`–`0x3F`):

| Code | Name | Meaning |
|---|---|---|
| `0x00` | `NONE` | No power-off recorded (fresh board) |
| `0x01` | `HOST_REQUEST` | Host wrote `POWER_OFF_REQUEST` |
| `0x02` | `BUTTON` | Button tap — powered off after `DELAY_FORCED` |
| `0x03` | `LOW_VOLTAGE_CUTOFF` | Battery fell below `LOW_VOLTAGE_THRESHOLD` |
| `0x04` | `WATCHDOG_EXPIRY` | Watchdog timeout elapsed |
| `0x05` | `BUTTON_FORCED` | Button held ≥5s — cut immediately, delay bypassed |

**Informational events** (`0x40`–`0x7F`) — no power transition, log-only:

| Code | Name | Meaning |
|---|---|---|
| `0x40` | `SHUTDOWN_CANCELLED` | A button-initiated shutdown was cancelled by a second press, **or a watchdog-initiated shutdown was cancelled by a late kick (semantic review, 2026-07-15)** |
| `0x41` | `FACTORY_RESET` | Configuration was reset to defaults |

**Power-on events** (`0x80`–`0xBF`):

| Code | Name | Meaning |
|---|---|---|
| `0x80` | `NONE` | No power-on recorded |
| `0x81` | `SCHEDULED_WAKE` | Armed wake time came due |
| `0x82` | `MISSED_WAKE` | Armed wake came due while unpowered **or while power was unusable (battery below `RECOVERY_THRESHOLD`, no mains)**; fired when power became usable |
| `0x83` | `BUTTON` | Button press. **Not possible below the cutoff floor** — a press there does not boot (spec walk, 2026-07-15); between cutoff and recovery it does |
| `0x84` | `POWER_RESTORED` | Power became available; booted per `POWER_ON_MODE`. **Covers both mains arriving and battery voltage recovering past `RECOVERY_THRESHOLD` after an emergency cutoff** — an emergency cutoff records the host as ON, so Restore-previous re-boots it |
| `0x85` | `MAX_SLEEP_TIMEOUT` | `MAX_SLEEP_SECONDS` elapsed with no armed wake. **Held below the recovery threshold like any automatic wake**; fires when power is usable |
| `0x86` | `WATCHDOG_RECOVERY` | Re-powered after a watchdog-forced cycle |
| `0x87` | `FIRST_POWER_ON` | First ever power-up, or first after a total power loss |

### 8.3 Simultaneous wake priority — resolved

The spec required this ordering be "fixed and deterministic" and left the specific order to this document. **PowerMOD performs exactly one wake no matter how many trigger conditions are true at once**, and reports the highest-priority reason below:

| Priority | Reason | Why here |
|---|---|---|
| 1 (highest) | `WATCHDOG_RECOVERY` | Indicates a **fault**. An operator must never lose this to a coincident routine event — it is the difference between "working" and "silently rebooting every 40 minutes." |
| 2 | `BUTTON` | Explicit human action, and the only trigger a person directly caused. |
| 3 | `SCHEDULED_WAKE` | The normal, expected explanation. **Spec-mandated to outrank `MAX_SLEEP_TIMEOUT`.** |
| 4 | `MISSED_WAKE` | Same alarm as (3), distinguished by power having been unavailable. Cannot actually co-occur with (3) — both listed for completeness. |
| 5 | `MAX_SLEEP_TIMEOUT` | Informative (the host stranded itself), but it only fires *because* nothing better did. |
| 6 | `FIRST_POWER_ON` | **Added 2026-07-15 — see below.** Fires once in the device's life. Outranks `POWER_RESTORED`, which is true alongside it *every* time. |
| 7 (lowest) | `POWER_RESTORED` | Least specific: "there is power now." Almost always true alongside something better, which is exactly why it ranks last. |

Principle: **most-specific and most-fault-bearing wins**, per the spec. The frequent real case is `MISSED_WAKE` + `POWER_RESTORED` both becoming true at the same instant when power returns to a device with an overdue alarm; the ordering above reports the informative one.

**`FIRST_POWER_ON` was missing from this table until 2026-07-15.** The table claimed to define *the* order but ranked six of the seven wake reasons in the `0x8n` enum. It is not merely an omission, because `FIRST_POWER_ON` genuinely co-occurs:

- **With `POWER_RESTORED`, always.** Power became available is true on every first power-up, so this pair happens on **every device, on the bench, the first time anyone plugs it in** — the single most-observed boot in the product's life, and the reason code for it was unspecified.
- **With `BUTTON`, plausibly.** Holding the button while connecting power is the factory-reset gesture. So the one moment `FIRST_POWER_ON` can fire is a moment a user may well be holding the button.

It cannot co-occur with `SCHEDULED_WAKE`, `MISSED_WAKE`, `MAX_SLEEP_TIMEOUT`, or `WATCHDOG_RECOVERY` — all four require state from a previous run, which by definition does not exist. **So ranking it above `POWER_RESTORED` and below `BUTTON` fully resolves it**: the bench case reports `FIRST_POWER_ON`, and a held button during factory reset still reports `BUTTON` (the more specific description of what the person did).

---

## 9. Watchdog (`WATCHDOG_KICK` `0x59`, `WATCHDOG_TIMEOUT` `0x4C`)

Disabled by default (`WATCHDOG_TIMEOUT = 0`). When enabled, the host writes `0xA5` to `WATCHDOG_KICK` at least once per `WATCHDOG_TIMEOUT` seconds. On expiry, PowerMOD records `WATCHDOG_EXPIRY`, runs the normal `DELAY_FORCED` shutdown, waits out `MIN_OFF_DURATION`, then re-powers the host and records `WATCHDOG_RECOVERY`. **A kick received during the `DELAY_FORCED` window cancels the shutdown** (logged `SHUTDOWN_CANCELLED`): the host has proven it is alive, and cycling it anyway would reduce the service the watchdog exists to restore. **The cancelling kick is still a kick — the countdown restarts from it**, so a host that recovers late is not immediately re-condemned by the deadline it already missed.

> **Corrected 2026-07-15.** This previously said the watchdog "**immediately** re-powers the host" — a **zero-second** power cycle, which is precisely the rapid-reboot failure the minimum-off-duration gap was about (§7.1). It was written while that gap was believed closed. A hung host power-cycled with no off time may never reset cleanly, which would have made the watchdog *cause* the unrecoverable state it exists to escape.

### 9.1 The watchdog arms on the host's first kick, not at power-on

**This matters, and it is not optional.** If the watchdog started counting the moment the rail came up, any host whose boot takes longer than `WATCHDOG_TIMEOUT` would be power-cycled before it ever ran — forever. A 60-second timeout on a host with a 90-second boot is an unbreakable boot loop, bricking the device in the field with no way in over I2C because the host never gets far enough to talk.

**Rule: after every power-on, the watchdog is disarmed. It arms on the first `WATCHDOG_KICK` and stays armed until power is cut.** A host that never kicks is never watchdogged — which is also precisely the right behavior for a host whose software doesn't know about the watchdog at all.

This costs one flag and removes the need for a separate boot-grace-period register.

---

## 10. Event log (`0x60`–`0x88`, read-only)

| Addr | Name | Type | Notes |
|---|---|---|---|
| `0x60` | `EVENT_LOG_COUNT` | uint8 | Number of valid entries, `0`–`8` |
| `0x61`–`0x88` | `EVENT_LOG` | 8 × 5 bytes | Entry 0 at `0x61` is **most recent** |

Each 5-byte entry: byte 0 = reason (§8.2 enum), bytes 1–4 = uint32 LE timestamp. **The whole log — count plus all eight entries — latches as one block on the first byte read anywhere in `0x60`–`0x88`, released at STOP (§1.1). Per-entry latching (the original rule) was not enough:** entries are presented newest-first, so an event firing *mid-read* shifts every entry down one — a host bulk-reading during the shift would see one entry twice and miss another, with each individual entry still perfectly coherent. The set has to latch, not the elements.

**Entries are presented newest-first, which is not their physical order.** The underlying storage is a wear-levelled circular buffer writing entry *N* to slot *N* mod 8 (spec §Event log), so physical slot order is meaningless to a host. Firmware does the reordering at read time so a host can simply bulk-read 41 bytes from `0x60` and iterate. The cost is a small copy on read; the benefit is that no host ever has to reimplement circular-buffer arithmetic to answer "what happened last."

**Timestamps are only as meaningful as the RTC.** In relative-time mode (spec §RTC default state) they are offsets from an arbitrary epoch and restart after an RTC reset — read them for ordering and intervals, not as wall-clock history.

---

## 11. Decisions this document forced, and what remains open

Writing the map surfaced choices the spec had left implicit. Each is called out here rather than buried, since several are judgment calls that deserve a second opinion.

**Resolved here (spec had explicitly deferred these):**

1. **Simultaneous wake priority order** (§8.3) — spec required "fixed and deterministic," left the order open. Chosen on most-fault-bearing-wins.
2. **`DELAY_FORCED` default = 30.0s** — spec said this "should be set to something defensible for the flagship Linux SBC case rather than inherited unexamined." **Reasoning: 30s is sized for a host to *notice via polling and complete a real shutdown*, not merely flush a file.** That is the realistic response to seeing `SHUTDOWN_PENDING` — a Linux host will want to run its actual shutdown sequence, and a delay shorter than that makes the grace window decorative. Cost at the low-voltage floor is ~0.4% of a 2000mAh cell at 1A (30s × 1A = 8.3mAh), which the floor's margin absorbs comfortably. Accidental button presses are covered by cancel (§spec), not by a short delay.
3. **`RTC_VALID` auto-clears on `RTC_TIME` write** (§4) rather than needing a separate clear step.
4. **Watchdog arms on first kick** (§9.1) — closes a boot-loop bricking hazard the spec didn't anticipate.
5. **Read latching** (§1.1) — closes an RTC tearing bug; the read-side mirror of the write atomicity the spec already required.

6. **`LOW_VOLTAGE_THRESHOLD` defaults to `30` (3.0V, *enabled*), diverging from Witty Pi's disabled-by-default — confirmed after review.** The spec appeared ambiguous: it describes the cutoff as an "**independent hard voltage floor, enforced by the board regardless of host cooperation**… a physical safety limit, same category as any LiPo protection IC," while also adopting Witty Pi's register #19 "default disabled" as precedent.
   - **The ambiguity dissolves once you notice what else depends on it.** Three separate resolutions in the spec conclude "no new design needed" *because* this floor is active: the hung-host-on-battery case is bounded by it, the stuck-I2C-bus case is bounded by it, and the decision not to watchdog the battery case rests on it. Shipping the floor disabled silently falsifies all three for a default board — the safety net those arguments lean on wouldn't be there unless someone had read a register table and switched it on. The "hard floor" language is the load-bearing one; the Witty Pi default was inherited without noticing the conflict.
   - **Why we can safely diverge where Witty Pi couldn't.** Their likely reason for a disabled default is that their boards are frequently run with no battery, where an enabled threshold reading ~0V would fire immediately. PowerMOD gates both thresholds on the charger's battery-detect (mains-only mode has no voltage monitoring at all — §7), so the failure mode that probably forced their default cannot occur here. This is a divergence enabled by a design decision they don't have, not a disagreement about risk.
   - `0` (disabled) remains legal for integrators with their own protection circuitry — but opting out of over-discharge protection is now an explicit act rather than the out-of-box state.

7. **The three voltage thresholds are validated as an ordered set at commit — `LOW < CRITICAL < RECOVERY` (§7).** This started as a two-way check and grew a third member; the reasoning below is the original two-way case, and it applies unchanged to all three. **Reversed from an earlier "flag, don't decide."** This was initially left unvalidated on the grounds that it collided with the spec's hands-off principle and the "independently configurable" wording. **On review it isn't a collision.** The no-validation principle is specific to *wake-time writes*, where absolute and relative modes are both legitimate and PowerMOD genuinely cannot know which is intended — that is what the spec's entire wording-correction section is about. Configuration is already a different category: this map range-checks every config value and rejects out-of-range commits atomically. An inverted threshold pair is the same class of check, and unlike a wake time it has no valid interpretation — it is not an unusual choice but a broken one, reintroducing oscillation exactly when the cell is most fragile. "Independently configurable" is preserved in the sense that matters: either may still be set or disabled on its own.

**Added after this list was first written — and the fact they were missing is itself the finding.** This section is the map's account of its own decisions, and it silently fell ~8 decisions behind the document it describes. **Three documents into this audit, every one has had the same weak spot: its self-description.** Every edit goes to the body; nobody re-reads the summary.

8. **`MIN_OFF_DURATION` (`0x4F`–`0x50`) defined, default 5.0s** — the register that actually closes the spec's rapid-reboot gap, which had been "closed" by a delay-before-cut register that governs a different transition entirely (§7.1).
9. **`CRITICAL_VOLTAGE_THRESHOLD` (`0x42`) added, default 3.3V** — the Battery LED's warning state had no trigger behind it. Placed **between** its two siblings so the three read in the order a discharging cell meets them.
10. **`DELAY_HOST_REQUESTED` default changed 7.0s → 0** — Witty Pi's 7s exists because their architecture waits for the Pi to shut down; PowerMOD's host is already finished when it sends the command. A halted host still draws current, so the wait is measurable loss.
11. **`BUTTON_FORCED` (`0x05`) added** — the button had no way to cut power immediately; every press waited out the full forced delay even with the host hung.
12. **`INPUT_MILLIVOLTS` removed and `STATUS` bit 6 reserved** — both were exposing things PowerMOD turned out not to measure at the time (mains detect was a digital read under the MCP73871; there is no temperature sensing). **Half-reopened 2026-07-15: the charger reversal made mains detect a VBUS *ADC* divider, so the input-voltage half is measurable again and the spec has reopened it — deliberately not adopted in protocol v1; `0x32`–`0x33` reserved for it if adopted** (§6). ~~The temperature half is unchanged~~ — **the temperature half fell too (2026-07-15): the ATtiny's own die sensor (factory-calibrated, `SIGROW.TEMPSENSE0/1`) was on the board all along**; "no temperature sensing" was true of the *battery* and false of the *board*. `BOARD_TEMPERATURE` (`0x34`) now exposes it, with the battery-vs-board distinction stated at the register. *(MCU migration note: the SIGROW die sensor is AVR-specific; on the current PY32F003 the source is the PY32's internal ADC temperature channel — see the `0x34` register definition.)*
13. **Config block grown to `0x40`–`0x57`, commands moved to `0x58`–`0x5F`** — to keep the three voltage thresholds adjacent rather than orphaning the new one wherever it happened to fit.

**Deliberately left open (need hardware, not more thought):**

- ~~Factory reset hold duration and LED acknowledgment pattern~~ (guide FAQ 5.1) — **committed as v1 defaults 2026-07-15: 5s hold (one number for every deliberate hold gesture), both LEDs alternating 2s (a pattern no other state uses). Bench-check feel only.**
14. **Magic values made distinct per command — closed 2026-07-15, and it was not the cosmetic issue it looked like.** This list previously flagged "`CONFIG_COMMIT` lives at `0x5A` and its magic value is also `0x5A`" as *harmless but confusing*. **Reading the command tables together showed it wasn't harmless.** `0x5A` was the go-value for three commands, and `CONFIG_COMMIT` (`0x5A`) sits two addresses from `POWER_OFF_REQUEST` (`0x58`) — so a two-byte pointer slip on the most routine config operation performed the most destructive one. Worse, every host shutdown routine writes that same byte twice (commit wake, then power off), so swapping two address constants cut power with no wake armed. **Resolved: `POWER_OFF_REQUEST` → `0x3C`, `CONFIG_COMMIT` → `0xC0`; no value now means two things** (§1). The point is not tidiness — with distinct values, an address error is ignored rather than obeyed, which is what the magic-value rule was always claiming to deliver.
- ~~Whether `CHARGING` (`STATUS` bit 5) is readable from the chosen charger.~~ **Closed 2026-07-15, then re-closed against a different part the same day.** Originally: MCP73871 asserts `STAT1 = L` throughout Preconditioning / Constant Current / Constant Voltage. **After the charger reversal it rests on TP4056's `CHRG` output** — datasheet: *"Open Drain Charge Status Output. When the battery is being charged, the pin is pulled low by an internal switch, otherwise pin is in high impedance state."* Still reliable, still one GPIO. (**BQ24074 would still have failed here** — its `CHG` goes low only for the *first* charge cycle, so refresh charges read as "not charging". That disqualification survives both charger changes.)
15. **`BACKUP_TRICKLE` (`0x51`) added by the pre-BOM electrical walk and REMOVED hours later by the RTC reversal (both 2026-07-15).** The register solved the RV-3028's trickle-charger policy problem; the BM8563 that replaced it has no trickle charger, and supercap charging became a solder jumper — **which is strictly safer: no register write can ever charge a primary coin cell.** `0x51` stays reserved. Original rationale: The RTC's trickle charger and its backup *switchover* both ship factory-disabled (RV-3028 reg 37h: `TCE=0`, `BSM=00`) — so the supercap option had no charge path, and **without firmware setting `BSM` at first boot, the VBACKUP pads would do nothing at all**, making every backup ever fitted decorative. Firmware programs `BSM` unconditionally (harmless with nothing fitted); trickle stays host-controlled and off, because the board cannot know whether the pads hold a supercap (wants charging) or a primary coin cell (charging is a hazard).
16. **Telemetry completed against the hardware inventory (2026-07-15): `INPUT_MILLIVOLTS` (`0x32`), `BOARD_TEMPERATURE` (`0x34`), `STATUS.CHARGE_COMPLETE` (bit 6) — all three were signals the firmware already possessed and the protocol withheld.** The review question was "what do the components measure that the host can't see"; the answer was two ADC channels being read continuously and one status pin driving an LED. Zero hardware, zero pins, three registers. Considered and rejected in the same review: raw button state, time-since-last-kick, MCU self-VDD, host uptime (host-derivable or valueless); output V/I (needs hardware — the "already free" rule is the whole rule).
