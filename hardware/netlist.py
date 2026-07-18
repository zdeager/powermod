#!/usr/bin/env python3
"""PowerMOD — machine netlist, transcribed from ../powermod-schematic.md.

Single source of truth for generated KiCad artifacts:
  powermod.net        KiCad S-expression netlist (pcbnew: File > Import Netlist)
  powermod.kicad_sch  KiCad 7 schematic, global-label style (connectivity by
                      net labels on every pin; no drawn wires). Open, annotate
                      is already done, run ERC there — kicad-cli was not
                      available where this was generated.

Every (ref, pin, net) below is transcribed from powermod-schematic.md, whose
pin numbers were themselves extracted from datasheets. Footprint fields are
best-effort standard-library names — verify each in KiCad's footprint browser
before layout (checklist item 9).
"""
import uuid, sys, os

# ---------------------------------------------------------------- components
# ref: (value, footprint_besteffort, lcsc, {pin: (pinname, net)})
# net "NC" = deliberately unconnected (emitted as no-connect in the sch).
FP = {
  'R04':'Resistor_SMD:R_0402_1005Metric', 'R06':'Resistor_SMD:R_0603_1608Metric',
  'C04':'Capacitor_SMD:C_0402_1005Metric','C06':'Capacitor_SMD:C_0603_1608Metric',
  'C08':'Capacitor_SMD:C_0805_2012Metric','SOT':'Package_TO_SOT_SMD:SOT-23',
  'SOD':'Diode_SMD:D_SOD-323','TP':'TestPoint:TestPoint_Pad_2.0x2.0mm',
  'SJ':'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm',
}
COMPONENTS = {
 # --- ICs ---
 # LCSC verified 2026-07-17: C194063 is the TSSOP-8 BM8563 (wrong package, OOS).
 # C269877 = BM8563ESA, SOP-8 -> matches this SOIC-8 footprint. ~80k in stock.
 'U1': ('BM8563ESA', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'C269877', {
   '1':('OSCI','OSCI'), '2':('OSCO','OSCO'), '3':('INT','RTC_INT'), '4':('VSS','GND'),
   '5':('SDA','RTC_SDA'), '6':('SCL','RTC_SCL'), '7':('CLKOUT','NC'), '8':('VDD','RTC_VDD')}),
 # ATtiny1616 SOIC-20 (was ATtiny1617 QFN-24): 1.27mm pitch, no exposed pad,
 # hand-solderable, far easier to route. Pinout = KiCad ATtiny406-S base (verified
 # against the symbol lib). 4 signals reassigned off pins the 20-pin part lacks
 # (PB6/PB7/PC4/PC5 -> PA6/PA7/PC0/PC1); zero spare pins now. LCSC to confirm.
 # LCSC verified 2026-07-17: C2891852 was WRONG (a 4-pin 1.2mm header, not an MCU).
 # C614136 = ATTINY1616-SN (SOIC-20, 20MHz, 1.8-5.5V) — correct part, 0 stock at
 # LCSC at check time; in-stock sub = C145558 ATTINY1616-SFR (16MHz, 2.7V MIN
 # supply — thin margin at battery-empty, prefer the -SN from Mouser/DigiKey).
 'U2': ('ATtiny1616', 'Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm', 'C614136', {
   '1':('VCC','3V3'), '2':('PA4/VBAT_SENSE','VBAT_DIV'), '3':('PA5/VBUS_SENSE','VBUS_DIV'),
   '4':('PA6/LED_BAT_A','LED_BAT_A'), '5':('PA7/LED_BAT_B','LED_BAT_B'),
   '6':('PB5/CHG_STDBY','CHG_STDBY'), '7':('PB4/CHG_CHRG','CHG_CHRG'),
   '8':('PB3/LED_PWR_B','LED_PWR_B'), '9':('PB2/LED_PWR_A','LED_PWR_A'),
   '10':('PB1/SDA','SDA'), '11':('PB0/SCL','SCL'),
   '12':('PC0/CHG_CE','CHG_CE'), '13':('PC1/RTC_SCL','RTC_SCL'),
   '14':('PC2/RTC_INT','RTC_INT'), '15':('PC3/Q1_GATE_DRV','Q1_GATE_DRV'),
   '16':('PA0/UPDI','UPDI'), '17':('PA1/RTC_SDA','RTC_SDA'),
   '18':('PA2/BUTTON','BUTTON'), '19':('PA3/CONV_EN','CONV_EN'), '20':('GND','GND')}),
 'U3': ('TPS63020DSJR', 'Package_SON:VSON-14-1EP_3x4.45mm_P0.65mm_EP1.6x4.2mm', 'C15483', {
   '1':('VINA','VSYS'), '2':('GND','GND'), '3':('FB','FB'), '4':('VOUT','VOUT'),
   '5':('VOUT','VOUT'), '6':('L2','L2'), '7':('L2','L2'), '8':('L1','L1N'),
   '9':('L1','L1N'), '10':('VIN','VSYS'), '11':('VIN','VSYS'), '12':('EN','CONV_EN'),
   '13':('PS/SYNC','GND'), '14':('PG','NC'), '15':('PGND','GND')}),
 'U4': ('TP4056', 'Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm', 'C382139', {
   '1':('TEMP','GND'), '2':('PROG','PROG'), '3':('GND','GND'), '4':('VCC','VBUS'),
   '5':('BAT','VBAT'), '6':('STDBY','CHG_STDBY'), '7':('CHRG','CHG_CHRG'),
   '8':('CE','CHG_CE'), '9':('PAD','GND')}),
 'U5': ('XC6206P332MR', FP['SOT'], 'C5446', {   # pin order = convention, VERIFY
   '1':('VSS','GND'), '2':('VOUT','3V3'), '3':('VIN','VSYS')}),
 # --- FETs ---
 'Q1': ('AON7407', 'Package_DFN_QFN:DFN-8-1EP_3x3mm_P0.65mm_EP1.6x2.56mm', 'C176756', {
   '1':('S','VSYS'), '2':('S','VSYS'), '3':('S','VSYS'), '4':('G','Q1_GATE'),
   '5':('D','VBUS'), '6':('D','VBUS'), '7':('D','VBUS'), '8':('D','VBUS'), '9':('D','VBUS')}),
 'Q2': ('AON7407', 'Package_DFN_QFN:DFN-8-1EP_3x3mm_P0.65mm_EP1.6x2.56mm', 'C176756', {
   '1':('S','VSYS'), '2':('S','VSYS'), '3':('S','VSYS'), '4':('G','VBUS'),
   '5':('D','VBAT'), '6':('D','VBAT'), '7':('D','VBAT'), '8':('D','VBAT'), '9':('D','VBAT')}),
 'Q3': ('BSS138', FP['SOT'], 'C52895', {         # pin order = convention, VERIFY
   '1':('G','Q1_GATE_DRV'), '2':('S','GND'), '3':('D','Q3_DRAIN')}),
 # --- diodes / LEDs / crystal ---
 # TOGIALED TJ-S3227 dual-die LED, LCSC C601677 (~7.7k stock, yellow-green die
 # fixes the dim-green problem). Pinout from LCSC's EasyEDA model (verified
 # 2026-07-17): two INDEPENDENT diodes, top row anode=3 cathode=4, bottom row
 # anode=2 cathode=1. Local footprint matches that numbering (stock KiCad Avago
 # PLCC4 numbers the pads the OTHER way -> would reverse polarity, so NOT used).
 # Mapping below is polarity-correct (anodes->drive nets, cathodes->GND).
 # Red-vs-green DIE identity (top=RED assumed here) is not fixed by the EasyEDA
 # data; it's electrically irrelevant (both dies, identical 560R) and firmware-
 # adjustable — confirm against the datasheet colour drawing at assembly if the
 # silk label must match. Both D1/D2 are the same part, so any swap is uniform.
 'D1': ('TJ-S3227', 'powermod:LED_TJ-S3227_RG_3.2x2.7mm', 'C601677', {
   '1':('K_GRN','GND'), '2':('A_GRN','D1_GRN'), '3':('A_RED','D1_RED'), '4':('K_RED','GND')}),
 'D2': ('TJ-S3227', 'powermod:LED_TJ-S3227_RG_3.2x2.7mm', 'C601677', {
   '1':('K_GRN','GND'), '2':('A_GRN','D2_GRN'), '3':('A_RED','D2_RED'), '4':('K_RED','GND')}),
 'D3': ('1N4148WS', FP['SOD'], 'C51898295', {'1':('K','RTC_VDD'), '2':('A','3V3')}),
 'D4': ('1N4148WS', FP['SOD'], 'C51898295', {'1':('K','RTC_VDD'), '2':('A','VBACKUP')}),
 # D5 blocks the supercap back-draining through R27 into a dead 3V3 rail
 # (~3mA vs the RTC's 0.25uA — found in the 2026-07-17 pre-fab audit).
 # Charge path is now 3V3 -> R27 -> D5 -> JP1 -> VBACKUP; ceiling ~2.85V.
 'D5': ('1N4148WS', FP['SOD'], 'C51898295', {'1':('K','CHG_JPD'), '2':('A','CHG_JP')}),
 # Epson Q13FC13500004: 32.768kHz, CL=12.5pF (matches BM8563 internal caps),
 # 3215 2-pin, +-20ppm. LCSC C32346, ~286k stock (verified 2026-07-17).
 'Y1': ('Q13FC13500004', 'Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm', 'C32346', {
   '1':('X1','OSCI'), '2':('X2','OSCO')}),
 # --- connectors / electromech ---
 # merged-pad USB-C: reversible twins (A4≡B9, A9≡B4, A1≡B12, A12≡B1) share ONE pad,
 # so VBUS/GND are single pads -> no coincident-pad DRC flags, cleaner escape.
 'J1': ('USB_C_IN', 'powermod:USB_C_Receptacle_TYPE-C_16P_PowerMerged', 'C165948', {
   'A1':('GND','GND'),'A12':('GND','GND'),
   'A4':('VBUS','VBUS'),'A9':('VBUS','VBUS'),
   'A5':('CC1','CC1_IN'),'B5':('CC2','CC2_IN'),
   'A6':('D+','NC'),'A7':('D-','NC'),'B6':('D+','NC'),'B7':('D-','NC'),'SH':('SHIELD','GND')}),
 'J2': ('USB_C_OUT', 'powermod:USB_C_Receptacle_TYPE-C_16P_PowerMerged', 'C165948', {
   'A1':('GND','GND'),'A12':('GND','GND'),
   'A4':('VBUS','VOUT'),'A9':('VBUS','VOUT'),
   'A5':('CC1','CC1_OUT'),'B5':('CC2','CC2_OUT'),
   'A6':('D+','NC'),'A7':('D-','NC'),'B6':('D+','NC'),'B7':('D-','NC'),'SH':('SHIELD','GND')}),
 'J3': ('JST_PH_2', 'Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal', 'C173752', {
   '1':('BAT+','VBAT'), '2':('BAT-','GND')}),
 'J4': ('STEMMA_QT', 'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal', 'C51940130', {
   '1':('GND','GND'), '2':('VCC_NC','NC'), '3':('SDA','SDA'), '4':('SCL','SCL')}),
 'J5': ('UPDI_HDR', 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical', None, {
   '1':('UPDI','UPDI'), '2':('3V3','3V3'), '3':('GND','GND')}),
 'SW1':('BUTTON', 'Button_Switch_SMD:SW_SPST_PTS647_Sx50', 'C2799716', {
   '1':('A','BUTTON'), '2':('B','GND')}),
 'JP1':('CHG_JUMPER', FP['SJ'], None, {'1':('A','CHG_JPD'), '2':('B','VBACKUP')}),
 'JP2':('VSEL_JUMPER', FP['SJ'], None, {'1':('A','FB_MID'), '2':('B','VOUT')}),
 # C17554046 = Sumida CDMC6D28NP-1R5MC — the ONLY LCSC 1.5uH that fits this
 # footprint exactly (pads 2.0x3.4mm @ 5.7mm; verified 2026-07-17), but OOS at
 # LCSC. Consign it (stocked at Digi-Key/Mouser) or hand-solder (2 big pads,
 # trivial). In-stock alts (Chilisin SCDS74 6.9mm, CENKER 6x6 4.2mm) have a
 # different pad pitch -> would need a footprint change + switch-node re-route.
 'L1': ('1.5uH_4.5A', 'Inductor_SMD:L_Sumida_CDMC6D28_7.25x6.5mm', 'C17554046', {
   '1':('1','L1N'), '2':('2','L2')}),
 # --- test pads ---
 'TP1':('VBACKUP_PAD', FP['TP'], None, {'1':('P','VBACKUP')}),
 'TP2':('BAT_PAD',     FP['TP'], None, {'1':('P','VBAT')}),
 'TP3':('VOUT_PAD',    FP['TP'], None, {'1':('P','VOUT')}),
 'TP4':('GND_PAD',     FP['TP'], None, {'1':('P','GND')}),
 'TP5':('VBACKUP_GND_PAD', FP['TP'], None, {'1':('P','GND')}),
 'TP6':('VOUT_GND_PAD',    FP['TP'], None, {'1':('P','GND')}),
}
# JLC part numbers for the jellybean passives (verified on lcsc.com 2026-07-17).
# Resistors: UNI-ROYAL 0402WGF series (JLC Basic). Caps: Samsung CL-series
# (Basic) except 1u=C5673 (Extended, 25V, well-stocked; the Basic 50V had 50 in stock).
PASSIVE_LCSC = {
  '560':'C25126','1k':'C11702','1.2k':'C25862','5.1k':'C25905','10k':'C25744',
  '47k':'C25792','56k':'C25796','100k':'C25741','180k':'C25760','330k':'C25778',
  '620k':'C270590','1M':'C26083',
  '100n':'C1525','10u':'C15850','22u':'C45783','1u':'C5673','4.7u':'C19666',
}
def R(val,a,b,fp='R04'): return (val, FP[fp], PASSIVE_LCSC.get(val), {'1':('1',a),'2':('2',b)})
def C(val,a,b,fp='C04'): return (val, FP[fp], PASSIVE_LCSC.get(val), {'1':('1',a),'2':('2',b)})
COMPONENTS.update({
 'R1': R('1.2k','PROG','GND'),          # TP4056 1A
 'R2': R('5.1k','CC1_IN','GND'),  'R3': R('5.1k','CC2_IN','GND'),
 'R4': R('56k','CC1_OUT','VOUT'), 'R5': R('56k','CC2_OUT','VOUT'),
 'R6': R('1M','VBAT','VBAT_DIV'), 'R7': R('330k','VBAT_DIV','GND'),
 'R8': R('1M','VBUS','VBUS_DIV'), 'R9': R('330k','VBUS_DIV','GND'),
 'R10':R('100k','VSYS','Q1_GATE'),      # Q1 pull-up
 'R11':R('47k','Q1_GATE','Q3_DRAIN'),   # gate series
 'R12':R('100k','VBUS','GND'),          # Q2 gate pulldown (gate tied to VBUS)
 'R13':R('100k','Q1_GATE_DRV','GND'),   # Q3 gate pulldown
 'R14':R('100k','CONV_EN','GND'),       # EN defined during MCU reset
 'R15':R('10k','3V3','CHG_CHRG'), 'R16':R('10k','3V3','CHG_STDBY'),
 'R17':R('10k','3V3','RTC_SDA'),  'R18':R('10k','3V3','RTC_SCL'),
 'R19':R('10k','3V3','RTC_INT'),        # to 3V3, NOT VBACKUP (claims row 39)
 'R20':R('560','LED_PWR_A','D1_RED'), 'R21':R('560','LED_PWR_B','D1_GRN'),
 'R22':R('560','LED_BAT_A','D2_RED'), 'R23':R('560','LED_BAT_B','D2_GRN'),
 'R24':R('180k','FB','GND'), 'R25':R('1M','FB','FB_MID'), 'R26':R('620k','FB_MID','VOUT'),
 'R27':R('1k','3V3','CHG_JP'),          # supercap charge, behind JP1
 'R28':R('100k','VBUS','CHG_CE'),       # CE default-ON: TP4056 charges even with the MCU in reset/unprogrammed (2026-07-16); MCU PC4 push-pull overrides
 'C1': C('10u','VSYS','GND','C08'),  'C2': C('10u','VSYS','GND','C08'),
 'C3': C('22u','VOUT','GND','C08'),  'C4': C('22u','VOUT','GND','C08'),
 'C5': C('22u','VOUT','GND','C08'),
 'C6': C('4.7u','VBAT','GND','C06'), 'C7': C('10u','VBUS','GND','C08'),
 'C8': C('1u','VSYS','GND','C06'),   'C9': C('1u','3V3','GND','C06'),
 'C10':C('100n','VBAT_DIV','GND'),   'C11':C('100n','VBUS_DIV','GND'),
 'C12':C('100n','VSYS','Q1_GATE'),   # Q1 gate-source
 'C13':C('100n','RTC_VDD','GND'), 'C14':C('100n','3V3','GND'), 'C15':C('100n','VBUS','GND'),
 'C16':C('100n','VSYS','GND'),       # VINA decoupling — TI ref design (found at transcription)
})

