#!/bin/zsh
# Build v2 end-to-end: place -> route -> stitch GND -> DRC.
#
#   ./build_v2.sh [routing_passes]
#
# Order matters and is not obvious:
#   1. netclasses BEFORE export, or Freerouting routes 3A rails at 0.2mm.
#   2. export ALWAYS strips copper (Freerouting crashes on pre-routed boards).
#   3. Freerouting is stochastic -> run several passes, keep the best.
#   4. zones: solid pad connection (no starved thermals) + island removal.
#   5. stitch GND AFTER routing, so the via grid can see and avoid the traces.
set -e
cd "$(dirname "$0")"
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
BOARD=powermod_v2.kicad_pcb
PASSES=${1:-4}

python3 netclasses.py powermod_v2.kicad_pro
python3 layout_v2.py

best=9999
for i in $(seq 1 $PASSES); do
  "$KPY" fr_pipeline.py export $BOARD >/dev/null
  java -jar freerouting.jar -de powermod_v2.dsn -do v2p$i.ses -mp 80 > v2p$i.log 2>&1
  n=$(grep -oE '\([0-9]+ unrouted\)' v2p$i.log | tail -1 | grep -oE '[0-9]+')
  echo "  routing pass $i: ${n:-?} unrouted"
  if [ -n "$n" ] && [ "$n" -lt "$best" ]; then best=$n; cp v2p$i.ses v2best.ses; fi
  [ "$n" = "0" ] && break
done
echo "best routing: $best unrouted"

cp v2best.ses powermod_v2.ses
"$KPY" fr_pipeline.py export $BOARD >/dev/null      # strip, then import the winner
"$KPY" fr_pipeline.py import $BOARD

"$KPY" - <<'EOF'
import pcbnew
b = pcbnew.LoadBoard('powermod_v2.kicad_pcb')
for z in b.Zones():
    if not z.GetIsRuleArea():
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard('powermod_v2.kicad_pcb', b)
EOF

python3 stitch_gnd.py $BOARD

"$KPY" - <<'EOF'
import pcbnew
b = pcbnew.LoadBoard('powermod_v2.kicad_pcb')
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard('powermod_v2.kicad_pcb', b)
EOF

$CLI pcb drc $BOARD --refill-zones -o drc_v2.rpt >/dev/null
grep -E '^\[' drc_v2.rpt | sed 's/(.*//' | sort | uniq -c | sort -rn
grep 'Found' drc_v2.rpt
