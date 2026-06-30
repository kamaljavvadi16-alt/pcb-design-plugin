"""Generate <board>.kicad_pcb from board_spec (placement + outline + pours + keepouts).

Plain-Python s-expression emitter (no pcbnew): reads every board-specific value from board_spec
via config, loads stock/custom footprints verbatim, places them at absolute board-local mm, and
writes a board that pcbnew/kicad-cli load cleanly. Re-run any time; output is deterministic apart
from UUIDs. Routing/pours added post-route by import_ses.py; this wipes routing to a clean slate.

Generalized from the flex-box toolchain. The proven `load_fp` loader (incl. the part-specific
WROOM-EP and USB-C-slot DFM fixups) is kept verbatim -- those branches only fire when those exact
parts are present, and are harmless otherwise.
"""
import os
import re
import uuid
import config

config.require_toolchain()   # mandatory: fail clearly if KiCad isn't installed (-> run check_prereqs.py)
spec = config.spec
OX, OY = spec.ORIGIN
W, H = spec.W, spec.H
CORNER_R = getattr(spec, "CORNER_R", 0.0)
HERE = config.HERE
FP_DIR = config.FP_DIR
OUT = config.BOARD_PCB
NETS = spec.NETS
NID = {n: i for i, n in enumerate(NETS)}


def _validate():
    """Catch the common board_spec mistakes early with a clear message (not a deep traceback)."""
    errs = []
    if not NETS or NETS[0] != "":
        errs.append('NETS[0] must be the empty string "" (KiCad net 0 = no-net). '
                    'Put "" first in board_spec.NETS, then your real nets.')
    if len(NETS) != len(set(NETS)):
        errs.append("NETS has duplicate names; each net name must be unique.")
    known = set(NETS)
    for item in spec.FOOTPRINTS:
        ref, padnets = item[2], item[7]
        for pad, net in padnets.items():
            if net not in known:
                errs.append(f'{ref} pad "{pad}" -> net "{net}" is not declared in NETS '
                            f'(add "{net}" to NETS, or fix the typo).')
    if errs:
        raise SystemExit("board_spec error(s) -- fix these and re-run:\n  - " + "\n  - ".join(errs))


_validate()


def U():
    return str(uuid.uuid4())


def bx(x):
    return round(OX + x, 3)


def by(y):
    return round(OY + y, 3)


def copper_layers():
    return ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] if spec.LAYERS == 4 else ["F.Cu", "B.Cu"]


def _layer_list(names):
    if names == ["*"]:
        names = copper_layers()
    return " ".join(f'"{n}"' for n in names)


# ---------------- layers + setup blocks (built-in canonical KiCad 9/10 tables) ----------------
def layers_block():
    cu = ['(0 "F.Cu" signal)']
    if spec.LAYERS == 4:
        cu += ['(1 "In1.Cu" signal)', '(2 "In2.Cu" signal)']
    cu += ['(31 "B.Cu" signal)']
    tech = [
        '(32 "B.Adhes" user "B.Adhesive")', '(33 "F.Adhes" user "F.Adhesive")',
        '(34 "B.Paste" user)', '(35 "F.Paste" user)',
        '(36 "B.SilkS" user "B.Silkscreen")', '(37 "F.SilkS" user "F.Silkscreen")',
        '(38 "B.Mask" user)', '(39 "F.Mask" user)',
        '(40 "Dwgs.User" user "User.Drawings")', '(41 "Cmts.User" user "User.Comments")',
        '(42 "Eco1.User" user "User.Eco1")', '(43 "Eco2.User" user "User.Eco2")',
        '(44 "Edge.Cuts" user)', '(45 "Margin" user)',
        '(46 "B.CrtYd" user "B.Courtyard")', '(47 "F.CrtYd" user "F.Courtyard")',
        '(48 "B.Fab" user)', '(49 "F.Fab" user)',
    ]
    body = "\n".join("\t\t" + s for s in cu + tech)
    return "\t(layers\n" + body + "\n\t)"


def setup_block():
    return ("\t(setup\n"
            "\t\t(pad_to_mask_clearance 0)\n"
            "\t\t(allow_soldermask_bridges_in_footprints no)\n"
            "\t\t(aux_axis_origin 0 0)\n"
            "\t\t(grid_origin 0 0)\n"
            "\t)")