# ------------------------------------------------------------------ validate
def build_nets():
    nets={}
    for ref,(val,fp,lcsc,pins) in COMPONENTS.items():
        for pin,(pname,net) in pins.items():
            nets.setdefault(net,[]).append((ref,pin))
    return nets

def validate():
    nets=build_nets(); errs=[]
    # non-NC nets must have >=2 nodes
    for net,nodes in nets.items():
        if net!='NC' and len(nodes)<2: errs.append(f"singleton net {net}: {nodes}")
    # board-killer golden facts (from powermod-schematic.md §3 checklist)
    G=[('Q1','1','VSYS'),('Q1','4','Q1_GATE'),('Q1','5','VBUS'),
       ('Q2','1','VSYS'),('Q2','4','VBUS'),('Q2','5','VBAT'),
       ('U4','1','GND'),('U3','13','GND'),('U3','12','CONV_EN'),
       ('U1','3','RTC_INT'),('U2','16','UPDI'),('U2','10','SDA'),('U2','11','SCL'),
       ('J4','2','NC'),('D3','2','3V3'),('D4','2','VBACKUP'),
       ('D3','1','RTC_VDD'),('D4','1','RTC_VDD')]
    for ref,pin,net in G:
        got=COMPONENTS[ref][3][pin][1]
        if got!=net: errs.append(f"GOLDEN FAIL {ref}.{pin}: {got} != {net}")
    # INT pull-up rail
    if COMPONENTS['R19'][3]['1'][1]!='3V3': errs.append("R19 not to 3V3")
    # pin-count sanity
    expect={'U1':8,'U2':20,'U3':15,'U4':9,'U5':3,'Q1':9,'Q2':9,'Q3':3}
    for ref,npins in expect.items():
        if len(COMPONENTS[ref][3])!=npins: errs.append(f"{ref} pin count {len(COMPONENTS[ref][3])}!={npins}")
    return nets, errs

