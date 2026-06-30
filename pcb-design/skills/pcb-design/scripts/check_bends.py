"""Measure the interior angle at every 2-segment trace bend, to find right-angle or acute corners.
Interior angle: 180 = straight, ~135 = a clean 45deg bend (good), ~90 = right angle (flag),
<90 = acute corner / acid trap (bad). Junctions (3+ segments) and pad/via ends are skipped.
Read-only.   <kicad_python> check_bends.py [board.kicad_pcb]
"""
import sys
import math
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config
from collections import defaultdict

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
OX, OY = spec.ORIGIN
b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM

segs = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
ends = defaultdict(list)
for s in segs:
    a, c = s.GetStart(), s.GetEnd()
    ends[(s.GetLayer(), a.x, a.y)].append((c.x, c.y))
    ends[(s.GetLayer(), c.x, c.y)].append((a.x, a.y))

cats = {"straight(>=160)": 0, "bend 45deg (100-160)": 0, "right ~90 (80-100)": 0, "acute (<80)": 0}
flags = []
for (layer, vx, vy), nbrs in ends.items():
    if len(nbrs) != 2:
        continue
    (x1, y1), (x2, y2) = nbrs
    interior = abs(math.degrees(math.atan2(y1 - vy, x1 - vx) - math.atan2(y2 - vy, x2 - vx)))
    if interior > 180:
        interior = 360 - interior
    if interior >= 160:
        cats["straight(>=160)"] += 1
    elif interior >= 100:
        cats["bend 45deg (100-160)"] += 1
    elif interior >= 80:
        cats["right ~90 (80-100)"] += 1
        flags.append((interior, mm(vx) - OX, mm(vy) - OY, "F" if layer == pcbnew.F_Cu else "B"))
    else:
        cats["acute (<80)"] += 1
        flags.append((interior, mm(vx) - OX, mm(vy) - OY, "F" if layer == pcbnew.F_Cu else "B"))

print("bend angle distribution:")
for k, v in cats.items():
    print(f"   {k:24} {v}")
if flags:
    print(f"\n{len(flags)} right-angle/acute bend(s):")
    for ang, x, y, lyr in sorted(flags)[:40]:
        print(f"   interior {ang:5.1f} deg  @ ({x:5.1f}, {y:5.1f})  {lyr}.Cu")
else:
    print("\nNo right-angle or acute bends -- all corners are straight or 45 deg.")
