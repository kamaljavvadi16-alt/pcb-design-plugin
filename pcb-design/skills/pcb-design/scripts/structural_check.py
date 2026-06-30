"""Structural sanity checks on the board (generic). Reports outline bbox, off-board parts,
mounting holes, unrouted ratsnest, track/via tally per layer, and net count.
Read-only.   <kicad_python> structural_check.py [board.kicad_pcb]
"""
import sys
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
OX, OY = spec.ORIGIN
W, H = spec.W, spec.H
b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM

edge = b.GetBoardEdgesBoundingBox()
print(f"1. Board outline bbox: {mm(edge.GetWidth()):.2f} x {mm(edge.GetHeight()):.2f} mm "
      f"@ ({mm(edge.GetX())-OX:.1f},{mm(edge.GetY())-OY:.1f})  (spec {W} x {H})")

print("2. Footprints outside board outline (pads + silk/courtyard extent):")
any_out = False
for fp in b.GetFootprints():
    xs, ys = [], []
    for it in list(fp.Pads()) + list(fp.GraphicalItems()):
        bb = it.GetBoundingBox()
        xs += [bb.GetX(), bb.GetRight()]; ys += [bb.GetY(), bb.GetBottom()]
    if not xs:
        continue
    x0, y0 = mm(min(xs)) - OX, mm(min(ys)) - OY
    x1, y1 = mm(max(xs)) - OX, mm(max(ys)) - OY
    if x0 < -0.5 or y0 < -0.5 or x1 > W + 0.5 or y1 > H + 0.5:
        print(f"   ! {fp.GetReference()} extends to ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
        any_out = True
if not any_out:
    print("   none -- all parts within board edge")

holes = sorted(fp.GetReference() for fp in b.GetFootprints()
               if fp.GetReference().startswith(("H", "MH")))
print(f"3. Mounting holes: {holes}")

b.BuildConnectivity()
print(f"4. Unrouted ratsnest lines: {b.GetConnectivity().GetUnconnectedCount(False)}")

tracks = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
fcu = sum(1 for t in tracks if t.GetLayer() == pcbnew.F_Cu)
bcu = sum(1 for t in tracks if t.GetLayer() == pcbnew.B_Cu)
print(f"5. Tracks: {len(tracks)} (F.Cu {fcu}, B.Cu {bcu}), vias: {len(vias)}")
print(f"6. Nets: {b.GetNetCount()-1} (excl. unconnected net 0)")
