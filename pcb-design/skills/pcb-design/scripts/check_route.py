"""Post-route quality gate. Reports:
  - tracks per copper layer (a GND-plane inner layer MUST have 0 signal tracks)
  - per power/switching net: total trace length + via count (short loops = good switching layout)
  - total vias, unrouted ratsnest
Read-only.   <kicad_python> check_route.py [board.kicad_pcb]
"""
import sys
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config
from collections import defaultdict

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM
LN = {pcbnew.F_Cu: "F.Cu", pcbnew.In1_Cu: "In1.Cu", pcbnew.In2_Cu: "In2.Cu", pcbnew.B_Cu: "B.Cu"}
LAYERS = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if spec.LAYERS == 4 \
    else (pcbnew.F_Cu, pcbnew.B_Cu)
PLANE = {"In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu}.get(getattr(spec, "GND_PLANE_LAYER", None))

trk = list(b.GetTracks())
seg = [t for t in trk if t.Type() == pcbnew.PCB_TRACE_T]
via = [t for t in trk if t.Type() == pcbnew.PCB_VIA_T]

per_layer = defaultdict(int)
for t in seg:
    per_layer[t.GetLayer()] += 1
print("Tracks per layer:")
for ly in LAYERS:
    flag = "  <<< should be 0 (GND plane)" if ly == PLANE and per_layer[ly] else ""
    print(f"   {LN[ly]:7} {per_layer.get(ly,0)}{flag}")
print(f"Total: {len(seg)} segments, {len(via)} vias")

watch = getattr(spec, "POWER_NETS", [])
if watch:
    nlen, nvia = defaultdict(float), defaultdict(int)
    for t in seg:
        nlen[t.GetNetname()] += mm(t.GetLength())
    for v in via:
        nvia[v.GetNetname()] += 1
    print("\nPower/switching net trace length + vias:")
    for n in watch:
        print(f"   {n:10} {nlen.get(n,0):6.1f} mm   vias={nvia.get(n,0)}")

b.BuildConnectivity()
print(f"\nUnrouted ratsnest: {b.GetConnectivity().GetUnconnectedCount(False)}")
