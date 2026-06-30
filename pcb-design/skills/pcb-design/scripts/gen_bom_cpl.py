"""Generate JLCPCB assembly files from the routed board:
  fab/<board>-BOM.csv  (Comment, Designator, Footprint, LCSC Part #)  -- grouped by part
  fab/<board>-CPL.csv  (Designator, Mid X, Mid Y, Layer, Rotation)     -- pick-and-place

LCSC part numbers come from spec.LCSC (per-ref) and spec.LCSC_VAL (per value+package); blanks are
left for JLCPCB's BOM tool to auto-match by value+package. spec.EXCLUDE_ASSEMBLY drops hand-soldered
THT / not-populated parts from BOTH files. Mounting holes (HB*) and logos are excluded automatically.

CPL convention matches `kicad-cli pcb export pos`: Mid X = absolute X mm, Mid Y = -(absolute Y) mm,
Rotation = the KiCad footprint orientation. NOTE: JLC's library 0deg orientation can differ from
KiCad's per part -> verify each part's rotation/polarity in JLCPCB's CPL preview before assembly.
Runs under KiCad's bundled Python.
"""
import os
import csv
import re
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config
from collections import defaultdict

spec = config.spec
P = config.BOARD_PCB
OUT = config.FAB_DIR
mm = pcbnew.ToMM
b = pcbnew.LoadBoard(P)

LCSC = getattr(spec, "LCSC", {})
LCSC_VAL = getattr(spec, "LCSC_VAL", {})
CONN_DESC = getattr(spec, "CONN_DESC", {})
EXCLUDE_ASSEMBLY = set(getattr(spec, "EXCLUDE_ASSEMBLY", []))
PACKAGE_MAP = getattr(spec, "PACKAGE_MAP", {})


def package(fpname):
    """Clean a KiCad footprint name into a short JLC-friendly package label."""
    n = fpname.split(":")[-1]
    m = re.match(r'^[RCL]_(\d{4})_', n) or re.match(r'^LED_(\d{4})_', n)
    if m:
        return m.group(1)
    for k, v in PACKAGE_MAP.items():
        if k in n:
            return v
    # generic fallbacks
    for k, v in (("SOT-23-6", "SOT-23-6"), ("SOT-223", "SOT-223"), ("SOT-89", "SOT-89"),
                 ("SOT-23", "SOT-23"), ("SOIC-8", "SOIC-8"), ("TSSOP", "TSSOP")):
        if k in n:
            return v
    return n


bom = defaultdict(list)            # (value, package, lcsc) -> [designators]
cpl = []
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref in EXCLUDE_ASSEMBLY:
        continue
    attr = fp.GetAttributes()
    val = CONN_DESC.get(ref, fp.GetValue())
    fpname = fp.GetFPIDAsString()
    pkg = package(fpname)
    lcsc = LCSC.get(ref) or LCSC_VAL.get((fp.GetValue(), pkg), "")
    if not (attr & pcbnew.FP_EXCLUDE_FROM_BOM) and not ref.startswith(("HB", "MH", "LOGO")):
        bom[(val, pkg, lcsc)].append(ref)
    if not (attr & pcbnew.FP_EXCLUDE_FROM_POS_FILES) and not ref.startswith(("HB", "MH", "LOGO")):
        pos = fp.GetPosition()
        cpl.append((ref, round(mm(pos.x), 4), round(-mm(pos.y), 4),
                    "Bottom" if fp.IsFlipped() else "Top",
                    round(fp.GetOrientationDegrees() % 360, 2)))


def natkey(r):
    m = re.match(r'([A-Za-z]+)(\d+)', r)
    return (m.group(1), int(m.group(2))) if m else (r, 0)


os.makedirs(OUT, exist_ok=True)
bom_path = os.path.join(OUT, config.NAME + "-BOM.csv")
with open(bom_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (val, pkg, lcsc), refs in sorted(bom.items(), key=lambda kv: natkey(sorted(kv[1], key=natkey)[0])):
        w.writerow([val, ",".join(sorted(refs, key=natkey)), pkg, lcsc])

cpl_path = os.path.join(OUT, config.NAME + "-CPL.csv")
with open(cpl_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in sorted(cpl, key=lambda r: natkey(r[0])):
        w.writerow(list(row))

print(f"BOM: {bom_path}  ({len(bom)} part lines, {sum(len(v) for v in bom.values())} components)")
print(f"CPL: {cpl_path}  ({len(cpl)} placements)")
print(f"with LCSC#: {sum(1 for k in bom if k[2])} lines; "
      f"blank (assign in JLC): {sum(1 for k in bom if not k[2])} lines")
