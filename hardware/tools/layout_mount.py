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
sys.path.insert(0, os.path.join(os.path.dirname(__file__) or '.', '..'))
import layout_v2 as L

L.BOARD_W, L.BOARD_H = 65.0, 40.0
# Pi Zero 2 W mounting holes: 58 x 23mm grid, kept so the board mounts to the Pi.
L.HOLES = [(3.5,3.5),(61.5,3.5),(3.5,26.5),(61.5,26.5)]
L.HOLE_FP = 'MountingHole:MountingHole_2.7mm_M2.5'

# Pi body footprint is x 5.5..70.5, y 0..30. Keep TALL/user-facing parts out of
# it (on the bottom strip y>30); low-profile circuit may live anywhere.
L.FLOORPLAN = {
 'R3': (6.5, 22.13, 0),
 'D4': (62.7, 15.0, 0),
 'R20': (25.47, 28.5, 0),
 'C12': (22.0, 8.0, 0),
 'R26': (25.62, 19.4, 0),
 'TP4': (15.5, 37.0, 0),
 'R9': (19.0, 7.95, 0),
 'TP5': (61.5, 37.0, 0),
 'U1': (56.7, 10.18, 0),
 'D3': (59.3, 15.0, 0),
 'C5': (28.0, 15.1, 90),
 'R2': (6.5, 20.99, 0),
 'C2': (34.05, 8.2, 0),
 'R4': (48.97, 28.5, 0),
 'C4': (30.15, 12.66, 90),
 'R22': (20.47, 28.5, 0),
 'D1': (25.5, 36.0, -90),
 'R6': (6.34, 29.34, 0),
 'C8': (20.6, 22.88, 0),
 'C7': (8.62, 7.0, 0),
 'Y1': (62.6, 11.0, 0),
 'C9': (24.4, 22.88, 0),
 'JP2': (39.85, 32.5, 0),
 'R11': (25.92, 10.84, 90),
 'Q1': (19.52, 11.0, 0),
 'R28': (13.9, 15.5, 0),
 'C16': (36.24, 11.0, 90),
 'R23': (22.53, 28.5, 0),
 'Q2': (19.52, 16.0, 0),
 'R16': (54.03, 20.0, 0),
 'U4': (13.5, 11.62, 0),
 'R24': (25.6, 16.95, 0),
 'R7': (7.26, 28.11, 0),
 'C11': (45.01, 22.0, 0),
 'R14': (36.71, 13.4, 0),
 'R27': (59.5, 18.0, 0),
 'R21': (27.53, 28.5, 0),
 'R1': (10.74, 14.99, 0),
 'R13': (26.36, 15.35, 90),
 'C10': (42.99, 22.0, 0),
 'R12': (13.47, 7.0, 0),
 'C13': (55.0, 6.82, 0),
 'C3': (27.57, 10.9, 90),
 'R19': (57.0, 15.0, 90),
 'R8': (16.5, 7.95, 0),
 'D2': (20.5, 36.0, -90),
 'C14': (42.0, 20.0, 0),
 'J5': (14.0, 31.0, 90),
 'Q3': (23.77, 13.66, 0),
 'J4': (18.5, 4.0, 180),
 'J3': (2.55, 35.5, 90),
 'R17': (54.0, 15.0, 90),
 'TP6': (41.5, 37.0, 0),
 'TP3': (38.5, 37.0, 0),
 'C6': (11.29, 16.39, 0),
 'R25': (25.62, 18.1, 0),
 'R10': (24.5, 8.0, 0),
 'R18': (55.5, 15.0, 90),
 'R5': (51.03, 28.5, 0),
 'C15': (11.43, 7.0, 0),
 'U2': (46.87, 12.0, 0),
 'R15': (51.97, 20.0, 0),
 'J1': (4.9, 15.0, -90),
 'C1': (30.45, 8.2, 0),
 'U5': (22.56, 20.25, 0),
 'L1': (33.28, 18.06, 180),
 'U3': (33.45, 11.88, 0),
 'TP1': (58.5, 37.0, 0),
 'TP2': (12.5, 37.0, 0),
 'J2': (50.0, 35.05, 0),
 'SW1': (32.0, 35.5, -90),
 'JP1': (60.0, 32.5, 0),
}

if __name__ == '__main__':
    missing = set(L.COMPONENTS) - set(L.FLOORPLAN)
    if missing:
        print("NOT PLACED:", sorted(missing)); sys.exit(1)
    L.gen_pcb('powermod.kicad_pcb')
    print(f"OK: {len(L.FLOORPLAN)} components on {L.BOARD_W}x{L.BOARD_H}mm mount board")
