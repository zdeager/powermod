# PowerMOD: Generic Power Scheduler, UPS, and Battery Supply
## User Manual (draft v0.1)

---

## 1. Product Overview

PowerMOD is a generic power controller: real time clock, scheduled power-cycling, and optional UPS/battery backup, controlled entirely over I2C. It's designed to be dropped into any project that needs to power something on a schedule, protect against power interruptions, or both — a Linux single-board computer (SBC), a bare-metal microcontroller project, or anything else with a **3.3V** I2C bus and a power input to control. PowerMOD makes no assumptions about what it's connected to beyond that — and the 3.3V is a real limit, not a preference: **a 5V I2C bus will damage the board** unless you put a level shifter in between (Section 4). Everything modern — Pi, RP2040, ESP32, STM32 — is already 3.3V.

Unlike existing scheduled-power boards, PowerMOD never tries to infer whether whatever it's powering has finished shutting down, or what kind of device it even is. Instead, **the host tells it explicitly** — when it's safe to cut power, and when it should be woken up next. This means PowerMOD works the same way regardless of what's on the other end: Raspberry Pi OS, Alpine Linux, a bare-metal firmware loop, or anything else that speaks 3.3V I2C.

**This guide uses Linux SBCs as the primary worked example throughout** (Section 4 in particular), because that's the use case PowerMOD was first built and validated for, and it's where the richest integration guidance exists. If you're connecting a bare-metal or non-Linux host, see Section 5.3 — the core protocol and hardware work identically; only the specific host-side integration pattern differs.

### 1.1 Built-in Uninterruptible Power Supply (UPS) Functionality — LiPo Mode

PowerMOD integrates battery charging with power-path switching and a buck-boost converter, and can be used as a UPS. It works with any 3.7V-nominal Lithium Ion or Lithium Polymer battery (full-charged voltage 4.2V).

**Two things about "any battery" that you need before you connect one** — both are covered properly later, but they belong here, next to the promise that creates them:
- **⚠️ Meter your battery's polarity first.** The JST-PH connector is keyed, so you cannot plug it in backwards — **but vendors do not agree on which pin is positive**, so a reversed cell seats perfectly and can cause a fire. There is no protection circuitry. This is the direct cost of "any battery": the wider the support, the likelier a cell wired the other way. **FAQ 5.5** explains what to check.
- **⚠️ PowerMOD never checks battery temperature before charging** — see immediately below.

When 5V mains power is connected via the input USB-C connector, it takes priority to power the board and host together, while the battery is charged. **Because the battery is genuinely isolated from the system rail (not powering anything) whenever mains is present, it is safe to disconnect or replace the LiPo while PowerMOD is running on mains power** — host power is not interrupted. This isolation is structural — with 5V present the battery's switch is held off and its internal diode points the wrong way to conduct — not a controller decision, which is what makes it safe to rely on: if you need to swap a degraded cell on a device that's up on mains, you can do it without taking the host down.

**The one exception: an undersized supply.** If your mains supply can't hold its voltage under the host's draw, PowerMOD hands the entire load over to the battery — that's the UPS doing its job, but it means the battery *is* in the power path even though a cable is plugged in, and it stays there until the supply recovers or is replaced. Don't pull the cell while running a heavy load from a weak supply; with a properly rated supply (Section 2), the isolation holds and hot-swapping is safe.

> ### ⚠️ PowerMOD does not check battery temperature before charging
>
> **Charging a lithium cell below 0°C plates lithium onto the anode: permanent capacity loss, and a real safety risk — not just reduced runtime.** Charging much above 45°C is separately damaging. **PowerMOD will charge whenever mains is present and the battery is below full, regardless of how cold or hot the cell is.** It has no way to know.
>
> **This is a deliberate limitation, and it matters most in exactly the deployments PowerMOD is built for** — an outdoor or unheated enclosure will go below freezing, unattended, and PowerMOD will charge straight through it.
>
> Why not: temperature qualification needs a sensor *bonded to the cell*, which normally arrives as a third wire from a battery pack that has one built in. PowerMOD uses a 2-pin battery connector so it can work with any ordinary LiPo — and there's no third wire. A sensor on the board instead would read the board's own heat, not your battery's, and would err toward saying "warm enough" precisely when it isn't. We'd rather tell you the truth than give you a protection feature that quietly doesn't protect.
>
> **If you're deploying somewhere that goes below freezing, this is yours to handle.** Options, roughly in order of reliability:
> - Use a cell rated for **low-temperature charging** (some Li-ion chemistries are; most LiPo pouches are not — check your datasheet, not the listing).
> - Keep the battery in an enclosure that stays above 0°C.
> - Have your host read battery voltage and ambient temperature from its own sensors and simply **not** ask PowerMOD for power (or disconnect mains) while it's too cold to charge safely.
>
> If none of those are practical for your deployment, PowerMOD is not the right board for it, and we'd rather say so here than have you find out via a swollen cell.

**If mains and battery are both present, the host is always prioritized.** When the 5V input can't supply both your host's draw and the full charging current at once, PowerMOD backs the charging off rather than letting the host brown out — and if the input still can't hold up even with charging paused, PowerMOD hands the load to the battery entirely (it never splits it between the two). Either way your host keeps running; the symptom is a battery that charges slowly under heavy load — or, with a genuinely inadequate supply, one that discharges while plugged in (Section 2).

After mains power is disconnected, PowerMOD monitors the battery voltage. **Below a configurable low-voltage threshold, PowerMOD independently cuts power to the host — regardless of whether the host has said it's safe to do so.** This is a hard safety floor, not a request; see Section 4.3.

### 1.1b Mains-Only Mode (No Battery)

