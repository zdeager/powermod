import pcbnew, sys
mode=sys.argv[1]
b=pcbnew.LoadBoard('powermod.kicad_pcb')
if mode=='export':
    n=0
    for t in list(b.GetTracks()):
        b.Remove(t); n+=1
    print(f"stripped {n} tracks/vias")
    pcbnew.SaveBoard('powermod.kicad_pcb', b)
    ok=pcbnew.ExportSpecctraDSN(b,'powermod.dsn')
    print("DSN export:", ok)
else:
    ok=pcbnew.ImportSpecctraSES(b,'powermod.ses')
    print("SES import:", ok)
    pcbnew.SaveBoard('powermod.kicad_pcb', b)