# ---------------- non-plated mounting hole ----------------
def bighole_fp(ref, x, y, dia):
    r = round(dia / 2, 3)
    f = [f'\t(footprint "pcbskill:MountingHole_{dia}mm"',
         '\t\t(layer "F.Cu")',
         f'\t\t(uuid "{U()}")',
         f'\t\t(at {bx(x)} {by(y)} 0)',
         f'\t\t(property "Reference" "{ref}" (at 0 {-(r + 1.4)} 0) (layer "F.Fab") '
         f'(uuid "{U()}") (effects (font (size 1 1) (thickness 0.15))))',
         f'\t\t(property "Value" "{dia}mm" (at 0 {r + 1.4} 0) (layer "F.Fab") '
         f'(uuid "{U()}") (effects (font (size 1 1) (thickness 0.15))))',
         '\t\t(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)',
         f'\t\t(pad "" np_thru_hole circle (at 0 0) (size {dia} {dia}) (drill {dia}) '
         f'(layers "*.Cu" "*.Mask") (uuid "{U()}"))',
         f'\t\t(fp_circle (center 0 0) (end {round(r + 0.5, 3)} 0) '
         f'(stroke (width 0.15) (type solid)) (fill no) (layer "F.SilkS") (uuid "{U()}"))',
         "\t)"]
    return "\n".join(f)


# ---------------- silkscreen logo footprint (from a local *.kicad_mod) ----------------
def logo_fp(mod, x, y, ref="LOGO1", scale=1.0):
    path = mod if os.path.isabs(mod) else os.path.join(HERE, mod)
    raw = open(path, encoding="utf-8").read().strip()
    raw = raw.replace("(at 0 0 0)", f"(at {bx(x)} {by(y)} 0)", 1)
    raw = re.sub(r'"Reference" "[^"]+"', f'"Reference" "{ref}"', raw, count=1)
    raw = re.sub(r'\(uuid "[^"]+"\)', lambda m: f'(uuid "{U()}")', raw)
    if scale != 1.0:
        raw = re.sub(r'\(xy (-?\d+\.?\d*) (-?\d+\.?\d*)\)',
                     lambda m: f'(xy {round(float(m.group(1)) * scale, 4)} '
                               f'{round(float(m.group(2)) * scale, 4)})', raw)
    return "\t" + raw.replace("\n", "\n\t")


# ---------------- library footprint loader (kept verbatim from the flex toolchain) ----------------
def find_close(text, start):
    depth, j = 0, start
    while True:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1