PowerMOD does not require a LiPo battery to function. **With no battery connected, PowerMOD operates purely as a scheduled power switch** — mains in, scheduled/commanded power out to the host, with none of the UPS behavior above (no voltage monitoring, no emergency cutoff, no charging, since there's no battery present to protect or charge). This is a fully supported mode, not a degraded fallback — useful if you only want scheduled power-cycling (energy savings, forced reboots) without battery backup. See Section 1.2b for how clock and schedule continuity works in this mode.

There's nothing to configure: the mode follows automatically from whether a battery is physically connected. PowerMOD checks for the cell with a brief active test (momentarily pausing the charger and confirming the battery terminal holds its voltage) rather than just comparing a reading against some threshold. A deeply discharged battery is still recognized as a battery present, not mistaken for an absent one — it holds the test where an empty connector can't — so it charges normally and shows as critically low (Section 1.4) rather than silently disappearing from PowerMOD's view.

**One thing you lose in this mode that isn't obvious from the list above: tolerance of an undersized power supply.** When mains can't hold up, PowerMOD's protection works by handing the entire load over to the battery — and here there isn't one, so an undersized supply browns your host out instead. **The ≥2A supply requirement (Section 2) is a hard requirement in mains-only mode, not a recommendation.** It's worth pausing on, because it's backwards from intuition: *the simpler configuration is the less forgiving one.*

### 1.2 Accurate Realtime Clock and ON/OFF Scheduling

PowerMOD uses a standard crystal realtime clock, accurate to roughly **±20 ppm at room temperature — about a minute a month**. (An earlier draft used a factory-calibrated ±1 ppm part; it was swapped out deliberately — that accuracy cost more than the rest of the power stage combined and, as the modes below show, most hosts never benefit from it.) You can schedule the startup and/or shutdown of your host at any time — or an arbitrary sequence via I2C commands issued from your own scripts or software.

**It is not temperature-compensated, and that matters outdoors.** Like essentially every low-power RTC in this class, accuracy follows the crystal's temperature curve — roughly `−0.035 × (T−25)²` ppm, best at 25°C and falling away either side of it:

| Temperature | Drift (worst case, initial tolerance + temperature) |
|---|---|
| 25°C | ~1 min/month |
| 10°C or 40°C | ~1.3 min/month |
| 0°C | ~2 min/month |
| −10°C | ~2.7 min/month |
| −20°C | ~4 min/month |

**Whether this matters to you depends entirely on which time mode you use:**
- **Relative-time scheduling** (Section 4.1) — **doesn't care at all.** "Wake me 6 hours from now" is computed against PowerMOD's own clock, so a slow clock means a slightly long sleep, not a wrong one. This is the recommended mode for exactly this reason.
- **A host that re-syncs** (NTP, GPS) on each wake — **doesn't care either.** You'll correct the drift faster than it accumulates.
- **Absolute wall-clock schedules on a host that can't re-sync** — this is the case to think about. An unheated outdoor enclosure will drift roughly a minute a month, so a "run at 09:00" schedule wanders. Budget for it, or re-sync from some other source.

If you need genuine temperature compensation, that's a different class of RTC (with a real temperature sensor and correction) and PowerMOD doesn't have one.

**Unlike other boards, scheduling the ON/OFF sequence never requires installing OS-specific software on your host.** You write two values over I2C: the next wake time, and — separately, only once your own shutdown sequence is genuinely complete — a command to cut power now. How you determine "genuinely complete" is entirely up to you and your host's OS.

### 1.2b RTC Backup Power (Optional)

**PowerMOD ships with two solder pads (`VBACKUP`, `GND`) rather than a battery holder — the backup is yours to fit, and most people don't need one.** If you fit one, it **keeps the real time clock counting** through a total loss of both mains and battery power. Nothing else depends on it.

**Why pads instead of a holder:** a CR2032 holder would be the largest component on the board by a wide margin — the cell alone is about **seven times the combined footprint of every chip in PowerMOD**, and 65× the size of the RTC it exists to back up. Spending that on a part most integrators don't need was the wrong trade. Fit what your deployment actually calls for:

| What to fit | Backup | Good for |
|---|---|---|
| **Nothing** | none | Relative-time scheduling, or any host that re-syncs its clock on boot. **This is most people** — see below. |
| **Supercapacitor** | ~1–3 days | Riding out grid outages and battery swaps. No shelf life, nothing to replace, soldered once. **Requires closing one solder jumper** (see below). |
| **Coin cell** (solder-tab or lead-terminated) | years | Non-networked hosts on wall-clock schedules; remote sites that can go dark for weeks. |

> ### ⚠️ Never solder a bare coin cell to these pads
>
> Heating a lithium coin cell can make it vent or rupture. **Use a cell with solder tabs or wire leads already attached** — these are sold specifically for the purpose — or use a supercapacitor, which solders normally. If all you have is a loose CR2032 and a soldering iron, stop: that is the one combination this design cannot let you use.
>
> **Mind the polarity** — the pads are marked, and unlike the battery connector there's no plug to mislead you, so the marking is all you need. Get it right and it's unambiguous; get it wrong and you may damage the RTC.

**If you fit a supercapacitor, close the charge jumper next to the pads** (a solder jumper — one blob, once, while you're already soldering the cap). It ships **open** for a safety reason, not an oversight: the same pads may hold a lithium coin cell, and **charging a primary lithium cell can make it vent or rupture**. PowerMOD cannot see which one you soldered, so the charge path physically doesn't exist until you create it — no software setting can ever charge your coin cell by mistake. Coin-cell users: touch nothing, the open jumper is already correct.

**Your pending schedule and configuration do not depend on the coin cell** — those live in non-volatile memory and survive a total power loss (and a dead coin cell, and a firmware update) on their own. The coin cell has exactly one job: keeping the clock itself running when there's no power at all. That job can't be done any other way, which is why it's there.

**Where this actually matters for you:**
- **If your host syncs time from the network (NTP) on boot,** you will likely never notice the coin cell doing anything — your host just re-syncs after an outage.
- **If your host uses relative-time scheduling** (Section 4.1) and never sets wall-clock time, the coin cell is irrelevant to you by design — what the clock reads doesn't matter in that mode.
- **If your host relies on wall-clock schedules and can't re-sync** (no network, no GPS), the coin cell is what keeps your absolute schedule meaningful across an outage. This is the case it exists for.
- **If you're swapping the LiPo in the field:** on mains, you don't need the coin cell at all — the board stays powered from mains while the battery is isolated (Section 1.1). **With no mains present, pulling the battery cuts all power, and the coin cell is the only thing preserving the clock across the swap.**

**What the coin cell does not do:** it does not power the LEDs, and it does not enable PowerMOD to actually power the host. The clock surviving a total outage means PowerMOD still knows *when* it should wake your host — it does not mean your host will actually wake at that time if no real power source (mains or LiPo) is available when that time arrives. Think of the coin cell as protecting your clock, not as making PowerMOD outage-proof in general.

For what happens to a wake time that came due while the power was out, see Section 4.2.

### 1.3 e-Latching Power Switch

PowerMOD implements a physical power button, similar to the power switch on a PC or laptop. A single tap:
- **Powers on the host, if it is off.** No host cooperation needed — same mechanism as a scheduled wake.
- **If the host is on, immediately begins powering off the host** — after the configurable *forced* delay (Section 4.4), but **without waiting for or requiring any acknowledgment from the host.** This is a deliberate design choice, not an oversight: PowerMOD has no signal line to notify a sleeping or busy host that the button was pressed, so a "graceful request" the host might never see would be misleading. The button is a blunt, immediate manual override — closer to pulling the plug (with a grace delay) than to a polite shutdown request. **If your host needs to protect against this** (e.g., ensure filesystems are always in a safe state), it should poll the **shutdown-pending flag** (Section 4.3) frequently enough to notice that a power-off is in progress and use the remaining delay to attempt a fast save. There is no guarantee it will be running or listening at the moment the button is pressed — that's inherent to the design, not a gap in it.

  **The forced delay defaults to 30 seconds**, chosen so a Linux host that polls the shutdown-pending flag has time to notice and run a *real* shutdown sequence — not just flush a file. Check it against your own host's worst-case shutdown time and raise it if needed (Section 4.4). It's a separate register from the delay used when your host requests its own shutdown, precisely so you can make this one generous without slowing down every ordinary scheduled sleep.

- **Pressing the button again during a button-initiated power-off cancels it.** If you bump the button by accident, press it again before the delay elapses and the host stays up. This only works for shutdowns *the button started* — a second press will not cancel a shutdown your host requested itself (your host has already finished shutting down; keeping it powered would strand it), and it will never cancel a low-battery emergency cutoff (that's a safety floor, and it isn't negotiable).

- **Holding the button for 5 seconds cuts power immediately.** This is the "pull the plug" escape — no delay, no cancelling, and it works even if your host is hung solid. Use it when you want the thing off *now* and don't care what state it's in.

  **Tap and hold divide by intent**, which is worth internalising because it's the whole model:
  - **Tap** = *"start shutting down — I might change my mind."* Delay runs, LED shows it, tap again to abort.
  - **Hold 5s** = *"off, now."* Immediate, irreversible, recorded with its own reason code so you can tell the two apart afterwards.

  A hold simply overtakes a tap: the press starts the delay, and if you keep holding, the cut happens at 5s instead of waiting out the full window. You don't need to think about which you pressed first.

  **Below the low-voltage cutoff, the button does not power the host on.** The protection floor is as absolute for starting as it is for running: booting onto a cell below the floor would trip the cutoff immediately and spend the battery's last margin running out the shutdown delay. Between the cutoff and the recovery threshold, the button *does* work — you're present, and that hysteresis band exists to absorb a boot's voltage sag. If a press seems dead and the Battery LED shows the rare emergency flash (Section 1.4), that's the floor doing its job: supply mains power, or wait for the cell to recover.

  **The hold gesture only exists when your host was ON at the moment you pressed.** From OFF, a press powers the host on, and continued holding does nothing further — it will not boot your host and then cut it five seconds later. (The one other meaning of a long hold is the factory-reset gesture, which requires the button to be already held *while power is first connected* — Section 5.1.)

### 1.4 Status Indicators

PowerMOD has two bicolor LEDs:
- **Battery LED** — four states, using color and blink pattern together:
  - **Solid, color A** — charging (mains present, battery below full).
  - **Solid, color B** — charged/full (mains present, battery at capacity).
  - **Slow blink, color B** — discharging normally (running on battery, no mains present, battery healthy). This is the normal state whenever you're running on battery power with no issues.
  - **Fast blink** — battery critically low: below the **critical voltage threshold** (default 3.3V, configurable — Section 4.4), which sits above the cutoff (default 3.0V). This is an early warning shown *before* PowerMOD force-cuts power — if you see it, you still have time to act. **Once the cutoff actually fires, this LED drops to the rare flash below** — the same LED, telling the next chapter of the same story.
  - **A brief flash every ~10 seconds, color B** — emergency low-battery cutoff has fired (LiPo mode only). Your host is off, and the cell is below its protection floor.

    **Why this state is deliberately faint rather than urgent.** Everything the board draws in this state comes out of a cell that is *already below the voltage PowerMOD cut power to protect*. A fast-blinking LED here would pull several times PowerMOD's entire idle budget and hurry along exactly the over-discharge the cutoff exists to prevent — turning the warning light into part of the problem. A rare flash still tells you the board is alive and holding, at a fraction of the cost. **It is faint on purpose; it is not a fault.**

    Read this LED as the whole battery story on one indicator: **slow blink (fine) → fast blink (act now) → rare flash (host cut, board holding) → dark (fully depleted, board down)**.
  - **Off** — no battery present (mains-only mode, Section 1.1b).
- **Power LED** — four states, using color and blink pattern together:
  - **Solid, color A** — powering host.
  - **Slow blink, color A** — sleeping, with a wake **armed**.
  - **Slow blink, color B** — sleeping, with **no armed wake** — nothing will happen on its own until you intervene. Covers two cases: no wake time was ever set (e.g. after a button-forced-off with no pending schedule — see Section 1.3), **and** a wake time that was already in the past when your host committed it, and was therefore marked expired (Section 4.2).
  - **Off — emergency low-battery cutoff** (LiPo mode only). Your host has no power, and a dark Power LED says exactly that; **the Battery LED carries the emergency signal** (the rare flash above). Dark Power LED + flashing Battery LED = host down, battery below its floor. Everything dark = battery fully depleted.

**"Armed" rather than "scheduled" is a deliberate distinction, and a useful one.** A wake time your host wrote but which was already in the past gets accepted and then expires — so it *was* scheduled, and it will *never* fire. The Power LED shows color B for that case, because what the LED reports is "will anything happen on its own?", not "did anyone ask for something?" **This makes the LED a free bring-up diagnostic:** if you set a wake, your host sleeps, and the LED shows color B rather than color A, your timestamp was bad — a timezone or overflow bug — and you've caught it without attaching anything. Read `WAKE_STATUS` (Section 4.2) to distinguish "never set" from "expired."

For finer detail than the LED shows (e.g. distinguishing a scheduled shutdown from a button press, both of which show as "sleeping"), read the reason-code registers over I2C (Section 4.3).

If a battery is deeply discharged with no charging source, PowerMOD itself may eventually be unable to power any LED at all. **Extended, total absence of any LED activity should be read as "battery likely fully depleted," not as a normal sleep state** — this applies to LiPo mode only, since the coin cell (Section 1.2b) keeps the clock running but was never intended to power an LED either way.

### 1.5 Interface Introduction

1. USB-C connector for 5V mains power input.
2. USB-C connector for 5V power output to host.
3. I2C connector (4-pin, STEMMA-QT-style) for command/telemetry interface to host. **3.3V logic — see the warning in Section 4.**
4. On/off switch (physical button).
5. Power LED (bicolor status — Section 1.4).
6. Battery LED (bicolor charge status — Section 1.4).
7. PH2.0 2-pin battery connector — **rated 2A, and that rating lives in the plug's contacts, not the board** (Section 2). ⚠️ **Polarity is not standardized across battery vendors — meter it first** (FAQ 5.5).
8. Two solder pads (`VBACKUP`, `GND`) for an **optional** RTC backup — Section 1.2b. No holder is fitted; you choose whether to add a backup at all. The adjacent **charge jumper** ships open (Section 1.2b).
9. **`BAT` / `GND` solder pads — the high-current battery connection.** Soldering the cell here bypasses the connector's 2A contact limit and raises the 5V-from-battery ceiling from ~1.5A to ~2.6A (Section 2). Use these for any sustained load above ~1.5A, or when building more than a handful of units (a pad can't be reverse-seated — FAQ 5.5).
10. Unpopulated header exposing raw VOUT + GND — same power rail as the USB-C output, for hosts without a USB-C power input.
11. Voltage select jumper/solder-bridge — sets output voltage (both the USB-C output and the raw VOUT header) to 5V or 3.3V. Ships default at 5V. **Clearly check the jumper's current position before connecting a host** — PowerMOD does not detect or protect against a mismatched setting; connecting a 3.3V-only host while the jumper is set to 5V (or vice versa) can damage your host.

---

## 2. Specification / Technical Details

| | |
|---|---|
| Microcontroller | **ATtiny1617 (24-pin)** |
| Realtime Clock | BM8563-class (PCF8563-compatible) + 32.768 kHz crystal. ~±20 ppm; **not** temperature-compensated — see Section 1.2 for drift vs. temperature |
| DC/DC Converter | TPS63020 buck-boost, selectable 3.3V or 5V output (jumper/solder-bridge, default 5V) |
| Charging Manager | **TP4056 charger behind a PFET power-OR** — up to 1A charge current. **No battery temperature qualification** — see Section 1.1 |
| Power In | DC 5V via USB-C (non-PD) — **use a supply rated at least 2A**, see below — or 3.7V Li-ion/LiPo battery |
| Power Out | **Depends on source and battery connector — there is no single number.** ~2.7A on mains; ~1.0–1.5A on battery via the JST-PH connector; ~1.8–2.6A on battery via the solder pads. **3.3V mode is ~2A in every case.** See below |
| Standby Current | TBD — measure and document once hardware exists |
| I2C | **3.3V logic only** — no pull-ups fitted; host defines the bus. 5V hosts need a level shifter (Section 4) |
| I2C Address | 0x08 default, configurable |
| RTC Backup | **Optional** — two solder pads for a coin cell or supercap. No holder fitted (Section 1.2b) |
| Operating Environment | **−40°C to +85°C** electronics. Fitting a coin cell narrows this to **−30°C to +60°C** (the cell is then the limit); a supercap or no backup keeps the full range. Your LiPo narrows it further — see below |

**On the mains supply: use a 5V USB-C charger rated at least 2A — 3A if you want full output.** PowerMOD will draw up to the full 3A a USB-C supply can offer when it's powering your host *and* charging the battery at the same time, and — like essentially every board in this class — **it does not ask your charger's permission first.** It draws what it needs.

**With a battery fitted, plugging in something weaker fails gently — but be clear about how.** PowerMOD never blends the two sources; at any moment your host runs entirely from one or the other. A weak supply plays out in two stages:

- **Mildly undersized:** the input still carries everything. PowerMOD backs *charging* off to relieve it, and your host doesn't notice because PowerMOD's output is regulated — a sagging input still produces clean 5V (or 3.3V) out. **The battery is not helping here; it just isn't charging.** Symptom: a battery that charges slowly or never reaches 100% — so if you're wondering why it never gets there, an undersized charger is the first thing to check.
- **Severely undersized:** the input can't hold its voltage at all, and PowerMOD hands the whole load to the battery. Your host stays up, but now **the battery is discharging while a charger is plugged in**, and the board runs warmer than usual. Symptom: battery percentage *falling* with the cable connected — and your host can confirm it directly by reading the input-voltage register (Section 4.3) and watching it sag. That's not a PowerMOD fault to work around — replace the supply.

**Either way your host keeps running.** But "plugged in" does not automatically mean "not using the battery" — with a bad enough supply, you're on battery and losing ground.

> **⚠️ In mains-only mode (no battery), an undersized supply is not gentle — it browns out your host.** The protection above works by handing the load to the battery, and there isn't one. This is worth pausing on, because it's the opposite of what you'd expect: **the simpler configuration is the less forgiving one.** If you're running PowerMOD without a battery, the ≥2A supply isn't a recommendation, it's a requirement.

**On the two USB-C ports: they look identical, because they are.** One is input, one is output, and the silkscreen is what tells them apart.
- **Plugging your host into the input port does nothing** — two sinks, no power source, no harm.
- **Plugging a modern USB-C charger into the output port also does nothing.** USB-C chargers only switch their power on once they detect a device asking for it, and PowerMOD's output port isn't asking. It simply won't turn on.
- **The exception worth knowing: an old USB-A charger with an A-to-C cable.** A USB-A port has 5V live on it always — there's no handshake to save you. Plugged into the output port, it backfeeds 5V into PowerMOD. **In the default 5V configuration that's harmless** (5V meeting 5V). **If you've set the jumper to 3.3V, it is not** — you'd be putting 5V onto a rail your host expects to be 3.3V. **Check the label before plugging anything in, and check it twice if you're running at 3.3V.**

**On operating temperature:** PowerMOD's electronics are rated **−40°C to +85°C**, but the board is only as wide as its narrowest part, and that is never the silicon:
- **If you fit a coin cell, it becomes the board's limit (−30°C to +60°C).** Note the **+60°C ceiling** in particular — an outdoor enclosure in direct sun exceeds that more easily than people expect, and it's the *cell* that objects, not the circuitry. If you're mounting somewhere that bakes, think about shade, venting, or fitting a supercap instead (typically rated to the electronics' own range). **Fitting no backup at all leaves you with the full −40°C to +85°C.**
- **Your LiPo narrows it further**, and by more than you might assume: typical cells discharge down to about −20°C but are only safe to **charge between roughly 0°C and 45°C**. PowerMOD does not enforce that (see the warning in Section 1.1) — check your own cell's datasheet.
- **Running without a coin cell or without a battery widens the range back out** toward the electronics' own −40°C to +85°C. Mains-only mode with no coin cell is the most temperature-tolerant way to run PowerMOD.

