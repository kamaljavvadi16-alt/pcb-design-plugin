"""Generate an OPTIONAL <board>.kicad_sch documentation schematic from board_spec.SCHEMATIC.

In this toolchain the PCB (board_spec.FOOTPRINTS pad->net map) is the AUTHORITATIVE netlist; the
schematic is a human-readable reference sheet, not the source of truth. So this generator is opt-in:
define a `SCHEMATIC` dict in board_spec to draw one, otherwise it skips.

    SCHEMATIC = {
        "lib_symbols_file": "symbols_ref.txt",   # KiCad (symbol ...) defs for the lib_ids used
        "syms":  [(lib_id, ref, value, x, y, footprint, n_pins, hide_ref), ...],
        "pwr":   [(lib_id, value, x, y), ...],            # power:GND / power:+3V3 / power:PWR_FLAG
        "wires": [(x1, y1, x2, y2), ...],
        "labels":[(name, x, y, angle 0|180), ...],
        "junctions":[(x, y), ...],
        "nc":    [(x, y), ...],
        "texts": [(string, x, y, size), ...],
        "prop_pos": {ref: (ref_dx, ref_dy, val_dx, val_dy)},   # optional label-offset overrides
    }
Coordinates are KiCad schematic mm (a 0.1" grid = 2.54 mm). Re-run any time; deterministic apart
from UUIDs. Runs under system Python.
"""
import os
import uuid
import config

spec = config.spec
SCH = getattr(spec, "SCHEMATIC", None)
if not SCH:
    print("no board_spec.SCHEMATIC -> skipping schematic (FOOTPRINTS is the authoritative netlist)")
    raise SystemExit(0)

OUT = config.BOARD_SCH
SHEET = str(uuid.uuid4())
PROJECT = config.NAME


def U():
    return str(uuid.uuid4())


def fnum(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def prop(name, val, x, y, hide, justify=None):
    h = "\n\t\t\t\t(hide yes)" if hide else ""
    j = f"\n\t\t\t\t(justify {justify})" if justify else ""
    return (f'\t\t(property "{name}" "{val}"\n\t\t\t(at {fnum(x)} {fnum(y)} 0)\n'
            f"\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t){h}{j}\n\t\t\t)\n\t\t)")


PROP_POS = SCH.get("prop_pos", {})


def sym(lib_id, ref, value, x, y, footprint, n_pins, hide_ref):
    pins = "\n".join(f'\t\t(pin "{n}"\n\t\t\t(uuid "{U()}")\n\t\t)' for n in range(1, n_pins + 1))
    rdx, rdy, vdx, vdy = PROP_POS.get(ref, (2.54, -2.54, 2.54, 0))
    just = None if ref.startswith("#PWR") else "left"
    return f"""\t(symbol
\t\t(lib_id "{lib_id}")
\t\t(at {fnum(x)} {fnum(y)} 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "{U()}")
{prop("Reference", ref, x + rdx, y + rdy, hide_ref, just)}
{prop("Value", value, x + vdx, y + vdy, hide_ref, just)}
{prop("Footprint", footprint, x, y, True)}
{prop("Datasheet", "~", x, y, True)}
{prop("Description", "", x, y, True)}
{pins}
\t\t(instances
\t\t\t(project "{PROJECT}"
\t\t\t\t(path "/{SHEET}"
\t\t\t\t\t(reference "{ref}")
\t\t\t\t\t(unit 1)
\t\t\t\t)
\t\t\t)
\t\t)
\t)"""


def wire(x1, y1, x2, y2):
    return (f"\t(wire\n\t\t(pts\n\t\t\t(xy {fnum(x1)} {fnum(y1)}) (xy {fnum(x2)} {fnum(y2)})\n\t\t)\n"
            f"\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type solid)\n\t\t)\n\t\t(uuid \"{U()}\")\n\t)")


def label(name, x, y, ang):
    just = "right bottom" if ang == 180 else "left bottom"
    return (f'\t(label "{name}"\n\t\t(at {fnum(x)} {fnum(y)} {ang})\n'
            f"\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify {just})\n\t\t)\n"
            f'\t\t(uuid "{U()}")\n\t)')


def no_connect(x, y):
    return f'\t(no_connect\n\t\t(at {fnum(x)} {fnum(y)})\n\t\t(uuid "{U()}")\n\t)'


def junction(x, y):
    return (f"\t(junction\n\t\t(at {fnum(x)} {fnum(y)})\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n"
            f'\t\t(uuid "{U()}")\n\t)')


def text(s, x, y, size):
    s2 = s.replace("\n", "\\n")
    return (f'\t(text "{s2}"\n\t\t(exclude_from_sim no)\n\t\t(at {fnum(x)} {fnum(y)} 0)\n'
            f"\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size} {size})\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n"
            f'\t\t(uuid "{U()}")\n\t)')


libs = ""
lib_file = SCH.get("lib_symbols_file")
if lib_file:
    path = lib_file if os.path.isabs(lib_file) else os.path.join(config.HERE, lib_file)
    raw = open(path, encoding="utf-8").read().strip()
    libs = "\n".join("\t\t" + ln for ln in raw.splitlines())

parts = [f"""(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "{SHEET}")
\t(paper "A4")
\t(title_block
\t\t(title "{getattr(spec, 'TITLE', config.NAME)}")
\t\t(date "{getattr(spec, 'DATE', '')}")
\t\t(rev "{getattr(spec, 'REV', '')}")
\t\t(company "{getattr(spec, 'COMPANY', '')}")
\t)
\t(lib_symbols
{libs}
\t)"""]

for t in SCH.get("texts", []):
    parts.append(text(*t))
for w in SCH.get("wires", []):
    parts.append(wire(*w))
for j in SCH.get("junctions", []):
    parts.append(junction(*j))
for lb in SCH.get("labels", []):
    parts.append(label(*lb))
for n in SCH.get("nc", []):
    parts.append(no_connect(*n))
for s in SCH.get("syms", []):
    parts.append(sym(*s))
pwr_i = 0
for lib_id, value, x, y in SCH.get("pwr", []):
    pwr_i += 1
    parts.append(sym(lib_id, f"#PWR0{pwr_i:02d}", value, x, y, "", 1, True))

parts.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)')
parts.append(")")

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(parts) + "\n")
print("wrote", os.path.abspath(OUT))
print(f"{len(SCH.get('syms', []))} components, {len(SCH.get('pwr', []))} power symbols, "
      f"{len(SCH.get('wires', []))} wires, {len(SCH.get('labels', []))} labels")
