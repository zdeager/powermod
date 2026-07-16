import os,sys; sys.path.insert(0,'.')
import layout_mount   # sets board size, Pi holes, full mount FLOORPLAN
import layout_v2 as L
# user-interactable / mechanical parts only
INTERACT=['J1','J2','J3','J4','J5','SW1','D1','D2','TP1','TP2','TP3','TP4','TP5','TP6']
full=dict(L.FLOORPLAN)
L.FLOORPLAN={r:full[r] for r in INTERACT}
# bypass the "all components placed" guard by calling gen_pcb directly
L.gen_pcb('powermod_stencil.kicad_pcb')
print(f"stencil: {len(INTERACT)} placeable parts + 4 Pi holes on {L.BOARD_W}x{L.BOARD_H}mm")