**On the output current figures:** an earlier draft advertised a single "3A," which was never achievable — a non-PD USB-C input tops out at 15W total (covering the host *and* charging), and 3A at 5V draws more than double the battery connector's rating on the battery side. The honest answer isn't one smaller number, it's a table:

**There is no single output-current number, and any product that gives you one is hiding something.** What PowerMOD can deliver depends on where the power is coming from and how the battery is wired:

| Running on | 5V out | 3.3V out | What's actually limiting it |
|---|---|---|---|
| **Mains (USB-C)** | **~2.7A** | **~2.0A** | Your USB-C supply's 3A ceiling |
| **Battery, JST-PH connector** | **~1.0–1.5A** | **~1.6–2.0A** | The connector — rated 2A, and that's the wall |
| **Battery, soldered to the pads** | **~1.8–2.6A** | **~2.0A** | The converter's own switch limit |

**Read the worst row, not the best one.** On battery through the JST connector — the way most people will run this — 5V output is **~1.0A once the cell is near empty**. That is the honest floor, and it is the configuration a UPS is *for*.

**Output falls as the battery drains.** A fixed current limit delivers less power at a lower cell voltage; this is physics, not a defect. The ranges above run empty-cell → full-cell.

**Three things worth knowing:**
- **The connector costs you nearly half.** Same board, same chips: ~1.0–1.5A through the JST-PH versus ~1.8–2.6A soldered to the pads. If you need the current, solder to the pads. **Why the difference, since both land on the same copper:** the 2A is the rating of the connector's *contact interface* — a spring terminal pressing on a pin, with real contact resistance and a thermal limit — not of the board's traces. A solder joint is metallurgical, effectively milliohms. Using the connector puts a 2A-rated element in series with the cell; soldering removes it, and the next limit up (the converter's own switch rating) becomes the ceiling. (And no, board layout can't route around it — the connector's pins and the solder pads are already the same copper. The limiting junction is inside the *plug*, between your battery's crimp terminal and the pin, so it travels with the battery lead, not the board.) Sustained current past 2A doesn't melt the plug on the spot — it overheats and slowly degrades the spring contact until resistance, heat, and failure feed each other.
- **3.3V mode never exceeds ~2A**, whatever you do — the converter caps it there. **Solder pads gain you nothing in 3.3V mode.**
- **Charging is a tax.** On mains, ~2.7A drops to **~1.8A while the battery is charging at full rate**, because your host and the charger share one USB supply. Your host always wins that contest; charging absorbs the shortfall.

