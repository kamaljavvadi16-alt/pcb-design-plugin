"""THT<->SMD spacing gate, CPL-AWARE.

The >=3mm rule exists because the fab hand/wave-solders through-hole parts AFTER the SMD reflow --
the clearance stops that operation bridging onto an adjacent SMD land. It therefore applies only to
THT parts the fab actually PLACES, i.e. the ones in the CPL.

Applying it to every holed pad is expensive and wrong. On the board this skill came from, 12 holed
parts were 18% of the BOM but **65% of the placement budget**, and only ONE of them (the USB-C) was
machine-placed; the rest were hand-fitted after delivery or bare mounting holes. Correcting this
freed ~760 mm2 -- the difference between a shrink working and not.

Per-part thresholds:
    machine-placed THT (in the CPL) -> THT_SMD_MIN   (default 3.0)  real assembly gate
    hand-fitted THT                 -> THT_HAND_MIN  (default 1.5)  soldering-iron access
    any pad                         -> WARN          (0.5)          hard bridging floor

The CPL is read from FAB_DIR/<name>-CPL.csv. If it is missing, the old strict rule is used for all
THT pads and that is stated in the output -- so a missing CPL never silently relaxes the gate.
Read-only.
    <kicad_python> check_tht_smd.py [board.kicad_pcb] [cpl.csv]
"""
import csv
import os
import sys
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
THRESH = getattr(spec, "THT_SMD_MIN", 3.0)      # fab-placed THT: real assembly clearance
HAND = getattr(spec, "THT_HAND_MIN", 1.5)       # hand-fitted THT: iron access only
WARN = 0.5     # below this = real DFM problem (could bridge), whoever solders it

CPL = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    config.FAB_DIR or "", f"{config.NAME}-CPL.csv")
placed = None
if os.path.exists(CPL):
    placed = set()
    with open(CPL, newline="") as f:
        for row in csv.DictReader(f):
            d = (row.get("Designator") or "").strip()
            if d:
                placed.add(d)
    print(f"CPL: {os.path.basename(CPL)} -> {len(placed)} machine-placed parts")
else:
    print(f"!! CPL not found ({CPL}) -- applying {THRESH}mm to ALL THT pads (the old strict rule).")
    print("!! Generate the CPL (gen_bom_cpl.py) for per-part thresholds.")

b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM

tht, smd = [], []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    is_placed = True if placed is None else (ref in placed)
    for p in fp.Pads():
        if p.GetDrillSizeX() > 0 and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            tht.append((f"{ref}.{p.GetPadName()}", p, is_placed))
        elif p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
            smd.append((f"{ref}.{p.GetPadName()}", p))


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


n_fab = len({t.split(".")[0] for t, _, pl in tht if pl})
n_hand = len({t.split(".")[0] for t, _, pl in tht if not pl})
print(f"THT copper pads: {len(tht)}  ({n_fab} machine-placed parts @ {THRESH}mm, "
      f"{n_hand} hand-fit @ {HAND}mm)   SMD copper pads: {len(smd)}")
viol = []
for tn, tp, is_placed in tht:
    limit = THRESH if is_placed else HAND
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
    if bn is not None and best < limit:
        viol.append((best, tn, bn, limit, is_placed))

viol.sort()
crit = [v for v in viol if v[0] < WARN]
print(f"\ngaps below their part's threshold: {len(viol)}  "
      f"(of which <{WARN}mm critical: {len(crit)})")
for g, tn, sn, limit, is_placed in viol:
    who = "fab" if is_placed else "hand"
    flag = "  <<< CRITICAL" if g < WARN else ""
    print(f"   {g:4.2f}mm  (limit {limit:.1f}, {who:4})  {tn:10} -> {sn:10}{flag}")
if not viol:
    print("   none -- all THT pads clear their applicable threshold.")
sys.exit(1 if crit else 0)
