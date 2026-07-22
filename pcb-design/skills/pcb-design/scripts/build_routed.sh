#!/usr/bin/env bash
# Full reproducible board build: set net classes -> generate -> flip-to-back -> autoroute ->
# import (pours + stitching + silk) -> DRC. Freerouting is stochastic and occasionally leaves one
# hard net unrouted, so the whole generate->route->import cycle AUTO-RETRIES until DRC is clean
# (0 violations, 0 unconnected). On success, regenerates the fab package.
#
# Paths + the gerber layer list come from config.py (which reads board_spec.py). KiCad must be CLOSED.
# Requires: KiCad (kicad-cli + bundled python), Java (for freerouting.jar), a board_spec.py here.
set -e
cd "$(dirname "$0")"

# system python for the generators (python / python3 / py launcher)
PY="$(command -v python || command -v python3 || command -v py || true)"
[ -n "$PY" ] || { echo "No system Python found on PATH (need python, python3, or the py launcher)."; exit 1; }

# preflight: fail fast with clear guidance if KiCad / Java / freerouting / board_spec are missing
echo "== preflight: prerequisites =="
if ! "$PY" check_prereqs.py; then
  echo ""
  echo "Prerequisites missing (see above). Install them with:"
  echo "    $PY check_prereqs.py --install      # confirms each before installing"
  exit 1
fi

eval "$("$PY" config.py --sh)"

# freerouting time-cap so a stuck route can't hang the loop (skip gracefully if `timeout` is absent)
if command -v timeout >/dev/null 2>&1; then TO="timeout 340"; else TO=""; fi

echo "== 0. net classes (power width + via annular; creates .kicad_pro if missing) =="
"$PY" set_netclasses.py

# placement gate: generate once and fail fast on courtyard overlaps (the autorouter can't fix those)
echo "== placement gate (generate + courtyard-overlap check) =="
"$PY" gen_pcb.py
if ! "$KPY" check_overlap.py; then
  echo ""
  echo "Placement has courtyard overlaps (see above). Fix the x/y coordinates in board_spec.py"
  echo "before routing — overlapping parts can't be assembled and confuse the autorouter."
  exit 1
fi
if "$KPY" check_overlap.py | grep -qE "NPTH hole inside a courtyard: [1-9]"; then
  echo ""
  echo "A mounting hole sits inside a component courtyard. Move the hole or the part in"
  echo "board_spec.py — KiCad would only catch this at route time, after a full autoroute."
  exit 1
fi
# Hand-routed SEGMENTS/VIAS are coordinate-keyed and do NOT follow the parts they serve: move a
# footprint and a stale backbone can short a pad on every routing attempt. ~1s vs a routing round.
if ! "$KPY" check_handroutes.py; then
  echo ""
  echo "Hand-routed SEGMENTS/VIAS are stale or collide (see above). Fix them in board_spec.py."
  exit 1
fi

ATTEMPTS=6
clean=0
for n in $(seq 1 $ATTEMPTS); do
  echo "== build attempt $n/$ATTEMPTS =="
  "$PY" gen_pcb.py                                    # 1. placement (wipes routing -> clean slate)
  "$KPY" flip_back.py                                 # 1b. move FLIP_TO_BACK parts/logos to bottom
  "$KPY" export_dsn.py                                # 2. export DSN (+ mark GND plane = power)
  rm -f "$SES"                                        # 3. autoroute (freerouting, time-capped)
  $TO java -jar "$JAR" -de "$DSN" -do "$SES" -mp 100 >/dev/null 2>&1 || true
  if [ ! -f "$SES" ]; then echo "   freerouting hung/timed out or Java missing — retrying"; continue; fi
  "$KPY" import_ses.py                                # 4. import SES + pours + stitching + silk
  "$CLI" pcb drc --severity-error -o "$TOOLS/drc.rpt" "$BOARD" >/dev/null 2>&1 || true   # 5. DRC
  vio=$(grep -oE "Found [0-9]+ DRC violation" "$TOOLS/drc.rpt" | grep -oE "[0-9]+" | head -1)
  unc=$(grep -oE "Found [0-9]+ unconnected" "$TOOLS/drc.rpt" | grep -oE "[0-9]+" | head -1)
  echo "   -> DRC violations=${vio:-?}  unconnected=${unc:-?}"
  if [ "$vio" = "0" ] && [ "$unc" = "0" ]; then
    clean=1; echo "== clean build on attempt $n =="; break
  fi
  echo "   not clean — retrying autoroute..."
done
[ "$clean" = "1" ] || echo "== WARNING: still not clean after $ATTEMPTS attempts — inspect $TOOLS/drc.rpt =="

# 6. fab-house DFM gate. kicad-cli DRC does NOT police drill-to-drill spacing, annular ring or
#    via-hole-to-pad — a board can be 0/0 in KiCad and still carry real DANGERs. Gates the export.
echo "== 6. fab-house DFM check =="
dfm_ok=1
"$KPY" check_jlc_dfm.py || dfm_ok=0
[ "$dfm_ok" = "1" ] || echo "   !! DFM DANGERS — fab package will NOT be exported"

# 6b. silk DFM gate (verify; fix_silk already ran inside import_ses). Non-fatal: prints PASS/ISSUES.
echo "== 6b. silk DFM check =="
"$KPY" check_silk.py || echo "   (silk DFM reported issues — inspect before ordering)"

# 7. regenerate the fab package — only if BOTH the route and the DFM gate are clean, so a package
#    that looks finished can never be a package that carries a known defect.
if [ "$clean" = "1" ] && [ "$dfm_ok" = "1" ]; then
  echo "== 7. export fab (gerbers + drill + zip) =="
  bash export_fab.sh
  "$KPY" gen_bom_cpl.py || echo "   (BOM/CPL generation skipped)"
else
  echo "== 7. fab export SKIPPED (route clean=$clean, DFM ok=$dfm_ok) =="
fi
echo "== build done =="