That covers typical Linux SBC draw and essentially any MCU host. **The final number still depends on real converter efficiency and will be confirmed on hardware, not estimated.** If your host needs sustained high current, wait for it before designing PowerMOD in.

---

## 3. How Does PowerMOD Work?

After you tap the power button, PowerMOD powers your host via the output USB-C connector, and your host boots.

**When power is connected or restored, PowerMOD's default behavior is to restore whatever the host's power state was when power was lost** — if your host was running, it boots again; if it was already asleep, it stays asleep. A brand-new board with no history boots the host on first power-up, so installation works as you'd expect. This is configurable to two fixed alternatives (always boot, or never boot without an explicit button press or schedule) — see Section 4.4.

Why this default: it means an ordinary power blip doesn't wake a host that deliberately went to sleep until morning, while a host that was genuinely running when power died still comes back on its own. **A scheduled wake still fires regardless of this setting** — including one that came due while power was out (Section 1.2b), so unattended recovery doesn't depend on this mode at all.

Your host's own software is responsible for:
1. Reading the current time from PowerMOD's RTC on boot (useful regardless of which time mode you use — see Section 4.1).
2. At some point before it needs to sleep, writing a "wake at time T" command over I2C.
3. Doing whatever it needs to do before it's safe to lose power — for a Linux host, this means running its OS shutdown sequence (unmounting filesystems, stopping services); for a bare-metal project, this might just mean finishing the current task or flushing a write. See Section 5.3 for the difference in practice.
4. Once that's genuinely complete, issuing a "cut power now" command over I2C.

PowerMOD does not need to know how your host determines step 4 is complete — whether via an OS shutdown-sequence hook, a single line at the end of a firmware loop, or manual intervention. It simply waits for the command.

PowerMOD has an RTC and always knows the time. When the scheduled wake alarm is reached, PowerMOD powers the host — equivalent to a button tap. **If the wake alarm is reached while the host is already on** (a previous shutdown didn't finish, the host rebooted on its own, or the wake alarm's time arrives during the delay-before-cut window after "cut now" was already issued), **PowerMOD does nothing — the alarm is simply a no-op.** The host is considered "on" until power is actually cut, so an in-progress shutdown always takes precedence. It is not cached or fired later once the host eventually powers off. This is deliberate: a wake alarm exists to wake a sleeping host, and there's nothing meaningful to do if the host isn't sleeping. Your host will write a fresh wake time the next time it actually goes to sleep, so nothing is lost by PowerMOD not trying to "remember" a stale alarm.

PowerMOD also measures battery voltage. If it drops below the configured low-voltage threshold, PowerMOD begins the same power-off sequence used for a button press — after the configurable *forced* delay, it removes power — regardless of whether the host is aware or has acknowledged anything. PowerMOD does not notify the host beforehand (there is no signal line to the host at all — Section 1.3), and the cutoff cannot be cancelled by anything. A host that polls the shutdown-pending flag (Section 4.3) can notice it happening and use the remaining delay to flush state, which is the only reason the delay is there. See Section 4.3.

---

## 4. Software / Protocol Usage

PowerMOD is controlled entirely via I2C register reads and writes. There is no required host-side software package, service, or daemon — you integrate the commands below into your own host's boot and shutdown sequence directly.

> ### ⚠️ PowerMOD is a 3.3V I2C device. A 5V bus will damage it.
>
> **This is not "unsupported" — it's destructive.** PowerMOD's logic runs at 3.3V, and its I2C pins have an absolute maximum of about 3.8V. Wiring them to a 5V I2C bus (a classic Arduino Uno, or anything else with 5V pull-ups) **damages the board**, possibly not immediately and possibly not obviously.
>
> **If your host's I2C is 5V, you need a bidirectional level shifter between it and PowerMOD.** There is no version of this where it's fine to "just try it."
>
> **Most hosts are already 3.3V and need nothing:** Raspberry Pi and other Linux SBCs, RP2040, ESP32, STM32, and anything in the STEMMA-QT/Qwiic ecosystem — which is what this connector is.
>
> **PowerMOD fits no pull-up resistors of its own**, deliberately. Your host's pull-ups define the bus voltage, and PowerMOD only ever pulls the lines low — it never drives them high, so it can't impose a voltage on your bus. That's why the 3.3V figure is *your* responsibility to respect: PowerMOD has no way to enforce it, and no way to protect itself if you don't.

**For exact register addresses, encodings and enum values, see `powermod-register-map.md`** (protocol version 1). This section describes what the registers are *for*; that document is the wire-level reference you'll code against. Two things from it are worth knowing before you write any code:
- **All multi-byte values are little-endian.**
- **Read each multi-byte value in one transaction, starting at its first byte.** Doing so latches a coherent snapshot — reading the middle of a field on its own can return a torn value (this matters most for the clock, which is always counting).

### 4.1 Time

PowerMOD's RTC can be used two different ways, and you can pick either depending on what your host needs — PowerMOD doesn't require or assume one over the other.

- **If your host has accurate time (NTP, chronyd, GPS, etc.) and cares about wall-clock accuracy:** write it to PowerMOD's RTC whenever convenient — not just once at initial setup, but any time you want to (re)sync, as often as you like. This is useful if you want PowerMOD to also serve as a time source your host can read on boot (see below), or if your application logic depends on absolute scheduled times rather than relative ones.
- **If your host doesn't care about wall-clock time at all:** you never need to write real time to PowerMOD. Its RTC can sit at the default epoch value (or wherever it happens to be) indefinitely — this is fine, because the recommended scheduling pattern (Section 4.2) only ever reads PowerMOD's *current* value and adds an offset to it. What PowerMOD's clock actually reads relative to true wall time is irrelevant in this mode; only its internal consistency (it keeps ticking forward correctly between reads) matters.
- **Read RTC time.** Recommended on every boot regardless of which mode you use, so your host can set its own system clock even without network access — useful in wall-clock mode for obvious reasons, and still harmless (just not meaningful) in relative-time-only mode.
- **Read RTC validity flag.** If your board's coin cell has ever been fully depleted (alongside no mains and no LiPo), the RTC resets to the epoch — the same as first power-up. This register tells you whether that's happened since you last set the time, so you can tell "trustworthy time" apart from "reset since I last synced" — particularly useful if you're using wall-clock mode and need to know whether to re-sync before trusting an absolute schedule. **Note your pending schedule and configuration are not lost in this scenario** (they don't depend on the coin cell — Section 1.2b); only the clock resets. But a wake time is only as meaningful as the clock it's measured against, so if this flag is set, treat any pending absolute schedule with the same suspicion as the time itself.

### 4.2 Scheduling

