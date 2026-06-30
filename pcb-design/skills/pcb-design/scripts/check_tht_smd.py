"""JLCPCB-style spacing gate: every THT copper pad should sit >= THT_SMD_MIN mm (edge-to-edge) from
any SMD copper pad, so THT hand-assembly can't bridge onto a nearby SMD land. Reports the closest SMD
pad to each THT pad and flags gaps below the threshold. Read-only.
    <kicad_python> check_tht_smd.py [board.kicad_pcb]
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
THRESH = getattr(spec, "THT_SMD_MIN", 3.0)
WARN = 0.5     # below this = real DFM problem (could bridge); WARN..THRESH = advisory
b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM

tht, smd = [], []
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetDrillSizeX() > 0 and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            tht.append((f"{fp.GetReference()}.{p.GetPadName()}", p))
        elif p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
            smd.append((f"{fp.GetReference()}.{p.GetPadName()}", p))


def gap(pa, pb):
    sa = pa.GetEffectiveShape(pcbnew.F_Cu); sb = pb.GetEffectiveShape(pcbnew.F_Cu)
    lo, hi = 0.0, 6.0
    if sa.Collide(sb, pcbnew.FromMM(lo)):
        return 0.0
    for _ in range(16):
        midv = (lo + hi) / 2
        if sa.Collide(sb, pcbnew.FromMM(midv)):
            hi = midv
        else:
            lo = midv
    return hi


print(f"THT copper pads: {len(tht)}   SMD copper pads: {len(smd)}   threshold {THRESH}mm")
viol = []
for tn, tp in tht:
    best, bn = 99.0, None
    tb = tp.GetBoundingBox(); tref = tn.split(".")[0]
    for sn, sp in smd:
        if sn.split(".")[0] == tref:
            continue
        sb = sp.GetBoundingBox()
        dx = mm(tb.GetCenter().x - sb.GetCenter().x)
        dy = mm(tb.GetCenter().y - sb.GetCenter().y)
        if dx * dx + dy * dy > 64:
            continue
        g = gap(tp, sp)
        if g < best:
            best, bn = g, sn
    if bn is not None and best < THRESH:
        viol.append((best, tn, bn))

viol.sort()
crit = [v for v in viol if v[0] < WARN]
print(f"\nTHT<->SMD gaps below {THRESH}mm: {len(viol)}  (of which <{WARN}mm critical: {len(crit)})")
for g, tn, sn in viol:
    flag = "  <<< CRITICAL" if g < WARN else ""
    print(f"   {g:4.2f}mm  {tn:10} -> {sn:10}{flag}")
sys.exit(1 if crit else 0)
