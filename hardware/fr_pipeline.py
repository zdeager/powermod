"""Freerouting bridge: strip copper + export DSN, or import the routed SES.

    python3 fr_pipeline.py export [board.kicad_pcb]
    python3 fr_pipeline.py import [board.kicad_pcb]

Export ALWAYS strips every track and via first. Freerouting SIGKILLs /
StackOverflows in PolylineTrace.combine when fed a pre-routed board, so this is
not optional — it is the reason the export path exists at all.
"""
import pcbnew, sys, os

mode  = sys.argv[1]
board = sys.argv[2] if len(sys.argv) > 2 else 'powermod.kicad_pcb'
stem  = os.path.splitext(board)[0]

b = pcbnew.LoadBoard(board)
if mode == 'export':
    n = 0
    for t in list(b.GetTracks()):
        b.Remove(t); n += 1
    print(f"stripped {n} tracks/vias")
    pcbnew.SaveBoard(board, b)
    print("DSN export:", pcbnew.ExportSpecctraDSN(b, stem + '.dsn'))
else:
    print("SES import:", pcbnew.ImportSpecctraSES(b, stem + '.ses'))
    pcbnew.SaveBoard(board, b)