- **Write next wake time.** A timestamp — absolute or computed relative to PowerMOD's current RTC value, your choice (see below). PowerMOD will power the host at this time (see Section 3 for behavior if the host is already on when this time arrives). Writing a new wake time always replaces any previously stored one — there's no queue, just one wake time at a time. To cancel a pending wake without immediately scheduling a new one, use the separate **clear wake time** command.
- **Wake-time writes are atomic.** The write uses a staging-then-commit pattern internally, so a power loss mid-write leaves your previously-committed wake time intact rather than corrupted — you don't need to guard against this yourself.
- **Read back the stored wake time.** You can read the currently committed wake time and whether it's armed. Useful after an unexpected reboot: if your host crashed somewhere between writing a wake time and issuing "cut power now," this tells you whether the write actually landed, so you can decide whether to write a fresh one.
- **Write "cut power now."** Only issue this once your host's own shutdown sequence is genuinely complete. PowerMOD cuts power promptly — the host-requested delay **defaults to 0** (Section 4.4), because by this point your host has already declared itself finished and a halted host is still drawing current while you wait. This delay is separate from the longer *forced* delay used for button presses and low-battery cutoffs (Section 4.4) — there's no reason to make your host wait around once it's genuinely done, so keep this one short.

**Absolute vs. relative wake times — both are legitimate, pick whichever fits your use case.** If you're confident in both PowerMOD's RTC accuracy and your host's own clock (e.g., you're syncing real time via NTP/chronyd as described in Section 4.1), writing absolute wake times is completely fine — and necessary for schedules that only make sense in wall-clock terms, like "run at :15 past every hour" (a cron-style pattern). PowerMOD does not care which approach you use.

**Where relative scheduling helps specifically:** if you're in the relative-time-only mode from Section 4.1 (never syncing wall-clock time to PowerMOD at all), or if you simply want to eliminate the risk of clock-drift/timezone bugs producing a bad absolute timestamp, compute the wake time as "PowerMOD's current RTC value + desired offset" instead of an independently-calculated absolute time. This is a recommendation for that specific failure mode, not a requirement — if your clocks are trustworthy and your schedule is inherently wall-clock-based, use absolute times.

**PowerMOD accepts any well-formed timestamp without rejecting it** — there is no "is this plausible" check on the write itself, regardless of which approach you use. A miscalculated absolute timestamp (host clock drift, timezone bug) is treated as a host-side integration error, not something PowerMOD attempts to detect or correct.

**What decides whether a wake time ever fires is how it looked at the moment you committed it:**

- **Already in the past when you committed it** → it's marked expired immediately and **never fires.** Your host stays asleep rather than rebooting instantly. This is deliberate: an immediate reboot the moment a bad timestamp is written would look exactly like a boot loop, and it wouldn't fix the underlying miscalculation — only make its symptom more disruptive. The optional maximum-sleep safety net (Section 4.4) is the backstop against staying asleep indefinitely.
- **In the future when you committed it, but it came due while PowerMOD had no power to act** → it's a genuinely missed alarm, and it **fires as soon as usable power returns** rather than being discarded or waiting for the next scheduled time. Example: you schedule a wake for 2 PM; mains and battery are both unavailable from 1 PM to 4 PM; your host wakes as soon as power returns at 4 PM.
- **In the future when you committed it, but it comes due while the battery is below the recovery threshold with no mains present** → same treatment: **held, and fired the moment power is usable** (voltage back above recovery, or mains arrives). Booting your host onto a cell below PowerMOD's own protection floor would sag it straight back into the cutoff — consuming the wake and stranding the device. "As soon as it physically can" means *usable* power, not merely present power. Reported as a missed wake.

The distinction is "was this reachable when you asked for it," which PowerMOD can only know at the moment of the write — which is why it's evaluated then rather than later. In practice this means you don't need to think about it: ask for a time that's actually in the future and it will happen as soon as it physically can; ask for one that's already gone and nothing happens.

**This is not validation, and PowerMOD still won't reject anything.** It accepts whatever you write. Committing only decides what the accepted value *means*.

**Safety net for a schedule that's never set at all:** by default, if no valid wake time has ever been written, PowerMOD sleeps indefinitely once powered off — there is no implicit fallback. This matters if, for example, your host issues "cut power now" without having successfully written a wake time first (a failed write, or a logic bug) — with no wake time and no one present to press the button, the device would otherwise be stranded off indefinitely. **An optional, disabled-by-default safety register** lets you configure a maximum sleep duration (e.g. 24 hours); if enabled, PowerMOD will wake unconditionally after that duration even with no schedule set, giving your host another chance to establish one. Recommended for genuinely unattended/remote deployments; left disabled by default so it never activates unexpectedly for integrators who haven't opted in.

### 4.3 Battery and Power Status

- **Read battery voltage.** Raw voltage only — no state-of-charge/fuel-gauge estimation. Standard 3.7V-nominal LiPo assumptions apply (full ≈4.2V, cutoff ≈3.0–3.3V).
- **Read input (mains) voltage.** The raw voltage on the USB-C input, in millivolts; reads 0 with nothing plugged in. **Its best use is diagnosing an undersized supply** (Section 2): if this sags under your host's load while the battery percentage falls, your charger is the problem — you can now see the two-stage weak-supply story in numbers instead of inferring it from symptoms.
- **Read board temperature.** The temperature of PowerMOD's own board, in °C, from a factory-calibrated on-chip sensor (accurate to a few degrees). Two honest uses: estimating RTC drift against the Section 1.2 table, and judging whether an outdoor enclosure is anywhere near the freezing-charge hazard. **⚠️ It is the *board's* temperature, not your battery's** — a cell in free air or against a cold wall can be much colder than the board, so treat it as a rough enclosure proxy, not as permission to charge (the Section 1.1 warning stands in full).
- **Output voltage and output current are not available.** Nothing in PowerMOD's own operation measures them, and adding sensing purely so you could read a number conflicts with keeping the board simple and cheap. (Witty Pi exposes input/output voltage and output current; PowerMOD now exposes input voltage and board temperature, and holds the line on output sensing.) Practical consequences:
  - **To know whether mains is present, read the mains-vs-battery flag above** — it answers the question that actually matters ("is the input there?") rather than handing you a voltage to interpret.
  - **To confirm your output voltage jumper setting** (Section 1.5), check it visually. There's no register for it.
- **Read status flags.** A single byte of bit flags answering most "what's going on right now" questions in one read — the cheapest thing to poll if you only poll one thing:
  - **Mains vs. battery.** Use this to prioritize your own shutdown urgency: low stakes if on mains, real urgency if on battery (a hung shutdown on battery risks the emergency cutoff below).
  - **Battery present.** Tells you whether you're in LiPo mode or mains-only mode (Section 1.1b).
  - **Charging.** Whether the battery is currently being charged. Note this reports what the charger is *doing*, not whether it's *safe* — PowerMOD does not check battery temperature and will charge a frozen cell (Section 1.1).
  - **Charge complete.** The battery is full and the charger has terminated. Read the pair together: charging=1 → charging; complete=1 → full; **both 0 → not charging for some other reason** (on battery, or charging paused for a weak supply — check the input-voltage register).
  - **Shutdown pending** — see below.
  - **RTC valid** — see Section 4.1.
  - **Wake armed** — a committed, future wake time exists (Section 4.2).
  - **Configuration defaulted.** **Worth checking on every boot.** If PowerMOD's stored configuration ever fails its integrity check at startup, it falls back to factory defaults rather than running on corrupt values — which is the safe behavior, but it means **your settings silently reverted.** A voltage threshold you deliberately raised is back at its default and nothing else will tell you. If you see this flag set, re-apply your configuration.
- **Low-voltage emergency cutoff (not a command — automatic, board-enforced):** if battery voltage drops below the configured low-voltage threshold, PowerMOD will cut power independently, whether or not the host has issued "cut now." This exists specifically to protect against a hung or crashed host that never completes its own shutdown sequence.
- **Recovery:** after an emergency cutoff, PowerMOD does not restore power the moment voltage creeps back above the cutoff threshold. It waits until voltage recovers to a separate, higher **recovery threshold**, or until mains power is supplied (whichever comes first). This avoids a rapid cut/recover/cut oscillation as boot-current draw could otherwise re-sag a barely-recovered battery back below the cutoff point.

  **What actually happens when recovery is reached — stated precisely, because three parts of this manual used to imply three different things:** an emergency cutoff records your host as having been **ON** (it was cut involuntarily — it never chose to sleep). When the recovery condition is met, PowerMOD treats it as power becoming available again and applies your **power-on mode** (Section 4.4): the default **Restore-previous-state** boots the host (its recorded state is ON), **Always ON** boots it, and **Always OFF** leaves it down until a button press or scheduled wake. The reason code reported is *power restored* — whether it was mains arriving or the battery climbing past the recovery threshold; both mean the same thing here: power is usable again.
