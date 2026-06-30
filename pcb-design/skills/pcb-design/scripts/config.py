"""Shared configuration: locate the KiCad install and derive every path the toolchain needs
from the active board spec. Imported by BOTH plain-Python generators (gen_pcb/gen_sch/
set_netclasses) AND the pcbnew scripts that run under KiCad's bundled Python -- so this module
must NOT import pcbnew (path/glob/json only).

Layout assumption (matches the flex-box workflow this skill was distilled from):
    hardware/<board>/                      <- BOARD_DIR
        <board>.kicad_pcb / .kicad_sch / .kicad_pro
        fab/                               <- gerbers + BOM/CPL land here
        _tools/                            <- THIS directory: scripts + board_spec.py + freerouting.jar
The per-board data lives in `board_spec.py` next to these scripts; copy board_spec.example.py
to board_spec.py and edit it for a new board.

KiCad detection runs FIRST and independently of the board spec, so the preflight check
(check_prereqs.py) can verify the toolchain before any board exists. Set the env var PCB_SKIP_SPEC=1
to import this module WITHOUT requiring board_spec.py (used only by check_prereqs.py). Override KiCad
with KICAD_DIR (dir containing kicad-cli / the bundled python), or the spec module with BOARD_SPEC.
"""
import os
import sys
import glob
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))   # the _tools dir
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# tool paths under HERE (independent of any board)
FREEROUTING_JAR = os.path.join(HERE, "freerouting.jar")
DSN = os.path.join(HERE, "route.dsn")
SES = os.path.join(HERE, "route.ses")


# ---- KiCad install (detected before/without the board spec) ------------------------------
def _find_kicad_bin():
    env = os.environ.get("KICAD_DIR")
    if env and os.path.isdir(env):
        return env
    cands = []
    if sys.platform.startswith("win"):
        base = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad")
        cands += glob.glob(os.path.join(base, "*", "bin"))
        cands += glob.glob(r"C:\Program Files\KiCad\*\bin")
    elif sys.platform == "darwin":
        cands += glob.glob("/Applications/KiCad/KiCad.app/Contents/MacOS")
    else:  # linux: kicad-cli usually on PATH
        for p in ("/usr/bin", "/usr/local/bin"):
            if os.path.exists(os.path.join(p, "kicad-cli")):
                cands.append(p)
    cands = sorted(set(cands), reverse=True)   # newest version dir first
    return cands[0] if cands else None


KICAD_BIN = _find_kicad_bin()


def _exe(name):
    if not KICAD_BIN:
        return name  # fall back to PATH (Linux: kicad-cli/python on PATH)
    for ext in (".exe", ""):
        p = os.path.join(KICAD_BIN, name + ext)
        if os.path.exists(p):
            return p
    return os.path.join(KICAD_BIN, name)


KICAD_CLI = _exe("kicad-cli")
KICAD_PY = _exe("python")
if not KICAD_BIN and not sys.platform.startswith("win"):
    # Linux/macOS: KiCad ships pcbnew into the system python; prefer python3 over a bare "python"
    KICAD_PY = shutil.which("python3") or shutil.which("python") or "python3"


def _find_fp_dir():
    if not KICAD_BIN:
        return ""
    root = os.path.dirname(KICAD_BIN)          # .../<ver>
    for cand in (os.path.join(root, "share", "kicad", "footprints"),
                 os.path.join(root, "..", "share", "kicad", "footprints")):
        if os.path.isdir(cand):
            return os.path.abspath(cand)
    return os.path.join(root, "share", "kicad", "footprints")


FP_DIR = _find_fp_dir()

# ---- active board spec -------------------------------------------------------------------
_spec_name = os.environ.get("BOARD_SPEC", "board_spec")
spec = None
SPEC_OK = False
SPEC_ERROR = ""
NAME = BOARD_DIR = BOARD_PCB = BOARD_SCH = BOARD_PRO = BOARD_PRL = FAB_DIR = None
try:
    spec = __import__(_spec_name)
    SPEC_OK = True
except ImportError as e:
    SPEC_ERROR = str(e)
    if not os.environ.get("PCB_SKIP_SPEC"):
        raise SystemExit(
            f"config: could not import board spec '{_spec_name}'. Copy board_spec.example.py to "
            f"board_spec.py (or set BOARD_SPEC) and edit it for your board.\n  {e}")