# ---------------------------------------------------------------- generators
def u(): return str(uuid.uuid4())


def gen_bom(path):
    """JLCPCB assembly BOM (Comment, Designator, Footprint, LCSC Part #).
    Test points and solder jumpers are bare copper (not components) and have no
    CPL placement, so they are OMITTED — leaving them in makes JLC warn
    'designators don't exist in the CPL file'. Real parts with no LCSC (e.g. the
    J5 header) stay, with a blank LCSC = 'do not place / hand-solder' at upload."""
    from collections import defaultdict
    NONPLACED=('TestPoint','SolderJumper','Jumper')  # copper features, not parts
    groups=defaultdict(list)  # (value, footprint, lcsc) -> [refs]
    for ref,(val,fp,lcsc,pins) in COMPONENTS.items():
        if any(k in fp for k in NONPLACED): continue
        groups[(val,fp,lcsc or '')].append(ref)
    def keyf(r): return (r[0][0], int(''.join(c for c in r[0] if c.isdigit()) or 0))
    rows=[]
    for (val,fp,lcsc),refs in groups.items():
        des=','.join(sorted(refs,key=lambda r:(r[0],int(''.join(c for c in r if c.isdigit()) or 0))))
        rows.append((des,val,fp.split(':')[-1],lcsc))
    rows.sort(key=lambda x:x[0])
    out=['"Comment","Designator","Footprint","LCSC Part #"']
    for des,val,fp,lcsc in rows:
        out.append(f'"{val}","{des}","{fp}","{lcsc}"')
    open(path,'w').write('\n'.join(out)+'\n')
    placed=sum(1 for r in rows if r[3]); nolcsc=[r[0] for r in rows if not r[3]]
    return len(rows), placed, nolcsc

