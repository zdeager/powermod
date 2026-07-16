#!/usr/bin/env python3
"""PowerMOD mount-board layout: bigger board that still mounts to a Pi Zero 2 W.

The Pi's 58x23mm M2.5 hole grid is kept, but the board extends past the Pi's
65x30 body so the tall / user-facing parts (USB-C, battery JST, I2C, button,
LEDs) sit on a bottom strip IN THE CLEAR -- not covered by the Pi. The circuit
(all low-profile SMD, <2.8mm) spreads across the whole board, including under
the Pi, where it clears the standoff gap. Single-sided, components up.

  Board 76 x 46mm. Pi body occupies y 0..30 (holes at 9/67, 3.5/26.5).
  Bottom strip y 30..46 = the exposed extension.

Reuses layout_v2's generator (gen_pcb) by overriding its module globals.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__) or '.')
import layout_v2 as L

L.BOARD_W, L.BOARD_H = 76.0, 46.0
# Pi Zero 2 W mounting holes: 58 x 23mm grid, kept so the board mounts to the Pi.
L.HOLES = [(3.5,3.5),(61.5,3.5),(3.5,26.5),(61.5,26.5)]
L.HOLE_FP = 'MountingHole:MountingHole_2.7mm_M2.5'

# Pi body footprint is x 5.5..70.5, y 0..30. Keep TALL/user-facing parts out of
# it (on the bottom strip y>30); low-profile circuit may live anywhere.
L.FLOORPLAN = {
 # ===== USER-PLACED I/O (kept where you put them) =====
 'J1': (4.90, 15.50, -90), 'J4': (18.50, 4.00, 180),          # under the Pi (west edge / top edge)
 'J2': (56.50, 41.05, 0), 'J3': (9.00, 43.45, 180), 'J5': (73.50, 37.46, 0),
 'SW1': (24.50, 42.00, 0), 'D1': (32.50, 42.50, 0), 'D2': (38.50, 42.50, 0),
 'TP1': (65.85, 43.00, 0), 'TP2': (14.35, 43.00, 0), 'TP3': (45.35, 43.00, 0),
 'TP4': (17.50, 43.00, 0), 'TP5': (69.00, 43.00, 0), 'TP6': (48.50, 43.00, 0),
 # ===== CIRCUIT (low-profile, spread under the Pi + into the strips) =====
 # -- input / charger / OR (west, near J1) --
 'C7': (9.87, 8.00, 0), 'C15': (12.63, 8.00, 0), 'R12': (15.00, 8.00, 0), 'R8': (17.50, 8.00, 0), 'R9': (20.00, 8.00, 0),
 'R2': (11.50, 20.00, 0), 'R3': (11.50, 21.60, 0),
 'U4': (14.46, 12.18, 0), 'R1': (12.20, 17.11, 0), 'C6': (13.52, 15.76, 0), 'R28': (16.08, 16.00, 0),
 'Q1': (20.44, 11.00, 0), 'Q2': (20.44, 16.00, 0), 'Q3': (24.65, 13.50, 0),
 'C12': (23.50, 8.50, 0), 'R10': (26.00, 8.50, 0), 'R11': (27.45, 11.00, 90), 'R13': (27.45, 15.50, 90),
 # -- converter (center) --
 'U3': (33.00, 12.00, 0), 'L1': (33.00, 5.20, 0),
 'C1': (29.05, 10.55, 90), 'C2': (29.05, 14.10, 90), 'C3': (36.95, 10.55, 90), 'C4': (39.05, 10.50, 90),
 'C5': (37.00, 14.10, 90), 'C16': (39.00, 13.50, 90),
 'R14': (30.50, 16.50, 0), 'R24': (32.93, 18.00, 0), 'R25': (34.94, 18.00, 0), 'R26': (36.95, 18.00, 0), 'JP2': (46.85, 37.50, 0),
 'U5': (26.00, 20.31, 0), 'C8': (24.20, 22.89, 0), 'C9': (27.80, 22.89, 0),
 # -- MCU (center-east, near J4 top) --
 'U2': (46.85, 12.00, 0), 'C14': (42.50, 10.00, 90), 'C10': (42.50, 14.50, 90), 'C11': (43.65, 14.50, 90),
 'R15': (49.00, 8.50, 0), 'R16': (51.00, 8.50, 0),
 # -- RTC + backup (east) --
 'U1': (57.33, 12.00, 0), 'Y1': (63.17, 13.00, 0), 'C13': (55.00, 8.50, 0),
 'R17': (54.00, 17.00, 90), 'R18': (55.50, 17.00, 90), 'R19': (57.00, 17.00, 90),
 'D3': (60.08, 17.50, 0), 'D4': (63.42, 17.50, 0), 'R27': (60.00, 20.50, 0), 'JP1': (67.15, 37.50, 0),
 # -- dividers / CC / LED resistors (in the strips near their parts) --
 'R6': (13.00, 37.00, 0), 'R7': (15.00, 37.00, 0),                # VBAT divider (near J3/TP2/4)
 'R4': (47.00, 34.00, 0), 'R5': (49.00, 34.00, 0),                # J2 CC
 'R20': (31.00, 39.00, 0), 'R21': (33.00, 39.00, 0), 'R22': (37.00, 39.00, 0), 'R23': (39.00, 39.00, 0),  # LEDs
}

if __name__ == '__main__':
    missing = set(L.COMPONENTS) - set(L.FLOORPLAN)
    if missing:
        print("NOT PLACED:", sorted(missing)); sys.exit(1)
    L.gen_pcb('powermod_mount.kicad_pcb')
    print(f"OK: {len(L.FLOORPLAN)} components on {L.BOARD_W}x{L.BOARD_H}mm mount board")