if SPEC_OK:
    NAME = spec.NAME
    BOARD_DIR = os.path.dirname(HERE)
    BOARD_PCB = os.path.join(BOARD_DIR, NAME + ".kicad_pcb")
    BOARD_SCH = os.path.join(BOARD_DIR, NAME + ".kicad_sch")
    BOARD_PRO = os.path.join(BOARD_DIR, NAME + ".kicad_pro")
    BOARD_PRL = os.path.join(BOARD_DIR, NAME + ".kicad_prl")
    FAB_DIR = os.path.join(BOARD_DIR, "fab")


# ---- default .kicad_pro (so no GUI is needed to bootstrap a board) -----------------------
def default_pro():
    """A minimal-but-valid KiCad project dict. set_netclasses.py loads the existing .kicad_pro
    if present, else starts from this, then writes the Power class + DFM rule relaxations."""
    return {
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": 0.0,
                    "min_track_width": 0.0,
                    "min_through_hole_diameter": 0.3,
                    "min_via_diameter": 0.0,
                    "min_copper_edge_clearance": 0.5,
                },
                "rule_severities": {},
            },
        },
        "net_settings": {
            "classes": [{
                "name": "Default",
                "clearance": 0.2,
                "track_width": 0.25,
                "via_diameter": 0.7,
                "via_drill": 0.3,
                "microvia_diameter": 0.3,
                "microvia_drill": 0.1,
                "diff_pair_gap": 0.25,
                "diff_pair_width": 0.2,
            }],
            "netclass_patterns": [],
        },
        "meta": {"filename": (NAME or "board") + ".kicad_pro", "version": 3},
    }


def require_toolchain():
    """Hard gate: KiCad must be present before generating or loading a board. Entry-point scripts
    call this so a missing toolchain fails CLEARLY (pointing at the preflight) instead of cryptically.
    The full preflight (Java + freerouting too) is check_prereqs.py, which build_routed.sh runs."""
    cli = KICAD_CLI if os.path.isfile(KICAD_CLI) else shutil.which("kicad-cli")
    if not cli or not FP_DIR or not os.path.isdir(FP_DIR):
        raise SystemExit(
            "PCB toolchain not found (KiCad CLI and/or footprint library missing).\n"
            "Run the mandatory preflight first:\n"
            "    python check_prereqs.py            # report what's missing\n"
            "    python check_prereqs.py --install   # install it (confirms each)\n"
            "If KiCad is installed in a non-standard location, set KICAD_DIR to its bin directory.")


def gerber_layer_list():
    """Comma-separated layer list for `kicad-cli pcb export gerbers`. CRITICAL: a 4-layer board
    MUST include In1.Cu,In2.Cu or the fab builds a 2-layer board with no plane + no inner routing
    (the bug that made a flex-box upload read as 'PCB layers: 2')."""
    cu = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] if spec.LAYERS == 4 else ["F.Cu", "B.Cu"]
    rest = ["F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask",
            "F.Adhesive", "B.Adhesive", "F.Courtyard", "B.Courtyard", "F.Fab", "B.Fab",
            "Edge.Cuts", "Margin", "User.Comments", "User.Drawings", "User.Eco1", "User.Eco2"]
    return ",".join(cu + rest + list(getattr(spec, "GERBER_EXTRA_LAYERS", [])))


def _shq(p):
    """Quote a path for POSIX sh, using forward slashes (Windows tools accept them)."""
    return "'" + str(p).replace("\\", "/").replace("'", "'\\''") + "'"


if __name__ == "__main__":
    if "--sh" in sys.argv:
        # emit shell variable assignments: eval "$(python config.py --sh)"
        out = {
            "NAME": NAME, "TOOLS": HERE, "BOARD_DIR": BOARD_DIR, "BOARD": BOARD_PCB,
            "FAB": FAB_DIR, "DSN": DSN, "SES": SES, "JAR": FREEROUTING_JAR,
            "KPY": KICAD_PY, "CLI": KICAD_CLI, "GERBER_LAYERS": gerber_layer_list(),
        }
        for k, v in out.items():
            print(f"{k}={_shq(v)}")
        sys.exit(0)
    print("board       :", NAME or "(no board_spec.py)")
    print("board dir   :", BOARD_DIR)
    print("kicad bin   :", KICAD_BIN)
    print("kicad-cli   :", KICAD_CLI)
    print("kicad python:", KICAD_PY)
    print("footprints  :", FP_DIR, "(exists:", os.path.isdir(FP_DIR), ")")
    print("freerouting :", FREEROUTING_JAR, "(exists:", os.path.exists(FREEROUTING_JAR), ")")
    if SPEC_OK:
        print("gerber layers:", gerber_layer_list())
    print("\nRun  python check_prereqs.py  to verify the full toolchain is installed.")
