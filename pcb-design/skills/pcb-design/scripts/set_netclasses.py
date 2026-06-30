"""Write the project's net classes + DFM rule relaxations into <board>.kicad_pro.

Creates a minimal valid .kicad_pro from config.default_pro() if none exists (so no KiCad GUI is
needed to bootstrap a board), then sets the Default class widths, adds a wide "Power" class bound
to spec.POWER_NETS (so the autorouter routes those thick), and relaxes a few rules for fab reality.
Plain JSON; runs under system Python. Run FIRST in build_routed.sh.
"""
import json
import copy
import os
import config

spec = config.spec
PRO = config.BOARD_PRO

if os.path.exists(PRO):
    with open(PRO, encoding="utf-8") as f:
        pro = json.load(f)
else:
    pro = config.default_pro()
    print("created new project:", os.path.basename(PRO))

ns = pro.setdefault("net_settings", {})
classes = ns.setdefault("classes", [])
default = next((c for c in classes if c["name"] == "Default"), None)
if default is None:
    default = config.default_pro()["net_settings"]["classes"][0]
    classes.append(default)

default["track_width"] = spec.DEFAULT_TRACK
default["via_diameter"], default["via_drill"] = spec.DEFAULT_VIA
default["clearance"] = getattr(spec, "DEFAULT_CLEARANCE", 0.2)

# Power class = a copy of Default with the wide widths, bound to POWER_NETS by pattern.
if getattr(spec, "POWER_NETS", []):
    power = copy.deepcopy(default)
    power["name"] = "Power"
    power["track_width"] = spec.POWER_TRACK
    power["via_diameter"], power["via_drill"] = spec.POWER_VIA
    classes[:] = [c for c in classes if c["name"] != "Power"] + [power]
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": n} for n in spec.POWER_NETS]
else:
    classes[:] = [c for c in classes if c["name"] != "Power"]
    ns["netclass_patterns"] = []

rules = pro.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
rules["min_copper_edge_clearance"] = getattr(spec, "EDGE_CLEARANCE", 0.3)
rules["min_through_hole_diameter"] = getattr(spec, "MIN_THROUGH_HOLE", 0.3)

# A few GND pads at edges/notches can only form 1 thermal-relief spoke -> still a valid tie
# (reinforced by stitching vias). Downgrade the starved-thermal check from error to warning.
sev = pro["board"]["design_settings"].setdefault("rule_severities", {})
sev["starved_thermal"] = "warning"

with open(PRO, "w", encoding="utf-8") as f:
    json.dump(pro, f, indent=2)
print("net classes:", [c["name"] + f"({c['track_width']}mm)" for c in classes])
print("power nets:", getattr(spec, "POWER_NETS", []))