def load_fp(mod_file, libid, ref, value, x, y, rot, padnets):
    # Resolve a LOCAL custom .kicad_mod (in _tools/) first, else the installed KiCad library tree.
    _local = os.path.join(HERE, mod_file)
    _path = _local if os.path.exists(_local) else os.path.join(FP_DIR, mod_file)
    if not os.path.exists(_path):
        raise SystemExit(
            f'Footprint not found for {ref}: "{mod_file}".\n'
            f'  Looked for: {_path}\n'
            f'  Expected form: "<Lib>.pretty/<Name>.kicad_mod" '
            f'(e.g. "Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod"), or a local *.kicad_mod in this dir.\n'
            f"  Find the exact name in KiCad's Footprint Library Browser, or list the library folder:\n"
            f"      {os.path.join(FP_DIR, mod_file.split('/')[0] if '/' in mod_file else '')}")
    raw = open(_path, encoding="utf-8").read().strip()
    raw = re.sub(r'^\(footprint "[^"]+"', f'(footprint "{libid}"', raw, count=1)
    raw = raw.replace('(layer "F.Cu")',
                      f'(layer "F.Cu")\n\t(uuid "{U()}")\n\t(at {bx(x)} {by(y)} {rot})', 1)
    raw = raw.replace("REF**", ref)
    raw = re.sub(r'(\(property "Value" ")[^"]*(")', rf'\g<1>{value}\g<2>', raw, count=1)
    # Keep the Reference designator on F.SilkS (shrunk to 0.7mm) for hand assembly; fix_silk.py
    # declutters any that land on a pad/hole. Value stays on F.Fab.
    ri = raw.find('(property "Reference"')
    if ri >= 0:
        re_end = find_close(raw, ri)
        block = raw[ri:re_end + 1]
        block = block.replace('(layer "F.Fab")', '(layer "F.SilkS")')
        block = re.sub(r'\(size 1 1\)', '(size 0.7 0.7)', block, count=1)
        raw = raw[:ri] + block + raw[re_end + 1:]
    # per-pad net insertion (pad positions stay local; footprint-level rot rotates them).
    out, i = [], 0
    while True:
        m = re.search(r'\(pad\s+("?[^\s"]*"?)\s', raw[i:])
        if not m:
            out.append(raw[i:])
            break
        s = i + m.start()
        e = find_close(raw, s)
        out.append(raw[i:s])
        pad = raw[s:e + 1]
        name = m.group(1).strip('"')
        if name in padnets:
            net = padnets[name]
            pad = pad[:-1] + f'(net {NID[net]} "{net}") ' + ")"
        out.append(pad)
        i = e + 1
    body = "".join(out)
    # Strip any footprint-embedded (zone ...) block: KiCad stores footprint zones in ABSOLUTE board
    # coords, so our text-injected (at x y) does NOT translate them. Re-add needed keepouts as
    # board-level zones via spec.KEEPOUTS instead (e.g. an RF antenna keepout).
    while True:
        zi = body.find("(zone")
        if zi < 0:
            break
        ze = find_close(body, zi)
        body = body[:zi] + body[ze + 1:]
    # --- part-specific DFM fixups (only fire for these exact parts; harmless otherwise) ---
    if "WROOM" in libid and "GND" in NID:
        # The ESP32-WROOM courtyard is the oversize antenna T-shape; at a board edge it sweeps
        # neighbours -> bogus courtyard DRC. Strip its F.CrtYd polys (real RF clearance = a
        # spec.KEEPOUTS antenna zone). Then replace the fragmented EP (9 sub-pads + 12 thru-vias)
        # with ONE 3.7mm GND pad (fixes JLC multi-segment-mask + via-in-pad warnings; grounds to pour).
        i = 0
        while True:
            ci = body.find("(fp_poly", i)
            if ci < 0:
                break
            ce = find_close(body, ci)
            if '(layer "F.CrtYd")' in body[ci:ce + 1]:
                body = body[:ci] + body[ce + 1:]
                i = ci
            else:
                i = ce + 1
        out2, j = [], 0
        while True:
            m = re.search(r'\(pad\s+"39"', body[j:])
            if not m:
                out2.append(body[j:]); break
            s = j + m.start(); e = find_close(body, s)
            out2.append(body[j:s]); j = e + 1
        body = "".join(out2)
        ep = (f'(pad "39" smd rect (at -1.5 2.46) (size 3.7 3.7) '
              f'(layers "F.Cu" "F.Mask" "F.Paste") (solder_paste_margin -0.3) '
              f'(net {NID["GND"]} "GND") (uuid "{U()}"))')
        li = body.rfind(")")
        body = body[:li] + "\t" + ep + "\n" + body[li:]
    if "HRO_TYPE-C-31-M-12" in libid:
        # JLC routed-slot min ~0.8mm flagged the 0.6mm USB-C shield-tab slots. Widen to 0.85x1.70mm
        # (the ~0.5mm shield leg still solders in; copper -> 1.25x2.10mm for a 0.2mm annular; SH
        # neighbours are GND so the wider copper is clearance-safe).
        body = (body.replace("(drill oval 0.6 1.7)", "(drill oval 0.85 1.7)")
                    .replace("(drill oval 0.6 1.2)", "(drill oval 0.85 1.7)")
                    .replace("(size 1 2.1)", "(size 1.25 2.1)")
                    .replace("(size 1 1.6)", "(size 1.25 2.1)"))
    return "\t" + body.replace("\n", "\n\t")