- **Read shutdown-pending status.** Tells you a power-off is currently in progress and the delay timer is running, along with what triggered it. **This is the register to poll if you want any chance of reacting to a button press or a low-battery cutoff** — both happen without warning and without your host's consent, and this flag plus the forced delay (Section 4.4) is the entire window you get. Nothing requires you to poll it; PowerMOD will proceed either way.
- **Read time remaining before power is cut.** Valid while a shutdown is pending — tells you how long you actually have left, in tenths of a second. **This is what makes the pending flag actionable rather than merely alarming:** knowing a cut is coming doesn't help unless you know whether there's time to unmount cleanly or only time to flush. Don't compute this from your configured delay — you have no idea when the timer started, only PowerMOD does.
- **Read last-power-off reason and last-power-on reason.** These are **two separate registers**, and both are worth reading on boot:
  - **Last power-off reason** — why PowerMOD cut power the last time — one of exactly five: host-requested cut, button tap, **button-forced-off (distinct from a graceful shutdown — see Section 1.3)**, low-voltage emergency cutoff, or watchdog expiry. Note there is no "scheduled shutdown" reason and that's not an omission: PowerMOD schedules *wakes*, never shutdowns — when your host shuts down on its own schedule, it does so by issuing "cut power now," so it reports as a host-requested cut. This is the one that tells you whether your last shutdown was normal or whether your battery is failing.
  - **Last power-on reason** — why PowerMOD powered your host up: scheduled wake, missed wake fired on power restore, button press, power restored, max-sleep safety timeout, watchdog expiry. If more than one wake condition becomes true at effectively the same moment (e.g. a safety timeout and a scheduled wake coinciding), PowerMOD still performs a single wake, and the reported reason follows a fixed, deterministic priority order rather than being ambiguous.
  - A simple flag is also available: was the previous shutdown due to low battery? Convenient if that's all your host's logic needs.

  **These are two registers rather than one for a reason that matters to you:** booting is itself an event. If a single register held both, the wake reason would overwrite the power-off reason during the very act of powering your host up — so by the time your host could read it, "why did I lose power last time" would always have been replaced by "because you just woke up." Kept separate, the power-off reason survives your boot and is still there to read.
- **Read event log.** PowerMOD keeps the last 8 power transitions (each a reason code + timestamp, same format as the most-recent-reason registers above) in non-volatile storage, so it survives power loss and firmware updates. Useful for understanding what happened over multiple cycles on a remote device you can't check on in person — e.g., seeing a pattern of repeated low-voltage cutoffs might indicate a failing battery or charging problem before it becomes a hard failure. The log is a circular buffer (oldest entries are overwritten as new ones are added) rather than an unlimited history.
  - **If you use relative-time scheduling** (Section 4.1) and never set wall-clock time, the log's timestamps are offsets from an arbitrary epoch and restart from zero after any RTC reset — so read them for *ordering and intervals* ("three cutoffs within an hour of each other"), which is most of what the log is for, rather than as wall-clock history.

### 4.4 Configuration

**Configuration writes don't take effect until you commit them.** Writing any register in this section stages the value; it changes nothing until you write the commit command. This is deliberate — it's what makes a power loss partway through reconfiguring you harmless, and it's what lets several related values (like the two voltage thresholds) be validated and applied as one atomic set rather than passing through an invalid intermediate state.

The sequence is:

1. **Write** the config registers you want to change. Nothing has happened yet.
2. **Read them back if you want** — reads return your *staged* values, so you can confirm exactly what you're about to apply. Three safety nets behind this: staged values you never commit are **discarded when your host powers off**, so a fresh boot always reads the running configuration; the commit-status register **reports when uncommitted staged changes exist** (worth checking on boot if your software may have crashed mid-configuration); and a **discard command** throws staged changes away without committing them.
3. **Write the commit command.** PowerMOD validates the whole staged set, writes it, reads it back to verify, and stores a checksum.
4. **Check the commit status register.** It reports success, or why it refused — most usefully, that a staged value was out of range or that the threshold pair was inverted (below). **A rejected commit changes nothing at all**; it never applies partially.

If you skip step 3, nothing you wrote will survive — or take effect at all. See `powermod-register-map.md` for the exact addresses and command values.

