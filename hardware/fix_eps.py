import pcbnew
b=pcbnew.LoadBoard('powermod.kicad_pcb')
want={('U2','25'):'GND',('U3','15'):'GND',('U4','9'):'GND',('Q1','9'):'VBUS',('Q2','9'):'VBAT'}
fixed=[]
for fp in b.GetFootprints():
    ref=fp.GetReference()
    for pad in fp.Pads():
        key=(ref,pad.GetNumber())
        if key in want and pad.GetNetname()!=want[key]:
            net=b.FindNet(want[key])
            assert net, want[key]
            pad.SetNet(net); fixed.append(key)
# remove the 3 bad stitch traces (GND, 3.0mm, known starts)
bad_starts={(30.0,34.02),(36.45,25.2),(42.062,11.75)}
removed=0
for t in list(b.GetTracks()):
    if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND':
        s=t.GetStart(); x,y=pcbnew.ToMM(s.x),pcbnew.ToMM(s.y)
        e=t.GetEnd(); ln=pcbnew.ToMM((e-s).EuclideanNorm())
        if any(abs(x-a)<0.01 and abs(y-c)<0.01 for a,c in bad_starts) and ln>2.5:
            b.Remove(t); removed+=1
pcbnew.SaveBoard('powermod.kicad_pcb', b)
print("EPs fixed:",fixed," bad stitches removed:",removed)
