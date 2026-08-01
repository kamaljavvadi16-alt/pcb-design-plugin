"""BOARD SPEC -- the single file you edit per board. Copy this to `board_spec.py`, then edit.

Everything board-specific lives here as plain Python data; the generators/checkers read it via
config.py. This example is a COMPLETE, routable board: a 2-layer AMS1117 3.3 V regulator breakout
(input header -> LDO -> output header, with a power LED). It is also the skill's smoke-test board.

Coordinates are board-LOCAL millimetres, origin = top-left corner, +x right, +y DOWN. The board is
placed on the KiCad sheet at ORIGIN; you never think in sheet coordinates.

Read reference/design-rules.md and reference/dfm-rules.md before changing power/RF boards.
"""

# ===== identity =====
NAME = "example-regulator"        # output files are <NAME>.kicad_pcb / .kicad_sch / .kicad_pro
TITLE = "Example 3V3 Regulator Breakout"
REV = "1.0"
COMPANY = ""
DATE = "2026-06-30"

# ===== geometry =====
ORIGIN = (100.0, 50.0)            # where the board's top-left sits on the sheet (rarely changed)
W, H = 40.0, 30.0                 # board width x height (mm)
CORNER_R = 3.0                    # outline corner radius (0 = square corners)
THICKNESS = 1.6
LAYERS = 2                        # 2 or 4
GND_PLANE_LAYER = None            # 4-layer only: inner layer that is the SOLID GND plane, e.g. "In1.Cu"
EDGE = None                       # None = rounded rectangle; else a custom outline (see EDGE format below)

# ===== nets =====
# Index 0 MUST be "" (KiCad's no-net). Keep "GND" if you want ground pours.
NETS = ["", "GND", "VIN", "+3V3", "LEDA"]

# ===== net classes / design rules =====
DEFAULT_TRACK = 0.25              # signal track width (mm)
DEFAULT_VIA = (0.7, 0.3)          # (diameter, drill) -> 0.2mm annular
DEFAULT_CLEARANCE = 0.2           # copper-copper clearance (JLC min 0.127; 0.2 is safe)
POWER_TRACK = 0.5                 # width for nets in POWER_NETS
POWER_VIA = (0.9, 0.5)
POWER_NETS = ["VIN", "+3V3"]      # high-current nets routed thick
EDGE_CLEARANCE = 0.3              # copper-to-board-edge (JLC min 0.3)
MIN_THROUGH_HOLE = 0.3            # relax to 0.2 if a part has 0.2mm thermal/EP vias

# ===== footprints =====
# (mod_file, libid, ref, value, x, y, rot_deg, {pad_name: net})
#   mod_file : "<Lib>.pretty/<Name>.kicad_mod" (under KiCad's footprints dir) OR a local *.kicad_mod
#   libid    : "<Lib>:<Name>" (cosmetic; shows in KiCad)
#   only pads you list get a net; unlisted pads stay netless (fine for NC / mechanical pins)
def fp(lib, name):
    """Convenience: returns (mod_file, libid) for a stock KiCad footprint."""
    return (f"{lib}.pretty/{name}.kicad_mod", f"{lib}:{name}")

_HDR = "Connector_PinHeader_2.54mm"
FOOTPRINTS = [
    # input header (THT): VIN, GND
    (*fp(_HDR, "PinHeader_1x02_P2.54mm_Vertical"), "J1", "VIN_IN", 4, 12, 0,
     {"1": "VIN", "2": "GND"}),
    # AMS1117-3.3 LDO (SOT-223, tab = pin2 = VOUT). pin1=GND, pin2=+3V3(tab), pin3=VIN
    (*fp("Package_TO_SOT_SMD", "SOT-223-3_TabPin2"), "U1", "AMS1117-3.3", 16, 9, 0,
     {"1": "GND", "2": "+3V3", "3": "VIN"}),
    # input + output bulk caps (anti-droop): keep them HARD against the regulator pins
    (*fp("Capacitor_SMD", "C_0805_2012Metric"), "C1", "10uF", 10, 20, 0, {"1": "VIN", "2": "GND"}),
    (*fp("Capacitor_SMD", "C_0805_2012Metric"), "C2", "22uF", 24, 20, 0, {"1": "+3V3", "2": "GND"}),
    # power LED + series resistor
    (*fp("Resistor_SMD", "R_0603_1608Metric"), "R1", "330R", 28, 9, 0, {"1": "+3V3", "2": "LEDA"}),
    (*fp("LED_SMD", "LED_0805_2012Metric"), "D1", "GREEN", 32, 9, 0, {"1": "GND", "2": "LEDA"}),
    # output header (THT): +3V3, GND
    (*fp(_HDR, "PinHeader_1x02_P2.54mm_Vertical"), "J2", "3V3_OUT", 36, 13, 0,
     {"1": "+3V3", "2": "GND"}),
]

