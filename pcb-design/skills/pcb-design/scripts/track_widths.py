"""Report track width distribution per net (verify power nets routed thick). Read-only.
    <kicad_python> track_widths.py [board.kicad_pcb]
"""
import sys
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config
from collections import defaultdict

P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
b = pcbnew.LoadBoard(P)
bynet = defaultdict(lambda: defaultdict(float))  # net -> width(mm) -> length(mm)
for t in b.GetTracks():
    if t.Type() != pcbnew.PCB_TRACE_T:
        continue
    w = round(pcbnew.ToMM(t.GetWidth()), 3)
    bynet[t.GetNetname()][w] += pcbnew.ToMM(t.GetLength())
print(f"{'net':<14} widths(mm): total length")
for net in sorted(bynet):
    parts = ", ".join(f"{w}mm:{l:.0f}mm" for w, l in sorted(bynet[net].items()))
    print(f"{net:<14} {parts}")