def gen_net(path):
    nets,_=validate()
    out=['(export (version "E")\n (components']
    for ref,(val,fp,lcsc,_) in sorted(COMPONENTS.items()):
        f=f'\n   (fields (field (name "LCSC") "{lcsc}"))' if lcsc else ''
        out.append(f'  (comp (ref "{ref}") (value "{val}") (footprint "{fp}"){f})')
    out.append(' )\n (nets')
    code=1
    for net,nodes in sorted(nets.items()):
        if net=='NC': continue
        ns=''.join(f'\n   (node (ref "{r}") (pin "{p}"))' for r,p in sorted(nodes))
        out.append(f'  (net (code "{code}") (name "{net}"){ns})'); code+=1
    out.append(' ))')
    open(path,'w').write('\n'.join(out))
    return code-1

def gen_sch(path):
    """KiCad 7 schematic: one symbol per component, global label on every pin."""
    nets,_=validate()
    PITCH=2.54
    lib={}; inst=[]; labels=[]; nc=[]
    for ref,(val,fp,lcsc,pins) in sorted(COMPONENTS.items()):
        name=f"PM_{ref}"
        keys=list(pins.keys()); nleft=(len(keys)+1)//2
        half=6.35 if len(keys)>2 else 3.81
        pdefs=[]; coords={}
        for i,pin in enumerate(keys):
            side=0 if i<nleft else 1
            row=i if side==0 else i-nleft
            px=-half if side==0 else half
            py=(nleft-1)*PITCH/2 - row*PITCH
            ang=0 if side==0 else 180
            pdefs.append(f'(pin passive line (at {px-2.54 if side==0 else px+2.54} {py} {ang}) (length 2.54)'
                         f' (name "{pins[pin][0]}" (effects (font (size 1.0 1.0))))'
                         f' (number "{pin}" (effects (font (size 1.0 1.0)))))')
            coords[pin]=(px-2.54 if side==0 else px+2.54, py)
        h=max(nleft,len(keys)-nleft)*PITCH/2+1.27
        lib[name]=(f'(symbol "powermod:{name}" (pin_numbers hide) (in_bom yes) (on_board yes)\n'
          f' (property "Reference" "{ref[0]}" (at 0 {h+2.54} 0) (effects (font (size 1.27 1.27))))\n'
          f' (property "Value" "{val}" (at 0 {-h-2.54} 0) (effects (font (size 1.27 1.27))))\n'
          f' (symbol "{name}_1_1" (rectangle (start {-half} {h}) (end {half} {-h})'
          f' (stroke (width 0.15) (type default)) (fill (type background)))\n  '
          +'\n  '.join(pdefs)+'))', coords)
    # place instances on a grid
    x0,y0,dx,dy,percol=30.48,30.48,71.12,66.04,7
    body=[]
    for i,(ref,(val,fp,lcsc,pins)) in enumerate(sorted(COMPONENTS.items())):
        X=x0+(i//percol)*dx; Y=y0+(i%percol)*dy
        name=f"PM_{ref}"; _,coords=lib[name]
        props=(f'(property "Reference" "{ref}" (at {X} {Y-14} 0) (effects (font (size 1.27 1.27))))\n'
               f'  (property "Value" "{val}" (at {X} {Y+14} 0) (effects (font (size 1.27 1.27))))\n'
               f'  (property "Footprint" "{fp}" (at {X} {Y} 0) (effects (font (size 1.27 1.27)) hide))')
        pininst='\n  '.join(f'(pin "{p}" (uuid {u()}))' for p in pins)
        body.append(f'(symbol (lib_id "powermod:{name}") (at {X} {Y} 0) (unit 1)'
                    f' (in_bom yes) (on_board yes) (uuid {u()})\n  {props}\n  {pininst})')
        for p,(pname,net) in pins.items():
            cx,cy=coords[p]; ax,ay=X+cx,Y-cy
            if net=='NC':
                nc.append(f'(no_connect (at {ax} {ay}) (uuid {u()}))')
            else:
                labels.append(f'(global_label "{net}" (shape passive) (at {ax} {ay} 0)'
                              f' (effects (font (size 1.0 1.0)) (justify left)) (uuid {u()}))')
    sch=('(kicad_sch (version 20230121) (generator powermod_netlist_py)\n'
         f' (uuid {u()})\n (paper "A2")\n'
         ' (title_block (title "PowerMOD") (rev "1") (comment 1 "GENERATED from netlist.py — source of truth is powermod-schematic.md"))\n'
         ' (lib_symbols\n  '+'\n  '.join(v[0] for v in lib.values())+'\n )\n '
         +'\n '.join(body)+'\n '+'\n '.join(labels)+'\n '+'\n '.join(nc)+'\n)')
    open(path,'w').write(sch)

def gen_symlib(path):
    """Write the powermod symbol library so lib_ids resolve on disk too."""
    nets,_=validate()
    # regenerate defs identically to gen_sch's lib builder
    import re
    sch=open(os.path.join(os.path.dirname(path),'powermod.kicad_sch')).read()
    i=sch.find('(lib_symbols'); depth=0; j=i
    for k,ch in enumerate(sch[i:],i):
        if ch=='(':depth+=1
        elif ch==')':
            depth-=1
            if depth==0: j=k+1; break
    body=sch[i+len('(lib_symbols'):j-1]
    open(path,'w').write('(kicad_symbol_lib (version 20231120) (generator powermod_netlist_py)'+body+')')

if __name__=='__main__':
    nets,errs=validate()
    if errs:
        print("VALIDATION FAILED:"); [print(" ",e) for e in errs]; sys.exit(1)
    ncount=gen_net(os.path.join(os.path.dirname(__file__) or '.','powermod.net'))
    d0=os.path.dirname(__file__) or '.'
    nlines,placed,nolcsc=gen_bom(os.path.join(d0,'powermod_bom.csv'))
    print(f'BOM: {nlines} lines, {placed} with LCSC; blank (hand-solder/DNP): {nolcsc}')
    d=os.path.dirname(__file__) or '.'
    gen_sch(os.path.join(d,'powermod.kicad_sch'))
    gen_symlib(os.path.join(d,'powermod.kicad_sym'))
    open(os.path.join(d,'sym-lib-table'),'w').write(
      '(sym_lib_table (version 7)\n  (lib (name "powermod")(type "KiCad")(uri "${KIPRJMOD}/powermod.kicad_sym")(options "")(descr "generated")))\n')
    libs=sorted({c[1].split(':')[0] for c in COMPONENTS.values()})
    def _uri(l):  # 'powermod' is a local project library; the rest are KiCad stock
        return f"${{KIPRJMOD}}/{l}.pretty" if l=='powermod' else f"${{KICAD10_FOOTPRINT_DIR}}/{l}.pretty"
    open(os.path.join(d,'fp-lib-table'),'w').write(
      '(fp_lib_table (version 7)\n'+''.join(
        f'  (lib (name "{l}")(type "KiCad")(uri "{_uri(l)}")(options "")(descr ""))\n'
        for l in libs)+')\n')
    if not os.path.exists(os.path.join(d,'powermod.kicad_pro')):
        open(os.path.join(d,'powermod.kicad_pro'),'w').write('{"meta":{"filename":"powermod.kicad_pro","version":3}}')
    npins=sum(len(c[3]) for c in COMPONENTS.values())
    print(f"OK: {len(COMPONENTS)} components, {npins} pins, {ncount} nets -> powermod.net, powermod.kicad_sch")