# ===== pours (emitted at generation time) =====
# Each: {layer, net, priority, clearance, thermal_gap, thermal_bridge, region(optional polygon)}
# region omitted -> full board. For 4-layer, add the inner GND plane here at priority 1.
POURS = [
    {"layer": "B.Cu", "net": "GND", "priority": 0, "clearance": 0.4},
]
ADD_TOP_GND_POUR = True            # import_ses adds an F.Cu GND pour AFTER routing (won't block traces)

# ===== keepouts (rectangles/polygons that exclude tracks/vias/copper) =====
# Each: {name, layers:[...], region:[(x,y),...], tracks, vias, copperpour}  (True = allowed)
# Classic use: antenna keepout (copperpour NOT allowed, all layers). None needed for this board.
KEEPOUTS = []

# ===== pre-placed copper (hand-routed critical loops, plane ties) =====
SEGMENTS = []                      # (x1,y1,x2,y2,width,layer,net)
VIAS = []                          # (x,y,net)

# ===== GND stitching / plane ties =====
STITCH_GND = True                  # drop collision-checked GND vias on a grid to tie the pours F<->B
STITCH_PITCH = (9, 9)              # (dx, dy) mm grid for stitching vias
GND_PLANE_TIES = False             # 4-layer: drop a GND via beside every SMD GND pad (tie to plane)

# ===== silkscreen =====
SILK = [                           # (text, x, y, size_mm)  -- placed in clear margins
    (NAME, 20, 3, 0.8),
    ("VIN", 4, 9, 0.6), ("3V3", 36, 10, 0.6),
]
LOGO = None                        # or {"mod": "logo.kicad_mod", "x":.., "y":.., "ref":"LOGO1", "scale":1.0, "back":False}

# ===== mounting holes (non-plated) =====
HOLES = [("HB1", 3, 3, 2.2), ("HB2", 37, 27, 2.2)]    # (ref, x, y, drill_dia)

# ===== flip to back =====
FLIP_TO_BACK = []                  # refs (and silk-only logos) to move to the bottom layer

# ===== straggler routes (ADVANCED, usually empty -- freerouting handles normal nets) =====
# Close nets freerouting leaves open in congestion. Each op (see route_fix.py):
#   {"op":"tie_gnd",       "ref":"U3", "pad":"15"}                      pad -> GND plane via
#   {"op":"connect",       "a":("U5","3"), "b":("U6","5"), "net":"OC"}  pad <-> pad
#   {"op":"connect_track", "a":("U4","11"), "net":"NTC"}                pad -> nearest existing track of net
STRAGGLERS = []

# ===== DFM =====
THT_SMD_MIN = 3.0                  # THT pad -> SMD pad, for THT parts the FAB PLACES (in the CPL)
THT_HAND_MIN = 1.5                 # ...for THT parts YOU hand-fit after delivery (iron access only)
# --- fab-house DFM limits (check_jlc_dfm.py). KiCad's DRC checks NONE of these. ---
MIN_HOLE_GAP = 0.30                # hole edge -> hole edge (vias + drilled pads)
MIN_ANNULAR = 0.20                 # (via pad - via drill) / 2
MIN_HOLE_TO_PAD = 0.20             # via DRILL edge -> pad copper, ANY net (drill reg + solder wicking)
EP_MIN_PADS = 6                    # a via inside a pad is OK only if the footprint has >= this many
                                   # pads (i.e. it is an IC thermal EP, not a 2-pad chip land).
                                   # Pad AREA cannot tell them apart: a QFN EP can be 1.49mm2 and an
                                   # 0805 land 1.45mm2.
ACUTE_DEG = 80.0                   # flag trace corners sharper than this

# ===== BOM / CPL (JLCPCB assembly) =====
LCSC = {}                          # per-ref LCSC#, e.g. {"U1": "C6186"}
LCSC_VAL = {}                      # per (value, package), e.g. {("10uF","0805"): "C440198"}
EXCLUDE_ASSEMBLY = {"J1", "J2"}    # refs NOT machine-assembled (THT hand-solder); excluded from BOM+CPL
CONN_DESC = {}                     # BOM "Comment" override, e.g. {"J1": "Conn 1x2 2.54 (power in)"}

# ===== custom outline (only if EDGE is not None) =====
# A list of edge primitives, board-local mm, traced in order to form a closed loop:
#   ("line", x1, y1, x2, y2)
#   ("arc",  x1, y1, xmid, ymid, x2, y2)
# Use this for notches/cutouts (e.g. a connector overhang). Left as None here -> rounded rectangle.
