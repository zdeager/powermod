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
setopt NULL_GLOB 2>/dev/null || true   # zsh aborts a line on an unmatched glob
cd "$(dirname "$0")"
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
BOARD=powermod_v2.kicad_pcb
PASSES=${1:-4}

python3 netclasses.py powermod_v2.kicad_pro
python3 layout_v2.py

# Purge stale SES files FIRST. A leftover v2best.ses from a previous placement
# otherwise sails past the guard below and gets imported onto the new board:
# routes that match nothing, silently (seen: 185 DRC violations from exactly
# that, after a cleanup `rm` died on an unmatched zsh glob and deleted nothing).
rm -f v2best.ses powermod_v2.ses v2p*.ses

# -Djava.awt.headless=true is REQUIRED, not a nicety. Without it Freerouting
# finishes routing and then hangs trying to reach the macOS window server
# ("error messaging the mach port"), often before writing the SES at all — 3 of 3
# passes hung and produced nothing. With it: clean exit, SES written, ~40s.
# The watchdog below stays as a belt-and-braces guard (there is no `timeout` on
# this box), but it should no longer be what saves us.
route_once() {   # $1 = pass index -> writes v2p$1.ses, echoes unrouted count
  local i=$1 log=v2p$1.log ses=v2p$1.ses
  rm -f $ses
  java -Djava.awt.headless=true -jar freerouting.jar -de powermod_v2.dsn -do $ses -mp 80 > $log 2>&1 &
  local pid=$! t=0
  while [ $t -lt 240 ]; do
    kill -0 $pid 2>/dev/null || break            # exited on its own
    if [ -s $ses ] && grep -q 'Saving' $log 2>/dev/null; then
      sleep 2; kill $pid 2>/dev/null || true; break   # SES written: flush, then reap
    fi
    sleep 2; t=$((t+2))
  done
  # `|| true` throughout: with set -e, killing an already-exited java (the normal
  # case now that headless mode lets it exit on its own) returns nonzero and
  # would abort the build immediately after a SUCCESSFUL route.
  kill -9 $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  # `|| true`: with `set -e`, a grep that matches nothing (hung before it logged
  # a count) returns nonzero, which would abort the whole build silently.
  grep -oE '\([0-9]+ unrouted\)' $log 2>/dev/null | tail -1 | grep -oE '[0-9]+' || true
}

best=9999
for i in $(seq 1 $PASSES); do
  "$KPY" fr_pipeline.py export $BOARD >/dev/null
  n=$(route_once $i)
  if [ ! -s v2p$i.ses ]; then
    echo "  routing pass $i: ${n:-?} unrouted (hung before save — discarded)"
    continue
  fi
  echo "  routing pass $i: ${n:-?} unrouted"
  if [ -n "$n" ] && [ "$n" -lt "$best" ]; then best=$n; cp v2p$i.ses v2best.ses; fi
  [ "$n" = "0" ] && break
done
echo "best routing: $best unrouted"
[ -s v2best.ses ] || { echo "no pass produced a SES; aborting"; exit 1; }

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