# ---------------- board outline ----------------
def edge_line(x1, y1, x2, y2):
    return (f'\t(gr_line (start {bx(x1)} {by(y1)}) (end {bx(x2)} {by(y2)}) '
            f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{U()}"))')


def edge_arc(x1, y1, xm, ym, x2, y2):
    return (f'\t(gr_arc (start {bx(x1)} {by(y1)}) (mid {bx(xm)} {by(ym)}) (end {bx(x2)} {by(y2)}) '
            f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{U()}"))')


def outline():
    if getattr(spec, "EDGE", None):
        out = []
        for prim in spec.EDGE:
            if prim[0] == "line":
                out.append(edge_line(*prim[1:]))
            elif prim[0] == "arc":
                out.append(edge_arc(*prim[1:]))
        return out
    R = CORNER_R
    if R <= 0:
        return [edge_line(0, 0, W, 0), edge_line(W, 0, W, H),
                edge_line(W, H, 0, H), edge_line(0, H, 0, 0)]
    m = round(R * (1 - 0.70710678), 4)
    return [
        edge_line(R, 0, W - R, 0), edge_line(W, R, W, H - R),
        edge_line(W - R, H, R, H), edge_line(0, H - R, 0, R),
        edge_arc(W - R, 0, W - m, m, W, R), edge_arc(W, H - R, W - m, H - m, W - R, H),
        edge_arc(R, H, m, H - m, 0, H - R), edge_arc(0, R, m, m, R, 0),
    ]


# ---------------- zones ----------------
def _poly(region):
    pts = region or [(0, 0), (W, 0), (W, H), (0, H)]
    return "(polygon (pts " + " ".join(f"(xy {bx(x)} {by(y)})" for x, y in pts) + "))"


def keepout_zone(k):
    rule = (f'(keepout (tracks {"allowed" if k.get("tracks") else "not_allowed"}) '
            f'(vias {"allowed" if k.get("vias") else "not_allowed"}) (pads allowed) '
            f'(copperpour {"allowed" if k.get("copperpour") else "not_allowed"}) (footprints allowed))')
    return (f'\t(zone\n\t\t(net 0)\n\t\t(net_name "")\n'
            f'\t\t(layers {_layer_list(k["layers"])})\n\t\t(uuid "{U()}")\n'
            f'\t\t(name "{k["name"]}")\n\t\t(hatch edge 0.5)\n'
            f'\t\t(connect_pads (clearance 0))\n\t\t(min_thickness 0.25)\n'
            f'\t\t(filled_areas_thickness no)\n\t\t{rule}\n'
            f'\t\t(fill (thermal_gap 0.5) (thermal_bridge_width 0.5))\n'
            f'\t\t{_poly(k.get("region"))}\n\t)')


def pour_zone(p):
    net = p["net"]
    return (f'\t(zone\n\t\t(net {NID[net]})\n\t\t(net_name "{net}")\n'
            f'\t\t(layer "{p["layer"]}")\n\t\t(uuid "{U()}")\n'
            f'\t\t(name "{p.get("name", p["layer"].replace(".", "_") + "_" + net)}")\n'
            f'\t\t(hatch edge 0.5)\n\t\t(priority {p.get("priority", 0)})\n'
            f'\t\t(connect_pads (clearance {p.get("clearance", 0.4)}))\n\t\t(min_thickness 0.25)\n'
            f'\t\t(filled_areas_thickness no)\n'
            f'\t\t(fill yes (thermal_gap {p.get("thermal_gap", 0.5)}) '
            f'(thermal_bridge_width {p.get("thermal_bridge", 0.6)}) (island_removal_mode 0))\n'
            f'\t\t{_poly(p.get("region"))}\n\t)')


# ---------------- assemble ----------------
parts = []
parts.append('(kicad_pcb\n\t(version 20241229)\n\t(generator "pcbnew")\n'
             '\t(generator_version "9.0")\n\t(general\n\t\t(thickness '
             f'{getattr(spec, "THICKNESS", 1.6)})\n\t\t(legacy_teardrops no)\n\t)\n\t(paper "A4")')
parts.append(layers_block())
parts.append(setup_block())
for i, n in enumerate(NETS):
    parts.append(f'\t(net {i} "{n}")')

for mod, lib, ref, val, x, y, rot, nets in spec.FOOTPRINTS:
    parts.append(load_fp(mod, lib, ref, val, x, y, rot, nets))

for ref, x, y, dia in getattr(spec, "HOLES", []):
    parts.append(bighole_fp(ref, x, y, dia))

if getattr(spec, "LOGO", None):
    lg = spec.LOGO
    parts.append(logo_fp(lg["mod"], lg["x"], lg["y"], lg.get("ref", "LOGO1"), lg.get("scale", 1.0)))

parts += outline()

for s, x, y, size in getattr(spec, "SILK", []):
    parts.append(f'\t(gr_text "{s}" (at {bx(x)} {by(y)} 0) (layer "F.SilkS") '
                 f'(uuid "{U()}") (effects (font (size {size} {size}) (thickness 0.15))))')

for k in getattr(spec, "KEEPOUTS", []):
    parts.append(keepout_zone(k))

for p in getattr(spec, "POURS", []):
    parts.append(pour_zone(p))

for x1, y1, x2, y2, w, layer, net in getattr(spec, "SEGMENTS", []):
    parts.append(f'\t(segment (start {bx(x1)} {by(y1)}) (end {bx(x2)} {by(y2)}) '
                 f'(width {w}) (layer "{layer}") (net {NID[net]}) (uuid "{U()}"))')
for x, y, net in getattr(spec, "VIAS", []):
    parts.append(f'\t(via (at {bx(x)} {by(y)}) (size 0.8) (drill 0.4) '
                 f'(layers "F.Cu" "B.Cu") (net {NID[net]}) (uuid "{U()}"))')

parts.append(")")

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(parts) + "\n")
print("wrote", os.path.abspath(OUT))
print(f"{len(spec.FOOTPRINTS)} footprints, {spec.LAYERS}-layer, "
      f"{len(getattr(spec, 'POURS', []))} pours, {len(getattr(spec, 'KEEPOUTS', []))} keepouts")
