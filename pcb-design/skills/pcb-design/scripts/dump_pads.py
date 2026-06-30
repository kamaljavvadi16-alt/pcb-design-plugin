"""Dump every pad: ref, pad, net, board-local (x,y) mm, SMD/THT. Read-only.
    <kicad_python> dump_pads.py [board.kicad_pcb]
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
b = pcbnew.LoadBoard(P)
rows = []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    for pad in fp.Pads():
        p = pad.GetPosition()
        x = pcbnew.ToMM(p.x) - OX
        y = pcbnew.ToMM(p.y) - OY
        smd = "SMD" if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD else "THT"
        rows.append((ref, pad.GetPadName(), pad.GetNetname(), x, y, smd))
rows.sort(key=lambda r: (r[0], r[1]))
for ref, name, net, x, y, smd in rows:
    print(f"{ref:>4} {name:>3} {net:<14} ({x:6.2f},{y:6.2f}) {smd}")