- **State when power connected.** Three modes:
  - **Restore previous state (default)** — powers on only if the host was actively powered at the moment mains/battery power was lost; stays off if it had already been powered off, whether via a schedule or a button press. (An emergency cutoff counts as ON — your host didn't choose to go down — so recovery re-boots it; Section 4.3.) A board with no history (first ever power-up) boots. Note this refers to PowerMOD's own power output, not any host-side sleep/suspend concept — PowerMOD has no visibility into what your host's OS is doing internally.
  - **Always ON** — boots automatically whenever mains or battery power is first available, no button press needed.
  - **Always OFF** — requires an explicit button press or scheduled wake, matching the behavior of other boards in this category.

  **Which to choose.** The default suits most deployments and is the safest starting point. Reach for **Always ON** if your host has no schedule at all and you simply want it running whenever there's power — but be aware that on a scheduled, battery-backed deployment it means a brief power interruption at 2 AM will boot a host you intended to sleep until 6 AM, and unless your host's software checks whether it *should* be awake, it will happily stay up and drain the battery. Reach for **Always OFF** on a bench or hobby setup where you want nothing to happen without you. **A scheduled wake fires in all three modes**, so none of this affects whether your device recovers on schedule — only what happens on an unscheduled power event.
- **I2C address.** Default 0x08, configurable by writing the address register **and committing** — but note this requires updating your own host-side code to match, and does not take effect until PowerMOD is fully power-cycled. (So the address doesn't change under you mid-session: you commit, then it applies at the next power-up, by which time your code should already expect the new one.)
- **Low-voltage threshold** (default 3.0V, **enabled**) **and recovery threshold** (default 3.6V). Independently configurable, and either can be disabled (Section 4.3).

  **Unlike some boards in this category, the low-voltage cutoff is on by default.** It's a safety floor protecting your battery from over-discharge, and a floor that ships disabled protects nobody who didn't already know to switch it on. You can disable it if you have your own protection circuitry, but that's a deliberate choice rather than the starting state. Neither threshold does anything when no battery is connected — there's nothing to protect.

- **Critical voltage threshold** (default 3.3V). Below this, the Battery LED shows its critical-warning pattern (Section 1.4) — an early warning while you can still do something, since it sits above the 3.0V cutoff. Set to 0 to disable the warning entirely. **This only drives the LED; it never cuts power** — that's the cutoff's job.

  **The three thresholds describe one journey down a discharging cell**, and PowerMOD enforces their order: **3.3V critical (warn) → 3.0V cutoff (host off) → 3.6V recovery (host back)**. A commit that puts them out of order is rejected — a warning below the cutoff would fire at the same instant the host dies, and a critical threshold above recovery would alarm about the recovery that just succeeded.

  **Recovery must be higher than cutoff, and PowerMOD enforces it**: a commit that would set recovery at or below cutoff is rejected outright, because that reintroduces exactly the cut/recover/cut oscillation the two-threshold design exists to prevent. Leave yourself real margin — 0.1V passes the check but boot current can sag the rail further than that, so you'd oscillate anyway. **Aim for at least 0.3V; the defaults give you 0.6V.**

  **If you're raising both thresholds, stage both and commit once.** Validation runs against the whole staged set, so committing a higher cutoff first — while the old, now-lower recovery value is still in place — gets rejected even though your intended end state is fine.

  **Setting recovery to 0 (disabled) is a legitimate choice, not a broken one:** after an emergency cutoff your host then stays off until *mains* is supplied, rather than rebooting on battery recovery alone. Useful if you'd rather a device not resume on a marginal cell without someone physically present.
- **Delay before power cut — two separate registers.**
  - **Host-requested delay** (**default 0**) — the pause after your host issues "cut power now." **Defaults to zero deliberately.** Your host only sends that command once it has *already finished*, so there is nothing to wait for — and waiting is not free. A halted Raspberry Pi doesn't power itself off; it sits there drawing roughly 220–300mA depending on the model (measured across Pi 3/4/5 — halt deliberately leaves the SoC powered). On a 15-minute schedule, a 7-second delay would burn about **2% of a 2000mAh battery every day** doing nothing at all. Raise this only if your host has a specific reason to need a settle window.
  - **Forced delay** (default 30 seconds) — the pause after a button press, a low-battery cutoff, or a watchdog expiry, where your host has *not* declared anything and may be mid-work. **This is the only warning window your host gets, so size it to your host.** The 30s default assumes you might want to poll the shutdown-pending flag, notice, and run a real shutdown in the time available — measure your host and raise it if that's tight. It's a separate register precisely so you can make it generous without paying that cost on every ordinary scheduled sleep.
- **Minimum off duration** (default 5 seconds). After power is cut, PowerMOD holds it off for at least this long before *anything* can bring the host back — a scheduled wake, the button, the watchdog, mains returning, any of it. **This protects against the classic power-cycle-too-fast failure:** an SBC whose rails haven't discharged below its reset threshold may not cleanly restart, and hangs or boots strangely. You will normally never notice this register — a scheduled wake is minutes or hours away — it only engages when something tries to re-power the host almost immediately. Set to 0 to disable if you know your host doesn't care.
- **Watchdog timeout.** Disabled by default. If enabled, your host must write to the watchdog register periodically to declare itself alive; if it stops for longer than the configured timeout, PowerMOD power-cycles it and records a watchdog-expiry reason code. **This is the only mechanism that recovers a host that has hung while on mains power** — without it, a hung host stays hung until someone physically intervenes (Section 5.2). Recommended for remote or unattended deployments. PowerMOD doesn't know or care *why* your host stopped writing — it only restores service.

  **The watchdog does not start counting until your host kicks it for the first time after each power-on.** This means a slow boot can never trip it: if your host takes three minutes to come up and your timeout is 60 seconds, nothing happens until your software is actually running and has kicked once. It also means a host that never kicks at all is never watchdogged, so enabling this register can't strand software that doesn't know about it. Once your host has kicked once, the watchdog stays armed until power is cut — so make sure your kick lives somewhere that runs for as long as your host is up, not just at startup.

  **A late kick during the watchdog's own shutdown window cancels it.** If your host was busy rather than hung — it missed the deadline, the forced-delay window opened, and *then* it kicked — the shutdown is called off and logged, exactly parallel to a second button press cancelling a button-initiated shutdown. The watchdog exists to restore service; power-cycling a host that has just proven it's alive would do the opposite. (This is the only thing that cancels a watchdog shutdown — the button does not, and nothing cancels a low-battery cutoff.)
- **Maximum sleep before forced wake.** Disabled by default (see Section 4.2). If enabled, PowerMOD wakes unconditionally after this duration even with no schedule set — a safety net against a device being stranded off indefinitely by a failed/missing schedule write. If both a normal scheduled wake and this safety timeout are active at once, whichever time arrives first wins — no special precedence beyond that. "Unconditionally" means *even with no schedule* — it does not mean *onto a dying battery*: like a scheduled wake (Section 4.2), a max-sleep expiry while the battery is below the recovery threshold with no mains is held, and fires once power is usable.
- **Protocol/firmware version.** Read-only register — check this once at integration time if you care about compatibility across firmware revisions.

### 4.5 Firmware Updates

PowerMOD's firmware can be updated in the field via its 3-pin **UPDI** header (UPDI, VCC, GND). **Note this is UPDI, not the older AVR ISP** — a conventional 6-pin AVR ISP programmer will not work. Use any UPDI-capable programmer (SerialUPDI, jtag2updi, or a Microchip debugger); the Arduino IDE drives these via megaTinyCore if that's your preference. **Your RTC calibration and configuration (voltage thresholds, power-on mode, I2C address, etc.) are stored separately from the firmware itself and survive a reflash** — you should not need to back these up or restore them manually.

---

## 5. Frequently Asked Questions

### 5.1 What I2C address does PowerMOD use? Can I change it?

Default is 0x08. It's configurable — write the new address, then commit it (Section 4.4) — but changing it requires also updating your host-side integration code, and the new address only takes effect after a full power cycle (disconnect all power, including battery, then reconnect).

**Forgot the address you set, or want to reset all configuration back to defaults?** Hold the physical power button while power is first connected, and keep holding it for at least **5 seconds**, to trigger a factory reset.

**"Power first connected" means from completely dark — no mains *and* no battery.** On a battery-backed unit, that means disconnecting both and reconnecting while holding the button. This is deliberate, not an oversight: **a running system cannot be fat-fingered into a configuration wipe** — holding the button on a live board force-cuts the host (recoverable; Section 1.3), never resets anything. The reset gesture only exists when the board is already stateless in your hands. Conveniently, it's the same full power-down that an I2C address change already requires, so "recovery procedure" is one physical procedure: pull mains, pull battery, hold, reconnect, keep holding 5 seconds, watch for the alternating LEDs.

The reset restores the I2C address and all other configuration (voltage thresholds, power-on mode, delays, watchdog, etc.) to their defaults. **PowerMOD acknowledges the reset by alternating both LEDs for 2 seconds** — a pattern no other state uses — so you can tell it actually happened rather than guessing. (Release the button before 5 seconds and the board simply powers on normally; no reset. Your host is not powered during the 5-second window — the gesture resolves first, so a reset never yanks configuration out from under a booting host.) Your RTC time, any pending schedule, and the event log are not affected — the log in particular is deliberately preserved, since you're most likely to want it precisely when you've had to reset something.

### 5.2 What happens if my host crashes or hangs before it can issue "cut now"?

**Enable the watchdog (Section 4.4) if you want this handled automatically.** With it enabled, your host writes to a register periodically to say it's alive; if it stops, PowerMOD power-cycles it and records a watchdog-expiry reason. This is the only thing that recovers a hung host on mains power, and it's the reason to turn it on for anything remote.

**PowerMOD still does not detect or diagnose a hang** — and the distinction matters. The watchdog isn't PowerMOD noticing your host is unwell; it's your host failing to say it's well, which PowerMOD treats as a simple timeout without any idea whether you crashed, deadlocked, or just went quiet. Consistent with the core design principle (Section 1: PowerMOD never infers host state — it only acts on what the host explicitly tells it, or on the explicit absence of that).

**So the watchdog restores service; it doesn't tell you what happened.** Understanding *why* your host hung is still your own monitoring's job: if your host normally reports in (telemetry, a heartbeat, logs), a hang shows up as that reporting stopping. The event log (Section 4.3) shows what PowerMOD did around that time — including whether the watchdog fired, and how often — but not why your software hung. A device that quietly watchdog-reboots every few hours is working exactly as configured and still has a problem worth investigating.

**With the watchdog disabled (the default):**
- **On mains:** no automatic recovery from PowerMOD's side. Your host stays powered and unresponsive until you notice (via your own monitoring going quiet) and physically address it.
- **On battery:** PowerMOD's independent low-voltage cutoff (Section 4.3) will eventually force a power cycle once the battery drains below the safety threshold, protecting the battery from over-discharge — but this is not a fast recovery mechanism, and your host will be unresponsive until the battery genuinely drains.

If your host reboots on its own before it can issue "cut now" (crash, watchdog reset, or the sequence simply not completing), no special recovery logic is needed: any wake alarm that was pending simply becomes a no-op once the host is already running again (see Section 3). Nothing is stranded or requires cleanup — your host will write a fresh schedule whenever it next goes to sleep.

### 5.3 What kinds of hosts does PowerMOD actually work with?

Anything with a **3.3V** I2C bus and a power input you want controlled — PowerMOD's protocol and hardware make no assumptions beyond that. Two integration patterns are documented, covering most real projects:

**Linux SBC hosts** (any distribution — Raspberry Pi OS, Alpine, others): you are responsible for integrating the "write wake time" / "issue cut now" calls into your host's boot and shutdown sequence. A common, well-precedented integration pattern (used successfully on other embedded Linux platforms) is hooking a script into your shutdown sequence after filesystems are unmounted (e.g., a late-running script in `/etc/rc0.d/`-style shutdown ordering, or the systemd equivalent).

**Bare-metal/MCU firmware projects:** you're responsible for your own "when am I safe to cut" logic — which is often simpler than the Linux case, since there's no OS shutdown sequence to hook into. A single I2C write at the end of your application's work loop, right before you'd otherwise call your own sleep function, is typically sufficient.

Both cases use the identical I2C protocol (Section 4) — nothing about PowerMOD changes based on which one you're integrating with.

**The real boundary is 3.3V I2C, not Linux vs. bare-metal.** PowerMOD is generic across anything that can speak I2C at 3.3V logic — Linux SBCs, RP2040, ESP32, STM32, and the whole STEMMA-QT/Qwiic ecosystem. Two limits, both worth knowing before you design it in:

- **No I2C at all → not a fit.** Many routers, mini PCs/NUCs and other USB/Ethernet-only equipment simply don't expose a bus.
- **5V I2C → needs a level shifter, and will damage PowerMOD without one.** This is the case to watch: a classic 5V AVR like an Arduino Uno *can* host PowerMOD, but only through a bidirectional level shifter. See the warning at the top of Section 4. Everything modern is 3.3V and needs nothing.

### 5.4 Power connections for non-USB hosts and non-5V hosts

For power delivery to a host without a USB-C power input, use the raw VOUT/GND header (Section 1.5) instead of the USB-C output.

For a host that needs 3.3V instead of 5V, PowerMOD's output voltage (both USB-C and the raw header) is set by a jumper/solder-bridge, selectable between 5V and 3.3V — see Section 1.5. It ships set to 5V by default. **Check the jumper matches your host's expected voltage before connecting anything** — PowerMOD does not detect or protect against a mismatched setting.

**In 3.3V mode, use the raw VOUT header, not the USB-C output.** Nothing that expects USB-C power expects 3.3V on it, so the USB-C output isn't meaningful in this mode — it will still advertise itself as a nominal 5V source even though it isn't one. This won't hurt anything you're likely to plug in, but the raw header is the intended path for 3.3V hosts.

### 5.5 Is my battery protected against reverse polarity?

**No. And the connector will not save you — it is keyed, which is exactly the problem.**

> ### ⚠️ Verify your battery's polarity with a multimeter before you plug it in
>
> **JST-PH is a keyed connector with no standardised polarity.** Roughly **half** of battery vendors wire the positive terminal to one pin, and half to the other. There is no convention, and **wire colour does not settle it either**.
>
> **This means you cannot plug it in "the wrong way round" — and that is the danger.** The plug fits exactly one way, seats perfectly, and may still be reverse polarity. There is nothing to notice and nothing to line up. **PowerMOD has no reverse-polarity protection**, and reversing a LiPo can cause permanent damage or fire.
>
> **The board's silkscreen cannot help you here.** It tells you which pin is positive on *our* side; it cannot tell you which wire your vendor put there. The only actionable check is:
>
> **Meter the battery's own connector — red probe to the pin that will mate with the pad marked `+` — before it ever goes near the board.** Do this for every new battery, and again for any battery from a different supplier, even if an identical-looking one worked last time.
>
> If you're building more than a handful, consider soldering the cell to the labelled BAT/GND pads instead of using the connector. A pad is unambiguous in a way a keyed plug is not.
>
> **This is not a PowerMOD quirk.** Boards in this category ship this hazard unmitigated as a rule — the Witty Pi 4 L3V7 uses the same PH2.0 connector, has no protection either, and does not mention polarity anywhere in its 53-page manual. We would rather tell you than match them in silence.

### 5.6 What if the I2C bus itself becomes stuck or unresponsive?

PowerMOD doesn't attempt to detect or recover from a globally stuck/jammed I2C bus itself — that's inherently your host's responsibility (most I2C bus controllers/drivers have their own bus-recovery procedures for this). What matters is the worst case is already bounded: if I2C is completely unreachable for any reason (a stuck bus, a hung host, anything else), PowerMOD's independent battery-voltage safety floor (Section 4.3) still protects against over-discharge regardless — it doesn't depend on I2C communication at all. Your host being unable to gracefully schedule or shut down in this scenario is a real limitation, but not an unsafe one.

### 5.7 PowerMOD doesn't boot the host, or immediately shuts it down again?

*[To be written once real hardware/firmware exists and real failure modes are observed — Witty Pi's own equivalent FAQ section describes several GPIO-pin-conflict-driven failures specific to their design. PowerMOD's I2C-only interface is expected to avoid that entire failure category by construction, since it shares no GPIO pins with the host and doesn't passively monitor host signal lines — but this should be confirmed against real hardware, not assumed.]*

### 5.8 How should I store PowerMOD or its battery long-term?

No PowerMOD-specific guidance beyond standard LiPo/Li-ion battery handling practices — storage voltage, self-discharge, and general care are the same as for any lithium battery-powered device. Follow your battery manufacturer's recommendations.

**One PowerMOD-specific thing that isn't storage but belongs on your radar:** PowerMOD does not check battery temperature before charging, so a cold deployment can damage cells over time even though nothing looks wrong. See the warning in Section 1.1 — it's the one battery-safety responsibility this board hands entirely to you.

### 5.9 Can I use more than one PowerMOD with the same host?

Not something PowerMOD is designed for — one board per host is the only configuration considered or intended. Using multiple PowerMODs on a shared I2C bus hasn't been tested and isn't something we're planning to support.

**The reverse also isn't supported: one PowerMOD controlled by two hosts (two I2C masters).** Behaviour in that configuration is undefined — nothing arbitrates between two hosts writing conflicting wake times, or one host issuing a power-off request while the other assumes it's still running. PowerMOD assumes exactly one controlling host, and that assumption is load-bearing throughout its design.

---

## Draft notes / TBD markers (for internal use, not final manual)

Items above marked TBD or "open item" map directly to still-open items in the design spec:
- **Standby current** — needs real hardware to measure, and **the earlier note here was itself an example of the mistake the audit found.** It read: "the RTC draws 40nA and the buck-boost 25µA, so the ~0.3mA budget looks comfortable." Those are the two *smallest* terms — 0.01% and 8% of the budget. **The dominant term is the LEDs** (~67% of it in normal sleep; see spec §LED electrical specification), and it went uncosted while the noise got checked. The budget is **tight, not comfortable**, and it turns on LED drive current and duty cycle — not on the ICs.
- ~~Operating temperature range~~ — **resolved: −30°C to +60°C with the coin cell fitted** (Section 2). The electronics are rated −40°C to +85°C; the coin cell is the limit.
- **Maximum output current (Section 2)** — resolved as a per-mode table, not a number. ~~An earlier version of this note still said "charger 1.5A input… expected ~1.2A" — both figures belonged to the charger that was replaced~~; the binding limits are now the USB source (3A), the battery connector (2A), and the converter's own switch limit, per the table in Section 2. What remains open is real converter efficiency, which shifts the table's figures a few percent and is measured on hardware, not read.
- ~~Factory reset hold duration and acknowledgment LED pattern (FAQ 5.1)~~ — **committed as v1 defaults (2026-07-15): 5s hold, both LEDs alternating for 2s.** 5s matches the force-off hold — one number for every deliberate hold gesture. Bench note only: confirm the gesture *feels* right; the values ship unless hardware contradicts them.
- ~~Default forced delay~~ — **resolved: 30.0s** (register map §11). Sized for a host to notice via polling and complete a real shutdown, not merely flush.
- FAQ 5.7 deliberately left as a placeholder — writing it now would be guessing at failure modes; better to populate once real hardware exists, same as Witty Pi's own troubleshooting section was clearly written from real support tickets, not anticipated in advance.

**Audit revision (2026-07-15).** This draft was revised alongside the spec after a cross-document audit.

> **This note previously contained a flat contradiction of the guide it summarises** — it claimed "the RTC is now a part that genuinely backs §1.2's temperature-compensation claim," while §1.2 says the opposite, because that claim was retracted. **The changelog asserted the very thing the document withdrew.** It is corrected below, and worth recording: a changelog is the last thing anyone re-reads and the first thing a reader trusts.

**Claims withdrawn — the guide previously promised things PowerMOD does not do:**
- **±1 ppm factory-calibrated RTC ("30 seconds a year").** Withdrawn 2026-07-15 with the part swap: the accuracy was real but cost more than the entire power stage, and the recommended integration modes never see it. Now ~±20 ppm (~1 min/month); §1.2's table rescaled. If your host re-syncs or uses relative scheduling, nothing changed for you.
- **Temperature-compensated RTC.** It isn't, and never was. §1.2 now publishes the actual drift curve. (The wording appears to have been lifted from a competitor's feature list — they genuinely have it; we don't.)
- **Temperature-qualified charging.** Briefly added, then removed: the 2-pin battery connector gives a sensor no route to the cell. §1.1 now warns about the hazard instead of claiming to handle it.
- **Input voltage readable.** Withdrawn when mains detection was a digital read and the number wasn't free; the hardware then changed under it, and **as of 2026-07-15 it is readable after all** (Section 4.3) — along with board temperature and a charge-complete flag from the same review. A claim that went promised → withdrawn → delivered, each move for a stated reason.
- **"Any host with I2C."** The boundary is **3.3V** I2C — a 5V host damages the board.

**Behaviour changes that affect you:**
- Power-on default is **Restore-previous-state** (was Always ON).
- **Host-requested cut no longer waits** (was 7s) — a halted host is still drawing current.
- **Minimum off-duration** added: power stays off ~5s before anything can re-power the host.
- **Hold the button 5s** to force power off immediately.
- ~~Output current derated from 3A to **~1.2A**~~ — **superseded the same day.** The charger was reversed (MCP73871 → TP4056 behind a PFET power-OR), which roughly **doubled mains output to ~2.7A**. There is now **no single output number** — it depends on your source and how the battery is wired. See the table in Section 2. A **≥2A supply is still required, ≥3A for full output.**
- **The honest floor is ~1.0A** — 5V, on battery, through the JST-PH connector, cell near empty. That is the configuration most people will run, and the one a UPS exists for.
- **Critical-battery threshold** added (3.3V default) — the Battery LED's warning state previously had nothing to trigger it.
- Emergency-cutoff LED is now a **rare flash**, not a fast blink — it runs on a cell already below its protection floor.
- **RTC backup is now optional**, on solder pads. No holder is fitted.
- Opt-in **watchdog** added; reason codes split into power-on and power-off registers; the **shutdown-pending flag** this guide already told hosts to poll now actually exists.

**Claims that became true:** the LiPo hot-swap in §1.1. Worth stating precisely, since the charger chip today is the same TP4056 the original draft speced: **wired as originally drawn** (load hanging on the battery pin) the claim was the *opposite* of the hardware's behaviour; **wired behind the power-OR PowerMOD now uses**, the battery genuinely sits out of the path on mains and the claim holds — with the undersized-supply exception §1.1 documents.

**Contradictions resolved:** the wake-time rules in §1.2b and §4.2 previously contradicted each other outright, and are now one rule.
