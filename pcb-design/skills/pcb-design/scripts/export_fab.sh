#!/usr/bin/env bash
# Regenerate the fab package (gerbers + Excellon drill + zip) from the current board, via kicad-cli
# (no GUI plotting). The silk DFM cleanup is already baked into the board by import_ses.py, so the
# plotted silkscreen is JLCPCB-clean. Run after build_routed.sh, or standalone after fix_silk.py.
# KiCad must be CLOSED. The layer list (incl. inner layers for 4-layer) comes from config.py.
set -e
cd "$(dirname "$0")"
PY="$(command -v python || command -v python3 || command -v py || true)"
[ -n "$PY" ] || { echo "No system Python found on PATH (need python, python3, or the py launcher)."; exit 1; }
eval "$("$PY" config.py --sh)"
OUTDIR="$FAB/gerbers"

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/*          # clean sweep (dir holds only generated fab output)
# --no-protel-ext -> every layer exports as <board>-<layer>.gbr
"$CLI" pcb export gerbers --output "$OUTDIR/" --no-protel-ext --layers "$GERBER_LAYERS" "$BOARD"
"$CLI" pcb export drill --output "$OUTDIR/" --format excellon --excellon-units mm --drill-origin absolute "$BOARD"

# zip for upload: PowerShell on Windows, else `zip`
if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command "Compress-Archive -Force -Path '$OUTDIR/*' -DestinationPath '$FAB/${NAME}-gerbers.zip'"
elif command -v zip >/dev/null 2>&1; then
  ( cd "$OUTDIR" && zip -r -X "../${NAME}-gerbers.zip" . >/dev/null )
else
  echo "   (no zip tool found — gerbers are in $OUTDIR/, zip them manually for upload)"
fi
echo "== fab package regenerated: $FAB/${NAME}-gerbers.zip =="
