import subprocess, re, sys

DECK = r'''* PowerMOD full path: power stage + converter as constant-power load
.model dmod D(is=1e-14 n=1 rs=0.02)
.model swp  SW(vt=1.4 vh=0.2 ron=0.03 roff=1e7)
.model swn  SW(vt=1.4 vh=0.2 ron=1.0  roff=1e7)
.model swusb SW(vt=0.5 vh=0.1 ron=0.15 roff=1e9)
.subckt pmos d g s
Dbody d s dmod
Sch   d s s g swp
.ends
.subckt nmos d g s
Dbody s d dmod
Sch   d s g s swn
.ends

* --- params for this scenario ---
.param VB={VB}       ; battery voltage
.param VOUT={VOUT}   ; converter output setpoint (5 or 3.3)
.param IPI={IPI}     ; Pi load current at the output
.param BATT={BATT}   ; 1=battery present, 0=no battery

* battery (optionally absent)
Vbat vbat_i 0 dc {VB}
Rbat vbat_i vbat {RBAT}

* USB present 0..5ms, unplugged after (realistic float)
Vusb usb_src 0 dc 5
Vctl ubus_ctl 0 PWL(0 1  5m 1  5.02m 0)
Sbus usb_src vbus ubus_ctl 0 swusb
Cvbus vbus 0 10u
R12 vbus 0 100k

Xq1 vbus q1g  vsys pmos
Xq2 vbat vbus vsys pmos
Xq3 q3d  q1gd 0    nmos
R10 vsys q1g 100k
R11 q1g  q3d 47k
C12 vsys q1g 100n
R13 q1gd 0   100k
* Q1 driven on (steady running state) while USB present + a bit after (firmware)
Bmcu q1gd 0 V = 3.3 * (v(vsys) > 3.0) * (time < 5.1m)

* --- converter: constant-power sink on VSYS; VOUT regulated while VSYS>1.8 ---
* P_in = VOUT*IPI/eff ; I_vsys = P_in/VSYS (clamped)
Bconv vsys 0 I = ({VOUT}*{IPI}/0.90) / max(v(vsys),1.3) * (v(vsys)>1.6)
Cvsys vsys 0 20u
Cout  vout 0 66u
* VOUT node: regulated to setpoint while VSYS in range, else sags with VSYS
Bvout vout 0 V = (v(vsys) > 1.85) ? {VOUT} : (v(vsys)*{VOUT}/1.85)

.control
tran 5u 12m uic
meas tran vbus_usb   find v(vbus) at=3m
meas tran vsys_run   find v(vsys) at=3m
meas tran vout_run   find v(vout) at=3m
meas tran vsys_sag   min v(vsys) from=5m to=12m
meas tran vout_sag   min v(vout) from=5m to=12m
.endc
.end
'''

scenarios = [
 ("5V out, full batt 4.2, active 0.4A", dict(VB=4.2, VOUT=5.0, IPI=0.4, BATT=1, RBAT=0.1)),
 ("3.3V out, full batt 4.2, active 0.4A", dict(VB=4.2, VOUT=3.3, IPI=0.4, BATT=1, RBAT=0.1)),
 ("5V out, LOW batt 3.0, active 0.4A", dict(VB=3.0, VOUT=5.0, IPI=0.4, BATT=1, RBAT=0.1)),
 ("3.3V out, LOW batt 3.0, active 0.4A", dict(VB=3.0, VOUT=3.3, IPI=0.4, BATT=1, RBAT=0.1)),
 ("5V out, full batt, IDLE 0.15A", dict(VB=4.2, VOUT=5.0, IPI=0.15, BATT=1, RBAT=0.1)),
 ("5V out, NO battery (USB only), unplug", dict(VB=0.0, VOUT=5.0, IPI=0.4, BATT=0, RBAT=1e6)),
]

print(f"{'scenario':40}{'VBUS':>6}{'VSYSrun':>8}{'VOUTrun':>8}{'VSYSsag':>8}{'VOUTsag':>8}  verdict")
print("-"*100)
for name, p in scenarios:
    deck = DECK
    for k,v in p.items(): deck = deck.replace("{"+k+"}", str(v))
    open("_s.sp","w").write(deck)
    r = subprocess.run(["ngspice","-b","_s.sp"], capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    def g(tag):
        m = re.search(tag+r'\s*=\s*([-\d.eE+]+)', out)
        return float(m.group(1)) if m else float('nan')
    vbus=g('vbus_usb'); vsr=g('vsys_run'); vor=g('vout_run'); vss=g('vsys_sag'); vos=g('vout_sag')
    # verdict: does VOUT hold at setpoint during sag?
    set_=p['VOUT']
    ok = (vos > set_*0.95) if p['BATT'] else True
    verdict = ("VOUT holds" if vos>set_*0.95 else f"VOUT drops to {vos:.2f}") if p['BATT'] else f"VSYS dies (no batt): sag {vss:.2f}"
    print(f"{name:40}{vbus:6.2f}{vsr:8.2f}{vor:8.2f}{vss:8.2f}{vos:8.2f}  {verdict}")
