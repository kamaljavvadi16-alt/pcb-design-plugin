"""Scale a silkscreen-logo footprint (*.kicad_mod) and write a placeable copy into _tools/.

Use it to size a brand logo for a tight spot, then reference the output from board_spec.LOGO
(gen_pcb.py places it; flip_back.py can move it to the back). Silk-only: no copper, no nets.

    python make_logo.py <src.kicad_mod> <scale> [out.kicad_mod]

To CREATE a logo footprint from a PNG in the first place: in KiCad use
  Image Converter (bitmap2component) -> export to a silkscreen footprint -> save as *.kicad_mod.
(See reference/design-rules.md "Brand logos on silk".) This script only rescales an existing one.
"""
import os
import re
import sys

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(1)

SRC = sys.argv[1]
SCALE = float(sys.argv[2])
DST = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
    os.path.dirname(os.path.abspath(SRC)), "logo.kicad_mod")

raw = open(SRC, encoding="utf-8").read()


def s(v):
    return f"{round(float(v) * SCALE, 4)}"


raw = re.sub(r"\(xy (-?\d+\.?\d*) (-?\d+\.?\d*)\)",
             lambda m: f"(xy {s(m.group(1))} {s(m.group(2))})", raw)
# scale the x,y of every (at x y [rot]) but leave the trailing rotation alone
raw = re.sub(r"\(at (-?\d+\.?\d*) (-?\d+\.?\d*)",
             lambda m: f"(at {s(m.group(1))} {s(m.group(2))}", raw)
# normalise the footprint-level placement so gen_pcb.py's logo_fp() "(at 0 0 0)" replace still matches
raw = raw.replace("(at 0.0 0.0 0)", "(at 0 0 0)", 1)

with open(DST, "w", encoding="utf-8", newline="\n") as f:
    f.write(raw if raw.endswith("\n") else raw + "\n")
print("wrote", os.path.abspath(DST), f"(scale {SCALE})")
